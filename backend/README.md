# NEXUS Core (backend) — Phase 3

Phase 2 core foundation: configuration, environment state machine, hash-chained audit log,
secrets handling with redaction, event bus, data-quality gating, deterministic risk
engine, live-authority gate, halt/kill switch, execution governance and the status API.

Phase 3 adds the **instrument master**, **market sessions/calendar**, **free public feed
adapters**, the **first-party Parquet archive** and the **D-024 tiered retention** ladder.

**Live trading is disabled. There are no trading adapters in this phase.** Every intent
submitted to the gateway terminates in governance with an explicit reason code. The Phase 3
adapters are **read-only**: none accepts a credential, none exposes an order verb, and CI
fails the build if either ever becomes false.

**Cost: $0.** Every dependency is free/open-source (D-019). Every data source is a free
public endpoint (D-026). No paid service is called.

## Layout

```
src/nexus/
  core/          config, environment state, errors/reason codes, ids, time (UTC)
  domain/        canonical instruments, venue mappings, decision records
  audit/         hash-chained append-only audit log (SQLite now, Postgres migration ready)
  secrets/       providers (env / SOPS+age / OpenBao) + redaction
  events/        event bus (in-memory now, NATS JetStream transport ready)
  data/          freshness/integrity gate — fail closed on stale, crossed, missing data
                 records.py: canonical Bar/Tick/Quote/Book types, validators, transport
  instruments/   canonical instrument master + certification ladder; trading sessions/DST
  ingestion/     free public feed adapters (bybit, okx, binance_vision, dukascopy) + pipeline
  archive/       bars/rollups, Parquet+zstd store, D-024 tiered retention
  risk/          deterministic limits + sizing, portfolio snapshots, live-authority gate
  execution/     immutable intent, approval binding, order state machine, halt, gateway
  observability/ structlog (redacted JSON) + Prometheus metrics
  api/           FastAPI status/health/audit/control endpoints + read-only Phase 3 routes
migrations/      SQL schema (PostgreSQL + TimescaleDB target, SQLite-compatible core)
tests/           pytest suite, including the Section 8 risk test vectors
```

### Optional extras

| Extra | Packages | Why |
|-------|----------|-----|
| `archive` | `pyarrow`, `duckdb` | Parquet tick/bar store. Without it the archive raises `ArchiveUnavailable` rather than degrading to CSV |
| `streams` | `websockets` | Real-time public venue feeds |
| `postgres` | `psycopg[binary]` | PostgreSQL driver (`sqlalchemy` is a core dependency) |
| `nats` | `nats-py` | Event bus transport |
| `dev` | pytest, pytest-asyncio, ruff, mypy + the archive and streams extras | Local development (`httpx` is a core dependency) |

Install with `pip install -e ".[dev]"`, or in production `pip install ".[archive,streams,postgres,nats]"`.

### Read-only market-data API (Phase 3)

| Route | Purpose |
|-------|---------|
| `GET /v1/instruments` | The canonical master with per-venue certification states |
| `GET /v1/instruments/coverage` | What is proven ready for research/paper/live, and what is missing |
| `GET /v1/instruments/{id}/session` | Whether that instrument should be trading now, with a confidence level |
| `GET /v1/data/coverage` | What the archive actually holds — never what was requested |

All four reject `POST` (405) and need no authentication, because reading market data is not
a control action. There is no route containing `order`, `trade`, `execute`, `position` or
`withdraw`.

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy
```

## Run

```bash
uvicorn nexus.api.app:create_app --factory --host 0.0.0.0 --port 8000
curl -s localhost:8000/v1/status | python3 -m json.tool
```

`GET /v1/status` always reports the true environment, halt state and every blocking
live-authority gate. Control endpoints (`POST /v1/halt`, `/v1/halt/release`) require a
bearer token resolved from the secrets provider; with no token configured they return
503 rather than allowing unauthenticated control.

## Non-negotiables

- Fail closed on unknown state, stale data, missing approval, or unverified venue.
- The risk engine is deterministic; no model can alter hard limits.
- No secret value is ever logged, audited, or returned by the API.
- No live order path exists until Phase 8 adapters are certified and live authority is
  granted (legal review + owner approval + phase gates).
