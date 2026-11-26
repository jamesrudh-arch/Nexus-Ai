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
