# 09 — Stage 2: Typography & Design System

Status: **BUILT — AWAITING REVIEW** (see `docs/07-production-register.md`, Stage 2 row).
Review artefact: `design/stage2-specimen.html` (self-contained; production fonts embedded as
base64 woff2, all panels rendered by the generated token CSS).
Sources of truth: `design/tokens/primitives.json`, `design/tokens/semantic.shared.json`,
`design/tokens/semantic.dark.json`, `design/tokens/semantic.light.json` (W3C DTCG 2025.10).
Generated: `design/tokens.css` via `design/build_tokens.py`. Evidence: `design/test_tokens.py`
(exit 0 = every ratio, tint, scale and provenance claim below recomputes clean).

This stage **extends** `docs/03-product-ux-bible.md` §3 and **replaces nothing**. Every docs/03
value is preserved verbatim as a primitive (tested); where a docs/03 value fails WCAG as used,
the semantic tier routes around it and a *proposal* is recorded (§7) awaiting the owner.

---

## 1. Research completed

- **Dashboard typography for dense operational UI.** Hierarchy in a 30+-metric screen is
  weight-led, not size-led: a tight 11–24 px range with clear weight steps; tabular numerals
  (`font-variant-numeric: tabular-nums`, OpenType `tnum`) are mandatory in every numeric column
  because proportional figures make money columns ragged; small text gets **no** contrast
  discount — only ≥24 px (or ≥18.66 px bold) qualifies for the 3:1 large-text allowance, so the
  11 px label row must clear 4.5:1 like everything else; chart libraries ship foreign default
  fonts and must be overridden to the UI family *including axis labels*, or the product reads as
  two stitched-together apps.
- **Financial numerics.** One hero figure per screen (balance-first hierarchy); negatives as
  minus sign + semantic colour + direction glyph, never accounting parentheses mixed with minus
  on one screen; precision matched to printed-statement convention per asset class; compact
  notation ($1.2M) only where the exact figure is not actionable; locale formatting via
  `Intl.NumberFormat`, never hand-rolled concatenation.
- **Token architecture.** W3C Design Tokens Community Group format 2025.10 (stable Final CG
  Report; `$value`, `$type`, `{ref}` aliases, composite typography/shadow types) is read by
  Style Dictionary, Tokens Studio, Terrazzo and Figma variable import. Three tiers —
  primitive → semantic → component; **modes live in the semantic tier** (dark/light are alias
  swaps, primitives never change); components never reference primitives; keep mode out of
  names; three tiers is correct, more is a hobby project; component tokens are optional and
  arrive with the first components (Stage 3).

## 2. Type system

Families (docs/03 §3.1, D-019): **Inter** (UI) and **JetBrains Mono** (prices, IDs, code),
self-hosted latin subsets, SIL OFL 1.1, `font-display: swap`, fallbacks `system-ui` /
`ui-monospace`. Files: `design/fonts/*-latin-{400,500,600,700}-normal.woff2` (≈190 KB total).

| role | family | size | weight | leading | tracking | transform | numerals | origin |
|---|---|---|---|---|---|---|---|---|
| display | mono | 24 | 600 | 1.15 | −0.01em | — | tabular | **S2 add**: the one hero figure |
| heading-lg | sans | 20 | 600 | 1.25 | −0.01em | — | — | docs/03 §3.2 |
| heading-md | sans | 16 | 600 | 1.25 | 0 | — | — | docs/03 §3.2 |
| heading-sm | sans | 14 | 600 | 1.25 | 0 | — | — | docs/03 §3.2 |
| value | sans | 16 | 600 | 1.25 | 0 | — | tabular | **S2 add**: key card metric |
| body | sans | 14 | 400 | 1.5 | 0 | — | proportional | docs/03 §3.2 |
| data | mono | 13 | 400 | 1.4 | 0 | — | tabular | docs/03 §3.2 |
| data-emphasis | mono | 14 | 500 | 1.4 | 0 | — | tabular | **S2 add**: the row's figure |
| label | sans | 11 | 500 | 1.2 | +0.05em | uppercase | — | docs/03 §3.2 |
| caption | sans | 12 | 400 | 1.35 | 0 | — | tabular for times | **S2 add**: timestamps, hints |

Rules: exactly one `display` figure per screen; labels take `color.text.secondary`, captions
`color.text.muted`; nothing renders below 11 px; letter-spacing is never applied to numerals;
`tabular-nums` is applied to every financial figure, percentage, timestamp column and chart
axis label without exception.

## 3. Token architecture

- **Tier 1 `primitives.json`** — raw scales only (colour steps incl. the docs/03 values verbatim,
  space 4 px base, radius, border widths, font families/sizes/weights/leadings/tracking,
  numeric variants, motion). No purpose, no mode.
- **Tier 2 `semantic.shared.json` + `semantic.dark.json` + `semantic.light.json`** — purpose
  tokens: surfaces, text, borders, focus, brand accent, feedback (text/graphic/subtle per
  semantic hue), spacing purposes, radius purposes, elevation slots, typography roles, numeric
  policy. Dark is the default mode on `:root`; light is an override set on `[data-theme=light]`
  touching only colour and shadow.
- **Tier 3 component tokens** — deliberately empty at Stage 2; introduced with Stage 3
  components, referencing tier 2 only. A component reading tier 1 is a rejected change.
- Naming: DTCG groups → CSS `--category-concept-variant` kebab; mode never in a name; state and
  purpose never in primitives.
- Build: `design/build_tokens.py` → `design/tokens.css` (deterministic, tested). Fonts are
  declared there for production; the specimen embeds the same woff2 as base64 for offline review.

## 4. Numeric policy

Tabular everywhere (§2). Negatives: `-` sign + semantic negative colour + `▼`/`-` glyph
(docs/03 §3.3 pairing intact). Precision: fiat FX 4–5 dp; crypto 2–8 dp by pair tick size;
indices 2 dp; percentages 2 dp; never fewer than the venue's tick. Compact notation only for
non-actionable context (chart axes, summary deltas). Locale via `Intl.NumberFormat`. Every
figure carries a freshness stamp (`caption` role, `color.text.muted`) per docs/03 §3.3.

## 5. Colour, per mode (worst-case ratios, recomputed by test_tokens.py)

Dark (default): text primary 13.22+, secondary 5.54+, muted 4.55+; feedback text positive 7.43+,
negative 5.96+ (red.300), warning 7.12+, info 4.96+, intelligence 4.87+ (purple.300); graphics
≥3.0 everywhere incl. border.strong 3.37+ and focus 13.22+; badge tints = 12% of the docs/03 hue
over panel, text-on-tint 4.71+.
Light: text primary 16.27+, secondary 8.40+, muted 4.63+; feedback text 5.20+ (green.700),
5.60+ (red.700), 5.41+ (amber.800), 7.07+ (cyan.700), 7.23+ (purple.700); tints = 10% over
white, text-on-tint 5.69+.
Brand accent `#7364D8` (D-031): graphics-only token — 4.16 vs Ink, 3.91 vs Platinum (≥3:1 pass)
but <4.5:1 as text, therefore **never text**. Focus ring monochrome (platinum/ink): interaction
state is not brand voice.

## 6. Space, radius, elevation, motion

Space (4 px base): 0/4/8/12/16/24/32/48/64; purposes: inline 8/12, stack 8/12/24, gutter 16,
panel padding 16, section 32, table cell 12×8 (dense but readable, docs/03 §3.4).
Radius: control 4, card 6, overlay 8, pill 999.
Elevation: dark elevates by surface step first (canvas→panel→elevated); shadows 1/2/3 reinforce,
never signal alone; light shadows carry ink at 8/10/14% alpha.
Motion: 120/200/450 ms with `cubic-bezier(0.2, 0.8, 0.2, 1)` — the Stage 1 logo curve (docs/08
§9), so brand motion and UI motion are one system.

## 7. Proposals against previously approved work (recorded, NOT applied)

- **P-2** `docs/03` §3.1 `--text-muted #5C6B82`: 3.55:1 on canvas, 3.24 on panel, 2.89 on
  elevated — fails WCAG 4.5:1 for the 11–12 px text it serves. Semantic tier uses `#7A8CA4`.
- **P-3** `docs/03` §3.1 `--purple #9B59B6`: 4.12/3.75/3.35 as text — fails. Semantic tier uses
  `purple.300 #B07CC6` for text; the docs/03 value remains the graphic step.
- **P-4** `docs/03` §3.1 `--red #E74C3C`: 4.09:1 on elevated surfaces as text. Semantic tier uses
  `red.300 #EF8074` for text; the docs/03 value remains the graphic step.
- **P-1** (Stage 1, open): the five semantic hues are generic flat-UI defaults; restyling them
  remains a separate owner decision.
`docs/03` stands verbatim until the owner rules on P-1…P-4.

## 8. Accessibility floors (binding on Stage 3+)

4.5:1 all text including 11 px labels; 3:1 graphical objects and component boundaries; no
contrast discount for small text; colour never sole signal (docs/03 §3.3); focus visible as a
2 px monochrome outline at ≥3:1; reduced-motion honoured (Stage 1 §9 carries into UI motion).

## 9. What Stage 3 inherits

The nine dashboard screens compose from these tokens only: type roles (§2), semantic colours
per mode (§5), spacing/radius/elevation (§6), numeric policy (§4), badge construction (subtle
tint + text step + glyph + label, docs/03 §3.3/§3.4). Component tokens may be added then,
referencing tier 2 exclusively.

## 10. Honesty register for this stage

- All ratios recomputed from the token JSON by `test_tokens.py` at build time; the specimen
  renders from the generated CSS, not from hand-written values.
- Font binaries are the published OFL latin subsets (fontsource 5.3.0 tarballs from the npm
  registry), licences copied to `design/fonts/`.
- No dashboard, component, architecture or market code was written; Stage 3 remains untouched.
- The light mode is specified and tokenised but has no designed screens yet — Stage 3 designs
  dark first (docs/03), light follows from the same tokens.
