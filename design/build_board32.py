"""Stage 3.2 board: Overview + Live Markets interiors, chart anatomy, state variants.

Self-contained. All numeric content is tagged SPECIMEN (design placeholder);
production renders only real or labelled-simulated data (mandate §26, docs/03).

Run:  backend/.venv/bin/python design/build_board32.py
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
.wrap { max-width: 1240px; margin: 0 auto; padding: 44px 26px 96px; }
h2 { font-size: var(--font-size-heading); font-weight: var(--font-weight-semibold);
  line-height: var(--font-line-height-heading); letter-spacing: -0.01em; margin: 60px 0 4px; }
h2 .num { color: var(--color-brand-accent); margin-right: 10px; }
.lede { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
  letter-spacing: var(--font-tracking-label); text-transform: uppercase;
  color: var(--color-text-secondary); }
p { color: var(--color-text-secondary); max-width: 80ch; }
.cap { font-size: var(--font-size-caption); line-height: var(--font-line-height-caption);
  color: var(--color-text-muted); }
.mono { font-family: var(--font-family-mono); font-variant-numeric: var(--font-numeric-tabular); }
.ribbon { background: var(--color-feedback-warning-subtle); color: var(--color-feedback-warning-text);
  border-radius: var(--radius-control); padding: 8px 14px; font-size: var(--font-size-caption);
  margin: 18px 0; }
.shell { display: grid; grid-template-columns: 200px 1fr 250px; grid-template-rows: 40px 1fr auto;
  grid-template-areas: "top top top" "rail main ctx" "rail lower lower"; min-height: 640px;
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-overlay);
  overflow: hidden; background: var(--color-surface-canvas); }
.shell.norail { grid-template-columns: 200px 1fr; grid-template-areas: "top top" "rail main"; }
.top { grid-area: top; display:flex; align-items:center; gap:8px; padding: 0 12px;
  background: var(--color-surface-panel); border-bottom: 1px solid var(--color-border-subtle); }
.rail { grid-area: rail; background: var(--color-surface-panel);
  border-right: 1px solid var(--color-border-subtle); padding: 10px 8px; }
.ctx { grid-area: ctx; background: var(--color-surface-panel);
  border-left: 1px solid var(--color-border-subtle); padding: 12px; }
.main { grid-area: main; padding: var(--space-gutter); display: grid; gap: 12px;
  grid-template-columns: repeat(12, 1fr); align-content: start; }
.lower { grid-area: lower; padding: 0 var(--space-gutter) var(--space-gutter); display: grid;
  gap: 12px; grid-template-columns: repeat(12, 1fr); border-top: 1px solid var(--color-border-subtle);
  margin-top: 4px; padding-top: 12px; }
.region { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-card); padding: 12px; position: relative; }
.region > .rh { display:flex; align-items:baseline; gap:8px; margin-bottom: 8px; }
.region > .rh .t { font-size: var(--font-size-body); font-weight: var(--font-weight-semibold); }
.region > .rh .cap { margin-left:auto; }
.spec { position:absolute; top:8px; right:10px; font: var(--font-weight-medium) 9px/1
  var(--font-family-mono); letter-spacing:.1em; color: var(--color-text-muted);
  border:1px solid var(--color-border-subtle); border-radius: 3px; padding: 2px 4px; }
table { border-collapse: collapse; width: 100%; font-size: var(--font-size-data); }
th { font: var(--font-weight-medium) var(--font-size-label)/1.2 var(--font-family-sans);
  letter-spacing: var(--font-tracking-label); text-transform: uppercase;
  color: var(--color-text-secondary); text-align: left; padding: 0 var(--space-table-cell-x) 4px 0; }
td { padding: var(--space-table-cell-y) var(--space-table-cell-x) var(--space-table-cell-y) 0;
  border-top: 1px solid var(--color-border-subtle); color: var(--color-text-primary); }
.r { text-align: right; }
td.r, th.r { padding-right: 0; }
.num { font-family: var(--font-family-mono); font-variant-numeric: var(--font-numeric-tabular); }
.pos { color: var(--color-feedback-positive-text); } .neg { color: var(--color-feedback-negative-text); }
.warn { color: var(--color-feedback-warning-text); } .info { color: var(--color-feedback-info-text); }
.intel { color: var(--color-feedback-intelligence-text); }
.badge { display:inline-flex; align-items:center; gap:5px; padding: 1px 8px;
  border-radius: var(--radius-pill); font: var(--font-weight-medium) var(--font-size-label)/1.5
  var(--font-family-sans); letter-spacing: var(--font-tracking-label); }
.badge.pos { background: var(--color-feedback-positive-subtle); color: var(--color-feedback-positive-text); }
.badge.neg { background: var(--color-feedback-negative-subtle); color: var(--color-feedback-negative-text); }
.badge.warn { background: var(--color-feedback-warning-subtle); color: var(--color-feedback-warning-text); }
.badge.info { background: var(--color-feedback-info-subtle); color: var(--color-feedback-info-text); }
.badge.intel { background: var(--color-feedback-intelligence-subtle); color: var(--color-feedback-intelligence-text); }
.badge.mute { background: var(--color-surface-elevated); color: var(--color-text-secondary); }
.chip { display:inline-flex; align-items:center; gap:6px; padding: 2px 9px;
  border-radius: var(--radius-pill); border: 1px solid var(--color-border-strong);
  color: var(--color-text-primary); font: var(--font-weight-medium) var(--font-size-label)/1.5
  var(--font-family-sans); letter-spacing: var(--font-tracking-label); }
.clock { margin-left:auto; font-family: var(--font-family-mono); font-size: var(--font-size-data);
  color: var(--color-text-secondary); font-variant-numeric: var(--font-numeric-tabular); }
.navgrp { margin: 10px 6px 4px; }
.navitem { display:flex; align-items:center; gap:8px; padding: 6px 8px;
  border-radius: var(--radius-control); color: var(--color-text-secondary);
  font-size: var(--font-size-data); }
.navitem.active { background: var(--color-surface-elevated); color: var(--color-text-primary);
  font-weight: var(--font-weight-medium); }
.display { font-family: var(--font-family-mono); font-size: var(--font-size-display);
  font-weight: var(--font-weight-semibold); line-height: var(--font-line-height-display);
  letter-spacing: -0.01em; font-variant-numeric: var(--font-numeric-tabular); }
.bar { height: 4px; border-radius: 2px; background: var(--color-surface-elevated); position: relative; }
.bar i { position:absolute; inset:0 auto 0 0; border-radius:2px; background: var(--color-text-secondary); }
.skel { background: linear-gradient(90deg, var(--color-surface-elevated) 25%,
  var(--color-surface-panel) 50%, var(--color-surface-elevated) 75%); background-size: 200% 100%;
  border-radius: 4px; height: 12px; margin: 6px 0; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-gutter); }
.grid4 { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; }
footer { margin-top: 72px; border-top: 1px solid var(--color-border-subtle); padding-top: 18px;
  color: var(--color-text-muted); font-size: var(--font-size-caption); }
"""

ICON = ('<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
        'stroke-width="1.4" stroke-linecap="round">%s</svg>')
ICONS = {
    "overview": '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>',
    "markets": '<path d="M2 12 L6 7 L9 9.5 L14 3"/><path d="M10.5 3 H14 V6.5"/>',
    "opportunities": '<circle cx="8" cy="8" r="5.5"/><path d="M8 5 V8 L10.2 10.2"/>',
    "intelligence": '<path d="M8 2 L13 8 L8 14 L3 8 Z"/><circle cx="8" cy="8" r="1.4"/>',
    "positions": '<path d="M3 4 H13"/><path d="M3 8 H13"/><path d="M3 12 H9"/>',
    "history": '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8 V8 L10.4 9.6"/>',
    "lab": '<path d="M6 2 V6 L3 12.5 A1 1 0 0 0 4 14 H12 A1 1 0 0 0 13 12.5 L10 6 V2"/><path d="M5 2 H11"/>',
    "risk": '<path d="M8 2 L14 13 H2 Z"/><path d="M8 6.5 V9.5"/><circle cx="8" cy="11.4" r=".4"/>',
    "health": '<path d="M2 8 H5 L6.5 4.5 L9.5 11.5 L11 8 H14"/>',
    "settings": '<circle cx="8" cy="8" r="2.2"/><path d="M8 2 V4 M8 12 V14 M2 8 H4 M12 8 H14 M3.8 3.8 L5.2 5.2 M10.8 10.8 L12.2 12.2 M12.2 3.8 L10.8 5.2 M5.2 10.8 L3.8 12.2"/>',
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


def nav(active: str) -> str:
    out = []
    for grp, items in NAV:
        out.append(f'<div class="navgrp cap" style="letter-spacing:.08em">{grp}</div>')
        for label, icon, _ in items:
            cls = "navitem active" if label == active else "navitem"
            out.append(f'<div class="{cls}">{ICON % ICONS[icon]}<span>{label}</span></div>')
    return "".join(out)


TOPBAND = """
<div class="top">
  <span class="chip" style="border-color:transparent;background:var(--color-surface-elevated)">NEXUS</span>
  <span class="badge intel">ENV SHADOW</span>
  <span class="chip">HALT OFF</span>
  <span class="chip">ACCT ALL</span>
  <span class="badge pos">&#9650; FEEDS LIVE</span>
  <span class="clock">14:32:05 UTC</span>
</div>"""


def region(span: int, title: str, body: str, meta: str = "", specimen: bool = True) -> str:
    spec = '<span class="spec">SPECIMEN</span>' if specimen else ""
    return (f'<div class="region" style="grid-column: span {span}">{spec}'
            f'<div class="rh"><span class="t">{title}</span>'
            f'<span class="cap">{meta}</span></div>{body}</div>')


def overview_main() -> str:
    equity = ('<div class="display">48,210.66 <span class="cap">USDT</span></div>'
              '<div style="display:flex;gap:18px;margin-top:6px">'
              '<span class="cap">realized <b class="num pos">+1,842.10 ▲</b></span>'
              '<span class="cap">unrealized <b class="num neg">-204.08 ▼</b></span>'
              '<span class="cap">updated 14:32:05 UTC · <u>ledger#8841</u></span></div>')
    exposure = """<table>
<tr><th>venue</th><th class="r">gross</th><th class="r">net</th><th class="r">share</th></tr>
<tr><td>BYBIT</td><td class="r num">18,400.00</td><td class="r num">+2,100.00</td>
    <td class="r" style="width:70px"><span class="bar" style="width:64px;display:inline-block"><i style="width:38%"></i></span></td></tr>
<tr><td>OKX</td><td class="r num">9,204.50</td><td class="r num">-640.20</td>
    <td class="r"><span class="bar" style="width:64px;display:inline-block"><i style="width:19%"></i></span></td></tr>
<tr><td>FX-EDGE</td><td class="r num">6,120.00</td><td class="r num">+310.00</td>
    <td class="r"><span class="bar" style="width:64px;display:inline-block"><i style="width:13%"></i></span></td></tr>
</table>"""
    risk = """<table>
<tr><th>limit</th><th class="r">used</th><th class="r">headroom</th><th>state</th></tr>
<tr><td>daily loss</td><td class="r num">31%</td><td class="r num">1,380.00</td><td><span class="badge pos">OK</span></td></tr>
<tr><td>gross exposure</td><td class="r num">64%</td><td class="r num">12,900.00</td><td><span class="badge warn">WATCH</span></td></tr>
<tr><td>concentration</td><td class="r num">22%</td><td class="r num">—</td><td><span class="badge pos">OK</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">risk engine: <b class="pos">ACTIVE · fail-closed</b> ·
independent of model confidence</div>"""
    health = """<table>
<tr><th>feed</th><th>freshness</th><th class="r">latency</th></tr>
<tr><td>binance spot</td><td><span class="badge pos">LIVE</span></td><td class="r num">84 ms</td></tr>
<tr><td>okx spot</td><td><span class="badge pos">LIVE</span></td><td class="r num">112 ms</td></tr>
<tr><td>dukascopy fx</td><td><span class="badge warn">STALE 45s</span></td><td class="r num">—</td></tr>
</table>
<div class="cap" style="margin-top:6px">compromised feed → barred from decision pipeline</div>"""
    regime = """<div class="grid4">
<div><div class="cap">regime</div><div class="num" style="font-size:var(--font-size-emphasis);font-weight:600">RANGING</div><div class="cap">conf 0.62 ± 0.11</div></div>
<div><div class="cap">volatility</div><div class="num" style="font-size:var(--font-size-emphasis);font-weight:600">MED</div><div class="cap">HV 41% ± 6</div></div>
<div><div class="cap">risk tone</div><div class="num" style="font-size:var(--font-size-emphasis);font-weight:600">OFF</div><div class="cap">conf 0.55 ± 0.14</div></div>
<div><div class="cap">liquidity</div><div class="num" style="font-size:var(--font-size-emphasis);font-weight:600">NORMAL</div><div class="cap">spread idx 1.02</div></div>
</div><div class="cap" style="margin-top:6px">every regime value carries its uncertainty band</div>"""
    positions = """<table>
<tr><th>instrument</th><th>venue</th><th>side</th><th class="r">size</th><th class="r">entry</th>
    <th class="r">last</th><th class="r">uPnL</th><th>protective</th></tr>
<tr><td>BTCUSDT</td><td>BYBIT</td><td>LONG</td><td class="r num">0.250</td><td class="r num">66,980.0</td>
    <td class="r num">67,412.5</td><td class="r num pos">+108.12 ▲</td><td><span class="badge pos">SL VENUE-SET</span></td></tr>
<tr><td>ETHUSDT</td><td>OKX</td><td>SHORT</td><td class="r num">1.800</td><td class="r num">3,512.4</td>
    <td class="r num">3,540.1</td><td class="r num neg">-49.86 ▼</td><td><span class="badge pos">SL VENUE-SET</span></td></tr>
<tr><td>EURUSD</td><td>FX-EDGE</td><td>LONG</td><td class="r num">12,000</td><td class="r num">1.08420</td>
    <td class="r num">1.08465</td><td class="r num pos">+5.40 ▲</td><td><span class="badge warn">TRAILING PENDING</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">protective-order state is venue-reported, never assumed</div>"""
    opps = """<table>
<tr><th>#</th><th>instrument</th><th>thesis</th><th>verification</th></tr>
<tr><td class="num">1</td><td>BTCUSDT</td><td>mean-reversion post-liquidation cluster</td>
    <td><span class="badge intel">3/3 VERIFIED</span></td></tr>
<tr><td class="num">2</td><td>EURUSD</td><td>session-open imbalance, liquidity void above</td>
    <td><span class="badge warn">2/3 · RISK CHECK</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">confidence never overrides a failed mandatory condition</div>"""
    notrade = ('<div style="background:var(--color-feedback-intelligence-subtle);'
               'border-radius:var(--radius-control);padding:10px 12px">'
               '<div class="cap intel" style="letter-spacing:.05em;text-transform:uppercase">'
               'no trade justified — evidence insufficient</div>'
               '<div class="cap" style="margin-top:6px">watching: BTC funding reset 16:00 UTC · '
               'EURUSD london open · OKX depth recovery<br>would change view: funding flip + '
               'depth &gt; 1.5× baseline · invalidates: HV &gt; 55% or risk tone flip</div></div>')
    return (region(7, "Consolidated equity / P&L", equity, "P1 · drills to ledger") +
            region(5, "Exposure", exposure, "P2 · by venue") +
            region(7, "Live risk", risk, "P3 · limits vs usage") +
            region(5, "System health", health, "P4 · feeds") +
            region(12, "Market regime overview", regime, "with uncertainty", ) +
            region(7, "Open positions", positions, "dense · tabular") +
            region(5, "High-priority opportunities", opps, "verification-gated") +
            region(12, "", notrade, "", specimen=False))


def overview_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">side rail</div>
<div class="region" style="margin-top:8px"><div class="rh"><span class="t" style="font-size:var(--font-size-data)">intelligence activity</span></div>
  <div class="cap intel">◆ scanning OKX depth recovery</div>
  <div class="cap intel">◆ dossier #2211 drafted · awaiting review</div>
  <div class="cap intel">◆ belief update: EURUSD bias flat → soft-long</div></div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span><div class="rh"><span class="t" style="font-size:var(--font-size-data)">system health</span></div>
  <div class="cap">3 feeds live · 1 stale · 0 blocked<br>risk engine ACTIVE · reconciler idle</div></div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span><div class="rh"><span class="t" style="font-size:var(--font-size-data)">alert queue</span></div>
  <div class="cap"><span class="badge neg">1 CRIT</span> <span class="badge warn">2 WARN</span> <span class="badge info">4 INFO</span><br>
  crit: dukascopy stale &gt; 60s — new FX risk blocked</div></div>
<div class="cap" style="margin-top:10px">lower strip (full width below main): recent decisions |
research awaiting action | execution quality</div>"""


def lower_strip() -> str:
    dec = """<table>
<tr><td class="num">14:12</td><td>REJECT candidate #88 — risk check failed</td><td><u>case#88</u></td></tr>
<tr><td class="num">13:58</td><td>APPROVE paper order BTCUSDT 0.05</td><td><u>order#512</u></td></tr>
</table>"""
    res = """<table>
<tr><td>dossier #2211</td><td>funding-reset behaviour post-halving</td><td><span class="badge intel">AWAITING OWNER</span></td></tr>
</table>"""
    exe = """<table>
<tr><td>slippage p50</td><td class="r num">1.8 bps</td></tr>
<tr><td>fill rate</td><td class="r num">98.2%</td></tr>
<tr><td>rejects 24h</td><td class="r num">3</td></tr>
</table>"""
    return (region(4, "Recent decisions", dec, "") + region(4, "Research awaiting action", res, "") +
            region(4, "Execution quality", exe, ""))


def states_strip() -> str:
    loading = '<div class="skel" style="width:70%"></div><div class="skel" style="width:90%"></div><div class="skel" style="width:55%"></div><div class="cap">Loading positions…</div>'
    empty = ('<div class="cap" style="margin:10px 0">◇ &nbsp;No open positions. '
             'NEXUS is watching 12 instruments.</div>')
    error = ('<div class="badge neg" style="margin:6px 0">FAILED TO LOAD POSITIONS</div>'
             '<div class="cap">[Retry] [View logs]</div>')
    stale = ('<div class="badge warn" style="margin:6px 0">DATA STALE — last update 14:32:05 UTC '
             '(45s ago)</div><div class="cap">New risk blocked.</div>')
    return (region(3, "Loading", loading, "", specimen=False) +
            region(3, "Empty", empty, "", specimen=False) +
            region(3, "Error", error, "", specimen=False) +
            region(3, "Stale", stale, "", specimen=False))


def markets_main() -> str:
    nav_chips = ('<div style="display:flex;gap:8px;flex-wrap:wrap">'
                 '<span class="chip">CRYPTO · TRADE-ENABLED</span>'
                 '<span class="chip">FX · TRADE-ENABLED</span>'
                 '<span class="chip">INDICES · DATA-AVAILABLE</span>'
                 '<span class="chip" style="opacity:.55">EQUITIES · NOT SUPPORTED</span></div>'
                 '<div class="cap" style="margin-top:6px">capability registry: unsupported markets '
                 'are shown greyed with registry state, never as tradable</div>')
    watch = """<table>
<tr><th>symbol</th><th class="r">last</th><th class="r">chg%</th><th class="r">spread</th><th>session</th><th>fresh</th></tr>
<tr><td>BTCUSDT</td><td class="r num">67,412.5</td><td class="r num pos">+1.24 ▲</td><td class="r num">0.5</td><td>24/7</td><td><span class="badge pos">LIVE</span></td></tr>
<tr><td>ETHUSDT</td><td class="r num">3,540.1</td><td class="r num neg">-0.42 ▼</td><td class="r num">0.8</td><td>24/7</td><td><span class="badge pos">LIVE</span></td></tr>
<tr><td>EURUSD</td><td class="r num">1.08465</td><td class="r num pos">+0.06 ▲</td><td class="r num">0.3</td><td>LDN</td><td><span class="badge warn">STALE</span></td></tr>
<tr><td>XAUUSD</td><td class="r num">2,388.40</td><td class="r num pos">+0.31 ▲</td><td class="r num">1.2</td><td>LDN</td><td><span class="badge info">DELAYED 15m</span></td></tr>
</table>"""
    scanner = """<table>
<tr><th>condition</th><th class="r">hits</th></tr>
<tr><td>liquidation cluster ±0.5%</td><td class="r num">3</td></tr>
<tr><td>spread &gt; 2× baseline</td><td class="r num">1</td></tr>
<tr><td>funding |z| &gt; 2</td><td class="r num">2</td></tr>
</table>"""
    heat = ('<div style="display:grid;grid-template-columns:repeat(6,1fr);gap:3px">' +
            "".join(f'<div style="height:26px;border-radius:3px;background:{c}"></div>'
                    for c in ("#163630", "#152F2D", "#2C2027", "#163630", "#222236", "#2D2A22",
                              "#152F2D", "#2C2027", "#16293A", "#163630", "#2D2A22", "#152F2D",
                              "#222236", "#163630", "#2C2027", "#152F2D", "#16293A", "#2D2A22")) +
            '</div><div class="cap" style="margin-top:6px">heatmap metric + universe configurable; '
            'no entitlement → unavailable + cause, never synthetic</div>')
    sess = ('<div class="cap mono" style="display:flex;justify-content:space-between">'
            '<span>00</span><span>06</span><span>12</span><span>18</span><span>24 UTC</span></div>'
            '<div style="height:10px;border-radius:5px;background:var(--color-surface-elevated);'
            'position:relative;margin:4px 0"><i style="position:absolute;left:33%;width:25%;'
            'background:var(--color-feedback-info-subtle);inset:0 auto 0 33%"></i>'
            '<i style="position:absolute;left:66%;width:20%;inset:0 auto 0 66%;'
            'background:var(--color-feedback-intelligence-subtle)"></i></div>'
            '<div class="cap">LDN open · NY open · crypto 24/7 — session shading matches charts</div>')
    return (region(12, "Asset-class navigator", nav_chips, "capability registry", specimen=False) +
            region(8, "Watchlists", watch, "three zoom levels in context rail") +
            region(4, "Scanner", scanner, "") +
            region(6, "Global heatmap", heat, "observatory universe") +
            region(6, "Session map", sess, "UTC axis", specimen=False))


def markets_ctx() -> str:
    quote = """<table>
<tr><td>last</td><td class="r num">67,412.5</td></tr>
<tr><td>bid / ask</td><td class="r num">67,412.0 / 67,413.0</td></tr>
<tr><td>24h vwap</td><td class="r num">66,905.2</td></tr>
<tr><td>funding / 8h</td><td class="r num">+0.008%</td></tr>
<tr><td>open interest</td><td class="r num">1.24B</td></tr>
</table>"""
    return f"""
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail · three zooms</div>
<div class="region" style="margin-top:8px"><div class="rh"><span class="t" style="font-size:var(--font-size-data)">1 · list</span></div>
  <div class="cap">BTCUSDT +1.24 · ETHUSDT -0.42 · EURUSD +0.06 …</div></div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span><div class="rh"><span class="t" style="font-size:var(--font-size-data)">2 · quote</span><span class="cap">BTCUSDT · BYBIT</span></div>
  {quote}</div>
<div class="region" style="margin-top:8px"><div class="rh"><span class="t" style="font-size:var(--font-size-data)">3 · narrative</span></div>
  <div class="cap">research: funding-reset cluster watched 16:00 UTC · dossier #2211 ·
  venue notes: depth recovering post-outage</div></div>"""


CHART_SVG = """
<svg viewBox="0 0 720 300" style="width:100%;background:var(--color-surface-panel);
border:1px solid var(--color-border-subtle);border-radius:var(--radius-card)" role="img">
  <g font-family="JetBrains Mono, monospace" font-size="9" fill="var(--color-text-muted)">
    <text x="10" y="16">BTCUSDT · BYBIT · 15m · UTC · LIVE · venue-reported</text>
    <text x="640" y="16">[overlays ▾] [export]</text>
    <text x="688" y="40">68,400</text><text x="688" y="100">67,900</text>
    <text x="688" y="160">67,400</text><text x="688" y="220">66,900</text>
    <text x="60" y="292">08:00</text><text x="240" y="292">10:00</text>
    <text x="420" y="292">12:00</text><text x="600" y="292">14:00</text>
  </g>
  <g stroke="var(--color-border-subtle)" stroke-width="1">
    <line x1="0" y1="40" x2="680" y2="40"/><line x1="0" y1="100" x2="680" y2="100"/>
    <line x1="0" y1="160" x2="680" y2="160"/><line x1="0" y1="220" x2="680" y2="220"/>
    <line x1="60" y1="24" x2="60" y2="250"/><line x1="240" y1="24" x2="240" y2="250"/>
    <line x1="420" y1="24" x2="420" y2="250"/><line x1="600" y1="24" x2="600" y2="250"/>
  </g>
  <rect x="300" y="24" width="120" height="226" fill="var(--color-feedback-info-subtle)" opacity="0.5"/>
  <text x="306" y="36" font-family="Inter" font-size="8" fill="var(--color-feedback-info-text)">SESSION: LDN OPEN</text>
  <g stroke-width="1.4">
    <g stroke="var(--color-feedback-positive-text)">
      <line x1="80" y1="150" x2="80" y2="190"/><rect x="76" y="160" width="8" height="22" fill="var(--color-feedback-positive-text)"/>
      <line x1="120" y1="140" x2="120" y2="185"/><rect x="116" y="150" width="8" height="26" fill="var(--color-feedback-positive-text)"/>
      <line x1="200" y1="120" x2="200" y2="170"/><rect x="196" y="128" width="8" height="30" fill="var(--color-feedback-positive-text)"/>
      <line x1="320" y1="110" x2="320" y2="160"/><rect x="316" y="118" width="8" height="30" fill="var(--color-feedback-positive-text)"/>
      <line x1="480" y1="90" x2="480" y2="140"/><rect x="476" y="98" width="8" height="30" fill="var(--color-feedback-positive-text)"/>
    </g>
    <g stroke="var(--color-feedback-negative-text)">
      <line x1="160" y1="130" x2="160" y2="175"/><rect x="156" y="138" width="8" height="26" fill="var(--color-feedback-negative-text)"/>
      <line x1="240" y1="115" x2="240" y2="160"/><rect x="236" y="122" width="8" height="28" fill="var(--color-feedback-negative-text)"/>
      <line x1="360" y1="100" x2="360" y2="150"/><rect x="356" y="108" width="8" height="30" fill="var(--color-feedback-negative-text)"/>
      <line x1="440" y1="95" x2="440" y2="145"/><rect x="436" y="102" width="8" height="30" fill="var(--color-feedback-negative-text)"/>
      <line x1="560" y1="85" x2="560" y2="135"/><rect x="556" y="92" width="8" height="30" fill="var(--color-feedback-negative-text)"/>
    </g>
    <g stroke="var(--color-text-secondary)" stroke-dasharray="3 3">
      <line x1="0" y1="126" x2="680" y2="126"/><line x1="520" y1="24" x2="520" y2="250"/>
    </g>
  </g>
  <g font-family="JetBrains Mono, monospace" font-size="8">
    <rect x="524" y="118" width="66" height="14" rx="3" fill="var(--color-surface-elevated)"/>
    <text x="529" y="128" fill="var(--color-text-primary)">67,618.0</text>
    <rect x="452" y="24" width="64" height="14" rx="3" fill="var(--color-surface-elevated)"/>
    <text x="457" y="34" fill="var(--color-text-primary)">13:15 UTC</text>
  </g>
  <polygon points="360,70 366,76 360,82 354,76" fill="var(--color-feedback-intelligence-text)"/>
  <polygon points="240,180 246,186 240,192 234,186" fill="var(--color-feedback-warning-text)"/>
  <g stroke="var(--color-border-subtle)"><line x1="0" y1="252" x2="680" y2="252"/></g>
  <g fill="var(--color-text-secondary)" opacity="0.7">
    <rect x="76" y="262" width="8" height="14"/><rect x="116" y="258" width="8" height="18"/>
    <rect x="156" y="266" width="8" height="10"/><rect x="196" y="260" width="8" height="16"/>
    <rect x="236" y="264" width="8" height="12"/><rect x="316" y="256" width="8" height="20"/>
    <rect x="356" y="262" width="8" height="14"/><rect x="436" y="258" width="8" height="18"/>
    <rect x="476" y="264" width="8" height="12"/><rect x="556" y="260" width="8" height="16"/>
  </g>
  <text x="10" y="268" font-family="Inter" font-size="8" fill="var(--color-text-muted)">VOLUME</text>
</svg>"""


def chart_anatomy() -> str:
    return f"""
{CHART_SVG}
<div class="grid2" style="margin-top:12px">
  <div><div class="cap"><b>Mandatory chrome (docs/03 header rule):</b> instrument · venue ·
  timeframe · timezone (UTC + venue-local toggle) · data status · delayed flag — the title line
  above carries all six, mono, caption size.</div>
  <div class="cap" style="margin-top:6px"><b>Axes &amp; grid:</b> hairline borders; axis labels in
  mono tabular at caption size; price axis right; UTC time axis below; session shading bands
  match the session map on Live Markets.</div></div>
  <div><div class="cap"><b>Interaction (Stage 4 implements):</b> crosshair with mono value chips
  on both axes; event markers — ◆ research/decision (intelligence), ⚠ incident/warning (amber) —
  each links to its record; overlays menu; export CSV/PNG.</div>
  <div class="cap" style="margin-top:6px"><b>Honesty rule (docs/03 §8):</b> no synthetic depth,
  fabricated flow or invented Greeks; absent data renders unavailable + cause
  (entitlement / venue limitation / ingestion failure). Volume pane is venue-reported only.</div></div>
</div>"""


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    overview = f"""<div class="shell">{TOPBAND}
<div class="rail">{nav("Overview")}</div>
<div class="main">{overview_main()}</div>
<div class="ctx">{overview_ctx()}</div>
<div class="lower">{lower_strip()}</div></div>"""
    markets = f"""<div class="shell">{TOPBAND}
<div class="rail">{nav("Live Markets")}</div>
<div class="main">{markets_main()}
  <div class="region" style="grid-column: span 12"><div class="rh"><span class="t">Instrument workbench — chart anatomy</span>
  <span class="cap">docs/03 p3 · anatomy, not a live chart</span></div>{chart_anatomy()}</div>
</div>
<div class="ctx">{markets_ctx()}</div></div>"""
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 3.2 Overview & Live Markets</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 3 &middot; sub-deliverable 3.2</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Overview &amp; Live Markets — screen interiors</h1>
<div class="ribbon">DESIGN SPECIMEN — numeric values are labelled placeholders for typography and
density review. Production renders only real or labelled-simulated data (mandate §26); regions
carrying specimen numbers are tagged SPECIMEN in the corner.</div>

<h2><span class="num">01</span>Overview (Command Centre)</h2>
{overview}
<p class="cap">Hierarchy order is the layout order: P1 capital → P2 exposure → P3 live risk →
P4 health → regime with uncertainty → positions + opportunities → no-trade region; side rail and
lower strip per docs/03 §6. Every row drills to its source record (underlined ids).</p>

<h2><span class="num">02</span>Region states (docs/03 §5, contained per region)</h2>
<div class="main" style="padding:0">{states_strip()}</div>

<h2><span class="num">03</span>Live Markets + instrument workbench</h2>
{markets}
<p class="cap">Navigator reads the capability registry — unsupported asset classes appear greyed
with their registry state and are never offered as tradable. Watchlist → quote → narrative zooms
live in the docked context rail. Chart anatomy carries all six mandatory chrome facts and the
§8 honesty rule.</p>
<footer>Stage 3.2 &middot; interiors compose inside the approved 3.1 shell (D-033) with approved
Stage 2 tokens (D-032) &middot; batches 3.3–3.5 next on approval.</footer>
</div></body></html>"""
    out = HERE / "stage3-2-overview-markets.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
