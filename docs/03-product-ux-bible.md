# NEXUS Product & UX Bible — Phase 1

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026  
**Baseline:** Approved 2026-11-25 (D-017)  
**Feasibility:** Approved 2026-11-25 (D-018)  
**Date:** 2026-11-25  
**Status:** PROPOSED — requires owner approval (Phase 1 exit gate)  
**Owner profile:** Personal, Nigeria, multi-asset, intraday, autonomous live (within hard limits), conservative risk, cloud hosting, desktop + iOS + Android  
**Cost constraint:** **D-019 — FREE tools / FREE APIs / FREE data only. $0/month.** Every UI dependency must be open source or a genuinely free tier (see §3.5). No paid charting, no paid UI kit, no paid font, no paid push/SMS provider.

> Per Section 17: premium professional terminal, not a retail trading app.  
> Real data only. No fake balances, invented P&L, fabricated confidence, or simulated live feed in production.  
> Every chart shows instrument, venue, timeframe, timezone, data status, and whether values are delayed.

---

## Table of Contents

1. User Journeys
2. Page Architecture (15 pages)
3. Design System
4. Information Hierarchy
5. Interaction States
6. Command Centre Layout
7. Intelligence Core Screen
8. Graphics & Charting Prototypes
9. Mobile Specification
10. Accessibility
11. Open Items for Owner Approval

---

## 1. User Journeys

### J-01 — Morning Command Check (Desktop, 5 min)
**Goal:** Understand overnight state before intraday trading.
1. Owner opens Command Centre → sees environment state (OBSERVE/RESEARCH/SHADOW/PAPER/PILOT/LIVE), halt state, account group, UTC time.
2. Reviews consolidated equity, realized/unrealized P&L, exposure, live risk, system health.
3. Checks market regime overview (trending/ranging, volatility, risk-on/off, liquidity stress) with uncertainty.
4. Reviews open positions + high-priority opportunities (drill into source records).
5. Checks side rail: intelligence activity, system health, alert queue.
6. Reviews lower region: recent decisions, research cases awaiting action, execution quality.
7. **Exit:** Owner knows capital, exposure, risk, health, and what NEXUS is watching — and why it is waiting if no trade is justified.

### J-02 — Intraday Monitoring (Mobile, glanceable)
**Goal:** Monitor live positions and risk without opening desktop.
1. Owner opens mobile Command Centre (compact hierarchy) → equity, P&L, exposure, halt state at top.
2. Sees live positions with protective-order status (venue-reported, not assumed).
3. Receives critical alerts via push/SMS/Telegram (halt, limit breach, unknown order state, broker compromise).
4. Taps alert → drills into incident record (timeline, affected accounts/orders, financial impact).
5. **Exit:** Owner can halt new entries from phone in ≤2 taps with explicit confirmation.

### J-03 — Emergency Halt (Mobile, critical)
**Goal:** Stop new risk immediately during incident.
1. Owner taps Emergency Halt → sees exact scope (which accounts/instruments affected, what happens to working orders per configured policy).
2. Confirms with step-up auth (MFA) → halt engages, new entries blocked, eligible working orders cancelled per policy.
3. System moves to controlled safe state; incident ID created; owner notified on all channels.
4. Owner reviews incident timeline, reconciles positions, then resumes via explicit resume flow.
5. **Exit:** No new risk; account state protected; evidence preserved.

### J-04 — Research Case Review (Desktop)
**Goal:** Understand why NEXUS is watching an instrument and what would change its view.
1. Owner opens Research Dossiers → selects case → sees thesis, counter-thesis, asset/instrument identity, market context, catalysts.
2. Reviews evidence table: source, publication time, observation time, affected instruments, claim type, confidence, corroborating/contradictory sources.
3. Sees quantitative findings, scenario tree (base/upside/downside/tail), expected holding period, invalidation conditions, event risk, liquidity, costs, portfolio interaction.
4. Checks freshness, source quality, contradictions, final disposition.
5. **Exit:** Owner understands what is known, what is uncertain, and what would invalidate the thesis. Research completion ≠ trade signal.

### J-05 — Strategy Promotion (Desktop, gated)
**Goal:** Approve a strategy for live pilot.
1. Owner opens Strategy Laboratory → selects strategy → reviews dossier (hypothesis, rationale, eligible instruments, data reqs, entry/exit, horizon, sizing, risk budget, capacity, costs, failure modes, regime deps, benchmark, code version, test suite, validation history, kill conditions).
2. Reviews backtests, walk-forward, stress tests, paper/shadow results with confidence intervals and cost-adjusted metrics.
3. Sees lifecycle state (IDEA → … → LIVE-CANDIDATE → APPROVED) and promotion gate checklist.
4. Approves (or rejects) with explicit mandate scope (accounts, instruments, leverage band, notional limit, schedule).
5. **Exit:** Strategy is APPROVED only with mandate + kill conditions + rollback path. No self-promotion.

### J-06 — Incident Response (Mobile + Desktop)
**Goal:** Detect → classify → contain → protect → preserve → notify → investigate → recover → reconcile → review → prevent (Section 29.1).
1. Alert fires (Critical/High/Medium/Informational) → owner notified on all channels with delivery status.
2. Owner opens incident → sees severity, timeline, affected accounts/orders, financial impact, root cause (when known), corrective action.
3. Owner contains (halt/reduce/close per policy), preserves evidence, then recovers + reconciles.
4. Owner closes incident with approval → preventive controls implemented.
5. **Exit:** Every incident has ID, timeline, impact, root cause, corrective action, closure approval.

### J-07 — Connection Setup (Desktop, secure)
**Goal:** Connect an exchange/broker with correct scopes.
1. Owner opens Connections → selects venue → sees capability matrix, permissions, market-data entitlements, adapter health, last sync.
2. Sees explicit scope explanation (read-only/demo/live) + real-money acknowledgement for live.
3. Enters credentials via secure Secrets Manager flow (never in chat, never in browser storage).
4. System verifies account identity, permissions, instrument rules, reconciliation → marks SUPPORTED/CONNECTED/DATA-AVAILABLE/TRADE-ENABLED/LIVE-VERIFIED separately.
5. **Exit:** Owner sees exactly what the mandate covers. No live-by-default.

---

## 2. Page Architecture (15 pages, Section 17.2)

| # | Page | Purpose & Essential Content | Primary user action |
|---|------|-----------------------------|---------------------|
| 1 | **Command Centre** | Global equity, realized/unrealized P&L, exposure, live risk, system health, market regime, active research, open positions, decision queue | Glance + drill into source records |
| 2 | **Global Markets** | Asset-class navigator, watchlists, scanner, heatmaps, breadth, volatility, liquidity, cross-market relationships, session map | Scan + add to watchlist |
| 3 | **Instrument Workbench** | Candlestick/market profile/order book (where available), fundamentals, derivatives, events, research history, strategy fit, venue comparison | Analyze one instrument across venues |
| 4 | **Intelligence Core** | Current tasks, attention priorities, research depth, beliefs, uncertainty, scenario status, tool activity, concise rationale | Understand what NEXUS is doing + why |
| 5 | **Research Dossiers** | Evidence graph, source citations, chronology, counter-thesis, quantitative results, contradictions, freshness, final disposition | Review case file |
| 6 | **Memory & Knowledge** | Searchable episodic/semantic/procedural memory, asset relationships, expiring knowledge, corrections, learning history | Search + correct memory |
| 7 | **Strategy Laboratory** | Catalogue, hypotheses, code/model versions, backtests, walk-forward, stress, paper/shadow, promotion gates | Review + approve/reject promotion |
| 8 | **Portfolio & Risk** | Consolidated accounts, positions, factor exposures, margin, drawdown, concentration, stress scenarios, risk limits | Review exposure + limits |
| 9 | **Execution Room** | Order blotter, live order states, fills, slippage, venue health, rejected orders, reconciliation, kill switch | Monitor execution + halt |
| 10 | **Connections** | Exchange/broker cards, account identity, permissions, entitlements, adapter health, last sync, capability matrix | Connect + verify |
| 11 | **Scenario Studio** | What-if scenarios, shocks, macro pathways, portfolio repricing, strategy sensitivity | Run what-if |
| 12 | **Performance & Attribution** | Returns, drawdown, risk-adjusted metrics, benchmark comparisons, strategy attribution, costs, calibration | Review performance |
| 13 | **Audit & Replay** | Time-ordered record of research, decisions, approvals, orders, fills, changes, incidents | Replay + export |
| 14 | **Alerts & Operations** | Data outages, broker issues, model degradation, limit breaches, stale sources, delivery status | Triage alerts |
| 15 | **Settings & Governance** | User roles, account mandates, live authority, risk limits, data sources, model registry, retention, security | Configure mandates + limits |

**Navigation:** Left rail (desktop) with page icons + labels; top band (environment, halt, account group, time); side rail (intelligence activity, health, alerts) on Command Centre. Mobile: bottom tab bar (Command, Markets, Positions, Alerts, More) + top band.

---

## 3. Design System (Section 17.1)

### 3.1 Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-canvas` | `#0B0F14` (deep graphite) | App background |
| `--bg-panel` | `#121A24` | Panels/cards |
| `--bg-elevated` | `#1A2433` | Modals, dropdowns |
| `--border` | `#1F2B3A` | Separators |
| `--text-primary` | `#E6EDF3` | Headings, values |
| `--text-secondary` | `#8B9BB4` | Labels, metadata |
| `--text-muted` | `#5C6B82` | Timestamps, hints |
| `--green` | `#2ECC71` | Positive P&L, filled |
| `--red` | `#E74C3C` | Negative P&L, rejected |
| `--amber` | `#F39C12` | Warning, uncertainty, stale |
| `--cyan` | `#3498DB` | System info, links |
| `--purple` | `#9B59B6` | Research/intelligence layer |
| `--font-sans` | Inter, system-ui | UI text |
| `--font-mono` | JetBrains Mono, ui-monospace | Prices, IDs, code (tabular numerals) |

### 3.2 Typography

- **Headings:** 20/16/14px, semibold, tight leading.
- **Body:** 14px, regular, 1.5 leading.
- **Data:** 13px mono, tabular numerals, right-aligned in tables.
- **Labels:** 11px uppercase, letter-spacing 0.05em, secondary colour.

### 3.3 Colour Semantics (never sole signal)

- Green/red = market direction / P&L (always paired with ▲/▼ or +/- sign + label).
- Amber = warning/uncertainty (paired with ⚠ icon + text).
- Cyan = system information (paired with ℹ icon).
- Purple = research/intelligence (paired with ◆ icon).
- Status also uses shape/icon + text (e.g., ● LIVE, ◐ SHADOW, ○ OBSERVE).

### 3.4 Components

- **Cards:** Only for meaningful grouped info (equity block, exposure block). No decorative metric tiles.
- **Tables:** Dense but readable; sortable, filterable, column control; clear empty/error/loading states.
- **Charts:** Accurate axes, crosshair, timezone (UTC + venue-local), session shading, volume, overlays, event markers, export (CSV/PNG).
- **Buttons:** Primary (cyan), danger (red, for halt/close), ghost (secondary). Live actions require explicit confirmation modal with exact instrument/venue/account/side/size/type/cost/worst-case loss/impact/evidence/counter-case/stop-exit/expiry.
- **Badges:** Environment (OBSERVE/RESEARCH/SHADOW/PAPER/PILOT/LIVE), coverage (SUPPORTED/CONNECTED/DATA-AVAILABLE/TRADE-ENABLED/LIVE-VERIFIED), freshness (LIVE/DELAYED/STALE/UNAVAILABLE).

---

### 3.5 Zero-Cost UI Stack (D-019)

| Concern | Choice | Licence | Cost |
|---------|--------|---------|------|
| Framework | Next.js + React + TypeScript | MIT | $0 |
| Charts | TradingView **Lightweight Charts** (candles, volume, crosshair, overlays) | Apache-2 | $0 |
| Custom graphics (heatmaps, treemaps, correlation matrices, evidence graphs, fan charts) | D3 + visx, or hand-rolled SVG/Canvas | ISC / MIT | $0 |
| Tables / virtualization | TanStack Table + TanStack Virtual | MIT | $0 |
| Data fetching / cache | TanStack Query | MIT | $0 |
| Realtime | Native WebSocket / SSE from our own API | — | $0 |
| Styling | Tailwind CSS + CSS custom properties (tokens above) | MIT | $0 |
| Icons | Lucide | ISC | $0 |
| Fonts (self-hosted, no Google Fonts runtime call) | Inter, JetBrains Mono | SIL OFL 1.1 | $0 |
| Components | Radix UI primitives (headless, accessible) + our own styled layer | MIT | $0 |
| Maps (if session/geo view needed) | Leaflet + OpenStreetMap tiles | BSD-2 / ODbL | $0 |
| Mobile delivery | Responsive web + PWA (installable on iOS/Android) | — | $0 |
| Push notifications | Self-hosted **Web Push (VAPID)** — no paid push service | — | $0 |
| **Rejected** | TradingView paid plans, licensed chart libs (SciChart, Highcharts Stock), paid UI kits, Figma paid seats for delivery, paid analytics (GA4 is free but sends data off-box → self-hosted Plausible/Umami community instead) | — | Violates D-019 |

**Rule:** no screen may depend on a paid third-party runtime. If a visual cannot be built with the free
stack above, it is descoped or drawn by us in SVG/Canvas — never bought.

---

## 4. Information Hierarchy

**Priority order (Section 17):** Capital → Exposure → Live risk → System health → Evidence quality → Decisions.

1. **Top band (always visible):** Environment state, global halt state, active account group, time (UTC).
2. **Command Centre main:** Consolidated equity/P&L + exposure + regime + open positions + high-priority opportunities.
3. **Side rail:** Intelligence activity + system health + alert queue.
4. **Lower region:** Recent decisions + research awaiting action + execution quality.
5. **Drill-down:** Every element links to its source record (order, decision, case, incident, audit entry).

**No-trade visibility:** Command Centre must show why NEXUS is waiting, what it is watching, what would change its view, and which conditions would invalidate a thesis.

---

## 5. Interaction States

Every page/component must implement all states. No blank screens, no fake data.

| State | Visual | Content |
|-------|--------|---------|
| **Loading** | Skeleton shimmer (subtle) | "Loading positions…" with spinner |
| **Empty** | Icon + message | "No open positions. NEXUS is watching 12 instruments." |
| **Error** | Red banner + retry | "Failed to load positions. [Retry] [View logs]" |
| **Stale** | Amber badge + last-updated | "Data stale — last update 14:32:05 UTC (45s ago). New risk blocked." |
| **Delayed** | Cyan badge | "Delayed 15 min (venue feed). Values are delayed." |
| **Unavailable** | Grey badge + reason | "Order-book depth unavailable — cause: entitlement. [Request access]" |
| **Disconnected** | Red badge + reconnect | "Broker disconnected. Reconnecting… [View status]" |
| **Halted** | Red banner | "EMERGENCY HALT active — new entries blocked. [View incident]" |
| **No-trade** | Purple badge | "No trade justified — evidence insufficient. [View case]" |

**Approval binding (Section 24):** Approval requests show exact instrument, venue, account, side, size, order type, estimated cost, worst-case loss, portfolio impact, evidence summary, counter-case, stop/exit plan, expiry. Approval binds to that exact immutable intent. Any material change invalidates approval.

---

## 6. Command Centre Layout (Section 17.3)

```
┌─────────────────────────────────────────────────────────────────┐
│ TOP BAND: [Env: SHADOW] [Halt: OFF] [Account: All] [14:32 UTC] │
├──────────────────────────────────┬──────────────────────────────┤
│ MAIN:                            │ SIDE RAIL:                   │
│ ┌──────────────┐ ┌─────────────┐ │ Intelligence activity        │
│ │ Equity/P&L   │ │ Exposure    │ │ System health                │
│ └──────────────┘ └─────────────┘ │ Alert queue                  │
│ Market regime overview           │                              │
│ Open positions (table)           │                              │
│ High-priority opportunities      │                              │
├──────────────────────────────────┴──────────────────────────────┤
│ LOWER: Recent decisions | Research awaiting action | Exec quality│
└─────────────────────────────────────────────────────────────────┘
```

- **Top band:** Environment, halt, account group, time.
- **Main:** Equity/P&L + exposure, regime, positions, opportunities.
- **Side rail:** Intelligence, health, alerts.
- **Lower:** Decisions, research queue, execution quality.
- **Every element drills into its source record.**

---

## 7. Intelligence Core Screen (Section 17.4)

Shows:
- What the system is doing (current tasks, attention priorities, research depth Tier 0–4).
- Why the task was prioritized (novelty, uncertainty, event importance).
- Which sources/tools it used (tool allowlist, source registry).
- What it learned (memory updates with provenance).
- What remains uncertain (beliefs with confidence, validity interval, change conditions).
- What decision state resulted (ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN with reason codes).

**No hidden chain-of-thought.** Auditable evidence + structured findings + concise rationale only.

---

## 8. Graphics & Charting Prototypes (Section 23)

| Graphic | Data source | States |
|---------|-------------|--------|
| Global asset heatmap | Observatory (configurable universe + metric) | Empty (no universe), stale, unavailable |
| Correlation matrix | Rolling window controls + stability warnings | Break/unstable warning when relationship weakens |
| Yield / futures curves | Historical comparison | Missing curve → unavailable with cause |
| Vol surface / skew / term structure | Derivatives feed (where entitled) | No Greeks → unavailable, never fabricated |
| Order-book depth | Feed entitlement required | No entitlement → unavailable + reason |
| Exposure treemap + factor-risk decomposition | Portfolio engine | Empty (no positions) |
| Drawdown / equity curves | Ledger + trade annotations | Gross vs net separated; fees/funding/slippage shown |
| Evidence graph | Research engine (claims ↔ sources ↔ assets ↔ decisions) | Contradictions highlighted |
| Scenario fan charts | Scenario engine (assumptions + probability ranges) | Calibration shown |
| Strategy comparison | Strategy lab (cost-adjusted metrics + confidence intervals) | Never ranked by hit rate alone |

**Rule:** Do not draw synthetic depth, fabricated order flow, or unavailable Greeks. If absent, show unavailable state + cause (entitlement / venue limitation / ingestion failure).

---

## 9. Mobile Specification (Section 17.5)

- **Purpose:** Control + monitoring surface, not compute environment.
- **Must support:** Secure auth (biometrics + MFA), live status, approvals, account monitoring, emergency halt, incident alerts, research summaries.
- **May defer:** Deep charting, complex configuration → responsive desktop layouts.
- **Layout:** Bottom tab bar (Command, Markets, Positions, Alerts, More). Compact hierarchy; critical actions reachable in ≤2 taps.
- **Safety:** Live execution approval never depends on tiny ambiguous tap. Halt/approve require explicit confirmation modal with full intent details + step-up auth.
- **Offline:** Cached read-only view with stale badges; no order submission offline.

---

## 10. Accessibility (Section 17.1)

- Keyboard navigation (all actions reachable, visible focus).
- Screen-reader labels (aria-labels on charts, tables, alerts).
- Contrast ≥4.5:1 for body text; colour never sole signal (icons + text + shape).
- Scalable text (rem units; 200% zoom without breakage).
- Non-colour status cues (icons, patterns, labels).

---

## 11. Open Items for Owner Approval

| # | Item | Options | Default until decided |
|---|------|---------|----------------------|
| U-01 | Charting library | TradingView **Lightweight Charts** (Apache-2, $0) — decided by D-019 | **Lightweight Charts** (no paid charting option exists in scope) |
| U-02 | Language (English only vs multi-language) | English only vs + Hausa/Yoruba/Igbo/Pidgin | English only |
| U-03 | Report frequency (daily/weekly/monthly) | Daily+weekly+monthly vs custom | Daily+weekly+monthly (Section 31) |
| U-04 | Data retention (audit, market data, research) | 1yr / 3yr / 7yr / indefinite | 7yr audit, 3yr market data (to confirm) |
| U-05 | Emergency contacts (beyond owner) | None vs add contact | None (single owner) |

---

## Appendix: Traceability

- **Phase 1 exit gate:** Owner approves product experience (this Bible) → Phase 2 may begin.
- **Status:** PROPOSED (designed, not implemented). No production code written.
- **Next:** Owner approval → Phase 2 (Core foundation: identity, DB, audit, secrets, events, observability, CI/CD).

---

*Prepared 2026-11-25. No production code written. No live accounts connected.*
