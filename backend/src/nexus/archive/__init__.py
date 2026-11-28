"""First-party market-data archive (Section 4.4, retention per D-024/Q-08).

The archive exists because free venue endpoints trim their history without notice and have
no SLA (Z-08). Whatever NEXUS observed itself is the only series it can prove is complete.

Nothing here fabricates data: empty buckets produce no bar, gaps are reported and never
interpolated, and an unconfirmed (still-forming) bar can never overwrite a confirmed one.
"""

from nexus.archive.bars import (
    INTERVAL_DURATION,
    ROLLUP_CHAIN,
    AggregationReport,
    bar_identity,
    bars_from_ticks,
    bucket_start,
    find_gaps,
    interval_duration,
    is_rollup_of,
    merge_bars,
    rollup_bars,
)
from nexus.archive.parquet_store import (
    BAR_COLUMNS,
    FORMAT_VERSION,
    ArchiveError,
    ArchiveUnavailable,
    ParquetArchive,
    WriteResult,
)
from nexus.archive.retention import (
    CoverageWindow,
    DiskPressure,
    RetentionAction,
    RetentionPlan,
    RetentionPolicy,
    RetentionTier,
    build_inventory,
    default_tiers,
    disk_pressure,
)

__all__ = [
    "BAR_COLUMNS",
    "FORMAT_VERSION",
    "INTERVAL_DURATION",
    "ROLLUP_CHAIN",
    "AggregationReport",
    "ArchiveError",
    "ArchiveUnavailable",
    "CoverageWindow",
    "DiskPressure",
    "ParquetArchive",
    "RetentionAction",
    "RetentionPlan",
    "RetentionPolicy",
    "RetentionTier",
    "WriteResult",
    "bar_identity",
    "bars_from_ticks",
    "bucket_start",
    "build_inventory",
    "default_tiers",
    "disk_pressure",
    "find_gaps",
    "interval_duration",
    "is_rollup_of",
    "merge_bars",
    "rollup_bars",
]
