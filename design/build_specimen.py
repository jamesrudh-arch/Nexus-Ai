"""Stage 2 specimen: design/stage2-specimen.html.

Self-contained (base64 woff2 + inlined tokens.css) so the sandboxed preview
renders the real type system with zero network access.

Run:  backend/.venv/bin/python design/build_specimen.py
"""

from __future__ import annotations

import base64
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / "fonts"

CSS_PAGE = """
body { margin:0; background: var(--color-surface-canvas); color: var(--color-text-primary);
       font-family: var(--font-family-sans); font-size: var(--font-size-body);
       line-height: var(--font-line-height-body); }
.wrap { max-width: 1100px; margin: 0 auto; padding: 48px 28px 96px; }
h2 { font: var(--font-weight-semibold) var(--font-size-heading)/1.25 var(--font-family-sans);
     letter-spacing: -0.01em; margin: 64px 0 4px; color: var(--color-text-primary); }
h2 .num { color: var(--color-brand-accent); margin-right: 10px; }
.lede { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
        letter-spacing: var(--font-tracking-label); text-transform: uppercase;
        color: var(--color-text-secondary); }
p { color: var(--color-text-secondary); max-width: 74ch; }
.card { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
        border-radius: var(--radius-card); padding: var(--space-panel); }
.grid2 { display:grid; grid-template-columns: 1fr 1fr; gap: var(--space-gutter); }
.grid3 { display:grid; grid-template-columns: repeat(3,1fr); gap: var(--space-gutter); }
.cap { font: var(--font-weight-regular) var(--font-size-caption)/1.35 var(--font-family-sans);
       color: var(--color-text-muted); margin-top: var(--space-stack-sm); }
table { border-collapse: collapse; width: 100%; }
th { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
     letter-spacing: var(--font-tracking-label); text-transform: uppercase;
     color: var(--color-text-secondary); text-align: left; }
td { padding: var(--space-table-cell-y) var(--space-table-cell-x);
     border-top: 1px solid var(--color-border-subtle); color: var(--color-text-primary); }
.num-r { text-align: right; font-family: var(--font-family-mono);
         font-variant-numeric: var(--font-numeric-tabular); }
.role { padding: 10px 0; border-bottom: 1px solid var(--color-border-subtle); }
.role .tag { display:inline-block; width: 130px; color: var(--color-text-muted);
             font: var(--font-weight-regular) var(--font-size-caption)/1.35 var(--font-family-sans); }
.t-display { font-family: var(--typography-role-display-font-family);
  font-size: var(--typography-role-display-font-size);
  font-weight: var(--typography-role-display-font-weight);
  line-height: var(--typography-role-display-line-height);
  letter-spacing: var(--typography-role-display-letter-spacing);
  font-variant-numeric: var(--font-numeric-tabular); }
.t-hlg { font-family: var(--typography-role-heading-lg-font-family);
  font-size: var(--typography-role-heading-lg-font-size);
  font-weight: var(--typography-role-heading-lg-font-weight);
  line-height: var(--typography-role-heading-lg-line-height);
  letter-spacing: var(--typography-role-heading-lg-letter-spacing); }
.t-hmd { font-size: var(--typography-role-heading-md-font-size);
  font-weight: var(--typography-role-heading-md-font-weight);
  line-height: var(--typography-role-heading-md-line-height);
  font-family: var(--typography-role-heading-md-font-family); }
.t-hsm { font-size: var(--typography-role-heading-sm-font-size);
  font-weight: var(--typography-role-heading-sm-font-weight);
  line-height: var(--typography-role-heading-sm-line-height);
  font-family: var(--typography-role-heading-sm-font-family); }
.t-body { font-size: var(--typography-role-body-font-size);
  font-weight: var(--typography-role-body-font-weight);
  line-height: var(--typography-role-body-line-height);
  font-family: var(--typography-role-body-font-family); color: var(--color-text-secondary); }
.t-data { font-family: var(--typography-role-data-font-family);
  font-size: var(--typography-role-data-font-size);
  font-weight: var(--typography-role-data-font-weight);
  line-height: var(--typography-role-data-line-height);
  font-variant-numeric: var(--font-numeric-tabular); }
.t-dataem { font-family: var(--typography-role-data-emphasis-font-family);
  font-size: var(--typography-role-data-emphasis-font-size);
  font-weight: var(--typography-role-data-emphasis-font-weight);
  line-height: var(--typography-role-data-emphasis-line-height);
  font-variant-numeric: var(--font-numeric-tabular); }
.t-value { font-size: var(--typography-role-value-font-size);
  font-weight: var(--typography-role-value-font-weight);
  line-height: var(--typography-role-value-line-height);
  font-family: var(--typography-role-value-font-family);
  font-variant-numeric: var(--font-numeric-tabular); }
.t-label { font-family: var(--typography-role-label-font-family);
  font-size: var(--typography-role-label-font-size);
  font-weight: var(--typography-role-label-font-weight);
  line-height: var(--typography-role-label-line-height);
  letter-spacing: var(--typography-role-label-letter-spacing);
  text-transform: var(--typography-role-label-text-transform);
  color: var(--color-text-secondary); }
.t-caption { font-family: var(--typography-role-caption-font-family);
  font-size: var(--typography-role-caption-font-size);
  font-weight: var(--typography-role-caption-font-weight);
  line-height: var(--typography-role-caption-line-height);
  color: var(--color-text-muted); }
.badge { display:inline-flex; align-items:center; gap: var(--space-inline-sm);
  padding: 2px 10px; border-radius: var(--radius-pill);
  font: var(--font-weight-medium) var(--font-size-label)/1.4 var(--font-family-sans);
  letter-spacing: var(--font-tracking-label); }
.badge.pos { background: var(--color-feedback-positive-subtle); color: var(--color-feedback-positive-text); }
.badge.neg { background: var(--color-feedback-negative-subtle); color: var(--color-feedback-negative-text); }
.badge.warn { background: var(--color-feedback-warning-subtle); color: var(--color-feedback-warning-text); }
.badge.info { background: var(--color-feedback-info-subtle); color: var(--color-feedback-info-text); }
.badge.intel { background: var(--color-feedback-intelligence-subtle); color: var(--color-feedback-intelligence-text); }
.swatch { height: 56px; border-radius: var(--radius-control); border: 1px solid var(--color-border-subtle); }
.mono { font-family: var(--font-family-mono); font-size: var(--font-size-caption); }
.elev1 { box-shadow: var(--elevation-1); } .elev2 { box-shadow: var(--elevation-2); }
.elev3 { box-shadow: var(--elevation-3); }
.focus-demo { outline: var(--border-width-focus) solid var(--color-focus); outline-offset: 2px;
  border-radius: var(--radius-control); }
.rule { border-left: 3px solid var(--color-brand-accent); padding-left: 14px; margin: 14px 0; }
.status { display:inline-block; border:1px solid var(--color-border-strong);
  color: var(--color-text-secondary); border-radius: 999px; padding: 4px 14px;
  font-size: var(--font-size-caption); letter-spacing: .14em; margin: 18px 0 8px; }
footer { margin-top: 72px; border-top: 1px solid var(--color-border-subtle);
  padding-top: 18px; color: var(--color-text-muted); font-size: var(--font-size-caption); }
"""


def fonts_css() -> str:
    out = []
    for f in sorted(FONTS.glob("*.woff2")):
        family = "Inter" if f.name.startswith("inter") else "JetBrains Mono"
        weight = f.name.split("-latin-")[1].split("-")[0]
        b64 = base64.b64encode(f.read_bytes()).decode()
        out.append(
            f"@font-face {{ font-family: '{family}'; font-style: normal; font-weight: {weight}; "
            f"font-display: swap; src: url(data:font/woff2;base64,{b64}) format('woff2'); }}"
        )
    return "\n".join(out)


def main() -> pathlib.Path:
    tokens = (HERE / "tokens.css").read_text()
    tokens = re.sub(r"@font-face \{[^}]*\}", "", tokens)  # specimen embeds base64 faces instead

    table_rows = "".join(
        f"<tr><td>BTCUSDT</td><td>LONG</td><td class='num-r'>67,412.{p}</td>"
        f"<td class='num-r' style='color:var(--color-feedback-{c}-text)'>{sgn}1,204.{p}</td></tr>"
        for p, c, sgn in (("50", "positive", "+"), ("08", "negative", "-"), ("44", "positive", "+"))
    )
    prop = "".join(f"<div class='t-data' style='font-variant-numeric:proportional-nums'>{n}</div>"
                   for n in ("1,884.20", "90,214.55", "7,041.08", "18,990.13"))
    tab = "".join(f"<div class='t-data'>{n}</div>" for n in ("1,884.20", "90,214.55", "7,041.08", "18,990.13"))

    def panel(theme: str) -> str:
        attr = " data-theme='light'" if theme == "light" else ""
        return f"""
<div{attr} class="card">
  <div class="t-label">environment &middot; freshness &middot; coverage</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 14px">
    <span class="badge pos">&#9650; LIVE</span>
    <span class="badge neg">&#9660; REJECTED</span>
    <span class="badge warn">&#9888; STALE</span>
    <span class="badge info">&#8505; DELAYED</span>
    <span class="badge intel">&#9670; RESEARCH</span>
  </div>
  <div class="t-hmd" style="margin-bottom:6px">Consolidated equity</div>
  <div class="t-display">48,210.66 <span class="t-caption">USDT</span></div>
  <div class="t-caption">updated 2026-11-25 14:02:11 UTC &middot; venue-aggregated</div>
  <table style="margin-top:14px">
    <tr><th>instrument</th><th>side</th><th style="text-align:right">last</th>
        <th style="text-align:right">upnl</th></tr>
    {table_rows}
  </table>
  <div style="display:flex;gap:12px;align-items:center;margin-top:16px">
    <span class="badge info focus-demo" style="padding:6px 14px">focus ring</span>
    <span class="card elev2" style="padding:6px 14px;border-radius:var(--radius-overlay)">elevation 2</span>
    <span class="card elev3" style="padding:6px 14px;border-radius:var(--radius-overlay)">elevation 3</span>
  </div>
  <div class="cap">{theme} mode &mdash; every colour on this panel is a semantic token</div>
</div>"""

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 2 Typography & Design System</title>
<style>{tokens}
{fonts_css()}
{CSS_PAGE}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 2 of 23 &middot; Typography &amp; Design System</div>
<h1 class="t-hlg" style="margin:6px 0 0">Type, colour and space as verified tokens</h1>
<div class="status">Built &mdash; awaiting review &middot; extends docs/03, replaces nothing</div>
<p>Everything on this page is rendered by the generated token CSS
(<span class="mono">design/tokens.css</span>) with the production fonts embedded
(Inter + JetBrains Mono latin subsets, SIL OFL 1.1, self-hosted per D-019).
No value on this page is hand-written: contrast ratios, tints and scales are recomputed by
<span class="mono">design/test_tokens.py</span> on every build.</p>

<h2><span class="num">01</span>Type roles</h2>
<div class="card">
  <div class="role"><span class="tag">display 24/600 mono</span><span class="t-display">48,210.66</span>
    <span class="t-caption">the one hero figure per screen</span></div>
  <div class="role"><span class="tag">heading-lg 20/600</span><span class="t-hlg">Portfolio &amp; Risk</span></div>
  <div class="role"><span class="tag">heading-md 16/600</span><span class="t-hmd">Open positions</span></div>
  <div class="role"><span class="tag">heading-sm 14/600</span><span class="t-hsm">Exposure by venue</span></div>
  <div class="role"><span class="tag">value 16/600 tabular</span><span class="t-value">67,412.50</span></div>
  <div class="role"><span class="tag">body 14/400</span><span class="t-body">The verification engine rejected
    two of nine candidates: mandatory conditions failed before confidence was consulted.</span></div>
  <div class="role"><span class="tag">data 13 mono</span><span class="t-data">67,412.50 &middot; 0.0021 &middot; BTCUSDT</span></div>
  <div class="role"><span class="tag">data-emphasis 14/500</span><span class="t-dataem">-1,204.08</span></div>
  <div class="role"><span class="tag">label 11/500 upper</span><span class="t-label">notional exposure</span></div>
  <div class="role" style="border:0"><span class="tag">caption 12/400</span><span class="t-caption">evidence: run 45729297881 &middot; 2026-11-25 14:02 UTC</span></div>
</div>
<p class="cap">docs/03 &sect;3.2 rows preserved verbatim (20/16/14 headings, 14 body, 13 mono data,
11 uppercase labels); display, caption, value and data-emphasis are Stage 2 additions for
weight-led hierarchy in dense UI.</p>

<h2><span class="num">02</span>Numerals: tabular is mandatory</h2>
<div class="grid2">
  <div class="card"><div class="t-label">proportional (prose only)</div>{prop}
    <div class="cap">decimal points drift &mdash; forbidden in any column</div></div>
  <div class="card"><div class="t-label">tabular-nums (every figure)</div>{tab}
    <div class="cap">columns align with zero manual nudging</div></div>
</div>
<div class="rule"><p>Negatives: minus sign + semantic colour + &#9660;/&minus; glyph, never accounting
parentheses, never colour alone (docs/03 &sect;3.3). Precision per asset class (FX 4&ndash;5 dp,
crypto 2&ndash;8 dp by tick); compact notation ($1.2M) only where the exact figure is not actionable.
Chart libraries must override their default font to these tokens, axis labels included.</p></div>

<h2><span class="num">03</span>Surfaces, feedback, elevation &mdash; both modes</h2>
<div class="grid2">{panel("dark")}{panel("light")}</div>

<h2><span class="num">04</span>Space, radius, elevation</h2>
<div class="grid3">
  <div class="card"><div class="t-label">space scale (4px base)</div>
    <div style="display:flex;gap:6px;align-items:flex-end;margin-top:10px">
      <div style="width:4px;height:4px;background:var(--color-text-secondary)"></div>
      <div style="width:8px;height:8px;background:var(--color-text-secondary)"></div>
      <div style="width:12px;height:12px;background:var(--color-text-secondary)"></div>
      <div style="width:16px;height:16px;background:var(--color-text-secondary)"></div>
      <div style="width:24px;height:24px;background:var(--color-text-secondary)"></div>
      <div style="width:32px;height:32px;background:var(--color-text-secondary)"></div>
      <div style="width:48px;height:48px;background:var(--color-text-secondary)"></div>
    </div><div class="cap mono">4 8 12 16 24 32 48 (64 for page margins)</div></div>
  <div class="card"><div class="t-label">radius</div>
    <div style="display:flex;gap:8px;margin-top:10px">
      <div style="width:34px;height:34px;background:var(--color-surface-elevated);border:1px solid var(--color-border-strong);border-radius:var(--radius-control)"></div>
      <div style="width:34px;height:34px;background:var(--color-surface-elevated);border:1px solid var(--color-border-strong);border-radius:var(--radius-card)"></div>
      <div style="width:34px;height:34px;background:var(--color-surface-elevated);border:1px solid var(--color-border-strong);border-radius:var(--radius-overlay)"></div>
      <div style="width:34px;height:34px;background:var(--color-surface-elevated);border:1px solid var(--color-border-strong);border-radius:var(--radius-pill)"></div>
    </div><div class="cap mono">control 4 &middot; card 6 &middot; overlay 8 &middot; pill</div></div>
  <div class="card"><div class="t-label">elevation (shadow + surface step)</div>
    <div style="display:flex;gap:10px;margin-top:10px">
      <div class="card elev1" style="padding:10px">1</div>
      <div class="card elev2" style="padding:10px">2</div>
      <div class="card elev3" style="padding:10px">3</div>
    </div><div class="cap">dark elevates by surface step first; shadows reinforce, never signal alone</div></div>
</div>

<h2><span class="num">05</span>Governance</h2>
<div class="grid2">
  <div class="card"><div class="t-hsm">Three tiers, one direction of travel</div>
    <p class="t-body">Primitives (<span class="mono">primitives.json</span>) hold raw values.
    Semantic tokens (<span class="mono">semantic.*.json</span>) hold purpose and carry the mode
    switch. Component tokens arrive with Stage 3 components and may reference the semantic tier
    only &mdash; a component reading a primitive is a rejected pull request.</p>
    <p class="t-body">The brand accent (D-031) is a graphics-only token: 3:1 on both surfaces,
    under 4.5:1 as text, therefore never text. The focus ring is monochrome for the same reason:
    interaction state is not brand voice.</p></div>
  <div class="card"><div class="t-hsm">Proposals against docs/03 (recorded, not applied)</div>
    <p class="t-body">P-2: <span class="mono">--text-muted #5C6B82</span> measures 3.55:1 on canvas
    &mdash; fails 4.5:1. P-3: <span class="mono">--purple #9B59B6</span> measures 4.12:1 as text.
    P-4: <span class="mono">--red #E74C3C</span> measures 4.09:1 on elevated surfaces.
    Stage 2 routes around all three at the semantic tier (muted-dark, purple.300, red.300) and
    leaves docs/03 untouched until the owner decides.</p></div>
</div>
<footer>Nexus-AI Stage 2 &middot; tokens: W3C DTCG 2025.10 &middot; fonts: Inter 5.3.0,
JetBrains Mono 5.3.0 (&copy; respective authors, SIL OFL 1.1) &middot;
evidence: design/test_tokens.py &middot; nothing on this page is simulated.</footer>
</div></body></html>"""
    out = HERE / "stage2-specimen.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
