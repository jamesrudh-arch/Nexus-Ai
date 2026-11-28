"""Stage 3.5 board: System Health, Settings & Controls, mobile control surface.

Reuses 3.2/3.3 shell helpers; self-contained; specimen-tagged per D-034.

Run:  backend/.venv/bin/python design/build_board35.py
"""

from __future__ import annotations

import pathlib
import re

from build_board32 import CSS as CSS32, TOPBAND, nav, region
from build_board33 import CSS as CSS33
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS33 + """
.phone { width: 340px; margin: 0 auto; border: 1px solid var(--color-border-strong);
  border-radius: 22px; overflow: hidden; background: var(--color-surface-canvas);
  display: grid; grid-template-rows: 36px 1fr 52px; }
.phone .ptop { display:flex; align-items:center; gap:6px; padding: 0 10px;
  background: var(--color-surface-panel); border-bottom: 1px solid var(--color-border-subtle); }
.phone .pbody { padding: 12px; overflow: hidden; }
.phone .ptabs { display:grid; grid-template-columns: repeat(5,1fr);
  background: var(--color-surface-panel); border-top: 1px solid var(--color-border-subtle); }
.phone .ptab { display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:2px; color: var(--color-text-muted);
  font: var(--font-weight-medium) 9px/1.2 var(--font-family-sans); letter-spacing:.04em; }
.phone .ptab.on { color: var(--color-text-primary); }
.envladder { display:flex; gap:4px; flex-wrap:wrap; }
.envladder b { font: var(--font-weight-medium) 10px/1.7 var(--font-family-mono);
  letter-spacing:.06em; padding: 2px 8px; border-radius: 3px;
  background: var(--color-surface-elevated); color: var(--color-text-muted); }
.envladder b.on { background: var(--color-feedback-intelligence-subtle);
  color: var(--color-feedback-intelligence-text); }
.envladder b.lock { border: 1px dashed var(--color-feedback-negative-graphic);
  color: var(--color-feedback-negative-text); background: transparent; }
"""


def health_main() -> str:
    feeds = """<table>
<tr><th>venue / feed</th><th>adapter</th><th>coverage</th><th>freshness</th>
<th class="r">latency</th><th class="r">last sync</th><th>entitlements</th></tr>
<tr><td>binance spot</td><td>v1.4.2</td><td><span class="badge pos">LIVE-VERIFIED</span></td>
<td><span class="badge pos">LIVE</span></td><td class="r num">84 ms</td><td class="r num">14:32:04</td>
<td>klines · depth · trades</td></tr>
<tr><td>okx spot</td><td>v1.4.2</td><td><span class="badge pos">TRADE-ENABLED</span></td>
<td><span class="badge pos">LIVE</span></td><td class="r num">112 ms</td><td class="r num">14:32:02</td>
<td>klines · depth · trades</td></tr>
<tr><td>dukascopy fx</td><td>v0.9.7</td><td><span class="badge info">DATA-AVAILABLE</span></td>
<td><span class="badge warn">STALE 45s</span></td><td class="r num">—</td><td class="r num">14:31:20</td>
<td>ticks (throttling: 503)</td></tr>
<tr><td>bybit v5</td><td>v1.4.2</td><td><span class="badge mute">CONNECTED</span></td>
<td><span class="badge neg">GEO-BLOCKED</span></td><td class="r num">—</td><td class="r num">—</td>
<td>public only · 403 from runner region</td></tr>
</table>
<div class="cap" style="margin-top:6px">coverage states come from the capability registry
(docs/03 §3.4); a compromised or stale feed is barred from the decision pipeline while its badge
shows why — states are measured, never asserted</div>"""
    alerts = """<table>
<tr><th>sev</th><th>kind</th><th>subject</th><th>state</th><th></th></tr>
<tr><td><span class="badge neg">CRIT</span></td><td>stale source</td><td>dukascopy fx &gt; 60s — new FX risk blocked</td>
<td><span class="badge warn">ACK</span></td><td><u>inc#2214</u></td></tr>
<tr><td><span class="badge warn">WARN</span></td><td>limit watch</td><td>gross exposure 64% of limit</td>
<td><span class="badge mute">NEW</span></td><td><u>lim#41</u></td></tr>
<tr><td><span class="badge warn">WARN</span></td><td>model degradation</td><td>depth-recovery belief contra #7 open</td>
<td><span class="badge mute">NEW</span></td><td><u>case#2211</u></td></tr>
<tr><td><span class="badge info">INFO</span></td><td>delivery</td><td>push channel certificate rotates in 6d</td>
<td><span class="badge pos">RESOLVED</span></td><td><u>ops#88</u></td></tr>
</table>
<div class="cap" style="margin-top:6px">kinds per docs/03 p14: data outages · broker issues · model
degradation · limit breaches · stale sources · delivery status</div>"""
    delivery = """<table>
<tr><td>web push (self-hosted VAPID)</td><td><span class="badge pos">DELIVERING</span></td></tr>
<tr><td>sms fallback</td><td><span class="badge mute">ARMED · unused 30d</span></td></tr>
<tr><td>telegram bridge</td><td><span class="badge info">OPTIONAL · off</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">$0 providers only (D-019); delivery failures raise their
own alert — a silent channel is a defect</div>"""
    incident = """<div class="cap mono">inc#2214 · opened 14:31:20 · dukascopy throttle (503)</div>
<div class="cap" style="margin-top:6px">scope: fx feeds · action: new FX risk blocked 14:31:20 ·
feed barred from pipeline · backoff 90s exponential · reconciliation queued<br>
state: <span class="badge warn">DEGRADED</span> · positions unaffected · owner notified 14:31:22</div>"""
    return (region(12, "Feeds · adapters · entitlements", feeds, "p10 connections", specimen=False) +
            region(8, "Alert triage queue", alerts, "p14") +
            region(4, "Delivery status", delivery, "D-019 $0 channels", specimen=False) +
            region(12, "Incident #2214 timeline", incident, "scope · actions · reconciliation", specimen=False))


def health_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">integrity checks</span></div>
<div class="cap">tick monotonicity · gap scan · cross-venue price bounds · volume spikes —
failed check ⇒ feed barred + CRIT alert; checks themselves are versioned</div></div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">uptime 30d</span></div>
<div class="cap num">binance 99.94% · okx 99.91% · dukascopy 97.2% (throttle-bound)</div></div>"""


def settings_main() -> str:
    authority = """<div class="envladder">
<b>OBSERVE</b><b>RESEARCH</b><b class="on">SHADOW</b><b>PAPER</b><b>PILOT</b><b class="lock">LIVE</b></div>
<div class="cap" style="margin-top:8px">live authority: <span class="badge neg">DENIED</span> —
smoke evidence 2026-11-25 · promotion to PILOT/LIVE requires: owner request + MFA + recorded
mandate + rollback plan + independent risk-engine acknowledgement. The ladder is environment
state (docs/03), never a toggle: no control on this screen can enable live execution.</div>"""
    mandates = """<table>
<tr><th>mandate</th><th class="r">value</th><th>set by</th><th>change</th></tr>
<tr><td>daily loss limit</td><td class="r num">-1,400</td><td>owner</td><td><u>chg#44</u></td></tr>
<tr><td>gross exposure</td><td class="r num">52,000</td><td>owner</td><td><u>chg#41</u></td></tr>
<tr><td>per-instrument concentration</td><td class="r num">40%</td><td>owner</td><td><u>chg#39</u></td></tr>
<tr><td>per-strategy caps</td><td class="r num">see lab</td><td>owner</td><td><u>chg#37</u></td></tr>
</table>
<div class="cap" style="margin-top:6px">forms edit proposals only; application requires explicit
confirm with restated values; every applied change writes an audit entry</div>"""
    sources = """<table>
<tr><th>provider</th><th>role</th><th class="r">cost</th><th>state</th></tr>
<tr><td>binance public data</td><td>crypto klines/depth</td><td class="r num">$0</td><td><span class="badge pos">VERIFIED</span></td></tr>
<tr><td>okx v5</td><td>crypto + paper exec</td><td class="r num">$0</td><td><span class="badge pos">VERIFIED</span></td></tr>
<tr><td>dukascopy bi5</td><td>fx ticks</td><td class="r num">$0</td><td><span class="badge warn">THROTTLED</span></td></tr>
<tr><td>bybit v5</td><td>crypto (geo-blocked)</td><td class="r num">$0</td><td><span class="badge neg">403 REGION</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">D-019 column is mandatory: any proposed source with a cost
is rejected at this screen, not later</div>"""
    registry = """<table>
<tr><th>model / strategy</th><th>hash</th><th>state</th><th>retention</th></tr>
<tr><td>funding-reset MR</td><td class="mono">a41f…</td><td><span class="badge intel">PAPER</span></td><td>versions ∞ · runs 24m</td></tr>
<tr><td>depth-scanner tool</td><td class="mono">9c2e…</td><td><span class="badge pos">ALLOWLISTED</span></td><td>logs 24m</td></tr>
</table>"""
    security = """<table>
<tr><td>MFA</td><td><span class="badge pos">ENFORCED</span> step-up for halt, approvals, mandate changes</td></tr>
<tr><td>api keys</td><td><span class="badge pos">VAULT-ONLY</span> never in chat, repo, logs; redactor tested</td></tr>
<tr><td>sessions</td><td>2 active · revoke-all control</td></tr>
<tr><td>retention</td><td>audit ∞ · ticks 24m · dossiers ∞ · exports on-demand</td></tr>
</table>"""
    return (region(12, "Live authority & environment ladder", authority, "p15 · governance", specimen=False) +
            region(6, "Risk mandates", mandates, "owner-set only") +
            region(6, "Data sources & cost gate", sources, "D-019", specimen=False) +
            region(6, "Model & tool registry", registry, "allowlist + versions") +
            region(6, "Roles & security", security, "", specimen=False))


def settings_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">settings change log</span></div>
<div class="cap mono">chg#44 daily loss -1,400 · owner · MFA · 2026-11-20<br>
chg#41 gross 52,000 · owner · MFA · 2026-11-18<br>chg#40 paper-only route · owner · 2026-11-17</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">governance rule</span></div>
<div class="cap">configuration changes are decisions: they carry actor, auth method, restated
values and rollback — identical chrome to trade decisions</div></div>"""


def mobile() -> str:
    body = """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">command · compact</div>
<div class="display" style="font-size:var(--font-size-heading);margin-top:4px">48,210.66 <span class="cap">USDT</span></div>
<div class="cap mono pos">+1,842.10 realized · <span class="neg">-204.08 unrealized</span></div>
<div style="display:flex;gap:8px;margin-top:10px">
<div class="region" style="flex:1"><div class="cap">exposure</div><div class="num">33,724 / 52,000</div></div>
<div class="region" style="flex:1"><div class="cap">feeds</div><div class="cap"><span class="badge pos">3 LIVE</span> <span class="badge warn">1 STALE</span></div></div>
</div>
<div style="margin-top:10px"><span class="btn danger" style="width:100%;justify-content:center">EMERGENCY HALT</span></div>
<div class="cap" style="margin-top:6px">tap 1 = this button · tap 2 = confirmation modal with full
scope + MFA (docs/03 §9: never a tiny ambiguous tap)</div>
<div class="region" style="margin-top:10px"><div class="cap">positions 3 · protectives venue-set 2 ·
pending 1 · <u>drill</u></div></div>
<div class="region" style="margin-top:8px"><div class="cap"><span class="badge intel">NO-TRADE</span>
watching 12 instruments · funding reset 16:00 · <u>why</u></div></div>
<div class="badge warn" style="margin-top:10px">OFFLINE — cached read-only 14:29 UTC · no order
submission</div>"""
    tabs = "".join(
        f'<div class="ptab{" on" if t == "Command" else ""}">'
        f'<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" '
        f'stroke-width="1.4">{i}</svg>{t}</div>'
        for t, i in (("Command", '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>'),
                     ("Markets", '<path d="M2 12 L6 7 L9 9.5 L14 3"/>'),
                     ("Positions", '<path d="M3 4 H13"/><path d="M3 8 H13"/><path d="M3 12 H9"/>'),
                     ("Alerts", '<path d="M8 3 L13 12 H3 Z"/>'),
                     ("More", '<circle cx="4" cy="8" r="1"/><circle cx="8" cy="8" r="1"/><circle cx="12" cy="8" r="1"/>')))
    return f"""<div class="phone">
<div class="ptop"><span class="badge intel">SHADOW</span><span class="chip" style="padding:1px 7px">HALT OFF</span>
<span class="clock" style="font-size:10px">14:32 UTC</span></div>
<div class="pbody">{body}</div>
<div class="ptabs">{tabs}</div></div>"""


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    health = (f'<div class="shell">{TOPBAND}<div class="rail">{nav("System Health")}</div>'
              f'<div class="main">{health_main()}</div><div class="ctx">{health_ctx()}</div></div>')
    settings = (f'<div class="shell">{TOPBAND}<div class="rail">{nav("Settings & Controls")}</div>'
                f'<div class="main">{settings_main()}</div><div class="ctx">{settings_ctx()}</div></div>')
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 3.5 Health, Settings, Mobile</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 3 &middot; sub-deliverable 3.5 (final batch)</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
System Health · Settings &amp; Controls · mobile control surface</h1>
<div class="ribbon">DESIGN SPECIMEN — labelled placeholders for review. Governance and security
regions carry rules and measured-state chrome, not invented numbers; where states reference real
evidence (geo-block, throttle, DENIED live authority) they cite it.</div>

<h2><span class="num">01</span>System Health (p14 + p10)</h2>
{health}
<p class="cap">Coverage states come from the capability registry and are measured, never asserted;
the bybit row shows a real, cited condition (403 from hosted-runner region) rather than a painted
green tick. Integrity checks that bar a compromised feed are themselves versioned.</p>

<h2><span class="num">02</span>Settings &amp; Controls (p15)</h2>
{settings}
<p class="cap">The environment ladder is state, not a toggle: no control on this screen can enable
live execution — promotion requires owner request, MFA, recorded mandate, rollback plan and the
independent risk engine's acknowledgement. The D-019 cost column rejects paid sources at this
screen. Configuration changes carry the same decision chrome as trades.</p>

<h2><span class="num">03</span>Mobile control surface (docs/03 §9)</h2>
<div class="grid2">
<div>{mobile()}
<p class="cap">Control + monitoring, not compute: compact hierarchy, halt in two taps with full
scope + MFA, offline = cached read-only with stale badge and no order submission. Deep charting
and complex configuration defer to responsive desktop.</p></div>
<div><div class="card">
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">mobile must-support (docs/03 §9)</div>
<div class="cap" style="margin-top:6px">biometrics + MFA auth · live status · approvals with full
intent + step-up · account monitoring · emergency halt ≤2 taps · incident alerts · research
summaries. May defer: deep charting, complex configuration.<br><br>
Bottom tabs fixed: Command · Markets · Positions · Alerts · More. Top band keeps environment,
halt and UTC clock at 36px. Every state chrome from §5 applies per region on mobile too.</div>
</div></div></div>
<footer>Stage 3.5 &middot; completes the ten screens + mobile surface inside the approved shell
(D-033) with approved tokens (D-032), specimen policy (D-034), §7/intent chrome (D-035) and
governance chrome (D-036) &middot; Stage 3 now complete pending stage-level approval.</footer>
</div></body></html>"""
    out = HERE / "stage3-5-health-settings-mobile.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
