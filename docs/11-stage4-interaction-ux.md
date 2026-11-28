# 11 — Stage 4: Interaction & UX

Status: **IN PROGRESS**, sub-deliverables: 4.1 interaction system (this document §1, board
`design/stage4-1-interaction-system.html`) → 4.2 journeys & flows. Started only after Stage 3
stage-level approval (D-037). Stages 5–23 untouched.

Binding inputs: docs/03 §5 (nine interaction states, approval binding), §9 (mobile safety),
§10 (accessibility), docs/08 §9 (brand motion curve), docs/09 (tokens, a11y floors),
D-031 (accent graphics-only), D-037 (Stage 3 chrome).

---

## 1. Sub-deliverable 4.1 — Interaction system (BUILT — AWAITING REVIEW)

### 1.1 Research

Confirmation design for irreversible financial actions: confirmations must **restate specifics**
(amount, venue, account, timing) so the owner checks a statement rather than answers a question;
"are you sure?" is banned copy because it carries no information and is dismissed reflexively.
Friction must be **proportionate to risk**, not uniform — uniform friction trains dismissal;
step-up authentication fires on risk class, not on every click. Modals are earned interruptions:
reserved for consequential actions; irreversible confirmations may deliberately remove the
dismiss-without-choosing path; focus moves in on open, traps while open, returns to the trigger
on close; role=alertdialog for destructive confirms; stacking capped at two layers. Critical
alerts that need a response are never toasts. State representation: pending/settled/failed
visually distinct. Errors specific, actionable, non-blaming.

### 1.2 Component state machine

default → hover (border.strong, 120ms) → focus-visible (2px monochrome outline, instant) →
active (surface.elevated, no scale/glow) → selected (elevated + medium weight); disabled carries
a reason; loading = skeleton; error = in-region negative banner with retry + logs;
environment-locked = dashed negative border + lock glyph + reason. All chrome from approved
tokens; no state introduces a new colour.

### 1.3 Confirmation anatomy (binding on every consequential action)

Title names the exact action and object; irreversibility/binding chip shows the intent hash;
the body restates every docs/03 §5 field (instrument, venue, account, side, size, type, estimated
cost, worst-case loss in negative colour, portfolio impact, evidence summary, counter-case,
stop/exit, expiry with live countdown); MFA inline; **Cancel holds initial focus**; ESC and
backdrop cancel; confirm only via its button; focus returns to trigger; role=alertdialog.
Irreversible-class actions add typed confirmation (HALT / LIVE). Stacking ≤2 layers.

### 1.4 Friction ladder

none (view/filter/ack) → confirm+restated (mandate proposals) → +MFA (approve order, halt,
resume) → +typed+rollback (environment promotion to PILOT/LIVE). Live execution can never be
enabled by a single control or an ambiguous tap (docs/03 §9).

### 1.5 Halt & resume flow

One flow, four doors (top-band chip, mobile button, palette, alert banner) → scope modal
(accounts, instruments, working-order policy, typed HALT, MFA) → engaged state at the **risk
engine**, not the UI (a broken interface must not mean an un-halted book) + banner + incident id
+ all-channel notification + audit entry → incident timeline → resume as its own decision with
reconciliation checklist green + MFA + audit entry.

### 1.6 Command palette & keyboard model

⌘K palette over four groups (navigate, actions, instruments, records); environment-gated actions
render locked **with the reason**, never hidden; the palette triggers flows and never bypasses a
confirmation; keyboard-only complete. Global chords g+c/m/i/p/r; / filter; ? shortcut sheet;
j/k + enter on tables; chart crosshair arrows and t for timeframe presets; ESC always the safe
direction; skip-link to main; focus order = visual order; no traps except modals by design.

### 1.7 Motion spec

120ms state chrome · 200ms region swap and modal enter · 120ms modal exit · 200ms halt banner ·
1.2s brand moment on splash only (docs/08 §9 curve) · **0ms on money**: figure updates switch
instantly because animation on numbers misreads as a change in value. prefers-reduced-motion
zeroes all durations; state stays legible via colour+shape+text.

### 1.8 Alerts, labels, zoom

aria-live assertive: halt, CRIT, feed-barred; polite: stale/delayed, reconciliation. Charts
labelled with instrument, venue, timeframe, trend summary, data status. Badges always
glyph+text. 200% zoom: context rail docks first, tables scroll horizontally with pinned
instrument column, top band wraps — no clipped controls. Targets ≥44px mobile / ≥32px desktop.

### 1.9 Proposal P-5 (recorded, NOT applied)

docs/03 §3.2 states the type scale in px while §10 requires rem-based scalable text. Stage 4
specifies that type tokens are **consumed in rem** at implementation (identical rendered px at
100% zoom, scalable with user font settings); docs/03 and the Stage 2 token values remain
unchanged until the owner rules.

---

## 2. Sub-deliverable 4.2 — Journeys & flows (BUILT — AWAITING REVIEW)

Board: `design/stage4-2-journeys-flows.html`. Five flows, 31 steps; var audit clean.

### 2.1 Flows specified

- **J-01 Morning Command Check** (desktop ~5 min): top-band verification → capital/exposure →
  live risk & health → regime with uncertainty → positions & opportunities drill → rails & lower
  strip → no-trade reading. Branch: contained region error/stale; the check continues on healthy
  regions. Exit: owner can state capital, exposure, risk, health, evidence quality and what NEXUS
  watches, within one hop of drill.
- **J-02 Intraday Monitoring** (mobile): compact command → glance capital → positions with
  venue-reported protectives → assertive alert → incident drill → optional two-tap halt. Branch:
  offline = cached read-only with stale badge, no order submission, and an explicit statement that
  halt requires connectivity (no queued-halt fiction).
- **J-03 Emergency Halt** (mobile critical): four doors → scope modal with typed HALT + MFA →
  engage at the risk engine → notify & preserve → reconcile → resume as its own decision.
  Branches: MFA failure aborts with audit; partial venue ack invokes the unknown-order policy.
- **Approval binding**: verified candidate → review → freeze immutable intent hash → restate-not-
  ask confirm + MFA → route by environment (SHADOW ⇒ paper; live authority DENIED) → idempotent
  execute + reconcile. Branch: material change or expiry invalidates the approval and re-asks.
- **Incident triage**: CRIT alert → ack with SLA clock → scope → contain (feed barred, risk
  blocked) → notify (delivery failures alert themselves) → recover & close with note. Branch:
  insufficient containment escalates to J-03 with the incident linked.

### 2.2 Flow laws (binding on Stage 5+)

1. Every step names its screen region and chrome — a step without a surface is a missing design.
2. Every branch carries a visible state; silent failure is a defect.
3. Every exit condition is measurable (time, taps, green states) — journeys are testable at
   Stage 23 validation.
4. Critical mobile paths ≤2 taps; consequential paths pass restate-not-ask confirmation with MFA
   per the friction ladder.
5. Halt and risk blocks live in the risk engine; UI reflects engine state, never replaces it.
6. Approvals bind to immutable intents; material change invalidates and re-asks.

### 2.3 Stage 4 completion summary (pending stage-level approval)

4.1 interaction system (D-038) + 4.2 journeys & flows. Together they define how every approved
Stage 3 surface behaves: states, confirmations, friction, halt/resume, palette, keyboard, motion,
live regions, and the five owned journeys with measurable exits. Stage-level approval gates
Stage 5 (System Architecture).
