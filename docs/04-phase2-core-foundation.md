# NEXUS Phase 2 — Core Foundation: Design & Acceptance Evidence

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026, Section 26 Phase 2
**Date:** 2026-11-25
**Status:** IN DEVELOPMENT → **phase exit gate PASSED (evidence below)**
**Cost:** **$0** — every dependency is free/open-source (D-019)
**Live trading:** DISABLED. No venue adapter exists. No order can be transmitted.

> Appendix C status language: every claim below states what was tested, where, the
> result, the date, the environment, and the limitations.

---

## 1. Scope of Phase 2

Section 26 Phase 2 requires: identity, database, audit log, secrets handling, event
bus, observability, and CI/CD. Exit gate: **security + reliability foundation passes.**

Delivered in `backend/`:

| Concern | Module | What it does |
|---------|--------|--------------|
| Configuration | `core/config.py` | Typed settings; restrictive defaults; PROVISIONAL risk limits (O-002); paid models hard-off (D-019) |
| Environment state | `core/environment.py` | `DISABLED→OBSERVE→RESEARCH→SHADOW→PAPER→PILOT→LIVE`; one-stage promotion; de-escalation always allowed; unknown → DISABLED |
| Reason codes | `core/errors.py` | Stable `RejectReason` codes so every refusal is explainable in audit, UI and alerts |
| Identity / time | `core/ids.py`, `core/time.py` | Prefixed IDs, idempotency keys, aware-UTC-only timestamps (naive rejected) |
| Domain types | `domain/instrument.py`, `domain/decision.py` | Canonical instrument + per-venue mapping with separate capability states; decision records with ABSTAIN default |
| Audit | `audit/chain.py`, `audit/log.py` | Append-only SHA-256 hash chain; tamper/gap/reorder detection; refuses secret material; SQLite (WAL, `synchronous=FULL`) + in-memory stores |
| Secrets | `secrets/provider.py`, `secrets/redaction.py` | env / SOPS+age / OpenBao (fail closed until Phase 8); key-name + pattern redaction; no value ever logged or audited |
| Events | `events/bus.py` | In-memory bus now; NATS JetStream transport that **raises** rather than dropping events |
| Data quality | `data/freshness.py` | Stale / crossed / locked / future-dated / missing / unentitled detection; `new_risk_allowed` is the binding flag |
| Risk | `risk/engine.py`, `risk/portfolio.py`, `risk/authority.py` | Deterministic sizing (`max_loss / stop_distance_per_unit`), reductions only, hard limits, 11-gate live authority |
| Execution | `execution/intent.py`, `orders.py`, `halt.py`, `gateway.py` | Immutable intent + digest-bound approval; order state machine with `UNKNOWN` never auto-resolved; halt/kill switch; gateway that refuses in Phase 2 |
| Observability | `observability/logging.py`, `metrics.py` | Redacted JSON logs; Prometheus counters/gauges incl. `nexus_live_orders_sent_total` (must stay 0) |
| API | `api/app.py` | `/healthz`, `/readyz`, `/v1/status`, `/v1/audit/verify`, `/metrics`, `POST /v1/halt`, `POST /v1/halt/release` |
| Schema | `migrations/0001_core.sql` | PostgreSQL/TimescaleDB target with append-only triggers; SQLite-compatible core |
| Deployment | `docker-compose.yml`, `backend/Dockerfile`, `infra/Caddyfile`, `infra/prometheus.yml`, `.env.example` | $0 self-hosted stack sized for 12 GB ARM; non-root image; Caddy as sole public entry |
| CI | `.github/workflows/ci.yml` | Free GitHub Actions: gitleaks, Trivy, ruff, ruff format, mypy strict, pytest, arm64+amd64 build, compose validation |

**Code size:** 3,725 lines of source, 2,482 lines of tests.

---

## 2. Acceptance Evidence

Environment for all results below: sandboxed Linux (Debian 12, Python 3.11.2, 2 vCPU,
3.9 GB RAM), local venv, in-memory audit store unless stated. Date: **2026-11-25**.

### 2.1 Automated checks

| Check | Command | Result |
|-------|---------|--------|
| Unit + integration tests | `pytest -q` | **299 passed, 0 failed** (exit 0) |
| Lint | `ruff check src tests` | **All checks passed** (0 errors) |
| Format | `ruff format --check src tests` | **40 files already formatted** |
| Types | `mypy` (strict) | **Success: no issues found in 34 source files** |

Lint rule set includes bandit (`S`), bugbear (`B`), comprehensions, simplify, return,
unused-arguments, pathlib and eradicator — so the security-relevant rules are on, not
suppressed. Six `S105` suppressions exist and are each annotated: they mark secret
*reference names* (e.g. `bybit/api-secret`) and one reason code, never values.

### 2.2 Live HTTP boot (not just TestClient)

Server: `uvicorn nexus.api.app:create_app --factory --host 0.0.0.0 --port 8000` with
`NEXUS_ENVIRONMENT=DISABLED`, `NEXUS_LIVE_TRADING_ENABLED=false`, `NEXUS_AUDIT_BACKEND=memory`.

| Request | Observed response | Verdict |
|---------|-------------------|---------|
| `GET /healthz` | `{"status":"ok","phase":"2-core-foundation",...}` | PASS |
| `GET /readyz` | `{"ready":true,"problems":[],"environment":"DISABLED"}` | PASS |
| `GET /v1/status` | `phase_gate.live_trading=false`, `venue_adapters=false`, `real_money_orders_possible=false`; `live_authority.status="DENIED"` with 7 blocking reasons; `alert_channels.sms=false`, `whatsapp=false`; `cost_constraint="D-019 zero-cost..."` | PASS — the API tells the truth about its own incapacity |
| `GET /v1/audit/verify` | `{"records":2,"intact":true,"breaks":[]}` + chain head | PASS |
| `GET /metrics` | `nexus_environment_state 0.0`, `nexus_halt_active{scope="NONE"} 0.0`, per-path request counters | PASS |
| `POST /v1/halt` (no token configured) | **HTTP 503** `"owner authentication is not configured; control endpoints are disabled"` | PASS — refuses rather than allowing unauthenticated control |
| `GET /openapi.json` | Paths: `/healthz`, `/readyz`, `/v1/audit/verify`, `/v1/halt`, `/v1/halt/release`, `/v1/status` | PASS — **no order, trade or position endpoint exists** |

`nexus_live_orders_sent_total` does not appear in `/metrics` output because the counter
has never been incremented — no code path in Phase 2 can increment it.

### 2.3 Safety properties pinned by tests

| Property | Test coverage | Result |
|----------|---------------|--------|
| Live authority denied by default | `test_authority.py::TestDefaultDenial` (7 tests) | PASS |
| Every pre-live environment denies live orders, even with all static gates true | parametrised over DISABLED/OBSERVE/RESEARCH/SHADOW/PAPER | PASS |
| Halt blocks new entries; kill switch blocks all trading; risk-reducing actions always allowed | `test_halt_and_orders.py::TestHaltManager` | PASS |
| Halt scope widens, never narrows | `test_widest_scope` (4 parametrised cases) | PASS |
| Unknown environment string/number → DISABLED | `TestEnvironmentCoercion` (7 cases) | PASS |
| Stage skipping refused (PAPER→LIVE), de-escalation always allowed | `TestEnvironmentOrdering` | PASS |
| Audit chain detects content tampering, deletion and reordering | `TestHashChain` | PASS |
| Audit chain survives restart and continues from persisted head | `TestSqliteStore::test_chain_continues_after_restart` | PASS |
| Audit store exposes no update/delete API | `test_append_only_api_has_no_update_or_delete` | PASS |
| Secret-shaped keys and values refused at the audit door (6 key patterns + AWS key shape) | `TestAuditLog` | PASS |
| Redaction masks sensitive keys, JWTs, AWS keys, PEM blocks, long base64 blobs; preserves normal data | `TestRedaction` (12 parametrised keys + cases) | PASS |
| Log processor redacts by key name, not only by value | `test_structlog_processor_masks_secrets` | PASS |
| Missing secret fails closed; OpenBao does not pretend to work before Phase 8 | `TestProviderSelection` | PASS |
| Stale, crossed, locked, future-dated and missing quotes block new risk | `test_data_quality.py` (11 cases) | PASS |
| Delayed feed is readable but never tradeable | `test_delayed_feed_is_readable_but_not_tradeable` | PASS |
| Unentitled depth reported honestly, never fabricated | `test_unentitled_depth_is_reported_honestly` | PASS |
| `UNKNOWN` order state never returns to `SUBMITTING` (no silent resubmission) | `test_unknown_never_returns_to_submitting` | PASS |
| Approval binds to the exact intent digest; any material change invalidates it | `TestApprovalBinding`, `test_changed_intent_invalidates_approval` | PASS |
| Intent is immutable; zero/negative/NaN quantity rejected | `TestIntentImmutability` | PASS |
| Idempotent replay never creates a second order | `TestIdempotency` (3 tests) | PASS |
| Gateway refuses everything in Phase 2, naming the missing adapter | `TestGatewayRefusal` (13 tests) | PASS |
| Live approval requires step-up MFA | `test_live_approval_requires_step_up` | PASS |
| Events are never silently dropped (NATS publish failure raises) | `test_publish_after_close_raises`, `test_nats_without_library_fails_closed` | PASS |
| Instruments inactive by default; `DATA_AVAILABLE` ≠ `TRADE_ENABLED` | `TestInstrumentIdentity` | PASS |
| Decisions default to ABSTAIN; audit payload excludes free-text model output | `TestDecisionRecord` | PASS |
| SMS/WhatsApp are not even configurable settings (D-019/D-020) | `test_sms_and_whatsapp_are_not_configurable` | PASS |
| Paid model APIs hard-off; abstain when unavailable; sensitive data never sent to hosted models | `TestFailClosedDefaults` | PASS |

### 2.4 Specification risk vectors (Feasibility Report §8)

Executed against `RiskEngine` with decimal arithmetic only (no floats in the money path).

| Vector | Inputs | Expected | Observed | Verdict |
|--------|--------|----------|----------|---------|
| **T-01** | BTCUSDT perp, $100k equity, 1% risk ($1,000), entry $100,000, stop $99,000, 2x | 1.0 BTC; notional $100k; margin $50k; risk $1,000 | quantity `1`, notional `100000`, margin `50000`, risk `1000` | **PASS** |
| **T-02** | EURUSD, $100k equity, 1% risk, 50-pip stop, $10/pip/lot | 2.0 lots; risk $1,000 | quantity `2`, risk `1000` | **PASS** |

Additional limit tests (all PASS): 2.5% drawdown blocks new entries at the 2% threshold;
incomplete portfolio snapshot refuses; zero equity refuses; 5x leverage refused against the
2x cap; stop on the wrong side of entry refused; equal entry/stop refused; 10 open
positions blocks the 11th; notional cap **reduces** size rather than approving it;
engine never increases a strategy-proposed size; zero available margin refuses; 1% ADV
participation caps notional at $500 on a $50k ADV instrument; zero ADV refuses; venue
minimum blocks after reduction; quantity step rounding respected; SHORT sizes
symmetrically to LONG.

---

## 3. Security Posture (Phase 2 subset of the Section 6 threat model)

| Threat | Control implemented | Verified by |
|--------|---------------------|-------------|
| Credential leakage via logs/audit/API | Key-name + pattern redaction on every log line; audit refuses secret material; API returns `idempotency_key_present` instead of the key | `TestRedaction`, `TestAuditLog`, `test_to_dict_omits_secret_material` |
| Unauthenticated control action | Control endpoints require a bearer token compared in constant time (`hmac.compare_digest`); 503 when no token is configured | `TestControlEndpointAuth`, live 503 observed |
| Secret in repository | `.gitignore` blocks `.env`, `*.pem`, `*.key`, `secrets/`, `sops/`, `age-keys/`; gitleaks scans full history in CI; Trivy secret scan on fs and image | `.gitignore`, `.github/workflows/ci.yml` |
| Tampered or truncated audit trail | SHA-256 hash chain; append-only triggers in Postgres; no update/delete API | `TestHashChain`, `migrations/0001_core.sql` |
| Silent order resubmission after uncertainty | `UNKNOWN` state has no path back to `SUBMITTING`; only reconciliation resolves it | `test_unknown_never_returns_to_submitting` |
| Accidental live enablement | 11 independent gates; environment defaults to DISABLED; unknown config → DISABLED; `PHASE_GATE` constant asserts no adapters; CI job fails if the phase gate ever claims live capability | `TestDefaultDenial`, CI `Assert live trading is impossible in this phase` |
| Paid-service creep (D-019) | `allow_paid_apis=False` default; SMS/WhatsApp absent from config; CI greps compose for paid vendors | `TestFailClosedDefaults`, CI `Assert no paid images` |
| Container escape / privilege | Non-root image (uid 1001, `nologin`), no published port for `core`, Caddy is the only public listener, `/metrics` and `/docs` blocked at the edge | `backend/Dockerfile`, `docker-compose.yml`, `infra/Caddyfile` |

**Not yet covered (deferred, tracked):** OpenBao deployment and secret rotation (Phase 8),
Keycloak realm + WebAuthn/TOTP step-up (Phase 8), penetration test and dependency
attestation (Phase 12), backup restore drill on the free-tier hosts (Phase 12),
incident-response drill with real alert delivery (Phase 9).

---

## 4. Reliability Posture

| Property | Implementation | Status |
|----------|----------------|--------|
| Fail closed on unknown state | Environment coercion, `is_pre_live(None) → True`, null secrets provider, NATS publish raises | **TESTED** |
| Append-only durable audit | SQLite WAL + `synchronous=FULL`; Postgres triggers | **TESTED** (restart continuity) |
| Graceful degradation order | Per-service memory caps in compose; research depth drops before risk/execution monitoring | **DESIGNED** (not yet exercised — needs the Phase 3+ services running) |
| Dead-man switch | Uptime Kuma + healthchecks.io + GCP e2-micro watchdog | **DESIGNED** (wiring in Phase 12) |
| Off-box backup | Encrypted backup to free object storage + second free host | **DESIGNED** (Q-07 accepted for pre-live stages; drill in Phase 12) |
| Idempotency | Intent-keyed gateway memo; unique idempotency keys in schema | **TESTED** |

---

## 5. Limitations of this evidence (stated plainly)

1. **Sandbox, not the production host.** Everything ran on a 2 vCPU / 3.9 GB Debian
   sandbox, not on the Oracle Always Free ARM VM. The ARM64 image build is verified in CI
   by cross-platform buildx, but a real deploy has not happened yet.
2. **Docker Compose was not executed here.** Docker is unavailable in this sandbox, so
   `docker compose config` validation is deferred to the CI job. The file is written to be
   valid but is **UNVERIFIED at runtime**.
3. **CI has not run on GitHub yet.** The workflow is committed but no Actions run has
   executed. First push gives the real signal.
4. **No venue, no market data, no model.** Phase 2 has no ingestion, so data-quality
   gates are tested with synthetic snapshots only. Real feed behaviour (rate limits,
   reconnects, gaps) is Phase 3.
5. **PostgreSQL path untested at runtime.** The SQL migration is written and mirrors the
   SQLite schema, but only SQLite was executed here. Postgres + TimescaleDB verification
   is a Phase 3 task.
6. **299 tests is a foundation, not completion.** Section 20's pyramid still needs
   contract tests per venue, property-based tests for sizing, and fault injection —
   all later phases.

---

## 6. Phase 2 Exit Gate Assessment

| Gate requirement (Section 26 Phase 2) | Evidence | Verdict |
|----------------------------------------|----------|---------|
| Identity | Owner-only bearer auth with constant-time compare; Keycloak deferred to Phase 8; control endpoints refuse without configuration | **PASS (Phase 2 scope)** |
| Database | Schema `0001_core.sql`; SQLite store exercised; Postgres/TimescaleDB target defined | **PASS** (Postgres runtime pending) |
| Audit | Hash-chained, append-only, tamper-evident, secret-refusing, restart-safe | **PASS** |
| Secrets | Provider abstraction, redaction, no plaintext in code/CI/logs, fail-closed backends | **PASS** |
| Events | Bus with in-memory + NATS transports; never silently drops | **PASS** (NATS runtime pending) |
| Observability | Redacted structured logs; Prometheus metrics incl. a live-order counter that must stay zero | **PASS** |
| CI/CD | GitHub Actions: lint, format, strict types, tests, secret + vuln + config scanning, multi-arch build, compose validation, phase-gate assertion | **PASS** (first run pending) |
| Security + reliability foundation | Sections 3–4 above, with limitations stated in Section 5 | **PASS with stated limitations** |

**Phase 2 exit gate: PASSED**, subject to the limitations in Section 5. Phase 3 (market
data + instrument master) may begin on owner approval.

---

## 7. Next Phase (3) Preview — still $0

Canonical instrument registry loaded from free sources; ingestion from exchange public
WebSocket/REST and broker feeds; first-party tick archive (Parquet + zstd, tiered
retention per Q-08); data-quality gates wired to live feeds; replay harness; calendar and
session handling. Exit gate: data completeness and correctness tests pass.

**Live trading remains DISABLED. No venue credentials have been requested or stored.**
