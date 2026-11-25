# NEXUS First Development Report — Appendix B Feasibility Report

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026  
**Baseline:** Approved 2026-11-25 (D-017)  
**Feasibility approval:** Approved 2026-11-25 (D-018)  
**Revision:** v1.1 — 2026-11-25, rewritten for the zero-cost constraint (D-019)  
**Status:** CONFIRMED (approved), **revised** — Sections 4, 10, 11, 13 now zero-cost only  
**Owner profile:** Personal, Nigeria, multi-asset, intraday, autonomous live (within hard limits), conservative risk, $100k+ capital, cloud hosting, **FREE tools / FREE APIs / FREE data only — $0/month (D-019)**

> Per Section 0.4 and Appendix B, this report must be approved before production code.  
> Per Section 0.6: no guaranteed returns, no 99.9% prediction claims.  
> Per Appendix C: every status below states what was tested, where, result, date, environment, and limitations.

---

## Table of Contents

1. Architecture & Service Boundaries
2. Official API Capability Matrix (Bybit, Binance, OKX, MT4, MT5, cTrader, IBKR, OANDA, Alpaca)
3. Nigeria Region / Account Eligibility & Permissions
4. Data Source Comparison, Licensing, Latency, History & Cost
5. Canonical Asset / Instrument Schema & Contract-Mapping Examples
6. Threat Model & Live-Money Permission Model
7. Backtesting & Event-Replay Design (with Limitations)
8. Risk Engine Mathematical Specification & Test Vectors
9. UI Wireframes & Design System
10. Cost, Hosting Estimates & Milestone Schedule
11. Open Questions, Assumptions, Rejected Options & Owner Decisions Required
12. Staged Delivery Plan & Test Strategy
13. External Dependencies Requiring Owner Accounts/Permissions

---

## 1. Architecture & Service Boundaries

### 1.1 Reference Architecture (Section 22)

```
┌─────────────────────────────────────────────────────────────────┐
│  CONTROL SURFACES (responsive web: desktop + iOS + Android)     │
│  Command Centre | Markets | Workbench | Intelligence | Research │
│  Strategy Lab | Portfolio/Risk | Execution | Connections | Audit │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST (control) + WebSocket/SSE (live)
┌──────────────────────────▼──────────────────────────────────────┐
│  API & REALTIME GATEWAY (TypeScript)                            │
│  Auth (OIDC + MFA) | RBAC | Rate limits | Audit logging         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│  INTELLIGENCE CORE (Python) — persistent, inspectable           │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐         │
│  │ Observatory │ │  Research    │ │ Cognitive Core   │         │
│  │ (ingest +   │ │  Engine      │ │ (memory, beliefs,│         │
│  │  regime)    │ │  (evidence   │ │  scenarios)      │         │
│  │             │ │   graph)     │ │                  │         │
│  └──────┬──────┘ └──────┬───────┘ └────────┬─────────┘         │
│         │               │                    │                   │
│  ┌──────▼───────────────▼──────────────────▼─────────┐         │
│  │  Quant Lab + Strategy Factory (versioned, gated)  │         │
│  └──────────────────────┬────────────────────────────┘         │
│                         │ eligibility protocol (Sec 9)          │
└─────────────────────────┼───────────────────────────────────────┘
                          │ signed order intents ONLY
┌─────────────────────────▼───────────────────────────────────────┐
│  GOVERNANCE (deterministic, separately deployed)                │
│  ┌──────────────┐ ┌───────────────┐ ┌──────────────────┐       │
│  │ Risk Engine  │ │ Portfolio     │ │ Execution Gateway│       │
│  │ (hard limits)│ │ (exposure,    │ │ (idempotency,    │       │
│  │              │ │  sizing)      │ │  routing, recon) │       │
│  └──────┬───────┘ └───────┬───────┘ └────────┬─────────┘       │
└─────────┼─────────────────┼──────────────────┼───────────────────┘
          │                 │                  │
┌─────────▼─────────────────▼──────────────────▼───────────────────┐
│  BROKER/EXCHANGE ADAPTERS (shared contract, venue semantics kept) │
│  Bybit V5 | Binance | OKX v5 | MT5 bridge | MT4 bridge |         │
│  cTrader Open API | IBKR TWS/Web | OANDA v20 | Alpaca | CCXT*    │
└─────────────────────────┬────────────────────────────────────────┘
                          │ REST / WebSocket / FIX / terminal bridge
                          ▼
                   Exchanges / Brokers

┌─────────────────────────────────────────────────────────────────┐
│  PLATFORM SERVICES                                              │
│  PostgreSQL (system of record) | TimescaleDB (time-series)      │
│  Redis (cache/locks) | NATS JetStream (events)                  │
│  S3-compatible (raw files, artifacts) | MLflow (experiments)    │
│  OpenTelemetry + Prometheus + Grafana (observability)           │
│  Secrets Manager / KMS (credentials) | Temporal (workflows)     │
└─────────────────────────────────────────────────────────────────┘
```

*CCXT is a prototype aid only; venue-specific features require native adapter coverage (Section 16).

### 1.2 Service Boundaries (Section 22.1)

| Service | Responsibility | Trust boundary |
|---------|----------------|----------------|
| Identity & Access | OIDC, MFA, RBAC, step-up auth for live authority | **Trusted** — owns auth |
| Account & Connection Registry | Workspaces, connections, scopes, mandates | **Trusted** — owns secrets refs |
| Instrument Master | Canonical IDs, venue aliases, contract specs, calendars | **Trusted** — versioned metadata |
| Market Data Ingestion | Normalize quotes/trades/books/derivatives; quality checks | **Untrusted input** — validate all feeds |
| Research Orchestration | Source registry, evidence graph, case files, freshness | **Untrusted content** — prompt-injection defenses |
| Cognitive Orchestration | Memory, beliefs, scenarios, tool allowlists | **Untrusted reasoning** — cannot authorize orders |
| Quant Analytics | Stats, volatility, forecasts, portfolio math | **Untrusted models** — deterministic checks required |
| Strategy Registry | Lifecycle IDEA→RETIRED, dossiers, promotion gates | **Untrusted proposals** — gated promotion |
| Portfolio & Risk | Exposure, sizing, hard limits, authorization tokens | **Trusted (deterministic)** — final authority |
| Execution Gateway | Signed intents only, idempotency, routing, reconciliation | **Trusted (deterministic)** — broker is truth |
| Adapters | Venue translation, raw+normalized responses | **Semi-trusted** — venue semantics preserved |
| Ledger & Reconciliation | Internal mirror vs broker truth; mismatch = incident | **Trusted** — blocks risk on mismatch |
| Notification & Incident | Severity-aware alerts, delivery status, escalation | **Trusted** — critical path |
| Audit & Compliance | Tamper-evident log of research/decisions/orders/changes | **Trusted** — append-only |
| Web/Mobile API | Typed REST + WebSocket/SSE gateway | **Trusted** — enforces RBAC |

### 1.3 Trust Boundaries & Design Principles

1. **Intelligence proposes; governance disposes.** Language models never authorize orders. Only the deterministic Risk Engine issues authorization tokens.
2. **Broker is authoritative for execution truth.** Internal ledger is a mirror; mismatch blocks risk-increasing orders (Section 12.1).
3. **Fail closed.** Lost data, model timeout, disconnect, stale price, clock drift, DB/risk-service failure, duplicate events, unknown order state → no new risk (Section 13.2).
4. **Least privilege.** Research agents cannot submit orders. Execution services cannot browse arbitrary sites or change strategies. Risk controls cannot be modified by model instructions.
5. **No withdrawal authority.** Trading keys are trade-only, withdrawal-disabled where supported (Section 13.3).
6. **Signed intents.** Execution Gateway accepts only signed, risk-authorized intents with idempotency keys. UNKNOWN order state never blindly resubmits.

---

## 2. Official API Capability Matrix

> Verified against official documentation (Appendix A) on 2026-11-25.  
> Status: **PROPOSED** (designed, not implemented). Each venue must reach SANDBOX-VERIFIED before LIVE-PILOT-VERIFIED.

### 2.1 Bybit — V5 REST + WebSocket

- **Docs:** https://bybit-exchange.github.io/docs/v5/intro — V5 unifies Spot, Derivatives, Options in one spec. Unified trading account shares funds across Spot, USDT Perpetual, USDC Perpetual, Options. Portfolio margin supported.
- **Coverage:** Spot ✓, Linear (USDT Perpetual/Futures) ✓, Inverse (Perpetual/Futures) ✓, Options ✓ (Unified account).
- **Auth:** API key + secret, HMAC signing. Separate testnet/demo where supported.
- **Market data:** REST (`/v5/market/*`) + WebSocket public/private streams. Candles, orderbook, ticker, recent trades, instrument rules, risk rules.
- **Trading:** `POST /v5/order/create` with `category=spot/linear/inverse/option`. Order, position, account, asset modules.
- **Streams:** Public (market) + private (orders, positions, executions, wallet). Reconnect + snapshot recovery required.
- **Limits:** Rate limits per endpoint; instrument precision, min notional, leverage bands per symbol.
- **Certification proof required:** Spot/derivatives/options entitlement as applicable; balances, positions, order lifecycle, private streams, precision, rate limits, reconciliation.

### 2.2 Binance — Spot / Margin / Futures (separate adapters)

- **Docs:** https://developers.binance.com/en/docs/introduction — central portal for Spot, Futures, Wallet, etc. REST, WebSocket APIs, WebSocket Streams, FIX, SBE.
- **Coverage:** Spot, Margin, Futures (USD-M, COIN-M), Options (where eligible). Separate adapters per product family (Section 11).
- **Auth:** HMAC, RSA, Ed25519 depending on interface. Testnet/demo where supported.
- **Market data:** REST + WebSocket Streams (ticker, depth, trades, candles). User-data streams for private events.
- **Trading:** Product-specific order endpoints; symbol filters (price, lot size, notional), order types, time-in-force.
- **Limits:** Request weights + endpoint limits; throttling on exceed. Retry/backoff + health monitoring required.
- **Certification proof required:** Account permissions, symbol filters, order types, user streams, product eligibility, regional availability.

### 2.3 OKX — API v5 REST + WebSocket

- **Docs:** https://www.okx.com/docs-v5/en/ — API v5, account modes, production/demo separation. Python libraries available.
- **Coverage:** Spot, Margin, Derivatives (perpetual, futures), Options, Earn (where eligible).
- **Auth:** API key + secret + passphrase, signature. Demo trading services separate from production.
- **Market data:** REST (instruments, tickers, candles, orderbook) + WebSocket (public/private). Account mode (cash, cross, isolated, portfolio margin) affects endpoints.
- **Trading:** Place/amend/cancel, leverage set, margin increase/decrease, position mode, Greeks, fee rates.
- **Limits:** Trading-related rate limits, sub-account limits, fill-ratio-based limits. Transaction timeouts documented.
- **Certification proof required:** Account mode, product permissions, live/demo separation, order/position lifecycle, instrument rules.

### 2.4 MetaTrader 5 — Terminal Bridge (Python package)

- **Docs:** https://www.mql5.com/en/docs/python_metatrader5 — `pip install MetaTrader5`. IPC directly from MT5 terminal.
- **Coverage:** Account info, terminal info, symbols (total/get/info/tick/select), market book, copy rates/ticks, orders (total/get/check/send/calc margin/profit), positions, history orders/deals.
- **Auth:** Terminal login (account, password, server) + terminal running. Bridge must authenticate to central service with signed messages, heartbeat, terminal/account identity, fail closed on disconnect.
- **Market data:** Symbol info/tick, copy rates (OHLCV), copy ticks, market book (depth where broker provides).
- **Trading:** `order_check`, `order_send`, `order_calc_margin`, `order_calc_profit`. Symbol specification (digits, tick value/size, volume min/max/step, trade mode, margin currency).
- **Limits:** Broker-specific symbol mapping, lot/stop constraints, trade context, terminal restart, server reconciliation.
- **Certification proof required:** Terminal/account identity, symbol spec, market data, order result, deals, positions, reconnect, terminal restart.

### 2.5 MetaTrader 4 — MQL4 Expert Advisor + Bridge

- **Docs:** https://www.metatrader4.com/en/trading-platform/help/autotrading/mql4 — terminal-side automation via MQL4 Expert Advisors.
- **Coverage:** EA runs in terminal; authenticated local/remote bridge to central service. Separate adapter from MT5 (Section 11.5).
- **Auth:** EA + bridge signed messages; terminal login credentials stay in terminal/VPS, never in browser.
- **Market data:** Broker feed via terminal (quotes, candles). Symbol mapping broker-specific.
- **Trading:** Order ticket lifecycle (open/modify/close), trade context, lot/stop constraints.
- **Limits:** Broker symbol mapping, lot/stop constraints, terminal restart, server reconciliation.
- **Certification proof required:** Broker symbol mapping, lot/stop constraints, trade context, order ticket lifecycle, terminal restart, server reconciliation.

### 2.6 cTrader — Open API (JSON / Protobuf)

- **Docs:** https://help.ctrader.com/open-api/ — anyone with cTrader ID (cTID) can build apps. JSON or Protobuf; official SDKs: C# (OpenAPI.Net), Python (OpenApiPy).
- **Coverage:** Real-time market data, all trading operations permitted in cTrader apps, past/current/pending operations (deals, orders, positions).
- **Auth:** cTrader ID + broker account access; live and demo scopes. Demo recommended for development.
- **Market data:** Real-time quotes, historical data (rate-limited).
- **Trading:** Orders, positions, deals via Open API messages (`ProtoOA*`).
- **Limits:** 50 req/s per connection (non-historical), 5 req/s (historical).
- **Certification proof required:** cTID + broker account access, live scopes, symbols, orders, positions, deals, rate limits.

### 2.7 Interactive Brokers — TWS API / Web API / FIX

- **Docs:** https://www.interactivebrokers.com/docs/ — Web API, TWS API, FIX entry point.
- **Coverage:** Stocks, options, futures, forex, bonds, funds (where eligible). Gateway/session state, market-data subscriptions, contract qualification, order ack, execution reports.
- **Auth:** Gateway session (TWS/IB Gateway) or Web API OAuth. Market-data subscriptions per account.
- **Market data:** Subscriptions, snapshots, streaming. Contract qualification required before trading.
- **Trading:** Order ack, execution reports, account permissions.
- **Limits:** Gateway/session, subscription limits, order rate limits.
- **Certification proof required:** Gateway/session state, subscriptions, contract qualification, order ack, execution reports, permissions.
- **⚠️ Nigeria:** IBKR does not offer services to Nigerian residents (see Section 3). Adapter built but **cannot go live for Nigeria** until eligibility changes.

### 2.8 OANDA — v20 REST + Streaming

- **Docs:** https://developer.oanda.com/rest-live-v20/introduction/ — v20 trading engine. Available to all divisions except OANDA Global Markets and OANDA TMS Brokers S.A.
- **Coverage:** FX spot, CFDs (where eligible), market data (real-time rates 24h, historical back to 2005), trading (place/modify/close orders, account settings, history).
- **Auth:** Personal access token (Bearer) via Account Management Portal. Demo + live accounts.
- **Market data:** Pricing stream + historical pricing endpoints.
- **Trading:** Account, Order, Trade, Position, Transaction endpoints. Instrument precision per pair.
- **Limits:** Division eligibility, token scope, pricing stream, account state, order/transaction lifecycle.
- **Certification proof required:** Division eligibility, token scope, pricing stream, account state, order/transaction lifecycle, precision.
- **⚠️ Nigeria:** OANDA not available to Nigerian clients (see Section 3). Adapter built but **cannot go live for Nigeria**.

### 2.9 Alpaca — Trading API

- **Docs:** https://docs.alpaca.markets/us/v1.1/docs/trading-api — Paper trading free for all; live brokerage for eligible individuals/businesses + crypto.
- **Coverage:** US equities, ETFs, options (where eligible), crypto (24/7). Fractional shares ($1 min, market orders only for fractional).
- **Auth:** API keys (paper/live separate). Paper is real-time simulation with free real-time data.
- **Market data:** Real-time (paper) + live entitlements per account.
- **Trading:** Market, limit, stop, plus complex orders. User protections enabled.
- **Limits:** Live-account eligibility, market-data entitlement, order states, asset availability, account restrictions.
- **Certification proof required:** Live eligibility, data entitlement, order states, asset availability, restrictions.
- **⚠️ Nigeria:** Live brokerage is US-focused; paper globally available. Live for Nigeria **UNVERIFIED** — requires eligibility check.

### 2.10 Capability Matrix (Summary)

| Venue | Spot | Perps/Futures | Options | FX/CFD | Stocks/ETFs | Market Data | Private Streams | Sandbox/Demo | Nigeria Live |
|-------|------|---------------|---------|--------|-------------|-------------|-----------------|--------------|--------------|
| Bybit V5 | ✓ | ✓ (Linear/Inverse) | ✓ | — | — | REST+WS | ✓ | ✓ (testnet) | Partial* |
| Binance | ✓ | ✓ (separate) | ✓* | — | — | REST+WS+FIX | ✓ (user-data) | ✓ (testnet) | Restricted* |
| OKX v5 | ✓ | ✓ | ✓ | — | — | REST+WS | ✓ | ✓ (demo) | Available* |
| MT5 | — | — | — | ✓ | ✓* | Terminal feed | Terminal | ✓ (demo) | Via broker |
| MT4 | — | — | — | ✓ | ✓* | Terminal feed | Terminal | ✓ (demo) | Via broker |
| cTrader | — | — | — | ✓ | ✓* | REST+WS | ✓ | ✓ (demo) | Via broker |
| IBKR | — | ✓ | ✓ | ✓ | ✓ | Subscriptions | ✓ | ✓ (paper) | **No** |
| OANDA v20 | — | — | — | ✓ | — | REST+stream | ✓ | ✓ (demo) | **No** |
| Alpaca | — | — | ✓* | — | ✓ | REST+WS | ✓ | ✓ (paper) | Unverified |

*See Section 3 for Nigeria details. ✓* = product/region dependent. All require account-specific verification.

---

## 3. Nigeria Region / Account Eligibility & Permissions

> **Rule (Section 16.2):** Never assume universal access. Discover and display actual capability. No VPN circumvention of restrictions.

### 3.1 Bybit — Partial Access (Nigeria)

- **Status:** Nigeria is **not** on Bybit's fully restricted list (14 jurisdictions: US, Canada, China, Singapore, Dubai, UK, etc.). Nigeria is in the **partial access** tier: crypto trading permitted, fiat services limited to NGN only [2](https://www.bitdegree.org/crypto/tutorials/bybit-restricted-countries).
- **P2P:** Active for Nigerians (USDT/NGN via P2P) [1](https://earnifyhub.com/blog/crypto/crypto-nigeria-exchanges-p2p-2026).
- **KYC:** Required; sign-up screen is final test. Local regulatory friction noted [4](https://kkinvesting.io/en/posts/bybit-exchange-guide/).
- **NEXUS implication:** Bybit adapter can proceed to sandbox. Live requires KYC, NGN-only fiat understanding, and Nigerian legal review. **Verdict: ADOPT (with limitations).**

### 3.2 OKX — Available (Nigeria removed from restricted list)

- **Status:** OKX removed Nigeria from its restricted list on **8 July 2026** (Risk and Compliance Disclosure, last updated 8 July 2026) [5](https://www.coinperps.com/learn/okx-restricted-countries).
- **P2P:** Available (USDT/NGN) [1](https://earnifyhub.com/blog/crypto/crypto-nigeria-exchanges-p2p-2026).
- **NEXUS implication:** OKX adapter can proceed to sandbox/demo. Live requires account-mode verification and legal review. **Verdict: ADOPT.**

### 3.3 Binance — Restricted (Nigeria)

- **Status:** Binance suspended all NGN services (deposits, withdrawals, Naira P2P) in **February 2024**; Nigerian ISPs block Binance domains; Nigerian SEC declared Binance unregistered [1](https://breet.io/blog/does-binance-work-in-nigeria) [3](https://alertlend.com/crypto-exchanges-banned-in-nigeria-2026-regulatory-guide).
- **What works:** Crypto-to-crypto trading and on-chain withdrawals via app; no Naira, no P2P, no airdrops, no cards [1](https://breet.io/blog/does-binance-work-in-nigeria).
- **Legal risk:** Using VPN to bypass domain blocks risks account suspension and regulatory gray area [1](https://earnifyhub.com/blog/crypto/crypto-nigeria-exchanges-p2p-2026). SEC discourages unlicensed platforms.
- **NEXUS implication:** Binance adapter built for framework completeness, but **live trading for Nigeria is BLOCKED** pending legal review and eligibility change. Sandbox/testnet only. **Verdict: TEST (sandbox only); live DEFERRED.**

### 3.4 Interactive Brokers — Not Available (Nigeria)

- **Status:** "IBKR does not offer its services to residents of Nigeria" (official IBKR response) [4](https://x.com/IBKR/status/1937631690534293796?lang=en). Multiple 2026 reviews confirm Nigeria restricted due to compliance/FATF [2](https://tradersunion.com/brokers/forex/view/interactive_brokers/is-regulated-in-nigeria/) [5](https://www.tic.co.tz/interactive-brokers/).
- **NEXUS implication:** IBKR adapter **DEFERRED** for Nigeria. Build only if owner relocates or eligibility changes. **Verdict: REJECT for Nigeria live; framework retained.**

### 3.5 OANDA — Not Available (Nigeria)

- **Status:** "OANDA is not available to clients in Nigeria" (June 2026 analysis) [1](https://tradersunion.com/brokers/forex/view/oanda/is-regulated-in-nigeria/).
- **NEXUS implication:** OANDA adapter **DEFERRED** for Nigeria. **Verdict: REJECT for Nigeria live; framework retained.**

### 3.6 Alpaca — Unverified (Nigeria)

- **Status:** Paper trading free globally; live brokerage for eligible individuals/businesses (US-focused) [Alpaca docs]. No explicit Nigeria live confirmation found.
- **NEXUS implication:** Alpaca paper adapter can proceed. Live **UNVERIFIED** — requires eligibility check with Alpaca. **Verdict: TEST (paper only); live DEFERRED.**

### 3.7 MT4 / MT5 / cTrader — Via Brokers Serving Nigeria

- **Status:** Terminal/Open API availability depends on **broker** (not MetaTrader/Spotware). Brokers serving Nigeria (e.g., Exness, Deriv — noted as Nigeria-accepting in IBKR reviews) offer MT4/MT5/cTrader with local deposit methods.
- **NEXUS implication:** MT5/MT4/cTrader adapters proceed to sandbox with a Nigeria-serving broker demo account. Live requires broker-specific eligibility, symbol mapping, and legal review. **Verdict: ADOPT (broker-dependent).**

### 3.8 Nigerian Regulatory Context (2026)

- Nigeria moved from banning crypto to banning *unlicensed* exchanges only; licensed domestic venues (Quidax, Busha) lead for Naira trades [3](https://alertlend.com/crypto-exchanges-banned-in-nigeria-2026-regulatory-guide).
- 2026 requirements: TIN + NIN for crypto transactions; ISA 2025 compliance for licensed venues.
- **NEXUS implication:** Nigerian legal review (D-013) must cover ISA 2025, SEC Nigeria licensing, CBN directives, TIN/NIN, tax/reporting. Live stays disabled until reviewed.

---

## 4. Data Source Comparison, Licensing, Latency & History — ZERO-COST ONLY

> **Owner constraint D-019 (2026-11-25): FREE tools, FREE APIs, FREE data ONLY.**
> Every component of NEXUS must have a **$0 option**. No paid data licence, no paid API tier, no paid
> SaaS subscription, and no paid infrastructure is part of the plan. Any paid component is
> **OUT OF SCOPE** unless the owner separately and explicitly approves that specific spend in writing.
> Paid vendors are listed below only as *rejected* options, for the record — not as a roadmap.

### 4.1 Market Data (free sources only)

| Source | Coverage | Latency | History | Cost | Licence / Rights | Verdict |
|--------|----------|---------|---------|------|------------------|---------|
| Exchange public WebSocket + REST (Bybit V5, OKX v5, Binance) | Crypto spot/perps/options, order book, trades, funding, open interest | Real-time (WS push) | REST klines + locally archived ticks (we build our own history from the live stream) | **$0** | Display/storage per exchange ToS; no redistribution | **ADOPT** (primary for crypto) |
| Exchange **demo/testnet** APIs (Bybit demo, OKX demo trading, Binance testnet) | Same endpoints as live, simulated funds | Real-time | n/a | **$0** | Testnet ToS | **ADOPT** (shadow/paper) |
| Broker feeds via MT5 Python API / MT4 MQL4 / cTrader Open API | FX, metals, indices, stocks, futures (broker-dependent) | Real-time (terminal, tick/copy_rates/market book) | Broker server history (copy_rates, download depth varies) | **$0** (free with broker account, demo included) | Broker ToS; symbol mapping required | **ADOPT** (primary for FX/CFD/metals) |
| CCXT (open-source library) | Unified access to 100+ exchanges | Real-time (via exchange) | Limited | **$0** (OSS, MIT) | Exchange ToS still applies | **ADOPT** (adapter accelerator) |
| Dukascopy public historical feed (via free OSS downloaders) | FX/metals tick + candle history | n/a (historical) | Multi-year tick history | **$0** | Personal-use terms; verify per dataset | **ADOPT** (backtest history for FX) |
| Binance/Bybit public data archives (data.binance.vision, public dumps) | Crypto klines/trades/aggTrades | n/a (historical) | Multi-year | **$0** | Public archive terms | **ADOPT** (backtest history for crypto) |
| Polygon.io / Databento / dxFeed / LSEG / Bloomberg / Tiingo paid / Finnhub paid | Institutional depth, consolidated tape | Real-time | Deep | **Paid** | Redistribution restrictions | **REJECTED — out of scope (D-019 zero cost)** |

**Zero-cost data strategy (how we get depth without paying):** we *record* the free real-time streams
ourselves into our own time-series store from day one. The longer the system runs in Observe/Research,
the deeper our own first-party tick archive becomes — no licence fee, and the provenance is fully ours.
Backtests before that archive is deep use the free public history archives listed above, clearly labelled
by source, coverage window and any known gaps.

### 4.2 Macro & Public Data (Free, Primary-Source)

| Source | Coverage | Freshness | Cost | Licence | Verdict |
|--------|----------|-----------|------|---------|---------|
| FRED (St. Louis Fed) | US macro time series + release metadata | Daily/weekly; release calendar | Free (API key) | Public; cite source | **ADOPT** |
| SEC EDGAR | US issuer filings, company facts | Filing-based; fair-access required | Free | Fair access; no bulk abuse | **ADOPT** |
| EIA | Energy data, fundamentals | Daily/weekly/monthly | Free (API key) | Public | **ADOPT** |
| CFTC COT | Positioning (Commitments of Traders) | Weekly | Free | Public | **ADOPT** |
| Central-bank APIs (CBN, Fed, ECB, BoE, BoJ) | Rates, FX, policy | Per release calendar | Free | Public; respect revisions | **ADOPT** |
| National statistical agencies | GDP, CPI, jobs, etc. | Per release calendar | Free | Public | **ADOPT** |

### 4.3 News & Filings (free only)

| Source | Coverage | Cost | Licence | Verdict |
|--------|----------|------|---------|---------|
| Official exchange announcement feeds (Bybit/OKX/Binance announcements, listing/delisting, maintenance) | Listings, delistings, maintenance, funding changes | **$0** | Public; store source + timestamp | **ADOPT** (high value for intraday crypto events) |
| Regulator RSS/press feeds (SEC Nigeria, CBN, CFTC, SEC, FCA) | Policy, enforcement, licensing changes | **$0** | Public; cite source | **ADOPT** |
| SEC EDGAR full-text search + RSS (8-K, 10-Q, 13F) | US issuer filings, earnings, holdings | **$0** | Fair access; no bulk abuse | **ADOPT** |
| Issuer IR feeds / public earnings-call transcripts (company sites) | Earnings, guidance | **$0** | Cite source; respect robots/ToS | **ADOPT** |
| FRED release calendar + ALFRED vintages | Macro event timing, point-in-time revisions | **$0** | Public | **ADOPT** |
| Free-tier news APIs (GDELT, NewsAPI free dev tier, Finnhub free tier) | Headlines, sentiment proxies | **$0** (free tier only, rate-limited, non-commercial terms) | Store source + URL + timestamp; no redistribution | **ADOPT with caution** — dev-tier limits; treat as secondary corroboration, never sole basis for a live decision |
| Paid news/sentiment vendors, paid alternative data (on-chain premium, satellite, shipping) | Premium sentiment/alt-data | **Paid** | Redistribution limits | **REJECTED — out of scope (D-019 zero cost)** |
| Free public on-chain explorers/REST (blockchain.info, mempool.space public API, exchange proof-of-reserve pages) | Basic on-chain/flow context | **$0** (public rate limits) | Public terms; methodology must be documented | **ADOPT** (rate-limited, cached, labelled) |

### 4.4 Intraday Implications (D-008) under the zero-cost constraint

- Free exchange/broker WS feeds provide real-time ticks, candles and order-book depth sufficient for intraday **observation**, shadow and paper trading. This is genuinely adequate for the staged rollout.
- **Known free-tier gaps (accepted risks, disclosed not hidden):**
  - No consolidated cross-venue tape → we build our own per-venue records and never claim a single "market" price.
  - No vendor SLA, no support, no guaranteed uptime on free feeds → data-quality gates must fail **closed** (stale/crossed market blocks new risk).
  - Free API rate limits → local caching, backoff, and per-venue rate-limit budgets are mandatory (Section 11).
  - Historical depth before our own archive exists is patchy → backtests must declare coverage windows and gaps; results carry wider uncertainty bands.
- **Gate change (replaces the earlier paid-upgrade gate):** if free feeds prove insufficient in shadow, NEXUS **narrows scope** — fewer instruments, fewer venues, longer horizons, or stays in Observe/Research — rather than purchasing data. Any spend requires a separate, explicit, written owner approval as its own decision record.

---

## 5. Canonical Asset / Instrument Schema & Contract-Mapping Examples

### 5.1 Canonical Instrument Registry (Section 3.1)

Each instrument has a **stable internal ID** + venue-specific aliases. Metadata is **versioned** (venues change specs).

```json
{
  "instrument_id": "INS-BTCUSDT-PERP-BYBIT",
  "canonical_symbol": "BTC/USDT:USDT",
  "asset_class": "crypto",
  "instrument_type": "perpetual_swap",
  "underlying": "BTC",
  "venue": "bybit",
  "venue_symbol": "BTCUSDT",
  "currency": "USDT",
  "settlement_currency": "USDT",
  "contract_size": 1,
  "multiplier": 1,
  "tick_size": 0.1,
  "tick_value": 0.1,
  "lot_size": 0.001,
  "min_notional": 5,
  "price_precision": 1,
  "quantity_precision": 3,
  "margin_model": "cross|isolated|portfolio",
  "trading_hours": "24/7",
  "expiry": null,
  "exercise_style": null,
  "shortable": true,
  "fees": {"maker": 0.0002, "taker": 0.00055},
  "funding": {"interval_hours": 8, "cap": 0.0075},
  "data_entitlements": ["public_ws", "private_ws"],
  "status": {"supported": true, "connected": false, "data_available": false, "trade_enabled": false, "live_verified": false},
  "version": 3,
  "updated_at": "2026-11-25T00:00:00Z"
}
```

**Coverage truth (Section 3.2):** SUPPORTED ≠ CONNECTED ≠ DATA-AVAILABLE ≠ TRADE-ENABLED ≠ LIVE-VERIFIED. UI must distinguish all five. No instrument is advertised as tradable merely because a feed exposes its price.

### 5.2 Contract-Mapping Examples (Never assume equivalence)

| Canonical | Bybit | Binance | OKX | MT5 (broker) | Notes |
|-----------|-------|---------|-----|--------------|-------|
| BTC/USDT perp | BTCUSDT (linear) | BTCUSDT (USD-M) | BTC-USDT-SWAP | BTCUSD / BTCUSDT (broker symbol) | Different settlement, funding, mark price, precision |
| EUR/USD spot FX | — | — | — | EURUSD (broker) | Pip value, swap, session liquidity broker-specific |
| XAU/USD (gold) | — | — | — | XAUUSD (broker) | Contract size (100 oz vs 1 oz), tick value differ |
| US500 index CFD | — | — | — | US500 / SPX500 (broker) | Cash CFD vs futures basis; multiplier differs |
| AAPL equity | — | — | — | AAPL (broker) | Corporate actions, borrow, halts |

**Rule (Section 11.6):** The same instrument may have different symbols, multipliers, hours, spreads, swaps, margin, and execution rules across brokers. Compare executable economics per account; never assume BTCUSD at one broker equals BTCUSDT at an exchange.

---

## 6. Threat Model & Live-Money Permission Model

### 6.1 Threat Scenarios (Section 18.1)

| Threat | Preventive | Detective | Recovery |
|--------|------------|-----------|----------|
| Stolen API keys | Secrets Manager + KMS encryption; withdrawal-disabled keys; IP allowlist; least-privilege scopes | Access audit; anomaly alerts | Revoke/rotate keys; incident ID; block account |
| Compromised user session | OIDC + MFA; step-up auth for live authority; short sessions | Session anomaly detection | Force logout; revoke grants |
| Malicious research content / prompt injection | Treat all external content as untrusted data; never allow source text to issue tool commands; schema-validated tool calls | Injection tests; source credibility scoring | Quarantine source; abstain (Tier 4) |
| Supply-chain compromise | Dependency scanning, SAST/DAST, container scanning, secret scanning; lockfiles | Vulnerability reports; SBOM | Pin/rollback; rebuild |
| Replayed / duplicate orders | Idempotency keys, client order IDs, request journaling, signed intents | Duplicate-order rate metric | UNKNOWN state; reconcile before retry |
| Insider misuse | RBAC, least privilege, signed/timestamped high-impact actions, tamper-evident audit | Audit review; limit-breach alerts | Revoke; incident protocol |
| Compromised broker bridge | Signed messages, heartbeat, terminal identity, fail closed | Bridge health monitoring | Disconnect; reconcile; block entries |
| Database tampering | Encrypted backups, append-only audit, point-in-time recovery | Audit integrity checks | Restore; reconcile |
| Denial of service | Rate limits, backpressure, queue depth alerts | SLO monitoring | Degrade gracefully; fail closed |
| False market data | Freshness/consistency checks, source comparison, staleness gates | Data-quality metrics | Block new risk; incident |

### 6.2 Live-Money Permission Model (Sections 2.1, 13.3, 18.2)

- **Scopes:** Read-only / Demo / Live — clearly explained in connection flow. Live requires explicit real-money acknowledgement + separate authorization grant.
- **Mandate display:** UI shows which accounts/instruments the mandate covers.
- **Scoped authority:** Per account, platform, asset class, instrument group, strategy, order type, leverage band, notional limit, daily loss limit, open-risk limit, operating schedule.
- **No withdrawals:** Trading credentials must not have withdrawal/transfer permissions. Default design excludes withdrawals, internal transfers, payment initiation.
- **Key hygiene:** Separate credentials per platform/account, minimum scopes, IP allowlisting, withdrawal-disabled where supported. Never in browser local storage, repos, logs, analytics, or prompts.
- **Step-up auth:** MFA for owner access; step-up for live authority changes. Permission changes authenticated, logged, immediately reflected by Execution Gateway.

---

## 7. Backtesting & Event-Replay Design (with Limitations)

### 7.1 Design (Sections 7.2, 20.2, 20.3)

- **Point-in-time data:** No look-ahead. Use as-of timestamps; corporate-action adjustments; contract rolls; symbol changes.
- **Realistic costs:** Spread, commission, funding, borrow, financing, slippage, market-impact proxy, order delay, partial fills, halts.
- **Validation:** Walk-forward (rolling/anchored) + purged/embargoed splits where leakage possible (overlapping holding periods). Tune only on train/validation; holdout isolated. Track hypotheses tested (multiple-testing control).
- **Bias checks:** Survivorship, selection, look-ahead. Capacity + cost sensitivity. Final untouched holdout.
- **Reproducibility:** Code version, model version, dataset IDs, timestamps, transforms, params, seed, environment, run ID, artifacts. Unreproducible = ineligible for production (Section 7.1).
- **Event replay:** Durable event streams (NATS JetStream) with replay + idempotent consumers. Event envelope: ID, type, source, schema version, event time, ingestion time, correlation/causation IDs, payload. Separate market-data / account-order / model-research streams.
- **Simulation:** Historical replay, synthetic order book, partial fills, slippage, gaps, disconnects, rate limits (Section 20.1).

### 7.2 Known Limitations

- Free data has limited history depth and no consolidated tape → backtests may understate gaps/slippage.
- No order-book depth on free feeds → market-impact modelling is proxy-based.
- Survivorship bias risk if universe is current-only → require point-in-time universe.
- Intraday backtests without tick depth cannot prove execution quality → shadow/paper required before live.
- RL is research-only until simulator realism, reward design, safety constraints, and out-of-sample performance demonstrated.

---

## 8. Risk Engine Mathematical Specification & Test Vectors

### 8.1 Deterministic Calculations (Section 13.1)

All calculations validated against independent reference cases and broker-reported values. Rounding only per venue precision.

| Calculation | Formula | Inputs |
|-------------|---------|--------|
| Contract value | `quantity × contract_size × multiplier × price` | Qty, contract size, multiplier, price |
| Tick value | `tick_size × contract_size × multiplier` | Tick size, contract size, multiplier |
| Account-currency conversion | `value × FX_rate` | Value, FX rate (venue-local + ECB/FRED reference) |
| Stop risk | `|entry_price − stop_price| × quantity × contract_size × multiplier` | Entry, stop, qty, contract specs |
| Position size (risk-based) | `max_loss / stop_distance_per_unit` | Max loss ($), stop distance ($/unit) |
| Margin requirement | `notional / leverage` (venue model) | Notional, leverage, venue margin model |
| Liquidation buffer | `distance_to_liq / price` | Liq price, current price |
| Portfolio impact | `Δexposure / equity`, `Δrisk / portfolio_risk` | Exposure, equity, risk |

### 8.2 Conservative Profile (D-006, PROVISIONAL)

- Max risk per trade: **1% of account equity**
- Max leverage: **2x**
- Daily halt: **2% drawdown** → block new entries
- Additional gates: per-account/strategy/portfolio exposure, gross/net leverage, margin utilization, concentration, liquidity/spread/volatility, event-risk, overnight/weekend, max open positions/order frequency, instrument-specific (expiry/delivery), data-staleness, latency, broker health, reconciliation (Section 13).

### 8.3 Test Vectors (must pass before live)

| # | Scenario | Expected |
|---|----------|----------|
| T-01 | BTCUSDT perp, $100k equity, 1% risk ($1,000), entry $100,000, stop $99,000 (1% distance) | Size = $1,000 / $1,000 per unit = 1.0 BTC; notional $100k; margin at 2x = $50k; PASS if within limits |
| T-02 | EURUSD, $100k equity, 1% risk, 50-pip stop, pip value $10 per lot | Size = $1,000 / (50 × $10) = 2.0 lots; PASS if ≤ venue max |
| T-03 | Order would exceed 2x leverage | REJECT with reason code |
| T-04 | Daily drawdown hits 2% | Block new entries; allow reduce/close only |
| T-05 | Stale price (> threshold) | Block new risk-increasing orders |
| T-06 | UNKNOWN order state | Block resubmit; require reconciliation |
| T-07 | Risk service unavailable | No new live order bypasses risk service |
| T-08 | Duplicate idempotency key | Second submit rejected as duplicate |

---

## 9. UI Wireframes & Design System

### 9.1 Design System (Section 17.1)

| Element | Direction |
|---------|-----------|
| Canvas | Deep graphite/navy; subtle separators; high contrast |
| Typography | Professional sans-serif; tabular numerals for prices/P&L |
| Colour semantics | Green positive, red negative, amber warning, cyan system, purple research; colour never sole signal |
| Charts | Accurate axes, crosshair, timezone, session shading, volume, overlays, event markers, export |
| Cards | Only for meaningful grouped info; no decorative metric tiles |
| Tables | Dense but readable, sortable, filterable, column control, empty/error/loading states |
| Motion | Subtle state transitions only; no animated gradients or fake thinking effects |
| Mobile | Purpose-built compact hierarchy; critical actions reachable; no desktop shrink |
| Accessibility | Keyboard nav, screen-reader labels, contrast, scalable text, non-colour status cues |

### 9.2 Page Map (Section 17.2) — 15 Pages

Command Centre, Global Markets, Instrument Workbench, Intelligence Core, Research Dossiers, Memory & Knowledge, Strategy Laboratory, Portfolio & Risk, Execution Room, Connections, Scenario Studio, Performance & Attribution, Audit & Replay, Alerts & Operations, Settings & Governance.

### 9.3 Command Centre Wireframe (ASCII)

```
┌─────────────────────────────────────────────────────────────────┐
│ TOP BAND: [Env: OBSERVE] [Halt: OFF] [Account: All] [Time UTC] │
├──────────────────────────────────┬──────────────────────────────┤
│ MAIN: Equity/P&L | Exposure      │ SIDE RAIL: Intelligence      │
│ Regime overview | Open positions │ activity | System health     │
│ High-priority opportunities      │ Alert queue                  │
├──────────────────────────────────┴──────────────────────────────┤
│ LOWER: Recent decisions | Research awaiting action | Exec quality│
└─────────────────────────────────────────────────────────────────┘
Every element drills into its source record.
```

### 9.4 Intelligence Core Screen (Section 17.4)

Shows: what system is doing, why prioritized, sources/tools used, what learned, what remains uncertain, decision state. **No hidden chain-of-thought** — auditable evidence + structured findings + concise rationale only.

### 9.5 Mobile (Section 17.5)

Secure auth, live status, approvals, account monitoring, emergency halt, incident alerts, research summaries. Deep charting/config via desktop. Live approval never depends on tiny ambiguous tap.

### 9.6 Charts & Graphics (Section 23)

Heatmap, correlation matrix (with stability warnings), yield/futures curves, vol surface/skew/term structure, order-book depth (where entitled), exposure treemap, factor-risk decomposition, drawdown/equity curves with trade annotations, evidence graph, scenario fan charts, strategy comparison with confidence intervals. **No synthetic depth, fabricated order flow, or unavailable Greeks** — show unavailable state with cause (entitlement/venue/ingestion).

---

## 10. Zero-Cost Plan: $0 Hosting, $0 Tooling, $0 Data (D-019)

> **Owner constraint D-019 (2026-11-25): FREE tools and FREE APIs only. No paid services.**
> Target monthly spend for the whole system: **$0**. Verified against current (Nov 2026) free-tier terms.
> **No-spend rule:** if any required component has no $0 option, NEXUS does not silently adopt a paid
> service — it raises a blocking decision to the owner and, until approved, narrows scope instead.

### 10.1 Compute — free always-on VMs (verified Nov 2026)

| Role | Provider / offer | Free allowance (current) | Why it fits | Catch (disclosed) |
|------|------------------|--------------------------|-------------|-------------------|
| **Primary host** (all 15 services in Docker Compose) | **Oracle Cloud Always Free — Ampere A1 (ARM64)** | **2 OCPUs / 12 GB RAM** (1,500 OCPU-hrs + 9,000 GB-hrs/mo), **200 GB** block storage, **10 TB/mo** egress, 20 GB object storage, 1× 10 Mbps load balancer | Always-free (no expiry), enough RAM for Postgres + TimescaleDB + NATS + Redis + app services + a small local model; ARM64 images are mainstream now | Allowance was **halved on 15 Jun 2026** (4 OCPU/24 GB → 2/12 GB, enforced 18 Aug 2026) and can change again; **idle reclaim** if 7-day CPU/network/memory stay <20%; no support ticket; card required at signup (not charged) |
| **Secondary host** (off-box watchdog + alert relay + backup target) | **Google Cloud Always Free — e2-micro** | 1× e2-micro (2 shared vCPU burst, 1 GB RAM), 30 GB disk, 1 GB NA egress/mo | Independent failure domain: if the Oracle box dies or is reclaimed, this box still fires alerts and holds the latest encrypted backup | Only free in **us-west1 / us-central1 / us-east1**; 1 GB RAM = watchdog duties only; adds ~30–120 ms latency to Nigeria (fine for alerts, not for execution) |
| Local dev / backtest burst | Owner's existing PC | n/a | Heavy backtests and research runs happen locally, free, without touching VM CPU | Owner hardware only; not a production host |
| **Rejected** | Render / Railway / Fly.io free tiers | Sleep after 5–15 min idle; trials; $1/mo usage | **A trading system must not sleep.** Free PaaS tiers are structurally unfit | — |
| **Rejected** | AWS Free Tier | New accounts: credits (~$100–$200, 6 months), no always-free VM | Credits expire → becomes a bill | — |
| **Rejected** | Paid VPS / MT "forex VPS" | $5–$100/mo | Violates D-019. MT bridges run on the free Oracle box via Wine instead | — |

**Latency reality (no sugar-coating):** a US/EU free VM is **not** colocated with any venue. That is
acceptable for Observe → Research → Shadow/Paper and for intraday (minutes-to-hours) horizons, but it is
**not** acceptable for latency-sensitive scalping or any HFT-style claim. If measurement in Shadow shows
round-trip latency harming fills, the answer under D-019 is to **drop scalping from scope**, not to buy
a closer server.

### 10.2 Software — self-hosted, free licences only

| Concern | Chosen component | Licence | Cost |
|---------|------------------|---------|------|
| System of record | PostgreSQL 16 + TimescaleDB (Apache-2 community) | Apache-2 / PostgreSQL | $0 |
| Research/analytics store | DuckDB + Parquet on local disk | MIT | $0 |
| Event bus | NATS + JetStream | Apache-2 | $0 |
| Cache / rate-limit buckets | Valkey (Redis OSS fork) | BSD-3 | $0 |
| Object storage | MinIO (community) on block volume | AGPL-3 (self-host, no redistribution) | $0 |
| Secrets | **OpenBao** (Vault OSS fork) or SOPS + age + encrypted files | MPL-2.0 | $0 |
| Identity / MFA | Keycloak (owner-only realm, TOTP/WebAuthn) | Apache-2 | $0 |
| TLS / reverse proxy | Caddy (automatic Let's Encrypt) | Apache-2 | $0 |
| Private access (no open ports) | Tailscale free personal plan **or** Cloudflare Tunnel (cloudflared) | Free tier | $0 |
| Observability | Prometheus + Grafana OSS + Loki + Alertmanager | AGPL/Apache | $0 |
| Uptime / dead-man switch | Uptime Kuma (self-hosted) + healthchecks.io free tier + GCP e2-micro watchdog | MIT / free tier | $0 |
| Error tracking | Sentry free tier (self-hosted option available) | FSL/BUSL, self-host free | $0 |
| CI/CD | GitHub free private repos + GitHub Actions (2,000 min/mo free) | Free tier | $0 |
| Security scanning | Trivy, Semgrep OSS, Dependabot, gitleaks | OSS / free | $0 |
| Containerization | Docker Engine + Docker Compose | Apache-2 | $0 |
| Backend / API | Python 3.12, FastAPI, Pydantic, SQLAlchemy | MIT/BSD | $0 |
| Venue SDKs | Official: `MetaTrader5` (pip), ccxt (MIT), venue REST/WS via `httpx`/`websockets` | OSS | $0 |
| Frontend | Next.js + React + TypeScript + TradingView **Lightweight Charts** (Apache-2) + TanStack Table/Query | MIT/Apache-2 | $0 |
| Fonts / icons | Inter + JetBrains Mono (SIL OFL), Lucide icons (ISC) | Free | $0 |
| Testing | pytest, hypothesis, Playwright, Grafana k6, Locust | OSS | $0 |
| MT4/MT5 on Linux | Wine (MetaQuotes' documented Linux path; official `mt5linux.sh`) | LGPL/OSS | $0 |
| **Rejected** | Grafana Cloud / Datadog / New Relic paid tiers, TradingView paid plans, managed K8s, Snowflake/BigQuery, paid charting licences | — | Violates D-019 |

### 10.3 Intelligence — free models only, with hard governance

| Layer | Free option | Current free limits (verified Nov 2026) | Rule |
|-------|-------------|------------------------------------------|------|
| **Local (primary for sensitive context)** | Ollama / llama.cpp running quantized open-weight models (e.g. 7B–14B Q4_K_M) on the 12 GB ARM box | No rate limit, no data leaves the box, **no GPU on free tier** → realistic ~5–12 tok/s CPU | Used for anything touching account data, positions, credentials-adjacent context |
| Free hosted APIs (secondary, non-sensitive only) | **Google Gemini free tier** (Flash-class, 1M-token context); **Groq free** (gpt-oss-120b/20b, Qwen3.8-27B, Whisper); **OpenRouter `:free`**; **NVIDIA NIM** | Gemini: per-project limits shown in AI Studio, not published; **free-tier prompts may be used to improve Google's products outside EEA/UK/CH**. Groq: 30 RPM, 1,000 req/day, 8K TPM, **200K tokens/day per model**. OpenRouter: 20 RPM, **50 req/day**. NIM: ~40 RPM, dev/test only | Provider router with per-key daily token budgets, backoff, and cached dedupe |
| Deterministic quant layer | pandas/numpy/statsmodels/scikit-learn/vectorbt (OSS) | None | **All trade-critical signals are computed here, not by an LLM** |

**Two non-negotiable governance rules (free-tier specific):**
1. **No free hosted model may ever receive credentials, account numbers, balances, positions, order details,
   or personally identifying data** — Gemini's free tier may use prompts for product improvement. Sensitive
   context stays on the local model. Enforced by an outbound redaction gate with tests.
2. **No live order may depend on an LLM being reachable.** Free tiers are rate-limited and can vanish. If the
   model layer is exhausted or unavailable, the decision state is **ABSTAIN** (fail closed) — never a guess,
   never a silent fallback to a weaker model without logging it in the audit trail.

### 10.4 Notifications — free channels, and the one honest gap

| Channel (D-016) | Free implementation | Free limit | Verdict |
|-----------------|---------------------|------------|---------|
| In-app | WebSocket / SSE from our own API | None | **ADOPT** |
| **Telegram** | Official Bot API (free, unlimited practical use) | Very high informal limits; we self-throttle | **ADOPT — primary critical channel** (instant, free, works on any phone) |
| Push (mobile/desktop) | Self-hosted **Web Push (VAPID)** + PWA install on iOS/Android | None (browser-provided) | **ADOPT** |
| Email | **Brevo free** (300/day, full API + SMTP + webhooks, no card) with Gmail SMTP as fallback | 300/day | **ADOPT** (daily budget + dedupe; alerts are consolidated, not one-per-event) |
| Uptime/dead-man | healthchecks.io free tier + GCP e2-micro watchdog | Free tier | **ADOPT** (detects "NEXUS itself died") |
| **SMS** | **No reliable $0 gateway exists for Nigeria.** Free "SMS APIs" are trial-credit-only, geo-restricted, or sender-ID-blocked for Nigerian numbers | — | ⚠️ **BLOCKED BY D-019** — owner decision required (see Q-05) |
| **WhatsApp** | WhatsApp Business Cloud API charges per business-initiated conversation; unofficial WhatsApp automation risks account ban | — | ⚠️ **BLOCKED BY D-019** — not free, and ToS-risky. Owner decision required (see Q-05) |

**Disclosure:** D-016 asked for *all* channels including SMS and WhatsApp. Those two cannot be delivered at
$0. Everything else is free and covers critical alerting with delivery status, retries and escalation.
Telegram + Web Push + Email + in-app is the proposed free critical-alert set.

### 10.5 What still costs money — and none of it is tooling

These are **market costs of trading itself**, not subscriptions, and they are unavoidable at any venue:

| Item | Nature | Control |
|------|--------|---------|
| Spread, commission, funding/swap, borrow, slippage | Per-trade market cost, charged by the venue | Modelled explicitly in backtests and in position sizing (Section 8); never hidden |
| Broker real-time data subscription for *some* exchange-listed markets | Broker-dependent; many MT5/cTrader brokers include FX/metals/indices data free with an account, while exchange-listed equity/futures depth may need a paid feed | **Broker selection criterion:** pick brokers whose free account data covers our instruments; if not, drop that instrument class from scope |
| Deposit/withdrawal & FX conversion fees | Venue/payment-rail cost | Documented per venue; no automated withdrawals at all (Section 1.4) |
| Capital itself | Owner's own funds | Out of scope for tooling spend |

**Everything NEXUS *builds and runs* on is $0.** Trading still has trading costs — pretending otherwise
would be a false claim.

### 10.6 Zero-cost trade-offs you must accept (honest list)

| # | Trade-off | Consequence | Mitigation at $0 |
|---|-----------|-------------|------------------|
| Z-01 | Single 12 GB ARM VM, no HA | One host failure stops the system | Fail-closed design; GCP e2-micro watchdog fires alerts; IaC rebuild script restores in <1 hr; no position left unmanaged because protective orders live **at the venue**, not on our VM |
| Z-02 | Oracle idle-reclaim (<20% CPU/net/mem over 7 days) | VM can be reclaimed | A live ingest + monitoring workload keeps utilization above thresholds naturally; encrypted daily backup to free object storage + GCP box; reclaim detected by watchdog |
| Z-03 | Free allowances can be cut without notice (Oracle did it in Jun 2026) | Capacity can shrink | Modular services with per-service memory caps; graceful degradation order (drop research depth before dropping risk/execution monitoring); re-verify terms each phase |
| Z-04 | 200 GB block + 20 GB object storage | Tick archive will hit the ceiling | Parquet + zstd columnar compression, tiered retention (raw ticks rolled up to 1s→1m bars), purge policy, and honest labelling of data coverage windows |
| Z-05 | No GPU | No large local models; CPU inference only | Small quantized models for language tasks; deterministic quant models do the actual signal work |
| Z-06 | Free LLM tiers: 50–1,000 req/day, may vanish, may train on prompts | Research synthesis is throttled; privacy risk | Local-first for sensitive data; request budgeting; cached reuse; **ABSTAIN when unavailable** |
| Z-07 | MT4/MT5 via Wine on Linux | Bridge fragility, upgrade risk | Pinned Wine version, MT5 preferred (MetaQuotes' documented Linux path), demo-only until 30 days stable, health-checked, isolated container, cTrader Open API as a native-protocol alternative |
| Z-08 | Free feeds: no SLA, no support, rate limits | Data gaps/staleness will occur | Data-quality gates fail closed; per-venue rate-limit budgets; multiple free sources cross-checked; staleness surfaced in UI |
| Z-09 | US/EU free VM, not colocated | Latency unsuitable for scalping | Scope limited to intraday/day horizons measured in Shadow; scalping excluded unless latency evidence supports it |
| Z-10 | No SMS/WhatsApp at $0 | One fewer critical channel | Telegram + Web Push + Email + in-app, each with delivery status, retries, escalation |

### 10.7 Total monthly cost

| Category | Cost |
|----------|------|
| Compute (Oracle Always Free + GCP e2-micro) | **$0** |
| Databases, queues, storage, observability, identity, TLS, CI/CD | **$0** (self-hosted OSS + free tiers) |
| Market data (exchange WS/REST, broker feeds, free public archives) | **$0** |
| Macro/filings/news (FRED, EDGAR, EIA, CFTC, regulators, exchange announcements, free-tier news) | **$0** |
| Models (local Ollama + Gemini/Groq/OpenRouter/NIM free tiers) | **$0** |
| Notifications (Telegram, Web Push, Brevo free email, in-app, healthchecks.io) | **$0** |
| Software licences | **$0** (Apache-2 / MIT / BSD / MPL / AGPL self-hosted) |
| **TOTAL** | **$0 / month** |

*SMS and WhatsApp remain blocked by D-019 and require a separate owner decision (Q-05).*

### 10.3 Milestone Schedule (Section 26 Phases)

| Phase | Work package | Exit gate | Indicative duration |
|-------|--------------|-----------|---------------------|
| 0 — Discovery | Owner decisions, feasibility dossier | Approved scope + unresolved register | **DONE** (this report) |
| 1 — Product/UX bible | Journeys, page architecture, design system, prototypes | Owner approves experience | 2–3 weeks |
| 2 — Core foundation | Identity, DB, audit, secrets, events, observability, CI/CD | Security + reliability foundation passes | 3–4 weeks |
| 3 — Market data + instrument master | Canonical instruments, calendars, ingestion, quality, replay | Data completeness/correctness tests pass | 3–4 weeks |
| 4 — Read-only connectors | Bybit, MT5, MT4, cTrader + prioritized platforms; snapshots/health | Capability matrix verified per account | 4–6 weeks (staged per venue) |
| 5 — Research + memory | Source registry, evidence graph, cases, retrieval, freshness | Reproducibility + provenance tests pass | 3–4 weeks |
| 6 — Quant + strategy lab | Backtest engine, experiment registry, lifecycle, validation | No-leakage + realistic-cost suite passes | 3–4 weeks |
| 7 — Risk + portfolio | Exposure, sizing, limits, stress, authorization | Adversarial risk tests pass | 2–3 weeks |
| 8 — Execution gateway | State machine, idempotency, live adapters, reconciliation, kill switches | Sandbox + fault injection pass | 3–4 weeks |
| 9 — Shadow/paper | Live observation, decision logging, simulated execution, drills | Stability/calibration/operational gate pass | 4+ weeks (market-dependent) |
| 10 — Restricted live pilot | Small mandate, strict caps, monitoring, rollback | Pilot meets risk/execution criteria | 4+ weeks |
| 11 — Multi-market expansion | Additional instruments/venues/strategies/sources | Each expansion independently certified | Ongoing |
| 12 — Production hardening | Security audit, DR, load, observability, runbooks, legal review, release | Production readiness review approved | 3–4 weeks |

*No phase skipping (Section 26.1): later live capabilities cannot enable before dependencies/gates pass.*

---

## 11. Open Questions, Assumptions, Rejected Options & Owner Decisions Required

### 11.1 Open Questions (require owner input before live)

| # | Question | Why it matters | Default stance |
|---|----------|----------------|----------------|
| Q-01 | Per-account currency (USD/USDT/NGN)? | Sizing, FX, reporting | No live assumptions |
| Q-02 | Exact risk numbers (per-trade, daily, drawdown, exposure, max positions)? | Hard-limit enforcement | Conservative PROVISIONAL |
| Q-03 | Which broker(s) for MT4/MT5/cTrader serving Nigeria? | Symbol mapping, eligibility, deposits | Sandbox with demo first |
| Q-04 | Nigerian legal review scope/timeline? | Live gate | Live disabled until reviewed |
| Q-05 | **SMS and WhatsApp cannot be delivered at $0** (D-019). Accept the free alert set (Telegram + Web Push + Email + in-app), or explicitly approve per-message spend for SMS/WhatsApp as a separate decision? | Critical alert delivery during outages | Free set only: Telegram (primary) + Web Push + Brevo email + in-app |
| Q-06 | Model policy under zero cost: local-first (Ollama, private) + free hosted tiers (Gemini/Groq/OpenRouter) for non-sensitive research only? | Research quality, privacy, rate limits, fallback | Local-first for sensitive data; free APIs for non-sensitive; ABSTAIN if unavailable |
| Q-07 | Oracle Always Free is the primary host but can be reclaimed/cut without notice. Accept single-VM risk with watchdog + encrypted backups + <1 hr IaC rebuild, or restrict to Shadow/Paper until a second free host is validated? | Availability of the whole system | Accept for Observe→Shadow/Paper; re-review before any live phase |
| Q-08 | 200 GB storage cap limits how much tick history we can archive. Accept tiered retention (raw ticks → 1s → 1m rollups, purge policy), or narrow the instrument universe to keep depth? | Backtest depth and data-quality honesty | Tiered retention + honest coverage labels |

### 11.2 Assumptions (PROVISIONAL, require approval)

| # | Assumption | Why needed | Risk if wrong |
|---|------------|------------|---------------|
| A-01 | Free feeds are sufficient for Observe/Research/Shadow/Paper | Build the whole staged rollout at $0 (D-019) | **Narrow scope** (fewer instruments/venues, longer horizons) — never buy data without separate written approval |
| A-02 | Bybit/OKX live viable for Nigeria | Prioritize crypto adapters | Fall back to MT/cTrader brokers |
| A-03 | Free-tier US/EU VM latency acceptable for **intraday/day** horizons (minutes–hours) | Avoid paid VPS entirely | Drop scalping from scope; keep day-trading horizons only |
| A-04 | Oracle Always Free allowance (2 OCPU / 12 GB / 200 GB) stays available and is not reclaimed | Single-VM hosting at $0 | Rebuild via IaC on GCP free tier / local box; watchdog alerts; scope paused, never silently degraded |
| A-05 | Local quantized model + free API tiers give adequate research quality | Zero-cost intelligence layer | Reduce research depth tiers, increase deterministic quant weighting, ABSTAIN more often |
| A-06 | A Nigeria-serving MT5/cTrader broker provides free real-time data for our instruments with a demo account | FX/metals/indices coverage at $0 | Drop that instrument class from scope; crypto-only via exchange feeds |
| A-07 | Owner's $100k+ capital supports conservative 1% sizing within venue minimums | Risk math | Reduce size or revisit limits |

### 11.3 Rejected Options

| Option | Reason for rejection |
|--------|---------------------|
| IBKR live for Nigeria | Does not serve Nigerian residents (official) |
| OANDA live for Nigeria | Does not serve Nigerian clients |
| Binance live for Nigeria (now) | NGN/P2P suspended; domain blocked; regulatory gray area |
| Alpaca live for Nigeria (now) | Unverified eligibility; paper only |
| CCXT as sole adapter | Venue-specific features require native coverage |
| LLM-direct orders | Violates governance; risk engine must authorize |
| Live-by-default on connect | Violates Section 34; staged rollout required |
| 99.9% accuracy marketing | Violates Section 0.6; no guaranteed returns |
| **Paid data vendors (Polygon, Databento, dxFeed, LSEG, Bloomberg, Tiingo, Finnhub paid)** | **Violates D-019 zero-cost constraint** |
| **Paid hosting (any VPS, managed Postgres/K8s, "forex VPS")** | **Violates D-019; free always-on tiers exist** |
| **Free PaaS tiers (Render/Railway/Fly) for production** | Sleep on idle; a trading system must never sleep |
| **AWS Free Tier as primary host** | Credits expire (6 months) → becomes a bill |
| **Paid LLM APIs (OpenAI/Anthropic/Google paid tiers)** | **Violates D-019; local + free tiers suffice for research synthesis** |
| **Paid SMS gateways (Twilio etc.) / WhatsApp Business Cloud API** | **Violates D-019; blocked pending explicit owner approval (Q-05)** |
| **Paid observability/SaaS (Datadog, Grafana Cloud, New Relic)** | **Violates D-019; self-hosted OSS covers it** |
| **Paid charting (TradingView plans, licensed chart libs)** | **Violates D-019; Lightweight Charts (Apache-2) covers it** |

### 11.4 Owner Decisions Required

1. ✅ **DONE** — Feasibility Report approved (D-018, 2026-11-25).
2. ✅ **DONE** — Zero-cost constraint recorded (D-019, 2026-11-25): free tools/APIs/data only, $0/month.
3. Confirm per-account currency (Q-01) or defer with understanding.
4. Confirm exact risk numbers, or approve the conservative PROVISIONAL profile for Risk Policy drafting (Q-02).
5. Nominate MT/cTrader broker(s) for sandbox (Q-03), or authorize demo-first broker selection by us against the free-data criterion (A-06).
6. Confirm Nigerian legal review commissioning (Q-04).
7. **Decide Q-05:** accept the free alert set (Telegram + Web Push + Email + in-app) — SMS/WhatsApp are not available at $0.
8. Confirm Q-06 model policy (local-first + free tiers + ABSTAIN on unavailability).
9. Confirm Q-07 single-free-VM risk acceptance, or restrict to Shadow/Paper until a second free host is validated.
10. Confirm Q-08 storage/retention policy (tiered rollups + purge) or a narrower instrument universe.

---

## 12. Staged Delivery Plan & Test Strategy

### 12.1 Test Pyramid (Section 20.1)

| Layer | Examples | Gate |
|-------|----------|------|
| Static + unit | Types, lint, schemas, risk math, conversions, state transitions | Every commit |
| Component | Adapter contract, research parser, memory retrieval, tool schemas, portfolio calc | Every component change |
| Integration | DB, event bus, broker sandbox, market data, secrets, notifications, workflows | Every integration change |
| Simulation | Historical replay, synthetic book, partial fills, slippage, gaps, disconnects, rate limits | Every strategy/execution release |
| End-to-end | Connect, fetch positions, risk-approved intent, test order, reconcile, audit | Every release candidate |
| Resilience | Crash, network loss, stale feed, duplicate event, DB outage, clock drift, provider outage | Before production |
| Security | Threat tests, permission tests, injection tests, secret scans, access-control tests | Every release candidate |
| Operational acceptance | Monitoring, alerts, backup restore, runbooks, incident drill, rollback | Before live authority |

### 12.2 Execution Fault Injection (Section 20.5) — must pass before live

- Order accepted but response times out → verify no duplicate.
- Partial fill + cancel → reconcile remaining qty + actual position.
- Private WS disconnect while working → recover via REST snapshot + replay.
- Stale/crossed market data → block new risk-increasing orders.
- Broker reject (precision/margin/market state) → record reason, no retry loop.
- Terminal restart with open positions → reconnect + reconcile before entries.
- DB/event bus unavailable → fail closed, preserve durable journal.
- Clock drift → detect + block time-sensitive decisions.
- Risk service unavailable → no bypass.
- Duplicate/delayed/out-of-order events → idempotency + sequence handling.

### 12.3 Backtesting Standards (Section 20.2)

Point-in-time data, realistic calendars/fees/spreads/slippage/borrow/funding/financing/impact, order delay, partial fills, halts, rolls, corporate actions. No look-ahead/survivorship/selection bias. Capacity + cost sensitivity. Final untouched holdout.

---

## 13. External Dependencies Requiring Owner Accounts/Permissions

Every dependency below is **$0**. Owner accounts are required, but none of them involve a subscription,
a paid tier, or a purchase. (A card may be requested for identity verification at signup by cloud providers;
it is not charged while staying inside the always-free limits — stated explicitly so there is no surprise.)

| Dependency | Owner action required | Cost | Notes |
|------------|----------------------|------|-------|
| Bybit account + API keys (trade-only, withdrawal-disabled, IP allowlist) | Create account, KYC (Nigeria), generate keys | **$0** | Demo/testnet first. Never share secrets in chat; OpenBao/SOPS flow only |
| OKX account + API keys (demo trading first) | Create account, KYC, generate keys | **$0** | Demo first |
| Binance **testnet** keys (sandbox only for Nigeria) | Register testnet | **$0** | Live deferred (restricted jurisdiction) |
| MT4/MT5 broker **demo** account (Nigeria-serving broker) | Open demo, terminal login | **$0** | Broker TBD (Q-03); criterion: free real-time data for our instruments (A-06) |
| cTrader ID (cTID) + broker demo account | Register cTID | **$0** | Demo first |
| **Oracle Cloud Always Free** account (primary host) | Signup + card for identity verification | **$0** (always-free limits) | 2 OCPU / 12 GB ARM, 200 GB, 10 TB egress. Owner owns the tenancy |
| **Google Cloud free tier** account (watchdog host) | Signup + card for identity verification | **$0** (e2-micro, US regions) | Off-box watchdog, alert relay, backup target |
| GitHub account (private repo + Actions) | Already in place | **$0** (2,000 Actions min/mo) | CI/CD, dependency + secret scanning |
| FRED / EIA API keys | Register | **$0** | Public data |
| SEC EDGAR / CFTC / regulator feeds | None (public) | **$0** | Fair-access rate limits respected |
| Exchange public data archives (data.binance.vision etc.) | None | **$0** | Backtest history |
| **Telegram** account + bot (created by us via BotFather) | Owner installs Telegram, starts the bot | **$0** | Primary critical alert channel |
| **Brevo free** account (email alerts) | Signup, verify sending domain or use provided sender | **$0** (300/day) | Consolidated alerts within daily budget |
| Web Push (browser/PWA) | Owner enables notifications in browser | **$0** (self-hosted VAPID) | No provider needed |
| healthchecks.io free tier (dead-man switch) | Signup | **$0** | Detects "NEXUS itself died" |
| Nigerian legal counsel | Commission jurisdiction review | **Owner's own cost, outside NEXUS tooling** | Live gate (Q-04) — not a system dependency we can source free |
| LLM access | **None required to start**: local Ollama on our VM | **$0** | Optional free keys (Gemini/Groq/OpenRouter/NIM) for non-sensitive research only (Q-06) |
| **SMS / WhatsApp** | ⚠️ **Cannot be provided at $0** | Not free | **BLOCKED by D-019** — owner decision required (Q-05) |

> **Security rule:** Never ask owner to disclose passwords, API secrets, or seed phrases in chat (Section 0.2). All credentials via the encrypted secrets flow (OpenBao or SOPS+age) with encryption, rotation, revocation, and audit — all self-hosted and free.
>
> **Zero-cost rule (D-019):** if a dependency cannot be satisfied at $0, it is recorded as BLOCKED with the
> reason and escalated to the owner as a separate decision. NEXUS never silently signs up for a paid service.

---

## Appendix: Status & Traceability

- **This report:** CONFIRMED — approved by owner 2026-11-25 (D-018); **revised to v1.1** the same day to enforce the zero-cost constraint (D-019). Sections 4, 10, 11, 13 rewritten; paid options moved to *Rejected*.
- **Phase 1 (Product/UX Bible):** DESIGNED — `docs/03-product-ux-bible.md`, awaiting owner approval.
- **Monthly spend of the system:** **$0** (Section 10.7). SMS/WhatsApp excluded — not available free (Q-05).
- **Live trading:** DISABLED until Phases 0–9 gates pass + Nigerian legal review + separate live-authority approval.
- **Traceability:** Each requirement → design component → implementation item → test case → test result → release status (NOT STARTED / IN DISCOVERY / DESIGNED / IN DEVELOPMENT / TESTING / BLOCKED / ACCEPTED / DEFERRED).
- **No production code written. No live accounts connected. No paid service adopted.**

---

*Prepared 2026-11-25. Sources: Official docs (Appendix A) + Nigeria eligibility research (cited inline). No production code written. No live accounts connected.*
