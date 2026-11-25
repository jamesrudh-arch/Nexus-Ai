"""Market-data ingestion (Section 4, Section 22.1).

Phase 3 adapters are **public-data only**. No adapter in this package accepts credentials,
and none can place an order — that is enforced by the absence of any such parameter, and
asserted in CI.

Free sources (D-019): Bybit V5 public REST, OKX v5 public REST, Dukascopy public historical
bi5, data.binance.vision bulk dumps. None has an SLA (Z-08); gaps and throttling are
expected and are recorded rather than papered over.
"""

from nexus.ingestion.base import (
    BackoffPolicy,
    BarRecord,
    BookLevel,
    BookRecord,
    FeedKind,
    HistoricalSource,
    HttpTransport,
    IngestFault,
    IngestReport,
    InstrumentInfoRecord,
    MarketDataAdapter,
    QuoteRecord,
    RateLimited,
    RecordingTransport,
    TickRecord,
    TokenBucket,
    Transport,
    dedupe_bars,
    dedupe_ticks,
    require_decimal,
    sort_bars,
    to_decimal,
    to_utc,
    validate_bar,
    validate_quote,
    validate_tick,
)
from nexus.ingestion.bybit import BybitPublicAdapter
from nexus.ingestion.dukascopy import DukascopyHistorical, DukascopyHour
from nexus.ingestion.okx import OkxPublicAdapter
from nexus.ingestion.pipeline import IngestionPipeline, PipelineReport, summarise_reports

__all__ = [
    "BackoffPolicy",
    "BarRecord",
    "BookLevel",
    "BookRecord",
    "BybitPublicAdapter",
    "DukascopyHistorical",
    "DukascopyHour",
    "FeedKind",
    "HistoricalSource",
    "HttpTransport",
    "IngestFault",
    "IngestReport",
    "IngestionPipeline",
    "InstrumentInfoRecord",
    "MarketDataAdapter",
    "OkxPublicAdapter",
    "PipelineReport",
    "QuoteRecord",
    "RateLimited",
    "RecordingTransport",
    "TickRecord",
    "TokenBucket",
    "Transport",
    "dedupe_bars",
    "dedupe_ticks",
    "require_decimal",
    "sort_bars",
    "summarise_reports",
    "to_decimal",
    "to_utc",
    "validate_bar",
    "validate_quote",
    "validate_tick",
]
