"""Live-authority gate (Section 2, Section 34, D-004, D-013).

Live trading requires *all* independent gates to be true at the moment of the request.
Any missing, unknown or false gate refuses. There is no override flag, no debug bypass,
and no way to enable live trading from configuration alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nexus.core.environment import EnvironmentState, can_place_live_order


class LiveAuthorityStatus(StrEnum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class LiveAuthority:
    """Evaluation of whether a real-money order may be sent right now.

    ``halt_active`` and ``kill_switch_active`` are runtime states supplied by the
    execution gateway, not configuration — an operator can always stop the system even
    when every static gate is satisfied.
    """

    environment: EnvironmentState
    live_trading_enabled: bool
    legal_review_complete: bool
    owner_live_authority_granted: bool
    phase_gate_complete: bool  # Phases 0-9 accepted with evidence
    venue_live_verified: bool  # per-account LIVE_VERIFIED capability state
    mandate_active: bool  # scoped mandate exists for this account/instrument/strategy
    halt_active: bool = False
    kill_switch_active: bool = False
    data_quality_ok: bool = True
    reconciliation_ok: bool = True
    reasons: tuple[str, ...] = field(default=())

    @property
    def status(self) -> LiveAuthorityStatus:
        return LiveAuthorityStatus.GRANTED if self.granted else LiveAuthorityStatus.DENIED

    @property
    def granted(self) -> bool:
        return not self.blocking_reasons

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        """Every gate that is currently failing. Empty means authority is granted."""
        blockers: list[str] = []
        if self.halt_active:
            blockers.append("HALT_ACTIVE")
        if self.kill_switch_active:
            blockers.append("KILL_SWITCH_ACTIVE")
        if not self.live_trading_enabled:
            blockers.append("LIVE_TRADING_DISABLED")
        if not can_place_live_order(self.environment):
            blockers.append(
                f"ENVIRONMENT_NOT_AUTHORIZED:{EnvironmentState(self.environment).name}"
                if isinstance(self.environment, EnvironmentState)
                else "ENVIRONMENT_NOT_AUTHORIZED:UNKNOWN"
            )
        if not self.legal_review_complete:
            blockers.append("LEGAL_REVIEW_NOT_COMPLETE")
        if not self.owner_live_authority_granted:
            blockers.append("OWNER_LIVE_AUTHORITY_NOT_GRANTED")
        if not self.phase_gate_complete:
            blockers.append("PHASE_GATE_INCOMPLETE")
        if not self.venue_live_verified:
            blockers.append("VENUE_NOT_LIVE_VERIFIED")
        if not self.mandate_active:
            blockers.append("MANDATE_NOT_FOUND")
        if not self.data_quality_ok:
            blockers.append("DATA_STALE")
        if not self.reconciliation_ok:
            blockers.append("RECONCILIATION_MISMATCH")
        return (*blockers, *self.reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "granted": self.granted,
            "blocking_reasons": list(self.blocking_reasons),
            "environment": self.environment.name
            if isinstance(self.environment, EnvironmentState)
            else str(self.environment),
            "gates": {
                "live_trading_enabled": self.live_trading_enabled,
                "legal_review_complete": self.legal_review_complete,
                "owner_live_authority_granted": self.owner_live_authority_granted,
                "phase_gate_complete": self.phase_gate_complete,
                "venue_live_verified": self.venue_live_verified,
                "mandate_active": self.mandate_active,
                "halt_active": self.halt_active,
                "kill_switch_active": self.kill_switch_active,
                "data_quality_ok": self.data_quality_ok,
                "reconciliation_ok": self.reconciliation_ok,
            },
        }


def evaluate_authority(
    settings: Any,
    *,
    environment: EnvironmentState | None = None,
    halt_active: bool = False,
    kill_switch_active: bool = False,
    phase_gate_complete: bool = False,
    venue_live_verified: bool = False,
    mandate_active: bool = False,
    data_quality_ok: bool = True,
    reconciliation_ok: bool = True,
) -> LiveAuthority:
    """Build the authority evaluation from settings plus runtime state."""
    env = settings.environment if environment is None else environment
    if not isinstance(env, EnvironmentState):
        try:
            env = EnvironmentState(int(env))
        except (TypeError, ValueError):
            env = EnvironmentState.DISABLED
    return LiveAuthority(
        environment=env,
        live_trading_enabled=bool(settings.live_trading_enabled),
        legal_review_complete=bool(settings.legal_review_complete),
        owner_live_authority_granted=bool(settings.owner_live_authority_granted),
        phase_gate_complete=phase_gate_complete,
        venue_live_verified=venue_live_verified,
        mandate_active=mandate_active,
        halt_active=halt_active,
        kill_switch_active=kill_switch_active,
        data_quality_ok=data_quality_ok,
        reconciliation_ok=reconciliation_ok,
    )
