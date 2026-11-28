"""Order state machine (Section 12.3, Section 34).

Unknown states are never resolved by guessing or resubmitting. An order whose state cannot
be determined stays UNKNOWN, blocks new risk on that instrument/account, and requires
reconciliation against the venue before anything else happens.
"""

from __future__ import annotations

from enum import StrEnum


class OrderState(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED_BY_GOVERNANCE = "REJECTED_BY_GOVERNANCE"
    SUBMITTING = "SUBMITTING"
    ACCEPTED_BY_VENUE = "ACCEPTED_BY_VENUE"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED_BY_VENUE = "REJECTED_BY_VENUE"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


TERMINAL = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.EXPIRED,
        OrderState.REJECTED_BY_VENUE,
        OrderState.REJECTED_BY_GOVERNANCE,
        OrderState.RECONCILED,
    }
)

_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.DRAFT: frozenset({OrderState.PENDING_APPROVAL, OrderState.REJECTED_BY_GOVERNANCE}),
    OrderState.PENDING_APPROVAL: frozenset(
        {OrderState.APPROVED, OrderState.REJECTED_BY_GOVERNANCE, OrderState.EXPIRED}
    ),
    OrderState.APPROVED: frozenset(
        {OrderState.SUBMITTING, OrderState.REJECTED_BY_GOVERNANCE, OrderState.EXPIRED, OrderState.CANCELLED}
    ),
    OrderState.SUBMITTING: frozenset(
        {
            OrderState.ACCEPTED_BY_VENUE,
            OrderState.WORKING,
            OrderState.FILLED,
            OrderState.REJECTED_BY_VENUE,
            OrderState.UNKNOWN,  # send without ack — never assumed rejected
        }
    ),
    OrderState.ACCEPTED_BY_VENUE: frozenset(
        {
            OrderState.WORKING,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.WORKING: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.CANCEL_REQUESTED: frozenset(
        {OrderState.CANCELLED, OrderState.WORKING, OrderState.FILLED, OrderState.UNKNOWN}
    ),
    # UNKNOWN may only be resolved by reconciliation against the venue.
    OrderState.UNKNOWN: frozenset(
        {OrderState.RECONCILED, OrderState.WORKING, OrderState.FILLED, OrderState.CANCELLED}
    ),
    OrderState.FILLED: frozenset({OrderState.RECONCILED}),
    OrderState.CANCELLED: frozenset({OrderState.RECONCILED}),
    OrderState.EXPIRED: frozenset({OrderState.RECONCILED}),
    OrderState.REJECTED_BY_VENUE: frozenset({OrderState.RECONCILED}),
    OrderState.REJECTED_BY_GOVERNANCE: frozenset(),
    OrderState.RECONCILED: frozenset(),
}


def allowed_transitions(state: OrderState) -> frozenset[OrderState]:
    """Legal next states for ``state``."""
    return _TRANSITIONS.get(state, frozenset())


def can_transition(current: OrderState, target: OrderState) -> bool:
    """True when the move is legal. Unknown states are never auto-resolved."""
    return target in allowed_transitions(current)


def is_terminal(state: OrderState) -> bool:
    return state in TERMINAL


def blocks_new_risk(state: OrderState) -> bool:
    """States that must be resolved before new entries on the same instrument/account."""
    return state in {OrderState.UNKNOWN, OrderState.SUBMITTING, OrderState.CANCEL_REQUESTED}
