"""Stage 4.2 board: journeys & flows (J-01, J-02, J-03, approval binding, incident triage).

Every step cites the screen region (boards 3.x) and chrome (4.1) it uses; every branch
carries a state; every exit condition is measurable.

Run:  backend/.venv/bin/python design/build_board42.py
"""

from __future__ import annotations

import pathlib
import re

from build_board33 import CSS as CSS33
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS33 + """
.flow { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  align-items: stretch; }
.fstep { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-card); padding: 10px 10px 8px; position: relative; }
.fstep .n { position: absolute; top: -9px; left: 10px; background: var(--color-surface-elevated);
  border: 1px solid var(--color-border-strong); border-radius: 999px; padding: 0 8px;
  font: var(--font-weight-semibold) 10px/1.6 var(--font-family-mono); }
.fstep .t { font-size: var(--font-size-data); font-weight: var(--font-weight-semibold);
  margin-top: 4px; }
.fstep .w { font-size: var(--font-size-caption); line-height: 1.35; color: var(--color-text-muted);
  margin-top: 3px; }
.branch { border-left: 3px solid var(--color-feedback-warning-graphic); padding: 6px 10px;
  margin: 10px 0 0; background: var(--color-feedback-warning-subtle); border-radius: 0
  var(--radius-control) var(--radius-control) 0; }
.branch.neg { border-color: var(--color-feedback-negative-graphic);
  background: var(--color-feedback-negative-subtle); }
.exit { border: 1px dashed var(--color-feedback-positive-graphic); border-radius:
  var(--radius-control); padding: 8px 12px; margin-top: 10px; }
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 44px 0 2px; }
h3 .tag { font: var(--font-weight-medium) 10px/1.6 var(--font-family-mono); letter-spacing: .08em;
  color: var(--color-text-muted); border: 1px solid var(--color-border-subtle); border-radius: 3px;
  padding: 2px 6px; margin-left: 8px; vertical-align: 2px; }
"""


def flow(steps: list[tuple[str, str, str]]) -> str:
    return '<div class="flow">' + "".join(
        f'<div class="fstep"><span class="n">{i}</span><div class="t">{t}</div>'
        f'<div class="w">{w}</div></div>'
        for i, (t, w) in enumerate(steps, 1)) + "</div>"


J01 = [
    ("Open Command Centre", "top band verified: env SHADOW · halt OFF · acct ALL · UTC clock (3.2 §01)"),
    ("Capital & exposure", "P1 hero figure + realized/unrealized with ledger link; P2 exposure by venue"),
    ("Live risk & health", "P3 limits vs usage + fail-closed state; P4 per-feed freshness — stale feed shows why"),
    ("Regime & uncertainty", "regime cells each with confidence band (3.2 §01)"),
    ("Positions & opportunities", "drill any row to source record; verification chips on candidates"),
    ("Rails & lower strip", "intel activity · health · alert queue; decisions · research awaiting · exec quality"),
    ("No-trade reading", "why waiting · watching · would-change · invalidates (3.2 §01 region)"),
]
J01B = ("Branch: any region error/stale → contained banner + retry/logs; new FX risk blocked while "
        "dukascopy stale; the check continues on healthy regions — one failing feed never blanks "
        "the morning check.")
J01X = ("Exit: owner can state capital, exposure, live risk, health, evidence quality and what "
        "NEXUS is watching — within ~5 min, desktop, no drill deeper than one hop.")

J02 = [
    ("Open mobile Command", "36px top band: env · halt · UTC (3.5 §03)"),
    ("Glance capital", "compact hero + realized/unrealized; exposure & feed chips"),
    ("Positions check", "protective states venue-reported; pending trail flagged"),
    ("Alert arrives", "push (self-hosted VAPID) assertive live region; CRIT interrupts"),
    ("Tap → incident", "incident timeline card: scope · actions · impact · reconciliation"),
    ("Optional halt", "full-width button = tap 1; scope modal + MFA = tap 2 (docs/03 §9)"),
]
J02B = ("Branch: offline → cached read-only banner with stale badge; no order submission; halt "
        "cannot be initiated offline: the phone shows the last known halt state and says "
        "explicitly that halt requires connectivity.")
J02X = "Exit: intraday monitoring without desktop; every critical path ≤2 taps; no hidden states."

J03 = [
    ("Trigger", "four doors, one flow: top-band chip · mobile button · palette · alert banner (4.1 §1.5)"),
    ("Scope modal", "accounts · instruments · working-order policy restated; typed HALT; MFA"),
    ("Engage", "risk engine blocks new entries (not the UI); banner + top band negative; incident id minted"),
    ("Notify & preserve", "all channels notified; audit + evidence frozen; positions split affected/unaffected"),
    ("Reconcile", "reconciliation queue drains; unmatched rows investigated before resume"),
    ("Resume decision", "separate confirm: scope + checklist green + MFA; own audit entry"),
]
J03B = ("Branch: MFA failure → flow aborts, halt state unchanged, failure audited; partial venue "
        "ack → unknown-order policy: CRIT + new risk stays blocked on that instrument.")
J03X = "Exit: no new risk anywhere; working orders handled per policy; evidence preserved; resume is a decision, never a toggle."

APPROVAL = [
    ("Candidate verified", "V1·V2·V3 pass chips; FAIL ends candidate with reason code (3.3 §02)"),
    ("Review intent", "expanded card: evidence · counter-case · worst case · cost · impact · expiry"),
    ("Freeze intent", "immutable hash minted; approval will bind to exactly this intent (docs/03 §5)"),
    ("Confirm + MFA", "restate-not-ask modal; cancel-first focus; backdrop never confirms (4.1 §02)"),
    ("Route by environment", "SHADOW ⇒ paper; PILOT/LIVE would require authority GRANTED (it is DENIED)"),
    ("Execute & record", "idempotent execution + reconciliation; audit links approval→order→fills"),
]
APPROVALB = ("Branch: any material change to instrument/venue/account/side/size/type/cost/stop "
             "before execution → approval INVALIDATED, chip flips, re-confirmation required; "
             "expiry passes → same.")
APPROVALX = "Exit: approval bound to an immutable intent; every downstream record links back to it."

TRIAGE = [
    ("CRIT alert", "assertive live region + top band freshness flip; queue badge counts (3.5 §01)"),
    ("Acknowledge", "owner or policy ack; ack state visible; SLA clock starts"),
    ("Incident scope", "incident card: affected feeds/accounts/instruments; impact split"),
    ("Contain", "feed barred from pipeline; new risk blocked per policy; risk engine informed"),
    ("Notify", "all channels; delivery failures raise their own alert (3.5 §01)"),
    ("Recover & close", "reconciliation green; post-incident note; retention per policy; resolve state"),
]
TRIAGEB = ("Branch: containment insufficient (e.g. venue-side unknown orders) → escalate to halt "
           "flow J-03 with incident linked; escalation is one tap from the incident card.")
TRIAGEX = "Exit: cause named, containment evidenced, reconciliation green, closure note written — no silent recoveries."


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    def block(title: str, tag: str, steps, branch: str, exit_: str, neg: bool = False) -> str:
        cls = "branch neg" if neg else "branch"
        return (f"<h3>{title}<span class='tag'>{tag}</span></h3>{flow(steps)}"
                f"<div class='{cls}'>{branch}</div><div class='exit cap'>{exit_}</div>")

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 4.2 Journeys & Flows</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 4 &middot; sub-deliverable 4.2 (final batch)</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Journeys &amp; flows — every step on a designed surface</h1>
<div class="ribbon">Each step cites the screen region (boards 3.1–3.5) and interaction chrome
(4.1) it uses; every branch carries a state; every exit condition is measurable. No step lands
on an undesigned surface; no branch dead-ends.</div>

{block("J-01 · Morning Command Check", "desktop · ~5 min", J01, J01B, J01X)}
{block("J-02 · Intraday Monitoring", "mobile · glanceable", J02, J02B, J02X)}
{block("J-03 · Emergency Halt", "mobile · critical", J03, J03B, J03X, neg=True)}
{block("Approval binding", "desktop or mobile · consequential", APPROVAL, APPROVALB, APPROVALX)}
{block("Incident triage", "any surface · operational", TRIAGE, TRIAGEB, TRIAGEX)}

<h3>Flow laws<span class="tag">binding on Stage 5+</span></h3>
<div class="card"><div class="cap">1 · Every step names its screen region and chrome — a step
without a surface is a missing design, not an implementation detail.<br>
2 · Every branch carries a visible state (docs/03 §5); silent failure is a defect.<br>
3 · Every exit condition is measurable (time, taps, states green) — journeys are testable at
Stage 23 validation.<br>
4 · Critical paths ≤2 taps on mobile; consequential paths always pass a restate-not-ask
confirmation with MFA where the friction ladder says so.<br>
5 · Halt and risk blocks live in the risk engine; UI states reflect engine state, never replace
it.<br>
6 · Approvals bind to immutable intents; material change invalidates and re-asks.</div></div>
<footer>Stage 4.2 &middot; completes Stage 4 with 4.1 (D-038) &middot; stage-level approval
requested next; Stage 5 (System Architecture) waits on it.</footer>
</div></body></html>"""
    out = HERE / "stage4-2-journeys-flows.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
