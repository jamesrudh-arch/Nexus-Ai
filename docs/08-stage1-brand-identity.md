# 08 — Stage 1: Brand Identity — Guidelines & Evidence

Status: **APPROVED** 2026-11-25 — decisions D-030 (mark = Direction B) and D-031 (colour
system), recorded in `docs/07-production-register.md`. This document is now binding.
Review artefact: `brand/stage1-presentation.html` (self-contained; served or opened directly).
Source of truth for every asset: `brand/geometry.py`, `brand/identity.py`; raster evidence via
`brand/raster.py`. Regenerate all vector masters with `identity.write_assets(Path("brand/svg"))`.

This document is the permanent brand guideline. Stage 2 (Typography & Design System) extends
it; it may not contradict it. Nothing here overrides `docs/03-product-ux-bible.md`; where the
two touch (colour semantics, contrast floors), docs/03 remains authoritative.

---

## 1. Positioning

Institutional quant and trading-technology identities (Two Sigma, Citadel Securities,
Jane Street, D.E. Shaw, Hudson River Trading, Jump, DRW, Millennium) are wordmark-led and
typographically restrained. The mandate forbids generic AI logos, ordinary cryptocurrency
branding and meaningless futuristic decoration. Three principles follow, and every asset is
tested against them:

1. **Monochrome first.** Every mark is designed and verified in a single colour before any
   accent is permitted. A mark that only works in colour does not work.
2. **Geometry over decoration.** One shared motif — the diamond *node* — and explicit integer
   coordinates in a 96-unit field. No gradients, glows, shadows or ornament anywhere.
3. **Tiered responsive mark.** Detailed lockups for large formats; a solid mark for small
   ones; minima measured by rasterisation, not assumed (§7).

**The motif.** A diamond node placed where a decision is gated: the point at which independent
signals converge and must be verified before anything passes. It appears in all three
directions and is the hyphen-position idea of the wordmark. It is meaning, not decoration.

## 2. Colour system (computed, not tasted)

Docs/03 §3.1 owns five semantic hues: risk red 5.6°, amber 36.8°, gain green 145.4°,
info cyan 204.1°, model purple 282.6°. A brand accent must sit ≥30° from all five in hue or
dashboard chrome becomes indistinguishable from system state. A sweep of the hue circle at the
required contrast leaves exactly three free windows: **67–115°, 235–252°, 313–335°**.

| candidate | hex | hue | nearest semantic gap | vs Ink | vs Platinum | verdict |
|---|---|---|---|---|---|---|
| Brass | #B08D57 | 44.6° | 7.8° (amber) | — | — | reject: hue collision |
| Bone | #D8C3A5 | 36.9° | 0.1° (amber) | — | — | reject: hue collision |
| Slate blue | #7C93B8 | 214.6° | 10.5° (cyan) | — | — | reject: hue collision |
| Ice | #9FD8E8 | 192.2° | 11.9° (cyan) | — | — | reject: hue collision |
| Indigo | #5B6EE8 | 231.0° | 21.6° (purple window edge) | — | — | reject: <30° rule |
| Lime | #85BC4E | 88.0° | free | — | 1.91:1 | reject: fails WCAG 3:1 |
| **Violet** | **#7364D8** | **247.8°** | **34.8°** | **4.16:1** | **3.91:1** | **adopted** |

Surfaces and neutrals:

| token | hex | role | evidence |
|---|---|---|---|
| Ink | #0B0F14 | primary dark surface | Platinum-on-Ink 16.27:1 (AAA) |
| Graphite | #121A24 | raised dark surface | vs Platinum 14.82:1; never paired with Ink for text (1.10:1) |
| Platinum | #E6EDF3 | light surface; field colour on dark | AAA on both darks |
| Accent | #7364D8 | the node; "AI" in colour lockups only | ≥3:1 on both surfaces (WCAG 1.4.11 graphical) |

**Usage rules.**
- The accent appears only on the node and on the wordmark's terminal "AI" in colour lockups.
  Surfaces, type and data visuals stay monochrome. An accent pixel always means *the brand is
  speaking*, never *a position is green*.
- Semantic hues (docs/03) remain the only carriers of market meaning; colour is never the sole
  signal (docs/03 §3.3). The node must never take a semantic hue.
- Contrast floors: ≥4.5:1 text, ≥3:1 graphical elements (WCAG 2.1). Ink/Graphite are never a
  text pair.
- No gradients on any brand element, in any medium.

## 3. The mark — Direction B adopted (D-030)

**The system mark is Direction B — Nexus N.** Directions A and C are archived
explorations kept in `brand/geometry.py` for provenance; their masters live in
`brand/svg/archive/` and must not be used as system assets. The evidence that decided
it is preserved below, one family, three directions:

All directions share the 96-unit field and the node motif. Masters are locked to their
approved surface (`mark-<dir>-on-ink|on-platinum|mono-on-ink|mono-on-platinum.svg`) because
Direction B's knockout is a surface-coloured counterform.

- **A — Convergence.** Four diagonal rays stopping one module short of a diamond node; the gap
  is the gate. Elegant at display size; carries ~9% ink at 16 px, so it fades below 24 px.
  Viable for secondary/large-format use only.
- **B — Nexus N (recommended).** The letter drawn solid, its diagonal interrupted by a 32u
  knockout holding a 14u node — the gate inside the name. Strongest silhouette at every size
  measured (31% ink at 16 px), monochrome-safe on both surfaces, and it owns a letterform no
  peer in the sector uses as a mark.
- **C — Aperture.** Four shutter blades in rotational symmetry around the node; an iris that
  admits only what is verified. Honest metaphor, weakest silhouette: blades detach into noise
  at 16–24 px (16% ink at 16 px). Not recommended.

Evidence renders: `brand/png/size_ladder_{A,B,C}.png` (16/24/32/48/96 px, monochrome on Ink),
`brand/png/direction_*_400.png`. Lit-pixel fractions at 16 px: A 0.094, B 0.312, C 0.160.

## 4. Wordmark and lockups

The wordmark is **drawn, not typed**: eight monoline glyphs (N E X U S - A I) on the same
stroke discipline as the mark — cap 48u, stroke 7u, tracking 10u — so the identity never
depends on a licensed or installed face (the production font stack is decided in Stage 2 and
will set UI type, not the logo). The terminal "AI" takes the accent in colour lockups and
returns to the field colour in monochrome.

| lockup | ratio | use |
|---|---|---|
| primary, horizontal (`lockup-primary-*`) | 411.08 : 96 | headers, covers, wide placements |
| stacked secondary (`lockup-stacked-*`) | 96 : 128.82 | square-ish placements, social |
| mark alone | 96 : 96 | everything small; favicons; app icon |
| app icon (`app-icon-*`) | 96 : 96 inside iOS squircle safe area (18u inset, r=22u) | installs |

Light and dark: every lockup ships on Ink and on Platinum. On light surfaces the field colour
is Ink; the accent is unchanged (3.91:1 vs Platinum). Monochrome masters replace the accent
with the field colour.

## 5. Construction and proportions

96-unit field; 8u guide module (12 × 12). Direction B: stems 14u wide, 68u long, inset 14u;
diagonal corner-to-corner at 14u horizontal weight; knockout diamond 32u; node diamond 14u;
visible ring (the gate) 9u. Wordmark cap/stroke/tracking 48/7/10u. Every coordinate is an
explicit integer in the field; the module governs rhythm (centre, gate, clear space) while
stem and node widths are optically tuned integers recorded in `geometry.py` so any redraw is
exact. Diagram: `brand/stage1-presentation.html` §5.

**Clear space:** x = 14u (node width) on all sides of any lockup or mark; nothing enters it —
no type, rules, UI chrome or image edges.

## 6. Backgrounds

Approved grounds: Ink, Graphite, Platinum, and monochrome photography-free fields at ≥16.27:1
or ≤ the Platinum value in practice — i.e. only the three neutrals. The mark never sits on
semantic hues, gradients, patterns, photography or busy data visuals. On any unapproved ground
the mark goes inside a neutral plate with full clear space.

## 7. Minimum sizes (measured)

| element | minimum | evidence |
|---|---|---|
| the mark (B), monochrome | 16 px | ladder: letterform legible, node reads from 24 px |
| archive A (not for use) | 24 px | 9.4% ink at 16 px — fades |
| archive C (not for use) | 32 px | blades fragment below |
| primary lockup | 96 px wide (cap ≈ 10.6 px) | below this the wordmark cap drops under legible size |
| stacked lockup | 64 px wide | same cap rule |
| favicons / app icons | mark B only | wordmarks never survive 16–48 px |

Below any minimum, step down the tier: lockup → mark → (nothing). Never scale a lockup to fit
a slot below its minimum.

## 8. Misuse (forbidden)

Stretching or squashing; rotation; glows, shadows, bevels, outlines; gradients on any brand
element; off-system recolouring; recolouring the node to a semantic hue (a green node reads as
profit, a red node as loss); placement on busy or photographic grounds; re-drawing or
"correcting" the glyphs; adding effects in motion. The presentation §7 shows each with a slash.

## 9. Motion concept — "the gate opens"

The node appears first (0–200 ms, scale-in, ease-out); stems reveal out from it (200–450 ms);
the diagonal draws toward the gate and stops one ring short (450–700 ms); the wordmark tracks
in at 96% → 100% width with opacity 0 → 1 (700–1200 ms). 1.2 s total, cubic-bezier(0.2, 0.8,
0.2, 1), no loops, no glow, no colour change; `prefers-reduced-motion` renders the final frame
statically. Implemented as mask reveals over finished geometry so motion never redraws the
mark. Keyframe strip: presentation §8. Motion becomes buildable assets in Stage 2.

## 10. Decisions (resolved)

1. **Mark direction — D-030:** Direction B, as recommended. 2026-11-25.
2. **Colour system — D-031:** Ink / Graphite / Platinum monochrome with accent #7364D8, as
   evidenced in §2. 2026-11-25.

Both recorded in `docs/07-production-register.md`. Stage 2 (Typography & Design System) inherits
these as binding constraints: the type and token system must draw its neutrals from §2, keep the
accent out of data visuals, and honour the contrast floors restated here.

## 11. Honesty register for this stage

- All colour numbers computed (hue distance + WCAG 2.1 relative contrast), script-reproducible.
- All size claims measured by rasterising the actual geometry at the stated pixel sizes.
- SVG masters validated by an independent spec parser (svgelements) in addition to the
  in-house renderer; no asset is hand-edited after generation.
- No market data, performance claim, integration or test result is asserted anywhere in this
  stage. The animation is a concept (static keyframes), explicitly not a built asset.
