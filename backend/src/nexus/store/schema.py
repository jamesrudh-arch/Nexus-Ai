"""Versioned SQLite schema for operational state (Stage 6, R-1 / D-042).

R-1 declares SQLite (governance + operational state) and Parquet+zstd/DuckDB (time series) the
single-node system of record. This module is the SQLite half of that decision.

The DDL lives in Python rather than in ``.sql`` files for a concrete deployment reason: the core
image is built from ``backend/`` and the repository's ``migrations/`` directory is mounted only
into the (now opt-in) ``db`` service, so a runner that read files from the repo would find nothing
inside the container. Keeping the statements next to the code that applies them means the schema is
always available, and each migration still has a stable version and a SHA-256 checksum that the
runner refuses to see changed after it has been applied.

``backend/migrations/0001_core.sql`` remains the portable PostgreSQL target: same tables, same
columns, ``TIMESTAMPTZ``/``NUMERIC``/``JSONB`` types instead of ``TEXT``. Promotion under trigger
conditions T-1…T-4 is a copy, not a rewrite.

Type mapping (SQLite ← PostgreSQL):

* ``TIMESTAMPTZ`` → ``TEXT`` holding ISO-8601 UTC (``core.ids.iso_utc``).
* ``NUMERIC(28, 12)`` → ``TEXT`` holding ``str(Decimal)`` — never ``REAL`` (L-4).
* ``TEXT[]`` / ``JSONB`` → ``TEXT`` holding canonical JSON (``store.serialise``).

Referential integrity is declared with ``REFERENCES`` but ``PRAGMA foreign_keys`` is deliberately
left off: boot recovery re-projects audit entries in chain order, which is not always parent-first,
and a hard foreign-key failure during recovery would be worse than the inconsistency it prevents.
Writer order and recovery reconcile the relations instead; this is a known, chosen limitation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

__all__ = ["MIGRATIONS", "Migration", "SCHEMA_MIGRATIONS_DDL"]


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered, forward-only schema migration.

    ``requires`` names a table that must already exist in *this* database for the migration to
    apply. A migration whose requirement is absent is skipped and reported — never marked applied,
    because a later boot against a durable audit store must still apply it.
    """

    version: str
    description: str
    sql: str
    requires: str | None = None

    @property
    def checksum(self) -> str:
        """SHA-256 of the statement text. Changing an applied migration is refused."""
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()

    @property
    def statements(self) -> int:
        return len([part for part in self.sql.split(";") if part.strip()])


SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    description TEXT NOT NULL,
    statements  INTEGER NOT NULL,
    applied_at  TEXT NOT NULL
);
"""

_OPERATIONAL = """
-- ---------------------------------------------------------------- instrument master
CREATE TABLE IF NOT EXISTS instrument (
    instrument_id       TEXT PRIMARY KEY,
    canonical_symbol    TEXT NOT NULL,
    asset_class         TEXT NOT NULL DEFAULT '',
    base_currency       TEXT NOT NULL DEFAULT '',
    quote_currency      TEXT NOT NULL DEFAULT '',
    settlement_currency TEXT NOT NULL DEFAULT '',
    underlying          TEXT,
    expiry              TEXT,
    strike              TEXT,
    option_type         TEXT CHECK (option_type IS NULL OR option_type IN ('CALL', 'PUT')),
    active              INTEGER NOT NULL DEFAULT 0,
    data_status         TEXT NOT NULL DEFAULT 'UNAVAILABLE',
    notes               TEXT NOT NULL DEFAULT '',
    payload             TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- ---------------------------------------------------------------- decisions
CREATE TABLE IF NOT EXISTS decision (
    decision_id           TEXT PRIMARY KEY,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    state                 TEXT NOT NULL,
    verb                  TEXT NOT NULL,
    instrument_id         TEXT REFERENCES instrument (instrument_id),
    venue                 TEXT,
    strategy_id           TEXT,
    model_id              TEXT,
    horizon               TEXT,
    confidence            TEXT,
    rationale             TEXT NOT NULL DEFAULT '',
    reason_codes          TEXT NOT NULL DEFAULT '[]',
    evidence_refs         TEXT NOT NULL DEFAULT '[]',
    counter_evidence_refs TEXT NOT NULL DEFAULT '[]',
    intent_id             TEXT,
    risk_check            TEXT NOT NULL DEFAULT '{}',
    expires_at            TEXT,
    audit_ref             TEXT
);
CREATE INDEX IF NOT EXISTS ix_decision_created ON decision (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_decision_state   ON decision (state);

-- ---------------------------------------------------------------- intents & approvals
CREATE TABLE IF NOT EXISTS trade_intent (
    intent_id          TEXT PRIMARY KEY,
    decision_id        TEXT REFERENCES decision (decision_id),
    created_at         TEXT NOT NULL,
    expires_at         TEXT,
    environment        TEXT NOT NULL,
    instrument_id      TEXT NOT NULL,
    venue              TEXT NOT NULL,
    account_id         TEXT NOT NULL,
    side               TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    order_type         TEXT NOT NULL,
    quantity           TEXT NOT NULL,
    limit_price        TEXT,
    stop_price         TEXT,
    protective_stop    TEXT,
    take_profit        TEXT,
    time_in_force      TEXT NOT NULL DEFAULT 'GTC',
    reduce_only        INTEGER NOT NULL DEFAULT 0,
    post_only          INTEGER NOT NULL DEFAULT 0,
    quote_currency     TEXT NOT NULL DEFAULT 'USD',
    max_loss_usd       TEXT,
    estimated_cost_usd TEXT,
    strategy_id        TEXT,
    model_id           TEXT,
    evidence_summary   TEXT NOT NULL DEFAULT '',
    counter_case       TEXT NOT NULL DEFAULT '',
    exit_plan          TEXT NOT NULL DEFAULT '',
    idempotency_key    TEXT NOT NULL UNIQUE,
    digest             TEXT NOT NULL,
    payload            TEXT NOT NULL DEFAULT '{}',
    audit_ref          TEXT
);
CREATE INDEX IF NOT EXISTS ix_intent_created ON trade_intent (created_at DESC);

CREATE TABLE IF NOT EXISTS approval (
    approval_id      TEXT PRIMARY KEY,
    intent_id        TEXT NOT NULL REFERENCES trade_intent (intent_id),
    intent_digest    TEXT NOT NULL,
    approved_by      TEXT NOT NULL,
    approved_at      TEXT NOT NULL,
    expires_at       TEXT,
    scope            TEXT NOT NULL DEFAULT '{}',
    step_up_verified INTEGER NOT NULL DEFAULT 0,
    audit_ref        TEXT
);
CREATE INDEX IF NOT EXISTS ix_approval_intent ON approval (intent_id);

-- ---------------------------------------------------------------- orders & fills
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    intent_id       TEXT REFERENCES trade_intent (intent_id),
    venue           TEXT NOT NULL,
    account_id      TEXT NOT NULL,
    venue_order_id  TEXT,
    state           TEXT NOT NULL,
    submitted_at    TEXT,
    updated_at      TEXT NOT NULL,
    filled_qty      TEXT NOT NULL DEFAULT '0',
    average_price   TEXT,
    fees_quote      TEXT NOT NULL DEFAULT '0',
    funding_quote   TEXT NOT NULL DEFAULT '0',
    reject_reason   TEXT,
    idempotency_key TEXT NOT NULL,
    audit_ref       TEXT,
    UNIQUE (venue, account_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_orders_state   ON orders (state);
CREATE INDEX IF NOT EXISTS ix_orders_updated ON orders (updated_at DESC);

CREATE TABLE IF NOT EXISTS fills (
    fill_id        TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL REFERENCES orders (order_id),
    venue          TEXT NOT NULL,
    venue_trade_id TEXT,
    filled_at      TEXT NOT NULL,
    quantity       TEXT NOT NULL,
    price          TEXT NOT NULL,
    fee_quote      TEXT NOT NULL DEFAULT '0',
    fee_currency   TEXT,
    is_maker       INTEGER,
    side           TEXT NOT NULL,
    audit_ref      TEXT
);
CREATE INDEX IF NOT EXISTS ix_fills_order ON fills (order_id);

-- ---------------------------------------------------------------- durable gateway result
-- The gateway's idempotency ledger was in-memory only (finding F-7): a restart lost it, so a
-- replayed intent could be processed a second time. Persisting the result makes the replay
-- refusal survive a restart, which is the whole point of an idempotency key.
CREATE TABLE IF NOT EXISTS execution_result (
    intent_id         TEXT PRIMARY KEY,
    status            TEXT NOT NULL,
    order_id          TEXT,
    order_state       TEXT NOT NULL,
    reasons           TEXT NOT NULL DEFAULT '[]',
    idempotent_replay INTEGER NOT NULL DEFAULT 0,
    at                TEXT NOT NULL,
    audit_ref         TEXT
);

-- ---------------------------------------------------------------- risk & halts
CREATE TABLE IF NOT EXISTS halt_event (
    halt_id              TEXT PRIMARY KEY,
    seq                  INTEGER,
    action               TEXT NOT NULL CHECK (action IN ('ENGAGE', 'RELEASE')),
    scope                TEXT NOT NULL,
    reason               TEXT NOT NULL,
    triggered_by         TEXT NOT NULL,
    incident_id          TEXT,
    at                   TEXT NOT NULL,
    affected_accounts    TEXT NOT NULL DEFAULT '[]',
    affected_instruments TEXT NOT NULL DEFAULT '[]',
    cancel_working_orders INTEGER NOT NULL DEFAULT 1,
    audit_ref            TEXT
);
CREATE INDEX IF NOT EXISTS ix_halt_at ON halt_event (at);

CREATE TABLE IF NOT EXISTS risk_limit_change (
    change_id        TEXT PRIMARY KEY,
    requested_by     TEXT NOT NULL,
    approved_by      TEXT,
    limit_name       TEXT NOT NULL,
    old_value        TEXT,
    new_value        TEXT NOT NULL,
    requested_at     TEXT NOT NULL,
    effective_at     TEXT,
    cooldown_seconds INTEGER NOT NULL DEFAULT 3600,
    status           TEXT NOT NULL DEFAULT 'PENDING',
    audit_ref        TEXT
);

-- ---------------------------------------------------------------- projection bookkeeping
-- One row per audit record that has been projected into the tables above. Boot recovery compares
-- this set against the chain to finish any write that was audited but not projected (law L-2).
CREATE TABLE IF NOT EXISTS op_projection (
    audit_ref    TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    projected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_projection_entity ON op_projection (entity_type, entity_id);
"""

_MEMORY = """
-- ---------------------------------------------------------------- intelligence memory
-- Schema only, by design: stages 8-10 own the writers. Creating the tables now fixes the shape
-- of persistent memory (provenance is mandatory, an item is immutable once cited) so the
-- intelligence stages cannot invent a store that cannot answer "what was this decision based on".
CREATE TABLE IF NOT EXISTS dossier (
    dossier_id     TEXT PRIMARY KEY,
    instrument_id  TEXT,
    venue          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    state          TEXT NOT NULL DEFAULT 'DRAFT',
    summary        TEXT NOT NULL DEFAULT '',
    stance         TEXT NOT NULL DEFAULT 'ABSTAIN',
    uncertainty    TEXT NOT NULL DEFAULT '',
    sufficiency    TEXT NOT NULL DEFAULT 'INSUFFICIENT',
    payload        TEXT NOT NULL DEFAULT '{}',
    audit_ref      TEXT
);
CREATE INDEX IF NOT EXISTS ix_dossier_created ON dossier (created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_ref (
    evidence_id  TEXT PRIMARY KEY,
    dossier_id   TEXT REFERENCES dossier (dossier_id),
    source       TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'DATA',
    observed_at  TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    data_status  TEXT NOT NULL DEFAULT 'UNAVAILABLE',
    locator      TEXT NOT NULL DEFAULT '',
    checksum     TEXT,
    payload      TEXT NOT NULL DEFAULT '{}',
    audit_ref    TEXT
);
CREATE INDEX IF NOT EXISTS ix_evidence_dossier ON evidence_ref (dossier_id);
CREATE INDEX IF NOT EXISTS ix_evidence_status  ON evidence_ref (data_status);

CREATE TABLE IF NOT EXISTS memory_item (
    memory_id    TEXT PRIMARY KEY,
    kind         TEXT NOT NULL DEFAULT 'OBSERVATION',
    scope        TEXT NOT NULL DEFAULT 'GLOBAL',
    subject      TEXT NOT NULL DEFAULT '',
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    superseded_by TEXT,
    cited_by     TEXT NOT NULL DEFAULT '[]',
    confidence   TEXT,
    payload      TEXT NOT NULL DEFAULT '{}',
    audit_ref    TEXT
);
CREATE INDEX IF NOT EXISTS ix_memory_kind    ON memory_item (kind);
CREATE INDEX IF NOT EXISTS ix_memory_created ON memory_item (created_at DESC);
"""

_AUDIT_APPEND_ONLY = """
-- Append-only enforcement inside SQLite, mirroring the plpgsql triggers in the PostgreSQL target.
-- Requires audit_log to exist: the audit store is constructed before migrations run (see
-- store.migrations.MigrationRunner for the explicit refusal when it is not).
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE is not permitted');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE is not permitted');
END;
"""

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version="0001_operational",
        description="operational state: instruments, decisions, intents, approvals, orders, "
        "fills, execution results, halt events, limit changes, projection bookkeeping",
        sql=_OPERATIONAL,
    ),
    Migration(
        version="0002_memory",
        description="intelligence memory schema (dossiers, evidence refs, memory items) — "
        "tables only; writers arrive with stages 8-10",
        sql=_MEMORY,
    ),
    Migration(
        version="0003_audit_append_only",
        description="append-only triggers on audit_log (no UPDATE, no DELETE)",
        sql=_AUDIT_APPEND_ONLY,
        requires="audit_log",
    ),
)
