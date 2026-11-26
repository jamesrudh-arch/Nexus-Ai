# 10 — Stage 3: Complete Dashboard Design

Status: **IN PROGRESS**, split into reviewable sub-deliverables per the owner's standing order:
**3.1 layout & information architecture** — APPROVED 2026-11-25 (D-033; §1 below).
Batches 3.2…3.5 draw the screen interiors inside the approved shell. Started only after Stage 2 approval
(D-032). Stages 4–23 untouched.

Binding inputs: docs/03 (page architecture §2, hierarchy §4, states §5, Command Centre §6,
mobile §9), docs/08 (brand), docs/09 (tokens, numeric policy, a11y floors), D-019 ($0 stack),
D-031 (accent graphics-only).

---

## 1. Sub-deliverable 3.1 — Shell, IA, screen map (BUILT — AWAITING REVIEW)

### 1.1 Research

- docs/03 re-read in full for fixed decisions: 15-page architecture, always-visible top band
  (environment, halt, account group, UTC time), left rail icon+label nav, Command Centre side
  rail (intelligence activity, health, alert queue) and lower strip, nine interaction states on
  every page/component, drill-down of every element to its source record, no-trade visibility.
- Current trading-terminal practice: density is a requirement, not a failure — made legible by
  hard boundaries between regions, one consistent rhythm inside each, type chosen for scanning;
  fixed edges (chart centre, tools left, context right; nothing floats, nothing overlaps);
  context rails carry three zoom levels (list → quote → narrative); telemetry (clock, engine
  state, constraints) belongs in the persistent header; each region does exactly one job.

### 1.2 Shell specification

- **Top band, 40 px, always visible:** mark (monochrome B, 20 px), environment badge
  (OBSERVE/RESEARCH/SHADOW/PAPER/PILOT/LIVE), global halt state, active account group,
  worst-case feed-freshness chip (LIVE/DELAYED/STALE semantics per docs/03 §3.3), UTC clock in
  mono tabular. Halt-active flips the band chip to negative and mounts a full-width banner.
- **Left rail, 208 px** (56 px icon-only below 1200 px): grouped nav — COMMAND (Overview);
  MARKETS (Live Markets, Trade Opportunities); INTELLIGENCE (Intelligence Centre);
  TRADING (Open Positions, Trade History); STRATEGY (Strategy Laboratory); RISK
  (Portfolio & Risk); SYSTEM (System Health, Settings & Controls). Active item: elevated
  surface + primary text; no accent colour in nav (D-031).
- **Main region:** 12-column grid, 16 px gutter; regions take whole spans (12, 7/5, 4/4/4);
  region = panel surface + hairline border + radius-card + 16 px padding; region chrome:
  heading-sm title, label caps column heads, caption metadata; one job per region.
- **Context rail, 264 px,** docked, on screens that define one (watchlist/quote/narrative on
  Live Markets; dossier on Opportunities/Intelligence; blotter detail on Open Positions; result
  panels on Laboratory; limits on Portfolio & Risk; alert queue on System Health). Never
  floating; below 1440 px it becomes a docked edge tab.
- **Lower strip** (recent decisions | research awaiting action | execution quality) on Overview
  only, per docs/03 §6.
- **No-trade visibility** is a first-class intelligence-tinted region on Overview: why NEXUS is
  waiting, what it watches, what would change its view, what invalidates the thesis.

### 1.3 Screen map (ten workspaces over the fifteen approved pages)

| screen | consolidates docs/03 pages | hierarchy lead |
|---|---|---|
| Overview | p1 Command Centre | P1 capital → P6 decisions |
| Live Markets | p2 Global Markets + p3 Instrument Workbench | scan → compare → drill |
| Trade Opportunities | p1 queue + p5 dispositions + p2 scanner | P5 evidence before size |
| Intelligence Centre | p4 + p5 + p6 | P5 → P6 |
| Open Positions | p8 positions + p9 Execution Room | P1 → P3 |
| Strategy Laboratory | p7 + p11 Scenario Studio | P6 with evidence |
| Portfolio & Risk | p8 (+ p11 stress views) | P1 → P2 → P3 |
| Trade History | p12 + p13 + p9 fills | recorded evidence |
| System Health | p14 + p10 Connections | P4 before P6 |
| Settings & Controls | p15 | governance |

Every approved docs/03 page has exactly one **primary** screen; where a second screen consumes
its records (decision queue, dispositions, fills, stress views) the feed is explicit and the
record stays single-sourced — no page is dropped, split or renamed away.

### 1.4 State chrome placement (docs/03 §5)

Global: Halted, Disconnected (top band + banner). Per feed/region: Stale, Delayed,
Unavailable (region header badge + last-updated caption; policy banner where new risk is
blocked). Per region: Loading (skeleton shimmer), Empty (icon + message + what NEXUS watches),
Error (red banner + retry + view logs) — one failing feed never blanks a screen. No-trade:
Overview region + Opportunities screen.

### 1.5 Unconditional rules

- Every figure, badge and row links to its source record; a number without a source link is a
  defect (docs/03 §4).
- Only overlays: confirmation modals (docs/03 §3.4/§5 approval binding) and, from Stage 4, the
  command palette. No floating widgets.
- Charts override library fonts to docs/09 tokens including axis labels; tabular numerals on
  every figure column.
- Mobile (<1024 px) follows docs/03 §9 (bottom tabs Command/Markets/Positions/Alerts/More +
  top band); designed in batch 3.5.

### 1.6 Evidence

`design/stage3-1-layout-ia.html` renders the shell, screen map, state placement and responsive
table from `design/tokens.css` (self-contained, fonts embedded); var audit clean. No screen
interiors are drawn in 3.1 — batches 3.2–3.5 compose them inside this shell, each presented for
review before the next.

---

## 2. Sub-deliverable 3.2 — Overview & Live Markets interiors (BUILT — AWAITING REVIEW)

Board: `design/stage3-2-overview-markets.html`. Composes inside the approved 3.1 shell with
approved Stage 2 tokens; var audit clean; 27 regions, 15 specimen-tagged.

### 2.1 Specimen-data policy (binding on all batches)

Design boards show labelled placeholder values so typography and density can be reviewed before
any data engine exists. Every region carrying specimen numbers carries a corner `SPECIMEN` tag
and the board opens with a ribbon stating the policy. Production renders only real or
labelled-simulated data (mandate §26); a region without a source link or a specimen tag is a
defect in either context.

### 2.2 Overview region plan (hierarchy = layout order)

P1 consolidated equity (display figure + realized/unrealized split with sign + glyph + ledger
link) → P2 exposure by venue (gross/net/share bar) → P3 live risk (limit usage, headroom,
fail-closed engine state) → P4 system health (per-feed freshness + latency, compromised-feed
bar) → regime overview (each value with uncertainty band) → open positions (protective order
state venue-reported) + high-priority opportunities (verification-gated, confidence never
overrides a failed mandatory condition) → no-trade region (watching / would-change /
invalidates) → side rail (intelligence activity, health, alert queue) → lower strip (recent
decisions, research awaiting action, execution quality).

### 2.3 Live Markets region plan

Capability-registry navigator (unsupported asset classes greyed with registry state, never
offered as tradable) → watchlist table (last/chg%/spread/session/freshness, tabular) → scanner
conditions → global heatmap (configurable universe + metric; no entitlement → unavailable +
cause) → session map on a UTC axis → context rail with the three zooms (list → quote →
narrative) → instrument workbench chart anatomy.

### 2.4 Chart anatomy (binding on every chart, Stage 3.3+ included)

Mandatory chrome line: instrument · venue · timeframe · timezone (UTC + venue-local) · data
status · delayed flag, mono caption. Axes/grid in hairline + mono tabular labels; price right,
UTC below; session shading bands identical to the session map; crosshair with mono value chips;
event markers ◆ intelligence / ⚠ warning, each linking to its record; overlays menu; export
CSV/PNG; volume pane venue-reported only. Honesty rule (docs/03 §8): no synthetic depth,
fabricated flow or invented Greeks — absent data renders unavailable + cause.

### 2.5 State variants demonstrated

Loading (skeleton shimmer + message), Empty (icon + "watching N instruments"), Error (negative
badge + retry + view logs), Stale (warning badge + last-updated + new-risk-blocked) — contained
per region; one failing feed never blanks a screen.

---

## 3. Sub-deliverable 3.3 — Intelligence Centre & Trade Opportunities (BUILT — AWAITING REVIEW)

Board: `design/stage3-3-intelligence-opportunities.html`. Var audit clean; 16 regions, 10
specimen-tagged.

### 3.1 Intelligence Centre region plan (docs/03 §7 chrome, complete)

Attention priorities (rank, why-now chips: novelty/uncertainty/event, research depth Tier 0–4,
cycle position OB→AN→RS→VF→DC→LE) · current tasks & tool activity (allowlist + source registry
enforced, every line links to its run record) · beliefs & uncertainty (confidence as a band with
validity interval and change conditions; a point estimate without them is a defect) · scenario
status with calibration state · dossier view (evidence graph claims↔sources↔assets↔decisions with
contradictions highlighted and linked, chronology, counter-thesis, quant result with run id,
disposition + reason code, freshness) · memory & knowledge (type tabs, expiring TTLs, corrections
as first-class entries) · decision-state strip carrying the complete vocabulary
ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN with reason codes. Context rail: knowledge-
sufficiency meter with stated basis and what it is sufficient *for*, tier legend, audit posture
(no hidden chain-of-thought).

### 3.2 Trade Opportunities region plan

Verified candidate queue: three verification stages per row (V1 evidence & data sufficiency,
V2 risk & mandate compliance, V3 execution safety — definitions finalise at Stage 11, chrome
reserved); any FAIL ends the candidate with a reason code; confidence never overrides a failed
stage. Expanded intent carries exactly the docs/03 §5 approval-binding fields (instrument, venue,
side, size, estimated cost, worst-case loss, portfolio impact, evidence summary, counter-case,
stop/exit plan, expiry) because Stage 4 approval binds to that immutable intent. Queue states:
empty (links to the Overview no-trade region), degraded engine (frozen queue + cause), verifying.
Context rail: verification trail with timestamps; mandate checks — environment SHADOW routes any
approval to paper execution; live authority DENIED until the owner authorises.

### 3.3 Button chrome decision

Buttons render as ghost/outline using semantic text + border tokens (primary = info/cyan family,
danger = negative family, ghost = border.strong) so every label clears 4.5:1 in both modes with
the approved Stage 2 token set. Filled buttons require dedicated on-colour text tokens; those
enter with the component tier at Stage 4, not before.

---

## 4. Sub-deliverable 3.4 — Positions, Laboratory, Risk, History (BUILT — AWAITING REVIEW)

Board: `design/stage3-4-trading-risk-history.html`. Four shells; var audit clean; 16 specimen tags.

### 4.1 Open Positions (p8 positions + p9 execution room)

Positions blotter with venue-reported protective-order state and a reconciliation column:
unmatched rows block new risk on that instrument until resolved. Order blotter carries working
orders, fills with slippage vs arrival, and rejects with reason codes linked to venue responses.
Reconciliation card (ledger vs venue per account) sits beside the emergency-halt control, which
shows its exact scope — accounts, instruments, working-order policy — before any confirm
(docs/03 J-03). Context rail: per-position protective detail with venue ack timestamps and the
unknown-order policy (unconfirmable order state → CRIT alert + new risk blocked).

### 4.2 Strategy Laboratory (p7 + p11)

Catalogue with cost-adjusted Sharpe as confidence intervals, maxDD, turnover, environment state
and promotion-gate progress; never ranked by hit rate alone (docs/03 §8). Selected-strategy panel:
hypothesis, backtest vs walk-forward vs stress rows, the five promotion gates with owner approval
last, model-registry code hash and pinned data window. Scenario studio mini-panel: shocks with
portfolio reprice and limit-after. Context rail states the promotion law (RESEARCH → SHADOW →
PAPER → PILOT → LIVE, each step owner-approved, rollback recorded before promotion, never
automatic) and paper-runtime progress.

### 4.3 Portfolio & Risk (p8 + p11)

Consolidated accounts, factor exposures with usage bars, concentration vs per-instrument limits,
stress repricing with calibration state, and a risk-limits ledger: owner-set only, every change
audited and linked, with the standing rule that the independent fail-closed risk engine cannot be
widened by model confidence. Context rail: equity/drawdown curve anatomy — gross solid, net
dashed with fees/funding/slippage deducted, trade annotations linking to records (docs/03 §8).

### 4.4 Trade History (p12 + p13 + p9 fills)

Fills table (venue-reported, slippage and fees per fill); performance & attribution with
cost breakdown and benchmark comparison; calibration panel that shows under-sampled cases rather
than hiding them; append-only audit & replay stream across research, decisions, approvals,
orders, fills, changes and incidents with replay selector and CSV/PNG export carrying a
provenance header (window, filters, data status).

---

## 5. Sub-deliverable 3.5 — System Health, Settings & Controls, mobile (BUILT — AWAITING REVIEW)

Board: `design/stage3-5-health-settings-mobile.html`. Two shells + mobile frame; var audit clean.

### 5.1 System Health (p14 + p10)

Feed/adapter/entitlement grid with registry coverage states (SUPPORTED/CONNECTED/
DATA-AVAILABLE/TRADE-ENABLED/LIVE-VERIFIED), freshness, latency, last sync; states are measured
and cited (the bybit row shows the real geo-block condition, not a painted tick). Alert triage
queue over the six docs/03 p14 kinds with severity, state and incident links; delivery status for
the $0 self-hosted channels (D-019) where a silent channel raises its own alert; incident
timeline card with scope, actions, reconciliation state and owner-notification time. Context
rail: versioned feed-integrity checks (failed check ⇒ feed barred + CRIT).

### 5.2 Settings & Controls (p15)

Environment ladder OBSERVE→RESEARCH→SHADOW→PAPER→PILOT→LIVE rendered as **state, not a toggle**:
LIVE shown locked; promotion requires owner request + MFA + recorded mandate + rollback plan +
independent risk-engine acknowledgement; live authority displays its DENIED state with the smoke
evidence date. Risk mandates owner-set with audit links; data-source table carries a mandatory
D-019 cost column that rejects paid sources at this screen; model/tool registry with hashes and
retention; roles & security (MFA step-up surfaces, vault-only keys with tested redactor,
sessions, retention). Context rail: settings change log and the rule that configuration changes
carry trade-grade decision chrome.

### 5.3 Mobile control surface (docs/03 §9)

340px frame: 36px top band (environment, halt, UTC), compact Command hierarchy (equity, P&L,
exposure, feeds), full-width EMERGENCY HALT at tap 1 with scope + MFA confirmation at tap 2,
positions/no-trade summaries, offline banner (cached read-only, stale badge, no order
submission), fixed bottom tabs Command · Markets · Positions · Alerts · More. Must-support list
from §9 reproduced verbatim on the board; deep charting and complex configuration defer to
responsive desktop.

---

## 6. Stage 3 completion summary (pending stage-level approval)

Ten screens + mobile surface, all composing inside the approved 3.1 shell with approved Stage 2
tokens: boards 3.1 (shell/IA), 3.2 (Overview, Live Markets, chart anatomy), 3.3 (Intelligence,
Opportunities), 3.4 (Positions, Laboratory, Risk, History), 3.5 (Health, Settings, mobile).
Cross-cutting laws restated on every board: specimen-tagged design data vs real-or-labelled
production data; drill-down from every figure; verification gates before decisions; owner-only
mandates; fail-closed risk; no hidden chain-of-thought; capability registry never advertises
unsupported markets; $0 cost gate; WCAG floors from docs/09.
Stage 3 is complete at batch level (D-033…D-036); **stage-level approval is requested next** and
gates Stage 4 (Interaction & UX).
