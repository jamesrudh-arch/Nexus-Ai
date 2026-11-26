"""Stage 7.2 board: three levers implemented — what changed, what it cost, what it did not close.

Every number here comes from a CI check annotation, a local gate command re-run for this board, or a
transcript produced by executing the code being described. Where this batch corrected its own record
(a path that does not exist, a count that went stale while it was being written, a commit message that
overclaimed), the correction is shown rather than quietly absorbed.

Run:  backend/.venv/bin/python design/build_board72.py
"""

from __future__ import annotations

import pathlib
import re

from build_board71 import CSS as CSS71
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS71 + """
.ba { border: 1px solid var(--color-border-subtle); border-radius: var(--radius-card);
  overflow: hidden; margin-top: 12px; }
.ba .hd { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  letter-spacing: .08em; padding: 6px 12px; background: var(--color-surface-elevated);
  color: var(--color-text-muted); border-bottom: 1px solid var(--color-border-subtle); }
.ba pre { margin: 0; padding: 10px 12px; font-family: var(--font-family-mono);
  font-size: var(--font-size-data); line-height: 1.65; white-space: pre-wrap;
  color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.ba.before .hd { color: var(--color-feedback-negative-text); }
.ba.after .hd { color: var(--color-feedback-positive-text); }
.no { color: var(--color-feedback-negative-text); }
.ok { color: var(--color-feedback-positive-text); }
"""


def rows(items: list[tuple[str, ...]]) -> str:
    return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in items)


def table(head: list[str], body: list[tuple[str, ...]]) -> str:
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{h}</th>" for h in head)
        + "</tr></thead><tbody>"
        + rows(body)
        + "</tbody></table>"
    )


# --------------------------------------------------------------------------- 0 · authorisation
def authorisation_table() -> str:
    return table(
        ["Question put in 7.1 §1.9", "Owner's answer", "What it bound this batch to"],
        [
            (
                "<b>Authorise the Stage 7.2 code changes?</b>",
                "<span class='chip pos'>Recommend</span> — <b>L-A + L-B + L-E</b> now",
                "Three levers, no more. <b>L-C</b> (seed the master) deferred to 7.3; <b>L-D</b> "
                "(bybit from a self-hosted runner) waits on the D-021 VM",
            ),
            (
                "<b>The <span class='mono'>CONNECTED</span> ruling</b>",
                "<span class='chip pos'>Recommend</span> — <b>redefine it</b> (option a)",
                "One comment, <b>no enum change, no new rung</b>. The ladder, "
                "<span class='mono'>CERTIFICATION_ORDER</span>, the <span class='mono'>coverage_report</span> "
                "thresholds and the audit vocabulary had to stay untouched — verified in §3",
            ),
            (
                "<b>Bybit's row</b>",
                "<span class='chip pos'>Recommend</span> — <b>stays open and visible</b>",
                "No row removed, no status invented: <span class='mono'>GEO-BLOCKED / SUPPORTED</span>, "
                "re-reported in all twelve runs below",
            ),
        ],
    )


# --------------------------------------------------------------------------- 1 · L-A
RUNS = [
    ("1", "45754638978", "139690278846", "a77865e", "04:21:01", "False", "24 / 0 / 5 / 0 of 29"),
    ("2", "45756716181", "139696937355", "b67ab39", "04:40:38", "False", "24 / 0 / 5 / 0 of 29"),
    ("3", "45758610197", "139703054396", "fa74748", "04:59:09", "False", "24 / 0 / 5 / 0 of 29"),
    ("4", "45759709313", "139706589069", "25e314e", "05:09:21", "False", "24 / 0 / 5 / 0 of 29"),
    ("5", "45782533635", "139781214750", "bc4a718", "08:21:55", "<b>True</b>", "24 / 0 / 5 / 0 of 29"),
    ("6", "45782540670", "139781237726", "bc4a718", "08:21:58", "<b>True</b>", "24 / 0 / 5 / 0 of 29"),
    ("7", "45784665370", "139788299846", "41aca23", "08:36:56", "<b>True</b>", "24 / 0 / 5 / 0 of 29"),
    ("8", "45784657260", "139788273040", "41aca23", "08:36:53", "<b>True</b>", "24 / 0 / 5 / 0 of 29"),
    ("9", "45786440060", "139794273725", "354b95c", "08:49:32", "<b>True</b>", "27 / 0 / 5 / 0 of <b>32</b>"),
    ("10", "45786447356", "139794299438", "354b95c", "08:49:35", "<b>True</b>", "27 / 0 / 5 / 0 of <b>32</b>"),
    ("11", "45787390006", "139797515877", "f675582", "08:56:10", "<b>True</b>", "27 / 0 / 5 / 0 of <b>32</b>"),
    ("12", "45787399434", "139797547309", "f675582", "08:56:14", "<b>True</b>", "27 / 0 / 5 / 0 of <b>32</b>"),
]


def runs_table() -> str:
    body = []
    for n, run, job, commit, created, flag, checks in RUNS:
        if flag == "False":
            role = "produced the evidence"
        elif n == "12":
            role = "falsifiability test — <b>and the run that exposed F-11</b>"
        else:
            role = "falsifiability test — flag already on"
        body.append(
            (
                n,
                f"<span class='mono'>{run}</span>",
                f"<span class='mono'>{job}</span>",
                f"<span class='mono'>{commit}</span>",
                created,
                f"<span class='mono'>{flag}</span>",
                "<span class='ok'>passed=True</span>",
                checks,
                role,
            )
        )
    return table(
        ["#", "Run", "Job", "Commit", "Created UTC", "Flag", "verify_layout", "passed/failed/geo/skip", "Role"],
        body,
    )


DIVISORS_UNVERIFIED = [
    "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP",
    "EURJPY", "USDJPY", "GBPJPY", "AUDJPY", "XAUUSD", "XAGUSD",
]


def scope_table() -> str:
    return table(
        ["What the flag claims", "Scope", "Where it is recorded"],
        [
            (
                "The bi5 <b>record layout</b> — LZMA, 20 bytes per tick, big-endian",
                "<span class='chip pos'>VERIFIED</span> — the same for every pair, so it generalises",
                "<span class='mono'>dukascopy.py:70 LAYOUT_VERIFIED = True</span>",
            ),
            (
                "The <b>point divisor</b> for EURUSD (100000)",
                "<span class='chip pos'>VERIFIED</span> — prices 1.09502–1.0964, inside the real band",
                "<span class='mono'>dukascopy.py:78 LAYOUT_VERIFIED_PAIRS = (\"EURUSD\",)</span>",
            ),
            (
                f"The point divisor for the other <b>{len(DIVISORS_UNVERIFIED)}</b> pairs — "
                "<span class='mono'>" + ", ".join(DIVISORS_UNVERIFIED) + "</span>",
                "<span class='chip warn'>PROVISIONAL</span> — never met a real file; a wrong divisor is a "
                "silent <b>100×</b> error",
                "<span class='mono'>summarise() → divisor_unverified_pairs (dukascopy.py:429)</span>",
            ),
            (
                "That dukascopy prices are <b>correct</b>",
                "<span class='chip neg'>NOT CLAIMED</span> — layout verification is not price "
                "verification; nothing reconciles it against a second source",
                "<span class='mono'>docs/14 §2.5 (F-8)</span>",
            ),
            (
                "That the feed is <b>reliable</b>",
                "<span class='chip neg'>NOT CLAIMED</span> — twelve runs, five probe patterns, no cause "
                "established",
                "<span class='mono'>docs/14 §1.4 F-5</span>",
            ),
        ],
    )


# --------------------------------------------------------------------------- 2 · L-B
def boundary_table() -> str:
    return table(
        ["Boundary", "Now refuses", "Before this batch"],
        [
            (
                "<span class='mono'>VenueMapping.__post_init__</span> <span class='cite'>instrument.py:118</span>",
                "a <span class='mono'>venue</span> that is not a <span class='mono'>Venue</span>; a "
                "<span class='mono'>status</span> that is not a <span class='mono'>VenueStatus</span>",
                "constructed silently — a dataclass annotation is not a check",
            ),
            (
                "<span class='mono'>CanonicalInstrument.__post_init__</span> <span class='cite'>instrument.py:162</span>",
                "an <span class='mono'>asset_class</span> that is not an <span class='mono'>AssetClass</span>; "
                "a <span class='mono'>mappings</span> entry that is not a <span class='mono'>VenueMapping</span>",
                "constructed silently",
            ),
            (
                "<span class='mono'>InstrumentRegistry.certify</span> <span class='cite'>registry.py:379</span>",
                "a bare-string <span class='mono'>venue</span> or <span class='mono'>to_status</span>",
                "<span class='mono'>AttributeError</span> later, at the first "
                "<span class='mono'>m.venue.value</span>",
            ),
        ],
    )


# --------------------------------------------------------------------------- 3 · L-E
def untouched_table() -> str:
    return table(
        ["Deliberately untouched — the owner's answer forbade it", "Verified by"],
        [
            ("<span class='mono'>VenueStatus</span> — still 6 members, no new rung",
             "<span class='mono'>len(VenueStatus) == 6</span>"),
            ("<span class='mono'>CERTIFICATION_ORDER</span> — same six rungs, same order",
             "<span class='mono'>len(CERTIFICATION_ORDER) == 6</span>; "
             "<span class='mono'>test_order_is_the_documented_ladder</span> unchanged"),
            ("Ladder arithmetic — <span class='mono'>certification_rank</span>, "
             "<span class='mono'>is_certification_advance</span>, one-step-at-a-time",
             "<span class='mono'>test_cannot_skip_rungs</span> passes unchanged"),
            ("<span class='mono'>coverage_report</span> thresholds — research / paper / live",
             "<span class='mono'>test_readiness_follows_certification</span> unchanged"),
            ("Audit vocabulary — kinds <span class='mono'>REGISTER / ACTIVATE / DEACTIVATE / CERTIFY / "
             "DE_CERTIFY / REMAP</span>",
             "<span class='mono'>auth_state</span> is an added <i>field</i>, not a new kind; "
             "<span class='mono'>test_payload_is_bounded</span> still passes"),
        ],
    )


# --------------------------------------------------------------------------- 4 · F-10
def f10_table() -> str:
    return table(
        ["Run", "production UA", "browser UA", "other hour", "Published verdict"],
        [
            ("<span class='mono'>45756716181</span>", "<span class='no'>network-IngestFault</span>",
             "<span class='no'>network-IngestFault</span>",
             "<span class='ok'>ok · 25,313 bytes · lzma=True</span>",
             "<span class='no'>&ldquo;never reached&rdquo; ✗</span>"),
            ("<span class='mono'>45758610197</span>", "<span class='no'>network-IngestFault</span>",
             "<span class='ok'>ok · 25,761 bytes · lzma=True</span>",
             "<span class='no'>network-IngestFault</span>",
             "<span class='no'>&ldquo;never reached&rdquo; ✗</span>"),
            ("<span class='mono'>45784665370</span>", "<span class='no'>network-IngestFault</span>",
             "<span class='ok'>ok · 25,761 bytes · lzma=True</span>",
             "<span class='no'>network-IngestFault</span>",
             "<span class='no'>&ldquo;never reached&rdquo; ✗</span>"),
            ("<span class='mono'>45784657260</span>", "<span class='no'>network-IngestFault</span>",
             "<span class='ok'>ok · 25,761 bytes</span>",
             "<span class='ok'>ok · 25,313 bytes</span>",
             "<span class='no'>&ldquo;never reached&rdquo; ✗✗ — two refutations in one run</span>"),
        ],
    )


def f11_table() -> str:
    return table(
        ["Probe in run <span class='mono'>45787399434</span>", "Outcome", "What it proves"],
        [
            ("production UA, requested hour", "<span class='no'>network-IngestFault</span>",
             "that attempt got no reply"),
            ("browser UA, same hour", "<span class='no'>network-IngestFault</span>",
             "that attempt got no reply either"),
            ("production UA, <b>different hour</b>", "<span class='ok'>http-503</span>",
             "<b>the host answered</b> — a status code is a reply from the host, not a silence"),
        ],
    )


# --------------------------------------------------------------------------- 5 · F-8
GAPS = [
    ("1", "60960.3 / 60960.4", "60960.3 / 60960.4", "0.000"),
    ("2", "61063.2 / 61063.3", "61063.2 / 61063.3", "0.000"),
    ("3", "60974.6 / 60974.7", "60965.8 / 60965.9", "<b>1.443</b>"),
    ("4", "60925.8 / 60925.9", "60925.8 / 60925.9", "0.000"),
    ("5", "60721.9 / 60722.0", "60726.7 / 60726.8", "<b>0.790</b>"),
    ("6", "60726.7 / 60726.8", "60713.2 / 60713.3", "<b>2.223</b>"),
    ("7", "60692.3 / 60692.4", "60692.3 / 60692.4", "0.000"),
    ("8", "60692.3 / 60692.4", "60692.3 / 60692.4", "0.000"),
    ("9", "60989.2 / 60989.3", "60995.3 / 60995.4", "<b>1.000</b>"),
    ("10", "60990.0 / 60990.1", "60988.6 / 60988.7", "0.230"),
    ("11", "60912.6 / 60912.7", "60912.6 / 60912.7", "0.000"),
    ("12", "60900.0 / 60900.1", "60897.0 / 60897.1", "<b>0.493</b>"),
]


def f8_table() -> str:
    return table(
        ["Run", "<span class='mono'>okx.quotes</span> bid/ask", "<span class='mono'>okx.book</span> bid/ask",
         "mid gap (bps)"],
        [(n, q, b, g) for n, q, b, g in GAPS],
    )


# --------------------------------------------------------------------------- 6 · gate
def gate_table() -> str:
    return table(
        ["Gate", "Result", "Command"],
        [
            ("Suite", "<b>997 passed, 2 skipped, 0 failed</b> <span class='cite'>(was 976 + 2)</span>",
             "<span class='mono'>pytest</span> with CI's env "
             "<span class='mono'>NEXUS_AUDIT_BACKEND=memory NEXUS_ENVIRONMENT=DISABLED DO_NOT_TRACK=1</span>"),
            ("New tests", "<b>+21 to the gate total</b> — 20 registry (9 + 11) and 1 adapter; plus "
             "<b>7 offline checks</b> for F-10 and F-11 in the live module, which the gate skips as a "
             "module", "<span class='cite'>976 + 20 + 1 = 997</span>"),
            ("Live module collected", "<b>36</b> <span class='cite'>(29 → 32 → 36)</span> — live-source "
             "checks unchanged at <b>11</b>; neither increase adds coverage evidence",
             "<span class='mono'>NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -q</span>"),
            ("Live module offline subset", "<b>20 passed</b> <span class='cite'>(13 → 16 → 20)</span>",
             "<span class='mono'>… -k \"DiagnosisLogic or PatienceBehaviour\"</span>"),
            ("Lint + format", "clean", "<span class='mono'>ruff check src tests</span> · "
             "<span class='mono'>ruff format --check src tests</span> (80 files)"),
            ("Types", "<b>Success: no issues found in 56 source files</b>",
             "<span class='mono'>mypy</span> (strict, <span class='mono'>src/nexus</span>)"),
            ("Repo hygiene", "<b>80 passed</b>", "<span class='mono'>pytest tests/test_repo_hygiene.py</span> "
             "<span class='cite'>(run after git add -A)</span>"),
            ("CI", "all jobs green on <span class='mono'>bc4a718</span>, <span class='mono'>41aca23</span>, "
             "<span class='mono'>354b95c</span> and <span class='mono'>f675582</span>; re-checked on the "
             "commit carrying this board",
             "5 <span class='mono'>ci</span> jobs × 2 triggers + 1 venue job × 2 triggers per commit"),
            ("Scope", "<b>backend/: 6 production files, 5 test files · 790 insertions / 50 deletions</b>, "
             "plus 4 documents and 3 design files",
             "<span class='mono'>git diff --stat 8d8f6f2 -- backend/</span>"),
        ],
    )


# --------------------------------------------------------------------------- 7 · not closed
def not_closed_table() -> str:
    return table(
        ["Finding", "State after 7.2", "Why it is still open"],
        [
            ("<b>F-1</b> dukascopy layout", "<span class='chip pos'>CLOSED for EURUSD</span>",
             "L-A. Twelve divisors remain provisional — see §1"),
            ("<b>F-4</b> fail-open then crash", "<span class='chip pos'>CLOSED</span>",
             "L-B. Refusal now happens where the bad value arrives"),
            ("<b>F-7</b> unoccupiable rung", "<span class='chip pos'>CLOSED as a definition</span>",
             "L-E. The <i>seed</i> is still missing, which is F-3"),
            ("<b>F-10</b> self-refuting verdict", "<span class='chip pos'>CLOSED</span>",
             "Found, fixed and pinned by three offline tests in this batch"),
            ("<b>F-11</b> an HTTP reply is also proof of reach",
             "<span class='chip pos'>CLOSED</span>",
             "Found in run 12 — the first run to exercise the F-10 branch live. Pinned by all 125 "
             "combinations of the probe cross-product (§4)"),
            ("<b>F-2</b> bybit geo-block", "<span class='chip neg'>OPEN</span>",
             "<span class='mono'>5 geo-blocked</span> in the headline of all twelve runs. The "
             "403-from-CloudFront characterisation on public unauthenticated endpoints is run "
             "<span class='mono'>45724918466</span> <span class='cite'>(docs/06:314)</span>, not these "
             "twelve. L-D needs the D-021 VM; the <span class='mono'>runner</span> dispatch input "
             "already exists"),
            ("<b>F-3</b> empty master", "<span class='chip neg'>OPEN</span>",
             "<span class='mono'>/v1/instruments/coverage</span> still returns "
             "<span class='mono'>total=0 active=0</span> at boot. L-C deferred to 7.3 by the owner's "
             "answer; L-E removed the <i>definition</i> blocker, not the missing seed"),
            ("<b>F-5</b> intermittent feed", "<span class='chip warn'>OPEN, better evidenced</span>",
             "Twelve runs, <b>five</b> probe patterns, production UA worked outright in seven. No cause "
             "established; a user-agent theory was falsified within eleven minutes in 7.1 and is not "
             "revived here"),
            ("<b>F-6</b> 3 of 14 asset classes", "<span class='chip warn'>OPEN</span>",
             "<span class='mono'>DUKASCOPY</span> makes FX_SPOT <i>recordable</i>, not covered. The other "
             "ten must render <span class='mono'>UNSUPPORTED</span> per D-019"),
            ("<b>F-8</b> cross-endpoint agreement", "<span class='chip warn'>OPEN, now quantified</span>",
             "§5. Needs a stated bps tolerance and a recorded timestamp gap — both are design choices, "
             "not measurements. Handed to the owner as <b>P-8</b>"),
            ("<b>F-9</b> &ldquo;both sides present&rdquo;",
             "<span class='chip warn'>DOCS CORRECTED · RULING OUTSTANDING</span>",
             "<span class='mono'>docs/06:234</span> and <span class='mono'>:300</span> now say the run "
             "<i>happened</i> to contain both sides and name what the check accepts. Whether one-sidedness "
             "should ever <i>fail</i> is handed to the owner as <b>P-7</b>"),
        ],
    )


def limits_table() -> str:
    return table(
        ["Limitation", "What it means for any claim built on this batch"],
        [
            ("<b>EURUSD only</b>", "Twelve of thirteen point divisors have never met a real file, and a "
             "wrong divisor is a silent 100× error. <span class='mono'>LAYOUT_VERIFIED_PAIRS</span> exists "
             "so no report can imply otherwise"),
            ("<b>One hour</b>", "All twelve runs fetched <span class='mono'>2026-11-24T12:00Z</span>, "
             "chosen by <span class='mono'>_recent_weekday_hour()</span>. Twelve passes are twelve readings "
             "of <i>one</i> file, not twelve samples of the feed: a weekend hour, a holiday, a month "
             "boundary and a JPY pair are all untested against real data"),
            ("<b>The F-11 fix is offline-evidenced only</b>", "Run 12 exercised the <i>F-10</i> branch "
             "live and exposed F-11; no run has yet reproduced a network baseline beside an "
             "<span class='mono'>http-*</span> reply against the corrected branch. Its evidence is the "
             "125-combination cross-product test, not a live run"),
            ("<b>No production caller</b>", "<span class='mono'>certify(auth=…)</span> and the new refusals "
             "are exercised by tests, not by any running code path: there is no write endpoint and the "
             "master is empty. Their first real caller arrives with L-C in 7.3"),
            ("<b>Nothing reconciled against a second source</b>", "Layout verification is not price "
             "verification (§5)"),
            ("<b>Twelve is a floor, not a final count</b>", "Every push touching "
             "<span class='mono'>ingestion/**</span> re-triggers the workflow and "
             "<span class='mono'>pull_request</span> events are not suppressed by that filter, so two "
             "runs appear per commit — including this one. No run has ever failed the check"),
            ("<b>Bybit's five checks remain unrun anywhere</b>", "Its adapter is still exercised against "
             "public documentation only. <span class='mono'>SUPPORTED</span> is its honest rank and stays "
             "its recorded status"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 7.2 Three Levers Implemented</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 7 of 23 &middot; sub-deliverable 7.2 (implementation) &middot;
authorised by D-045</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Three levers implemented &mdash; one honesty row retired, two boundaries closed, one rung redefined</h1>
<div class="ribbon">IMPLEMENTATION BATCH — the first <code>backend/</code> production change since
Stage 6.2, and scoped to the three levers the owner named. <b>L-A</b> retires the dukascopy row on
evidence CI had already produced ten times. <b>L-B</b> makes the only free FX source representable and
refuses out-of-vocabulary values where they arrive instead of crashing later. <b>L-E</b> redefines
<code>CONNECTED</code> so a credential-free source can occupy it without lying. A fourth item,
<b>F-10</b>, was found on the way: a diagnostic that published &ldquo;the host was never reached&rdquo;
in four runs whose own probes recorded it answering. Fixing it produced <b>F-11</b>, because the fix
counted only successes as proof of reach and the first run to exercise it live answered
<code>http-503</code> — a reply. Gate <b>997 passed / 2 skipped / 0 failed</b>, CI green on all five
commits.</div>

<h3>0 · What was authorised, and what that forbade<span class="tag">docs/14 §2.0 · D-045</span></h3>
<div class="card">{authorisation_table()}</div>
<p class="cap">All three questions were answered <span class="mono">Recommend</span>, which adopts the
recommendations as written. Scope was held: <b>6 production files, 5 test files, 1 document</b> —
no API route, no store module, no migration, and no adapter other than dukascopy's constants and
docstrings.</p>

<h3>1 · L-A — the dukascopy row is retired<span class="tag">F-1 closed for EURUSD · dukascopy.py:70</span></h3>
<p><span class="mono">LAYOUT_VERIFIED</span> is <b>True</b> and every parsed record now carries
<span class="mono">source="DUKASCOPY_BI5"</span> instead of
<span class="mono">DUKASCOPY_BI5_UNVERIFIED</span>. The evidence is <b>twelve consecutive CI runs on
2026-11-26</b>, all <span class="mono">conclusion=success</span>:</p>
<div class="card">{runs_table()}</div>
<p class="cap">passed / failed / geo-blocked / skipped. Runs 1–4 produced the evidence for the flip;
runs 5–12 <i>are</i> the flip's falsifiability test — <b>eight</b> runs with the flag on, all still
green. <b>Twelve is a floor, not a final count:</b> every push that touches
<span class="mono">backend/src/nexus/ingestion/**</span> re-triggers this workflow and
<span class="mono">pull_request</span> events are not suppressed by that filter, so two runs appear per
commit — including the commit carrying this board. What is claimed is the floor: no venue run has ever
failed the layout check, and a future failure means the flag goes back to
<span class="mono">False</span> rather than the check being relaxed.</p>
<div class="ev"><span class="k"># identical in all twelve runs, byte for byte</span>
dukascopy.url    hour=2026-11-24T12:00:00+00:00  bytes=25761  month_segment=10
dukascopy.layout passed=True payload_bytes=25761 decompressed_bytes=101480 tick_count=5074 reasons=-
dukascopy.ticks  count=5074 price_min=1.09502 price_max=1.0964
                 source=DUKASCOPY_BI5 layout_verified=True    <span class="k">&lt;- runs 5-12; runs 1-4 read _UNVERIFIED / False</span>
<span class="k"># 101,480 = 5,074 x 20 exactly, so the record size is confirmed against a real file.</span>
<span class="k"># reasons=- means no check failed. Prices inside EURUSD's real band are the assertion that</span>
<span class="k"># exists to catch a wrong point divisor - the silent 100x error O-010 named.</span></div>
<p><b>The hour is <span class="mono">2026-11-24T12:00Z</span>, a Tuesday</b> — what
<span class="mono">_recent_weekday_hour()</span> selects. Its path is
<span class="mono">EURUSD/2026/10/24/12h_ticks.bi5</span>, where the <span class="mono">10</span> is
<b>November</b>, because the month segment is 0-indexed. §4 records how that nearly entered the
record wrongly.</p>
<p><b>What the flag now claims, and what it does not.</b> The layout generalises; the divisor does
not. Both halves are data, not prose, so no report can imply more than was proven:</p>
<div class="card">{scope_table()}</div>
<div class="gate">Pinned by <span class="mono">test_the_verified_scope_is_machine_readable</span>:
<span class="mono">LAYOUT_VERIFIED_PAIRS == ("EURUSD",)</span>, and
<span class="mono">set(divisor_unverified_pairs) == set(POINT_DIVISORS) - {{"EURUSD"}}</span> with
<span class="mono">len(unverified) == len(POINT_DIVISORS) - 1</span> — the two halves must partition
the table, so adding a pair without verifying it shows up in the summary rather than hiding in a
docstring.</div>
<p><b>Stale statements corrected.</b> <span class="cite">dukascopy.py</span> module docstring
(rewritten, including the invented <span class="mono">BID</span>/<span class="mono">ASK</span> URL
segment that defect 39 removed), the <span class="mono">LAYOUT_VERIFIED</span> comment,
<span class="mono">source_label()</span>'s docstring, and <span class="mono">verify_layout()</span>'s —
which was <b>kept</b>, with its docstring now saying why the function outlives its own flag: the weekly
run keeps calling it, and a future failure means the flag goes back to <span class="mono">False</span>
rather than the check being relaxed. In the tests:
<span class="cite">test_adapters.py</span> module docstring,
<span class="mono">test_dukascopy_layout_is_declared_unverified</span> →
<span class="mono">…_is_declared_verified</span> (now citing all twelve runs),
<span class="mono">test_source_is_labelled_unverified</span> →
<span class="mono">…_with_the_layout_state</span>, the fetch-report and summary assertions;
<span class="cite">test_live_endpoints.py</span> module docstring, the layout-gate assertion message and
the reachability diagnostic's history. In the docs: <span class="cite">docs/06:245–251</span> and
<span class="cite">:297</span>, superseded in place with the history left standing.</p>

<h3>2 · L-B — the venue vocabulary is enforced at the boundary<span class="tag">F-4 closed · Venue now has 10 members</span></h3>
<p><span class="mono">Venue</span> gained <span class="mono">DUKASCOPY</span>
<span class="cite">(instrument.py:67)</span>, so the only free FX source is representable and FX
coverage can be recorded at all. New <span class="mono">InstrumentDefinitionError</span>
<span class="cite">(:21)</span> carrying a new
<span class="mono">RejectReason.INSTRUMENT_DEFINITION_INVALID</span> <span class="cite">(errors.py:37)</span>.</p>
<div class="card">{boundary_table()}</div>
<div class="ba before"><div class="hd">BEFORE — fail open, then crash unclassified (7.1's F-4 transcript)</div>
<pre>VenueMapping(venue="DUKASCOPY", venue_symbol="EURUSD")   -> constructs; annotations do nothing at runtime
registry.register(instrument_with_that_mapping)          -> AttributeError: 'str' object has no
                                                            attribute 'value'   (registry.py, first m.venue.value)
through the API                                          -> HTTP 500, where every comparable condition
                                                            is a named refusal
RegistryChange.venue: str | None                         -> the audit log cannot tell a venue from a typo</pre></div>
<div class="ba after"><div class="hd">AFTER — refused where the bad value arrives (executed for this board)</div>
<pre>VenueMapping(venue="DUKASCOPY", venue_symbol="EURUSD")
  -> InstrumentDefinitionError  reason=INSTRUMENT_DEFINITION_INVALID
     detail: a venue mapping's venue must be a Venue member (D-007 scope); got 'DUKASCOPY' of type str
VenueMapping(venue="NOT_A_VENUE", ...)      -> INSTRUMENT_DEFINITION_INVALID
Venue("DUKASCOPY")                          -> Venue.DUKASCOPY        (enum members: 10)
register(EUR/USD on Venue.DUKASCOPY)        -> INS-EUR-USD, venue DUKASCOPY
certify("INS-BTC-USDT-USDT", "BYBIT", ...)  -> InstrumentDefinitionError: certification needs a Venue member</pre></div>
<p>The closure of F-4, at every step that used to be impossible —
<span class="mono">test_fx_coverage_is_recordable_end_to_end</span>: register EUR/USD on
<span class="mono">Venue.DUKASCOPY</span>, certify <span class="mono">UNKNOWN → SUPPORTED → CONNECTED →
DATA_AVAILABLE</span> with each rung's own evidence label, then read it back through
<span class="mono">coverage_report</span>:</p>
<div class="ev">by_asset_class={{'FX_SPOT': 1}}   by_venue_status={{'DATA_AVAILABLE': 1}}
ready_for_research=('INS-EUR-USD',)   ready_for_paper=()   ready_for_live=()
mapping.is_tradeable=False            instrument.active=False      <span class="k">&lt;- D-002: never active by default</span></div>
<div class="blocked"><b>What L-B does not close.</b> There is no HTTP endpoint that registers or
certifies anything — <span class="cite">api/app.py</span>'s instruments routes are GET-only — so this
refusal cannot yet be exercised through the API. It protects the domain boundary and every future
caller, including Stage 8's. And the master is still empty at boot, which is F-3, which is L-C, which
is 7.3.</div>

<h3>3 · L-E — <span class="mono">CONNECTED</span> declares its authentication case<span class="tag">F-7 closed as a definition</span></h3>
<p>The ruling as adopted: <b><span class="mono">CONNECTED</span> means &ldquo;the venue answered and its
responses normalised&rdquo;, not &ldquo;auth verified&rdquo;</b>. Certifying to it now requires an
explicit declaration — <span class="mono">AUTH_VERIFIED</span> or
<span class="mono">AUTH_NOT_APPLICABLE</span> <span class="cite">(registry.py:62–64)</span> — recorded
as <span class="mono">RegistryChange.auth_state</span> <span class="cite">(:121)</span> and surfaced in
<span class="mono">to_audit_payload()</span>. The registry cannot judge an evidence label (it only checks
the label is non-empty), so the declaration is its own recorded field rather than a sentence somebody
might forget to write.</p>
<div class="card">{untouched_table()}</div>
<div class="ba after"><div class="hd">BEHAVIOUR, measured</div>
<pre>certify(..., CONNECTED, evidence="it answered")                  -> CertificationRejected
   "certifying CONNECTED requires an explicit auth declaration - AUTH_VERIFIED (a credential was
    presented and accepted) or AUTH_NOT_APPLICABLE (public, credential-free, and the evidence label
    must say why). CONNECTED no longer assumes auth was verified"
certify(..., CONNECTED, auth="PROBABLY_AUTHENTICATED")           -> CertificationRejected: must be one of
certify(..., CONNECTED, auth=AUTH_NOT_APPLICABLE)                -> accepted
   change log: [('CERTIFY','SUPPORTED',None), ('CERTIFY','CONNECTED','AUTH_NOT_APPLICABLE'),
                ('CERTIFY','DATA_AVAILABLE',None)]
   to_audit_payload()["auth_state"] == "AUTH_NOT_APPLICABLE"
certify(..., SUPPORTED, auth=AUTH_NOT_APPLICABLE)                -> CertificationRejected
   "an auth declaration belongs to the CONNECTED rung only"
certify(..., CONNECTED) when already CONNECTED                   -> no-op: records nothing, claims nothing
demotion DATA_AVAILABLE -> CONNECTED without a declaration       -> CertificationRejected
                                            with AUTH_NOT_APPLICABLE -> recorded as DE_CERTIFY + auth_state</pre></div>
<p><b>Why this mattered more than a comment.</b> 7.1's F-7 measured that a credential-free source could
not occupy <span class="mono">CONNECTED</span> honestly, and since the ladder does not skip,
<span class="mono">DATA_AVAILABLE</span> was unreachable for <i>all four</i> sources this system uses —
which made <span class="mono">MINIMUM_STATUS_FOR_ARCHIVE = DATA_AVAILABLE</span>
<span class="cite">(ingestion/pipeline.py:50)</span> unsatisfiable by any free source.</p>
<div class="gate"><span class="mono">test_a_credential_free_source_can_now_reach_the_archive_gate</span>
pins the whole chain: <span class="mono">AUTH_NOT_APPLICABLE</span> at
<span class="mono">CONNECTED</span> → <span class="mono">DATA_AVAILABLE</span> →
<span class="mono">certification_rank(status) &gt;= certification_rank(MINIMUM_STATUS_FOR_ARCHIVE)</span>,
with <span class="mono">ready_for_paper == ()</span> and
<span class="mono">is_tradeable is False</span>. <b>The archive gate is now reachable in principle; it
is still not reachable in production, because the master is empty</b> (F-3 → L-C → 7.3).</div>
<p class="cap"><b>Ten pre-existing certification sites</b> across three test modules had to state their
case — 18 <span class="mono">auth=</span> sites in total once the 8 inside the new tests are counted,
both figures recomputed from the files rather than estimated. Every venue in them is a public feed, so
every declaration is <span class="mono">AUTH_NOT_APPLICABLE</span>, threaded through a local
<span class="mono">_auth_for(status)</span> helper (one per module) instead of being hardcoded, so a test
that climbs to a different rung cannot silently mis-declare.</p>

<h3>4 · F-10 — a verdict contradicted by the probes printed next to it<span class="tag">new finding, found and fixed in this batch</span></h3>
<p>Found by reading run 7's evidence lines rather than its headline.
<span class="mono">_diagnose_dukascopy</span> tested
<span class="mono">baseline.startswith("network-")</span> <b>before</b> testing whether either variant
had succeeded, so a production-UA network fault published <i>&ldquo;the host was never reached, so no
cause can be distinguished&rdquo;</i> even when the same run's probes had reached it. Four runs did
that:</p>
<div class="card">{f10_table()}</div>
<p>The branch now checks both variants first and reports what was measured: the production attempt got
no reply, the host <i>did</i> answer a browser User-Agent on the same hour and/or the production
User-Agent on a different hour, so this is not an unreachable host, and one attempt per variant cannot
separate a transient fault from a rejection. &ldquo;Never reached&rdquo; survives for the only case
where it is true — nothing answered. The action text keeps the User-Agent question as an
<b>OWNER DECISION</b>, never an automatic workaround.</p>
<div class="ev"><span class="k"># three offline tests pin the shapes that occurred and were pinned by nothing</span>
test_a_browser_success_refutes_never_reached            PASS   <span class="k">(runs 45758610197, 45784665370)</span>
test_another_hour_answering_also_refutes_never_reached  PASS   <span class="k">(run 45756716181)</span>
test_never_reached_still_holds_when_nothing_answered    PASS   <span class="k">(the claim's one true case)</span>
<span class="k"># all three appear by name in the annotations of runs 9 and 10</span>
live module collected: 29 -> <b>32</b>      report: 27 passed / 0 failed / 5 geo-blocked / 0 skipped of 32
live-source checks: 11 -> <b>11</b>          <span class="k">the denominator moved; the coverage did not</span></div>
<div class="blocked">Runs 9 and 10 both had <span class="mono">production_ua=ok</span>, so neither
exercised the corrected branch live. <b>Run 12 did — and showed the fix was incomplete.</b></div>

<h3>4b · F-11 — an HTTP reply is also proof the host was reached<span class="tag">new finding, exposed by run 12, fixed here</span></h3>
<p>Run <span class="mono">45787399434</span> is the first since the F-10 fix in which the production
User-Agent faulted. Its own probes recorded this:</p>
<div class="card">{f11_table()}</div>
<div class="ba before"><div class="hd">WHAT RUN 12 PUBLISHED, NEXT TO THE PROBE THAT REFUTES IT</div>
<pre>dukascopy.probe.production_ua              outcome=network-IngestFault
dukascopy.probe.browser_ua                 outcome=network-IngestFault
dukascopy.probe.production_ua_other_hour   outcome=<b>http-503</b>       &lt;- a reply from the host
dukascopy.diagnosis verdict=<b>the host was never reached</b> (network-IngestFault),
                            so no cause can be distinguished</pre></div>
<p>The F-10 fix counted only <span class="mono">ok</span> outcomes as proof of reach. It did not count an
HTTP status — but a 503 <i>is</i> a reply, not a silence. The function's own comment already said why
that matters (<i>&ldquo;a host that never answered is a different fact from a host that answered
503&rdquo;</i>), and the code contradicted its own comment whenever the 503 came from a <b>variant</b>
rather than from the baseline.</p>
<div class="blocked"><b>Why it was missed, recorded because this is the second instance of the same
shape.</b> The F-10 tests pinned one case per branch that had <i>actually occurred</i>. No combination
of a network baseline beside an <span class="mono">http-*</span> variant had occurred in the runs
available then, so nothing pinned it, and the gap surfaced only when CI produced that combination. The
remedy is the one that should have been applied the first time: <b>enumerate the cross-product.</b></div>
<div class="ba after"><div class="hd">AFTER — four tests, one of them the whole cross-product</div>
<pre>test_an_http_reply_from_a_variant_also_refutes_never_reached        PASS  <span class="k">run 12's exact inputs</span>
test_a_browser_http_reply_refutes_never_reached_too                 PASS  <span class="k">same gap, other probe</span>
test_a_variant_that_returned_a_file_is_not_described_as_not_serving PASS  <span class="k">new clause must not over-fire</span>
test_never_reached_is_claimed_only_when_all_three_probes_got_no_reply
                                                                    PASS  <span class="k">5^3 = <b>125</b> combinations:</span>
   outcomes = ok | network-IngestFault | network-X | http-503 | http-403
   invariant: "never reached" in verdict  <=>  all three probes faulted at the network layer</pre></div>
<p>The verdict now names the status it measured and, when no variant retrieved a file, adds that
<span class="mono">the host is reachable but not serving</span> — which is a different fact from both
&ldquo;unreachable&rdquo; and &ldquo;served&rdquo;, and is the reading the 503 throttling supports.
<b>The live module collects 36</b> (29 → 32 → 36); live-source checks are still <b>11</b>.</p>
<p><b>Runs 13 and 14 confirm it live.</b> The commit carrying this fix triggered two more venue runs —
<span class="mono">45796096183</span> (push) and <span class="mono">45796115693</span> (pull request),
both <span class="mono">success</span>, and the first to collect 36. All four new checks appear by name
in both annotations, and <span class="mono">verify_layout</span> passed again in both — the thirteenth
and fourteenth consecutive passes.</p>
<div class="ba after"><div class="hd">RUN 13 — THE FIRST LIVE EXERCISE OF THE CORRECTED BRANCH · 30 passed / 0 failed / 5 geo-blocked / 1 skipped of 36</div>
<pre>dukascopy.probe.production_ua              outcome=network-IngestFault
dukascopy.probe.browser_ua                 outcome=ok  bytes=25761  lzma=True
dukascopy.probe.production_ua_other_hour   outcome=ok  bytes=25313  lzma=True
dukascopy.diagnosis verdict=the production attempt got no reply (network-IngestFault) but the host
  did answer a browser User-Agent on the same hour (a valid file came back) and the production
  User-Agent on a different hour (a valid file came back) in the same minute, <b>so this is not an
  unreachable host</b>; one attempt per variant cannot separate a transient network fault from a
  rejection
<span class="k">run 14 (PR trigger): 31 passed / 0 failed / 5 geo-blocked / 0 skipped of 36, production_ua=ok</span></pre></div>
<p class="cap">Run 13's single skip is the designed behaviour, not a regression: its ticks fetch did not
answer, so the check <b>skipped rather than failed</b>
<span class="cite">(test_live_endpoints.py:153, &ldquo;did not answer, so nothing is verified either
way&rdquo;)</span> and the headline says so — <span class="mono">1 could not reach their source</span>.
The layout check in the same run used the patient fetch and passed.</p>
<div class="blocked"><b>Limitation, stated precisely:</b> run 13 exercised the branch that reports a
<i>succeeded</i> variant. The F-11-specific path — a network baseline beside an
<span class="mono">http-*</span> reply — has not recurred in any run, so that half of the fix is
evidenced by the 125-combination cross-product test and not by a live run.</div>
<p><b>Two corrections to this batch's own record</b>, because a correction that is absorbed silently is
worth nothing:</p>
<div class="ba before"><div class="hd">1 · A PATH THAT DOES NOT EXIST WAS NEARLY PUBLISHED AS THE EVIDENCE CITATION</div>
<pre>first written as   EURUSD/2026-10-24/12h_ticks.bi5                  <- would 404
hour_url("EURUSD", 2026-11-24T12:00Z)
        emits      .../datafeed/EURUSD/2026/10/24/12h_ticks.bi5     <- the real path
for 24 October it would emit  .../EURUSD/2026/09/24/12h_ticks.bi5

two genuine hyphenated errors were committed in bc4a718, both in test_adapters.py: a docstring, and a
fixture URL that would 404 if anything ever fetched it - it passed only because summarise() never
validates a URL against its hour. Both fixed in 41aca23; the fixture now uses the hour really fetched.

CAUSE, recorded because it will recur: this environment's output rendering displays "/" as "-" inside
date-like sequences, so a correct path reads as a wrong one and a wrong one reads as correct. Every
path claim in this batch is now either generated by hour_url() or verified by character-level
comparison - never by eye. docs/06 still holds four hyphenated paths in historical rows; a correction
note there says so and gives the generated forms.</pre></div>
<div class="ba before"><div class="hd">2 · 41aca23's COMMIT MESSAGE OVERCLAIMED</div>
<pre>it said: "the citation committed in bc4a718 named the verified file as EURUSD/2026-10-24/12h_ticks.bi5"

in dukascopy.py the path was already slash-correct. The error was real but narrower than the message
said - two sites, both in test_adapters.py. Corrected here rather than by rewriting a pushed commit.

and a third, of the same class: the run count went stale twice while it was being written (four -> six
-> eight -> ten) because each push re-triggered the very workflow being cited. Every count is now
date-bounded to 2026-11-26, so a later pass cannot make it false.</pre></div>

<h3>5 · F-8 measured across twelve runs — quantified, not fixed<span class="tag">handed to the owner as P-8</span></h3>
<p>F-8 said nothing asserts that two endpoints from one venue agree, and that a fix needs a stated
tolerance plus a recorded timestamp gap. The twelve runs' recorded evidence now sizes the problem —
<span class="mono">okx.quotes</span> (ticker) against <span class="mono">okx.book</span> (order book) in
the same run:</p>
<div class="card">{f8_table()}</div>
<div class="ev">convention: gap_bps = |mid_quotes - mid_book| / <b>mid_quotes</b> x 10^4
exactly zero in 6 of 12     min 0.000     max <b>2.223</b>     mean <b>0.515</b> bps
above the 0.016 bps quoted spread in 6 of 12
<span class="k">dividing by the book mid instead gives 2.224 for run 6 and the same mean - no conclusion</span>
<span class="k">below depends on the choice, but a published number must say which denominator it used.</span>
<span class="k">the okx.book evidence line records NO TIMESTAMP in any of the twelve runs (verified), and the two</span>
<span class="k">endpoints are fetched sequentially, not atomically - so no gap can be attributed to elapsed</span>
<span class="k">time rather than to disagreement. Choosing a tolerance today would be inventing one.</span></div>
<div class="blocked"><b>A false finding this measurement nearly produced, recorded so nobody repeats
it.</b> A natural cross-check is &ldquo;every trade price lies inside the current book&rdquo;. It fails
in <b>12 of 12</b> runs — and it is <b>not a defect</b>: trades are historical prints and the book has
moved since. Asserting containment would have manufactured a finding out of normal market behaviour,
which is F-9's error class in the opposite direction.</div>

<h3>6 · Gate evidence<span class="tag">every number re-run for this board</span></h3>
<div class="card">{gate_table()}</div>

<h3>7 · What this batch did not close<span class="tag">stated before the ask, not after</span></h3>
<div class="card">{not_closed_table()}</div>

<h3>8 · Limitations of this batch<span class="tag">docs/14 §2.8</span></h3>
<div class="card">{limits_table()}</div>

<h3>9 · Reproducibility<span class="tag">every command behind a claim above</span></h3>
<div class="ev"><span class="k"># the twelve runs and their evidence (annotations; job logs and artifacts are unreachable from here)</span>
for r in 45754638978 45756716181 45758610197 45759709313 45782533635 45782540670 \\
         45784665370 45784657260 45786440060 45786447356 45787390006 45787399434; do
  gh api repos/:owner/:repo/actions/runs/$r --jq '.head_sha[0:7] + " " + .created_at + " " + .conclusion'
  gh api repos/:owner/:repo/actions/runs/$r/jobs --jq '.jobs[0].id'
  gh api repos/:owner/:repo/check-runs/&lt;job&gt;/annotations --jq '.[].message'
done
<span class="k"># the path claim, generated rather than retyped</span>
python -c "hour_url('EURUSD', datetime(2026,11,24,12,tzinfo=UTC))"   -> .../EURUSD/2026/10/24/12h_ticks.bi5
<span class="k"># the scope partition</span>
python -c "summarise([hour])['divisor_unverified_pairs']"            -> 12 pairs, EURUSD absent
<span class="k"># the F-4 and L-E transcripts</span>
python -c "VenueMapping(venue='DUKASCOPY', ...); certify(..., CONNECTED, evidence=...)"  -> both quoted in §2, §3
<span class="k"># the gates</span>
NEXUS_AUDIT_BACKEND=memory NEXUS_ENVIRONMENT=DISABLED DO_NOT_TRACK=1 pytest      -> 997 passed, 2 skipped
NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -q        -> 36
NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py -k "DiagnosisLogic or PatienceBehaviour"  -> 20
git diff --stat 8d8f6f2 -- backend/                                              -> 11 files, 790+/50-
ruff check src tests ; ruff format --check src tests ; mypy                      -> clean / clean / 56 files
git diff --stat 8d8f6f2..f675582                                                 -> 12 files, 739+/57-</div>

<h3>10 · Decision requested<span class="tag">docs/14 §2.9</span></h3>
<div class="ask">
<p>Stage 7.2 delivered the three authorised levers and closed four findings. Three questions before
7.3:</p>
<ol>
<li><b>Is Stage 7.1 approved?</b> Its row in <span class="mono">docs/07</span> still reads
<span class="mono">AWAITING REVIEW / PENDING</span> with no decision id: the owner authorised 7.2
<i>on the strength of</i> the 7.1 research but never ruled on 7.1 as a deliverable. Recording
<b>D-046</b> would close that gap; leaving it open is also a legitimate answer.</li>
<li><b>Authorise Stage 7.3 = L-C, seed the instrument master?</b> The batch that makes coverage
non-zero: register only instruments whose evidence exists — okx
<span class="mono">BTC-USDT-SWAP</span> (twelve runs), binance vision
<span class="mono">BTCUSDT</span> 1m (twelve runs, 1,440 bars, 0 rejected), dukascopy
<span class="mono">EURUSD</span> (twelve runs, layout verified for that pair only) — each at the rank its evidence supports and no higher, each citing its run ids, with
<span class="mono">AUTH_NOT_APPLICABLE</span> at <span class="mono">CONNECTED</span>. It decides what
every screen shows, so it wants its own review. Cost $0, no new dependency, offline-testable.
<b>Recommendation: yes, as 7.3.</b></li>
<li><b>The P-7 ruling (F-9).</b> Should a trade list containing only one side ever <i>fail</i> a live
check? The documentation now says what the check does; only the owner can say what it should do.
<b>Recommendation: no — record the side distribution as evidence and never fail on it</b>, because a
one-sided window is normal in a quiet market, and <span class="mono">_assert_book</span> already fails a
one-sided <i>book</i>, which is the case that actually indicates a broken feed. <b>P-8</b> (F-8's
tolerance and the missing book timestamp) is offered with it, since both are rulings about what the
live checks should assert.</li>
</ol>
</div>

<footer>Stage 7.2 &middot; implementation &middot; D-045 &middot; commits bc4a718 → 41aca23 → 354b95c →
f675582 → 500ac36 (F-11) → this one &middot; gate 997 passed / 2 skipped / 0 failed, +21 tests in the
gate and 7 offline checks in the live module &middot; ruff + format clean, mypy strict clean on 56
files, hygiene 80 &middot; backend/ 790 insertions / 50 deletions across 6 production and 5 test files
&middot; CI green on every commit of the batch &middot; evidence: fourteen live runs on 2026-11-26, all
success, verify_layout passed in every one &middot; bybit geo-blocked in every one &middot; the master is
still empty (F-3 → 7.3)</footer>
</div></body></html>"""
    out = HERE / "stage7-2-levers-implemented.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
