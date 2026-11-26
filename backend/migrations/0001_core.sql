-- NEXUS core schema (Phase 2)
-- Target: PostgreSQL 16 + TimescaleDB (Apache-2 community). This file is the *portable target*
-- kept by R-1 (D-042), not the schema that runs today: the live schema is the SQLite one in
-- nexus/store/schema.py, applied by nexus/store/migrations.py. The two are kept column-for-column
-- compatible so promotion under trigger conditions T-1...T-4 is a copy, not a rewrite.
--
-- That compatibility was a claim, and until Stage 8.2 nothing checked it: no test read this file, so
-- it had drifted in both directions. An entire table (venue_instrument_mapping) existed only here,
-- which left the venue mappings Stage 7.3 seeded nowhere to be projected; and columns the application
-- really writes — halt_event.cancel_working_orders, audit_ref on six tables, instrument.payload —
-- existed only in the SQLite schema, so a promotion following this file would have lost them.
-- tests/test_schema_fidelity.py now compares the two and fails on divergence, with the legitimate type
-- translations (TIMESTAMPTZ, JSONB, BOOLEAN, TEXT[], and every numeric as TEXT so Decimals survive)
-- written down in one place a reader can argue with.
--
-- The version *boundaries* differ and that is not drift. SQLite applies four versioned migrations;
-- this directory holds two files. The append-only triggers of 0003_audit_append_only are declared in
-- this file, attached to the audit_log table they protect, because PostgreSQL binds a trigger to its
-- table. 0004_memory_fidelity has no counterpart here at all: it exists to bring the SQLite schema
-- back to this one, so the target needed no change to converge. What must agree is the schema the two
-- produce, and that is what the fidelity test asserts.
--
-- All timestamps are TIMESTAMPTZ in UTC. Money/quantity use NUMERIC, never FLOAT.

BEGIN;

-- ---------------------------------------------------------------- audit (append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    seq         BIGINT      PRIMARY KEY,
    record_id   TEXT        NOT NULL UNIQUE,
    event_type  TEXT        NOT NULL,
    actor       TEXT        NOT NULL,
    payload     TEXT        NOT NULL,          -- canonical JSON, redacted before write
    timestamp   TIMESTAMPTZ NOT NULL,
    prev_hash   TEXT        NOT NULL,
    record_hash TEXT        NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_event_type ON audit_log (event_type);
CREATE INDEX IF NOT EXISTS ix_audit_timestamp  ON audit_log (timestamp);

-- Append-only enforcement: no UPDATE, no DELETE. Retention is by partition/archival,
-- never by mutation (Section 15.4).
CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_log;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_log;
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

-- ---------------------------------------------------------------- instruments
CREATE TABLE IF NOT EXISTS instrument (
    instrument_id      TEXT PRIMARY KEY,          -- INS-BTCUSDT-PERP-BYBIT
    canonical_symbol   TEXT NOT NULL,             -- BTC/USDT:USDT
    asset_class        TEXT NOT NULL,
    base_currency      TEXT NOT NULL,
    quote_currency     TEXT NOT NULL,
    settlement_currency TEXT NOT NULL,
    underlying         TEXT,
    expiry             DATE,
    strike             NUMERIC(24, 10),
    option_type        TEXT CHECK (option_type IS NULL OR option_type IN ('CALL', 'PUT')),
    active             BOOLEAN NOT NULL DEFAULT FALSE,   -- staged activation (D-002)
    data_status        TEXT NOT NULL DEFAULT 'UNAVAILABLE',
    notes              TEXT NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS venue_instrument_mapping (
    mapping_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instrument_id      TEXT NOT NULL REFERENCES instrument (instrument_id) ON DELETE CASCADE,
    venue              TEXT NOT NULL,             -- BYBIT | OKX | MT5 | CTRADER | ...
    venue_symbol       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'UNKNOWN',
    contract_size      NUMERIC(28, 12),
    tick_size          NUMERIC(28, 12),
    tick_value         NUMERIC(28, 12),
    min_order_qty      NUMERIC(28, 12),
    max_order_qty      NUMERIC(28, 12),
    qty_step           NUMERIC(28, 12),
    quote_currency     TEXT,
    settlement_currency TEXT,
    trading_hours      TEXT,
    margin_rate        NUMERIC(12, 8),
    fees               JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes              TEXT NOT NULL DEFAULT '',
    certified_at       TIMESTAMPTZ,
    audit_ref          TEXT
    UNIQUE (instrument_id, venue, venue_symbol)
);

-- ---------------------------------------------------------------- decisions & intents
CREATE TABLE IF NOT EXISTS decision (
    decision_id   TEXT PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    state         TEXT NOT NULL,
    verb          TEXT NOT NULL,
    instrument_id TEXT REFERENCES instrument (instrument_id),
    venue         TEXT,
    strategy_id   TEXT,
    model_id      TEXT,
    horizon       TEXT,
    confidence    NUMERIC(6, 5),
    rationale     TEXT NOT NULL DEFAULT '',
    reason_codes  TEXT[] NOT NULL DEFAULT '{}',
    evidence_refs TEXT[] NOT NULL DEFAULT '{}',
    counter_evidence_refs TEXT[] NOT NULL DEFAULT '{}',
    intent_id     TEXT,
    risk_check    JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at    TIMESTAMPTZ,
    audit_ref          TEXT
);
CREATE INDEX IF NOT EXISTS ix_decision_created ON decision (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_decision_state   ON decision (state);

CREATE TABLE IF NOT EXISTS trade_intent (
    intent_id       TEXT PRIMARY KEY,
    decision_id     TEXT REFERENCES decision (decision_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    environment     TEXT NOT NULL,
    instrument_id   TEXT NOT NULL,
    venue           TEXT NOT NULL,
    account_id      TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    order_type      TEXT NOT NULL,
    quantity        NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    limit_price     NUMERIC(28, 12),
    stop_price      NUMERIC(28, 12),
    protective_stop NUMERIC(28, 12),
    take_profit     NUMERIC(28, 12),
    time_in_force   TEXT NOT NULL DEFAULT 'GTC',
    reduce_only     BOOLEAN NOT NULL DEFAULT FALSE,
    post_only       BOOLEAN NOT NULL DEFAULT FALSE,
    quote_currency  TEXT NOT NULL DEFAULT 'USD',
    max_loss_usd    NUMERIC(28, 10),
    estimated_cost_usd NUMERIC(28, 10),
    strategy_id     TEXT,
    model_id        TEXT,
    evidence_summary TEXT NOT NULL DEFAULT '',
    counter_case    TEXT NOT NULL DEFAULT '',
    exit_plan       TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    digest          TEXT NOT NULL,               -- SHA-256 of material fields,
    payload            JSONB NOT NULL DEFAULT '{}'::jsonb
    audit_ref          TEXT
    UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_intent_created ON trade_intent (created_at DESC);

CREATE TABLE IF NOT EXISTS approval (
    approval_id      TEXT PRIMARY KEY,
    intent_id        TEXT NOT NULL REFERENCES trade_intent (intent_id),
    intent_digest    TEXT NOT NULL,              -- binding: mismatch invalidates approval
    approved_by      TEXT NOT NULL,
    approved_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at       TIMESTAMPTZ,
    scope            JSONB NOT NULL DEFAULT '{}'::jsonb,
    step_up_verified BOOLEAN NOT NULL DEFAULT FALSE,
    audit_ref          TEXT
);

-- ---------------------------------------------------------------- orders & fills
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    intent_id       TEXT REFERENCES trade_intent (intent_id),
    venue           TEXT NOT NULL,
    account_id      TEXT NOT NULL,
    venue_order_id  TEXT,
    state           TEXT NOT NULL,
    submitted_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    filled_qty      NUMERIC(28, 12) NOT NULL DEFAULT 0,
    average_price   NUMERIC(28, 12),
    fees_quote      NUMERIC(28, 12) NOT NULL DEFAULT 0,
    funding_quote   NUMERIC(28, 12) NOT NULL DEFAULT 0,
    reject_reason   TEXT,
    idempotency_key TEXT NOT NULL,
    audit_ref          TEXT
    UNIQUE (venue, account_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_orders_state ON orders (state);
CREATE INDEX IF NOT EXISTS ix_orders_updated ON orders (updated_at DESC);

CREATE TABLE IF NOT EXISTS fills (
    fill_id        TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL REFERENCES orders (order_id),
    venue          TEXT NOT NULL,
    venue_trade_id TEXT,
    filled_at      TIMESTAMPTZ NOT NULL,
    quantity       NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    price          NUMERIC(28, 12) NOT NULL,
    fee_quote      NUMERIC(28, 12) NOT NULL DEFAULT 0,
    fee_currency   TEXT,
    is_maker       BOOLEAN,
    side           TEXT NOT NULL,
    audit_ref          TEXT
);

-- ---------------------------------------------------------------- risk & halts
CREATE TABLE IF NOT EXISTS halt_event (
    halt_id       TEXT PRIMARY KEY,
    action        TEXT NOT NULL CHECK (action IN ('ENGAGE', 'RELEASE')),
    scope         TEXT NOT NULL,
    reason        TEXT NOT NULL,
    triggered_by  TEXT NOT NULL,
    incident_id   TEXT,
    at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    affected_accounts   TEXT[] NOT NULL DEFAULT '{}',
    affected_instruments TEXT[] NOT NULL DEFAULT '{}',
    seq                  BIGINT
    cancel_working_orders BOOLEAN NOT NULL DEFAULT TRUE
    audit_ref            TEXT
);

CREATE TABLE IF NOT EXISTS risk_limit_change (
    change_id     TEXT PRIMARY KEY,
    requested_by  TEXT NOT NULL,
    approved_by   TEXT,
    limit_name    TEXT NOT NULL,
    old_value     NUMERIC(28, 12),
    new_value     NUMERIC(28, 12) NOT NULL,
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_at  TIMESTAMPTZ,                   -- cooling-off period (Section 10.1)
    cooldown_seconds INTEGER NOT NULL DEFAULT 3600,
    status        TEXT NOT NULL DEFAULT 'PENDING',
    audit_ref     TEXT
);

-- ---------------------------------------------------------------- market time series: RETIRED
-- market_tick and market_bar were defined here but never written to. The first-party archive
-- (nexus.archive.parquet_store: Parquet + zstd, Hive-partitioned, queried with DuckDB) already
-- holds market time series and is the tested path, so R-1 (D-042) retires these tables instead of
-- wiring them: one data class has exactly one system of record (law L-3), and two durability
-- stories for ticks is how a system ends up quoting numbers it cannot explain.
-- The D-024 retention ladder (ticks 30d -> 1m 12mo -> 5m/1d indefinite) is enforced by
-- nexus.archive.retention, not by a TimescaleDB retention policy.

-- ---------------------------------------------------------------- durable gateway result
-- The gateway's idempotency ledger (Stage 6, finding F-7). Without it a restart lost the record of
-- which intents had already been processed, which is exactly when a duplicate order becomes
-- possible.
CREATE TABLE IF NOT EXISTS execution_result (
    intent_id         TEXT PRIMARY KEY,
    status            TEXT NOT NULL,
    order_id          TEXT,
    order_state       TEXT NOT NULL,
    reasons           TEXT[] NOT NULL DEFAULT '{}',
    idempotent_replay BOOLEAN NOT NULL DEFAULT FALSE,
    at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_ref         TEXT
);

-- ---------------------------------------------------------------- projection bookkeeping
-- One row per audit record projected into the tables above, so boot recovery can finish a write
-- that was audited but never projected (law L-2).
CREATE TABLE IF NOT EXISTS op_projection (
    audit_ref    TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_projection_entity ON op_projection (entity_type, entity_id);

COMMIT;

-- ---------------------------------------------------------------- migration bookkeeping
-- The runner creates this before applying anything (store/schema.py SCHEMA_MIGRATIONS_DDL). It was
-- absent from this file, so a PostgreSQL deploy following it could not record what it had applied —
-- and forward-only migrations are only forward-only if the versions already applied are readable.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    description TEXT NOT NULL,
    statements  INTEGER NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL
);

-- Deferrals, as distinct from bypasses: a version absent from schema_migrations is either waiting for
-- a table this database does not have, or was moved past by mistake. Only the second is fatal, and
-- telling them apart needs the first to be written down. See store/schema.py, same name.
CREATE TABLE IF NOT EXISTS schema_migration_skips (
    version    TEXT PRIMARY KEY,
    reason     TEXT NOT NULL,
    skipped_at TIMESTAMPTZ NOT NULL
);
