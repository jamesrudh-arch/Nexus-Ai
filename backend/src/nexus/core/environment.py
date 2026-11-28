"""Execution environment state machine (Section 2, Section 26 staged rollout).

Order is strictly increasing in authority. Promotion is one-way per session and must be
an explicit, audited owner action — never inferred, never automatic.
"""

from __future__ import annotations

from enum import IntEnum


class EnvironmentState(IntEnum):
    """Staged rollout environments, ordered by trading authority.

    DISABLED is the default and the value used whenever state is unknown, unreadable,
    or inconsistent (fail closed).
    """

    DISABLED = 0
    OBSERVE = 1  # market data only, no decisions
    RESEARCH = 2  # research + dossiers, no orders
    SHADOW = 3  # decisions computed and logged, never sent
    PAPER = 4  # simulated execution against live data
    PILOT = 5  # restricted live, small mandate, hard caps
    LIVE = 6  # autonomous live within hard limits


_PRE_LIVE_MAX = EnvironmentState.PAPER


def is_pre_live(state: EnvironmentState | int | None) -> bool:
    """True when the state cannot place a real order.

    ``None`` (unknown) is treated as pre-live: the most restrictive reading.
    """
    if state is None:
        return True
    try:
        resolved = EnvironmentState(int(state))
    except ValueError:
        return True
    return resolved <= _PRE_LIVE_MAX


def can_place_live_order(state: EnvironmentState | int | None) -> bool:
    """True only for PILOT and LIVE — and only as one of several required gates."""
    if state is None:
        return False
    try:
        resolved = EnvironmentState(int(state))
    except ValueError:
        return False
    return resolved >= EnvironmentState.PILOT


def promotion_is_valid(current: EnvironmentState, target: EnvironmentState) -> bool:
    """Whether an environment change from ``current`` to ``target`` is permitted.

    - De-escalation to any safer stage: always allowed (stopping is never blocked).
    - Same stage: allowed as an idempotent no-op.
    - Advance: exactly one stage at a time. Skipping stages is refused, so no build can
      jump from PAPER to LIVE without passing through PILOT.
    """
    if target <= current:
        return True
    return target.value == current.value + 1


def is_promotion(current: EnvironmentState, target: EnvironmentState) -> bool:
    """True only when the move actually increases trading authority."""
    return target > current
