"""Fail-closed boot recovery (Stage 6: findings F-2, F-3, F-7; laws L-1, L-2, L-6).

At boot the system answers three questions before it is allowed to say it is ready:

1. **Can the past be trusted?** ``AuditLog.verify()`` walks the hash chain. A break means the
   record of what happened is not what happened, so recovery raises :class:`BootRefused` instead of
   serving state derived from it (L-6).
2. **Is anything still stopped?** Halt state is re-derived from durable ``halt_event`` rows: the
   last engagement without a matching release means the system boots HALTED (L-1). This closes F-3
   — previously ``HaltManager`` started from ``HaltState()`` and a restart silently cleared a halt.
   If the halt history cannot be read at all, the answer is not "assume released": it boots into the
   kill switch, because an indeterminate halt state is exactly the case where guessing is unsafe.
3. **Is anything unfinished?** Audited writes whose projection never landed are re-applied (L-2),
   and every order left in a non-terminal state is resolved the only honest way: states that could
   mean "sent but unacknowledged" become ``UNKNOWN`` and block new risk until reconciliation, and
   pre-submission states expire, because an approval that survived a restart was never re-confirmed
   by the owner.

Nothing here guesses a fill, narrows a halt, or marks an unknown order as failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.execution.halt import HaltScope, HaltState
from nexus.execution.orders import OrderState, allowed_transitions, is_terminal
from nexus.store.operational import OperationalStore, PersistenceError
from nexus.store.writeahead import reproject_missing

__all__ = [
    "BootRecoveryReport",
    "BootRefused",
    "RecoveryIncomplete",
    "SENT_STATES",
    "derive_halt_state",
    "indeterminate_halt_state",
    "recover",
]

#: States where a restart cannot know whether the venue received the order.
SENT_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.SUBMITTING,
        OrderState.ACCEPTED_BY_VENUE,
        OrderState.WORKING,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCEL_REQUESTED,
        OrderState.UNKNOWN,
    }
)

#: States where nothing was transmitted, so nothing can be unknown at the venue.
PRE_SUBMISSION_STATES: frozenset[OrderState] = frozenset(
    {OrderState.DRAFT, OrderState.PENDING_APPROVAL, OrderState.APPROVED}
)


class BootRefused(NexusError):
    """The audit chain failed verification, so boot state cannot be trusted. Do not serve."""

    def __init__(self, detail: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(
            RejectReason.AUDIT_CHAIN_INVALID,
            detail,
            retryable=False,
            context=context,
        )


class RecoveryIncomplete(NexusError):
    """Recovery could not finish. The system stays halted rather than partially ready."""

    def __init__(self, detail: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(
            RejectReason.BOOT_RECOVERY_INCOMPLETE,
            detail,
            retryable=True,
            context=context,
        )


@dataclass(frozen=True, slots=True)
class BootRecoveryReport:
    """What boot recovery found and did. Audited as ``boot.recovery``."""

    halt_state: HaltState | None = None
    halt_indeterminate: bool = False
    chain_breaks: tuple[str, ...] = ()
    orders_marked_unknown: tuple[str, ...] = ()
    orders_expired: tuple[str, ...] = ()
    orders_rejected: tuple[str, ...] = ()
    reprojected: tuple[str, ...] = ()
    at: str = field(default_factory=lambda: iso_utc(utc_now()))

    @property
    def halted(self) -> bool:
        return bool(self.halt_state is not None and self.halt_state.active)

    @property
    def blocks_new_risk(self) -> bool:
        """True when an unresolved order or a halt means no new risk may be taken."""
        return self.halted or bool(self.orders_marked_unknown)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "halt_active": self.halted,
            "halt_scope": self.halt_state.scope.value if self.halt_state else HaltScope.NONE.value,
            "halt_indeterminate": self.halt_indeterminate,
            "halt_incident_id": self.halt_state.incident_id if self.halt_state else None,
            "halt_reason": self.halt_state.reason if self.halt_state else "",
            "chain_breaks": list(self.chain_breaks),
            "orders_marked_unknown": list(self.orders_marked_unknown),
            "orders_expired": list(self.orders_expired),
            "orders_rejected": list(self.orders_rejected),
            "reprojected": list(self.reprojected),
            "blocks_new_risk": self.blocks_new_risk,
        }


def derive_halt_state(events: Any) -> HaltState | None:
    """Replay durable halt events in order. ``None`` means genuinely not halted."""
    current: HaltState | None = None
    for event in events:
        if event.engaged:
            current = HaltState(
                scope=event.scope,
                active=True,
                reason=event.reason,
                triggered_by=event.triggered_by,
                incident_id=event.incident_id,
                since=event.at,
                affected_accounts=event.affected_accounts,
                affected_instruments=event.affected_instruments,
                cancel_working_orders=event.cancel_working_orders,
            )
        else:
            current = None
    return current


def indeterminate_halt_state(reason: str) -> HaltState:
    """The fail-closed answer when halt history cannot be read: the kill switch."""
    return HaltState(
        scope=HaltScope.ALL_TRADING,
        active=True,
        reason=reason,
        triggered_by="BOOT_RECOVERY",
        incident_id=None,
        since=iso_utc(utc_now()),
    )


def recover(
    *,
    audit: Any,
    store: OperationalStore,
    strict: bool = True,
) -> BootRecoveryReport:
    """Run boot recovery. Raises :class:`BootRefused` when the chain cannot be trusted."""
    breaks = tuple(str(item) for item in audit.verify())
    if breaks:
        detail = (
            f"audit chain verification found {len(breaks)} break(s) at boot; refusing to derive "
            "state from a record that does not verify"
        )
        if strict:
            raise BootRefused(detail, context={"breaks": len(breaks), "first": breaks[0][:120]})

    reprojected = reproject_missing(audit=audit, store=store)

    halt_state: HaltState | None
    indeterminate = False
    try:
        halt_state = derive_halt_state(store.halt_events())
    except (PersistenceError, NexusError, ValueError) as exc:
        halt_state = indeterminate_halt_state(
            f"halt history unreadable at boot ({type(exc).__name__}); failing closed"
        )
        indeterminate = True

    unknown: list[str] = []
    expired: list[str] = []
    rejected: list[str] = []
    for order in store.orders():
        if is_terminal(order.state):
            continue
        if order.state in SENT_STATES:
            if order.state is OrderState.UNKNOWN:
                unknown.append(order.order_id)
                continue
            if OrderState.UNKNOWN in allowed_transitions(order.state):
                store.update_order_state(
                    order.order_id,
                    OrderState.UNKNOWN,
                    reason="boot recovery: state at restart cannot prove the venue never received "
                    "this order; reconciliation required before new risk",
                    audit_ref=None,
                )
                unknown.append(order.order_id)
            continue
        if order.state in PRE_SUBMISSION_STATES:
            target = (
                OrderState.EXPIRED
                if OrderState.EXPIRED in allowed_transitions(order.state)
                else OrderState.REJECTED_BY_GOVERNANCE
            )
            store.update_order_state(
                order.order_id,
                target,
                reason="boot recovery: never transmitted; approval not re-confirmed after restart",
                audit_ref=None,
            )
            (expired if target is OrderState.EXPIRED else rejected).append(order.order_id)

    report = BootRecoveryReport(
        halt_state=halt_state,
        halt_indeterminate=indeterminate,
        chain_breaks=breaks,
        orders_marked_unknown=tuple(unknown),
        orders_expired=tuple(expired),
        orders_rejected=tuple(rejected),
        reprojected=reprojected,
    )
    if not breaks:
        # A broken chain is not written to: appending to a record that does not verify would make
        # the damage harder to see, not easier.
        audit.record("boot.recovery", report.to_dict(), actor="BOOT_RECOVERY")
    return report
