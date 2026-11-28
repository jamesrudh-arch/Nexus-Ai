"""Market-data quality gating (Section 4.4, Section 15.2).

Data is never assumed good. Age, crossing, missing fields and clock faults are checked
before anything downstream may take new risk. Reads may continue while labelled stale;
new entries may not.
"""

from nexus.data.freshness import (
    DataQualityGate,
    DataStatus,
    GateResult,
    MarketSnapshot,
    OrderBookSnapshot,
)

__all__ = [
    "DataQualityGate",
    "DataStatus",
    "GateResult",
    "MarketSnapshot",
    "OrderBookSnapshot",
]
