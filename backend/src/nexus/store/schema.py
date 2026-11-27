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


# Both tables are created on every boot rather than by a versioned migration: the runner has to be
# able to read them before it knows which migrations this database has seen.
#
# `schema_migration_skips` exists because a *deferral* and a *bypass* look identical in
# `schema_migrations` — in both cases the version is simply absent. Migration 0003 is legitimately
# skipped on an ephemeral audit backend (there is no audit_log to protect), and since 0004 there is a
# migration behind it, so applying 0004 while 0003 waits would put an applicable migration below an
# applied one. The runner refuses that shape as a hole, and it is right to: the refusal is how a
# permanently bypassed migration gets noticed. What it could not tell apart was a hole from a skip it
# had itself reported one boot earlier. Remembering the skip is what makes the two distinguishable, so
# a deferral stays a deferral instead of becoming an unbootable database.
SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    description TEXT NOT NULL,
    statements  INTEGER NOT NULL,
    applied_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migration_skips (
    version    TEXT PRIMARY KEY,
    reason     TEXT NOT NULL,
    skipped_at TEXT NOT NULL
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

_MEMORY_FIDELITY = """
-- 0004: make the applied schema faithful to the portable PostgreSQL target, where it was not.
--
-- Found by diffing both DDLs column by column (Stage 8.1, F-15). Two of the three fixes here need a
-- table rebuild because SQLite refuses both `ALTER COLUMN ... TYPE` and `ADD CONSTRAINT` (executed and
-- recorded in `docs/15` §5.3). Both tables are empty today — nothing has ever written to them — but the
-- rebuild copies rows anyway, because a migration that is only safe on an empty table is a migration
-- that will be run against a non-empty one someday.
--
-- Deliberately NOT changed: `confidence` stays TEXT-affinity. The PostgreSQL target says NUMERIC(6,5),
-- but TEXT is this schema's convention for every numeric column — 19 of them across 8 tables — because
-- SQLite's NUMERIC affinity stores a REAL, i.e. a float, and the house rule is that Decimals travel as
-- strings so no precision is lost. Making this one column NUMERIC would make it the only float-backed
-- numeric column in the applied schema and would break that rule. The CHECK below is what actually
-- enforces numeric-ness; ordering must use `CAST(confidence AS REAL)`, which is asserted in
-- tests/test_schema_fidelity.py.
CREATE TABLE IF NOT EXISTS dossier_0004 (
    dossier_id     TEXT PRIMARY KEY,
    instrument_id  TEXT REFERENCES instrument (instrument_id),
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
INSERT INTO dossier_0004 (dossier_id, instrument_id, venue, created_at, updated_at, state, summary,
                          stance, uncertainty, sufficiency, payload, audit_ref)
    SELECT dossier_id, instrument_id, venue, created_at, updated_at, state, summary,
           stance, uncertainty, sufficiency, payload, audit_ref FROM dossier;
DROP TABLE dossier;
ALTER TABLE dossier_0004 RENAME TO dossier;
CREATE INDEX IF NOT EXISTS ix_dossier_created ON dossier (created_at DESC);

CREATE TABLE IF NOT EXISTS memory_item_0004 (
    memory_id     TEXT PRIMARY KEY,
    kind          TEXT NOT NULL DEFAULT 'OBSERVATION',
    scope         TEXT NOT NULL DEFAULT 'GLOBAL',
    subject       TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    superseded_by TEXT,
    cited_by      TEXT NOT NULL DEFAULT '[]',
    confidence    TEXT CHECK (confidence IS NULL OR CAST(confidence AS REAL) <> 0.0
                              OR confidence IN ('0', '0.0', '0.00', '0.000', '0.0000', '0.00000')),
    payload       TEXT NOT NULL DEFAULT '{}',
    audit_ref     TEXT
);
INSERT INTO memory_item_0004 (memory_id, kind, scope, subject, body, created_at, superseded_by,
                              cited_by, confidence, payload, audit_ref)
    SELECT memory_id, kind, scope, subject, body, created_at, superseded_by,
           cited_by, confidence, payload, audit_ref FROM memory_item;
DROP TABLE memory_item;
ALTER TABLE memory_item_0004 RENAME TO memory_item;
CREATE INDEX IF NOT EXISTS ix_memory_kind    ON memory_item (kind);
CREATE INDEX IF NOT EXISTS ix_memory_created ON memory_item (created_at DESC);

-- The third fix is additive: the PostgreSQL target has declared venue_instrument_mapping since
-- 0001_core.sql and the applied schema never had it at all, so the four venue mappings Stage 7.3
-- seeded had nowhere to be projected (F-16). BIGINT GENERATED ALWAYS AS IDENTITY has no SQLite
-- equivalent; INTEGER PRIMARY KEY AUTOINCREMENT is the translation, and NUMERIC(28,12) becomes TEXT
-- for the same precision reason as confidence above.
CREATE TABLE IF NOT EXISTS venue_instrument_mapping (
    mapping_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id       TEXT NOT NULL REFERENCES instrument (instrument_id) ON DELETE CASCADE,
    venue               TEXT NOT NULL,
    venue_symbol        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'UNKNOWN',
    contract_size       TEXT,
    tick_size           TEXT,
    tick_value          TEXT,
    min_order_qty       TEXT,
    max_order_qty       TEXT,
    qty_step            TEXT,
    quote_currency      TEXT,
    settlement_currency TEXT,
    trading_hours       TEXT,
    margin_rate         TEXT,
    fees                TEXT NOT NULL DEFAULT '{}',
    notes               TEXT NOT NULL DEFAULT '',
    certified_at        TEXT,
    audit_ref           TEXT,
    UNIQUE (instrument_id, venue, venue_symbol)
);
CREATE INDEX IF NOT EXISTS ix_mapping_venue ON venue_instrument_mapping (venue, venue_symbol);
"""

_MEMORY_BELIEFS = """
-- 0005: the three columns F-18 asked for and D-051 deferred to this batch, plus the link that lets one
-- evidence row say it contradicts another.
--
-- Found by reading the approved view against the delivered schema (Stage 8.1, F-18, `docs/15` §4). `docs/03`
-- §7 asks the Intelligence Centre to show "beliefs with confidence, validity interval, change conditions",
-- and `docs/10` §3.1 turns the omission into a rule: confidence comes "as a band with validity interval and
-- change conditions", and "a point estimate without them is a defect". `memory_item` had `confidence` and
-- neither of the other two, so the one column it had was the one those sentences call a defect standing
-- alone. The refusal that enforces the sentence lives in `intelligence/memory.py`, not here: a column cannot
-- refuse a row that fills it badly, and these three are nullable because not every memory item is a belief.
--
-- All four are `ADD COLUMN`, which is what `docs/15` §5.3's executed survey makes cheap. SQLite permits a
-- nullable column, a NOT NULL column with a constant default, a self-referencing foreign key and a CHECK on
-- a new column, and refuses only `ALTER COLUMN ... TYPE` and `ADD CONSTRAINT`. Nothing here needs the
-- create-copy-drop-rename rebuild 0004 needed, and no row is copied, because none of the four changes what
-- an existing column means.
--
-- Deliberately NOT added, each with its reason rather than in silence:
--   * `expires_at`. F-18's second gap is that no expiry column exists anywhere, and §5.3 lists it among the
--     cheap additions, but the scope this batch was ruled into is three columns on `memory_item` plus
--     `contradicts` (`docs/15` §11.14 ruling 4, restating D-052's ruling 3) and `expires_at` is not one of
--     the three. `valid_until` is not a substitute: it says until when the claim holds in the world, while
--     an expiry says when this system should stop serving the row, and `docs/10` §3.1's "expiring TTLs" asks
--     for the second. That gap stays open and is recorded as still open.
--   * `confidence_low` and `confidence_high`. `docs/10` §3.1 asks for confidence "as a band" and D-035
--     approved "beliefs as bands". A band is an interval on the confidence axis, and `valid_from` and
--     `valid_until` are on the time axis, so after this migration a belief still carries exactly one
--     number. That is F-24, recorded rather than fixed here, because two more columns are not this
--     batch's ruling either.
--   * an index on `valid_until`. Nothing queries by validity yet, and an index with no reader behind it is
--     machinery nobody reads — the reasoning D-052's ruling 4 used to decline a periodic checksum audit.
--     `memory_items()` therefore scans, and the scan is written down in the store instead of left to be
--     discovered by whoever hits it.
--
-- `contradicts` is the fourth column and the one that is not on `memory_item`. It points at another row of
-- the same table, which SQLite accepts on `ADD COLUMN` (a self-referencing foreign key with a NULL default)
-- and which `PRAGMA foreign_key_list` then reports. Like every foreign key here it is declared and not
-- enforced, so `intelligence/evidence.py` refuses a dangling parent itself. It also joins
-- `CHECKSUMMED_FIELDS`: a stored column outside that tuple is a column that can change undetected, which is
-- F-21, and `tests/test_evidence_writer.py` derives the covered set from this table so the two had to move
-- together.
ALTER TABLE memory_item ADD COLUMN valid_from TEXT;
ALTER TABLE memory_item ADD COLUMN valid_until TEXT;
ALTER TABLE memory_item ADD COLUMN change_conditions TEXT NOT NULL DEFAULT '';
ALTER TABLE evidence_ref ADD COLUMN contradicts TEXT REFERENCES evidence_ref (evidence_id);
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
    Migration(
        version="0004_memory_fidelity",
        description="restore dossier's instrument foreign key, constrain memory_item.confidence to a "
        "numeric value, and create venue_instrument_mapping — the three places the applied schema had "
        "diverged from the portable PostgreSQL target (F-15, F-16)",
        sql=_MEMORY_FIDELITY,
        requires="dossier",
    ),
    Migration(
        version="0005_memory_beliefs",
        description="give memory_item the validity interval and change conditions F-18 asked for, and "
        "give evidence_ref a contradicts link — the columns the approved view needs and D-051 deferred "
        "to the batch that writes memory_item",
        sql=_MEMORY_BELIEFS,
        # Both tables this migration alters arrive from 0002 in one executescript, so requiring one of
        # them requires the other. `memory_item` is named because it is the table this batch is about.
        requires="memory_item",
    ),
)
