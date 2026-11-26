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

### 1.5 Scope of 6.2 (implementation, pending unpause)

Operational store (SQLite writer for the eight unused tables, retiring `market_tick`/`market_bar`
from the DDL); durable halt + boot recovery; migration runner; write-ahead discipline; compose tier
fix (`db` → opt-in profile); intelligence-memory schema (tables only, no writer until stages 8–10);
tests for restart-with-active-halt, crash-between-write-and-audit, chain-verify-on-restore and
migration idempotence.
