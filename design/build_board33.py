"""Stage 3.3 board: Intelligence Centre + Trade Opportunities interiors.

Reuses the 3.2 shell helpers; self-contained; specimen-tagged like 3.2.

Run:  backend/.venv/bin/python design/build_board33.py
"""

from __future__ import annotations

import pathlib
import re

from build_board32 import CSS as CSS32, TOPBAND, nav, region
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent

CSS = CSS32 + """
.btn { display:inline-flex; align-items:center; gap:6px; padding: 4px 12px;
  border-radius: var(--radius-control); border: 1px solid var(--color-border-strong);
  background: transparent; color: var(--color-text-primary);
  font: var(--font-weight-medium) var(--font-size-data)/1.4 var(--font-family-sans); }
.btn.primary { border-color: var(--color-feedback-info-graphic);
  color: var(--color-feedback-info-text); }
.btn.danger { border-color: var(--color-feedback-negative-graphic);
  color: var(--color-feedback-negative-text); }
.meter { height: 6px; border-radius: 3px; background: var(--color-surface-elevated);
  position: relative; margin: 4px 0; }
.meter i { position:absolute; inset:0 auto 0 0; border-radius:3px;
  background: var(--color-feedback-intelligence-graphic); }
.tier { display:inline-block; min-width: 34px; text-align:center; padding: 1px 6px;
  border-radius: 3px; background: var(--color-surface-elevated);
  font: var(--font-weight-medium) 10px/1.5 var(--font-family-mono); letter-spacing: .06em;
  color: var(--color-text-secondary); }
.cycle { display:inline-flex; gap:3px; }
.cycle b { font: var(--font-weight-medium) 9px/1.6 var(--font-family-mono); letter-spacing:.04em;
  padding: 1px 5px; border-radius: 3px; background: var(--color-surface-elevated);
  color: var(--color-text-muted); }
.cycle b.on { background: var(--color-feedback-intelligence-subtle);
  color: var(--color-feedback-intelligence-text); }
"""

GRAPH = """
<svg viewBox="0 0 460 190" style="width:100%;background:var(--color-surface-canvas);
border:1px solid var(--color-border-subtle);border-radius:var(--radius-control)" role="img">
  <g font-family="Inter" font-size="8.5" fill="var(--color-text-secondary)">
    <line x1="120" y1="60" x2="230" y2="40" stroke="var(--color-border-strong)"/>
    <line x1="120" y1="60" x2="230" y2="95" stroke="var(--color-border-strong)"/>
    <line x1="230" y1="40" x2="340" y2="68" stroke="var(--color-border-strong)"/>
    <line x1="230" y1="95" x2="340" y2="68" stroke="var(--color-border-strong)"/>
    <line x1="230" y1="95" x2="340" y2="140" stroke="var(--color-feedback-warning-graphic)" stroke-dasharray="4 3"/>
    <line x1="120" y1="140" x2="230" y2="95" stroke="var(--color-border-strong)"/>
  </g>
  <g font-family="Inter" font-size="8.5">
    <rect x="30" y="46" width="90" height="28" rx="4" fill="var(--color-feedback-intelligence-subtle)"/>
    <text x="38" y="63" fill="var(--color-feedback-intelligence-text)">CLAIM: funding reset
      </text>
    <text x="38" y="72" fill="var(--color-feedback-intelligence-text)">mean-reverts &lt; 2h</text>
    <rect x="30" y="126" width="90" height="28" rx="4" fill="var(--color-feedback-intelligence-subtle)"/>
    <text x="38" y="143" fill="var(--color-feedback-intelligence-text)">CLAIM: depth recovers</text>
    <text x="38" y="152" fill="var(--color-feedback-intelligence-text)">post-outage ~40m</text>
    <rect x="185" y="26" width="90" height="26" rx="4" fill="var(--color-feedback-info-subtle)"/>
    <text x="193" y="42" fill="var(--color-feedback-info-text)">SRC: binance fills #8812</text>
    <rect x="185" y="82" width="90" height="26" rx="4" fill="var(--color-feedback-info-subtle)"/>
    <text x="193" y="98" fill="var(--color-feedback-info-text)">SRC: okx depth stream</text>
    <rect x="300" y="54" width="90" height="26" rx="4" fill="var(--color-surface-elevated)"/>
    <text x="308" y="70" fill="var(--color-text-primary)">ASSET: BTCUSDT</text>
    <rect x="300" y="126" width="90" height="26" rx="4" fill="var(--color-feedback-warning-subtle)"/>
    <text x="308" y="142" fill="var(--color-feedback-warning-text)">CONTRADICTION #7</text>
  </g>
  <g font-family="JetBrains Mono, monospace" font-size="7.5" fill="var(--color-text-muted)">
    <text x="128" y="36">supports</text><text x="250" y="36">about</text>
    <text x="240" y="120">conflicts</text>
  </g>
</svg>"""


def intelligence_main() -> str:
    attn = """<table>
<tr><th>#</th><th>attention item</th><th>why now</th><th>depth</th><th>cycle</th></tr>
<tr><td class="num">1</td><td>OKX depth recovery post-outage</td>
    <td><span class="badge warn">EVENT</span> <span class="badge intel">UNCERTAINTY</span></td>
    <td><span class="tier">T3</span></td>
    <td><span class="cycle"><b>OB</b><b>AN</b><b class="on">RS</b><b>VF</b><b>DC</b><b>LE</b></span></td></tr>
<tr><td class="num">2</td><td>BTC funding reset 16:00 UTC</td>
    <td><span class="badge intel">NOVELTY</span></td>
    <td><span class="tier">T2</span></td>
    <td><span class="cycle"><b class="on">OB</b><b>AN</b><b>RS</b><b>VF</b><b>DC</b><b>LE</b></span></td></tr>
<tr><td class="num">3</td><td>EURUSD london-open imbalance</td>
    <td><span class="badge intel">UNCERTAINTY</span></td>
    <td><span class="tier">T4</span></td>
    <td><span class="cycle"><b>OB</b><b>AN</b><b>RS</b><b class="on">VF</b><b>DC</b><b>LE</b></span></td></tr>
</table>
<div class="cap" style="margin-top:6px">research depth Tier 0–4 · cycle OB→AN→RS→VF→DC→LE
(observe→analyse→research→verify→decide→learn) · prioritisation reasons shown, never implicit</div>"""
    tools = """<table>
<tr><td class="num">14:31</td><td>depth-scanner · okx</td><td>resampled book @1s</td><td><span class="badge pos">OK</span></td></tr>
<tr><td class="num">14:28</td><td>funding-watch · binance</td><td>next reset 16:00 UTC</td><td><span class="badge pos">OK</span></td></tr>
<tr><td class="num">14:19</td><td>news-screener · rss set A</td><td>3 items scored &lt; threshold</td><td><span class="badge mute">DROPPED</span></td></tr>
<tr><td class="num">14:02</td><td>dukascopy fx · ticks</td><td>throttled (503)</td><td><span class="badge warn">RETRYING</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">tool allowlist + source registry enforced; every line links
to its run record</div>"""
    beliefs = """<table>
<tr><th>belief</th><th class="r">confidence</th><th>valid until</th><th>changes if</th><th></th></tr>
<tr><td>BTC funding reset mean-reverts &lt; 2h</td><td class="r num">0.68 [0.57–0.77]</td>
    <td class="num">18:00 UTC</td><td>flip of funding sign twice</td><td></td></tr>
<tr><td>OKX depth recovers ~40m post-outage</td><td class="r num">0.61 [0.48–0.74]</td>
    <td class="num">15:10 UTC</td><td>depth &lt; 1.2× baseline at 15:10</td><td><span class="badge warn">⚠ CONTRA #7</span></td></tr>
<tr><td>EURUSD bias soft-long into LDN</td><td class="r num">0.55 [0.44–0.66]</td>
    <td class="num">09:30 UTC</td><td>UK gilts auction surprise</td><td></td></tr>
</table>
<div class="cap" style="margin-top:6px">confidence always a band with validity interval and change
conditions — a point estimate without them is a defect</div>"""
    scenarios = """<table>
<tr><th>scenario</th><th class="r">probability range</th><th>calibration</th></tr>
<tr><td>vol compression into US open</td><td class="r num">0.35–0.50</td><td><span class="badge pos">CALIBRATED</span></td></tr>
<tr><td>liquidity stress (spread &gt; 3×)</td><td class="r num">0.05–0.12</td><td><span class="badge warn">UNDER-SAMPLED</span></td></tr>
</table>"""
    dossier = f"""<div class="grid2">
<div>{GRAPH}
<div class="cap" style="margin-top:6px">evidence graph: claims ↔ sources ↔ assets ↔ decisions;
contradictions highlighted and linked (#7), never silently averaged away</div></div>
<div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">chronology</div>
<div class="cap mono">13:41 outlier cluster · 13:52 depth drop · 14:02 feed throttle ·
14:19 contra-source found · 14:31 depth recovering</div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase;margin-top:8px">counter-thesis</div>
<div class="cap">recovery is venue-specific re-stocking, not genuine liquidity return — would
show as spread recovery lagging depth by &gt; 5m (watching)</div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase;margin-top:8px">quant result</div>
<div class="cap">n=41 similar events · median recovery 38m IQR [24–61] · <u>run#45729297881</u></div>
<div style="margin-top:8px"><span class="badge intel">DISPOSITION: WAIT</span>
<span class="cap">freshness 14:31:52 UTC · reason code RC-114 evidence-incomplete</span></div>
</div></div>"""
    memory = """<div style="display:flex;gap:6px;margin-bottom:8px">
<span class="btn primary">search memory…</span><span class="tier">EPISODIC</span>
<span class="tier">SEMANTIC</span><span class="tier">PROCEDURAL</span></div>
<table>
<tr><td>expiring</td><td>okx outage topology note</td><td class="r num">TTL 6h</td></tr>
<tr><td>correction</td><td>funding persistence prior widened after #2201</td><td class="r num">14:05</td></tr>
<tr><td>procedural</td><td>throttle backoff for dukascopy = 90s exponential</td><td class="r num">v3</td></tr>
</table>
<div class="cap" style="margin-top:6px">every memory update carries provenance; corrections are
first-class entries, not overwrites</div>"""
    decisions = """<div style="display:flex;gap:8px;flex-wrap:wrap">
<span class="badge pos">ACCEPT</span><span class="badge neg">REJECT</span>
<span class="badge warn">WAIT</span><span class="badge warn">REDUCE</span>
<span class="badge neg">EXIT</span><span class="badge info">ESCALATE</span>
<span class="badge mute">ABSTAIN</span></div>
<div class="cap" style="margin-top:6px">the complete decision vocabulary (docs/03 §7), each with a
reason code; recent: 14:12 REJECT RC-201 risk-check-failed · 13:58 ACCEPT RC-010 mandate-within-limits</div>"""
    return (region(7, "Attention priorities", attn, "why-now explicit") +
            region(5, "Current tasks · tool activity", tools, "allowlist enforced") +
            region(7, "Beliefs & uncertainty", beliefs, "bands + validity + change conditions") +
            region(5, "Scenario status", scenarios, "calibration shown") +
            region(7, "Dossier #2211 — funding reset", dossier, "p5 view", specimen=True) +
            region(5, "Memory & knowledge", memory, "p6 view") +
            region(12, "Decision states", decisions, "with reason codes", specimen=False))


def intelligence_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">knowledge sufficiency</span></div>
<div class="cap">task: OKX depth recovery</div><div class="meter"><i style="width:72%"></i></div>
<div class="cap">0.72 — sufficient for VERIFY, not for DECIDE<br>basis: 41 events · 2 sources · 1 contra open</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">research depth tiers</span></div>
<div class="cap">T0 glance · T1 scan · T2 correlate · T3 test · T4 full dossier</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">audit posture</span></div>
<div class="cap">no hidden chain-of-thought: auditable evidence + structured findings + concise
rationale only (docs/03 §7)</div></div>"""


def opportunities_main() -> str:
    queue = """<table>
<tr><th>#</th><th>instrument · venue</th><th>side</th><th>thesis</th><th>V1</th><th>V2</th><th>V3</th>
    <th class="r">worst case</th><th class="r">expiry</th><th></th></tr>
<tr><td class="num">1</td><td>BTCUSDT · BYBIT</td><td>LONG</td><td>mean-reversion post-liquidation cluster</td>
    <td><span class="badge pos">PASS</span></td><td><span class="badge pos">PASS</span></td>
    <td><span class="badge pos">PASS</span></td><td class="r num">-184.20</td><td class="num">16:40 UTC</td>
    <td><span class="btn primary">review</span></td></tr>
<tr><td class="num">2</td><td>EURUSD · FX-EDGE</td><td>LONG</td><td>session-open imbalance, liquidity void above</td>
    <td><span class="badge pos">PASS</span></td><td><span class="badge warn">PENDING</span></td>
    <td><span class="badge mute">—</span></td><td class="r num">—</td><td class="num">09:20 UTC</td>
    <td><span class="btn">watch</span></td></tr>
<tr><td class="num">3</td><td>ETHUSDT · OKX</td><td>SHORT</td><td>funding-extreme fade</td>
    <td><span class="badge pos">PASS</span></td><td><span class="badge neg">FAIL RC-201</span></td>
    <td><span class="badge mute">—</span></td><td class="r num">—</td><td class="r">—</td>
    <td><span class="btn">archived</span></td></tr>
</table>
<div class="cap" style="margin-top:6px">V1 evidence &amp; data sufficiency · V2 risk &amp; mandate
compliance · V3 execution safety (stage definitions finalise at Stage 11; chrome reserved here).
A FAIL at any stage ends the candidate — confidence never overrides it.</div>"""
    detail = """<div class="grid2">
<div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">evidence summary</div>
<div class="cap">· liquidation cluster 66,850–66,920 absorbed 14:02–14:11 (<u>fills#8812</u>)<br>
· depth 1.8× baseline at ±0.4% (<u>depth-run#4471</u>)<br>· funding reset 16:00 UTC removes carry headwind (<u>dossier#2211</u>)</div>
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase;margin-top:8px">counter-case</div>
<div class="cap">recovery may be re-stocking, not liquidity return — spread recovery lag &gt; 5m
invalidates entry timing (mitigation: enter on spread confirmation)</div>
</div>
<div>
<table>
<tr><td>side / size</td><td class="r num">LONG 0.050 BTC</td></tr>
<tr><td>est cost (fees+spread+slip)</td><td class="r num">3.90</td></tr>
<tr><td>worst-case loss (stop honoured)</td><td class="r num neg">-184.20</td></tr>
<tr><td>portfolio impact</td><td class="r num">gross +0.8% · conc +1.1%</td></tr>
<tr><td>stop / exit plan</td><td class="r num">66,780 / 16:40 UTC flat</td></tr>
</table>
<div style="display:flex;gap:8px;margin-top:10px">
<span class="btn primary">approve → paper</span><span class="btn danger">reject</span><span class="btn">defer</span></div>
<div class="cap" style="margin-top:6px">approval binds to this exact immutable intent (docs/03 §5);
any material change invalidates it. Interaction + step-up flows arrive at Stage 4.</div>
</div></div>"""
    states = """<div class="region" style="border:0;padding:0;background:transparent">
<div class="cap" style="margin:8px 0">◇ &nbsp;No justified opportunities — NEXUS is watching
12 instruments. <u>see Overview no-trade region</u></div>
<div class="badge warn" style="margin:6px 0">RESEARCH ENGINE DEGRADED</div>
<div class="cap">cause: model registry reload · queue frozen, no new candidates · [view status]</div>
<div class="skel" style="width:80%;margin-top:10px"></div><div class="skel" style="width:60%"></div>
<div class="cap">verifying candidate 2 of 3…</div></div>"""
    return (region(12, "Verified candidate queue", queue, "verification-gated") +
            region(8, "Candidate #1 — full intent", detail, "approval-binding fields") +
            region(4, "Queue states", states, "", specimen=False))


def opportunities_ctx() -> str:
    return """
<div class="cap" style="letter-spacing:.05em;text-transform:uppercase">context rail</div>
<div class="region" style="margin-top:8px"><span class="spec">SPECIMEN</span>
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">verification trail #1</span></div>
<div class="cap mono">V1 14:22:04 pass · feeds live, depth entitled<br>
V2 14:24:41 pass · limits, mandate, concentration<br>V3 14:25:02 pass · venue reachable, idempotency key minted</div></div>
<div class="region" style="margin-top:8px">
<div class="rh"><span class="t" style="font-size:var(--font-size-data)">mandate checks</span></div>
<div class="cap"><span class="badge pos">PAPER-ONLY</span> environment SHADOW → approval routes to
paper execution; live authority DENIED (smoke evidence)</div></div>"""


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    intel = f"""<div class="shell">{TOPBAND}
<div class="rail">{nav("Intelligence Centre")}</div>
<div class="main">{intelligence_main()}</div>
<div class="ctx">{intelligence_ctx()}</div></div>"""
    opps = f"""<div class="shell">{TOPBAND}
<div class="rail">{nav("Trade Opportunities")}</div>
<div class="main">{opportunities_main()}</div>
<div class="ctx">{opportunities_ctx()}</div></div>"""
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 3.3 Intelligence & Opportunities</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 3 &middot; sub-deliverable 3.3</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Intelligence Centre &amp; Trade Opportunities — screen interiors</h1>
<div class="ribbon">DESIGN SPECIMEN — labelled placeholders for review; production renders only
real or labelled-simulated data. Numeric regions carry the SPECIMEN tag.</div>

<h2><span class="num">01</span>Intelligence Centre (docs/03 p4+p5+p6)</h2>
{intel}
<p class="cap">Every §7 requirement has chrome: tasks + attention with explicit why-now and depth
Tier 0–4; cycle position per task; tool allowlist/source registry lines; beliefs as bands with
validity intervals and change conditions; contradictions highlighted in the evidence graph, never
averaged away; memory updates with provenance and first-class corrections; the full decision
vocabulary with reason codes. No hidden chain-of-thought anywhere.</p>

<h2><span class="num">02</span>Trade Opportunities</h2>
{opps}
<p class="cap">The queue is verification-gated: three stages, any FAIL ends the candidate and the
row says why (reason code). The expanded intent carries exactly the approval-binding fields of
docs/03 §5 — instrument, venue, side, size, cost, worst case, impact, evidence, counter-case,
stop/exit, expiry — because approval will bind to this immutable intent at Stage 4. Environment
SHADOW routes any approval to paper; live authority stays DENIED until the owner authorises.</p>
<footer>Stage 3.3 &middot; composes inside the approved shell (D-033) with approved tokens (D-032)
and the 3.2 specimen policy (D-034) &middot; batch 3.4 next on approval.</footer>
</div></body></html>"""
    out = HERE / "stage3-3-intelligence-opportunities.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
