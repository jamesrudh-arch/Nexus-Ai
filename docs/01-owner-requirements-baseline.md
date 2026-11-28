# NEXUS Owner Requirements Baseline — Approved

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026  
**Approved:** 2026-11-25 (D-017)  
**Owner:** Personal, Nigeria  
**Status:** APPROVED — gates implementation per Section 0.4

> This baseline is the contract for the build. Changes require owner approval, rationale, date, and impact analysis (Section 0.5). Never silently rewrite a confirmed requirement.

## 1. Confirmed Decisions

### 1.1 Product & Users
- **Product:** NEXUS — Autonomous Financial Intelligence System (working label, may be renamed without architecture change)
- **User model:** Personal accounts only (single owner). No multi-user SaaS, no billing, no tenancy.
- **Jurisdiction:** Nigeria (resident, operating from Nigeria). Nigerian legal review required before live.
- **Visual identity:** Dark, restrained, premium terminal (Section 17). Green/red = market direction, amber = warning, cyan = system, purple = research. Real data only; no fake metrics.

### 1.2 Markets & Horizons
- **Asset universe:** Multi-asset broad (Section 3): FX, equities, ETFs/ETPs, indices, commodities, futures, options, fixed income, crypto, other listed products. Full canonical registry; staged activation.
- **Horizons/styles:** Intraday / day trading (scalping, intraday, day). Real-time quotes, tick/minute candles, order-book depth where entitled. No unvalidated HFT claims.
- **No-trade is valid:** System must be able to say "no trade is justified" (Section 35).

### 1.3 Autonomy & Authority
- **Target mode:** Fully autonomous live *within hard limits* (Section 2). NEXUS may independently research, decide, execute, and manage trades.
- **Staged rollout (mandatory):** Observe → Research → Shadow/Paper → Restricted live pilot → Autonomous live. Each stage requires separate owner approval.
- **Authority is scoped:** Per account, platform, asset class, instrument group, strategy, order type, leverage band, notional limit, daily loss limit, open-risk limit, operating schedule (Section 2.1).
- **Emergency halt:** Blocks new entries, cancels eligible working orders per configured policy, moves to controlled safe state.

### 1.4 Capital & Risk
- **Initial capital:** Over $100,000 USD equivalent (per-account currency OPEN: USD/USDT/NGN).
- **Risk profile:** Conservative — ~1% max risk per trade, leverage ≤2x, halt new entries at ~2% daily drawdown. Exact numbers to be finalized in Risk Policy (PROVISIONAL until then).
- **Hard limits override AI:** Risk engine is deterministic, not generative. No model/plugin/strategy can change hard limits. Limit changes require authenticated owner action + audit + cooling-off (Section 10.1).
- **Sizing:** Instrument-specific contract value, tick value, FX conversion, margin, stop distance, volatility, liquidity, portfolio risk. Never fixed lot size (Section 10.2).
- **No withdrawal authority:** Trading credentials must not have withdrawal/transfer permissions (Section 13.3).

### 1.5 Venues & Accounts
- **Venues (all, independently certified):** Bybit (V5), Binance, OKX (API v5), MT5, MT4, cTrader Open API, IBKR (TWS/Web API), OANDA v20, Alpaca, plus additional brokers via adapter contract.
- **Certification:** Each venue must pass SANDBOX-VERIFIED before LIVE-PILOT-VERIFIED. Capability matrix per account (Section 11).
- **Nigeria eligibility:** To be verified per venue against official docs (see Feasibility Report). IBKR and OANDA currently do not serve Nigeria; Binance is restricted (NGN/P2P suspended); Bybit/OKX serve Nigeria with limitations.

### 1.6 Research, Data & Learning
- **ZERO-COST CONSTRAINT (D-019, 2026-11-25):** Free tools, free APIs, free data **only**. Target spend for the entire system: **$0/month**. No paid data licence, no paid API tier, no paid SaaS subscription, no paid infrastructure, no paid software licence. Any component without a $0 option is recorded as BLOCKED and escalated to the owner as a separate decision — NEXUS never silently adopts a paid service.
- **Data sources:** Free/official only — exchange public WebSocket/REST (Bybit, OKX, Binance), broker feeds (MT5/MT4/cTrader, free with account), free public history archives (data.binance.vision, Dukascopy), FRED, SEC EDGAR, EIA, CFTC, central-bank and regulator feeds, exchange announcement feeds, free-tier news APIs (rate-limited, secondary corroboration only).
- **If free coverage is insufficient:** NEXUS **narrows scope** (fewer instruments/venues, longer horizons, stays in Observe/Research) — it does **not** purchase data. Paid vendors are rejected, not a roadmap.
- **Depth without paying:** we record the free real-time streams into our own time-series archive from day one, building first-party history with full provenance.
- **Research:** Persistent, source-aware, time-aware, proportional to uncertainty. Evidence graph, freshness rules, audit trail. Research completion ≠ trade signal (Section 5.5).
- **Learning:** Independent research + learning from private history permitted. **No self-promotion to production** — every change passes experiment → backtest → out-of-sample → shadow → owner approval → rollback readiness (Section 6.3).

### 1.7 Hosting, Devices & Alerts (all at $0)
- **Hosting:** Cloud-native core (Docker Compose) on **free always-on VMs only**: Oracle Cloud Always Free (Ampere A1 ARM, 2 OCPU / 12 GB RAM, 200 GB block, 10 TB egress) as primary host; Google Cloud free-tier e2-micro as an independent off-box watchdog/alert relay/backup target. **No paid VPS, no managed database, no paid SaaS.** Mobile is a secure control surface, not a compute host.
- **MT4/MT5 bridges:** run on the same free VM via **Wine** (MetaQuotes' documented Linux path) — no paid "forex VPS". cTrader Open API is the native-protocol alternative.
- **All infrastructure software is self-hosted open source:** PostgreSQL + TimescaleDB, NATS JetStream, Valkey, MinIO, DuckDB/Parquet, OpenBao (or SOPS+age) for secrets, Keycloak for identity/MFA, Caddy + Let's Encrypt for TLS, Tailscale/Cloudflare Tunnel for private access, Prometheus + Grafana OSS + Loki + Uptime Kuma for observability, GitHub free private repos + Actions for CI/CD, Trivy/Semgrep/gitleaks/Dependabot for scanning.
- **Intelligence at $0:** local quantized open-weight models via Ollama (primary for anything sensitive) plus free API tiers (Gemini free, Groq free, OpenRouter `:free`, NVIDIA NIM) for non-sensitive research only. **No paid LLM API.** No trade decision may depend on a rate-limited free model being reachable — if unavailable, the decision state is ABSTAIN (fail closed). Sensitive data (credentials, balances, positions, orders) is never sent to a free hosted model.
- **Disclosed free-tier trade-offs:** single VM (no HA), Oracle idle-reclaim risk and allowance-change risk, 200 GB storage cap, no GPU, US/EU latency (not colocated → scalping out of scope unless Shadow evidence supports it), MT-over-Wine fragility. Mitigations: fail-closed design, protective orders held at the venue, encrypted off-box backups, IaC rebuild <1 hr, tiered data retention, per-service memory caps, pinned Wine.
- **Devices:** Desktop + iOS + Android (responsive web / PWA). Mobile supports auth (biometrics + MFA), live status, approvals, emergency halt, incident alerts, research summaries. Live approval never depends on a tiny ambiguous tap.
- **Alerts (free channels):** in-app (WebSocket), **Telegram Bot API (primary critical channel)**, Web Push (self-hosted VAPID, works on iOS/Android PWA + desktop), email (Brevo free 300/day with daily budget + consolidation), dead-man switch (healthchecks.io free + GCP watchdog) — all with delivery status, retries, escalation, severity-aware (Critical/High/Medium/Informational, Section 24).
- ⚠️ **SMS and WhatsApp cannot be delivered at $0.** No reliable free SMS gateway exists for Nigerian numbers, and WhatsApp Business Cloud API charges per business-initiated conversation (unofficial WhatsApp automation also risks account bans). Both are **BLOCKED by D-019** pending an explicit separate owner decision (Q-05 in the Feasibility Report).

### 1.8 Stack & Delivery
- **Reference stack (Section 22):** Python (research/quant/orchestration), TypeScript (web/API/realtime UI), MQL4/MQL5 bridges, PostgreSQL/TimescaleDB, NATS JetStream or Kafka/Redpanda, Docker, React/Next.js, OpenTelemetry/Prometheus/Grafana, MLflow.
- **Licence rule (D-019):** every component must be free/open-source (Apache-2, MIT, BSD, MPL, PostgreSQL, ISC, AGPL used self-hosted only) or a genuinely free tier. No paid licence, no paid plan, no paid add-on. UI charting uses TradingView **Lightweight Charts** (Apache-2); fonts Inter + JetBrains Mono (SIL OFL); icons Lucide (ISC).
- **Ownership:** Owner owns source code, build instructions, migrations, test reports, known issues, handover docs (Section 32). Owner also owns the free cloud tenancies (Oracle, GCP, GitHub) and all API keys.

## 2. Unresolved / Provisional

| ID | Item | Status | Default stance |
|----|------|--------|----------------|
| O-001 | Per-account currency | OPEN | No live capital assumptions |
| O-002 | Exact risk numbers | PROVISIONAL (conservative) | Conservative profile until Risk Policy finalized |
| O-003 | Per-venue Nigeria eligibility | OPEN | Framework first; certify per account |
| O-004 | Nigerian legal review outcome | OPEN | Live disabled until reviewed |
| O-005 | Free-data sufficiency for intraday | PROVISIONAL | Free only (D-019). If insufficient → narrow scope (fewer instruments/venues, longer horizons, stay in Observe/Research). **Never purchase data** without a separate written owner decision |
| O-006 | SMS + WhatsApp alerting | **BLOCKED by D-019** | Not available at $0. Free set in use: in-app + Telegram + Web Push + email. Owner decision required (Q-05) |
| O-007 | Single free VM as primary host (Oracle Always Free) | OPEN (Q-07) | Accept for Observe→Shadow/Paper with watchdog + encrypted backups + IaC rebuild; re-review before any live phase |
| O-008 | 200 GB storage cap vs tick-history depth | OPEN (Q-08) | Tiered retention (raw ticks → 1s → 1m rollups, purge policy) + honest coverage labels, or narrower instrument universe |

*Per Section 0.4: a deferred decision concerning live authority, capital, leverage, API permissions, risk limits, custody, jurisdiction, or security must remain disabled until resolved. No dangerous defaults.*

## 3. Excluded Features (Non-Goals, Section 34)

- Dashboard-only product with fake backend activity
- Chatbot inventing trades/market facts
- Universal strategy trading every market with identical rules
- LLM directly submitting orders without deterministic risk authorization
- Live trading enabled by default after connecting an account
- Hard-coded 99.9% accuracy claims or guaranteed profit statements
- Backtests omitting costs, look-ahead checks, or realistic fills
- Unlicensed redistribution or scraping of restricted data
- Integration marked complete after only auth or price retrieval
- Automatic strategy self-modification in production
- Unbounded leverage, unlimited position size, hidden permissions
- Silent recovery from order uncertainty by resubmitting orders
- Undocumented plugins, hidden external calls, untracked model-provider changes

## 4. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Autonomous live with $100k+ capital | Real-money loss | Conservative limits, staged rollout, kill switch, reconciliation gates |
| Multi-venue complexity (9+ venues) | Long timeline, integration bugs | Shared adapter contract, independent certification, sandbox-first |
| Free-data limitations (latency, history, rate limits, no SLA) | Poor intraday decisions | Data-quality gates fail closed, staleness blocks new risk, per-venue rate-limit budgets, multiple free sources cross-checked, first-party tick archive built from day one, honest coverage labels |
| Zero-cost constraint (D-019) blocks paid data/infra/SMS | Capability ceiling; single-VM availability risk | Narrow scope rather than spend; free-tier watchdog on a second cloud; encrypted off-box backups; IaC rebuild <1 hr; venue-held protective orders; blocked items escalated as owner decisions, never silently paid for |
| Free-tier terms can change without notice (Oracle halved its ARM allowance 15 Jun 2026) | Capacity loss mid-build | Per-service memory caps, graceful degradation order (research depth drops before risk/execution monitoring), terms re-verified at every phase gate |
| Free LLM tiers: rate limits (50–1,000 req/day), may vanish, may train on prompts | Research throttling; privacy exposure | Local-first for sensitive data, outbound redaction gate with tests, request budgeting + caching, ABSTAIN when unavailable, model changes logged in audit trail |
| MT4/MT5 via Wine on ARM Linux | Bridge fragility | Pinned Wine version, MT5 preferred (MetaQuotes' documented path), demo-only until 30 days stable, health checks, isolated container, cTrader Open API alternative |
| Nigerian eligibility restrictions | Some venues unavailable | Per-venue capability matrix; no VPN circumvention |
| Legal/regulatory change (Nigeria SEC/CBN) | Live authority revoked | Jurisdiction review, supported-country matrix, audit exports |
| Intraday latency & execution quality | Slippage, adverse selection | Execution analytics, venue comparison, latency monitoring |

## 5. Acceptance Criteria (Summary)

Every capability must pass (Section 28):
- Product/UX: approved designs, all states, responsive, accessible
- Market data: provenance, timestamps, gap detection, replay tests
- Research: cited evidence, contradiction handling, freshness, abstention tests
- Memory: persistence, retrieval relevance, provenance, correction/expiry
- Strategy lab: versioned experiments, no leakage, realistic costs, walk-forward, stress
- Risk: independent numerical tests, limit enforcement, fail-closed, adversarial bypass tests
- Broker integration: official capability matrix, account verification, order lifecycle, reconciliation
- Execution: idempotency, partial fills, reject handling, unknown-state recovery, kill switch, audit
- Security: threat model, secret handling, permission tests, vulnerability report, incident drill
- Operations: monitoring, alerts, backup restore, DR, runbooks, SLO report
- Legal/data: jurisdiction + data-rights review, provider terms, supported-product matrix
- Delivery: source, build instructions, env template, migrations, test report, known issues, handover

**Defect severity:** Blocker/Critical = release prohibited. Major = fix or waive. Minor/Cosmetic = may accept with owner visibility (Section 28.1).

## 6. Performance Standard (Section 21)

The "99.9% standard" is a **quality ambition**, not a prediction guarantee. Every 99.9% claim must state denominator, window, exclusions, source, and confidence interval. Operational reliability ≠ profitable trades. No guaranteed returns. Forecast quality measured by calibration, Brier/log loss, directional/magnitude error on rolling out-of-sample evaluation.

## 7. Status & Next Step

- ✅ **Appendix B Feasibility Report** — written, **approved by owner 2026-11-25 (D-018)**, then **revised to v1.1** the same day to enforce the zero-cost constraint (D-019): `docs/02-feasibility-report.md`. Paid options moved to *Rejected*.
- ✅ **Phase 1 Product/UX Bible** — DESIGNED, awaiting owner approval: `docs/03-product-ux-bible.md`.
- **Monthly cost of the whole system: $0** (Feasibility Report §10.7).
- **Next:** owner decisions on Q-05 (SMS/WhatsApp not free), Q-07 (single free VM), Q-08 (storage cap), then Phase 2 (Core foundation: identity, DB, audit, secrets, events, observability, CI/CD).
- **No production code written. No live accounts connected. No paid service adopted. Live trading disabled.**

---

*Baseline approved by owner: 2026-11-25 (D-017). Zero-cost constraint added: 2026-11-25 (D-019). Feasibility approved: 2026-11-25 (D-018). Next review: after Phase 1 approval.*
