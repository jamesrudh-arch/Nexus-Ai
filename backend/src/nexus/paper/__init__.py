"""Paper trading: simulated execution and real-time analysis (Stage 11, D-059).

The package that lets the system run its trades and analyse them in real time *before* any actual
trading. It is deliberately incapable of reaching a venue: there is no socket, no HTTP client and no
credential anywhere in it, and ``can_place_live_orders`` is ``False`` on every class here.

Read :mod:`nexus.paper.engine` first — its docstring states what this package is not, and why that
matters more than what it is.
"""

from __future__ import annotations

from nexus.paper.account import PaperAccount, PaperPosition, PaperSnapshot, rebuild_from_fills
from nexus.paper.analysis import AnalysisConfig, AnalysisVerdict, Analyzer, QuoteFlowAnalyzer
from nexus.paper.engine import (
    InMemoryPaperLedger,
    PaperEngineStatus,
    PaperExecutionResult,
    PaperLedger,
    PaperTradingEngine,
)
from nexus.paper.fill_model import (
    FillModelConfig,
    FillOutcome,
    NoFillReason,
    Side,
    SimulatedFill,
    SimulatedFillModel,
)
from nexus.paper.realtime import EquityFractionSizer, LoopStats, PaperTradingLoop, Sizer

__all__ = [
    "AnalysisConfig",
    "AnalysisVerdict",
    "Analyzer",
    "EquityFractionSizer",
    "FillModelConfig",
    "FillOutcome",
    "InMemoryPaperLedger",
    "LoopStats",
    "NoFillReason",
    "PaperAccount",
    "PaperEngineStatus",
    "PaperExecutionResult",
    "PaperLedger",
    "PaperPosition",
    "PaperSnapshot",
    "PaperTradingEngine",
    "PaperTradingLoop",
    "QuoteFlowAnalyzer",
    "Side",
    "SimulatedFill",
    "SimulatedFillModel",
    "Sizer",
    "rebuild_from_fills",
]

#: The one claim this package makes about itself, published so it can be asserted rather than
#: trusted. ``test_paper_trading.py`` fails if any of it stops being true.
CAPABILITY = {
    "simulated": True,
    "environment": "PAPER",
    "can_place_live_orders": False,
    "is_venue_adapter": False,
    "network_access": False,
    "credentials_required": False,
    "phase_gate_unchanged": True,
}
