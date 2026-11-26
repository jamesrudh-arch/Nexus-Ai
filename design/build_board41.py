"""Stage 4.1 board: interaction system — states, confirmations, halt flow, palette,
keyboard, motion, alerts/a11y.

Run:  backend/.venv/bin/python design/build_board41.py
"""

from __future__ import annotations

import pathlib
import re

from build_board32 import CSS as CSS32
from build_board33 import CSS as CSS33
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS33 + """
.backdrop { background: color-mix(in srgb, var(--color-surface-canvas) 72%, transparent);
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-overlay);
  padding: 26px; display: flex; align-items: center; justify-content: center; position: relative; }
.backdrop::before { content: "backdrop · page aria-hidden · focus trapped";
  position: absolute; top: 8px; left: 12px; font: var(--font-weight-medium) 9px/1
  var(--font-family-mono); letter-spacing: .08em; color: var(--color-text-muted); }
.modal { width: 560px; background: var(--color-surface-elevated);
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-overlay);
  box-shadow: var(--elevation-3); padding: 16px; }
.modal .mh { display: flex; align-items: center; gap: 8px; }
.modal .mh .t { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold); }
.steps { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
.step { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-card); padding: 10px; position: relative; }
.step .n { position: absolute; top: -9px; left: 10px; background: var(--color-surface-elevated);
  border: 1px solid var(--color-border-strong); border-radius: 999px; padding: 0 8px;
  font: var(--font-weight-semibold) 10px/1.6 var(--font-family-mono); }
.kbd { display: inline-block; padding: 1px 6px; border: 1px solid var(--color-border-strong);
  border-bottom-width: 2px; border-radius: 4px; background: var(--color-surface-elevated);
  font: var(--font-weight-medium) 10px/1.6 var(--font-family-mono); color: var(--color-text-primary); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-gutter); }
"""


def state_machine() -> str:
    rows = [
        ("default", "border.subtle · text.primary/secondary per role", "—"),
        ("hover", "border.strong · text.primary · cursor pointer on interactive only", "120ms"),
        ("focus-visible", "2px outline color.focus, offset 2 — monochrome (D-031)", "instant"),
        ("active/pressed", "surface.elevated · no scale, no glow", "120ms"),
        ("selected/active-nav", "surface.elevated + text.primary + medium weight", "120ms"),
        ("disabled", "text.muted · border.subtle · no pointer · reason in tooltip", "—"),
        ("loading", "skeleton shimmer in region · label 'Loading …'", "—"),
        ("error", "negative banner in region · retry + view logs", "200ms"),
        ("locked (env-gated)", "dash-border negative · lock glyph · reason text", "—"),
    ]
    return "<table><tr><th>state</th><th>chrome (tokens)</th><th>transition</th></tr>" + "".join(
        f"<tr><td><b>{a}</b></td><td>{b}</td><td class='num'>{c}</td></tr>" for a, b, c in rows
    ) + "</table>"


def modal_mock() -> str:
    return f"""
<div class="backdrop"><div class="modal" role="alertdialog" aria-modal="true">
  <div class="mh"><span class="t">Approve paper order — BTCUSDT LONG 0.050</span>
    <span class="badge intel">BINDS TO INTENT 9c2e…</span></div>
  <table style="margin-top:10px">
    <tr><td>instrument · venue · account</td><td class="r num">BTCUSDT · BYBIT · main-a</td></tr>
    <tr><td>side · size · type</td><td class="r num">LONG 0.050 · limit 66,900.0</td></tr>
    <tr><td>estimated cost (fees+spread+slip)</td><td class="r num">3.90</td></tr>
    <tr><td>worst-case loss (stop honoured)</td><td class="r num neg">-184.20</td></tr>
    <tr><td>portfolio impact</td><td class="r num">gross +0.8% · conc +1.1%</td></tr>
    <tr><td>stop / exit plan</td><td class="r num">66,780.0 / flat 16:40 UTC</td></tr>
    <tr><td>evidence · counter-case</td><td class="r"><u>dossier#2211</u> · <u>contra#7 open</u></td></tr>
    <tr><td>approval expires</td><td class="r num">16:40:00 UTC (countdown live)</td></tr>
  </table>
  <div class="cap" style="margin:8px 0">Any material change to this intent invalidates the
  approval (docs/03 §5). Environment SHADOW ⇒ execution routes to <b>paper</b>; live authority
  DENIED.</div>
  <div style="display:flex;gap:8px;align-items:center">
    <span class="btn" style="opacity:1">MFA code <span class="num">______</span></span>
    <span style="flex:1"></span>
    <span class="btn">Cancel</span>
    <span class="btn primary">Approve → paper</span>
  </div>
  <div class="cap" style="margin-top:8px">focus enters on <b>Cancel</b> (the safe choice) ·
  ESC or backdrop = cancel · confirm only via its button · focus returns to trigger on close ·
  role=alertdialog interrupts screen readers deliberately</div>
</div></div>"""


def friction_table() -> str:
    rows = [
        ("view balance / filter / sort", "none", "routine, reversible"),
        ("acknowledge alert", "none", "reversible"),
        ("edit mandate proposal", "confirm + restated values", "consequential, reversible"),
        ("approve order (paper/shadow)", "confirm + full intent restated + MFA", "binds intent"),
        ("emergency halt", "confirm + scope restated + MFA", "irreversible window"),
        ("resume after halt", "confirm + scope + reconciliation checklist + MFA", "re-entry to risk"),
        ("promote environment (PILOT/LIVE)", "confirm + restated mandate + MFA + typed LIVE + rollback plan", "irreversible class"),
    ]
    return ("<table><tr><th>action class</th><th>friction</th><th>why</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) + "</table>"
            "<div class='cap' style='margin-top:6px'>Friction is proportionate to risk, never "
            "uniform: uniform friction trains dismissal (research). Confirmations restate "
            "specifics — amount, venue, account, timing — so the owner checks a statement, not a "
            "question; “are you sure?” is banned copy.</div>")


def halt_flow() -> str:
    steps = [
        ("1 · trigger", "top-band chip · mobile full-width button · palette action · alert banner. All open the same scope modal — one flow, four doors."),
        ("2 · scope modal", "restates affected accounts, instruments, and what happens to each working order under the configured policy; typed confirmation HALT for full-scope halt; MFA."),
        ("3 · engaged", "top band flips negative + full-width banner; new entries blocked at the risk engine (not the UI); incident id minted; owner notified on all channels; state change written to audit."),
        ("4 · incident", "timeline card: scope, actions, reconciliations queued, positions unaffected/affected split; drill to every record."),
        ("5 · resume", "separate confirm: scope + reconciliation checklist green + MFA; resume is a decision with its own audit entry — never a toggle back."),
    ]
    return ("<div class='steps'>" + "".join(
        f"<div class='step'><span class='n'>{i}</span><div class='cap' "
        f"style='letter-spacing:.05em;text-transform:uppercase;margin-top:6px'>{t}</div>"
        f"<div class='cap' style='margin-top:4px'>{b}</div></div>"
        for i, (t, b) in [(s[0][:1], s) for s in []] or
        [(s[0][0], s) for s in steps]) + "</div>")


def palette_mock() -> str:
    return f"""
<div class="modal" style="width:520px" role="dialog" aria-modal="true">
  <div style="display:flex;align-items:center;gap:8px">
    <span class="kbd">⌘K</span>
    <span class="cap" style="flex:1;border-bottom:1px solid var(--color-border-subtle);padding:4px 0">
    type to search actions, instruments, records…</span></div>
  <table style="margin-top:8px">
    <tr><th>navigate</th><td>Open Positions · Portfolio & Risk · …</td><td class="r"><span class="kbd">↵</span></td></tr>
    <tr><th>actions</th><td>Emergency halt … <span class="badge neg">LOCKED: opens scope modal</span></td><td class="r"><span class="kbd">↵</span></td></tr>
    <tr><th>instruments</th><td>BTCUSDT · workbench</td><td class="r"><span class="kbd">↵</span></td></tr>
    <tr><th>records</th><td>incident #2214 · dossier #2211 · order #512</td><td class="r"><span class="kbd">↵</span></td></tr>
  </table>
  <div class="cap" style="margin-top:8px">environment-gated actions render locked with the reason,
  never hidden; the palette triggers flows, it never bypasses a confirmation; keyboard-only
  complete; ESC closes and returns focus.</div>
</div>"""


def keyboard_table() -> str:
    rows = [
        ("<span class='kbd'>⌘K</span> / <span class='kbd'>Ctrl K</span>", "command palette", "global"),
        ("<span class='kbd'>g</span> then <span class='kbd'>c|m|i|p|r</span>", "jump to screen (command/markets/intelligence/positions/risk)", "global"),
        ("<span class='kbd'>/</span>", "focus region search/filter", "global"),
        ("<span class='kbd'>?</span>", "shortcut sheet", "global"),
        ("<span class='kbd'>j</span>/<span class='kbd'>k</span>, <span class='kbd'>↵</span>", "row move / drill to source record", "tables"),
        ("<span class='kbd'>←</span>/<span class='kbd'>→</span>, <span class='kbd'>t</span>", "crosshair move / cycle timeframe preset", "charts"),
        ("<span class='kbd'>Esc</span>", "cancel modal / close palette (safe direction)", "overlays"),
        ("<span class='kbd'>Tab</span>/<span class='kbd'>⇧Tab</span>", "focus order = visual order; trapped inside modals by design", "global"),
    ]
    return ("<table><tr><th>keys</th><th>action</th><th>scope</th></tr>" +
            "".join(f"<tr><td>{a}</td><td>{b}</td><td class='cap'>{c}</td></tr>" for a, b, c in rows) +
            "</table><div class='cap' style='margin-top:6px'>Skip-link to main on every screen; "
            "focus-visible ring never suppressed; no keyboard traps except modals (which trap by "
            "design and return focus to the trigger on close).</div>")


def motion_table() -> str:
    rows = [
        ("state chrome (hover/focus/selected)", "120ms", "standard easing"),
        ("region content swap / tab change", "200ms", "fade + 4px rise, no scale"),
        ("modal enter / exit", "200ms", "elevation-3 + fade; exit 120ms"),
        ("halt banner engage", "200ms", "slide from top band; stays until resolved"),
        ("brand moment (splash only)", "1.2s", "the gate opens (docs/08 §9)"),
        ("price / figure updates", "0ms", "<b>no motion on money</b> — values switch instantly; animation on numbers misreads as change in value"),
    ]
    return ("<table><tr><th>what moves</th><th>duration</th><th>curve / note</th></tr>" +
            "".join(f"<tr><td><b>{a}</b></td><td class='num'>{b}</td><td class='cap'>{c}</td></tr>"
                    for a, b, c in rows) +
            "</table><div class='cap' style='margin-top:6px'>prefers-reduced-motion: every "
            "duration → 0; state remains legible via colour+shape+text (docs/03 §3.3).</div>")


def a11y_block() -> str:
    return """<div class="grid2">
<div class="card"><div class="t" style="font-size:var(--font-size-body);font-weight:600">Live regions & labels</div>
<div class="cap" style="margin-top:6px">aria-live=assertive: halt engage/resume, CRIT alerts,
feed barred. aria-live=polite: stale/delayed transitions, reconciliation results. Charts carry
aria-labels naming instrument, venue, timeframe, trend summary and data status; tables expose
column semantics; every badge pairs glyph+text (colour never sole signal).</div></div>
<div class="card"><div class="t" style="font-size:var(--font-size-body);font-weight:600">Zoom, targets, text units</div>
<div class="cap" style="margin-top:6px">200% zoom: context rail docks to edge tabs first, tables
scroll horizontally with pinned instrument column, top band wraps to two rows — no clipped
controls. Touch targets ≥44px mobile / ≥32px desktop. <b>Proposal P-5:</b> docs/03 §3.2 states
sizes in px while §10 requires rem-based scalable text; Stage 4 specifies consumption of type
tokens in rem (identical rendered px at 100%); docs/03 unchanged pending owner ruling.</div></div>
</div>"""


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())
    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 4.1 Interaction System</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 4 of 23 &middot; sub-deliverable 4.1</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Interaction system: states, confirmations, flows, keyboard, motion</h1>
<div class="ribbon">DESIGN SPECIMEN — the modal and palette below show labelled placeholder
intent fields so the anatomy can be reviewed; production confirmations restate the live intent
hash and values at trigger time.</div>

<h2><span class="num">01</span>Component state machine</h2>
<div class="card">{state_machine()}</div>

<h2><span class="num">02</span>Confirmation anatomy — restate, never ask</h2>
{modal_mock()}
<p class="cap">The confirmation is a statement to be checked, not a question to be dismissed:
every §5 binding field restated, worst case in negative colour, expiry counting, evidence and
open counter-case linked, MFA inline, cancel holding initial focus. Irreversible-class actions
add a typed confirmation; nothing confirms via backdrop click.</p>

<h2><span class="num">03</span>Friction proportionate to risk</h2>
<div class="card">{friction_table()}</div>

<h2><span class="num">04</span>Emergency halt &amp; resume flow</h2>
{halt_flow()}
<p class="cap">Halt blocks new risk at the risk engine, not in the UI — a broken interface must
not mean an un-halted book. Resume is its own decision with a reconciliation checklist.</p>

<h2><span class="num">05</span>Command palette &amp; keyboard model</h2>
<div class="grid2"><div>{palette_mock()}</div><div class="card">{keyboard_table()}</div></div>

<h2><span class="num">06</span>Motion spec</h2>
<div class="card">{motion_table()}</div>

<h2><span class="num">07</span>Alerts, labels, zoom — accessibility floors</h2>
{a11y_block()}
<footer>Stage 4.1 &middot; interaction system only; journeys &amp; flows (J-01…J-03, approval,
incident triage) arrive in 4.2 &middot; approved shell D-033, tokens D-032, Stage 3 chrome
D-037 &middot; P-5 recorded against docs/03 (§3.2 px vs §10 rem).</footer>
</div></body></html>"""
    out = HERE / "stage4-1-interaction-system.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
