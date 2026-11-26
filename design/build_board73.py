"""Stage 7.3 board: the instrument master is seeded — what it claims, and what it refuses to claim.

Every number here comes from a CI check annotation, a local gate command re-run for this board, or a
transcript produced by executing the code being described (`backend/.venv/bin/python`, the block in
§2 is reproduced verbatim). Where this batch corrected its own record — a run count in source that
disagreed with itself, a docstring sentence that had lost its subject, a board ribbon that said "ten"
where its own section said "twelve" — the correction is shown rather than quietly absorbed.

Run:  backend/.venv/bin/python design/build_board73.py
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
/* `.card` wraps every table in this board but was undefined in the shared shell (CSS71), so the
   tables rendered unbordered — the same gap exists in the 7.1 and 7.2 boards. Definition copied
   verbatim from `build_specimen.py`, the approved visual language, rather than invented here.
   Added to THIS board's extension only: restyling two already-approved artefacts silently is not
   this batch's call to make. */
.card { background: var(--color-surface-panel); border: 1px solid var(--color-border-subtle);
        border-radius: var(--radius-card); padding: var(--space-panel); }
.card table { width: 100%; }
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


# --------------------------------------------------------------------- 0 · how one word was read
def reading_table() -> str:
    return table(
        ["Question asked in <span class='cite'>docs/14</span> §2.9", "Read as", "What this batch did"],
        [
            (
                "<b>1 · Is batch 7.1 approved?</b> Its row still reads "
                "<span class='mono'>AWAITING REVIEW / PENDING</span> with no decision id",
                "<span class='chip neg'>NOT ANSWERED</span>",
                "<code>Proceed</code> authorises the work <i>ahead</i>. It does not retroactively "
                "approve a deliverable <i>behind</i> it, so 7.1's row is untouched and the question "
                "is re-asked in §11",
            ),
            (
                "<b>2 · Authorise Stage 7.3 = L-C, seed the master?</b> "
                "<i>Recommendation: yes</i>",
                "<span class='chip'>YES</span>",
                "L-C implemented: 3 canonical instruments, 4 venue mappings, 10 rungs, each at the "
                "rank its evidence supports and no higher",
            ),
            (
                "<b>3 · The P-7 ruling</b> — may a one-sided trade list fail a live check? "
                "<i>Recommendation: no, record the distribution</i>",
                "<span class='chip'>ADOPTED</span>",
                "Still never fails, now pinned by 5 offline tests, and records "
                "<span class='mono'>buy=</span>/<span class='mono'>sell=</span>/"
                "<span class='mono'>unspecified=</span> counts rather than only the set of sides",
            ),
            (
                "<b>P-8</b> — F-8's tolerance <i>(recommendation: not choosable today)</i>",
                "<span class='chip'>ADOPTED IN PART</span>",
                "The missing measurement was added (<span class='mono'>observed_at</span> on the "
                "book line). <b>No tolerance chosen, none asserted</b> — and the measurement "
                "immediately reframed the finding (§6)",
            ),
        ],
    )


# ------------------------------------------------------------------------------- 1 · what was seeded
def seed_table() -> str:
    return table(
        ["Canonical instrument", "Class", "Venue", "Venue symbol", "Rank seeded", "What the rank cites"],
        [
            (
                "<span class='mono'>BTC/USDT:USDT</span><br>"
                "<span class='cite'>INS-BTC-USDT-USDT</span>",
                "<span class='mono'>CRYPTO_PERP</span>",
                "<b>OKX</b>",
                "<span class='mono'>BTC-USDT-SWAP</span>",
                "<span class='chip'>DATA_AVAILABLE</span>",
                "Five public endpoints verified against live responses in every run read. Economics "
                "<span class='mono'>ctVal=0.01 tickSz=0.1 minSz=0.01 qtyStep=0.01</span> read off "
                "the instrument endpoint, not assumed",
            ),
            (
                "<span class='mono'>BTC/USDT:USDT</span><br>"
                "<span class='cite'>same instrument</span>",
                "<span class='mono'>CRYPTO_PERP</span>",
                "<b>BYBIT</b>",
                "<span class='mono'>BTCUSDT</span>",
                "<span class='chip neg'>SUPPORTED</span>",
                "An adapter exists — <i>all</i> <span class='mono'>SUPPORTED</span> claims, and no "
                "more. 403 geo-blocked from every hosted runner (F-2), never verified, needs the "
                "D-021 VM (L-D)",
            ),
            (
                "<span class='mono'>BTC/USDT</span><br><span class='cite'>INS-BTC-USDT</span>",
                "<span class='mono'>CRYPTO_SPOT</span>",
                "<b>BINANCE</b>",
                "<span class='mono'>BTCUSDT</span>",
                "<span class='chip'>DATA_AVAILABLE</span>",
                "A real 71,720-byte daily ZIP downloaded and parsed end to end: "
                "<b>1,440 of 1,440</b> 1m bars accepted, <b>0 rejected</b>, 23.98 h spanned, "
                "<span class='mono'>timestamp_units=us</span>",
            ),
            (
                "<span class='mono'>EUR/USD</span><br><span class='cite'>INS-EUR-USD</span>",
                "<span class='mono'>FX_SPOT</span>",
                "<b>DUKASCOPY</b>",
                "<span class='mono'>EURUSD</span>",
                "<span class='chip'>DATA_AVAILABLE</span>",
                "25,761 &rarr; 101,480 bytes = <b>5,074 ticks &times; 20 exactly</b>, prices "
                "1.09502&ndash;1.0964 in band, layout verified — <b>EURUSD only, one hour, "
                "unreconciled</b> (F-8)",
            ),
        ],
    )


def rank_refusal_table() -> str:
    return table(
        ["Rank not claimed", "Why no seeded mapping may hold it"],
        [
            (
                "<span class='mono'>TRADE_ENABLED</span>",
                "Needs a sandbox order lifecycle observed end to end. Nothing here has ever placed "
                "an order, and no credential exists to place one with",
            ),
            (
                "<span class='mono'>LIVE_VERIFIED</span>",
                "Needs a live pilot with reconciliation proven. <span class='cite'>docs/12</span> "
                "§1.4 says so explicitly, and F-8 is precisely the reconciliation that is not proven",
            ),
            (
                "<span class='mono'>DUKASCOPY</span> at either",
                "Structurally impossible: it publishes tick data, not an order book or an account. "
                "It can never be a trading venue, so no amount of evidence would reach these rungs",
            ),
        ],
    )


# ------------------------------------------------------------------------- 3 · F-3 before and after
def f3_table() -> str:
    return table(
        ["Route", "Before 7.3", "After 7.3"],
        [
            (
                "<span class='mono'>GET /v1/instruments/coverage</span>",
                "<span class='no'>total=0 &nbsp;active=0</span><br>"
                "<span class='cite'>ready_for_research=()</span>",
                "<span class='ok'>total=3 &nbsp;active=0</span><br>"
                "<span class='cite'>ready_for_research = all three</span>",
            ),
            (
                "<span class='mono'>GET /v1/status</span> &rarr; <span class='mono'>instrument_master</span>",
                "<span class='no'>{count: 0, active: 0}</span>",
                "<span class='ok'>{count: 3, active: 0}</span>",
            ),
            (
                "<span class='mono'>by_asset_class</span>",
                "<span class='no'>{}</span>",
                "<span class='ok'>{CRYPTO_PERP: 1, CRYPTO_SPOT: 1, FX_SPOT: 1}</span> — the three "
                "classes F-6 counted, and no others invented",
            ),
            (
                "<span class='mono'>by_venue_status</span>",
                "<span class='no'>{}</span>",
                "<span class='ok'>{DATA_AVAILABLE: 3, SUPPORTED: 1}</span>",
            ),
            (
                "<span class='mono'>ready_for_paper</span> / <span class='mono'>ready_for_live</span>",
                "<span class='cite'>()</span>",
                "<span class='cite'>()</span> — unchanged, and meant to be: both need trade authority "
                "nobody has been given (D-002)",
            ),
            (
                "Archive gate<br><span class='cite'>pipeline.MINIMUM_STATUS_FOR_ARCHIVE</span>",
                "<span class='no'>Unsatisfiable in production</span> — no mapping anywhere could "
                "reach <span class='mono'>DATA_AVAILABLE</span>, however honest the adapters were",
                "<span class='ok'>Reachable</span> with the registry the app actually boots: a "
                "BINANCE bar and a DUKASCOPY bar are accepted and resolve to real instrument ids",
            ),
            (
                "&hellip;and bybit through the same gate",
                "<span class='cite'>n/a — nothing was seeded</span>",
                "<span class='no'>Still refused</span>: "
                "<span class='mono'>status_refusals={&quot;BYBIT:SUPPORTED&quot;: 1}</span>, nothing "
                "archived. <b>The gate is a gate</b>",
            ),
            (
                "<span class='mono'>GET /v1/data/coverage</span>",
                "<span class='cite'>configured=false, files=0</span>",
                "<span class='cite'>configured=false, files=0</span> — unchanged on purpose. Seeding "
                "the master must not imply data has been stored",
            ),
        ],
    )


# ----------------------------------------------------------------------------- 6 · the P-8 payload
def p8_table() -> str:
    return table(
        ["Run", "Id", "Commit", "<span class='mono'>.quotes observed_at</span>",
         "<span class='mono'>.book observed_at</span>",
         "&Delta;t <span class='neg'>(F-14: venue skew, not fetch time)</span>",
         "quotes mid", "book mid",
         "<span class='mono'>gap_bps</span>", "<span class='mono'>gap_bps/&Delta;t</span>"],
        [
            ("18", "<span class='cite'>45819528009</span>", "<span class='cite'>c48c714</span>",
             "<span class='mono'>12:26:10.568</span>", "<span class='mono'>12:26:11.906</span>",
             "<b>1.338 s</b>", "60606.25", "60606.25", "<b>0.000</b>", "0.000"),
            ("19", "<span class='cite'>45819539643</span>", "<span class='cite'>c48c714</span>",
             "<span class='mono'>12:26:19.069</span>", "<span class='mono'>12:26:20.356</span>",
             "<b>1.287 s</b>", "60591.25", "60587.05", "<b>0.693</b>", "0.539"),
            ("22", "<span class='cite'>45825586882</span>", "<span class='cite'>4760462</span>",
             "<span class='mono'>13:05:02.973</span>", "<span class='mono'>13:05:04.408</span>",
             "<b>1.435 s</b>", "60780.05", "60777.25", "<b>0.461</b>", "0.321"),
            ("23", "<span class='cite'>45825598469</span>", "<span class='cite'>4760462</span>",
             "<span class='mono'>13:05:09.075</span>", "<span class='mono'>13:05:10.458</span>",
             "<b>1.383 s</b>", "60784.95", "60777.35", "<b>1.250</b>", "0.904"),
        ],
    )


# ----------------------------------------------------------------- 11 · what was asked, what was ruled
def ruled_table() -> str:
    return table(
        ["Question as asked", "Owner's answer", "Recorded as", "What it changed"],
        [
            ("<b>Is batch 7.1 approved?</b> Still <span class='mono'>PENDING</span> with no decision id",
             "<span class='ok'><b>Approve</b></span>", "<b>D-047</b>",
             "Its nine findings (F-1&hellip;F-9) and five $0 levers (L-A&hellip;L-E) are ratified rather "
             "than unratified by drift. The register row flips <span class='mono'>AWAITING REVIEW</span> "
             "&rarr; <span class='mono'>APPROVED</span>, and every lever delivered since stands on a "
             "ratified research base"),
            ("<b>P-9</b> &mdash; accumulate a rate bound, or stop comparing the mids at all?",
             "<span class='mono'>Recommend</span>", "<b>D-048</b>",
             "Two paths were on offer, so the ambiguity is resolved explicitly rather than hidden: "
             "<b>accumulate, and keep recording</b>. Implemented in <span class='cite'>7929a96</span> "
             "&mdash; &sect;12"),
            ("<b>Dukascopy's rank</b> &mdash; <span class='mono'>DATA_AVAILABLE</span> or "
             "<span class='mono'>CONNECTED</span>?",
             "<span class='mono'>Recommend</span>", "<b>D-048</b>",
             "Stays <span class='mono'>DATA_AVAILABLE</span>. "
             "<span class='cite'>pipeline.py:47-49</span> reserves the higher rung for a source that has "
             "actually produced stored bars, and dukascopy has produced none; read the other way it would "
             "apply equally to okx and empty the master"),
            ("<b>What comes next?</b> Close Stage 7 with bybit's row open, or hold the stage on the D-021 VM?",
             "<span class='mono'>stage8</span>", "<b>D-048</b>",
             "<b>Stage 7 closed</b>, bybit left open and <i>visible</i> at "
             "<span class='mono'>SUPPORTED</span>/<span class='mono'>GEO-BLOCKED</span> with "
             "<span class='mono'>F-2</span> and <span class='mono'>D-021</span> in its notes and rendered "
             "in the API. Stage 8 named as the next batch"),
            ("<b>The D-046 reading</b> &mdash; was any part of &sect;0's reading of "
             "<span class='mono'>Proceed</span> wrong?",
             "Not contested", "&mdash;",
             "&sect;0's reading stands: <span class='mono'>Proceed</span> pointed forward, and 7.1's "
             "approval came separately as D-047 rather than being inferred from it. That is why it was "
             "written down instead of assumed"),
        ],
    )


# ----------------------------------------------------------------------- 12 · P-9 implemented, and F-14
def p9_table() -> str:
    return table(
        ["Run", "Id", "<span class='mono'>gap_bps</span>",
         "<span class='mono'>dt_observed_s</span>", "<span class='mono'>dt_wall_s</span>",
         "<span class='mono'>bps_per_s_observed</span>", "<span class='mono'>bps_per_s_wall</span>",
         "quotes mid", "book mid"],
        [
            ("24", "<span class='cite'>45829853116</span>", "<b class='ok'>0.000</b>",
             "<span class='mono'>0.439</span>", "<span class='mono'>0.300</span>",
             "0.000", "0.000", "60804.15", "60804.15"),
            ("25", "<span class='cite'>45829842623</span>", "<b class='ok'>0.000</b>",
             "<span class='mono'>0.739</span>", "<span class='mono'>0.294</span>",
             "0.000", "0.000", "60804.15", "60804.15"),
        ],
    )


def f14_table() -> str:
    return table(
        ["Adapter", "<span class='mono'>observed_at</span> bound to", "Site"],
        [
            ("<b>okx</b>", "the response's <span class='mono'>ts</span> field &mdash; venue time",
             "<span class='cite'>okx.py:216, :380</span>"),
            ("<b>bybit</b>", "<span class='mono'>ts</span>/<span class='mono'>time</span>, falling back "
             "to <span class='mono'>server_time</span> &mdash; venue time",
             "<span class='cite'>bybit.py:353, :416, :439</span>"),
            ("<b>binance-vision</b>", "<span class='mono'>transact_time</span> &mdash; venue time",
             "<span class='cite'>binance_vision.py:339</span>"),
            ("<b>dukascopy</b>", "<span class='mono'>base + timedelta(milliseconds=offset_ms)</span> "
             "&mdash; derived from the file's own hour and tick offset",
             "<span class='cite'>dukascopy.py:253</span>"),
        ],
    )


def mandate_table() -> str:
    return table(
        ["Venue", "Asset class", "Verified?", "Rank", "What the evidence actually says"],
        [
            ("<b>OKX</b>", "<span class='mono'>CRYPTO_PERP</span>", "<span class='ok'><b>Yes</b></span>",
             "<span class='mono'>DATA_AVAILABLE</span>",
             "Five public endpoints against live responses, instrument economics read off the listing "
             "(<span class='mono'>ctVal=0.01 tickSz=0.1 minSz=0.01</span>)"),
            ("<b>BINANCE (vision)</b>", "<span class='mono'>CRYPTO_SPOT</span>",
             "<span class='ok'><b>Yes</b></span>", "<span class='mono'>DATA_AVAILABLE</span>",
             "Real 71,720-byte daily ZIP, <b>1,440 of 1,440</b> 1m bars, 0 rejected, "
             "<span class='mono'>timestamp_units=us</span>"),
            ("<b>DUKASCOPY</b>", "<span class='mono'>FX_SPOT</span>",
             "<span class='warn'><b>EURUSD only</b></span>", "<span class='mono'>DATA_AVAILABLE</span>",
             "25,761 &rarr; 101,480 bytes = <b>5,074 &times; 20</b> exactly, prices in band; layout "
             "verified in every run <i>that reached the source</i>; <b>12 of 13 divisors still "
             "unverified</b> and named by <span class='mono'>LAYOUT_VERIFIED_PAIRS</span>"),
            ("<b>BYBIT</b>", "<span class='mono'>CRYPTO_PERP</span>",
             "<span class='neg'><b>No</b></span>", "<span class='mono'>SUPPORTED</span>",
             "403 geo-blocked from every hosted runner; <b>open by ruling</b>, needs the D-021 VM as a "
             "self-hosted runner (lever L-D). Visible in the API with its reason rather than omitted"),
        ],
    )


def close_table() -> str:
    return table(
        ["Finding", "State at closure", "Remedy or reason"],
        [
            ("<b>F-2</b> bybit geo-block", "<span class='neg'>OPEN, visible</span>",
             "L-D from the D-021 VM; the <span class='mono'>runner</span> dispatch input already exists"),
            ("<b>F-14</b> <span class='mono'>observed_at</span> is venue time",
             "<span class='neg'>NEW, OPEN</span>",
             "A semantic change across four adapters, every record type and every test asserting on "
             "them &mdash; needs its own authorisation"),
            ("<b>F-8 / P-9</b> cross-endpoint rate", "<span class='warn'>OPEN, accumulating</span>",
             "<span class='mono'>okx.cross_endpoint</span> now records the gap, both &Delta;t readings "
             "and both rates every run; a bound needs many more samples"),
            ("<b>F-5</b> intermittent feed", "<span class='warn'>OPEN</span>",
             "Five probe patterns, no cause established. Runs 24&ndash;25 had <b>no skips at all</b>, "
             "runs 22&ndash;23 had one each &mdash; which is why the F-13 qualifier is permanent"),
            ("<b>F-6</b> 3 of 14 asset classes", "<span class='warn'>OPEN, visible</span>",
             "The eleven uncovered classes render <span class='mono'>UNSUPPORTED</span> per D-019; "
             "<span class='mono'>len(AssetClass) == 14</span> is asserted so growth forces the scope to "
             "be re-argued"),
            ("<b>F-11</b> half the fix offline-evidenced", "<span class='warn'>OPEN as a limitation</span>",
             "The <span class='mono'>http-*</span>-beside-a-network-fault path has still not recurred "
             "live"),
            ("<b>F-1, F-3, F-4, F-7, F-9/P-7, F-10, F-12, F-13</b>",
             "<span class='ok'>CLOSED in Stage 7</span>",
             "Dukascopy layout (EURUSD) &middot; empty master &middot; venue vocabulary &middot; "
             "<span class='mono'>CONNECTED</span> as a definition &middot; one-sidedness &middot; the "
             "self-contradicting verdict &middot; run counts in source &middot; a floor that counted a "
             "skip as a pass"),
        ],
    )


# ------------------------------------------------------------------------------- 7 · F-12
def f12_table() -> str:
    return table(
        ["Where", "What it said", "Why that is a defect"],
        [
            (
                "<span class='cite'>dukascopy.py</span> module docstring",
                "&ldquo;twelve consecutive CI runs &hellip; four before the flip &hellip; and "
                "<b>eight after it</b>&rdquo;",
                "Not current, and it contradicts the comment fifty lines below about the <i>same</i> "
                "flag",
            ),
            (
                "The comment on <span class='mono'>LAYOUT_VERIFIED</span> itself",
                "&ldquo;It passed <b>ten</b> times in a row &hellip; four before the flip and "
                "<b>six after it</b>&rdquo;",
                "<b>The same file disagreed with itself</b> about the evidence for its own central "
                "claim — the flag that decides whether every dukascopy record is labelled "
                "<span class='mono'>DUKASCOPY_BI5</span> or "
                "<span class='mono'>DUKASCOPY_BI5_UNVERIFIED</span>",
            ),
            (
                "The sentence stating the flag's value",
                "&ldquo;&hellip;the silent 100x error warned about below.<br>"
                "<span class='no'>therefore <span class='mono'>True</span> and every record "
                "carries &hellip;</span>&rdquo;",
                "Flipping the flag replaced "
                "&ldquo;<span class='mono'>LAYOUT_VERIFIED</span> is therefore "
                "<span class='mono'>False</span>&rdquo; and took the <b>subject</b> with the old "
                "value. A docstring that cannot name its own claim cannot be checked against the "
                "code beneath it",
            ),
            (
                "<span class='cite'>design/build_board72.py</span> ribbon",
                "&ldquo;evidence CI had already produced <b>ten</b> times&rdquo; — while §1 of the "
                "same board said <b>twelve</b>",
                "The same defect in a <i>published</i> artefact. Corrected and the board regenerated",
            ),
        ],
    )


# ---------------------------------------------------------------------------------- 8 · the gate
def gate_table() -> str:
    return table(
        ["Gate", "Result", "Command"],
        [
            ("Suite", "<b>1,036 passed, 2 skipped, 0 failed</b> "
             "<span class='cite'>(was 997 + 2)</span>",
             "<span class='mono'>pytest</span> with CI's env "
             "(<span class='mono'>NEXUS_AUDIT_BACKEND=memory NEXUS_ENVIRONMENT=DISABLED "
             "DO_NOT_TRACK=1</span>)"),
            ("New tests", "<b>+39</b> — 36 in <span class='cite'>test_instrument_seed.py</span>, "
             "3 in <span class='cite'>test_repo_hygiene.py</span> for F-12",
             "<span class='mono'>pytest tests/test_instrument_seed.py</span>"),
            ("Existing tests broken by boot seeding", "<b>zero</b>",
             "Full suite run before staging; the only failure was hygiene's untracked-file guard, "
             "which is the known trap and not a behaviour change"),
            ("Live module collected", "<b>41</b> <span class='cite'>(was 36)</span>; live-source "
             "checks still <b>11</b>",
             "<span class='mono'>NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py "
             "--collect-only -q</span>"),
            ("Live module offline subset", "<b>25 passed</b> <span class='cite'>(was 20)</span>",
             "<span class='mono'>&hellip; -k &quot;DiagnosisLogic or PatienceBehaviour or "
             "TradeSideRuling&quot;</span>"),
            ("Lint / format", "clean", "<span class='mono'>ruff check src tests</span>, "
             "<span class='mono'>ruff format --check src tests</span> (82 files)"),
            ("Types", "<b>Success: no issues found in 57 source files</b> "
             "<span class='cite'>(was 56)</span>", "<span class='mono'>mypy</span> (strict)"),
            ("Repo hygiene", "<b>83 passed</b> <span class='cite'>(was 80)</span>",
             "<span class='mono'>pytest tests/test_repo_hygiene.py</span>"),
            ("CI, this batch", "Runs <span class='cite'>45819528009</span> (push) and "
             "<span class='cite'>45819539643</span> (pull request), both "
             "<span class='mono'>conclusion=success</span>: <b>36 passed / 0 failed / 5 geo-blocked "
             "/ 0 skipped of 41</b>",
             "<span class='mono'>gh api &hellip;/check-runs/&lt;job&gt;/annotations</span>"),
        ],
    )


# --------------------------------------------------------------------------- 9 · what is still open
def open_table() -> str:
    return table(
        ["Finding", "State after 7.3", "Why"],
        [
            ("<b>F-3</b> empty master", "<span class='chip'>CLOSED</span> §3",
             "L-C. The archive gate is reachable with the registry the app boots, and still refuses "
             "what has not been earned"),
            ("<b>F-9 / P-7</b> one-sidedness", "<span class='chip'>CLOSED</span> §5",
             "Ruled, implemented, pinned, and live-evidenced in run 19 at "
             "<span class='mono'>buy=2 sell=48</span>"),
            ("<b>F-12</b> run counts in source", "<span class='chip'>NEW · CLOSED</span> §7",
             "Found in this batch, corrected, and guarded by a negative-controlled test"),
            ("<b>F-8 / P-8</b> cross-endpoint agreement",
             "<span class='chip neg'>OPEN · REFRAMED as P-9</span> §6",
             "&Delta;t is now recorded, and it shows the endpoints are not simultaneous. A constant "
             "bps tolerance would measure nothing"),
            ("<b>F-6</b> 3 of 14 asset classes", "<span class='chip neg'>OPEN · now visible</span>",
             "The three classes with a verified free source are seeded; the other eleven must still "
             "render <span class='mono'>UNSUPPORTED</span> per D-019. "
             "<span class='mono'>len(AssetClass) == 14</span> is asserted so growth forces the "
             "scope to be re-argued"),
            ("<b>F-2</b> bybit geo-block", "<span class='chip neg'>OPEN · now visible in the API</span>",
             "Seeded at <span class='mono'>SUPPORTED</span> with the reason attached (§4). L-D still "
             "needs the D-021 VM"),
            ("<b>F-5</b> intermittent feed", "<span class='chip neg'>OPEN</span>",
             "Unchanged by this batch; five probe patterns, no cause established"),
            ("<b>F-11</b> half the fix offline-evidenced", "<span class='chip neg'>OPEN as a limitation</span>",
             "The <span class='mono'>http-*</span>-beside-a-network-fault path has still not recurred "
             "in a live run (§2.8)"),
        ],
    )


def limits_table() -> str:
    return table(
        ["#", "Limitation"],
        [
            ("1", "<b>The seed is a record, not a feed.</b> Nothing here fetches, streams or stores "
                  "market data. It changes what the system <i>knows it has proven</i>; the first "
                  "writer to the archive is still to come"),
            ("2", "<b>Ranks are only as good as their labels.</b> <span class='mono'>certify</span> "
                  "cannot judge an evidence label, so the seed's honesty rests on labels that name "
                  "what was measured. That is why every label is asserted non-trivial, over 40 "
                  "characters, and inside the audit payload's 200-char bound — and why a future seed "
                  "must be held to the same standard rather than copying the shape"),
            ("3", "<b>Dukascopy's rank is a judgement call</b>, argued in §1 and reversible by one "
                  "line. If <span class='mono'>DATA_AVAILABLE</span> is read as requiring "
                  "reconciliation against a second source, the honest rank is "
                  "<span class='mono'>CONNECTED</span> and EUR/USD leaves "
                  "<span class='mono'>ready_for_research</span>"),
            ("4", "<b>One instrument per verified source.</b> Three canonical instruments is what "
                  "the evidence supports, not what a UI wants. A fourth needs its own evidence, and "
                  "the seed has no mechanism for speculative rows — which is the point"),
            ("5", "<b><span class='mono'>data_status</span> stays "
                  "<span class='mono'>UNAVAILABLE</span> for all three.</b> No pipeline is running, "
                  "so nothing is flowing. Claiming <span class='mono'>LIVE</span> at seed time would "
                  "describe a feed that does not exist yet"),
            ("6", "<b>Seeding at boot is a behaviour change to "
                  "<span class='mono'>create_app</span>.</b> Every boot without an injected registry "
                  "now writes thirteen change-log entries. They are recorded against "
                  "<span class='mono'>STAGE-7.3-SEED</span> so they can be told apart from anything "
                  "a human or a pipeline claimed, and the registry is in-memory by default, so "
                  "nothing persists unless a store is configured"),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI &middot; Stage 7.3 The Master Is Seeded</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 7 of 23 &middot; sub-deliverable 7.3 (implementation) &middot;
authorised by D-046 &middot; <b>closed by D-047 + D-048 on 2026-11-26</b></div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
The instrument master is seeded &mdash; three instruments, four venues, and eleven ranks it declines</h1>
<div class="ribbon">IMPLEMENTATION BATCH &mdash; lever <b>L-C</b>, the last one deliverable from here.
The master was empty at boot, so every coverage route reported <code>total=0 active=0</code> and the
archive gate was unsatisfiable in production however honest the adapters were (<b>F-3</b>). It now
carries what previous CI runs already proved, and nothing else: <b>3 canonical instruments, 4 venue
mappings, 10 rungs climbed</b>, bybit included at <code>SUPPORTED</code> rather than dropped from
sight. Gate <b>1,036 passed / 2 skipped / 0 failed</b>, CI green on both events of this commit. Two
rulings landed with it &mdash; <b>P-7</b> adopted and pinned, <b>P-8</b> measured, and that
measurement reframed F-8 as <b>P-9</b>. One new finding, <b>F-12</b>: the file the seed cites most
had been disagreeing with itself about its own evidence.</div>
<div class="gate" style="margin-top:14px"><b>REVIEWED AND CLOSED &mdash; 2026-11-26.</b> The five
questions in &sect;11 were answered: batch 7.1 is <b>approved (D-047)</b>, and <b>D-048</b> ruled
P-9, confirmed dukascopy&rsquo;s rank, and closed Stage 7 with bybit&rsquo;s row left open and
visible. &sect;12 records what the rulings produced as code &mdash; the cross-endpoint pair is now
recorded rather than reconstructed by hand &mdash; and the new finding its first live run exposed,
<b>F-14</b>: <code>observed_at</code> is venue time in all four adapters, so receipt latency cannot
be measured at all. Stage 8 is named as the next batch.</div>

<h3>0 &middot; How one word was read<span class="tag">docs/14 §3.0 &middot; D-046</span></h3>
<p>The owner answered §2.9's three questions with <span class="mono">Proceed</span>. One word cannot
carry three different meanings safely, so the reading is written down where it can be corrected
rather than assumed silently:</p>
<div class="card">{reading_table()}</div>
<p class="cap"><b>D-046 is recorded as what it actually is</b> &mdash; the authorisation of Stage 7.3
plus adoption of the two recommendations. It is <i>not</i> an approval of Stage 7.1, because
<code>Proceed</code> points forward. Question 1 is re-asked in §11.</p>

<h3>1 &middot; L-C &mdash; what was seeded, and at what rank<span class="tag">nexus/instruments/seed.py &middot; F-3</span></h3>
<p>A new module writes down what CI already proved. It contacts no venue, needs no credential and
performs no I/O &mdash; a seed that needed the network to be true would not be a record, it would be
a hope:</p>
<div class="card">{seed_table()}</div>
<p class="cap"><b>Ten rungs climbed, thirteen change-log entries</b> (3 <span class="mono">REGISTER</span>
+ 10 <span class="mono">CERTIFY</span>), every one
<span class="mono">requested_by=STAGE-7.3-SEED</span>. The three <span class="mono">CONNECTED</span>
rungs declare <span class="mono">AUTH_NOT_APPLICABLE</span> and no other rung carries a declaration,
because lever L-E put that field on one rung only. Longest evidence label <b>163 characters</b>
against the audit payload's 200-char bound.</p>

<div class="gate"><b>The one judgement call, argued rather than asserted.</b> Why
<span class="mono">DATA_AVAILABLE</span> for dukascopy and not <span class="mono">CONNECTED</span>?
Because the rank is defined by the code that consumes it &mdash;
<span class="cite">ingestion/pipeline.py:47-49</span> says <i>&ldquo;<span class="mono">DATA_AVAILABLE</span>
means the feed was actually observed working &mdash; accepting <span class="mono">UNKNOWN</span> would
archive data from a mapping nobody has verified&rdquo;</i> &mdash; and every venue run that reached
the source since 2026-11-25 observed this feed working and returned real ticks that parsed. Withholding the rung
because the prices are unreconciled would have to be applied to okx too (F-8 <i>is</i> that unresolved
question), which would leave the master empty and defeat L-C. And
<span class="mono">DATA_AVAILABLE</span> is not <span class="mono">LIVE_VERIFIED</span>, which is the
rank that would claim reconciliation. So the scope limits travel <b>in the record</b> instead of being
expressed by withholding a rung: the label says <i>&ldquo;EURUSD only, one hour, unreconciled
(F-8)&rdquo;</i> and the notes name the twelve unverified divisors, the intermittent feed and the
absence of lot economics.</div>

<p><b>Nothing is seeded at a rank needing a credential.</b> This is the part that makes a seed
trustworthy, so it is stated as data rather than as intent:</p>
<div class="card">{rank_refusal_table()}</div>
<div class="gate">Pinned by <span class="mono">test_nothing_claims_a_rank_that_needs_a_credential</span>,
<span class="mono">test_nothing_is_active_or_tradeable</span> and
<span class="mono">test_coverage_is_non_zero_and_research_ready_is_the_only_readiness</span>.
Observed: <span class="mono">active()=()</span>, <span class="mono">tradeable()=()</span>, every
mapping's <span class="mono">is_tradeable=False</span>, every instrument's
<span class="mono">active=False</span> (D-002: data is not permission).</div>

<p><b>Economics nobody measured are reported missing, not filled in.</b> okx publishes
<span class="mono">ctVal/tickSz/minSz/qtyStep</span> and they were read off the live instrument
endpoint. The other three sources publish no lot economics in the data this project verified, so
nothing is invented for them &mdash; and <span class="mono">coverage_report</span> has fields for
exactly that, which a seed supplying quiet numbers would empty:</p>
<div class="ev"><span class="k"># executed, not described</span>
missing_contract_size = ('INS-BTC-USDT-USDT@BYBIT', 'INS-BTC-USDT@BINANCE', 'INS-EUR-USD@DUKASCOPY')
missing_tick_size     = ('INS-BTC-USDT-USDT@BYBIT', 'INS-BTC-USDT@BINANCE')
<span class="k"># okx is the one mapping with measured economics, so it appears in neither list.</span>
<span class="k"># dukascopy's tick_size 0.00001 is the one DERIVED value - from the verified point</span>
<span class="k"># divisor 100000 - and its notes say "derived from the verified divisor", not "published".</span></div>

<h3>2 &middot; The two traps a boot-time seed has to avoid<span class="tag">both pinned by test</span></h3>
<p>Both fail silently and both corrupt a record that is supposed to be append-only, so neither was
left to care:</p>
<div class="ba before"><div class="hd">TRAP 1 &mdash; register() OVERWRITES</div><pre>Re-registering an instrument that already exists replaces the stored record and logs REMAP.
At boot that would reset every certified mapping to UNKNOWN &mdash; each restart silently
uncertifying the master it had just built.</pre></div>
<div class="ba before"><div class="hd">TRAP 2 &mdash; certify() DOWNWARD IS A DEMOTION</div><pre>Claiming a rung BELOW the current one is recorded as DE_CERTIFY. A seed that restated its own
ranks on every boot would demote anything a future pipeline had since earned.</pre></div>
<p>So an instrument already in the master is <b>never re-registered</b>, and a rung already held is
<b>never re-claimed</b>. Observed by executing the module:</p>
<div class="ba after"><div class="hd">SECOND CALL &mdash; TRANSCRIPT</div><pre># first call
registered      = ('INS-BTC-USDT-USDT', 'INS-BTC-USDT', 'INS-EUR-USD')
rungs_climbed   = 10   rungs_skipped = 0
changes         = 13  kinds = ['CERTIFY', 'REGISTER']
requested_by    = ['STAGE-7.3-SEED']
auth declared   = [('BINANCE', 'AUTH_NOT_APPLICABLE'), ('DUKASCOPY', 'AUTH_NOT_APPLICABLE'), ('OKX', 'AUTH_NOT_APPLICABLE')]
longest label   = 163 chars (limit 200)

# second call (a boot must not rewrite history)
registered      = ()   climbed = 0   skipped = 10
changes         = 13  (unchanged)</pre></div>
<div class="gate">Pinned by <span class="mono">test_a_second_call_registers_nothing_climbs_nothing_and_records_nothing</span>,
<span class="mono">test_no_remap_and_no_de_certify_entries_appear</span> (asserting the kind set is
<i>exactly</i> <span class="mono">{{REGISTER, CERTIFY}}</span>),
<span class="mono">test_status_survives_repeated_boots</span>, and
<span class="mono">test_a_mapping_somebody_else_certified_higher_is_never_demoted</span> &mdash; which
certifies okx to <span class="mono">TRADE_ENABLED</span> first and then proves a later boot leaves it
there instead of restating it down.</div>
<p><span class="mono">SeedMapping.__post_init__</span> refuses a ladder that could not be climbed
&mdash; one starting above <span class="mono">SUPPORTED</span>, skipping a rung, empty, putting an
auth declaration on the wrong rung, omitting it from <span class="mono">CONNECTED</span>, or carrying
a label past the 200-char bound. <b>A bad seed fails when it is declared, not halfway through a
boot</b>; six tests cover the refusals and a seventh pins that the declared seed satisfies its own
guard.</p>

<h3>3 &middot; F-3 closed &mdash; the observable, through the API and through the gate<span class="tag">docs/14 §3.3</span></h3>
<p>Stage 7.2 proved the archive gate was reachable <i>in principle</i>, with a registry built inside a
test. This proves it is reachable with the registry the application actually boots &mdash; and that
it still refuses what has not been earned:</p>
<div class="card">{f3_table()}</div>
<div class="ba after"><div class="hd">THE GATE, EXECUTED AGAINST THE SEEDED REGISTRY</div><pre>BINANCE  BTCUSDT 1m bar  -> bars_accepted=1  status_refusals={{}}                 id=INS-BTC-USDT
DUKASCOPY EURUSD 1m bar  -> bars_accepted=1  status_refusals={{}}                 id=INS-EUR-USD
BYBIT    BTCUSDT 1m bar  -> bars_accepted=0  status_refusals={{'BYBIT:SUPPORTED': 1}}  archived: none

MINIMUM_STATUS_FOR_ARCHIVE is VenueStatus.DATA_AVAILABLE   <span class="k">&lt;- pipeline.py:50</span>
instrument_id resolved from the master, not invented by the pipeline</pre></div>
<p><b>Two escape hatches, both tested.</b> <span class="mono">create_app(seed=False)</span> boots an
empty master on purpose, and an <b>injected</b> registry is never seeded at all &mdash; what a caller
built is what the app serves, so a test fixture stays a test fixture and no composition root has its
own registry silently rewritten underneath it. Every pre-existing
<span class="mono">count == 0</span> pin in the suite still passes because of that rule, not despite it.</p>

<h3>4 &middot; Bybit stays visible &mdash; and &ldquo;visible&rdquo; now means something<span class="tag">D-045 ruling &middot; F-2</span></h3>
<p>The owner's ruling was that bybit's row stays open <b>and visible</b> rather than being dropped
from sight. Seeding it at <span class="mono">SUPPORTED</span> keeps it in the master; the reason it
goes no higher lives in the mapping's <span class="mono">notes</span>. But
<span class="mono">_mapping_to_dict</span> did not expose <span class="mono">notes</span>, so
<span class="mono">/v1/instruments</span> served <span class="mono">BYBIT &hellip; SUPPORTED</span>
with no reason attached &mdash; and a rank on its own reads as coverage.</p>
<div class="ba before"><div class="hd">BEFORE &mdash; WHAT THE API SERVED</div><pre>{{"venue": "BYBIT", "venue_symbol": "BTCUSDT", "status": "SUPPORTED", "is_tradeable": false,
 "contract_size": null, "tick_size": null, ...}}
<span class="k"># True, and unreadable as anything but a claim of coverage. No reason, no finding, no path out.</span></pre></div>
<div class="ba after"><div class="hd">AFTER &mdash; notes SERIALISED FOR MAPPINGS AND INSTRUMENTS</div><pre>{{"venue": "BYBIT", "venue_symbol": "BTCUSDT", "status": "SUPPORTED", "is_tradeable": false,
 "notes": "GEO-BLOCKED from every hosted runner (403 at the CloudFront edge, run 45724918466;
           finding F-2). Adapter exists; never verified. Needs the D-021 deployment VM as a
           self-hosted runner (L-D).", ...}}
<span class="k"># The rank, and the reason it stops there, in the same payload.</span></pre></div>
<div class="gate">A status with no visible reason is visible only in the sense that it is not hidden,
which is not the same thing. No test pinned the previous key set, so nothing else moved. Pinned by
<span class="mono">test_bybit_is_present_at_its_honest_rank_with_the_block_recorded</span> and
<span class="mono">test_the_seeded_master_lists_bybit_as_supported_not_as_covered</span>, which reads
the reason back <i>through the API</i>.</div>

<h3>5 &middot; P-7 ruled and pinned<span class="tag">docs/14 §3.5 &middot; F-9</span></h3>
<p>Accepted as recommended: <b>a one-sided trade list is evidence, never a failure.</b>
<span class="mono">_assert_ticks</span> already accepted <span class="mono">side in (None, "BUY",
"SELL")</span>; the ruling is now pinned by <span class="mono">TestTradeSideRuling</span> rather than
resting on an absence. The history is F-9 &mdash; <span class="cite">docs/06</span> recorded okx's
first live verification as &ldquo;50 trades with both sides present&rdquo;, which read as an invariant
but never was one, and run <span class="cite">45759709313</span> returned 50 buys and passed.</p>
<div class="ev"><span class="k"># run 19, live: the distribution as recorded, and it passed</span>
okx.trades count=50 price_min=60591.2 price_max=60593.9 sides=['BUY', 'SELL'] buy=2 sell=48 unspecified=0
<span class="k"># run 45759709313, live: one side only, and it passed - correctly</span>
okx.trades count=50 sides=['BUY']</div>
<p><b>Counts, not just the set of sides.</b> <span class="mono">sides=['BUY','SELL']</span> is
identical for a 49/1 minute and a 25/25 minute, so the set alone cannot be compared between runs.
<span class="mono">side=None</span> is recorded as <span class="mono">unspecified=</span>, because
some feeds do not say and that is a fact about the feed rather than a defect in it.</p>
<div class="gate"><b>The asymmetry with the book is the ruling, not an inconsistency.</b>
<span class="mono">_assert_book</span> still fails a one-sided book and a test asserts that it does: a
book with no asks cannot be crossed, quoted or traded against, so it indicates a broken feed, while a
one-sided trade window indicates a quiet market. Two different things, two different rules, both
pinned.</div>

<h3>6 &middot; P-8 measured &mdash; and it reframed F-8<span class="tag">P-9 &middot; the batch's real finding</span></h3>
<p>The <span class="mono">.book</span> evidence line now records <span class="mono">observed_at</span>,
which <span class="mono">.quotes</span> always did. That is precisely the half F-8 named as missing.
<b>Four</b> runs have carried it &mdash; <span class="cite">c48c714</span>'s
<span class="mono">push</span>/<span class="mono">pull_request</span> pair and
<span class="cite">4760462</span>'s &mdash; all four <span class="mono">conclusion=success</span>:</p>
<div class="card">{p8_table()}</div>
<p class="cap">Convention as in §2.5: <span class="mono">gap_bps = |mid_quotes &minus; mid_book| /
mid_quotes &times; 1e4</span>. Both timestamps come from the same annotation, so &Delta;t is measured
rather than inferred. <b>&Delta;t is 1.287&ndash;1.435 s, mean 1.361 s &mdash; remarkably stable
across four runs and two commits.</b> <span class="mono">gap_bps</span> is 0.000&ndash;1.250, mean
0.601, exactly zero in 1 of 4; the implied rate is 0.000&ndash;0.904 bps/s. Every nonzero gap exceeds
the 0.016 bps quoted spread by at least <b>29&times;</b>, which is what §2.5 could not explain and
&Delta;t now does: the spread is a property of the book at one instant, and the gap is a property of
<b>1.3 seconds of market</b>.</p>
<div class="ba after"><div class="hd">WHAT THIS ESTABLISHES</div><pre>The two endpoints are fetched SEQUENTIALLY, about 1.3 s apart - not simultaneously.
So a nonzero gap is not evidence of disagreement at all: it is evidence that the market
moved during the fetch interval.

Run 19 shows the mechanism directly. The trade list's newest tick is 12:26:18.592 at
60591.2-60593.9; the book read 1.764 s later sits at 60587 - a 0.693 bps fall, which is
exactly the size of the "gap".

Run 18 had the same dt and a gap of precisely zero, because the price did not move in
that window. Same interval, different market, different "gap".</pre></div>
<div class="gate"><b>That reframes F-8.</b> §2.5's distribution &mdash; exactly zero in 6 of 12 runs,
max <b>2.223 bps</b>, mean <b>0.515</b>, 6 of 12 above the 0.016 bps quoted spread &mdash; is not
twelve measurements of endpoint disagreement. It is twelve measurements of <b>how far BTC moved in
roughly 1.3 seconds</b>. A constant bps tolerance is therefore the wrong instrument: the honest bound
is a rate, <span class="mono">gap_bps / &Delta;t</span>, and four runs give 0.000&ndash;0.904 bps/s
&mdash; a range whose upper end so small a sample cannot bound.
<b>No tolerance is asserted and none is chosen</b>, because a number picked to make the observed runs
pass is not a measurement. §11 asks the owner to rule on the reframing rather than on a number.</div>
<p class="cap">Nothing in <span class="mono">_assert_book</span> asserts agreement between the two
endpoints, which is why all four runs passed with gaps of 0.000, 0.693, 0.461 and 1.250 without any
being judged. The measurement was added to the evidence line only &mdash; that is the whole of P-8's
adopted half.</p>
<div class="blocked"><b>One limitation this batch owes rather than hides.</b> Runs 22 and 23 both
skipped <span class="mono">test_parsed_ticks_are_in_the_right_price_band</span> (F-5: the feed did not
answer inside the patience budget), and that is the check which emits the renamed
<span class="mono">layout_flag=</span> key from F-13. So that correction is <b>offline-evidenced only</b>
and has not yet been observed in a live run &mdash; the same class of limitation as F-11.
<span class="mono">verify_layout</span> itself passed in both runs, so the layout claim is
live-evidenced; the renamed key is not yet.</div>

<h3>7 &middot; F-12 and F-13 &mdash; the record contradicting its own evidence<span class="tag">NEW &middot; both found and fixed here</span></h3>
<p>Found while writing this board's own §1, in the module the seed cites most. Two defects, both in
<span class="cite">ingestion/dukascopy.py</span>, both surviving <span class="cite">62fe026</span>
(&ldquo;bound the run counts, so they cannot go stale again&rdquo;):</p>
<div class="card">{f12_table()}</div>
<p><b>The cause is structural, not careless.</b> Two venue runs appear per commit
(<span class="mono">push</span> and <span class="mono">pull_request</span>, the latter not suppressed
by the path filter), so a total written into source is stale on the very push that carries it. Prose
was bounded in <span class="cite">62fe026</span>; source was not.</p>
<div class="ba before"><div class="hd">BEFORE &mdash; THE SAME FILE, TWO COUNTS, ONE FLAG</div><pre>module docstring :  "...twelve consecutive CI runs... four before the flip... and eight after it"
flag's comment   :  "It passed ten times in a row... four before the flip and six after it"

module docstring :  "...the silent 100x error warned about below.
                     therefore ``True`` and every record carries source=..."
                     <span class="k">^ no subject. Nothing says WHAT is True.</span></pre></div>
<div class="ba after"><div class="hd">AFTER &mdash; A FLOOR, AND A SENTENCE WITH A SUBJECT</div><pre>module docstring :  "...passed on a genuine bi5 hour in every CI run since 2026-11-25: four
                     before the flip (45754638978, 45756716181, 45758610197, 45759709313) and
                     every run after it."
flag's comment   :  "It has passed in every venue run since 2026-11-25 ... (the enumerated
                     table grows in docs/14 §2.1, never here: a count in source is stale on
                     the next push)"
<span class="k"># ...which F-13, below, then had to correct AGAIN. Replacing a stale count with an</span>
<span class="k"># unqualified universal is not a fix; it is a different way of being wrong.</span>
module docstring :  "...``LAYOUT_VERIFIED`` is therefore ``True`` and every record carries
                     source="DUKASCOPY_BI5"."

<span class="k"># The four pre-flip ids stay enumerated: they are fixed history and will never change.</span>
<span class="k"># The post-flip set is a floor, and docs/14 §2.1 is the only place allowed to grow.</span></pre></div>
<div class="gate"><b>Guarded, and the guard is negative-controlled.</b>
<span class="mono">TestSourceStatesNoVenueRunCount</span> (3 tests) scans every shipped module for a
run count and fails with an instruction to state a floor instead. Its patterns are deliberately narrow
so static facts survive &mdash; &ldquo;five different probe patterns&rdquo;, &ldquo;twelve other
pairs&rdquo; and &ldquo;12 of the 13 divisors&rdquo; are facts about the world, not tallies of runs.
Injecting <span class="mono">seventeen venue runs</span> into <span class="cite">seed.py</span> made
the guard fail as designed; removing it made the suite green. <b>A guard that has never been seen to
fire proves nothing.</b> Two further tests pin the positive form: the claim is stated as a floor, the
four pre-flip ids remain cited, and the sentence naming the flag still has its subject.</div>

<div class="ba before"><div class="hd">F-13 &mdash; THE &ldquo;FIX&rdquo; ABOVE WAS ITSELF WRONG</div><pre>The replacement floors were UNIVERSALS: "every CI run since 2026-11-25", "every venue run since
2026-11-25". The two runs this batch's own first commit triggered falsified the second one.

run 45822394958 (push)          run 45822408025 (pull request)
  35 passed / 0 failed            35 passed / 0 failed
  5 geo-blocked / 1 SKIPPED       5 geo-blocked / 1 SKIPPED
  skipped: verify_layout_...      skipped: parsed_ticks_...
  dukascopy.layout  ABSENT        dukascopy.layout  present, passed=True

Run 20 performed NO layout verification at all - and still published:

  dukascopy.ticks count=5074 ... source=DUKASCOPY_BI5 layout_verified=True
                                                       ^^^^^^^^^^^^^^^^^ the CONSTANT, echoed</pre></div>
<p>The harness emitted <span class="mono">LAYOUT_VERIFIED</span> &mdash; a module constant &mdash; under
the key <span class="mono">layout_verified=</span>, not a result measured in that run. A reader of run
20's annotation would conclude the layout had been verified there. It had not.</p>
<div class="gate"><b>And the claim was never safe, even before run 20 broke it.</b> The check has
<i>always</i> been able to skip: <span class="cite">docs/14</span> §2.1 already recorded run 13
skipping its ticks fetch and called it designed behaviour &mdash; two paragraphs below the unqualified
universal, unreconciled. An unqualified &ldquo;every run&rdquo; over a check that can skip is a claim
waiting for its counterexample.</div>
<p><b>Three corrections, all applied.</b> <b>(1)</b> The claim is qualified everywhere it appears
&mdash; this module's docstring, its <span class="mono">LAYOUT_VERIFIED</span> comment,
<span class="mono">verify_layout()</span>'s own docstring, <span class="cite">docs/14</span> §2.1 and
§3.6, <span class="cite">docs/07</span>, <span class="cite">docs/00</span>, both boards and
<span class="cite">design/index.html</span> &mdash; each stating that a skip is not a pass and why.
<b>(2)</b> The evidence key is renamed <span class="mono">layout_verified=</span> &rarr;
<span class="mono">layout_flag=</span> on the <span class="mono">dukascopy.ticks</span> line, with a
comment naming run <span class="cite">45822394958</span> as the reason: the value is the constant, so
the key now says so instead of implying a measurement. <b>(3)</b> The guard test is rewritten.</p>
<div class="ba before"><div class="hd">THE GUARD HAD PINNED THE FALSE CLAIM IN PLACE</div><pre>test_the_dukascopy_claim_is_stated_as_a_floor originally asserted:

    assert "every CI run since 2026-11-25" in text
    assert "every venue run since 2026-11-25" in text

Correcting the prose would have FAILED CI. The guard was load-bearing for the error.</pre></div>
<div class="ba after"><div class="hd">AFTER &mdash; IT ASSERTS THE QUALIFICATION, NOT THE WRAPPING</div><pre>assert "that reached the source" in text          <span class="k"># the qualifier is present</span>
assert "A skip is not a pass" in text             <span class="k"># and so is the reason for it</span>
for unqualified in ("every CI run since", "every venue run since"):
    assert unqualified not in text                <span class="k"># the false form cannot return</span>
assert text.count("that reached the source") >= 3 <span class="k"># in all three places, not one</span>

<span class="k"># Matched independently of how prose wraps across "#:" comment prefixes: an exact-phrase</span>
<span class="k"># match fails on a line break and passes on a rewrap, which is backwards for a guard.</span></pre></div>
<div class="gate"><b>Negative-controlled both ways.</b> Injecting
<span class="mono">seventeen venue runs</span> fails the count rule; injecting
<span class="mono">every venue run since 2026-11-25</span> fails the qualification rule with
<i>&ldquo;the unqualified claim crept back in&rdquo;</i>; removing both makes the suite green.
<b>The sharper lesson is recorded rather than smoothed over: a guard that asserts a stale-prone exact
phrase is worse than no guard, because it makes the error load-bearing.</b> F-5 &mdash; the
intermittent feed that causes the skips &mdash; remains open, which is what makes the qualifier
permanent rather than temporary.</div>

<h3>8 &middot; Gate evidence<span class="tag">re-run for this board</span></h3>
<div class="card">{gate_table()}</div>
<p class="cap">Scope of the batch: <b>5 production files, 3 test files, 3 documents, 1 board</b>.
Every number above was produced by the command beside it and re-verified before being written here;
anything that re-triggers per push is stated as a floor or a bound, never as a total.</p>

<h3>9 &middot; What 7.3 did not close<span class="tag">docs/14 §3.8</span></h3>
<div class="card">{open_table()}</div>

<h3>10 &middot; Limitations of this batch<span class="tag">docs/14 §3.9</span></h3>
<div class="card">{limits_table()}</div>

<h3>11 &middot; Decision requested &mdash; and answered<span class="tag">docs/14 §3.10 &middot; §4.0</span></h3>
<p class="cap">These five were asked when this board was first presented. All five are now ruled, so
the request is kept as asked and the answer is written beside it &mdash; a question that was answered
should still show what was actually being decided.</p>
<div class="card">{ruled_table()}</div>
<div class="ask">
<ol>
<li><b>The D-046 reading.</b> §0 records how <span class="mono">Proceed</span> was read. If any part
of it was wrong &mdash; in particular if Stage 7.1 was meant to be approved, or if P-8's tolerance was
meant to be chosen now &mdash; say so and the record will be corrected rather than defended.</li>
<li><b>Is batch 7.1 approved?</b> Still unanswered, still <span class="mono">PENDING</span> with no
decision id in <span class="cite">docs/07</span>. Its nine findings and five levers are the
foundation everything since has stood on, which is exactly why it should not stay unratified by
drift.</li>
<li><b>P-9 &mdash; F-8's reframing.</b> §6's two runs show the okx quotes and book endpoints are
fetched &asymp;1.3 s apart, so the recorded &ldquo;gaps&rdquo; (max 2.223 bps over twelve runs, 0.693
in run 19) are market movement during the fetch interval, not endpoint disagreement.
<b>Recommendation: drop the idea of a constant bps tolerance</b> and either treat
<span class="mono">gap_bps / &Delta;t</span> as the quantity of interest, accumulating runs until a
rate bound can be sized, or accept that the two endpoints are simply not simultaneous and stop
comparing their mids at all. A fixed tolerance would encode a number that measures nothing.</li>
<li><b>Dukascopy's rank (§10 item 3).</b> <span class="mono">DATA_AVAILABLE</span> as argued in §1, or
<span class="mono">CONNECTED</span> if <span class="mono">DATA_AVAILABLE</span> is read as requiring
cross-source reconciliation? <b>Recommendation: keep
<span class="mono">DATA_AVAILABLE</span></b>, because the pipeline defines the rung as &ldquo;the feed
was actually observed working&rdquo;, and because the alternative would apply equally to okx and empty
the master.</li>
<li><b>What comes next.</b> Stage 7's mandate &mdash; retire the unverified rows market by market
&mdash; is now discharged for dukascopy/EURUSD and demonstrably <i>not</i> dischargeable for bybit
from a hosted runner. The remaining Stage 7 work is L-D, which needs the D-021 VM.
<b>Recommendation: close Stage 7 with bybit's row open and recorded, and take the next batch to
Stage 8</b>, rather than hold a stage open on a machine that does not exist yet.</li>
</ol>
</div>

<h3>12 &middot; What the rulings produced<span class="tag">commit 7929a96 &middot; docs/14 §4</span></h3>
<p>The owner answered P-9 with <span class="mono">Recommend</span>, but the recommendation as
published offered two paths &mdash; accumulate a rate bound, or stop comparing the mids at all. That
ambiguity is mine, so it is resolved here rather than hidden: <b>accumulate the rate, and keep
recording.</b> Dropping the comparison would discard the only instrument that can tell a
1.3-second market move from a venue serving a stale ticker beside a live book, which is the defect
F-8 was originally raised about.</p>
<p>A ruling that is not implemented is prose, so the pair is now recorded properly instead of being
reconstructed by hand from two separate evidence lines. A live check fetches quotes and book
<b>back-to-back</b> &mdash; the interval measured across the whole test class spanned the trades and
candles fetches in between, and adjacent calls measure the endpoints themselves, which is the
denominator the rate needs:</p>
<div class="ev"><span class="mono">EVIDENCE okx.cross_endpoint quotes_mid=&hellip; book_mid=&hellip;
gap_bps=&hellip; dt_observed_s=&hellip; dt_wall_s=&hellip; bps_per_s_observed=&hellip;
bps_per_s_wall=&hellip; quoted_spread_bps=&hellip; <b>asserts_agreement=False</b></span></div>
<div class="card">{p9_table()}</div>
<p class="cap">Three pure functions hold the arithmetic so it can be pinned without a venue:
<span class="mono">_gap_bps</span> is &sect;2.5&rsquo;s convention
<span class="mono">|qm &minus; bm| / qm &times; 1e4</span> in exactly one place, and
<span class="mono">_rate_bps_per_second</span> returns <span class="mono">None</span> rather than
dividing by a non-positive interval &mdash; a rate with no denominator is the same defect F-8 named.
Seven offline tests re-derive run <span class="mono">45819539643</span>&rsquo;s published 0.693 bps
over 1.287 s and require 0.539 bps/s back, and one of them <i>is</i> the ruling: <b>a 5,064 bps
divergence, the book at half the price, must pass.</b> Writing that test caught an arithmetic error
of mine &mdash; I expected <span class="mono">5064.713</span>, the helper produced
<span class="mono">5064.56</span> &mdash; so the verified value is hardcoded with its arithmetic
shown beside it.</p>
<div class="blocked"><b>F-14 &mdash; found by the dual recording, on its first run.</b>
<span class="mono">dt_observed_s=0.739</span> beside <span class="mono">dt_wall_s=0.294</span> is not
possible if both measure one interval: the venue-stamped gap was <b>2.5&times; the wall clock</b>.
Reading the adapters explains it, and the explanation is not local to okx.</div>
<div class="card">{f14_table()}</div>
<p class="cap"><b>Not fixed here, deliberately.</b> Changing what
<span class="mono">observed_at</span> means touches four adapters, every record type and every test
that asserts on those fields &mdash; a semantic change that deserves its own authorisation rather
than riding along inside a stage closure. It is recorded with its cost, which is how Stage 7.1
handled every finding needing code. The mitigation that <i>is</i> in place is the dual recording
itself: it made the discrepancy visible on the first attempt instead of hiding it inside one
ambiguous field for a month.</p>
<div class="gate"><b>It also corrects &sect;6&rsquo;s mechanism, though not its conclusion &mdash; and
strengthens the conclusion.</b> The &asymp;1.3 s in that table was venue-timestamp skew between two
endpoints across non-adjacent tests; the true adjacent fetch interval is &asymp;0.3 s wall clock.
Fetched adjacently the two endpoints <b>agreed exactly</b>, gap 0.000 bps in both runs. Shrink the
interval and the &ldquo;disagreement&rdquo; disappears, which is what a market-movement explanation
predicts and what an endpoint-disagreement explanation does not. No tolerance is asserted, and none
should be.</div>
<div class="card">{mandate_table()}</div>
<p class="cap">Both honesty rows carried since Stage 5 are therefore retired <b>or</b> accounted for:
dukascopy&rsquo;s <span class="mono">LAYOUT_VERIFIED = False</span> is retired for EURUSD, and
bybit&rsquo;s geo-block is not retired but is now visible in the API with its reason, finding id and
remedy attached rather than living only in a document.</p>
<div class="card">{close_table()}</div>

<footer>Stage 7.3 &middot; implementation &middot; D-046 &middot; closed by D-047 + D-048 &middot; commits c48c714 (L-C, P-7, P-8) and
the F-12 correction &middot; gate 1,036 passed / 2 skipped / 0 failed, +39 tests &middot; ruff +
format clean, mypy strict clean on 57 files, hygiene 83 &middot; CI runs 45819528009 and 45819539643
both success, 36 passed / 0 failed / 5 geo-blocked of 41, and 4760462's pair
45825586882 + 45825598469 both success at 35 / 0 / 5 geo-blocked / 1 skipped of 41 &middot; the master now carries three
instruments and four venue mappings, bybit among them at SUPPORTED and not omitted &middot; verify_layout
has passed in every venue run <i>that reached the source</i> since 2026-11-25, stated as a floor
because each later commit adds two more attempts, and qualified because a run whose feed never answers
skips rather than passes (F-13) &middot; and 7929a96's pair 45829853116 + 45829842623 both success at
44 passed / 0 failed / 5 geo-blocked / <b>0 skipped</b> of 49, which is the first run with no skips at
all and so live-evidences F-13's renamed layout_flag= key at last, and returned a fully one-sided
trade list (buy=0 sell=50) that passed &mdash; P-7 vindicated live a second time &middot; F-3 closed,
F-12 and F-13 closed, F-8 reframed as P-9 and now ruled and implemented, <b>F-14 found</b>, F-2 F-5
F-6 F-11 F-14 still open</footer>
</div></body></html>"""
    out = HERE / "stage7-3-master-seeded.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
