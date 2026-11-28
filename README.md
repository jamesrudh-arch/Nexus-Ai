# NEXUS — Autonomous Financial Intelligence System

**Status:** Phase 3 gate (market data + instrument master) built; Stages 6–11 delivered — **1,668 tests, 0 failures, 2 skipped**, ruff clean, mypy strict clean (73 files). CI green on `push` and `pull_request` across five jobs: secret scan, backend (lint · types · tests · phase-gate assertions), multi-arch image build with a Trivy scan blocking on HIGH+CRITICAL and no exception list, compose validation, and a smoke run.  
**Cost: $0/month — free tools, free APIs, free data only (D-019).**  
**No trading adapters. No venue credentials. No endpoint that can place a real order. Live trading disabled in code, not just config** — `PHASE_GATE` sits at phase 3 with `venue_adapters`, `order_capability`, `real_money_orders_possible` and `live_trading` all `False`, and CI asserts that on every push by asking the running process rather than by grepping route names. The ten routes under `/v1/paper` execute *simulated* fills against real quotes and label every response `simulated: true`; they are proven inert by the same job.

> Built to the NEXUS Living Master Specification v1.0 (25 Nov 2026).  
> Owner: Personal, Nigeria. Multi-asset, intraday, autonomous live (within hard limits), conservative risk.

## Docs

| Doc | Purpose |
|-----|---------|
| `docs/00-discovery-ledger.md` | Living record of every owner decision (D-001–D-029) + open items (O-001–O-011; O-001/O-006/O-008/O-011 CLOSED) |
| `docs/01-owner-requirements-baseline.md` | Approved baseline (2026-11-25) — gates implementation |
| `docs/02-feasibility-report.md` | Appendix B First Development Report v1.1 — architecture, capability matrix, Nigeria eligibility, **$0 hosting/tooling/data plan**, threat model, staged plan |
| `docs/03-product-ux-bible.md` | Phase 1 — journeys, 15-page architecture, design system, states, mobile, $0 UI stack, accessibility |
| `docs/04-phase2-core-foundation.md` | Phase 2 — design, acceptance evidence, security/reliability posture, stated limitations |
| `docs/05-phase3-market-data.md` | Phase 3 (**ACCEPTED**, D-027) — instrument master, sessions, free-feed adapters, Parquet archive, retention, acceptance evidence, CI run history, **30 defects found & fixed**, stated limitations |
| `docs/06-phase4-venue-certification.md` | Phase 4 (in pre-flight) — VM-first bring-up plan, Bybit + OKX demo certification scope (D-028/D-029), **5 pre-flight defects**, what is still unverified |
| `docs/07-production-register.md` | The production register — stage-by-stage narrative, every component's research/implementation/tests/evidence, and the decision log (D-030 onward) |
| `docs/08`–`docs/11` | Stages 1–4 of the design system: brand identity, typography & tokens, dashboard design, interaction & UX |
| `docs/12-stage5-system-architecture.md` | Stage 5 — system architecture, and the ADRs |
| `docs/13-stage6-database-memory.md` | Stage 6 — database & persistent memory, migrations, promotion triggers T-1…T-4 |
| `docs/14-stage7-market-venue-coverage.md` | Stage 7 — market & venue coverage, the instrument master, free-source levers L-A…L-E |
| `docs/15-stage8-intelligence-memory.md` | Stage 8 — intelligence memory: dossiers, evidence, beliefs, findings F-15…F-30 |
| `docs/16-stage9-candidate-thesis.md` | Stage 9 — candidate thesis, decision verbs, the confidence band (D-057) |
| `docs/17-postgres-cutover-audit.md` | The PostgreSQL cutover (D-058) — executed migrations against a real server, credential sweep, findings F-31…F-40 |
| `docs/18-stage11-paper-trading.md` | Stage 11 — **the paper trading platform and the dashboard frontend** (D-059): what it simulates and what it refuses to, the measurements, findings F-41…F-44, questions Q-6…Q-9 |
| `backend/` | `nexus-core` Python package: config, audit chain, secrets, events, data gates, risk engine, live-authority gate, halt, gateway, API — plus Phase 3 `instruments/`, `ingestion/`, `archive/`, `data/records.py`, Stage 6 `store/` (durable operational state, migrations, fail-closed boot recovery, and PostgreSQL as a second engine behind `NEXUS_DATABASE_URL`), Stage 8 `intelligence/`, and **Stage 11 `paper/`** (fill model, account book, engine, real-time analyzer, loop, runner) |
| `frontend/` | The dashboard — Next.js 15 / React 18 / TypeScript / Tailwind, the stack `docs/03` §3.5 ruled. Four of the fifteen ruled pages built against real endpoints (Command Centre, the paper bench, Execution Room, Portfolio & Risk) plus Settings & Governance; the rest listed as staged. Requests only relative `/api/*` paths, which `next.config.mjs` proxies to the backend |
| `docker-compose.yml`, `infra/`, `.github/workflows/ci.yml` | $0 self-hosted stack (NATS, Valkey, MinIO, Caddy, Prometheus/Grafana/Loki; Postgres+Timescale is an **opt-in `postgres` profile** per R-1/D-042 — SQLite + Parquet are the single-node system of record) + free CI |

## Running it

The API and the paper loop are **two processes on purpose**: the API is request/response, while a
real-time loop must keep polling across an API redeploy, and a crash in either must not take the other
down. Both read the same settings and both write the same Parquet archive, so the quotes the runner
observes are the quotes the API can re-read — but they do **not** share a blotter. The runner's ledger is
in-process, and `/v1/paper` serves the API's own platform, so the dashboard does not yet show what the
standalone runner is doing. That is **F-44**, `OPEN`, and `docs/18` §7.1 states it rather than hiding it:
the runner prints a full report every cycle and on exit because nothing else reads it later.

```bash
# backend — SQLite by default (a PostgreSQL server is not $0, D-019)
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,archive]'        # 'archive' = pyarrow + duckdb, both free/OSS
uvicorn nexus.api.app:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"

# the paper trading machine, in its own process
python -m nexus.paper.runner --feed "okx-public:BTC-USDT-SWAP" --poll 5
#   --cycles N   stop after N cycles (exit 4 if nothing was observed, 2 on a bad feed spec)

# dashboard — proxies /api/* to the backend, so the browser never learns where it is
cd frontend && npm install
NEXUS_API_URL=http://127.0.0.1:8000 npm run dev
```

In the compose stack the loop is the `paper-runner` service, on the same image as `core` and **opt-in**:
`docker compose --profile paper up`. It is behind a profile because it spends a rate budget shared across
every endpoint (P-9/F-8) and that should be a choice, not a side effect of bringing the stack up.

The `archive` extra is required by the paper machine, not merely useful to it: the runner archives
each quote **before** the analyzer sees it, because a consumer must never act on a record the archive
does not hold. Without pyarrow the archive raises `ArchiveUnavailable` and names the extra rather than
falling back to a lossy format.

The runner refuses to start if the phase gate or `NEXUS_LIVE_TRADING_ENABLED` would permit a real
order. Its exit codes are deliberate: a bounded run that observed nothing exits non-zero, because a
compose healthcheck, a cron entry or a CI step that reads success during a feed outage is worse than
one that reads failure.

## Key Decisions (summary)

- **Free everything (D-019):** free tools, free APIs, free data, free hosting — **$0/month**. No paid licence, tier, or subscription. Anything with no $0 option is BLOCKED and escalated, never silently purchased.
- Personal accounts only; Nigeria; multi-asset; intraday/day trading
- Fully autonomous live *within hard limits*, staged rollout (Observe → Research → Shadow/Paper → Pilot → Autonomous)
- Capital $100k+ USD equiv.; Conservative risk (1% per trade, ≤2x leverage, 2% daily halt)
- All venues (Bybit, Binance, OKX, MT4, MT5, cTrader, IBKR, OANDA, Alpaca) — each independently certified
- Cloud hosting on free always-on VMs; desktop + iOS + Android; independent research (owner approves changes)
- Nigerian legal review required before live; reference stack (Python + TypeScript + MQL bridges), all OSS

## $0 Stack (verified Nov 2026)

| Layer | Free choice |
|-------|-------------|
| Compute | Oracle Cloud **Always Free** Ampere A1 (2 OCPU / 12 GB ARM, 200 GB, 10 TB egress) + Google Cloud free **e2-micro** as off-box watchdog |
| Data | Exchange public WS/REST, broker feeds (MT5/MT4/cTrader), free public archives, FRED, SEC EDGAR, EIA, CFTC, regulator + exchange announcement feeds |
| Models | Local Ollama (quantized open weights) + free tiers (Gemini, Groq, OpenRouter `:free`, NVIDIA NIM) for non-sensitive research only |
| Infra software | PostgreSQL+TimescaleDB, NATS, Valkey, MinIO, DuckDB/Parquet, OpenBao, Keycloak, Caddy, Prometheus/Grafana/Loki, Uptime Kuma — all self-hosted OSS |
| Alerts | In-app, **Telegram Bot API**, Web Push (self-hosted VAPID), Brevo free email (300/day), healthchecks.io dead-man switch |
| Frontend | Next.js, React, TradingView **Lightweight Charts**, Tailwind, Radix, D3/visx, TanStack, Inter/JetBrains Mono, Lucide — all OSS |
| CI/CD | GitHub free private repos + Actions (2,000 min/mo), Trivy, Semgrep, gitleaks, Dependabot |

⚠️ **Not available at $0:** SMS and WhatsApp alerting (blocked, owner decision Q-05). Trading costs
(spread, commission, funding, slippage) are venue market costs, not tooling — always modelled explicitly.

**Disclosed free-tier trade-offs** (`docs/02-feasibility-report.md` §10.6, Z-01–Z-10): single VM (no HA),
Oracle idle-reclaim/allowance-change risk, 200 GB storage cap, no GPU, non-colocated latency (scalping out
of scope), MT-over-Wine fragility, free-feed rate limits with no SLA.

## Nigeria Eligibility (highlights)

- **Bybit:** Partial access (crypto OK, NGN-only fiat) — ADOPT with limitations
- **OKX:** Available (removed from restricted list July 2026) — ADOPT
- **Binance:** Restricted (NGN/P2P suspended, domain blocked) — sandbox only, live DEFERRED
- **IBKR / OANDA:** Not available to Nigeria — DEFERRED
- **Alpaca:** Paper only; live UNVERIFIED — DEFERRED
- **MT4/MT5/cTrader:** Via Nigeria-serving brokers — ADOPT (broker-dependent)

See `docs/02-feasibility-report.md` §3 for full matrix with sources.

## Gates

- ✅ Phase 0 — Discovery + Owner Requirements Baseline approved (D-017, 2026-11-25)
- ✅ Appendix B — Feasibility Report approved (D-018), revised to v1.1 for zero cost (D-019)
- ✅ Phase 1 — Product/UX Bible approved (D-022, 2026-11-25)
- ✅ Q-05 alerts — free set accepted (D-020); Q-07 single free VM accepted (D-021)
- ✅ **Phase 2 — Core foundation: exit gate PASSED, owner-ACCEPTED** (D-023, `docs/04-phase2-core-foundation.md`)
- ✅ Q-08 storage — tiered retention accepted (D-024); Q-01 currency — USD base + NGN reporting (D-025)
- 🔶 **Phase 3 — Market data + instrument master: code-complete, owner-ACCEPTED (D-027)**, with the two egress-dependent items below still open (`docs/05-phase3-market-data.md`)
  - Exit gate PASSED for offline-verifiable scope. **Two items outstanding, both need network egress this sandbox lacks:**
    - **P3-A** verify the four free feeds against their *live* endpoints and record real response shapes as fixtures
    - **P3-B** run Dukascopy `verify_layout()` on a real bi5 download before `LAYOUT_VERIFIED` flips to `True`
- ⏳ Open owner decisions: Q-02 exact risk numbers, Q-03 MT/cTrader broker, Q-04 legal review, Q-06 LLM policy
- ✅ Stage 6 — database & persistent memory (D-042–D-044); Stage 7 — market & venue coverage **CLOSED** (D-048), Bybit's row left open and visible
- ✅ Stage 8 — intelligence memory, batches 8.1–8.7 approved (D-051…D-056)
- ✅ Stage 9.1 — candidate thesis approved (D-057); F-26 answered and still `OPEN`
- ✅ **PostgreSQL cutover built and audited** (D-058, `docs/17`) — SQLite stays the dev/test default because a server is not $0; F-35…F-38 and F-40 remain `OPEN`
- 🔶 **Stage 11 — paper trading platform + dashboard frontend: delivered, `AWAITING REVIEW`** (D-059 recorded for ratification, `docs/18`) — F-41…F-43 `CLOSED`, **F-44 `OPEN`** (the paper ledger is in-process, so a restart loses the blotter), and **Q-6 needs a ruling** on the route gate that was lexical and is now semantic for the paper namespace
- ⏭️ Next: persist the paper ledger (F-44), then the remaining eleven dashboard pages **behind** their data rather than ahead of it; Phase 4 venue certification against demo/paper accounts only (still $0)

**No live trading until Phases 0–9 gates pass + Nigerian legal review + separate live-authority approval.**

---

*No guaranteed returns. No 99.9% prediction claims. Operational reliability ≠ profitable trades.*
