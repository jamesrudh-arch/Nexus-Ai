"""Deterministic risk engine and live-authority gate (Section 10).

Nothing in this package is generative. Limits are numbers, checks are pure functions,
and refusals are total: any missing input fails closed.
"""

from nexus.risk.authority import LiveAuthority, LiveAuthorityStatus
from nexus.risk.engine import (
    PositionSizeRequest,
    PositionSizeResult,
    RiskCheckResult,
    RiskEngine,
    size_from_risk,
)
from nexus.risk.portfolio import PortfolioSnapshot, PositionSnapshot

__all__ = [
    "LiveAuthority",
    "LiveAuthorityStatus",
    "PortfolioSnapshot",
    "PositionSizeRequest",
    "PositionSizeResult",
    "PositionSnapshot",
    "RiskCheckResult",
    "RiskEngine",
    "size_from_risk",
]
