"""The paper trading engine (Stage 11, D-059).

This is the machine the owner asked for: it takes the decisions the system actually produces,
executes them, and reports what they would have done — in real time, against real market data,
before any real order is ever sent.

What it is **not** is a venue adapter. That distinction is load-bearing rather than semantic:

* ``PHASE_GATE["venue_adapters"]`` stays ``False`` and ``PHASE_GATE["order_capability"]`` stays
  ``False``. Nothing here registers with :class:`~nexus.execution.gateway.ExecutionGateway`, so the
  gateway's step-7 refusal ("no adapter for VENUE") is untouched and CI's phase-gate assertion still
  measures the truth.
* There is no socket, no HTTP client and no credentials anywhere in this package. It could not send
  an order if it were misconfigured, because there is no send path to misconfigure.
* It never consults :class:`~nexus.risk.authority.LiveAuthority`. That gate answers "may we spend
  real money", and asking it from a simulator would either be meaningless or, worse, would imply
  that a ``GRANTED`` from here means something about live trading. It does not.

The engine does run the *governance* checks that are not about money — halt state, data quality,
approval binding, idempotency, risk sizing — because those are exactly what should be rehearsed. A
paper trade that skipped them would prove nothing about the real path.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.execution.halt import HaltManager
from nexus.execution.orders import OrderState
from nexus.paper.account import PaperAccount, PaperSnapshot
from nexus.paper.fill_model import FillOutcome, NoFillReason, Side, SimulatedFillModel

__all__ = [
    "InMemoryPaperLedger",
    "PaperEngineStatus",
    "PaperExecutionResult",
    "PaperLedger",
    "PaperTradingEngine",
]


class PaperEngineStatus(StrEnum):
    """Outcome of one paper submission.

    ``SIMULATED`` is the success case and reads oddly on purpose: the word that belongs on a paper
    trade is the one that says it was not real.
    """

    SIMULATED = "SIMULATED"
    SIMULATED_PARTIAL = "SIMULATED_PARTIAL"
    UNFILLED = "UNFILLED"
    REFUSED = "REFUSED"


class PaperLedger(Protocol):
    """Where paper orders and fills are kept.

    A Protocol rather than a base class so the SQL implementation can live beside the store without
    this module importing it — which keeps the engine importable, and testable, with no database at
    all.
    """

    def record_order(self, order: dict[str, Any]) -> None: ...

    def record_fill(self, fill: dict[str, Any]) -> None: ...

    def orders(self, *, limit: int = 200) -> list[dict[str, Any]]: ...

    def fills(self, *, limit: int = 500) -> list[dict[str, Any]]: ...


class InMemoryPaperLedger:
    """The default ledger: a bounded in-process log.

    Used when no store is configured, which is the case in tests and in a ``DISABLED`` or ``OBSERVE``
    environment. It is explicitly *not* durable and says so in ``describe()`` — a paper run that
    restarts and finds its history gone should not be mistaken for a strategy that made nothing.
    """

    def __init__(self, *, order_limit: int = 5_000, fill_limit: int = 20_000) -> None:
        self._orders: list[dict[str, Any]] = []
        self._fills: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._order_limit = order_limit
        self._fill_limit = fill_limit

    def record_order(self, order: dict[str, Any]) -> None:
        with self._lock:
            self._orders.append(order)
            if len(self._orders) > self._order_limit:
                del self._orders[: len(self._orders) - self._order_limit]

    def record_fill(self, fill: dict[str, Any]) -> None:
        with self._lock:
            self._fills.append(fill)
            if len(self._fills) > self._fill_limit:
                del self._fills[: len(self._fills) - self._fill_limit]

    def orders(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._orders[-limit:])

    def fills(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._fills[-limit:])

    def describe(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "memory",
                "durable": False,
                "orders": len(self._orders),
                "fills": len(self._fills),
            }


@dataclass(slots=True)
class PaperExecutionResult:
    """What the engine did with one intent."""

    status: PaperEngineStatus
    intent_id: str
    order_id: str
    order_state: OrderState
    instrument_id: str
    venue: str
    side: str
    quantity: Decimal
    outcome: FillOutcome | None = None
    reasons: tuple[str, ...] = ()
    checks: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: iso_utc(utc_now()))
    simulated: bool = True
    environment: str = "PAPER"

    @property
    def refused(self) -> bool:
        return self.status is PaperEngineStatus.REFUSED

    @property
    def filled_quantity(self) -> Decimal:
        return Decimal("0") if self.outcome is None else self.outcome.filled_quantity

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "intent_id": self.intent_id,
            "order_id": self.order_id,
            "order_state": self.order_state.value,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "side": self.side,
            "quantity": str(self.quantity),
            "filled_quantity": str(self.filled_quantity),
            "average_price": None
            if self.outcome is None or self.outcome.average_price is None
            else str(self.outcome.average_price),
            "total_commission": None if self.outcome is None else str(self.outcome.total_commission),
            "no_fill_reason": None
            if self.outcome is None or self.outcome.no_fill_reason is None
            else self.outcome.no_fill_reason.value,
            "reasons": list(self.reasons),
            "simulated": True,
            "environment": "PAPER",
            "at": self.at,
        }


class PaperTradingEngine:
    """Executes governance-approved intents against real quotes, in simulation.

    Thread-safe: the account is replaced under a lock, never mutated, so a reader always sees a
    consistent snapshot and two concurrent fills cannot both spend the same cash.
    """

    def __init__(
        self,
        *,
        account: PaperAccount,
        fill_model: SimulatedFillModel | None = None,
        halt: HaltManager | None = None,
        ledger: PaperLedger | None = None,
        audit: Any | None = None,
        events: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self._account = account
        self._fill_model = fill_model or SimulatedFillModel()
        self._halt = halt
        self._ledger: PaperLedger = ledger or InMemoryPaperLedger()
        self._audit = audit
        self._events = events
        self._settings = settings
        self._lock = threading.RLock()
        self._seen: dict[str, PaperExecutionResult] = {}

    # -- what this engine is ----------------------------------------------

    #: The one property that must never change. Asserted by tests and published by the API so a
    #: caller can check it rather than trust it.
    simulated = True
    can_place_live_orders = False
    is_venue_adapter = False

    @property
    def adapter_count(self) -> int:
        """Always zero: there is nothing here that can talk to a venue."""
        return 0

    def describe(self) -> dict[str, Any]:
        ledger_description = (
            self._ledger.describe() if hasattr(self._ledger, "describe") else {"backend": "unknown"}
        )
        return {
            "engine": "paper",
            "simulated": True,
            "environment": "PAPER",
            "can_place_live_orders": False,
            "is_venue_adapter": False,
            "adapter_count": 0,
            "account_id": self._account.account_id,
            "currency": self._account.currency,
            "fill_model": self._fill_model.describe(),
            "ledger": ledger_description,
            "halt_connected": self._halt is not None,
        }

    @property
    def account(self) -> PaperAccount:
        with self._lock:
            return self._account

    def snapshot(self, marks: dict[tuple[str, str], Decimal] | None = None) -> PaperSnapshot:
        with self._lock:
            return self._account.snapshot(marks)

    def orders(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """The blotter, newest last. Reading the ledger is a public operation, not a private one."""
        return self._ledger.orders(limit=limit)

    def fills(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Every simulated execution, each still carrying the real quote it filled against."""
        return self._ledger.fills(limit=limit)

    def reset(self, *, starting_cash: Decimal | None = None) -> PaperSnapshot:
        """Return the account to its starting capital and forget what it has already simulated.

        The idempotency map is cleared too, and that is deliberate: after a reset the engine is a
        new machine, so an intent id it has seen before should be allowed to run again rather than
        being answered from a history that no longer exists. A reset is visible in the account's
        ``created_at``, which is why a paper result should never be quoted without it.
        """
        capital = self._account.starting_cash if starting_cash is None else starting_cash
        with self._lock:
            self._account = PaperAccount(
                account_id=self._account.account_id,
                currency=self._account.currency,
                simulated_cash=capital,
                starting_cash=capital,
            )
            self._seen.clear()
            return self._account.snapshot()

    # -- running a trade ---------------------------------------------------

    def run(
        self,
        intent: Any,
        *,
        quote: Any,
        mark: Decimal | None = None,
        approval: Any | None = None,
        sizing_ok: bool = True,
        sizing_reasons: tuple[str, ...] = (),
        data_quality_ok: bool = True,
        now: Any | None = None,
    ) -> PaperExecutionResult:
        """Execute one intent in simulation and return what happened.

        ``quote`` is the real top-of-book observation the fill executes against; ``mark`` is the real
        last price used to value the position afterwards. Neither is ever synthesised here — if the
        caller has no quote, the order does not fill, and the result says why.

        ``now`` is the clock staleness is judged against. It defaults to the wall clock, but a loop
        replaying archived history must be able to pass the historical moment: otherwise every
        replayed quote looks minutes old and the fill model refuses all of it as stale, which is the
        right answer for live data and the wrong one for a replay.
        """
        intent_id = getattr(intent, "intent_id", None) or new_id("PPI")
        with self._lock:
            previous = self._seen.get(intent_id)
        if previous is not None:
            replayed = PaperExecutionResult(
                status=previous.status,
                intent_id=intent_id,
                order_id=previous.order_id,
                order_state=previous.order_state,
                instrument_id=previous.instrument_id,
                venue=previous.venue,
                side=previous.side,
                quantity=previous.quantity,
                outcome=previous.outcome,
                reasons=("IDEMPOTENCY_CONFLICT:intent already simulated",),
                checks=previous.checks,
            )
            self._record("paper.idempotent_replay", replayed.to_audit_payload())
            return replayed

        result = self._evaluate(
            intent,
            intent_id=intent_id,
            quote=quote,
            mark=mark,
            approval=approval,
            sizing_ok=sizing_ok,
            sizing_reasons=sizing_reasons,
            data_quality_ok=data_quality_ok,
            now=now,
        )
        with self._lock:
            self._seen.setdefault(intent_id, result)
        self._record("paper.refused" if result.refused else "paper.executed", result.to_audit_payload())
        if self._events is not None:
            from nexus.events.bus import EventEnvelope

            self._events.publish(EventEnvelope(topic="nexus.paper.result", payload=result.to_audit_payload()))
        return result

    # -- internals ---------------------------------------------------------

    def _evaluate(
        self,
        intent: Any,
        *,
        intent_id: str,
        quote: Any,
        mark: Decimal | None,
        approval: Any | None,
        sizing_ok: bool,
        sizing_reasons: tuple[str, ...],
        data_quality_ok: bool,
        now: Any | None,
    ) -> PaperExecutionResult:
        instrument_id = str(getattr(intent, "instrument_id", ""))
        venue = str(getattr(intent, "venue", ""))
        quantity = Decimal(str(getattr(intent, "quantity", "0")))
        order_id = new_id("PPO")
        checks: dict[str, Any] = {"simulated": True, "environment": "PAPER"}
        reasons: list[str] = []

        # The halt switch applies to paper trading too. An operator who has stopped the system has
        # stopped it, and a simulator that keeps trading through a halt would be rehearsing
        # behaviour the real system is forbidden from having.
        # Whether this order only reduces risk decides if a halt stops it. `HaltScope.NEW_ENTRIES`
        # exists so an operator can stop the system opening positions while still being able to
        # close them; a paper engine that ignored that distinction would rehearse a behaviour the
        # real one is forbidden from having, and would leave simulated positions stranded.
        risk_reducing = bool(getattr(intent, "reduce_only", False)) or self._closes_position(intent)
        if self._halt is not None:
            # `HaltManager.state` is a property, not a method: calling it would raise TypeError on
            # the first quote that arrived with a halt engaged, which is exactly the moment this
            # branch exists for.
            state = self._halt.state
            checks["halt"] = {
                "active": state.active,
                "scope": str(state.scope),
                "blocks_new_entries": state.blocks_new_entries(),
                "allows_risk_reducing": state.allows_risk_reducing(),
                "this_order_is_risk_reducing": risk_reducing,
            }
            # One rule, because the scopes nest: ALL_TRADING also blocks new entries, and
            # `allows_risk_reducing()` is unconditionally true — a kill switch that trapped an open
            # position would be worse than the incident that triggered it. So the only question is
            # whether this order opens risk while a halt is up.
            if state.blocks_new_entries() and not (risk_reducing and state.allows_risk_reducing()):
                reasons.append(f"HALT_BLOCKS_NEW_ENTRIES:{state.scope}")

        if not data_quality_ok:
            reasons.append("DATA_QUALITY:instrument or venue data quality gate failed")
        if not sizing_ok:
            # `list.extend` returns None, so an `or` fallback here would be built and discarded:
            # written naively this silently reported *no* reason at all when sizing refused without
            # supplying one, which is the case an operator most needs explained.
            if sizing_reasons:
                reasons.extend(f"RISK:{reason}" for reason in sizing_reasons)
            else:
                reasons.append("RISK:sizing refused")
        if approval is not None:
            bound = getattr(approval, "intent_id", None)
            if bound != intent_id:
                reasons.append("APPROVAL_MISMATCH:approval is bound to a different intent digest")

        side = self._resolve_side(intent)
        checks["side_resolution"] = side
        if side is None:
            reasons.append("SIDE_UNRESOLVED:cannot tell whether this opens or closes a position")

        if reasons:
            return PaperExecutionResult(
                status=PaperEngineStatus.REFUSED,
                intent_id=intent_id,
                order_id=order_id,
                order_state=OrderState.REJECTED_BY_GOVERNANCE,
                instrument_id=instrument_id,
                venue=venue,
                side=str(getattr(intent, "side", "")),
                quantity=quantity,
                reasons=tuple(dict.fromkeys(reasons)),
                checks=checks,
            )

        assert side is not None  # narrowed above
        outcome = self._fill_model.simulate(
            order_id=order_id,
            instrument_id=instrument_id,
            venue=venue,
            side=side,
            quantity=quantity,
            quote=quote,
            limit_price=getattr(intent, "limit_price", None),
            currency=str(getattr(intent, "quote_currency", "USD")),
            now=now,
        )
        checks["fill_model"] = self._fill_model.describe()
        checks["no_fill_reason"] = None if outcome.no_fill_reason is None else outcome.no_fill_reason.value

        if not outcome.filled:
            # Named `order_state`, not `state`: the halt branch above already binds `state` to a
            # HaltState, and reusing the name here put two unrelated types in one variable.
            order_state = OrderState.EXPIRED
            if outcome.no_fill_reason is NoFillReason.LIMIT_NOT_MARKETABLE:
                # A limit the market never reached is not an expired order; a real venue would leave
                # it resting. Reporting WORKING keeps the blotter honest that nothing was wrong with
                # the order — it simply never became marketable.
                order_state = OrderState.WORKING
            unfilled = PaperExecutionResult(
                status=PaperEngineStatus.UNFILLED,
                intent_id=intent_id,
                order_id=order_id,
                order_state=order_state,
                instrument_id=instrument_id,
                venue=venue,
                side=side.value,
                quantity=quantity,
                outcome=outcome,
                reasons=(
                    f"{outcome.no_fill_reason.value}:{outcome.detail}"
                    if outcome.no_fill_reason is not None
                    else "UNFILLED",
                ),
                checks=checks,
            )
            self._persist(unfilled, mark=mark)
            return unfilled

        with self._lock:
            for fill in outcome.fills:
                self._account = self._account.apply_fill(
                    instrument_id=fill.instrument_id,
                    venue=fill.venue,
                    side=fill.side.value,
                    quantity=fill.quantity,
                    price=fill.price,
                    commission=fill.commission,
                    at=fill.filled_at,
                )

        filled = PaperExecutionResult(
            status=(
                PaperEngineStatus.SIMULATED_PARTIAL
                if outcome.partially_filled
                else PaperEngineStatus.SIMULATED
            ),
            intent_id=intent_id,
            order_id=order_id,
            order_state=(OrderState.PARTIALLY_FILLED if outcome.partially_filled else OrderState.FILLED),
            instrument_id=instrument_id,
            venue=venue,
            side=side.value,
            quantity=quantity,
            outcome=outcome,
            reasons=(
                (
                    f"PARTIAL_FILL:only {outcome.filled_quantity} of {quantity} was available at the "
                    "displayed size",
                )
                if outcome.partially_filled
                else ()
            ),
            checks=checks,
        )
        self._persist(filled, mark=mark)
        return filled

    def _resolve_side(self, intent: Any) -> Side | None:
        """Turn a position intent (LONG/SHORT) into the order side that crosses the spread.

        ``TradeIntent.side`` says what position is *wanted*, not what order to send: going long is a
        BUY, but closing a long is a SELL. The current position decides which, and getting this
        wrong would let the simulator buy when the strategy meant to exit.
        """
        declared = str(getattr(intent, "side", "")).upper()
        if declared in ("BUY", "SELL"):
            return Side(declared)
        if declared == "LONG":
            # Buying is correct whether this opens a long or closes a short: both cross to the ask.
            return Side.BUY
        if declared == "SHORT":
            return Side.SELL
        if declared in ("CLOSE", "EXIT", "FLAT"):
            held = self.account.position(
                str(getattr(intent, "instrument_id", "")), str(getattr(intent, "venue", ""))
            )
            current = held.quantity if held is not None else Decimal("0")
            if current > 0:
                return Side.SELL
            if current < 0:
                return Side.BUY
            return None  # nothing to close; refusing beats inventing a direction
        return None

    def _closes_position(self, intent: Any) -> bool:
        """Whether executing this intent would make the account's exposure smaller.

        Derived from the position actually held, not from the intent's wording: a SHORT against a
        flat account opens risk, while the same SHORT against a long closes it.
        """
        held = self.account.position(
            str(getattr(intent, "instrument_id", "")), str(getattr(intent, "venue", ""))
        )
        if held is None or held.is_flat:
            return False
        side = self._resolve_side(intent)
        if side is None:
            return False
        return (held.quantity > 0 and side is Side.SELL) or (held.quantity < 0 and side is Side.BUY)

    def _persist(self, result: PaperExecutionResult, *, mark: Decimal | None) -> None:
        payload = result.to_audit_payload()
        self._ledger.record_order(
            {
                **payload,
                "mark": None if mark is None else str(mark),
                "account_id": self._account.account_id,
            }
        )
        if result.outcome is not None:
            for fill in result.outcome.fills:
                self._ledger.record_fill(fill.to_dict())

    def _record(self, kind: str, payload: dict[str, Any]) -> None:
        if self._audit is not None:
            self._audit.record(kind, payload)
