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

**STAGE 1 — NEXUS-AI BRAND IDENTITY.** Status: `BUILT — AWAITING REVIEW`. No later stage has been
started. Per the workflow, Stages 2 to 23 are `NOT STARTED` and are deliberately not touched: no
typography system, no dashboard, no architecture changes, no agents, no strategies, no integrations.

---

## Register

| Stage | Component | Research completed | Implementation status | Tests performed | Evidence | Review status | Requested changes | Approval status |
|-------|-----------|--------------------|-----------------------|-----------------|----------|---------------|-------------------|-----------------|
| 1 | **Brand identity — three logo directions** (primary lockup, secondary/stacked, icon & monogram, light + dark, app icon, construction & proportions, clear space, minimum sizes, misuse rules, colour system, animation concept) | Peer set reviewed: institutional quant identities (Jane Street, Citadel, Two Sigma, Hudson River Trading, PDT) are restrained and near-monochrome, letting form carry the brand rather than decoration. Logo-scalability and brand-guideline literature reviewed for the hard constraints: icon-only marks must survive 16px, wordmarks do not; guidelines must specify clear space, minimum size per medium, background/contrast rules, and misuse examples; WCAG 2.1 wants 3:1 for graphical elements and 4.5:1 for text; construction must sit on one grid with even stroke weights and no gradients that muddy at small size; iOS masks app icons to a squircle so content needs a safe zone. Existing project decisions inventoried so nothing approved is replaced — `docs/03` §3.1 already defines UI tokens and §3.2 typography | Three directions built as **hand-authored SVG on a documented grid**, not as generated raster art: **A — Convergence**, **B — Nexus N**, **C — Aperture**. Each ships as a primary horizontal lockup, a stacked secondary, an icon-only mark, a monogram, light and dark variants, and a rounded app-icon tile. A single self-contained presentation page renders every panel with inline SVG, labelled, with clear space and minimum size shown visually rather than described, and a live 16px/24px/32px favicon test | Geometry generated programmatically so proportions are computed rather than eyeballed; contrast ratios computed with the WCAG relative-luminance formula for every proposed pairing; the 16px legibility claim tested by actually rasterising the mark at 16px and inspecting it, not asserted | `brand/` (18 SVG masters + measured PNG evidence), `docs/08-stage1-brand-identity.md` (guidelines + construction + colour rationale), `brand/stage1-presentation.html` (review artefact: 32 inline SVG panels + base64 size ladders, zero external refs), live preview on port 8000 | **PENDING — presented to owner** | — | **NOT APPROVED** — awaiting owner decision on direction, accent colour, and the semantic-palette proposal |
| 1 | **Brand colour system proposal** | `docs/03` §3.1 was inventoried before proposing anything. It assigns five hues to *semantic* dashboard roles: green `#2ECC71` (positive P&L), red `#E74C3C` (negative/rejected), amber `#F39C12` (warning/uncertainty/stale), cyan `#3498DB` (system info/links), purple `#9B59B6` (research/intelligence layer) | A **monochrome-first** identity is proposed (ink/graphite/platinum), which is both the institutional norm and collision-free. Any chromatic accent is offered as a small candidate set with its contrast ratios and its collision risk against those five semantic roles stated explicitly, rather than chosen silently | Collision check: a brand accent must not be any of the five semantic hues, or the mark competes with meaning inside the dashboard it brands. Contrast computed per candidate against ink and platinum | `docs/08` §colour | **PENDING** | — | **NOT APPROVED** |
| 1 | **Proposal affecting previously recorded work** | The five semantic hues in `docs/03` §3.1 are the widely-used "flat UI" defaults. They are functional and accessible, but generic for an institutional financial product | **Nothing has been changed.** Recorded here as a proposal only, because `docs/03` predates this stage and must not be silently replaced | — | `docs/08` §colour, "Proposal P-1" | **PENDING** | — | **NOT APPROVED** — `docs/03` §3.1 stands as-is until the owner decides |
| — | *Historical: Phases 1–4 (discovery, core foundation, market data, venue certification)* | Recorded in `docs/00`–`docs/06` with their own evidence and decisions D-001…D-029 | Phase 3 `ACCEPTED` (D-027); Phase 4 authorised VM-first (D-028), Bybit + OKX first (D-029) | 930 tests / 0 failures / 2 skipped; ruff + mypy strict clean; CI green on both events | `docs/00` change log, `docs/06` §5, GitHub Actions runs | Reviewed and accepted for Phase 3 | — | Phase 3 `APPROVED`. **Phase 4 partially open**: O-009 partially closed (OKX verified live twice; Bybit geo-blocked from hosted runners and unverified; Binance Vision verified end-to-end), O-010 open (a real 25,761-byte bi5 file downloaded, but `LAYOUT_VERIFIED` stays `False` until a run reports the layout measurements intact) |

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
