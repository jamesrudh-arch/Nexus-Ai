-- NEXUS intelligence-memory schema (Stage 6, PostgreSQL target)
-- Mirror of migration 0002_memory in nexus/store/schema.py (SQLite), which is the one applied
-- today. Tables only, by design: stages 8-10 own the writers. Fixing the shape now is what makes
-- provenance mandatory rather than optional — an evidence row that cannot say where it came from,
-- when it was observed, and what its data status was, cannot support a decision anyone can audit.
--
-- Stage 8.2 delivered the first writer (`evidence_ref`, in nexus/intelligence/evidence.py, audited as
-- `evidence.recorded`) and Stage 8.3 the second (`dossier`, in nexus/intelligence/dossier.py, audited as
-- `dossier.opened`, served read-only by GET /v1/intelligence/dossiers). memory_item still has none; it
-- arrives with stage 10, together with the three columns F-18 wants and D-051 deferred to that batch.
--
-- All timestamps are TIMESTAMPTZ in UTC. Confidence uses NUMERIC, never FLOAT — here. The SQLite side
-- keeps memory_item.confidence as TEXT and constrains it with a CHECK instead, because SQLite's NUMERIC
-- affinity would store a REAL, i.e. a float, and this schema's rule is that Decimals travel as strings:
-- 26 numeric columns across 8 tables are TEXT for that reason today, and 19 across 7 were before 0004
-- added venue_instrument_mapping's seven. Migration 0004 considered changing the type and rejected it;
-- the CHECK is what it added. tests/test_schema_fidelity.py re-derives that count from both DDLs.

BEGIN;

CREATE TABLE IF NOT EXISTS dossier (
    dossier_id    TEXT PRIMARY KEY,
    instrument_id TEXT REFERENCES instrument (instrument_id),
    venue         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    state         TEXT NOT NULL DEFAULT 'DRAFT',
    summary       TEXT NOT NULL DEFAULT '',
    stance        TEXT NOT NULL DEFAULT 'ABSTAIN',   -- ABSTAIN is the default, not a fallback
    uncertainty   TEXT NOT NULL DEFAULT '',
    sufficiency   TEXT NOT NULL DEFAULT 'INSUFFICIENT',
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_ref     TEXT
);
CREATE INDEX IF NOT EXISTS ix_dossier_created ON dossier (created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_ref (
    evidence_id  TEXT PRIMARY KEY,
    dossier_id   TEXT REFERENCES dossier (dossier_id),
    source       TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'DATA',
    observed_at  TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_status  TEXT NOT NULL DEFAULT 'UNAVAILABLE',  -- LIVE|DELAYED|STALE|UNAVAILABLE|FAULT (A-06)
    locator      TEXT NOT NULL DEFAULT '',
    checksum     TEXT,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_ref    TEXT
);
CREATE INDEX IF NOT EXISTS ix_evidence_dossier ON evidence_ref (dossier_id);
CREATE INDEX IF NOT EXISTS ix_evidence_status  ON evidence_ref (data_status);

CREATE TABLE IF NOT EXISTS memory_item (
    memory_id     TEXT PRIMARY KEY,
    kind          TEXT NOT NULL DEFAULT 'OBSERVATION',
    scope         TEXT NOT NULL DEFAULT 'GLOBAL',
    subject       TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_by TEXT,                    -- memory is superseded, never edited in place
    cited_by      TEXT[] NOT NULL DEFAULT '{}',
    confidence    NUMERIC(6, 5),
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_ref     TEXT
);
CREATE INDEX IF NOT EXISTS ix_memory_kind    ON memory_item (kind);
CREATE INDEX IF NOT EXISTS ix_memory_created ON memory_item (created_at DESC);

COMMIT;
