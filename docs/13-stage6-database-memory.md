# 13 — Stage 6: Database & Persistent Memory

Status: **IN PROGRESS**, sub-deliverables: 6.1 persistent-memory architecture + P-6 ruling (this
document §1, board `design/stage6-1-persistent-memory.html`) → 6.2 implementation (requires the
backend pause at `d9a83fe` to be lifted by the owner). Design only so far: Stage 6.1 changes no
code. Started after Stage 5 stage-level approval (D-041), which carried P-6 in as the first item.

Binding inputs: `backend/migrations/0001_core.sql`, `audit/log.py`, `execution/halt.py`,
`archive/parquet_store.py`, `api/app.py`, `core/config.py`, `pyproject.toml`,
`docker-compose.yml`, `tests/`; A-02/A-03/A-05/A-06 (D-040); D-019 ($0), D-024 (retention),
D-025 (USD risk math / NGN display), D-028 (VM-first), D-041 (T1–T5 tiers).

---

## 1. Sub-deliverable 6.1 — Findings, storage tiers, P-6 ruling (BUILT — AWAITING REVIEW)

### 1.1 Findings (research, each cited to code)

- **F-1 (positive).** Two durable stores exist and are tested: `SqliteAuditStore` (WAL,
  `synchronous=FULL`, SHA-256 hash chain, tamper/gap/reorder detection, `assert_no_secrets`
  refusing secret keys, patterns and long secret-like values; 22 tests) and `ParquetArchive`
  (zstd, Hive-style `dataset/venue/symbol/interval/year/month` partitions, files never rewritten,
  DuckDB reads; 59 tests in `test_archive_bars.py` plus `test_parquet_archive.py`,
  `test_retention.py`).
- **F-2 (gap).** **Operational state has DDL but no writer.** `0001_core.sql` defines 12 tables;
  a grep for `INSERT`/`CREATE TABLE` across `src/nexus` returns two hits only (`audit/log.py`, and
  a DuckDB `SELECT` in `parquet_store.py`). So `decision`, `trade_intent`, `approval`, `orders`,
  `fills`, `halt_event`, `risk_limit_change` and `instrument` have no persistence path — a core
  restart loses them. `market_tick`/`market_bar` are unused for a good reason: Parquet already
  holds that job, so they should be **retired from the DDL, not wired** (L-3, one system of record).
- **F-3 (safety gap).** **Halt is volatile, so a restart clears an active halt.**
  `HaltManager.__init__` (halt.py:90–96) builds `HaltState()` = `scope NONE, active False`
  (halt.py:43–56); nothing re-derives state from the audit chain at boot. Fail-open on restart is
  the one behaviour this system must never have. The engagement *is* in the chain — recovery is
  derivable, just not derived.
- **F-4 (cost nuance).** The Postgres path is part-paid, not free: portable DDL (TIMESTAMPTZ UTC,
  NUMERIC never FLOAT, append-only triggers, hypertable conversion deliberately commented at line
  243) and `sqlalchemy>=2.0,<3` already a **runtime** dependency — but no driver installed
  (`asyncpg`, `psycopg` both absent), and the wiring was Phase 4 work that never happened.
- **F-5 (positive).** The refusal is well built: an unrecognised `database_url` scheme is refused
  rather than downgraded, and only the scheme enters the error context because a URL can carry a
  password (api/app.py:311–341).
- **F-6 (cost of status quo).** `core` waits on `db` healthy while nothing reads it: 1.5 GB of the
  12 GB free-tier budget plus startup latency — documented by the compose file itself.

### 1.2 Storage tiers

Eight data classes with engine, durability, writer-today status and retention rule (board table +
diagram). Durable and tested: governance record (SQLite audit chain) and market time series
(Parquet+zstd, D-024 ladder ticks 30d · 1m 12mo · 5m/1d indefinite). Gap Stage 6 closes:
operational state. Schema-only, writer later: intelligence memory (dossiers, evidence refs —
stages 8–10). Engine undecided and not claimed: vector recall (pgvector would pull Postgres in via
trigger T-3; a DuckDB VSS path is unverified in this environment). Volatile by design: Valkey
cache (loss costs latency, never correctness) and MinIO objects (exports, reports, learning
artifacts with provenance).

### 1.3 P-6 ruling — recommendation R-1

Options examined: (a) wire Postgres as system of record — rejected for now (new driver, untested
path, 1.5 GB, and migrating a working tested audit store is risk where there is no defect);
(b) SQLite-only with `db` removed — close but under-specifies the future and discards a paid seam;
(c) hybrid SQLite audit + Timescale time series — rejected, it duplicates what Parquet+DuckDB
already does and is tested, giving one data class two durability stories.

**R-1 (recommended):** declare **SQLite (governance + operational state) and Parquet+zstd/DuckDB
(time series) the single-node system of record**. Move TimescaleDB out of `core`'s `depends_on`
into an opt-in `db` profile, returning 1.5 GB to the budget (T3 drops from 3.71 GB to 2.18 GB).
Keep `0001_core.sql` as the portable migration target and the existing `AuditStore` Protocol as the
seam, so Postgres remains one wiring change away — gated on four **measured** trigger conditions:
**T-1** a second writer process exists (SQLITE_BUSY contention); **T-2** operational write
throughput hits a benchmarked ceiling (Stage 23, not guessed); **T-3** hypertable partitioning or
pgvector genuinely required; **T-4** deployment leaves a single VM. Two audit stores at once is
worse than the memory it saves.

### 1.4 Laws (binding on 6.2 and every later stage)

**L-1 fail-closed boot** — halt re-derived from the audit chain at start; last engagement without
a matching release ⇒ boot HALTED (closes F-3). **L-2 durable before acknowledged** — an intent,
approval, order or fill is acknowledged only after its row and its audit entry commit.
**L-3 one system of record per data class** — never two audit stores; a cache is never truth.
**L-4 portable DDL, forward-only migrations** — TIMESTAMPTZ UTC, NUMERIC never FLOAT, append-only
triggers on governance records; migrations numbered, idempotent, and their application is itself an
audit event; no destructive migration without owner approval. **L-5 secrets refused at the store
boundary** — `assert_no_secrets` before any write; a URL contributes only its scheme to errors.
**L-6 a restore is a verified restore** — recovery is incomplete until `/v1/audit/verify` passes on
the restored chain and reconciliation closes; until then, no new risk.

Boot sequence under L-1 (six steps on the board): open store → verify chain (refuse to serve on
tamper/gap/reorder, CRIT alert) → re-derive halt → reconcile open orders to UNKNOWN (never
auto-resolved; new risk blocked until closed) → apply migrations (audited) → `/readyz` only after
all pass, `/healthz` degraded with the specific reason.

### 1.6 Approval

§1 **APPROVED 2026-11-25 (D-042)**, and with it **R-1 adopted as the resolution of P-6**: SQLite
plus Parquet/DuckDB are the single-node system of record; TimescaleDB is demoted to an opt-in
profile; the portable DDL and the `AuditStore` Protocol remain the seam; triggers T-1…T-4 must be
measured. Laws L-1…L-6 bind 6.2 and every later stage. **Nothing has been applied yet** — the
compose tier change, the DDL retirement of `market_tick`/`market_bar`, and every writer are 6.2
code, and the backend remains paused at `d9a83fe` until the owner lifts it.

### 1.5 Scope of 6.2 (implementation, pending unpause)

Operational store (SQLite writer for the eight unused tables, retiring `market_tick`/`market_bar`
from the DDL); durable halt + boot recovery; migration runner; write-ahead discipline; compose tier
fix (`db` → opt-in profile); intelligence-memory schema (tables only, no writer until stages 8–10);
tests for restart-with-active-halt, crash-between-write-and-audit, chain-verify-on-restore and
migration idempotence.

---

## 2. Sub-deliverable 6.2 — Implementation (BUILT — AWAITING REVIEW)

Board: `design/stage6-2-implementation-evidence.html`. The owner lifted the backend pause for this
batch, so unlike Stages 1–5 it changes production code.

### 2.1 Gate evidence

```
pytest              975 passed, 2 skipped, 0 failed   (was 930 passed; +47 new tests)
  skips are pre-existing: live-egress verification, 7m interval
ruff check          All checks passed (src + tests)
ruff format         80 files already formatted
mypy --strict       Success: no issues found in 56 source files
new tests           47 — test_migrations.py 12 · test_store_persistence.py 17 · test_boot_recovery.py 18
```

### 2.2 What was built

`backend/src/nexus/store/` — six modules: `schema.py` (versioned SQLite DDL held in Python, because
the repo's `migrations/` directory is not mounted into the core image), `migrations.py`
(forward-only, checksummed, audited runner with skip-with-report), `operational.py`
(`SqliteOperationalStore`: nine entities, Decimal stored as exact TEXT, secrets refused at the
boundary, `OperationalStore` Protocol as the Postgres seam), `writeahead.py` (audit-first writes and
the projector registry), `recovery.py` (fail-closed boot recovery), `serialise.py` (canonical JSON
delegating to the system-wide `canonical_json`, so stored and audited payloads are byte-identical).

Wiring: `core/errors.py` gained four reason codes (`PERSISTENCE_FAILED`, `AUDIT_CHAIN_INVALID`,
`BOOT_RECOVERY_INCOMPLETE`, `MIGRATION_INVALID`); `audit/log.py` gained `records()` and a read-only
`store` property; `execution/halt.py` gained a durable `store` and `restored_state`;
`execution/gateway.py` gained a durable idempotency ledger with `rehydrate_from_store()`;
`api/app.py` builds the operational store, runs boot recovery, fails closed into the kill switch when
the chain does not verify, reports recovery problems through `/readyz`, and exposes a `persistence`
block on `/v1/status` (A-06: status on the wire).

Migrations: `0001_operational` (nine entity tables + `op_projection`), `0002_memory`
(`dossier`/`evidence_ref`/`memory_item` — schema only, writers arrive with stages 8–10),
`0003_audit_append_only` (SQLite triggers mirroring the PostgreSQL ones: UPDATE and DELETE on
`audit_log` are refused inside the database).

PostgreSQL target: `market_tick` and `market_bar` **retired** from `0001_core.sql` rather than wired
(Parquet+zstd already holds time series; one data class, one system of record), `execution_result`
and `op_projection` added, and `0002_memory.sql` created as the mirror.

Deployment: `db` moved to an opt-in `postgres` profile, `core` now depends on `nats` only, the
compose header documents tiers T1–T5 with the budget law, the KNOWN GAP note is replaced by a
RESOLVED note citing R-1/D-042, `infra/smoke-test.sh` defaults to `nats core`, and `.env.example`
states that SQLite is the implemented system of record with Postgres gated on triggers T-1…T-4.

### 2.3 Findings closed

**F-2** operational state is durable and tested. **F-3** a halt survives a restart with its original
incident id, scope, reason and timestamp; an unreadable halt history boots into the kill switch.
**F-6** 1.5 GB returned to the budget (T3 3.71 GB → 2.18 GB without `db`). **F-7** — found during
implementation — the gateway's `_seen_intents` ledger was in memory, so a restart lost the record of
which intents had been processed, which is precisely when a duplicate order becomes possible; it is
now durable and rehydrated at construction.

### 2.4 Defects the implementation exposed (ID-n; not register decisions)

**ID-1** migration 0003 failed outright on an ephemeral audit backend (no `audit_log` table to
protect) → migrations gained a `requires` declaration and a skip is *reported and not recorded*, so
a later durable boot still applies it. **ID-2** the forward-only gap check called a skipped
migration a hole, breaking the ordinary path of reopening a durable store with no audit store →
a hole is now an applicable pending migration *below* the last applied one. **ID-3** the explicit
ordering refusal never fired because SQLite reports `no such table: main.audit_log` → match widened.
**ID-4** tooling, not product: a patch script nested a docstring inside a triple-quoted string, died
at parse time and applied nothing while the suite still showed the old failures; caught by
assert-before-write, re-run. Recorded because a silent no-op patch is how evidence gets misreported.

### 2.5 Limitations (part of the deliverable)

Foreign keys declared but not enforced (`PRAGMA foreign_keys` off: recovery re-projects in chain
order, which is not always parent-first, and a hard FK failure mid-recovery would be worse than the
inconsistency it prevents). No PostgreSQL store implementation and no driver installed. Triggers
T-1…T-4 unmeasured — no claim that SQLite is sufficient at any particular scale. Vector recall still
undecided. Intelligence-memory tables have no writers. Off-VM backup remains untested: recovery here
means restart on the same host, and the 5.2 DR rows are unchanged. The compose change was validated
by YAML parse plus two asserted facts (db profiles, core depends_on) because Docker is unavailable in
this sandbox; CI's compose job is the real validation.

### 2.6 Stage 6 completion summary (pending stage-level approval)

6.1 fixed the architecture and resolved P-6 with R-1 (D-042); 6.2 implemented it: operational state
is durable, halt survives restart, the idempotency ledger survives restart, migrations are
forward-only and audited, boot recovery fails closed, and the deployment no longer pays for a
database nothing reads. Stage-level approval gates Stage 7 (market/venue coverage).
