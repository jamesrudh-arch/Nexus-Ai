"""Persistent operational state (Stage 6 — Database & Persistent Memory).

R-1 / D-042 declared SQLite (governance + operational state) and Parquet+zstd/DuckDB (market time
series) the single-node system of record for NEXUS. This package is the SQLite half:

* :mod:`nexus.store.schema` — the versioned DDL, kept next to the code that applies it.
* :mod:`nexus.store.migrations` — forward-only, idempotent, audited migration runner (law L-4).
* :mod:`nexus.store.operational` — durable writers and readers for decisions, intents, approvals,
  instruments, orders, fills, gateway results, halt events and limit changes (closes F-2 and F-7).
* :mod:`nexus.store.writeahead` — audit-first writes and the projector registry (law L-2).
* :mod:`nexus.store.recovery` — fail-closed boot recovery: verify the chain, re-derive the halt,
  finish unfinished writes, resolve non-terminal orders without guessing (laws L-1 and L-6).
* :mod:`nexus.store.serialise` — canonical JSON and exact Decimal round-trips (law L-4).

The ``OperationalStore`` Protocol is the seam R-1 kept: a PostgreSQL implementation under trigger
conditions T-1…T-4 satisfies the same surface and nothing above it changes.
"""

from __future__ import annotations

from nexus.store.migrations import (
    AppliedMigration,
    MigrationError,
    MigrationReport,
    MigrationRunner,
    SkippedMigration,
)
from nexus.store.operational import (
    ExecutionResultRow,
    HaltEventRow,
    OperationalStore,
    OrderRow,
    PersistenceError,
    SqliteOperationalStore,
    SqlOperationalStore,
)
from nexus.store.postgres import PostgresAuditStore, PostgresOperationalStore
from nexus.store.recovery import (
    BootRecoveryReport,
    BootRefused,
    RecoveryIncomplete,
    derive_halt_state,
    recover,
)
from nexus.store.schema import MIGRATIONS, Migration
from nexus.store.writeahead import project, reproject_missing, write_with_audit

__all__ = [
    "MIGRATIONS",
    "AppliedMigration",
    "BootRecoveryReport",
    "BootRefused",
    "ExecutionResultRow",
    "HaltEventRow",
    "Migration",
    "MigrationError",
    "MigrationReport",
    "MigrationRunner",
    "SkippedMigration",
    "OperationalStore",
    "OrderRow",
    "PersistenceError",
    "RecoveryIncomplete",
    "PostgresAuditStore",
    "PostgresOperationalStore",
    "SqlOperationalStore",
    "SqliteOperationalStore",
    "derive_halt_state",
    "project",
    "recover",
    "reproject_missing",
    "write_with_audit",
]
