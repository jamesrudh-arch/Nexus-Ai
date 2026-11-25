# NEXUS — Autonomous Financial Intelligence System

**Status:** Phase 3 (market data + instrument master) built — **868 tests, 0 failures**, ruff clean, mypy strict clean (49 files). CI green on `push` and `pull_request`: lint, types, tests, secret scan, multi-arch image build and a Trivy image scan blocking on HIGH+CRITICAL with no exception list.  
**Cost: $0/month — free tools, free APIs, free data only (D-019).**  
**No trading adapters. No venue credentials. No order endpoint. Live trading disabled in code, not just config.**

> Built to the NEXUS Living Master Specification v1.0 (25 Nov 2026).  
> Owner: Personal, Nigeria. Multi-asset, intraday, autonomous live (within hard limits), conservative risk.

## Docs

| Doc | Purpose |
|-----|---------|
| `docs/00-discovery-ledger.md` | Living record of every owner decision (D-001–D-026) + open items (O-001–O-008; O-001/O-006/O-008 CLOSED) |
| `docs/01-owner-requirements-baseline.md` | Approved baseline (2026-11-25) — gates implementation |
| `docs/02-feasibility-report.md` | Appendix B First Development Report v1.1 — architecture, capability matrix, Nigeria eligibility, **$0 hosting/tooling/data plan**, threat model, staged plan |
| `docs/03-product-ux-bible.md` | Phase 1 — journeys, 15-page architecture, design system, states, mobile, $0 UI stack, accessibility |
| `docs/04-phase2-core-foundation.md` | Phase 2 — design, acceptance evidence, security/reliability posture, stated limitations |
| `docs/05-phase3-market-data.md` | Phase 3 — instrument master, sessions, free-feed adapters, Parquet archive, retention, acceptance evidence, **8 defects found & fixed**, stated limitations |
| `backend/` | `nexus-core` Python package: config, audit chain, secrets, events, data gates, risk engine, live-authority gate, halt, gateway, API — plus Phase 3 `instruments/`, `ingestion/`, `archive/`, `data/records.py` |
| `docker-compose.yml`, `infra/`, `.github/workflows/ci.yml` | $0 self-hosted stack (Postgres+Timescale, NATS, Valkey, MinIO, Caddy, Prometheus/Grafana/Loki) + free CI |

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
- 🔶 **Phase 3 — Market data + instrument master: code-complete, 785 tests passing** (`docs/05-phase3-market-data.md`)
  - Exit gate PASSED for offline-verifiable scope. **Two items outstanding, both need network egress this sandbox lacks:**
    - **P3-A** verify the four free feeds against their *live* endpoints and record real response shapes as fixtures
    - **P3-B** run Dukascopy `verify_layout()` on a real bi5 download before `LAYOUT_VERIFIED` flips to `True`
- ⏳ Open owner decisions: Q-02 exact risk numbers, Q-03 MT/cTrader broker, Q-04 legal review, Q-06 LLM policy
- ⏭️ Next: Phase 4 — venue certification against **demo/paper** accounts only (still $0)

**No live trading until Phases 0–9 gates pass + Nigerian legal review + separate live-authority approval.**

---

*No guaranteed returns. No 99.9% prediction claims. Operational reliability ≠ profitable trades.*
