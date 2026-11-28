"""Emergency halt and kill switch (Section 12.5, Section 24, Section 29).

Two distinct mechanisms:
- **Halt**: blocks *new entries* and cancels eligible working orders per configured policy.
  Existing protective orders stay at the venue — positions are never left unmanaged.
- **Kill switch**: a stronger stop that also blocks management actions except
  risk-reducing ones (closing positions, cancelling orders).

Both are runtime state, not configuration, and both are audited with an incident ID.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now


class HaltScope(StrEnum):
    NONE = "NONE"
    NEW_ENTRIES = "NEW_ENTRIES"  # standard emergency halt
    ALL_TRADING = "ALL_TRADING"  # kill switch: only risk-reducing actions allowed


# Explicit severity ordering — StrEnum values are strings, so widening must not rely on
# comparison operators. Widening is monotonic: a halt never narrows by accident.
_SCOPE_RANK: dict[HaltScope, int] = {
    HaltScope.NONE: 0,
    HaltScope.NEW_ENTRIES: 1,
    HaltScope.ALL_TRADING: 2,
}


def widest_scope(current: HaltScope, requested: HaltScope) -> HaltScope:
    """Return the more restrictive of two scopes."""
    return current if _SCOPE_RANK[current] >= _SCOPE_RANK[requested] else requested


@dataclass(frozen=True, slots=True)
class HaltState:
    """Current halt/kill-switch state."""

    scope: HaltScope = HaltScope.NONE
    active: bool = False
    reason: str = ""
    triggered_by: str = "SYSTEM"
    incident_id: str | None = None
    since: str | None = None
    affected_accounts: tuple[str, ...] = ()
    affected_instruments: tuple[str, ...] = ()
    cancel_working_orders: bool = True  # policy: cancel eligible working orders on halt

    def blocks_new_entries(self) -> bool:
        return self.active and self.scope in (HaltScope.NEW_ENTRIES, HaltScope.ALL_TRADING)

    def blocks_all_trading(self) -> bool:
        return self.active and self.scope == HaltScope.ALL_TRADING

    def allows_risk_reducing(self) -> bool:
        """Closing a position or cancelling an order is allowed even under a kill switch."""
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "active": self.active,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "incident_id": self.incident_id,
            "since": self.since,
            "affected_accounts": list(self.affected_accounts),
            "affected_instruments": list(self.affected_instruments),
            "cancel_working_orders": self.cancel_working_orders,
        }


@dataclass(slots=True)
class _HaltEvent:
    action: str  # ENGAGE | RELEASE
    state: HaltState
    at: str = field(default_factory=lambda: iso_utc(utc_now()))


class HaltManager:
    """Thread-safe holder of halt state with an auditable, durable event history.

    ``store`` makes a halt survive a restart (Stage 6, finding F-3, law L-1): every engagement and
    release is written to ``halt_event``, and boot recovery re-derives the state from those rows
    before the API reports ready. Without a store the halt is runtime-only, which is the behaviour
    that used to clear an active halt on restart.

    ``restored_state`` is what recovery hands back. It is set directly rather than re-engaged so the
    original incident id, scope, reason and timestamp survive: a restarted system must show the halt
    the owner actually engaged, not a fresh one that happens to look similar.
    """

    def __init__(
        self,
        *,
        audit: Any = None,
        events: Any = None,
        store: Any = None,
        restored_state: HaltState | None = None,
    ) -> None:
        self._state = restored_state or HaltState()
        self._history: list[_HaltEvent] = []
        self._lock = threading.RLock()
        self._audit = audit
        self._events = events
        self._store = store
        if restored_state is not None:
            self._history.append(_HaltEvent(action="RESTORED", state=self._state))

    @property
    def state(self) -> HaltState:
        with self._lock:
            return self._state

    @property
    def active(self) -> bool:
        return self.state.active

    def engage(
        self,
        *,
        scope: HaltScope = HaltScope.NEW_ENTRIES,
        reason: str,
        triggered_by: str = "OWNER",
        affected_accounts: tuple[str, ...] = (),
        affected_instruments: tuple[str, ...] = (),
        cancel_working_orders: bool = True,
    ) -> HaltState:
        """Engage the halt. Idempotent: re-engaging widens scope and updates the reason."""
        with self._lock:
            incident = self._state.incident_id or new_id("INC")
            widened = widest_scope(self._state.scope, scope)
            self._state = HaltState(
                scope=widened,
                active=True,
                reason=reason,
                triggered_by=triggered_by,
                incident_id=incident,
                since=self._state.since or iso_utc(utc_now()),
                affected_accounts=tuple(dict.fromkeys((*self._state.affected_accounts, *affected_accounts))),
                affected_instruments=tuple(
                    dict.fromkeys((*self._state.affected_instruments, *affected_instruments))
                ),
                cancel_working_orders=cancel_working_orders,
            )
            self._record("ENGAGE")
            return self._state

    def release(self, *, reason: str, released_by: str = "OWNER") -> HaltState:
        """Release the halt. Release is an explicit owner action and is always audited."""
        with self._lock:
            previous = self._state
            self._state = HaltState(scope=HaltScope.NONE, active=False)
            self._record(
                "RELEASE", note=f"{reason} (by {released_by}; previous scope {previous.scope.value})"
            )
            return self._state

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"action": e.action, "at": e.at, "state": e.state.to_dict()} for e in self._history]

    def _record(self, action: str, *, note: str = "") -> None:
        self._history.append(_HaltEvent(action=action, state=self._state))
        entry: Any = None
        if self._audit is not None:
            payload: dict[str, Any] = {"action": action, **self._state.to_dict()}
            if note:
                payload["note"] = note
            entry = self._audit.record(f"halt.{action.lower()}", payload, actor=self._state.triggered_by)
        if self._store is not None:
            # Law L-2, durable before acknowledged: the audit entry above is committed first, so a
            # crash between the two leaves a record that boot recovery re-projects into halt_event
            # rather than a halt nobody can prove was ever engaged.
            self._store.save_halt_event(
                action=action,
                scope=self._state.scope,
                reason=self._state.reason or note,
                triggered_by=self._state.triggered_by,
                at=self._state.since or iso_utc(utc_now()),
                incident_id=self._state.incident_id,
                affected_accounts=self._state.affected_accounts,
                affected_instruments=self._state.affected_instruments,
                cancel_working_orders=self._state.cancel_working_orders,
                audit_ref=getattr(entry, "record_id", None),
            )
        if self._events is not None:
            from nexus.events.bus import EventEnvelope

            self._events.publish(EventEnvelope(topic="nexus.halt", payload=self._state.to_dict()))
