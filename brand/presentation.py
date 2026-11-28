"""Stage 1 brand identity presentation.

Regenerates ``brand/stage1-presentation.html`` — a fully self-contained page
(inline SVG, inline CSS, base64 raster evidence) so it renders identically in
the sandboxed preview iframe with no network access.

Run:  backend/.venv/bin/python brand/presentation.py
"""

from __future__ import annotations

import base64
import pathlib
import re

from geometry import (
    ACCENT,
    GRID,
    INK,
    MODULE,
    PLATINUM,
    GRAPHITE,
    DIRECTIONS,
    Line,
    Poly,
    to_svg,
    _diamond,
)
import identity

HERE = pathlib.Path(__file__).resolve().parent
PNG = HERE / "png"

# --------------------------------------------------------------------------- helpers


def inline(svg: str, *, width: str | None = None, cls: str = "") -> str:
    """Strip the XML header and make an svg embeddable in the page."""
    svg = svg.split("?>", 1)[-1].lstrip()
    svg = re.sub(r"^<svg ", '<svg class="%s" ' % cls, svg, count=1)
    if width:
        svg = re.sub(r'width="[^"]*"', f'width="{width}"', svg, count=1)
        svg = re.sub(r'height="[^"]*"', 'height="auto"', svg, count=1)
    return svg


def b64(path: pathlib.Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def mark_svg(key: str, fg: str, node: str | None = None, bg: str | None = None) -> str:
    return to_svg(DIRECTIONS[key]["build"](fg, node=node, bg=bg), bg=bg)


def lockup_svg(fg: str, bg: str | None = None, accent: bool = True) -> str:
    svg = identity.primary_lockup(fg, accent=accent)
    if bg:
        svg = identity.wrap(svg, bg)
    return svg


CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0B0F14; color: #E6EDF3;
       font: 15px/1.6 -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 48px 28px 96px; }
h1 { font-size: 30px; letter-spacing: .02em; margin: 0 0 6px; font-weight: 650; }
h2 { font-size: 20px; margin: 64px 0 4px; font-weight: 650; letter-spacing: .04em;
     text-transform: uppercase; color: #9FB0C3; }
h2 .num { color: #7364D8; margin-right: 10px; }
h3 { font-size: 16px; margin: 28px 0 6px; font-weight: 600; }
p, li { color: #B9C6D4; }
.lede { color: #8A9AAA; font-size: 14px; letter-spacing: .12em; text-transform: uppercase; }
.status { display: inline-block; border: 1px solid #7364D8; color: #A99BEA; border-radius: 999px;
          padding: 4px 14px; font-size: 12px; letter-spacing: .14em; margin: 18px 0 8px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; }
.grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.card { background: #121A24; border: 1px solid #1E2A38; border-radius: 10px; padding: 18px; }
.card.dark { background: #0B0F14; }
.card.light { background: #E6EDF3; color: #0B0F14; }
.card.light p, .card.light li { color: #33445A; }
.tile { border-radius: 8px; display: flex; align-items: center; justify-content: center;
        padding: 22px; }
.tile.on-ink { background: #0B0F14; border: 1px solid #1E2A38; }
.tile.on-light { background: #E6EDF3; }
.cap { font-size: 12px; color: #7C8DA0; letter-spacing: .08em; text-transform: uppercase;
       margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #1E2A38; color: #B9C6D4; }
th { color: #7C8DA0; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; font-size: 11.5px; }
td.ok { color: #7FD1A0; } td.no { color: #E08A8A; }
.swatch { height: 74px; border-radius: 8px; border: 1px solid #1E2A38; }
.mono { font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: 13px; }
.badge-rec { display: inline-block; background: #7364D8; color: #fff; font-size: 11px;
             letter-spacing: .1em; padding: 3px 10px; border-radius: 999px; margin-left: 8px;
             vertical-align: 2px; text-transform: uppercase; }
.badge-no { display: inline-block; background: transparent; border: 1px solid #4A5A6C;
            color: #8A9AAA; font-size: 11px; letter-spacing: .1em; padding: 3px 10px;
            border-radius: 999px; margin-left: 8px; vertical-align: 2px; text-transform: uppercase; }
.slash { position: relative; }
.slash::after { content: ""; position: absolute; inset: 0;
    background: linear-gradient(to top right, transparent 47%, #E05252 47%, #E05252 53%, transparent 53%); }
.frames { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.rule { border-left: 3px solid #7364D8; padding-left: 14px; margin: 14px 0; }
footer { margin-top: 72px; border-top: 1px solid #1E2A38; padding-top: 18px; font-size: 12.5px; color: #66788C; }
@media (max-width: 860px) { .grid2, .grid3, .grid4, .frames { grid-template-columns: 1fr 1fr; } }
"""


def section(num: int, title: str) -> str:
    return f'<h2><span class="num">{num:02d}</span>{title}</h2>'


# --------------------------------------------------------------------------- sections

def sec_cover() -> str:
    stacked = identity.stacked_lockup(PLATINUM)
    return f"""
<div class="lede">Nexus-AI &middot; Stage 1 of 23 &middot; Brand Identity</div>
<h1>Identity system: mark, wordmark, colour, construction</h1>
<div class="status">Approved 2026-11-25 &mdash; Direction B (D-030) &middot; colour system (D-031)</div>
<div class="grid2" style="margin-top:26px">
  <div class="tile on-ink">{inline(identity.wrap(stacked, INK), width="210")}</div>
  <div class="tile on-light">{inline(identity.wrap(identity.stacked_lockup(INK), PLATINUM), width="210")}</div>
</div>
<p class="cap">Stacked secondary lockup on Ink (dark surfaces) and Platinum (light surfaces).
The mark shown is Direction B, the recommended direction &mdash; all three follow below.</p>
"""


def sec_principles() -> str:
    return section(1, "Positioning &amp; principles") + """
<p>Institutional quant identities (Two Sigma, Citadel Securities, Jane Street, D.E. Shaw,
Hudson River Trading, Jump, DRW, Millennium) are wordmark-led and typographically
restrained. Credibility in this sector reads as <em>precision and restraint</em>, not iconographic
novelty. The mandate rules out generic AI logos, ordinary cryptocurrency branding and
meaningless futuristic decoration, so every element here carries a stated reason:</p>
<div class="grid3">
  <div class="card"><h3>Monochrome first</h3>
    <p>Every mark is designed and tested in one colour before accent is allowed. If a mark
    only works in colour, it does not work.</p></div>
  <div class="card"><h3>Geometry over decoration</h3>
    <p>All three directions are built from one shared motif &mdash; a diamond <em>node</em> on a
    96-unit grid &mdash; and nothing else. No gradients, no glows, no ornament.</p></div>
  <div class="card"><h3>Tiered responsive mark</h3>
    <p>A detailed lockup for large formats, a solid mark for small ones, measured at
    16&ndash;96&nbsp;px rather than assumed (&sect;7).</p></div>
</div>
<div class="rule"><p class="mono">Family motif: the node. A diamond placed where a decision is
gated &mdash; the point at which independent signals converge and are verified before anything
passes. The same motif recurs in all three directions and in the wordmark's hyphen position.</p></div>
"""


def sec_colour() -> str:
    rows = [
        ("Brass", "#B08D57", "44.6&deg;", "collides with amber (36.8&deg;)", False),
        ("Bone", "#D8C3A5", "36.9&deg;", "collides with amber", False),
        ("Slate blue", "#7C93B8", "214.6&deg;", "collides with cyan (204.1&deg;)", False),
        ("Ice", "#9FD8E8", "192.2&deg;", "collides with cyan", False),
        ("Indigo", "#5B6EE8", "231.0&deg;", "21.6&deg; from purple &mdash; under the 30&deg; rule", False),
        ("Lime", "#85BC4E", "88.0&deg;", "free hue, but 1.91:1 vs Platinum &mdash; fails 3:1", False),
        ("Violet", "#7364D8", "247.8&deg;", "34.8&deg; clear of all five semantic hues; 4.16:1 vs Ink, 3.91:1 vs Platinum", True),
    ]
    tr = "".join(
        f'<tr><td>{n}</td><td class="mono">{h}</td><td>{hue}</td><td>{why}</td>'
        f'<td class="{"ok" if ok else "no"}">{"PASS" if ok else "reject"}</td></tr>'
        for n, h, hue, why, ok in rows
    )
    return section(2, "Colour system &mdash; evidence, not taste") + f"""
<p>The product already owns five semantic hues (risk red 5.6&deg;, amber 36.8&deg;, gain green
145.4&deg;, info cyan 204.1&deg;, model purple 282.6&deg; &mdash; docs/03 &sect;3.1). A brand accent must sit
&ge;30&deg; away from all five in hue, or dashboards will read brand chrome as system state.
A sweep of the hue circle leaves exactly three free windows: 67&ndash;115&deg;, 235&ndash;252&deg;,
313&ndash;335&deg;. Candidates were then tested for WCAG contrast (&ge;3:1 for graphical elements
against both surfaces):</p>
<table><tr><th>candidate</th><th>hex</th><th>hue</th><th>verdict</th><th></th></tr>{tr}</table>
<div class="grid4" style="margin-top:22px">
  <div><div class="swatch" style="background:#0B0F14"></div>
    <p class="mono">Ink #0B0F14<br>primary dark surface</p></div>
  <div><div class="swatch" style="background:#121A24"></div>
    <p class="mono">Graphite #121A24<br>raised dark surface</p></div>
  <div><div class="swatch" style="background:#E6EDF3"></div>
    <p class="mono">Platinum #E6EDF3<br>light surface / ink on dark<br>16.27:1 vs Ink (AAA)</p></div>
  <div><div class="swatch" style="background:#7364D8"></div>
    <p class="mono">Accent #7364D8<br>the node; never a field colour<br>4.16:1 Ink &middot; 3.91:1 Platinum</p></div>
</div>
<div class="rule"><p>Usage rule: the accent appears only on the <em>node</em> and on the
wordmark's "AI" in colour lockups. Surfaces, type and data visuals stay monochrome
(Ink / Graphite / Platinum), so an accent pixel always means <em>the brand is speaking</em>,
never <em>a position is green</em>. Semantic hues from docs/03 remain the only carriers of
market meaning, and colour is never the sole signal (&sect;3.3).</p></div>
"""


def sec_directions() -> str:
    out = [section(3, "Three directions, one family")]
    verdicts = {
        "A": ("Measured, elegant at display sizes. The open gate is the idea, but the thin "
              "rays carry only ~9% ink at 16&nbsp;px &mdash; it fades below 24&nbsp;px, so it can "
              "never be the favicon.", "badge-no", "viable &mdash; secondary use"),
        "B": ("A solid letterform with the node cut into its diagonal: the gate inside the "
              "name. Strongest silhouette at every size tested (31% ink at 16&nbsp;px), "
              "monochrome-safe, and it owns a letter nobody else in the peer set owns.",
              "badge-rec", "recommended"),
        "C": ("Four shutter blades closing around the node. Honest aperture metaphor, but the "
              "blades detach into noise at 16&ndash;24&nbsp;px and the silhouette is the least "
              "distinctive of the three.", "badge-no", "not recommended"),
    }
    for key in ("A", "B", "C"):
        name = DIRECTIONS[key]["name"]
        text, badge_cls, badge = verdicts[key]
        ladder = b64(PNG / f"size_ladder_{key}.png")
        out.append(f"""
<h3>Direction {key} &mdash; {name}<span class="{badge_cls}">{badge}</span></h3>
<div class="grid2">
  <div><div class="tile on-ink">{inline(mark_svg(key, PLATINUM, node=ACCENT), width="190")}</div>
    <p class="cap">on Ink, colour</p></div>
  <div><div class="tile on-light">{inline(mark_svg(key, INK, node=INK, bg=PLATINUM), width="190")}</div>
    <p class="cap">on Platinum, one colour (the mandatory test)</p></div>
</div>
<p>{text}</p>
<img src="{ladder}" alt="size ladder {key}" style="width:100%;border-radius:8px">
<p class="cap">Measured ladder 16 / 24 / 32 / 48 / 96&nbsp;px, monochrome on Ink.</p>""")
    return "".join(out)


def sec_wordmark() -> str:
    return section(4, "Wordmark &amp; lockups") + f"""
<p>The wordmark is drawn, not typed: eight monoline glyphs on the same 8-unit discipline as
the mark (cap 48, stroke 7, tracking 10), so mark and word share one stroke language and the
identity never depends on a licensed face. The terminal "AI" takes the accent in colour
lockups and returns to the field colour in monochrome.</p>
<div class="grid2">
  <div><div class="tile on-ink">{inline(lockup_svg(PLATINUM, bg=INK), width="100%")}</div>
    <p class="cap">Primary lockup &mdash; horizontal, on Ink. Ratio 411.1 : 96 (&asymp; 4.28 : 1)</p></div>
  <div><div class="tile on-light">{inline(lockup_svg(INK, bg=PLATINUM), width="100%")}</div>
    <p class="cap">Primary lockup on Platinum (light surfaces)</p></div>
</div>
<div class="grid2" style="margin-top:18px">
  <div><div class="tile on-ink">{inline(identity.wrap(identity.stacked_lockup(PLATINUM), INK), width="170")}</div>
    <p class="cap">Stacked secondary &mdash; 96 : 128.8 (&asymp; 3 : 4), square-ish placements</p></div>
  <div><div class="tile on-ink">{inline(identity.wrap(identity.app_icon(PLATINUM, INK), INK), width="170")}</div>
    <p class="cap">Application icon &mdash; Direction B inside an iOS-squircle safe area
    (18u inset, corner radius 22u)</p></div>
</div>
"""


def sec_construction() -> str:
    grid_lines = []
    i = 0.0
    while i <= GRID:
        grid_lines.append(
            f'<line x1="{i}" y1="0" x2="{i}" y2="{GRID}" stroke="#223140" stroke-width="0.4"/>'
        )
        grid_lines.append(
            f'<line x1="0" y1="{i}" x2="{GRID}" y2="{i}" stroke="#223140" stroke-width="0.4"/>'
        )
        i += MODULE
    shapes = DIRECTIONS["B"]["build"](PLATINUM, node=ACCENT, bg=INK)
    body = "".join(
        f'<polygon points="{" ".join(f"{x},{y}" for x, y in sh.points)}" fill="{sh.fill}"/>'
        for sh in shapes if isinstance(sh, Poly)
    )
    guide = (
        '<line x1="14" y1="14" x2="82" y2="82" stroke="#7364D8" stroke-width="0.6" stroke-dasharray="3 3"/>'
        '<line x1="48" y1="0" x2="48" y2="96" stroke="#7364D8" stroke-width="0.5" stroke-dasharray="2 3"/>'
        '<line x1="0" y1="48" x2="96" y2="48" stroke="#7364D8" stroke-width="0.5" stroke-dasharray="2 3"/>'
        '<rect x="-14" y="-14" width="124" height="124" fill="none" stroke="#7FD1A0" '
        'stroke-width="0.8" stroke-dasharray="4 3"/>'
        '<text x="-14" y="-18" fill="#7FD1A0" font-size="6.5" font-family="monospace">clear space x = 14u (node width), all sides</text>'
        '<text x="0" y="105" fill="#7C8DA0" font-size="6.5" font-family="monospace">96u field &middot; 8u guide module &middot; stems 14u &middot; node 14u &middot; ring 9u</text>'
    )
    svg = (
        '<svg viewBox="-24 -30 144 146" width="430" role="img" style="background:#0B0F14;'
        'border:1px solid #1E2A38;border-radius:8px">'
        + "".join(grid_lines) + body + guide + "</svg>"
    )
    return section(5, "Construction, proportions, clear space") + f"""
<div class="grid2">
  <div>{svg}<p class="cap">Direction B on the 96-unit field with its 8-unit guide module.
  The centre lines carry the node; the diagonal runs corner to corner and is interrupted by a
  32u knockout in which the 14u node floats, leaving a 9u ring of surface &mdash; the gate.</p></div>
  <div><h3>Proportions</h3>
    <table>
      <tr><th>element</th><th>value</th></tr>
      <tr><td>mark field</td><td class="mono">96 &times; 96 u</td></tr>
      <tr><td>guide module</td><td class="mono">8 u (12 &times; 12 cells)</td></tr>
      <tr><td>stems (width / length / inset)</td><td class="mono">14 u / 68 u / 14 u</td></tr>
      <tr><td>diagonal</td><td class="mono">corner to corner, 14 u horizontal weight</td></tr>
      <tr><td>knockout / node / ring</td><td class="mono">32 u / 14 u / 9 u</td></tr>
      <tr><td>primary lockup</td><td class="mono">411.08 : 96 u</td></tr>
      <tr><td>stacked lockup</td><td class="mono">96 : 128.82 u</td></tr>
      <tr><td>wordmark cap / stroke / tracking</td><td class="mono">48 / 7 / 10 u</td></tr>
      <tr><td>clear space (every lockup)</td><td class="mono">x = 14 u = node width, all sides</td></tr>
    </table>
    <p class="cap">Nothing is freehand: every coordinate is an explicit integer in the 96-unit
    field. The 8u module governs the rhythm &mdash; centre, gate and clear space &mdash; while stem
    and node widths are optically tuned integers, stated here so any future redraw is exact.</p></div>
</div>
"""


def sec_min_sizes() -> str:
    small = "".join(
        f'<div style="text-align:center">{inline(mark_svg("B", PLATINUM, bg=INK), width=f"{s}")}'
        f'<p class="cap">{s}px</p></div>'
        for s in (16, 24, 32, 48)
    )
    lock_min = inline(lockup_svg(PLATINUM), width="96")
    lock_bad = inline(lockup_svg(PLATINUM), width="64")
    return section(6, "Minimum sizes (measured)") + f"""
<div class="grid2">
  <div class="card dark"><div style="display:flex;gap:26px;align-items:flex-end;justify-content:center">{small}</div>
    <p class="cap">Mark B, monochrome. Legible at 16&nbsp;px; the node reads from 24&nbsp;px.</p></div>
  <div class="card dark">
    <div style="margin-bottom:18px">{lock_min}<p class="cap">primary lockup minimum: 96&nbsp;px wide
    (cap height &asymp; 10.6&nbsp;px)</p></div>
    <div class="slash" style="display:inline-block">{lock_bad}</div>
    <p class="cap">below 96&nbsp;px wide: forbidden &mdash; switch to the mark alone</p></div>
</div>
<div class="rule"><p>Direction A may not be used below 24&nbsp;px and Direction C not below
32&nbsp;px (measured, &sect;3). Favicons and app icons therefore always use Direction B.
Wordmarks never appear below their minimum: at 16&ndash;48&nbsp;px only the mark or monogram
survives, which is exactly why the mark is solid.</p></div>
"""


def sec_misuse() -> str:
    def tile(label: str, svg: str, busy: bool = False) -> str:
        bg = ' style="background:repeating-linear-gradient(45deg,#3A2A1A 0 10px,#1A3A2A 10px 20px)"' if busy else ""
        return (f'<div><div class="tile on-ink slash"{bg}>{inline(svg, width="120")}</div>'
                f'<p class="cap">{label}</p></div>')

    base = mark_svg("B", PLATINUM, node=ACCENT, bg=INK)
    stretched = base.replace('viewBox="0 0 96 96"', 'viewBox="0 0 96 96"')
    stretched = stretched.replace("<svg ", '<svg ', 1)
    stretched = re.sub(
        r'(<svg[^>]*>)', r'\1<g transform="translate(48 48) scale(1.35 0.72) translate(-48 -48)">',
        stretched, count=1).replace("</svg>", "</g></svg>")
    glow = base.replace("<svg ", '<svg ', 1)
    glow = re.sub(
        r'(<svg[^>]*>)',
        r'\1<defs><filter id="gl" x="-40%" y="-40%" width="180%" height="180%">'
        r'<feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#7364D8"/></filter></defs>'
        r'<g filter="url(#gl)">', glow, count=1).replace("</svg>", "</g></svg>")
    grad = re.sub(r'fill="#E6EDF3"', 'fill="url(#gg)"', base)
    grad = re.sub(r'fill="#7364D8"', 'fill="url(#gg)"', grad)
    grad = re.sub(r'(<svg[^>]*>)',
                  r'\1<defs><linearGradient id="gg" x1="0" y1="0" x2="1" y2="1">'
                  r'<stop offset="0" stop-color="#E6EDF3"/><stop offset="1" stop-color="#7364D8"/>'
                  r'</linearGradient></defs>', grad, count=1)
    recolour = base.replace("#E6EDF3", "#E8833A").replace("#7364D8", "#39A85C")
    rotated = re.sub(r'(<svg[^>]*>)',
                     r'\1<g transform="rotate(-14 48 48)">', base, count=1).replace("</svg>", "</g></svg>")
    outlined = re.sub(r'fill="#E6EDF3"', 'fill="none" stroke="#E6EDF3" stroke-width="2"', base)
    outlined = re.sub(r'fill="#7364D8"', 'fill="none" stroke="#7364D8" stroke-width="2"', outlined)
    return section(7, "Misuse &mdash; forbidden treatments") + f"""
<div class="grid4">
  {tile("stretch or squash", stretched)}
  {tile("glows, shadows, bevels", glow)}
  {tile("gradients on the mark", grad)}
  {tile("off-system recolouring", recolour)}
  {tile("rotation", rotated)}
  {tile("outline / hollow forms", outlined)}
  {tile("busy or photographic ground", base, busy=True)}
  {tile("recolouring the node to a semantic hue", base.replace("#7364D8", "#2FBF71"))}
</div>
<p class="cap">The last tile is the dangerous one: a green node reads as profit, a red node as
loss. The node is brand violet or the field colour &mdash; never a state colour.</p>
"""


def sec_animation() -> str:
    shapes = DIRECTIONS["B"]["build"](PLATINUM, node=ACCENT, bg=INK)
    body = "".join(
        f'<polygon points="{" ".join(f"{x},{y}" for x, y in sh.points)}" fill="{sh.fill}"/>'
        for sh in shapes if isinstance(sh, Poly)
    )
    node_only = f'<polygon points="{" ".join(f"{x},{y}" for x, y in _diamond(48, 48, 7.0))}" fill="{ACCENT}"/>'

    clips = {
        "f2": '<rect x="14" y="40" width="14" height="16"/><rect x="68" y="40" width="14" height="16"/>',
        "f3": ('<rect x="14" y="14" width="14" height="68"/><rect x="68" y="14" width="14" height="68"/>'
               '<rect x="10" y="4" width="46" height="24" transform="rotate(51.5 21 14)"/>'),
    }

    def tile(inner: str, clip: str | None, fid: str, label: str) -> str:
        if clip:
            svg = (f'<svg viewBox="0 0 96 96" width="100%" role="img" style="background:#0B0F14;'
                   f'border:1px solid #1E2A38;border-radius:8px"><defs><clipPath id="{fid}">'
                   f'{clip}</clipPath></defs><g clip-path="url(#{fid})">{inner}</g></svg>')
        else:
            svg = (f'<svg viewBox="0 0 96 96" width="100%" role="img" style="background:#0B0F14;'
                   f'border:1px solid #1E2A38;border-radius:8px">{inner}</svg>')
        return f'<div><div style="padding:0">{svg}</div><p class="cap">{label}</p></div>'

    f1 = tile(node_only, None, "f1", "0&ndash;200 ms &middot; node scales in, ease-out")
    f2 = tile(body, clips["f2"], "f2", "200&ndash;450 ms &middot; stems grow out of the node")
    f3 = tile(body, clips["f3"], "f3", "450&ndash;700 ms &middot; diagonal draws toward the gate")
    f4 = tile(body, None, "f4", "700 ms &middot; stops one ring short of the node")
    f5 = (f'<div><div style="padding:0">{inline(identity.wrap(identity.primary_lockup(PLATINUM), INK), width="100%")}</div>'
          f'<p class="cap">700&ndash;1200 ms &middot; wordmark tracks in, opacity 0&rarr;1</p></div>')
    return section(8, "Logo animation concept &mdash; &ldquo;the gate opens&rdquo;") + f"""
<p>One motion idea for all directions: <em>the node appears first, then the structure reveals
out from it</em> &mdash; a decision verified, then executed. For Direction B, expressed as mask
reveals over the finished mark (so motion never redraws geometry):</p>
<div class="frames">{f1}{f2}{f3}{f4}{f5}</div>
<div class="rule"><p>Spec: 1.2&nbsp;s total, cubic-bezier(0.2, 0.8, 0.2, 1), no loops, no glow,
no colour change. <code>prefers-reduced-motion</code> renders the final frame statically. The
same beat sheet maps onto A (rays retract from the node) and C (blades close onto it) if either
is chosen. Motion stays a concept at Stage 1; it becomes buildable assets in Stage 2.</p></div>
"""


def sec_governance() -> str:
    assets = sorted(p.name for p in (HERE / "svg").glob("*.svg"))
    return section(9, "Deliverables, regeneration, status") + f"""
<div class="grid2">
  <div><h3>Assets on disk</h3>
    <p class="mono" style="line-height:1.9">brand/svg/ &mdash; {len(assets)} vector masters:<br>
    {", ".join(a.replace(".svg", "") for a in assets)}<br>
    brand/svg/archive/ &mdash; retired explorations A and C (D-030)<br>
    brand/png/ &mdash; measured evidence renders (ladders, lockups)<br>
    brand/geometry.py &middot; brand/identity.py &middot; brand/raster.py &mdash; the source of
    truth; every asset regenerates with
    <code>identity.write_assets()</code></p></div>
  <div><h3>Register &amp; decisions</h3>
    <p><strong>Decided 2026-11-25.</strong> D-030: the mark is Direction B; Directions A and C
    are archived explorations (<span class="mono">brand/svg/archive/</span>, not for use).
    D-031: colour system as &sect;2 &mdash; monochrome Ink / Graphite / Platinum with accent
    #7364D8 on the node and the wordmark's "AI" only.</p>
    <p>Stage 2 (typography &amp; design system) inherits both as binding constraints. Nothing in
    the backend was touched during Stage 1.</p></div>
</div>
<footer>Nexus-AI Stage 1 &middot; generated from brand/geometry.py + brand/identity.py &middot;
all colour claims computed (hue distance + WCAG 2.1 contrast), all size claims measured by
rasterisation. No simulated or illustrative evidence on this page.</footer>
"""


def main() -> pathlib.Path:
    body = "".join(
        [sec_cover(), sec_principles(), sec_colour(), sec_directions(), sec_wordmark(),
         sec_construction(), sec_min_sizes(), sec_misuse(), sec_animation(), sec_governance()]
    )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Nexus-AI · Stage 1 Brand Identity</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'>{body}</div></body></html>"
    )
    out = HERE / "stage1-presentation.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
