# NEXUS-AI — Production Register

The permanent register required by the sequential production workflow. One row per reviewable
deliverable, carrying its stage, what was researched, what was built, what was tested, the evidence,
and — separately — what has been **reviewed** and what has been **approved**.

Two rules govern this document:

1. **Approval is never inferred.** A stage that is complete is not a stage that is approved. Nothing
   advances on the strength of the work looking finished, and no row may be marked approved without a
   recorded decision from the owner.
2. **Nothing approved is silently replaced.** Where new work changes a previously approved decision,
   the change is recorded as a *proposal* against the original row, with the reason, and waits.

Statuses used below: `NOT STARTED` · `IN PROGRESS` · `BUILT — AWAITING REVIEW` ·
`REVIEWED — CHANGES REQUESTED` · `APPROVED` · `SUPERSEDED`.

---

## Current stage

**STAGE 1 — NEXUS-AI BRAND IDENTITY.** Status: `APPROVED` (2026-11-25, decisions D-030, D-031).
Mark: **Direction B — Nexus N**. Colour: monochrome Ink/Graphite/Platinum with accent `#7364D8`
as evidenced in `docs/08` §2. Directions A and C remain in `brand/geometry.py` as archived
explorations and are not usable system assets.

**STAGE 2 — TYPOGRAPHY & DESIGN SYSTEM.** Status: `APPROVED` (2026-11-25, D-032). Proposals
P-1…P-4 remain OPEN and unapplied — approval covered the Stage 2 system, not those rulings.

**STAGE 3 — COMPLETE DASHBOARD DESIGN.** Status: `IN PROGRESS`, split into reviewable
sub-deliverables per the owner's standing order: 3.1 layout & information architecture
= **APPROVED 2026-11-25 (D-033)**; batch 3.2 (Overview + Live Markets interiors) in progress. Started only after the Stage 2 approval above. Stages 4 to 23 remain
`NOT STARTED`:
the Stage 1 approval above, per the workflow; extends docs/03, replaces nothing; proposals
P-2…P-4 recorded against docs/03 §3.1 and deliberately not applied. Stages 3 to 23 remain
`NOT STARTED` and are deliberately not touched: no dashboard, no architecture changes, no
agents, no strategies, no integrations.

---

## Register

| Stage | Component | Research completed | Implementation status | Tests performed | Evidence | Review status | Requested changes | Approval status |
|-------|-----------|--------------------|-----------------------|-----------------|----------|---------------|-------------------|-----------------|
| 1 | **Brand identity — three logo directions** (primary lockup, secondary/stacked, icon & monogram, light + dark, app icon, construction & proportions, clear space, minimum sizes, misuse rules, colour system, animation concept) | Peer set reviewed: institutional quant identities (Jane Street, Citadel, Two Sigma, Hudson River Trading, PDT) are restrained and near-monochrome, letting form carry the brand rather than decoration. Logo-scalability and brand-guideline literature reviewed for the hard constraints: icon-only marks must survive 16px, wordmarks do not; guidelines must specify clear space, minimum size per medium, background/contrast rules, and misuse examples; WCAG 2.1 wants 3:1 for graphical elements and 4.5:1 for text; construction must sit on one grid with even stroke weights and no gradients that muddy at small size; iOS masks app icons to a squircle so content needs a safe zone. Existing project decisions inventoried so nothing approved is replaced — `docs/03` §3.1 already defines UI tokens and §3.2 typography | Three directions built as **hand-authored SVG on a documented grid**, not as generated raster art: **A — Convergence**, **B — Nexus N**, **C — Aperture**. Each ships as a primary horizontal lockup, a stacked secondary, an icon-only mark, a monogram, light and dark variants, and a rounded app-icon tile. A single self-contained presentation page renders every panel with inline SVG, labelled, with clear space and minimum size shown visually rather than described, and a live 16px/24px/32px favicon test | Geometry generated programmatically so proportions are computed rather than eyeballed; contrast ratios computed with the WCAG relative-luminance formula for every proposed pairing; the 16px legibility claim tested by actually rasterising the mark at 16px and inspecting it, not asserted | `brand/` (18 SVG masters + measured PNG evidence), `docs/08-stage1-brand-identity.md` (guidelines + construction + colour rationale), `brand/stage1-presentation.html` (review artefact: 32 inline SVG panels + base64 size ladders, zero external refs), live preview on port 8000 | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** — D-030 (mark = Direction B), D-031 (colour system). Proposal P-1 remains open on its own row |
| 1 | **Brand colour system proposal** | `docs/03` §3.1 was inventoried before proposing anything. It assigns five hues to *semantic* dashboard roles: green `#2ECC71` (positive P&L), red `#E74C3C` (negative/rejected), amber `#F39C12` (warning/uncertainty/stale), cyan `#3498DB` (system info/links), purple `#9B59B6` (research/intelligence layer) | A **monochrome-first** identity is proposed (ink/graphite/platinum), which is both the institutional norm and collision-free. Any chromatic accent is offered as a small candidate set with its contrast ratios and its collision risk against those five semantic roles stated explicitly, rather than chosen silently | Collision check: a brand accent must not be any of the five semantic hues, or the mark competes with meaning inside the dashboard it brands. Contrast computed per candidate against ink and platinum | `docs/08` §colour | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** (D-031) |
| 1 | **Proposal affecting previously recorded work** | The five semantic hues in `docs/03` §3.1 are the widely-used "flat UI" defaults. They are functional and accessible, but generic for an institutional financial product | **Nothing has been changed.** Recorded here as a proposal only, because `docs/03` predates this stage and must not be silently replaced | — | `docs/08` §colour, "Proposal P-1" | **PENDING** | — | **NOT APPROVED** — `docs/03` §3.1 stands as-is until the owner decides |
| 2 | **Typography & design system** (type roles, numeric policy, three-tier DTCG tokens, dark+light semantic colour, space/radius/elevation/motion, self-hosted OFL fonts) | Dashboard-typography literature: weight-led hierarchy in a tight 11–24px range, tabular numerals mandatory in numeric columns, no contrast discount for small text, chart fonts must be overridden to the UI family; financial-numerics practice: one hero figure, minus-sign negatives, per-asset-class precision, no compact notation on actionable figures; W3C DTCG 2025.10 token format and three-tier architecture with modes as semantic alias swaps; docs/03 §3 inventoried first — every approved value preserved verbatim | `design/tokens/*.json` (4 DTCG sources), `design/build_tokens.py` → `design/tokens.css` (268 lines, 108 aliases), `design/fonts/` 8 woff2 latin subsets + licences, `design/stage2-specimen.html` self-contained specimen rendering every role, both modes, badges, elevation | `design/test_tokens.py`: reference integrity both modes; WCAG matrix — every text token ≥4.5:1 on all three surfaces of its mode and on its badge tint, every graphical token ≥3:1; tint derivation recomputed from hue+surface+alpha; docs/03 values preserved verbatim (11 assertions); scale monotonicity; build determinism; font presence — ALL PASS | `design/stage2-specimen.html` (live preview :8001), `design/tokens.css`, `docs/09-stage2-typography-design-system.md` | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** (D-032) |
| 3.3 | **Intelligence Centre & Trade Opportunities interiors** ( §7 chrome complete, evidence graph, verification-gated queue, approval-binding intent fields) | docs/03 §7 re-read (tasks, depth tiers, prioritisation reasons, tool allowlist, beliefs with validity, decision vocabulary, no hidden chain-of-thought); §5 approval-binding field list reused verbatim for the candidate intent | Intelligence: 7 regions + context rail (sufficiency meter with basis, tier legend, audit posture); Opportunities: queue with 3-stage verification chips + reason codes, expanded immutable intent, queue states, mandate checks (SHADOW → paper, live DENIED) | var audit 0 undefined; §7 requirement checklist walked item-by-item against regions; approval-binding fields diffed against docs/03 §5 list; specimen tags on all numeric regions | `design/stage3-3-intelligence-opportunities.html` (live preview :8001), `docs/10` §3 | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** (D-035) |
| 3.2 | **Overview & Live Markets interiors** (region plans, specimen-data policy, chart anatomy, state variants) | docs/03 §5/§6/§8 re-read (states, Command Centre layout, graphics honesty rule); terminal-practice density rules from 3.1 carried forward | Overview: 8 main regions in hierarchy order + no-trade region + side rail + lower strip; Live Markets: registry navigator, watchlist, scanner, heatmap, session map, three-zoom context rail; instrument workbench chart anatomy with all six mandatory chrome facts; four contained state variants | var audit 0 undefined; 15/15 numeric regions specimen-tagged; hierarchy order checked against docs/03 §4 priority list; chart chrome checked against docs/03 header rule + §8 | `design/stage3-2-overview-markets.html` (live preview :8001), `docs/10` §2 | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** (D-034) |
| 3.1 | **Dashboard shell & information architecture** (top band, left rail, 12-col main, context rail, lower strip, screen map, state chrome placement, responsive rules) | docs/03 §2/§4/§5/§6/§9 re-read for fixed decisions (15 pages, top band, rails, nine states, drill-down, no-trade visibility); current terminal practice: density made legible by hard region boundaries and one job per region, fixed edges, nothing floating, context rails with list→quote→narrative zoom, telemetry in the persistent header | Shell spec + screen map mapping the ten mandate screens onto the fifteen approved docs/03 pages (each page one primary screen, secondary feeds explicit); board renders the shell with real tokens, nav states, region priorities P1–P6 and the no-trade region | CSS var audit: 0 undefined tokens in the board; screen-map completeness reviewed against docs/03 §2 page table (15/15 pages placed, none dropped); state placement covers all nine docs/03 §5 states | `design/stage3-1-layout-ia.html` (live preview :8001), `docs/10-stage3-dashboard-design.md` §1 | **REVIEWED — APPROVED 2026-11-25** | none | **APPROVED** (D-033) — batches 3.2–3.5 may compose inside this shell |
| 2 | **Proposals P-2…P-4 affecting docs/03 §3.1** | Contrast measurement of the approved tokens as actually used (11px labels, text on elevated surfaces) | **Nothing has been changed in docs/03.** P-2 `--text-muted #5C6B82` = 3.55:1 on canvas; P-3 `--purple #9B59B6` = 4.12:1 as text; P-4 `--red #E74C3C` = 4.09:1 on elevated. Stage 2 routes around them at the semantic tier only | `design/test_tokens.py` recomputes all three failures and all three workarounds | `docs/09` §7 | **PENDING** | — | **NOT APPROVED** — docs/03 §3.1 stands verbatim until the owner decides |
| — | *Historical: Phases 1–4 (discovery, core foundation, market data, venue certification)* | Recorded in `docs/00`–`docs/06` with their own evidence and decisions D-001…D-029 | Phase 3 `ACCEPTED` (D-027); Phase 4 authorised VM-first (D-028), Bybit + OKX first (D-029) | 930 tests / 0 failures / 2 skipped; ruff + mypy strict clean; CI green on both events | `docs/00` change log, `docs/06` §5, GitHub Actions runs | Reviewed and accepted for Phase 3 | — | Phase 3 `APPROVED`. **Phase 4 partially open**: O-009 partially closed (OKX verified live twice; Bybit geo-blocked from hosted runners and unverified; Binance Vision verified end-to-end), O-010 open (a real 25,761-byte bi5 file downloaded, but `LAYOUT_VERIFIED` stays `False` until a run reports the layout measurements intact) |

---

## Decisions

| ID | Date | Decision | Scope |
|----|------|----------|-------|
| D-030 | 2026-11-25 | The NEXUS-AI mark is **Direction B — Nexus N** (solid letterform, node knocked out of the diagonal). Directions A and C are archived explorations, not system assets. Favicon/app-icon/small-size use is Direction B monochrome per `docs/08` §7 | Stage 1 brand identity |
| D-035 | 2026-11-25 | Stage 3.3 approved: Intelligence Centre (§7 chrome complete, evidence graph with linked contradictions, beliefs as bands) and Trade Opportunities (verification-gated queue, immutable approval-binding intent, SHADOW routes approvals to paper) | Stage 3 batches 3.4–3.5 |
| D-034 | 2026-11-25 | Stage 3.2 approved: Overview & Live Markets interiors, specimen-data policy (tagged placeholders in design, real-or-labelled data in production), chart anatomy binding on all charts, contained state variants | Stage 3 batches 3.3–3.5 |
| D-033 | 2026-11-25 | Stage 3.1 shell & IA approved: top band, grouped rail, 12-col main, docked context rail, screen map (10 workspaces over 15 approved pages), state chrome placement, responsive rules | Stage 3 screen batches |
| D-032 | 2026-11-25 | Stage 2 typography & design system approved as presented: type roles, numeric policy, three-tier DTCG token architecture, dark+light semantic colour, self-hosted OFL fonts. Proposals P-1…P-4 NOT ruled on; docs/03 unchanged | Stage 2; binding on Stage 3 screens |
| D-031 | 2026-11-25 | Brand colour system = monochrome **Ink #0B0F14 / Graphite #121A24 / Platinum #E6EDF3** with accent **Violet #7364D8** restricted to the node and the wordmark's terminal "AI". Semantic hues in `docs/03` §3.1 remain the only carriers of market meaning; the node never takes a semantic hue | Stage 1 brand identity; binding on Stage 2 tokens |

---

## Dependency note

Stage 1 has no dependency on any later stage and introduces none. It adds `brand/` and `docs/08`, and
changes no backend, infrastructure, or CI behaviour. The only interaction with existing work is the
**proposal** above regarding `docs/03` §3.1, which is recorded and waits rather than being applied.

## What happens on approval

On approval of a direction, that direction becomes the single identity; the other two are archived in
the register as `SUPERSEDED — not selected` with their files retained, so the decision is traceable
and no approved component is later replaced without a record. Stage 2 (typography and design system)
then begins, and not before.
