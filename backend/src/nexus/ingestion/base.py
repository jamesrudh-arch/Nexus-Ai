"""Ingestion contracts — re-exported from :mod:`nexus.data.records`.

The record types, normalisation helpers, validators, transport protocols and rate limiting
live in :mod:`nexus.data.records` because the archiver, the ingestion pipeline and the venue
adapters all depend on them. Defining them here created an import cycle:

``archive.bars -> ingestion.base -> ingestion/__init__ -> ingestion.pipeline -> archive.bars``

This module stays as the ingestion-facing import path so adapter code reads naturally. It
defines nothing of its own; every name below is the same object as the one in
``nexus.data.records``.
"""

from __future__ import annotations

from nexus.data.records import (
    BackoffPolicy,
    BarRecord,
    BookLevel,
    BookRecord,
    FeedKind,
    Fetched,
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
    epoch_unit,
    event_time,
    require_decimal,
    sort_bars,
    to_decimal,
    to_utc,
    validate_bar,
    validate_quote,
    validate_tick,
)

__all__ = [
    "BackoffPolicy",
    "BarRecord",
    "BookLevel",
    "BookRecord",
    "FeedKind",
    "Fetched",
    "HistoricalSource",
    "HttpTransport",
    "IngestFault",
    "IngestReport",
    "InstrumentInfoRecord",
    "MarketDataAdapter",
    "QuoteRecord",
    "RateLimited",
    "RecordingTransport",
    "TickRecord",
    "TokenBucket",
    "Transport",
    "dedupe_bars",
    "dedupe_ticks",
    "event_time",
    "require_decimal",
    "sort_bars",
    "to_decimal",
    "epoch_unit",
    "to_utc",
    "validate_bar",
    "validate_quote",
    "validate_tick",
]
