"""NEXUS — Autonomous Financial Intelligence System.

Phase 2 (core foundation). Live trading is disabled: no venue adapter can be reached
from this package until Phases 3-8 gates pass and live authority is explicitly granted.

Cost constraint D-019: every dependency is free/open-source. No paid service is called.
"""

from __future__ import annotations

__version__ = "0.1.0"
__phase__ = "2-core-foundation"

PHASE_GATE = {
    "phase": 2,
    "name": "Core foundation",
    "live_trading": False,
    "venue_adapters": False,
    "real_money_orders_possible": False,
}
