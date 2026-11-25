-- NEXUS core schema (Phase 2)
-- Target: PostgreSQL 16 + TimescaleDB (Apache-2 community). SQLite-compatible subset is
-- created automatically by nexus.audit.log.SqliteAuditStore for single-host dev.
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
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
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
    expires_at    TIMESTAMPTZ
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
    digest          TEXT NOT NULL,               -- SHA-256 of material fields
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
    step_up_verified BOOLEAN NOT NULL DEFAULT FALSE
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
    side           TEXT NOT NULL
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
    affected_instruments TEXT[] NOT NULL DEFAULT '{}'
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

-- ---------------------------------------------------------------- market data (TimescaleDB)
-- Converted to a hypertable in production; kept as a plain table so SQLite dev and
-- Postgres-without-Timescale both work. Tiered retention per D-019 / Q-08:
--   raw ticks 7 days -> 1s bars 90 days -> 1m bars 3 years (Feasibility §10.6 Z-04).
CREATE TABLE IF NOT EXISTS market_tick (
    time           TIMESTAMPTZ NOT NULL,
    instrument_id  TEXT        NOT NULL,
    venue          TEXT        NOT NULL,
    bid            NUMERIC(28, 12),
    ask            NUMERIC(28, 12),
    last           NUMERIC(28, 12),
    volume         NUMERIC(28, 12),
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source         TEXT        NOT NULL DEFAULT 'UNKNOWN'
);
CREATE INDEX IF NOT EXISTS ix_tick_time ON market_tick (time DESC);
CREATE INDEX IF NOT EXISTS ix_tick_instrument_time ON market_tick (instrument_id, time DESC);

CREATE TABLE IF NOT EXISTS market_bar (
    time           TIMESTAMPTZ NOT NULL,
    instrument_id  TEXT        NOT NULL,
    venue          TEXT        NOT NULL,
    interval       TEXT        NOT NULL,          -- 1s | 1m | 5m | 1h | 1d
    open           NUMERIC(28, 12) NOT NULL,
    high           NUMERIC(28, 12) NOT NULL,
    low            NUMERIC(28, 12) NOT NULL,
    close          NUMERIC(28, 12) NOT NULL,
    volume         NUMERIC(28, 12) NOT NULL DEFAULT 0,
    trades         INTEGER,
    source         TEXT        NOT NULL DEFAULT 'UNKNOWN',
    PRIMARY KEY (instrument_id, venue, interval, time)
);

-- Uncomment when TimescaleDB is installed on the host (free, Apache-2 community):
-- SELECT create_hypertable('market_tick', 'time', if_not_exists => TRUE,
--                          chunk_time_interval => INTERVAL '1 day');
-- SELECT add_retention_policy('market_tick', INTERVAL '7 days');

COMMIT;
