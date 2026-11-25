# NEXUS Core (backend) — Phase 2

Core foundation: configuration, environment state machine, hash-chained audit log,
secrets handling with redaction, event bus, data-quality gating, deterministic risk
engine, live-authority gate, halt/kill switch, execution governance and the status API.

**Live trading is disabled. There are no venue adapters in this phase.** Every intent
submitted to the gateway terminates in governance with an explicit reason code.

**Cost: $0.** Every dependency is free/open-source (D-019). No paid service is called.

## Layout

```
src/nexus/
  core/          config, environment state, errors/reason codes, ids, time (UTC)
  domain/        canonical instruments, venue mappings, decision records
  audit/         hash-chained append-only audit log (SQLite now, Postgres migration ready)
  secrets/       providers (env / SOPS+age / OpenBao) + redaction
  events/        event bus (in-memory now, NATS JetStream transport ready)
  data/          freshness/integrity gate — fail closed on stale, crossed, missing data
  risk/          deterministic limits + sizing, portfolio snapshots, live-authority gate
  execution/     immutable intent, approval binding, order state machine, halt, gateway
  observability/ structlog (redacted JSON) + Prometheus metrics
  api/           FastAPI status/health/audit/control endpoints
migrations/      SQL schema (PostgreSQL + TimescaleDB target, SQLite-compatible core)
tests/           pytest suite, including the Section 8 risk test vectors
```

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
