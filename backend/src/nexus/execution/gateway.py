"""Execution gateway — the only path that could ever reach a venue (Section 12).

In Phase 2 there are **no venue adapters**. The gateway therefore terminates every intent
in governance: it validates authority, approval binding, idempotency and data quality,
then refuses with an explicit reason. This is the correct behaviour for this phase and is
covered by tests, so the refusal path is proven before any adapter exists.

Order of checks (all must pass):
1. halt / kill switch
2. live authority gates (environment, legal review, owner authority, phase gate, venue
   verification, mandate)
3. approval binding to the exact intent digest, not expired
4. idempotency (a replayed intent never produces a second order)
5. data quality for the instrument/venue
6. risk sizing against the live portfolio snapshot
7. adapter availability (Phase 2: none → refuse)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nexus.core.errors import RejectReason
from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.execution.halt import HaltManager
from nexus.execution.intent import ApprovalRecord, TradeIntent
from nexus.execution.orders import OrderState


class GatewayStatus(StrEnum):
    REFUSED = "REFUSED"
    APPROVED_NOT_SENT = "APPROVED_NOT_SENT"  # pre-live stages: logged, never transmitted
    SUBMITTED = "SUBMITTED"  # only possible once a verified live adapter exists


@dataclass(slots=True)
class SubmitResult:
    """Outcome of a submission attempt. Always carries reasons and an audit reference."""

    status: GatewayStatus
    intent_id: str
    order_id: str | None = None
    order_state: OrderState = OrderState.DRAFT
    reasons: tuple[str, ...] = ()
    idempotent_replay: bool = False
    checks: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: iso_utc(utc_now()))

    @property
    def refused(self) -> bool:
        return self.status is GatewayStatus.REFUSED

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "intent_id": self.intent_id,
            "order_id": self.order_id,
            "order_state": self.order_state.value,
            "reasons": list(self.reasons),
            "idempotent_replay": self.idempotent_replay,
        }


class ExecutionGateway:
    """Governance-only gateway for Phase 2. Adapters are attached in Phase 8."""

    def __init__(
        self,
        *,
        settings: Any,
        halt: HaltManager,
        audit: Any,
        events: Any | None = None,
        data_gate: Any | None = None,
        risk_engine: Any | None = None,
        adapters: dict[str, Any] | None = None,
        store: Any | None = None,
    ) -> None:
        self._settings = settings
        self._halt = halt
        self._audit = audit
        self._events = events
        self._data_gate = data_gate
        self._risk = risk_engine
        self._adapters = dict(adapters or {})  # empty in Phase 2 by design
        self._seen_intents: dict[str, SubmitResult] = {}
        self._lock = threading.RLock()
        # Stage 6, finding F-7: the idempotency ledger was in-memory only, so a restart lost it and
        # a replayed intent could be processed a second time. With a store the ledger is durable and
        # is rehydrated here, at construction, before any intent can be submitted.
        self._store = store
        self._rehydrated = 0
        if store is not None:
            self._rehydrated = self.rehydrate_from_store()

    @property
    def rehydrated_count(self) -> int:
        """How many ledger entries were reloaded from durable storage at boot."""
        return self._rehydrated

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)

    def register_adapter(self, venue: str, adapter: Any) -> None:
        """Attach a venue adapter. Only permitted from Phase 8 wiring, never at runtime
        by a model, plugin or strategy."""
        with self._lock:
            self._adapters[venue.upper()] = adapter

    def rehydrate_from_store(self) -> int:
        """Reload the durable idempotency ledger. Returns how many entries were restored.

        Restored entries keep their original status, order id, state and reasons, so a replay after
        a restart produces exactly the refusal an in-memory replay would have produced — including
        the ``IDEMPOTENCY_CONFLICT`` reason and the audit entry that accompanies it.
        """
        if self._store is None:
            return 0
        loaded = 0
        for row in self._store.execution_results():
            with self._lock:
                if row.intent_id in self._seen_intents:
                    continue
                self._seen_intents[row.intent_id] = SubmitResult(
                    status=GatewayStatus(row.status),
                    intent_id=row.intent_id,
                    order_id=row.order_id,
                    order_state=OrderState(row.order_state),
                    reasons=row.reasons,
                    idempotent_replay=False,
                    checks={"rehydrated_from": "store", "result_at": row.at},
                    at=row.at,
                )
                loaded += 1
        self._rehydrated = loaded
        return loaded

    def submit(
        self,
        intent: TradeIntent,
        *,
        approval: ApprovalRecord | None = None,
        portfolio: Any | None = None,
        quote: Any | None = None,
        mandate_active: bool = False,
        venue_live_verified: bool = False,
        phase_gate_complete: bool = False,
        reconciliation_ok: bool = True,
    ) -> SubmitResult:
        """Run every governance gate. Refuses unless all pass *and* an adapter exists."""
        with self._lock:
            previous = self._seen_intents.get(intent.intent_id)
        if previous is not None:
            replayed = SubmitResult(
                status=previous.status,
                intent_id=intent.intent_id,
                order_id=previous.order_id,
                order_state=previous.order_state,
                reasons=(RejectReason.IDEMPOTENCY_CONFLICT.value + ":intent already processed",),
                idempotent_replay=True,
                checks=previous.checks,
            )
            self._audit.record("execution.idempotent_replay", replayed.to_audit_payload())
            return replayed

        result = self._evaluate(
            intent,
            approval=approval,
            portfolio=portfolio,
            quote=quote,
            mandate_active=mandate_active,
            venue_live_verified=venue_live_verified,
            phase_gate_complete=phase_gate_complete,
            reconciliation_ok=reconciliation_ok,
        )
        with self._lock:
            self._seen_intents.setdefault(intent.intent_id, result)
        entry = self._audit.record(
            "execution.refused" if result.refused else "execution.accepted",
            result.to_audit_payload(),
        )
        if self._store is not None:
            # Law L-2: the audit entry is committed first, then the ledger row. A crash between the
            # two is repaired at boot by reproject_missing(), which reads the chain.
            self._store.save_execution_result(
                result.to_audit_payload(), audit_ref=getattr(entry, "record_id", None)
            )
        if self._events is not None:
            from nexus.events.bus import EventEnvelope

            self._events.publish(
                EventEnvelope(topic="nexus.execution.result", payload=result.to_audit_payload())
            )
        return result

    # -- internals ---------------------------------------------------------

    def _evaluate(
        self,
        intent: TradeIntent,
        *,
        approval: ApprovalRecord | None,
        portfolio: Any | None,
        quote: Any | None,
        mandate_active: bool,
        venue_live_verified: bool,
        phase_gate_complete: bool,
        reconciliation_ok: bool,
    ) -> SubmitResult:
        reasons: list[str] = []
        checks: dict[str, Any] = {"intent_digest": intent.digest(), "venue": intent.venue}

        # 1. Halt / kill switch
        halt_state = self._halt.state
        if halt_state.blocks_new_entries() and not intent.reduce_only:
            reasons.append(f"{RejectReason.HALT_ACTIVE.value}:{halt_state.reason}")
        if halt_state.blocks_all_trading():
            reasons.append(f"{RejectReason.KILL_SWITCH_ACTIVE.value}:kill switch engaged")

        # 2. Live authority
        from nexus.risk.authority import evaluate_authority

        authority = evaluate_authority(
            self._settings,
            halt_active=halt_state.blocks_new_entries(),
            kill_switch_active=halt_state.blocks_all_trading(),
            phase_gate_complete=phase_gate_complete,
            venue_live_verified=venue_live_verified,
            mandate_active=mandate_active,
            data_quality_ok=True,  # refined in step 5
            reconciliation_ok=reconciliation_ok,
        )
        checks["authority"] = authority.to_dict()

        # 3. Approval binding (required for live; optional pre-live but recorded)
        if approval is None:
            if authority.granted:
                reasons.append(RejectReason.APPROVAL_MISSING.value)
        elif not approval.binds(intent):
            reasons.append(
                f"{RejectReason.APPROVAL_INTENT_MISMATCH.value}:digest {approval.intent_digest[:12]}…"
            )
        elif approval.is_expired():
            reasons.append(RejectReason.APPROVAL_EXPIRED.value)
        elif authority.granted and not approval.step_up_verified:
            reasons.append("STEP_UP_REQUIRED:live approval needs MFA confirmation")

        # 4. Intent expiry
        if intent.is_expired():
            reasons.append(RejectReason.APPROVAL_EXPIRED.value + ":intent expired")

        # 5. Data quality
        data_ok = True
        if self._data_gate is not None:
            gate = self._data_gate.check_quote(quote)
            checks["data_quality"] = gate.to_dict()
            if not gate.new_risk_allowed:
                data_ok = False
                reasons.extend(gate.reasons)
        elif quote is None:
            data_ok = False
            reasons.append(f"{RejectReason.DATA_UNAVAILABLE.value}:no quote supplied")

        # 6. Risk sizing
        if self._risk is not None and portfolio is not None and data_ok:
            from nexus.risk.engine import PositionSizeRequest

            entry = intent.entry_price or intent.limit_price or (quote.mid if quote is not None else None)
            if entry is None or intent.protective_stop is None:
                reasons.append(f"{RejectReason.SIZING_UNDETERMINED.value}:entry or protective stop missing")
            else:
                request = PositionSizeRequest(
                    instrument_id=intent.instrument_id,
                    venue=intent.venue,
                    side=intent.side,
                    entry_price=entry,
                    stop_price=intent.protective_stop,
                    quote_currency=intent.quote_currency,
                )
                sizing = self._risk.evaluate(request, portfolio)
                checks["risk"] = sizing.to_audit_payload()
                if not sizing.approved:
                    reasons.extend(sizing.reasons)
        elif portfolio is None:
            reasons.append(f"{RejectReason.DATA_UNAVAILABLE.value}:no portfolio snapshot supplied")

        # 7. Adapter availability — Phase 2 has none, by design.
        adapter = self._adapters.get(intent.venue.upper())
        if adapter is None:
            reasons.append(
                f"{RejectReason.VENUE_NOT_SUPPORTED.value}:"
                f"no adapter for {intent.venue} (Phase 2: adapters land in Phase 8)"
            )

        if not authority.granted:
            reasons.extend(f"AUTHORITY:{r}" for r in authority.blocking_reasons if not r.startswith("HALT"))

        if reasons:
            return SubmitResult(
                status=GatewayStatus.REFUSED,
                intent_id=intent.intent_id,
                order_id=None,
                order_state=OrderState.REJECTED_BY_GOVERNANCE,
                reasons=tuple(dict.fromkeys(reasons)),
                checks=checks,
            )

        # Everything passed but we are pre-live: log the decision, never transmit.
        from nexus.core.environment import can_place_live_order

        if not can_place_live_order(self._settings.environment):
            return SubmitResult(
                status=GatewayStatus.APPROVED_NOT_SENT,
                intent_id=intent.intent_id,
                order_id=new_id("ORD"),
                order_state=OrderState.APPROVED,
                reasons=("PRE_LIVE_STAGE:intent recorded, not transmitted",),
                checks=checks,
            )

        # Unreachable in Phase 2: an adapter would have to exist AND all gates pass.
        return SubmitResult(
            status=GatewayStatus.REFUSED,
            intent_id=intent.intent_id,
            order_state=OrderState.REJECTED_BY_GOVERNANCE,
            reasons=("ADAPTER_NOT_CERTIFIED:live send path not implemented in Phase 2",),
            checks=checks,
        )
