"""Stage 3.4 board: Open Positions, Strategy Laboratory, Portfolio & Risk, Trade History.

Reuses 3.2 shell helpers; self-contained; specimen-tagged per D-034 policy.

Run:  backend/.venv/bin/python design/build_board34.py
"""

from __future__ import annotations

import pathlib
import re

from build_board32 import CSS as CSS32, TOPBAND, nav, region
from build_board33 import CSS as CSS33
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS33

EQUITY_SVG = """
<svg viewBox="0 0 460 150" style="width:100%;background:var(--color-surface-canvas);
border:1px solid var(--color-border-subtle);border-radius:var(--radius-control)" role="img">
  <g stroke="var(--color-border-subtle)" stroke-width="1">
    <line x1="0" y1="30" x2="440" y2="30"/><line x1="0" y1="70" x2="440" y2="70"/>
    <line x1="0" y1="110" x2="440" y2="110"/></g>
  <polyline fill="none" stroke="var(--color-text-secondary)" stroke-width="1.6"
    points="10,96 60,88 110,72 160,78 210,58 260,64 310,44 360,52 410,38 430,42"/>
  <polyline fill="none" stroke="var(--color-feedback-info-graphic)" stroke-width="1.2"
    stroke-dasharray="4 3" points="10,100 60,94 110,80 160,87 210,68 260,75 310,56 360,65 410,52 430,56"/>
  <g font-family="JetBrains Mono, monospace" font-size="7.5" fill="var(--color-text-muted)">
    <text x="444" y="33">+8%</text><text x="444" y="73">0</text><text x="444" y="113">-8%</text>
    <text x="10" y="142">gross — solid · net — dashed (fees/funding/slippage deducted)</text>
    <text x="300" y="142">trade annotations ◆ link to records</text></g>
  <polygon points="210,52 215,57 210,62 205,57" fill="var(--color-feedback-intelligence-text)"/>
  <polygon points="310,38 315,43 310,48 305,43" fill="var(--color-feedback-intelligence-text)"/>
</svg>"""


def positions_main() -> str:
    blotter = """<table>
<tr><th>instrument</th><th>venue</th><th>side</th><th class="r">size</th><th class="r">entry</th>
<th class="r">last</th><th class="r">uPnL</th><th>protective (venue-reported)</th><th>recon</th></tr>
<tr><td>BTCUSDT</td><td>BYBIT</td><td>LONG</td><td class="r num">0.250</td><td class="r num">66,980.0</td>
<td class="r num">67,412.5</td><td class="r num pos">+108.12 ▲</td><td><span class="badge pos">SL 66,780 SET</span></td>
<td><span class="badge pos">MATCHED</span></td></tr>
<tr><td>ETHUSDT</td><td>OKX</td><td>SHORT</td><td class="r num">1.800</td><td class="r num">3,512.4</td>
<td class="r num">3,540.1</td><td class="r num neg">-49.86 ▼</td><td><span class="badge pos">SL 3,588 SET</span></td>
<td><span class="badge pos">MATCHED</span></td></tr>
<tr><td>EURUSD</td><td>FX-EDGE</td><td>LONG</td><td class="r num">12,000</td><td class="r num">1.08420</td>
<td class="r num">1.08465</td><td class="r num pos">+5.40 ▲</td><td><span class="badge warn">TRAIL PENDING</span></td>
<td><span class="badge warn">1 UNMATCHED</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">protective-order state and fills are venue-reported, never
assumed; unmatched recon rows block new risk in that instrument until resolved</div>"""
    orders = """<table>
<tr><th>order</th><th>instrument</th><th>side</th><th>type</th><th class="r">size</th>
<th class="r">limit</th><th>state</th><th class="r">age</th></tr>
<tr><td class="num">#512</td><td>BTCUSDT</td><td>LONG</td><td>limit</td><td class="r num">0.050</td>
<td class="r num">66,900.0</td><td><span class="badge info">WORKING</span></td><td class="r num">4m12s</td></tr>
<tr><td class="num">#511</td><td>ETHUSDT</td><td>SHORT</td><td>stop</td><td class="r num">1.800</td>
<td class="r num">3,588.0</td><td><span class="badge pos">FILLED 13:58</span></td><td class="r num">—</td></tr>
<tr><td class="num">#509</td><td>EURUSD</td><td>LONG</td><td>limit</td><td class="r num">12,000</td>
<td class="r num">1.08380</td><td><span class="badge neg">REJECTED RC-311</span></td><td class="r num">—</td></tr>
</table>
<div class="cap" style="margin-top:6px">fills carry slippage vs arrival: <span class="num">+0.4 bps
· -1.1 bps</span> · rejects carry reason codes and link to the venue response</div>"""
    recon = """<table>
<tr><td>bybit</td><td class="r num">2/2</td><td><span class="badge pos">MATCHED</span></td></tr>
<tr><td>okx</td><td class="r num">2/2</td><td><span class="badge pos">MATCHED</span></td></tr>
<tr><td>fx-edge</td><td class="r num">1/2</td><td><span class="badge warn">UNMATCHED · investigating</span></td></tr>
</table>
<div style="margin-top:10px"><span class="btn danger">emergency halt</span></div>
<div class="cap" style="margin-top:6px">scope shown before confirm: accounts, instruments, working
orders per policy (docs/03 J-03) · idempotent execution + reconciliation (mandate)</div>"""
    return (region(12, "Positions blotter", blotter, "venue-reported protective state") +
            region(8, "Order blotter · fills · rejects", orders, "p9 execution room") +
            region(4, "Reconciliation · kill switch", recon, "ledger vs venue", specimen=False))


def positions_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">BTCUSDT protectives</span></div>
<div class="cap mono">SL 66,780.0 · venue-set · id #77120<br>TP none · expiry flat 16:40 UTC<br>
last venue ack 14:31:58 UTC</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">unknown-order policy</span></div>
<div class="cap">any order state the venue cannot confirm → alert CRIT + new risk blocked on that
instrument until reconciled</div></div>"""


def lab_main() -> str:
    catalog = """<table>
<tr><th>strategy</th><th>ver</th><th>state</th><th class="r">sharpe (cost-adj)</th>
<th class="r">maxDD</th><th class="r">turnover</th><th>promotion gate</th></tr>
<tr><td>funding-reset MR</td><td class="num">v0.4.2</td><td><span class="badge intel">PAPER</span></td>
<td class="r num">1.31 [0.8–1.8]</td><td class="r num">-6.1%</td><td class="r num">2.1×/d</td>
<td><span class="badge warn">GATE 4/5</span></td></tr>
<tr><td>session-open imbalance</td><td class="num">v0.2.0</td><td><span class="badge intel">SHADOW</span></td>
<td class="r num">0.94 [0.3–1.5]</td><td class="r num">-4.4%</td><td class="r num">0.8×/d</td>
<td><span class="badge warn">GATE 2/5</span></td></tr>
<tr><td>vol-compression fade</td><td class="num">v0.1.3</td><td><span class="badge mute">RESEARCH</span></td>
<td class="r num">0.61 [-0.1–1.3]</td><td class="r num">-7.9%</td><td class="r num">1.4×/d</td>
<td><span class="badge mute">GATE 1/5</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">cost-adjusted metrics with confidence intervals; never
ranked by hit rate alone (docs/03 §8); experimental strategies never auto-promote to live</div>"""
    detail = """<div class="grid2">
<div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">hypothesis</div>
<div class="cap">post-liquidation clusters mean-revert within 2h when funding reset removes carry
headwind and depth confirms absorption</div>
<table style="margin-top:8px">
<tr><th>evaluation</th><th class="r">sharpe</th><th class="r">maxDD</th><th class="r">n</th></tr>
<tr><td>backtest 24m</td><td class="r num">1.62</td><td class="r num">-5.2%</td><td class="r num">214</td></tr>
<tr><td>walk-forward</td><td class="r num">1.28</td><td class="r num">-6.1%</td><td class="r num">86</td></tr>
<tr><td>stress -2σ liq</td><td class="r num">0.71</td><td class="r num">-9.4%</td><td class="r num">18</td></tr>
</table></div>
<div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">promotion gates</div>
<div class="cap"><span class="badge pos">1 out-of-sample</span> <span class="badge pos">2 cost-adjusted</span>
<span class="badge pos">3 stress</span> <span class="badge warn">4 paper duration 11/14d</span>
<span class="badge mute">5 owner approval</span></div>
<div class="cap" style="margin-top:8px">model registry: code hash <span class="mono">a41f…</span> ·
data window pinned · learning history linked (controlled learning, Stage 18 chrome reserved)</div>
</div></div>"""
    scen = """<table>
<tr><th>shock</th><th class="r">reprice</th><th class="r">limit after</th></tr>
<tr><td>BTC -8% gap</td><td class="r num neg">-1,240</td><td class="r num">61%</td></tr>
<tr><td>spread 3× 4h</td><td class="r num neg">-310</td><td class="r num">47%</td></tr>
<tr><td>venue outage 2h</td><td class="r num neg">-95</td><td class="r num">44%</td></tr>
</table>
<div class="cap" style="margin-top:6px">scenario studio (p11): assumptions + probability ranges
shown; calibration stated, fan charts arrive with charts batch</div>"""
    return (region(12, "Strategy catalogue", catalog, "cost-adjusted + CI") +
            region(8, "funding-reset MR v0.4.2", detail, "gates explicit") +
            region(4, "Scenario studio", scen, "p11 views"))


def lab_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">promotion law</span></div>
<div class="cap">RESEARCH → SHADOW → PAPER → PILOT → LIVE, each step owner-approved; rollback plan
recorded before promotion; no automatic promotion ever (mandate)</div></div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">paper runtime</span></div>
<div class="meter"><i style="width:79%"></i></div>
<div class="cap">11 of 14 days · 0 gate breaches · 2 waits logged</div></div>"""


def risk_main() -> str:
    accounts = """<table>
<tr><th>account</th><th>venue</th><th class="r">equity</th><th class="r">margin</th><th>state</th></tr>
<tr><td>main-a</td><td>BYBIT</td><td class="r num">28,410.2</td><td class="r num">4,120.0</td><td><span class="badge pos">TRADE-ENABLED</span></td></tr>
<tr><td>main-b</td><td>OKX</td><td class="r num">13,680.4</td><td class="r num">1,904.5</td><td><span class="badge pos">TRADE-ENABLED</span></td></tr>
<tr><td>fx-1</td><td>FX-EDGE</td><td class="r num">6,120.0</td><td class="r num">310.0</td><td><span class="badge warn">DATA-AVAILABLE</span></td></tr>
</table>"""
    factors = """<table>
<tr><th>factor</th><th class="r">exposure</th><th class="r">limit</th><th>usage</th></tr>
<tr><td>crypto beta</td><td class="r num">+0.62</td><td class="r num">1.00</td>
<td style="width:70px"><span class="bar" style="width:64px;display:inline-block"><i style="width:62%"></i></span></td></tr>
<tr><td>fx carry</td><td class="r num">+0.18</td><td class="r num">0.50</td>
<td><span class="bar" style="width:64px;display:inline-block"><i style="width:36%"></i></span></td></tr>
<tr><td>vol short</td><td class="r num">-0.05</td><td class="r num">0.25</td>
<td><span class="bar" style="width:64px;display:inline-block"><i style="width:20%"></i></span></td></tr>
</table>"""
    conc = """<table>
<tr><th>instrument</th><th class="r">share</th><th>limit</th></tr>
<tr><td>BTCUSDT</td><td class="r num">38%</td><td><span class="badge warn">LIMIT 40%</span></td></tr>
<tr><td>ETHUSDT</td><td class="r num">19%</td><td><span class="badge pos">LIMIT 40%</span></td></tr>
<tr><td>EURUSD</td><td class="r num">13%</td><td><span class="badge pos">LIMIT 40%</span></td></tr>
</table>"""
    stress = """<table>
<tr><th>scenario</th><th class="r">reprice</th><th class="r">DD after</th><th>calibration</th></tr>
<tr><td>crypto -2σ joint</td><td class="r num neg">-2,140</td><td class="r num">-8.6%</td><td><span class="badge pos">CALIBRATED</span></td></tr>
<tr><td>liquidity stress 4h</td><td class="r num neg">-640</td><td class="r num">-5.5%</td><td><span class="badge warn">UNDER-SAMPLED</span></td></tr>
</table>"""
    limits = """<table>
<tr><th>limit</th><th class="r">value</th><th class="r">used</th><th>state</th><th>owner</th><th>change</th></tr>
<tr><td>daily loss</td><td class="r num">-1,400</td><td class="r num">31%</td><td><span class="badge pos">OK</span></td><td>owner</td><td><u>chg#44</u></td></tr>
<tr><td>gross exposure</td><td class="r num">52,000</td><td class="r num">64%</td><td><span class="badge warn">WATCH</span></td><td>owner</td><td><u>chg#41</u></td></tr>
<tr><td>per-instrument conc</td><td class="r num">40%</td><td class="r num">38%</td><td><span class="badge warn">WATCH</span></td><td>owner</td><td><u>chg#39</u></td></tr>
<tr><td>max drawdown</td><td class="r num">-10%</td><td class="r num">-4.2%</td><td><span class="badge pos">OK</span></td><td>owner</td><td><u>chg#12</u></td></tr>
</table>
<div class="cap" style="margin-top:6px">limits are owner-set only; every change carries an audit
entry; the risk engine is independent and fail-closed — model confidence cannot widen a limit</div>"""
    return (region(6, "Consolidated accounts", accounts, "") +
            region(6, "Factor exposures", factors, "") +
            region(6, "Concentration", conc, "") +
            region(6, "Stress repricing", stress, "p11") +
            region(12, "Risk limits ledger", limits, "owner-set · audited", specimen=False))


def risk_ctx() -> str:
    return f"""
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">equity & drawdown curves</span></div>
{EQUITY_SVG}
<div class="cap" style="margin-top:6px">gross vs net separated; fees/funding/slippage shown in the
net line (docs/03 §8); annotations link to trade records</div></div>"""


def history_main() -> str:
    fills = """<table>
<tr><th>ts (UTC)</th><th>order</th><th>instrument</th><th>side</th><th class="r">qty</th>
<th class="r">price</th><th class="r">fee</th><th class="r">slip bps</th><th>venue</th></tr>
<tr><td class="num">13:58:04</td><td class="num">#511</td><td>ETHUSDT</td><td>SHORT</td>
<td class="r num">1.800</td><td class="r num">3,512.4</td><td class="r num">0.42</td>
<td class="r num">-1.1</td><td>OKX</td></tr>
<tr><td class="num">13:12:41</td><td class="num">#508</td><td>BTCUSDT</td><td>LONG</td>
<td class="r num">0.250</td><td class="r num">66,980.0</td><td class="r num">1.05</td>
<td class="r num">+0.4</td><td>BYBIT</td></tr>
</table>"""
    perf = """<table>
<tr><th>metric</th><th class="r">value</th><th class="r">benchmark</th></tr>
<tr><td>return 30d</td><td class="r num pos">+3.8%</td><td class="r num">+1.1%</td></tr>
<tr><td>max DD 30d</td><td class="r num">-4.2%</td><td class="r num">-6.0%</td></tr>
<tr><td>sharpe (cost-adj)</td><td class="r num">1.24 [0.7–1.7]</td><td class="r num">0.41</td></tr>
<tr><td>costs 30d</td><td class="r num">84.10</td><td class="r num">—</td></tr>
</table>
<div class="cap" style="margin-top:6px">attribution by strategy + venue; costs broken into
fees / funding / slippage</div>"""
    calib = """<table>
<tr><th>predicted band</th><th class="r">realized within</th><th>state</th></tr>
<tr><td>confidence 0.6–0.8</td><td class="r num">71%</td><td><span class="badge pos">CALIBRATED</span></td></tr>
<tr><td>vol forecast ±</td><td class="r num">within 1σ 82%</td><td><span class="badge pos">CALIBRATED</span></td></tr>
<tr><td>liquidity stress</td><td class="r num">n=6</td><td><span class="badge warn">UNDER-SAMPLED</span></td></tr>
</table>"""
    audit = """<table>
<tr><th>ts</th><th>kind</th><th>record</th><th>actor</th></tr>
<tr><td class="num">14:12</td><td><span class="badge neg">DECISION</span></td><td>reject candidate #88 RC-201</td><td>risk engine</td></tr>
<tr><td class="num">13:58</td><td><span class="badge pos">APPROVAL</span></td><td>paper order #512 intent hash 9c2e…</td><td>owner (MFA)</td></tr>
<tr><td class="num">13:58</td><td><span class="badge info">ORDER</span></td><td>#511 fill · venue ack 77118</td><td>executor</td></tr>
<tr><td class="num">12:40</td><td><span class="badge warn">INCIDENT</span></td><td>dukascopy throttle · feed barred 6m</td><td>ingestion</td></tr>
</table>
<div class="cap" style="margin-top:6px">time-ordered research · decisions · approvals · orders ·
fills · changes · incidents; replay selector + export CSV/PNG; immutable, append-only</div>"""
    return (region(12, "Fills", fills, "venue-reported") +
            region(6, "Performance & attribution", perf, "p12") +
            region(6, "Calibration", calib, "shown, never hidden") +
            region(12, "Audit & replay", audit, "p13 · append-only"))


def history_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">export</span></div>
<div class="cap"><span class="btn">CSV</span> <span class="btn">PNG</span> filters: kind · venue ·
window · actor</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">retention</span></div>
<div class="cap">per mandate + Settings policy; exports carry provenance header (window, filters,
data status)</div></div>"""


def shell(active: str, main: str, ctx: str) -> str:
    return (f'<div class="shell">{TOPBAND}<div class="rail">{nav(active)}</div>'
            f'<div class="main">{main}</div><div class="ctx">{ctx}</div></div>')


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 3.4 Trading, Strategy, Risk, History</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 3 &middot; sub-deliverable 3.4</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Open Positions · Strategy Laboratory · Portfolio &amp; Risk · Trade History</h1>
<div class="ribbon">DESIGN SPECIMEN — labelled placeholders for review; production renders only
real or labelled-simulated data. Numeric regions carry the SPECIMEN tag; governance regions
(limits, reconciliation policy) carry rules, not numbers.</div>

<h2><span class="num">01</span>Open Positions (p8 positions + p9 execution room)</h2>
{shell("Open Positions", positions_main(), positions_ctx())}
<p class="cap">Protective-order state and fills are venue-reported; unmatched reconciliation rows
block new risk on that instrument; the kill switch shows its exact scope before any confirm
(docs/03 J-03).</p>

<h2><span class="num">02</span>Strategy Laboratory (p7 + p11)</h2>
{shell("Strategy Laboratory", lab_main(), lab_ctx())}
<p class="cap">Cost-adjusted metrics with confidence intervals, never hit-rate rankings; promotion
gates explicit with the owner-approval gate last; experimental strategies never auto-promote.</p>

<h2><span class="num">03</span>Portfolio &amp; Risk (p8 + p11)</h2>
{shell("Portfolio & Risk", risk_main(), risk_ctx())}
<p class="cap">Limits are owner-set only and every change carries an audit entry; the independent
fail-closed risk engine cannot be widened by model confidence; equity/drawdown curves separate
gross from net with fees, funding and slippage shown.</p>

<h2><span class="num">04</span>Trade History (p12 + p13 + p9 fills)</h2>
{shell("Trade History", history_main(), history_ctx())}
<p class="cap">Append-only audit stream across research, decisions, approvals, orders, fills,
changes and incidents; calibration is shown including under-sampled cases; exports carry a
provenance header.</p>
<footer>Stage 3.4 &middot; approved shell (D-033), tokens (D-032), specimen policy (D-034),
§7/intent chrome (D-035) &middot; batch 3.5 next on approval.</footer>
</div></body></html>"""
    out = HERE / "stage3-4-trading-risk-history.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
