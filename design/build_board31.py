"""Stage 3.1 board: design/stage3-1-layout-ia.html — shell, IA and screen map.

Self-contained like the Stage 2 specimen (inlined tokens.css + base64 fonts).

Run:  backend/.venv/bin/python design/build_board31.py
"""

from __future__ import annotations

import pathlib
import re

from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent

CSS = """
body { margin:0; background: var(--color-surface-canvas); color: var(--color-text-primary);
  font-family: var(--font-family-sans); font-size: var(--font-size-body);
  line-height: var(--font-line-height-body); }
.wrap { max-width: 1180px; margin: 0 auto; padding: 44px 26px 96px; }
h2 { font-size: var(--font-size-heading); font-weight: var(--font-weight-semibold);
  line-height: var(--font-line-height-heading); letter-spacing: -0.01em; margin: 60px 0 4px; }
h2 .num { color: var(--color-brand-accent); margin-right: 10px; }
.lede { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
  letter-spacing: var(--font-tracking-label); text-transform: uppercase;
  color: var(--color-text-secondary); }
p { color: var(--color-text-secondary); max-width: 78ch; }
.cap { font-size: var(--font-size-caption); line-height: var(--font-line-height-caption);
  color: var(--color-text-muted); }
.mono { font-family: var(--font-family-mono); font-size: var(--font-size-caption); }
.card { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-card); padding: var(--space-panel); }
table { border-collapse: collapse; width: 100%; font-size: var(--font-size-data); }
th { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
  letter-spacing: var(--font-tracking-label); text-transform: uppercase;
  color: var(--color-text-secondary); text-align: left; }
td { padding: var(--space-table-cell-y) var(--space-table-cell-x);
  border-top: 1px solid var(--color-border-subtle); color: var(--color-text-secondary);
  vertical-align: top; }
td b { color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
.status { display:inline-block; border:1px solid var(--color-border-strong);
  color: var(--color-text-secondary); border-radius: 999px; padding: 4px 14px;
  font-size: var(--font-size-caption); letter-spacing: .14em; margin: 16px 0 8px; }

/* ---- the shell mock ---- */
.shell { display: grid; grid-template-columns: 208px 1fr 264px;
  grid-template-rows: 40px 1fr; grid-template-areas: "top top top" "rail main ctx";
  height: 560px; border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-overlay); overflow: hidden; background: var(--color-surface-canvas); }
.top { grid-area: top; display: flex; align-items: center; gap: 10px; padding: 0 12px;
  background: var(--color-surface-panel); border-bottom: 1px solid var(--color-border-subtle); }
.rail { grid-area: rail; background: var(--color-surface-panel);
  border-right: 1px solid var(--color-border-subtle); padding: 10px 8px; overflow: hidden; }
.ctx { grid-area: ctx; background: var(--color-surface-panel);
  border-left: 1px solid var(--color-border-subtle); padding: 12px; overflow: hidden; }
.main { grid-area: main; padding: var(--space-gutter); display: grid; gap: var(--space-gutter);
  grid-template-columns: repeat(12, 1fr); grid-auto-rows: min-content; overflow: hidden; }
.region { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-card); padding: 12px; position: relative; }
.region .job { color: var(--color-text-muted); font-size: var(--font-size-caption);
  line-height: 1.35; margin-top: 4px; }
.region .prio { position: absolute; top: 10px; right: 10px; color: var(--color-text-muted);
  font: var(--font-weight-medium) 10px/1 var(--font-family-mono); letter-spacing: .08em; }
.navgrp { margin: 10px 6px 4px; }
.navitem { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: var(--radius-control); color: var(--color-text-secondary);
  font-size: var(--font-size-data); }
.navitem svg { flex: 0 0 auto; }
.navitem.active { background: var(--color-surface-elevated); color: var(--color-text-primary);
  font-weight: var(--font-weight-medium); }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px;
  border-radius: var(--radius-pill); border: 1px solid var(--color-border-strong);
  color: var(--color-text-primary); font: var(--font-weight-medium) var(--font-size-label)/1.5
  var(--font-family-sans); letter-spacing: var(--font-tracking-label); }
.chip.warn { background: var(--color-feedback-warning-subtle); color: var(--color-feedback-warning-text); border-color: transparent; }
.chip.pos { background: var(--color-feedback-positive-subtle); color: var(--color-feedback-positive-text); border-color: transparent; }
.chip.intel { background: var(--color-feedback-intelligence-subtle); color: var(--color-feedback-intelligence-text); border-color: transparent; }
.clock { margin-left: auto; font-family: var(--font-family-mono);
  font-size: var(--font-size-data); color: var(--color-text-secondary);
  font-variant-numeric: var(--font-numeric-tabular); }
.rule { border-left: 3px solid var(--color-brand-accent); padding-left: 14px; margin: 14px 0; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-gutter); }
footer { margin-top: 72px; border-top: 1px solid var(--color-border-subtle); padding-top: 18px;
  color: var(--color-text-muted); font-size: var(--font-size-caption); }
"""

ICON = ('<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
        'stroke-width="1.4" stroke-linecap="round">%s</svg>')
ICONS = {
    "overview": '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/>'
                '<rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>',
    "markets": '<path d="M2 12 L6 7 L9 9.5 L14 3"/><path d="M10.5 3 H14 V6.5"/>',
    "opportunities": '<circle cx="8" cy="8" r="5.5"/><path d="M8 5 V8 L10.2 10.2"/>',
    "intelligence": '<path d="M8 2 L13 8 L8 14 L3 8 Z"/><circle cx="8" cy="8" r="1.4"/>',
    "positions": '<path d="M3 4 H13"/><path d="M3 8 H13"/><path d="M3 12 H9"/>',
    "history": '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8 V8 L10.4 9.6"/>',
    "lab": '<path d="M6 2 V6 L3 12.5 A1 1 0 0 0 4 14 H12 A1 1 0 0 0 13 12.5 L10 6 V2"/>'
           '<path d="M5 2 H11"/>',
    "risk": '<path d="M8 2 L14 13 H2 Z"/><path d="M8 6.5 V9.5"/><circle cx="8" cy="11.4" r=".4"/>',
    "health": '<path d="M2 8 H5 L6.5 4.5 L9.5 11.5 L11 8 H14"/>',
    "settings": '<circle cx="8" cy="8" r="2.2"/><path d="M8 2 V4 M8 12 V14 M2 8 H4 M12 8 H14 '
                'M3.8 3.8 L5.2 5.2 M10.8 10.8 L12.2 12.2 M12.2 3.8 L10.8 5.2 M5.2 10.8 L3.8 12.2"/>',
}

NAV = [
    ("COMMAND", [("Overview", "overview", True)]),
    ("MARKETS", [("Live Markets", "markets", False), ("Trade Opportunities", "opportunities", False)]),
    ("INTELLIGENCE", [("Intelligence Centre", "intelligence", False)]),
    ("TRADING", [("Open Positions", "positions", False), ("Trade History", "history", False)]),
    ("STRATEGY", [("Strategy Laboratory", "lab", False)]),
    ("RISK", [("Portfolio & Risk", "risk", False)]),
    ("SYSTEM", [("System Health", "health", False), ("Settings & Controls", "settings", False)]),
]

SCREENS = [
    ("Overview", "Command Centre: capital, exposure, live risk, health, regime, positions, decision queue, no-trade visibility",
     "P1 capital → P2 exposure → P3 risk → P4 health → P5 evidence → P6 decisions",
     "main 12-col + side rail + lower strip", "docs/03 p1 Command Centre"),
    ("Live Markets", "Asset-class navigator, watchlists, scanner, heatmaps, breadth, volatility, liquidity, sessions; per-instrument workbench",
     "scan → compare → drill", "main + context rail (watchlist/quote/narrative zoom)",
     "docs/03 p2 Global Markets + p3 Instrument Workbench"),
    ("Trade Opportunities", "Ranked verified candidate theses awaiting owner decision; each carries evidence, counter-case, verification state",
     "P5 evidence quality first: justification before size", "main list + dossier context rail",
     "docs/03 p1 queue + p5 dispositions + p2 scanner output"),
    ("Intelligence Centre", "What NEXUS is doing and why: tasks, attention, beliefs, uncertainty, scenarios, tool activity; dossiers; memory",
     "P5 evidence → P6 decisions", "main + activity context rail",
     "docs/03 p4 Intelligence Core + p5 Research Dossiers + p6 Memory & Knowledge"),
    ("Open Positions", "Positions with venue-reported protective orders, working orders, fills, slippage, reconciliation, kill switch",
     "P1 capital → P3 live risk", "main blotter + execution context rail",
     "docs/03 p8 positions + p9 Execution Room"),
    ("Strategy Laboratory", "Catalogue, hypotheses, model versions, backtests, walk-forward, stress, promotion gates; scenario studio",
     "P6 decisions with evidence", "main + result context rail",
     "docs/03 p7 Strategy Laboratory + p11 Scenario Studio"),
    ("Portfolio & Risk", "Consolidated accounts, factor exposures, margin, drawdown, concentration, limits, stress repricing",
     "P1 → P2 → P3", "main + limits context rail",
     "docs/03 p8 Portfolio & Risk (+ p11 stress views)"),
    ("Trade History", "Fills, performance & attribution, calibration, audit & replay with export",
     "evidence of what happened, never recomputed narrative", "main tables + replay context rail",
     "docs/03 p12 Performance & Attribution + p13 Audit & Replay + p9 fills"),
    ("System Health", "Feed & adapter health, venue connections, entitlements, alert triage, delivery status",
     "P4 health before P6 decisions", "main status grid + alert queue context rail",
     "docs/03 p14 Alerts & Operations + p10 Connections"),
    ("Settings & Controls", "Mandates, live authority, risk limits, data sources, model registry, retention, security, roles",
     "governance reads last, writes rarest", "main forms + audit context rail",
     "docs/03 p15 Settings & Governance"),
]


def nav_html() -> str:
    out = []
    for grp, items in NAV:
        out.append(f'<div class="navgrp cap" style="letter-spacing:.08em">{grp}</div>')
        for label, icon, active in items:
            cls = "navitem active" if active else "navitem"
            out.append(f'<div class="{cls}">{ICON % ICONS[icon]}<span>{label}</span></div>')
    return "".join(out)


def shell_html() -> str:
    return f"""
<div class="shell">
  <div class="top">
    <span class="chip" style="border-color:transparent;background:var(--color-surface-elevated)">
      <svg width="12" height="12" viewBox="0 0 96 96"><polygon points="14,14 28,14 28,82 14,82" fill="var(--color-text-primary)"/><polygon points="68,14 82,14 82,82 68,82" fill="var(--color-text-primary)"/><polygon points="14,14 28,14 82,82 68,82" fill="var(--color-text-primary)"/><polygon points="48,32 64,48 48,64 32,48" fill="var(--color-surface-elevated)"/><polygon points="48,41 55,48 48,55 41,48" fill="var(--color-text-primary)"/></svg>
      NEXUS</span>
    <span class="chip intel">ENV SHADOW</span>
    <span class="chip">HALT OFF</span>
    <span class="chip">ACCT ALL</span>
    <span class="chip pos">&#9650; FEEDS LIVE</span>
    <span class="clock">14:32:05 UTC</span>
  </div>
  <div class="rail">{nav_html()}</div>
  <div class="main">
    <div class="region" style="grid-column: span 7">
      <div class="prio">P1</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase">consolidated equity / pnl</span>
      <div class="job">the one hero figure + realized/unrealized split; drills to account records</div></div>
    <div class="region" style="grid-column: span 5">
      <div class="prio">P2</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase">exposure</span>
      <div class="job">by venue, asset class, direction; never decorative tiles</div></div>
    <div class="region" style="grid-column: span 7">
      <div class="prio">P3</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase">live risk</span>
      <div class="job">limits vs usage, drawdown, margin headroom; fail-closed engine state</div></div>
    <div class="region" style="grid-column: span 5">
      <div class="prio">P4</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase">system health</span>
      <div class="job">feed integrity, adapters, latency; compromised feed barred from pipeline</div></div>
    <div class="region" style="grid-column: span 12">
      <div class="prio">P5/P6</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase">open positions + high-priority opportunities</span>
      <div class="job">dense tables, tabular numerals, every row drills to its source record</div></div>
    <div class="region" style="grid-column: span 12; background: var(--color-feedback-intelligence-subtle); border-color: transparent">
      <div class="prio">NO-TRADE</div><span class="cap" style="letter-spacing:.05em;text-transform:uppercase;color:var(--color-feedback-intelligence-text)">why NEXUS is waiting</span>
      <div class="job">what it watches, what would change its view, what invalidates the thesis — first-class region, never a toast</div></div>
  </div>
  <div class="ctx">
    <div class="cap" style="letter-spacing:.05em;text-transform:uppercase">side rail</div>
    <div class="region" style="margin-top:8px"><span class="cap">intelligence activity</span></div>
    <div class="region" style="margin-top:8px"><span class="cap">system health</span></div>
    <div class="region" style="margin-top:8px"><span class="cap">alert queue</span></div>
    <div class="job cap" style="margin-top:10px">lower strip (below main, full width): recent decisions | research awaiting action | execution quality</div>
  </div>
</div>"""


def main() -> pathlib.Path:
    tokens = (HERE / "tokens.css").read_text()
    tokens = re.sub(r"@font-face \{[^}]*\}", "", tokens)
    rows = "".join(
        f"<tr><td><b>{n}</b></td><td>{purpose}</td><td class='mono'>{hier}</td>"
        f"<td>{regions}</td><td>{src}</td></tr>"
        for n, purpose, hier, regions, src in SCREENS)
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 3.1 Layout & Information Architecture</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 3 of 23 &middot; sub-deliverable 3.1</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Shell, information architecture, screen map</h1>
<div class="status">Built &mdash; awaiting review &middot; every screen batch builds on this shell</div>
<p>The shell below is drawn entirely from approved material: docs/03 &sect;2 page architecture,
&sect;4 hierarchy, &sect;5 states, &sect;6 Command Centre layout; docs/09 tokens; D-031 brand rules.
Nothing floats, nothing overlaps; density is made legible by hard region boundaries and one job
per region. The ten mandate screens are workspaces over the fifteen approved docs/03 pages &mdash;
every approved page lands in exactly one screen, none is dropped.</p>

<h2><span class="num">01</span>The shell</h2>
{shell_html()}
<p class="cap">Top band 40px (always visible): mark, environment, halt, account group, worst-case
feed freshness, UTC clock. Left rail 208px: grouped icon+label nav, collapses to 56px icon-only.
Main: 12-column grid, 16px gutter. Context rail 264px on screens that opt in (watchlist/quote,
dossier, blotter). Lower strip on Overview only. Region chrome: heading-sm title, label caps for
column heads, caption for metadata; boundaries are hairline borders + surface steps.</p>

<h2><span class="num">02</span>Screen map &mdash; ten workspaces over fifteen approved pages</h2>
<div class="card"><table>
<tr><th>screen</th><th>purpose</th><th>hierarchy</th><th>regions</th><th>consolidates docs/03 pages</th></tr>
{rows}
</table></div>

<h2><span class="num">03</span>Grid, rhythm, density</h2>
<div class="grid2">
  <div class="card"><p style="margin:0">12-column grid, 16px gutter, 16px panel padding, 12px stack
  inside regions; tables 12&times;8px cells (docs/03 &sect;3.4 dense-but-readable). Regions take
  whole column spans (7/5, 12, 4/4/4) &mdash; never odd offsets, so boundaries always align.
  Type for scanning: values and figures in mono tabular, chrome in sans; nothing below 11px.</p></div>
  <div class="card"><p style="margin:0">Density rules: each region does exactly one job; hard
  boundaries (hairline + surface step) separate regions; no floating panels, no overlapping
  widgets &mdash; the only overlays are confirmation modals and the command palette (Stage 4).
  Charts inherit the token fonts including axis labels (docs/09 &sect;2).</p></div>
</div>

<h2><span class="num">04</span>Where the nine interaction states live</h2>
<div class="card"><table>
<tr><th>state (docs/03 &sect;5)</th><th>scope</th><th>chrome</th></tr>
<tr><td><b>Halted</b></td><td>global</td><td>top band chip flips to negative + full-width banner under top band; halt engage/resume flows (Stage 4)</td></tr>
<tr><td><b>Disconnected</b></td><td>global or per-venue</td><td>top band freshness chip &rarr; negative; venue rows badge in System Health</td></tr>
<tr><td><b>Stale / Delayed / Unavailable</b></td><td>per feed, per region</td><td>region header badge (amber/cyan/muted) + last-updated caption; new risk blocked banner where policy says so</td></tr>
<tr><td><b>Loading / Empty / Error</b></td><td>per region</td><td>skeleton shimmer / icon+message / red banner + retry inside the region only &mdash; one failing feed never blanks a screen</td></tr>
<tr><td><b>No-trade</b></td><td>Overview region + Opportunities screen</td><td>intelligence-tinted first-class region with watching/changing/invalidating lines</td></tr>
</table></div>
<div class="rule"><p>Drill-down is unconditional: every figure, badge and row links to its source
record (order, decision, case, incident, audit entry). A number without a source link is a defect.</p></div>

<h2><span class="num">05</span>Responsive behaviour</h2>
<div class="card"><table>
<tr><th>width</th><th>shell</th></tr>
<tr><td><b>&ge;1440</b></td><td>full three-region shell; context rail visible where the screen defines one</td></tr>
<tr><td><b>1024&ndash;1439</b></td><td>context rail becomes a docked edge tab (still docked, never floating); left rail labels collapse at &lt;1200</td></tr>
<tr><td><b>&lt;1024</b></td><td>mobile specification (docs/03 &sect;9): bottom tab bar Command/Markets/Positions/Alerts/More + top band; designed in batch 3.5</td></tr>
</table></div>
<footer>Stage 3.1 &middot; shell + IA only; no screen interiors yet &mdash; batches 3.2&ndash;3.5 draw
them inside this shell &middot; all colour/type from docs/09 tokens &middot; evidence: this board
renders from design/tokens.css.</footer>
</div></body></html>"""
    out = HERE / "stage3-1-layout-ia.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
