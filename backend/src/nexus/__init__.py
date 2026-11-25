"""NEXUS — Autonomous Financial Intelligence System.

Phase 3 (market data + instrument master), on top of the Phase 2 core foundation.

Live trading remains disabled. Phase 3 adds **read-only market data** adapters for public
venue endpoints; it adds no trading adapter, no venue credential and no order path. Nothing
in this package can place an order until the Phase 4-9 gates pass and live authority is
explicitly granted by the owner.

Cost constraint D-019: every dependency is free/open-source. No paid service is called.
"""

from __future__ import annotations

__version__ = "0.2.0"
__phase__ = "3-market-data"

PHASE_GATE = {
    "phase": 3,
    "name": "Market data and instrument master",
    "live_trading": False,
    "venue_adapters": False,  # trading adapters; market-data adapters are read-only
    "real_money_orders_possible": False,
    "market_data_sources": True,
    "order_capability": False,
}

#: Free, public, unauthenticated data sources wired in Phase 3 (D-019). Every one is
#: read-only. No entry here implies a trading connection or a stored credential.
DATA_SOURCES = (
    "BYBIT_V5_PUBLIC_REST",
    "OKX_V5_PUBLIC_REST",
    "BINANCE_VISION_PUBLIC_DUMP",
    "DUKASCOPY_BI5_PUBLIC",
)
