# NEXUS — Autonomous Financial Intelligence System

**Status:** Discovery complete · Feasibility approved (D-018) · Phase 1 UX Bible designed.  
**Cost: $0/month — free tools, free APIs, free data only (D-019).**  
**No production code yet. No live accounts connected. Live trading disabled.**

> Built to the NEXUS Living Master Specification v1.0 (25 Nov 2026).  
> Owner: Personal, Nigeria. Multi-asset, intraday, autonomous live (within hard limits), conservative risk.

## Docs

| Doc | Purpose |
|-----|---------|
| `docs/00-discovery-ledger.md` | Living record of every owner decision (D-001–D-019) + open items (O-001–O-008) |
| `docs/01-owner-requirements-baseline.md` | Approved baseline (2026-11-25) — gates implementation |
| `docs/02-feasibility-report.md` | Appendix B First Development Report v1.1 — architecture, capability matrix, Nigeria eligibility, **$0 hosting/tooling/data plan**, threat model, staged plan |
| `docs/03-product-ux-bible.md` | Phase 1 — journeys, 15-page architecture, design system, states, mobile, accessibility |

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
- ✅ Appendix B — Feasibility Report approved (D-018, 2026-11-25), revised to v1.1 for zero cost (D-019)
- ⏳ **Phase 1 — Product/UX Bible awaiting owner approval** (`docs/03-product-ux-bible.md`)
- ⏳ Open owner decisions: Q-05 (SMS/WhatsApp not free), Q-07 (single free VM), Q-08 (storage cap), Q-01–Q-04
- ⛔ Phase 2+ (code) starts only after Phase 1 approval

**No live trading until Phases 0–9 gates pass + Nigerian legal review + separate live-authority approval.**

---

*No guaranteed returns. No 99.9% prediction claims. Operational reliability ≠ profitable trades.*
