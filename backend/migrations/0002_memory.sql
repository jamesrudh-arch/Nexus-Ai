-- NEXUS intelligence-memory schema (Stage 6, PostgreSQL target)
-- Mirror of migration 0002_memory in nexus/store/schema.py (SQLite), which is the one applied
-- today. Tables only, by design: stages 8-10 own the writers. Fixing the shape now is what makes
-- provenance mandatory rather than optional — an evidence row that cannot say where it came from,
-- when it was observed, and what its data status was, cannot support a decision anyone can audit.
--
-- Stage 8.2 delivered the first writer (`evidence_ref`, in nexus/intelligence/evidence.py, audited as
-- `evidence.recorded`) and Stage 8.3 the second (`dossier`, in nexus/intelligence/dossier.py, audited as
-- `dossier.opened`, served read-only by GET /v1/intelligence/dossiers). Stage 8.5 delivered the third
-- (`memory_item`, in nexus/intelligence/memory.py, audited as `memory.recorded`) together with the three
-- columns F-18 wants and D-051 deferred to that batch — `valid_from`, `valid_until`, `change_conditions`
-- — and `evidence_ref.contradicts`, the link `docs/10` §3.1's "contradictions highlighted and linked"
-- needs. All four are declared below, where they always were for this file: the PostgreSQL target states
-- the end state and the SQLite side walks to it, which is why they reach SQLite through migration
-- `0005_memory_beliefs` (four `ADD COLUMN`s) rather than through an edit of `0002_memory` there — applied
-- migrations are immutable, and `tests/test_schema_fidelity.py` pins every checksum that says so.
-- Nothing serves `memory_item` over HTTP yet, and no writer calls any of the three.
--
-- Stage 8.7 added the fourth column F-18 asked for, `memory_item.expires_at`, on the same terms: declared
-- below where it always was for this file, reaching SQLite through migration `0006_memory_expiry` (one
-- `ADD COLUMN`) rather than through an edit of `0002_memory` there. D-054's ruling 4 ordered it and D-055's
-- ruling 4 scoped it to `memory_item` alone. `evidence_ref` does not gain one, and `valid_until` is still
-- not a substitute for it: `valid_until` says until when a claim holds in the world, while an expiry says
-- when this system should stop serving the row. **Nothing acts on the column** — no reader filters by it
-- and no route serves it — because `docs/10` §3.2's V1–V3 verification gates finalise at Stage 11 and are
-- what would consume it.
--
-- One thing this file still deliberately does not declare, because no batch has ruled on it. There is no
-- confidence band: `confidence` stays one NUMERIC(6,5) point, while `docs/10` §3.1 asks for it "as a band"
-- and D-035 approved "beliefs as bands". That is F-24 (`docs/15` §12), recorded rather than fixed, because
-- a band is two columns and the shape of a band has no ruling behind it.
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
    audit_ref    TEXT,
    -- Stage 8.5, F-18's fourth gap: one row saying it contradicts another. `docs/10` §3.1 asks the
    -- dossier view for "contradictions highlighted and linked" and before this column nothing recorded
    -- that two sources disagree, so nothing could be highlighted. It points one way and nothing
    -- back-links it in the store: the route derives the reverse direction by scanning, and a reader who
    -- wants "what contradicts this row" from the database alone has to scan too. Declared, not enforced
    -- (PRAGMA foreign_keys off), so evidence.py refuses a dangling parent itself. In CHECKSUMMED_FIELDS,
    -- because a stored column the checksum does not cover is a column that can change undetected (F-21).
    contradicts  TEXT REFERENCES evidence_ref (evidence_id)
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
    audit_ref     TEXT,
    -- Stage 8.5, F-18's first gap: `docs/03` §7 asks for "beliefs with confidence, validity interval,
    -- change conditions" and `docs/10` §3.1 calls a confidence without them a defect. All three are
    -- nullable or defaulted rather than NOT NULL because not every memory item is a belief — an
    -- OBSERVATION has no validity interval and needs none. The combination is what the writer refuses,
    -- and it refuses it in nexus/intelligence/memory.py rather than in a CHECK here, because the rule
    -- is "a point estimate without them is a defect", which is a statement about three columns at once
    -- and not about any one of them.
    --
    -- `valid_from` and `valid_until` bound the claim in the world, not the row in the store: they say
    -- from when and until when the belief is asserted to hold, which is not `created_at` (when this
    -- system recorded it) and not an expiry (when this system should stop serving it). SQLite reaches
    -- these four by appending them, because ADD COLUMN has no position clause, so its column order
    -- differs from the order declared here. tests/test_schema_fidelity.py compares names, types,
    -- nullability and foreign keys, and does not compare position.
    valid_from       TIMESTAMPTZ,
    valid_until      TIMESTAMPTZ,
    change_conditions TEXT NOT NULL DEFAULT '',
    -- Stage 8.7, F-18's second gap: `docs/10` §3.1 asks the memory & knowledge region to render
    -- "expiring TTLs", and before this column no expiry existed anywhere in either schema. It is not
    -- `valid_until` and does not replace it: that column bounds the claim in the world, this one says
    -- when *this system* should stop serving the row, and a belief can hold until 2027 while being
    -- expired for our purposes tomorrow. Nullable because not every memory item is a belief with a TTL —
    -- an OBSERVATION has no expiry and needs none — and NULL means "no expiry was stated", which is not
    -- the same claim as "never expires". The writer validates it
    -- (nexus/intelligence/memory.py) rather than a CHECK here, and **nothing reads it yet**: no filter,
    -- no route, no policy. D-055's ruling 4 is that the column is stored and acted on by nothing until
    -- Stage 11 finalises the V1–V3 gates that would consume it, because a filter invented here would be
    -- an expiry policy nobody has ruled on, wearing a WHERE clause.
    expires_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_memory_kind    ON memory_item (kind);
CREATE INDEX IF NOT EXISTS ix_memory_created ON memory_item (created_at DESC);

COMMIT;
