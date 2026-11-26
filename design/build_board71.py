"""Stage 7.1 board: market & venue coverage — what is actually verified, per venue and per class.

Every number here comes from a CI check annotation at HEAD, from a real in-process boot of the API,
or from a probe that was executed against the domain types. Where the record disagrees with the
evidence, both are shown.

Run:  backend/.venv/bin/python design/build_board71.py
"""

from __future__ import annotations

import pathlib
import re

from build_board42 import CSS as CSS42
from build_specimen import fonts_css

HERE = pathlib.Path(__file__).resolve().parent
CSS = CSS42 + """
h3 { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 40px 0 2px; }
h3 .tag { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  font-weight: var(--font-weight-regular); color: var(--color-text-muted); margin-left: 8px; }
.ev { border: 1px solid var(--color-border-subtle); border-left: 3px solid
  var(--color-feedback-intelligence-graphic); border-radius: 0 var(--radius-card)
  var(--radius-card) 0; background: var(--color-surface-panel); padding: 10px 12px;
  margin-top: 10px; font-family: var(--font-family-mono); font-size: var(--font-size-data);
  line-height: 1.6; color: var(--color-text-secondary); white-space: pre-wrap;
  font-variant-numeric: tabular-nums; }
.ev .k { color: var(--color-text-primary); }
.finding { border: 1px solid var(--color-border-subtle); border-radius: var(--radius-card);
  background: var(--color-surface-panel); padding: 12px 14px; margin-top: 12px; }
.finding .fid { font-family: var(--font-family-mono); font-size: var(--font-size-label);
  letter-spacing: .08em; color: var(--color-feedback-intelligence-text); }
.finding .ft { font-size: var(--font-size-emphasis); font-weight: var(--font-weight-semibold);
  margin: 3px 0 6px; color: var(--color-text-primary); }
.finding p { margin: 6px 0; }
.cite { font-family: var(--font-family-mono); font-size: var(--font-size-caption);
  color: var(--color-text-muted); }
.gate { border: 1px solid var(--color-feedback-positive-graphic); border-radius: var(--radius-card);
  padding: 10px 14px; background: var(--color-feedback-positive-subtle); margin-top: 12px;
  font-family: var(--font-family-mono); font-size: var(--font-size-data);
  color: var(--color-feedback-positive-text); }
.blocked { border: 1px solid var(--color-feedback-warning-graphic);
  border-radius: var(--radius-card); padding: 10px 14px;
  background: var(--color-feedback-warning-subtle); margin-top: 12px;
  font-family: var(--font-family-mono); font-size: var(--font-size-data);
  color: var(--color-feedback-warning-text); }
.ask { border: 1px solid var(--color-border-strong); border-radius: var(--radius-card);
  background: var(--color-surface-elevated); padding: 14px 16px; margin-top: 14px; }
.ask ol { margin: 6px 0 0 18px; padding: 0; }
.ask li { margin: 8px 0; font-size: var(--font-size-body); line-height: 1.6; }
"""


def rows(items: list[tuple[str, ...]]) -> str:
    return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in items)


def mandate_table() -> str:
    return f"""<table>
<tr><th>honesty row carried since Stage 5</th><th>what it said</th><th>what the evidence now says</th>
<th>status</th></tr>
{rows([
    ("<b>bybit</b> — 403 geo-block",
     "connected-but-untested: v5 code exercised against public docs only, never a real response "
     "(<span class='cite'>docs/12 §1.4</span>)",
     "unchanged. 5 of 5 live checks still <span class='chip neg'>GEO-BLOCKED</span> at HEAD. The "
     "block is a property of where CI runs, not of the adapter",
     "<span class='chip warn'>OPEN — needs a host elsewhere</span>"),
    ("<b>dukascopy</b> — <span class='mono'>LAYOUT_VERIFIED = False</span>",
     "connected, layout-unverified: bi5 layout implemented from documentation alone "
     "(<span class='cite'>dukascopy.py:9, :45</span>)",
     "<b>the evidence the flag demands now exists and has reproduced twice</b> — "
     "<span class='mono'>verify_layout</span> passed against a real 25,761-byte bi5 hour. The "
     "constant, the source tag and four written claims are all still stale",
     "<span class='chip pos'>EVIDENCED</span> <span class='chip warn'>NOT RETIRED</span>"),
])}
</table>"""


def evidence_base() -> str:
    return f"""<table>
<tr><th>source of truth</th><th>identity</th><th>what it gave</th><th>readable here?</th></tr>
{rows([
    ("live venue run <b>at HEAD</b>",
     "<span class='mono'>run 45759709313</span> · job <span class='mono'>139706589069</span> · "
     "<span class='mono'>25e314e</span> · 2026-11-26T05:10Z · <b>success</b>",
     "24 passed / 0 failed / 5 geo-blocked / 0 skipped of 29 — the <b>fourth</b> consecutive run with "
     "that headline",
     "<span class='chip pos'>yes — annotation</span>"),
    ("the three runs before it",
     "<span class='mono'>45758610197</span> · <span class='mono'>fa74748</span> · 04:59Z<br>"
     "<span class='mono'>45756716181</span> · <span class='mono'>b67ab39</span> · 04:41Z<br>"
     "<span class='mono'>45754638978</span> · <span class='mono'>a77865e</span> · 04:21Z — all success",
     "the same dukascopy layout result four times running, but <b>three different</b> reachability "
     "patterns — which is what makes F-1 solid and F-5 the opposite",
     "<span class='chip pos'>yes — annotations</span>"),
    ("CI on both commits of this batch",
     "<span class='mono'>run 45759700949</span> · <span class='mono'>25e314e</span> · <b>all five "
     "jobs success</b><br><span class='mono'>run 45758603745</span> · <span class='mono'>fa74748</span>"
     " · <b>all five jobs success</b>",
     "secret scanning · compose config · backend lint/types/tests · runtime smoke in a real container "
     "· amd64+arm64 image — the repository is green after a batch that changed only docs and design",
     "<span class='chip pos'>yes — per-job conclusions</span>"),
    ("job logs", "<span class='mono'>gh run view --log-failed</span> / <span class='mono'>…/jobs/&lt;id&gt;/logs</span>",
     "would give the full pytest transcript",
     "<span class='chip neg'>no — EOF against results-receiver.actions.githubusercontent.com, "
     "not in this sandbox's allowed hosts</span>"),
    ("raw captures + report artifact",
     "<span class='mono'>live-verification</span> (<span class='mono'>live-captures/</span>)",
     "the actual JSON and bi5 bytes each adapter received",
     "<span class='chip neg'>no — download dies against productionresultssa14.blob.core.windows.net</span>"),
    ("annotation completeness", "GitHub caps annotation text; the workflow truncates its own report",
     "<span class='mono'>…truncated: 807 escaped characters over the cap</span> — the 5 GEO-BLOCKED "
     "rows and 2 PASS rows are past the cut",
     "<span class='chip warn'>partial — composition measured locally instead (below)</span>"),
    ("in-process boot of the API",
     "<span class='mono'>create_app()</span> + <span class='mono'>TestClient</span>, "
     "<span class='mono'>NEXUS_AUDIT_BACKEND=memory</span>",
     "what <span class='mono'>/v1/instruments/coverage</span> and "
     "<span class='mono'>/v1/data/coverage</span> really return today",
     "<span class='chip pos'>yes — executed here</span>"),
    ("probe of the domain types", "<span class='mono'>Venue</span>, <span class='mono'>VenueMapping</span>, "
     "<span class='mono'>InstrumentRegistry.certify</span>, <span class='mono'>coverage_report</span>",
     "what it takes to record a verified source, and what happens to a venue the enum does not contain",
     "<span class='chip pos'>yes — executed here, transcript in F-3/F-4/F-7</span>"),
])}
</table>"""


def decomposition_table() -> str:
    return f"""<table>
<tr><th>class in <span class='mono'>tests/test_live_endpoints.py</span></th><th>checks</th>
<th>touches the network?</th><th>result at HEAD</th><th>is it coverage evidence?</th></tr>
{rows([
    ("<span class='mono'>TestBybitLiveEndpoints</span>", "5", "yes", "5 GEO-BLOCKED",
     "<b>yes</b> — evidence about bybit, and it says nothing was reachable"),
    ("<span class='mono'>TestOkxLiveEndpoints</span>", "5", "yes", "5 PASS", "<b>yes</b> — okx"),
    ("<span class='mono'>TestBinanceVisionLiveDumps</span>", "2", "yes", "2 PASS",
     "<b>yes</b> — binance vision archive"),
    ("<span class='mono'>TestDukascopyLiveLayout</span>", "3", "yes", "3 PASS",
     "<b>yes</b> — dukascopy URL, layout, price band"),
    ("<span class='mono'>TestDukascopyReachabilityDiagnostic</span>", "1", "yes", "1 PASS",
     "<b>partly</b> — it measures reachability, and at HEAD it declined to name a cause (F-5)"),
    ("<span class='mono'>TestDukascopyDiagnosisLogic</span>", "7", "<b>no</b>", "7 PASS",
     "<b>no</b> — tests our own verdict logic against fabricated inputs"),
    ("<span class='mono'>TestPatienceBehaviour</span>", "6", "<b>no</b>", "6 PASS",
     "<b>no</b> — tests our own retry policy against a fake transport"),
    ("<b>total</b>", "<b>29</b>", "16 network / 13 offline", "24 passed / 5 geo-blocked",
     "<b>11 checks are live evidence about a source</b>"),
])}
</table>"""


def okx_card() -> str:
    return """<div class="ev"><span class="k">okx.instruments</span>  count=1 symbol=BTC-USDT-SWAP
  contract_size=0.01 tick_size=0.1 min_qty=0.01 qty_step=0.01 status=live raw_fields=6
<span class="k">okx.quotes</span>     count=1 bid=61063.2 ask=61063.3 spread_bps=0.016
  observed_at=2026-11-26T04:41:19.571000+00:00
<span class="k">okx.trades</span>     count=50 price_min=61063.2 price_max=61064.8 sides=[BUY, SELL]
<span class="k">okx.bars</span>       count=100 interval=1m span_hours=1.65 close_min=60609
  close_max=61064.5 first=2026-11-26T03:02:00+00:00 last=2026-11-26T04:41:00+00:00
<span class="k">okx.book</span>       depth=40 best_bid=61063.2 best_ask=61063.3 spread_bps=0.016
  entitlement=LIVE</div>"""


def bv_card() -> str:
    return """<div class="ev"><span class="k">binance-vision.url</span>   day=2026-11-19 bytes=71720 zip=True
<span class="k">binance-vision.bars</span>  count=1440 interval=1m span_hours=23.98
  close_min=61446.56000000 close_max=64080.80000000
  first=2026-11-19T00:00:00+00:00 last=2026-11-19T23:59:00+00:00
<span class="k">binance-vision.parse</span> rows=1440 accepted=1440 rejected=0 had_header=False
  timestamp_units=us   &lt;- the microsecond fix (defect 40) proven on a real dump, not a fixture</div>"""


def duk_card() -> str:
    return """<div class="ev"><span class="k">dukascopy.url</span>     hour=2026-11-24T12:00:00+00:00 bytes=25761
  month_segment=10   capture calls=16   &lt;- sixteen transport calls to land one file
<span class="k">dukascopy.layout</span>  passed=True payload_bytes=25761 decompressed_bytes=101480
  tick_count=5074 reasons=-
  101480 / 20 = 5074 exactly; reasons empty is what verify_layout requires to pass
<span class="k">dukascopy.ticks</span>   count=5074 price_min=1.09502 price_max=1.0964
  source=DUKASCOPY_BI5_UNVERIFIED layout_verified=False   &lt;- F-1: the record still says unverified
<span class="k">dukascopy.probe</span>   production_ua=network-IngestFault browser_ua=network-IngestFault
  production_ua_other_hour=ok bytes=25313 lzma=True (10h_ticks.bi5)
<span class="k">dukascopy.diagnosis</span> verdict="the host was never reached (network-IngestFault), so no
  cause can be distinguished" action="re-run from a host with egress"   &lt;- F-5</div>"""


def venue_matrix() -> str:
    return f"""<table>
<tr><th>venue</th><th>adapter</th><th>credential</th><th>rank recorded in the running system</th>
<th>rank the evidence supports</th><th>why not higher</th></tr>
{rows([
    ("<b>OKX</b>", "<span class='mono'>ingestion/okx.py</span> · <span class='mono'>requires_credentials = False</span>",
     "none used", "<span class='chip neg'>nothing — the master is empty (F-3)</span>",
     "<span class='chip pos'>DATA_AVAILABLE</span> for BTC-USDT-SWAP only",
     "one instrument verified; TRADE_ENABLED needs a sandbox order lifecycle, LIVE_VERIFIED needs a "
     "live pilot + reconciliation (Stage 9+)"),
    ("<b>BYBIT</b>", "<span class='mono'>ingestion/bybit.py</span> · credential-free",
     "none used", "<span class='chip neg'>nothing</span>",
     "<span class='chip warn'>SUPPORTED</span> — adapter exists, has never seen a response",
     "403 at the CloudFront edge on public unauthenticated endpoints from every hosted runner; "
     "per D-007 okx's result says nothing about bybit"),
    ("<b>BINANCE</b> (Vision archive)", "<span class='mono'>ingestion/binance_vision.py</span> · credential-free",
     "none used", "<span class='chip neg'>nothing</span>",
     "<span class='chip pos'>DATA_AVAILABLE</span> for spot daily kline dumps",
     "an archive of history, not a venue: no quotes, no book, no orders, so no trade rung is even "
     "meaningful. Also <span class='mono'>market_tick</span>/<span class='mono'>market_bar</span> "
     "were retired from the DDL in Stage 6.2"),
    ("<b>DUKASCOPY</b>", "<span class='mono'>ingestion/dukascopy.py</span> · credential-free",
     "none used", "<span class='chip neg'>nothing — and it <b>cannot</b> be recorded: not a "
     "<span class='mono'>Venue</span> member (F-4)</span>",
     "<span class='chip pos'>DATA_AVAILABLE</span> for EURUSD bi5 ticks, once F-1 and F-4 are closed",
     "layout verified for one pair and one hour; 12 of the 13 divisors in "
     "<span class='mono'>POINT_DIVISORS</span> have never been checked against a real file"),
    ("MT4 · MT5 · CTRADER · IBKR · OANDA · ALPACA",
     "<span class='chip neg'>no adapter exists</span>", "would need credentials",
     "<span class='chip neg'>nothing</span>", "<span class='chip neg'>UNKNOWN</span>",
     "enum members only (D-007 scope). Every one is credentialed and most are paid, so they sit "
     "outside D-019's $0/month constraint — they must render UNSUPPORTED and greyed, never offered"),
])}
</table>"""


def asset_matrix() -> str:
    return f"""<table>
<tr><th>asset class</th><th>free source implemented</th><th>live-verified?</th><th>honest UI state</th></tr>
{rows([
    ("<span class='mono'>CRYPTO_PERP</span>", "okx (BTC-USDT-SWAP) · bybit adapter",
     "<span class='chip pos'>okx yes</span> <span class='chip neg'>bybit no</span>",
     "available for research on okx for one instrument; bybit greyed with its registry state"),
    ("<span class='mono'>CRYPTO_SPOT</span>", "binance vision daily kline dumps · okx/bybit spot code",
     "<span class='chip pos'>dumps yes</span>", "history available; live spot only where okx is verified"),
    ("<span class='mono'>FX_SPOT</span>", "dukascopy bi5 ticks (13 pairs have divisors)",
     "<span class='chip warn'>EURUSD only, and unrecordable (F-4)</span>",
     "provisional until F-1/F-4 close; every FX test models <span class='mono'>Venue.MT5</span>, "
     "which has no source at all"),
    ("<span class='mono'>METALS</span>", "XAUUSD (divisor 100) and XAGUSD (1000) sit in the same "
     "dukascopy feed", "<span class='chip neg'>never</span>",
     "plausible at $0, unproven — a candidate for Stage 7.2, not a claim"),
    ("<span class='mono'>CRYPTO_FUTURES</span> · <span class='mono'>CRYPTO_OPTIONS</span> · "
     "<span class='mono'>FX_CFD</span> · <span class='mono'>EQUITIES</span> · "
     "<span class='mono'>ETF</span> · <span class='mono'>INDICES</span> · "
     "<span class='mono'>FUTURES</span> · <span class='mono'>OPTIONS</span> · "
     "<span class='mono'>FIXED_INCOME</span> · <span class='mono'>COMMODITIES</span>",
     "<b>none</b> — 10 of the 14 declared classes have no source of any kind",
     "<span class='chip neg'>no</span>",
     "<span class='chip neg'>UNSUPPORTED</span>: greyed with the registry state, never offered as "
     "tradable (Stage 3.1 capability-honesty law)"),
])}
</table>"""


def retirement_table() -> str:
    return f"""<table>
<tr><th>lever</th><th>what it closes</th><th>cost</th><th>whose authorisation</th><th>can it be done from here?</th></tr>
{rows([
    ("<b>L-A</b> — flip <span class='mono'>LAYOUT_VERIFIED</span> to True, switch the source tag to "
     "<span class='mono'>DUKASCOPY_BI5</span>, correct the four stale statements",
     "the dukascopy honesty row (F-1)",
     "$0 — one constant at <span class='mono'>dukascopy.py:45</span>, the tag selection at "
     "<span class='mono'>:113</span>, and text at <span class='mono'>dukascopy.py:9/:14</span>, "
     "<span class='mono'>test_live_endpoints.py:10/:674</span>, <span class='mono'>docs/06:247/:297</span>",
     "<b>the owner's</b> — this is <span class='mono'>backend/</span> production code, and the "
     "Stage 6.2 lift was scoped to that batch",
     "yes, immediately, if authorised"),
    ("<b>L-B</b> — make the FX source representable: add <span class='mono'>DUKASCOPY</span> to "
     "<span class='mono'>Venue</span> and refuse an out-of-scope venue at the domain boundary "
     "instead of crashing",
     "F-4, and unblocks recording any FX coverage",
     "$0 — one enum member plus a validation that raises a classified "
     "<span class='mono'>NexusError</span> rather than <span class='mono'>AttributeError</span>",
     "<b>the owner's</b> — production code, and it changes D-007's venue scope list",
     "yes, immediately, if authorised"),
    ("<b>L-C</b> — seed the master from evidence: register the instruments the four sources really "
     "serve, each at the rank its evidence supports and no higher, with the run id as the "
     "<span class='mono'>evidence</span> label",
     "F-3 — coverage stops being all zeros, and the archive gate becomes reachable",
     "$0 — a bootstrap module plus tests; nothing is invented, every rank cites a run",
     "<b>the owner's</b> — production code, and it decides what the whole UI shows",
     "yes, immediately, if authorised"),
    ("<b>L-D</b> — dispatch <span class='mono'>venue-verification.yml</span> with "
     "<span class='mono'>runner</span> set to a self-hosted label on the deployment host",
     "F-2 — the bybit row, the only one that cannot be closed by editing anything",
     "$0 — the input already exists; D-021's host is an Oracle Always Free ARM64 VM and D-024 chose "
     "bybit for Nigeria, where it is not geo-blocked",
     "nobody's — no code change, but it needs the VM to exist",
     "<span class='chip neg'>no</span> — this sandbox has no egress to bybit and no VM; blocked on "
     "deployment (D-021/D-028)"),
    ("<b>L-E</b> — rule on what <span class='mono'>CONNECTED</span> means for a credential-free "
     "source, or add a rung for it",
     "F-7 — without it, recording DATA_AVAILABLE requires certifying 'auth verified' with evidence "
     "that says no auth was verified",
     "$0 — a definition and possibly one enum rung; the ladder's one-step rule stays intact",
     "<b>the owner's</b> — it is a change to the certification vocabulary every later stage cites",
     "yes, immediately"),
])}
</table>"""


def four_runs_table() -> str:
    return f"""<table>
<tr><th>what</th><th>1 · 45754638978<br>a77865e · 04:21Z</th><th>2 · 45756716181<br>b67ab39 · 04:41Z</th>
<th>3 · 45758610197<br>fa74748 · 04:59Z</th><th>4 · 45759709313<br>25e314e · 05:10Z</th><th>reading</th></tr>
{rows([
    ("headline", "24 / 0 / 5 blocked of 29", "24 / 0 / 5 blocked of 29", "24 / 0 / 5 blocked of 29",
     "24 / 0 / 5 blocked of 29", "<span class='chip pos'>identical four times</span>"),
    ("dukascopy <span class='mono'>verify_layout</span>",
     "passed=True · 25761 → 101480 · 5074 · reasons=-", "passed=True · 25761 → 101480 · 5074 · reasons=-",
     "passed=True · 25761 → 101480 · 5074 · reasons=-", "passed=True · 25761 → 101480 · 5074 · reasons=-",
     "<b>byte-identical</b> — the evidence O-010 demands, four times (F-1)"),
    ("dukascopy parsed band", "1.09502 – 1.0964", "1.09502 – 1.0964", "1.09502 – 1.0964",
     "1.09502 – 1.0964", "identical: the same hour file, and EURUSD's divisor is right"),
    ("tag still recorded", "<span class='mono'>…BI5_UNVERIFIED</span>", "<span class='mono'>…BI5_UNVERIFIED</span>",
     "<span class='mono'>…BI5_UNVERIFIED</span>", "<span class='mono'>…BI5_UNVERIFIED</span>",
     "<span class='chip warn'>stale in all four</span> — the constant never changed"),
    ("dukascopy probes", "production_ua <b>ok</b>", "both UAs failed; other hour ok (25313)",
     "production failed; <b>browser_ua ok</b>", "production_ua <b>ok</b>, first call",
     "<span class='chip neg'>three patterns in four runs</span> — no cause, no UA theory (F-5)"),
    ("transport calls for the bi5", "1", "16", "1 then 4", "1", "intermittency is real and varies wildly"),
    ("okx bid / ask", "60960.3 / 60960.4", "61063.2 / 61063.3", "60974.6 / 60974.7",
     "60925.8 / 60925.9", "prices move, as they should"),
    ("okx book best bid / ask", "60960.3 / 60960.4", "61063.2 / 61063.3", "<b>60965.8 / 60965.9</b>",
     "60925.8 / 60925.9", "gap from its own ticker: 0.0 · 0.0 · <b>8.8 USD = 1.4 bps</b> · 0.0 (F-8)"),
    ("okx trade sides", "['BUY','SELL']", "['BUY','SELL']", "['BUY','SELL']", "<b>['BUY']</b>",
     "all four passed — two-sidedness is <b>not asserted</b> for trades (F-9)"),
    ("okx book / entitlement", "depth 40 · LIVE · 0.016 bps", "depth 40 · LIVE · 0.016 bps",
     "depth 40 · LIVE · 0.016 bps", "depth 40 · LIVE · 0.016 bps", "identical"),
    ("binance vision dump", "71,720 B · 1440 rows · 0 rejected · us", "71,720 B · 1440 rows · 0 rejected · us",
     "71,720 B · 1440 rows · 0 rejected · us", "71,720 B · 1440 rows · 0 rejected · us",
     "identical — a fixed historical day, so it must be"),
    ("bybit", "5 GEO-BLOCKED", "5 GEO-BLOCKED", "5 GEO-BLOCKED", "5 GEO-BLOCKED",
     "<span class='chip neg'>unchanged, and unchangeable from a hosted runner</span> (F-2)"),
])}
</table>"""


def limits_table() -> str:
    return f"""<table>
<tr><th>limitation</th><th>why it matters</th></tr>
{rows([
    ("This batch changed <b>no production code</b>.",
     "The authorisation the owner gave for Stage 6.2 was scoped to that batch, so every finding here "
     "that needs a code change is stated as a request, not delivered. The only files touched are "
     "docs and design artifacts."),
    ("The live numbers come from <b>GitHub's runner, not this sandbox</b>.",
     "Nothing here was fetched from a venue by me: this environment has egress only to github.com, "
     "npm, and PyPI. Every market figure is quoted from a check annotation, with its run and job id."),
    ("The report is <b>truncated at GitHub's annotation cap</b> and the artifact is undownloadable.",
     "807 characters of the HEAD report are past the cut, including all five GEO-BLOCKED rows. The "
     "claim 'the 5 geo-blocked checks are the 5 bybit checks' is an <b>inference</b> from the local "
     "collection (TestBybitLiveEndpoints has exactly 5) plus the headline count — not a quoted row."),
    ("Two runs 20 minutes apart gave <b>different dukascopy diagnoses</b> (F-5).",
     "So the 503 is not 'characterised'. What reproduced in both is the layout pass, which is the "
     "evidence O-010 actually demands; the cause of the throttling remains unknown and is not "
     "claimed here."),
    ("okx numbers are a <b>snapshot at 04:41Z</b>.",
     "bid 61063.2 will be wrong by the time this is read. The durable claims are structural: "
     "uncrossed book, both trade sides, contiguous candles, entitlement LIVE."),
    ("Verification proves data <b>parsed inside asserted bands</b>, not that it is correct.",
     "A venue serving plausible-but-wrong prices would pass these checks. Reconciliation against a "
     "second source is what would catch that, and it is not built."),
    ("Dukascopy was verified for <b>one pair, one hour</b>.",
     "13 pairs carry divisors; 12 are unverified. A wrong divisor is a silent 100x error — the exact "
     "risk O-010 names — so 'FX covered' would overstate it badly."),
    ("No instrument is <span class='mono'>active</span>, and none can be traded.",
     "<span class='mono'>register()</span> forces <span class='mono'>active=False</span> (activation "
     "is a separate decision, D-002), trade authority needs TRADE_ENABLED, and the environment is "
     "DISABLED with <span class='mono'>NEXUS_LIVE_TRADING_ENABLED=false</span>."),
])}
</table>"""


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI · Stage 7.1 Market &amp; Venue Coverage</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 7 of 23 &middot; sub-deliverable 7.1 (research)</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
Market &amp; venue coverage &mdash; what is actually verified, per venue and per asset class</h1>
<div class="ribbon">RESEARCH BATCH — no production code is changed. Stage 7's mandate is recorded in
<code>docs/12</code> §1.4: <i>&ldquo;Stage 7 retires the unverified rows market by market with
evidence per market.&rdquo;</i> This board establishes, with measurements rather than restatements,
what those rows now say. Three of the nine findings below could only be found by <b>running</b>
things: booting the API, climbing the certification ladder, and handing the domain a venue its own
enum does not contain.</div>

<h3>0 · The two rows this stage exists to retire<span class="tag">docs/12 §1.4</span></h3>
<div class="card">{mandate_table()}</div>
<p class="cap">One of the two is now a paperwork problem: the evidence its own code demands exists,
twice, at HEAD. The other cannot be solved by editing anything at all.</p>

<h3>1 · Where every number on this board came from<span class="tag">and what could not be read</span></h3>
<div class="card">{evidence_base()}</div>

<h3>2 · &ldquo;24 passed of 29&rdquo; is not 24 items of coverage evidence<span class="tag">measured locally with --collect-only</span></h3>
<div class="card">{decomposition_table()}</div>
<div class="blocked">Honesty correction: the headline the workflow publishes reads
<b>24 passed / 0 failed / 5 geo-blocked / 0 skipped of 29</b>. Thirteen of those passes are tests of
our own retry and diagnosis logic against fabricated inputs — they would still pass if every venue
on earth disappeared. <b>Eleven checks are live evidence about a source</b>: 5 okx, 2 binance
vision, 3 dukascopy, 1 dukascopy reachability. Any coverage claim built on &ldquo;24 passed&rdquo;
would overstate what is proven by more than half.</div>

<h3>3 · The verified numbers, per source<span class="tag">quoted from run 45756716181 · b67ab39 · 04:41Z; reproduced by runs 45754638978, 45758610197 and 45759709313</span></h3>
<p><b>OKX</b> — five public endpoints, real responses, normalised. <span class="chip pos">5 / 5 PASS</span></p>
{okx_card()}
<p class="cap">Contract size 0.01 and tick size 0.1 are the numbers sizing math needs; the book is
uncrossed at 0.016 bps with entitlement <span class="mono">LIVE</span>, trades carry both sides, and
100 one-minute candles span 1.65 h. Verified in every run since 2026-11-25.</p>
<p><b>Binance Vision</b> — a genuine daily dump, downloaded and parsed end to end.
<span class="chip pos">2 / 2 PASS</span></p>
{bv_card()}
<p class="cap">1,440 rows in, 1,440 accepted, 0 rejected, spanning 23.98 h of a 24 h day. The
<span class="mono">timestamp_units=us</span> field is defect 40's fix observed on real data: spot
dumps publish microseconds, and had that stayed assumed-milliseconds every bar would have been dated
tens of thousands of years out.</p>
<p><b>Dukascopy</b> — the bi5 layout check the flag has been waiting for.
<span class="chip pos">4 / 4 PASS</span></p>
{duk_card()}
<p><b>Bybit</b> — <span class="chip neg">5 / 5 GEO-BLOCKED</span> at the edge, on public
unauthenticated endpoints, from a GitHub-hosted runner. Nothing about the adapter is implicated and
nothing about it is proven. Per D-007 venues are certified independently, so okx's five passes say
nothing here.</p>
<p><b>The four runs side by side</b> — what repeated exactly, and what did not:</p>
<div class="card">{four_runs_table()}</div>
<p class="cap">The dukascopy layout result is byte-identical across all four, including two runs on
commits that changed no code. The reachability probes gave three different patterns in four attempts,
and run 4 reverted to run 1's — which is what settles F-5 against any user-agent theory. Two further
differences only visible across runs: okx's ticker and book agreed exactly in run 4 and were 1.4 bps
apart in run 3 (F-8), and run 4's 50 trades were <b>all buys</b> and still passed (F-9).</p>

<h3>4 · Findings<span class="tag">F-n: research findings, not register decisions (those are D-0nn)</span></h3>

<div class="finding"><div class="fid">F-1 · EVIDENCED, NOT RETIRED</div>
<div class="ft">Dukascopy's layout check has passed against a real file four times running, and the
code still says no real file has ever been downloaded</div>
<p><span class="mono">verify_layout</span>'s own docstring states the bargain:
<i>&ldquo;Passing these is the evidence required to flip <span class="mono">LAYOUT_VERIFIED</span> to
<span class="mono">True</span>&rdquo;</i> <span class="cite">(dukascopy.py:219–225)</span>. It has now
returned <span class="mono">passed=True · payload_bytes=25761 · decompressed_bytes=101480 ·
tick_count=5074 · reasons=-</span> in <b>four consecutive runs</b> — <span class="mono">a77865e</span>,
<span class="mono">b67ab39</span>, <span class="mono">fa74748</span> and <span class="mono">25e314e</span>
— the last two of which changed no code at all, so the result depends on nothing in this batch. 101,480 is 5,074 ×
20 bytes exactly, offsets inside the hour, and the parsed prices 1.09502–1.0964 sit in EURUSD's real
band — which is the check that would catch a wrong point divisor, the silent 100× error O-010 names.</p>
<p>Against that, four statements and one constant are stale:
<span class="cite">dukascopy.py:45</span> <span class="mono">LAYOUT_VERIFIED = False</span>;
<span class="cite">dukascopy.py:113</span> still selects
<span class="mono">DUKASCOPY_BI5_UNVERIFIED</span>, visible in the same annotation line as the pass;
<span class="cite">dukascopy.py:9</span> and <span class="cite">test_live_endpoints.py:10</span> both
say no real file has ever been downloaded — contradicted by
<span class="cite">test_live_endpoints.py:165</span>, 40 lines later in the same file, which records
25,761 bytes; <span class="cite">test_live_endpoints.py:674</span> and
<span class="cite">docs/06:247, :297</span> still say <span class="mono">verify_layout</span> has
never run against a real file.</p>
<p><b>Consequence:</b> every FX tick the system ingests is tagged unverified, forever, unless a human
notices that CI has already produced the evidence. The retention policy (D-024) would file ticks it
believes are provisional. <b>Closes with:</b> lever L-A. <b>Needs:</b> the owner's authorisation for
<span class="mono">backend/</span>.</p></div>

<div class="finding"><div class="fid">F-2 · BLOCKED ON A HOST, NOT ON CODE</div>
<div class="ft">Bybit cannot be retired from any runner GitHub provides, and the lever to retire it
was built in Phase 4 and has never been used</div>
<p>All five bybit checks are classified <span class="mono">GEO-BLOCKED</span>: 403 from the CloudFront
edge on public, unauthenticated endpoints. That is where the check runs, not what it checks — and the
workflow already anticipated it, taking a <span class="mono">runner</span> input on dispatch whose own
description reads <i>&ldquo;use a self-hosted label once the deployment VM exists, because Bybit
geo-blocks hosted runners and cannot be verified from them&rdquo;</i>
<span class="cite">(venue-verification.yml:30–37, :73–76)</span>.</p>
<p>The tension is already on record and it resolves in our favour: D-024 chose bybit <b>for
Nigeria</b>, where it is not geo-blocked, while CI runs where it is; D-021's deployment host is an
Oracle Always Free ARM64 VM. So the retirement path costs $0 and needs no code change — a self-hosted
runner label on the host the system will run on anyway. <b>Consequence until then:</b> bybit's honest
rank is <span class="mono">SUPPORTED</span> (an adapter exists) and it must never be shown as
tradable or as data-available. <b>Closes with:</b> lever L-D. <b>Blocked on:</b> the VM existing; it
cannot be done from this sandbox, which has no egress to bybit.</p></div>

<div class="finding"><div class="fid">F-3 · THE BIGGEST ONE, AND IT WAS INVISIBLE</div>
<div class="ft">The instrument master is empty in the running system, nothing ever populates it, and
so the archive gate can never open</div>
<p><span class="cite">api/app.py:135</span> builds <span class="mono">InstrumentRegistry()</span> —
empty. <span class="mono">InstrumentRegistry.register</span>
<span class="cite">(registry.py:257)</span> and <span class="mono">.certify</span>
<span class="cite">(:354)</span> have <b>zero callers in production code</b>: every call site is a
test. The API exposes instruments <b>GET-only</b> — there is no registration endpoint — so nothing
outside the process can populate it either. A real boot, measured in-process just now, returns:</p>
<div class="ev"><span class="k">GET /v1/instruments/coverage</span>  200
  total=0 active=0 by_asset_class={{}} by_venue_status={{}} missing_contract_size=[]
  missing_tick_size=[] ready_for_research=[] ready_for_paper=[] ready_for_live=[]
  live_trading_enabled=false
  note="readiness_for_live describes certification only; live authority is DENIED"
<span class="k">GET /v1/data/coverage</span>       200
  configured=false files=0 bytes=0 partitions={{}}
  note="no archive configured; nothing has been persisted"</div>
<p><b>Consequence, and it is functional rather than cosmetic:</b>
<span class="cite">pipeline.py:50</span> sets
<span class="mono">MINIMUM_STATUS_FOR_ARCHIVE = VenueStatus.DATA_AVAILABLE</span>. With an empty
master, no venue mapping can ever hold that status, so <b>no source's data can be archived</b> —
including the three whose data CI verified this morning. The four adapters can fetch, normalise and
prove; the archive gate then refuses, correctly, because nothing has been certified. Stage 3.5's
System Health screen was designed to show &ldquo;registry-measured coverage state&rdquo;: today it
would render all zeros, and that rendering would be <i>honest</i>.</p>
<p><b>Closes with:</b> lever L-C (seed from evidence, each rank citing the run that justifies it),
which depends on L-E for the rung problem below. <b>Needs:</b> the owner's authorisation for
<span class="mono">backend/</span>.</p></div>

<div class="finding"><div class="fid">F-4 · FAIL-OPEN, THEN A CRASH</div>
<div class="ft">The only free FX source is not a member of the venue enum, the domain accepts it
anyway, and registration then dies with an unclassified AttributeError</div>
<p><span class="mono">Venue</span> <span class="cite">(domain/instrument.py:36–47)</span> has nine
members — BYBIT, BINANCE, OKX, MT4, MT5, CTRADER, IBKR, OANDA, ALPACA. <b>DUKASCOPY is not among
them</b>, although <span class="cite">ingestion/dukascopy.py:40</span> sets
<span class="mono">VENUE = "DUKASCOPY"</span> and it is the only FX source the project has. Executed,
not inferred:</p>
<div class="ev"><span class="k">Venue('DUKASCOPY')</span>  -> ValueError: 'DUKASCOPY' is not a valid Venue
<span class="k">VenueMapping(venue='DUKASCOPY', venue_symbol='EURUSD')</span>  -> constructed, no complaint
   (a dataclass does not enforce its annotations, so `venue: Venue` is documentation only)
<span class="k">registry.register(that instrument)</span>  -> CRASH
   AttributeError: 'str' object has no attribute 'value'
   at instruments/registry.py:282 -> if self._by_venue_symbol.get((m.venue.value, m.venue_symbol)) ...</div>
<p>So an out-of-scope venue is accepted at construction and then raises an <b>unhandled
<span class="mono">AttributeError</span> inside <span class="mono">register()</span></b> — not a
<span class="mono">CertificationRejected</span>, not any
<span class="mono">NexusError</span> reason code. Through the API that is a 500, in a codebase whose
posture everywhere else is a classified refusal. <span class="mono">RegistryChange.venue</span> is
typed <span class="mono">str | None</span> <span class="cite">(registry.py:91)</span>, so the audit
record could not distinguish an in-scope venue from an arbitrary string either.</p>
<p><b>Related, and it explains how this stayed hidden:</b> every FX test in the suite models EUR/USD
at <span class="mono">Venue.MT5</span> <span class="cite">(test_instrument_registry.py:403,
test_api_phase3.py:194, :225)</span> — a venue with no adapter, no source, and a credential
requirement. The FX coverage tests therefore pass while describing a venue the system cannot reach,
and the one venue it <i>can</i> reach cannot be expressed. <b>Closes with:</b> lever L-B.</p></div>

<div class="finding"><div class="fid">F-5 · DO NOT OVERCLAIM THE 503</div>
<div class="ft">Two runs twenty minutes apart produced different dukascopy diagnoses, so the 503 is
still unexplained — only the layout result reproduced</div>
<p>Four runs probed the same two hours and produced <b>three different patterns</b>:</p>
<div class="ev"><span class="k">run 45754638978 (04:21Z, a77865e)</span>
  production_ua=ok bytes=25761 lzma=True
  verdict="nothing to diagnose: the production User-Agent works"
<span class="k">run 45756716181 (04:41Z, b67ab39)</span>
  production_ua=network-IngestFault   browser_ua=network-IngestFault
  production_ua_other_hour=ok bytes=25313 lzma=True   (10h_ticks.bi5)
  verdict="the host was never reached (network-IngestFault), so no cause can be distinguished"
<span class="k">run 45758610197 (04:59Z, fa74748)</span>
  production_ua=network-IngestFault   browser_ua=ok bytes=25761 lzma=True
  production_ua_other_hour=network-IngestFault
  verdict="the host was never reached (network-IngestFault), so no cause can be distinguished"
<span class="k">run 45759709313 (05:10Z, 25e314e = HEAD)</span>
  production_ua=ok bytes=25761 lzma=True          &lt;- back to run 1's pattern
  verdict="nothing to diagnose: the production User-Agent works"</div>
<p>Run 3 pointed the opposite way from run 1 — the <b>browser</b> user agent succeeded where the
production one failed — and then run 4 reverted to run 1's pattern, with the production user agent
succeeding on the first call. So the sequence reads: production works, nothing works, browser works,
production works. Any theory drawn from one run is refuted by another, and the only reading that
survives all four is the one the diagnostic itself returned twice: <b>no cause can be
distinguished</b>. Adopting a browser user agent in the adapters on the strength of run 3 would have
been circumvention of a host's stated preference justified by a single noisy sample — and run 4 would
have falsified that justification eleven minutes later. The module already refuses to make the choice
for itself and leaves it to the owner; seven offline logic tests pin that refusal.</p>
<p>So the ledger's claim that the 503 was &ldquo;characterised&rdquo; is only partly supported:
throttling is <i>consistent</i> with the evidence (16 transport calls to land one 25,761-byte file in
run 2, 4 in run 3, 1 in runs 1 and 4; the patience helper exists because this feed answers
intermittently), while no cause has been <i>established</i> and no user-agent conclusion survives four
samples. <b>What reproduced in all four runs is the layout pass — the evidence O-010 actually
demands.</b>
<b>Closes with:</b> nothing here; the honest state is &ldquo;intermittent, cause unknown&rdquo;, and
it stays that way until runs accumulate or the deployment host offers a stable vantage point. Four
runs in 49 minutes is a start, not a characterisation.</p>
</div>

<div class="finding"><div class="fid">F-8 · EACH ENDPOINT IS CHECKED ALONE</div>
<div class="ft">Nothing asserts that two endpoints from the same venue agree with each other, and run
3 shows the gap is measurable</div>
<p>In run <span class="mono">45758610197</span>, okx's ticker check recorded
<span class="mono">bid=60974.6 ask=60974.7</span> and the order-book check, sampled seconds later in
the same run, recorded <span class="mono">best_bid=60965.8 best_ask=60965.9</span> — a difference of
<b>8.8 USD, about 1.4 bps</b>. Both are internally sound (each uncrossed at 0.016 bps) and both
passed. In a moving market that spread is entirely plausible; the point is that <b>the suite could not
distinguish it from a venue serving inconsistent data across endpoints</b>, because every check
validates one endpoint in isolation: uncrossed book, both trade sides, contiguous candles, prices
inside the quoted band.</p>
<p>Run 4 is the counter-example that shows why such an assertion would need a tolerance rather than
an equality: there the ticker read <span class="mono">bid=60925.8 ask=60925.9</span> and the book
<span class="mono">best_bid=60925.8 best_ask=60925.9</span> — <b>identical</b>. So the gap between two
endpoints sampled seconds apart ranges from 0.0 to 1.4 bps across the four runs, depending only on when
each call landed.</p>
<p><b>Consequence:</b> a cross-endpoint consistency assertion — ticker best bid/ask against the top of
the book, sampled together, with a tolerance stated in bps and a timestamp gap recorded — would be the
check that catches a venue whose feeds disagree. It is cheap, offline-testable against fixtures, and
belongs with the verification module rather than the adapters. <b>Closes with:</b> an optional addition
to L-A's batch; it is not required to retire either honesty row, and this board does not claim it
is.</p></div>

<div class="finding"><div class="fid">F-6 · 3 OF 14</div>
<div class="ft">Fourteen asset classes are declared; three have a free source, one more is plausible,
and ten have nothing at all</div>
<p><span class="mono">AssetClass</span> <span class="cite">(domain/instrument.py:19–33)</span> declares
14 classes. Implemented free sources cover <span class="mono">CRYPTO_PERP</span>,
<span class="mono">CRYPTO_SPOT</span> and <span class="mono">FX_SPOT</span>.
<span class="mono">METALS</span> is plausible at $0 and unproven: XAUUSD (divisor 100) and XAGUSD
(1000) are already in the same dukascopy <span class="mono">POINT_DIVISORS</span> table
<span class="cite">(:54–67)</span>, so the same bi5 path could serve them — but neither has ever been
downloaded, and a divisor is a claim, not evidence. The remaining <b>ten</b> classes have no source
of any kind, and the six venues that would serve them are enum members with no adapter, all
credentialed and mostly paid — outside D-019's $0/month constraint.</p>
<p><b>Consequence:</b> those ten must render <span class="mono">UNSUPPORTED</span>, greyed with their
registry state, and never be offered as tradable — the capability-honesty law from Stage 3.1. That is
a design obligation Stage 7 can state now and Stage 8+ must honour; it is not a gap to be filled by
invention. <b>Closes with:</b> the matrix above being published as the coverage contract, plus (if the
owner wants it) a METALS probe in Stage 7.2 — one download, $0.</p></div>

<div class="finding"><div class="fid">F-7 · THE LADDER HAS A RUNG FREE SOURCES CANNOT OCCUPY</div>
<div class="ft"><span class="mono">CONNECTED</span> means &ldquo;auth verified&rdquo;; the four sources
we have use no auth — and nothing refuses a certification whose evidence says so</div>
<p>The ladder <span class="cite">(registry.py:12–13)</span> is
<span class="mono">UNKNOWN → SUPPORTED → CONNECTED → DATA_AVAILABLE → TRADE_ENABLED →
LIVE_VERIFIED</span> and <span class="mono">is_certification_advance</span>
<span class="cite">(:62)</span> requires exactly one rung, so <span class="mono">certify</span>
<span class="cite">(:392)</span> refuses to skip. <span class="mono">CONNECTED</span> is documented as
<span class="mono"># auth verified</span> <span class="cite">(domain/instrument.py:55)</span>. All four
sources are credential-free by construction (<span class="mono">requires_credentials = False</span> in
each adapter). Executed against the real registry:</p>
<div class="ev"><span class="k">1.</span> register an OKX BTC-USDT-SWAP mapping
   -> id INS-BTC-USDT-USDT | mapping status UNKNOWN | active False
<span class="k">2.</span> certify straight to DATA_AVAILABLE, evidence = the run id
   -> REFUSED: cannot move UNKNOWN -> DATA_AVAILABLE; the ladder advances one step at a time
<span class="k">3.</span> climb it one rung at a time, each with the evidence it actually has
   -> SUPPORTED       evidence 'adapter exists: src/nexus/ingestion/okx.py'
   -> CONNECTED       evidence 'public UNAUTHENTICATED endpoints answered; no credential exists,
                       none was used, so no auth was verified'      <- accepted, without complaint
   -> DATA_AVAILABLE  evidence 'run 45756716181: instruments/quotes/trades/candles/book all
                       normalised from real responses'
<span class="k">4.</span> coverage_report
   -> total=1 active=0 by_venue_status={{'DATA_AVAILABLE': 1}} ready_for_research=('INS-BTC-USDT-USDT',)
      ready_for_paper=() ready_for_live=() | archive gate DATA_AVAILABLE satisfied: True</div>
<p>Three things follow. <b>(a)</b> A freshly registered mapping starts at
<span class="mono">UNKNOWN</span>, not <span class="mono">SUPPORTED</span>, so recording what CI
proved takes <b>four</b> rungs, each needing its own evidence label. <b>(b)</b> The
<span class="mono">CONNECTED</span> rung accepted evidence that <b>contradicts its own
definition</b> — <span class="mono">certify</span> requires a non-empty string
<span class="cite">(:371)</span> and cannot judge its content, so the ladder's honesty rests entirely
on whoever writes the label. <b>(c)</b> Once climbed, the archive gate opens — which is the proof that
F-3, not the adapters, is what stands between verified data and an archive.</p>
<p><b>Also worth correcting:</b> <span class="cite">docs/12 §1.4</span> describes okx as
&ldquo;connected + live-verified&rdquo;. In this codebase <span class="mono">LIVE_VERIFIED</span>
means <i>&ldquo;live pilot verified + reconciliation proven&rdquo;</i>
<span class="cite">(domain/instrument.py:58)</span>, which needs credentials and orders. What okx has
is <span class="mono">DATA_AVAILABLE</span>. The word &ldquo;live-verified&rdquo; in that sentence
means &ldquo;verified against live data&rdquo; — the same phrase, two different meanings, in the
document that Stage 7 is told to work from. <b>Closes with:</b> lever L-E, an owner ruling.</p></div>

<div class="finding"><div class="fid">F-9 · A CLAIMED INVARIANT THAT IS NOT ONE</div>
<div class="ft">&ldquo;50 trades with both sides present&rdquo; was a property of one sample, not an
assertion — and run 4 returned 50 buys and passed</div>
<p><span class="cite">docs/06:234</span> records okx's first live verification as <i>&ldquo;50 trades
with both sides present and prices inside the quoted band&rdquo;</i>, and the same phrase appears in
<span class="cite">docs/00</span>'s first-contact row. Reading the check itself:
<span class="mono">_assert_ticks</span> asserts that trades came back, that each
<span class="mono">observed_at</span> is timezone-aware, that each <span class="mono">source</span>
matches, that prices and quantities are positive, and that each <span class="mono">side</span> is
inside the vocabulary <span class="mono">(None, "BUY", "SELL")</span> — it never asserts that
<b>both</b> sides appear. <span class="mono">sides=[…]</span> is recorded as evidence only.</p>
<p>Run 4 makes the difference visible: <span class="mono">okx.trades count=50 price_min=60920.7
price_max=60925.9 sides=['BUY']</span> — all fifty buys — and the check <b>passed</b>, correctly,
because a 50-trade window in a quiet minute can legitimately be one-sided. Note the asymmetry with the
very next helper: <span class="mono">_assert_book</span> <i>does</i> fail a one-sided book
(<span class="mono">assert book.bids and book.asks, "one-sided book"</span>). So two-sidedness is
treated as an invariant for the book and as an observation for trades.</p>
<p><b>Consequence:</b> no defect in the code — the assertion set is defensible — but the
<b>documentation overstates what is verified</b>, which is precisely the class of error this stage
exists to correct. Either the claim is worded as an observation (&ldquo;both sides were present in that
sample&rdquo;), or, if the project wants it as an invariant, it needs a larger sample and a stated
tolerance. <b>Closes with:</b> a wording correction in <span class="mono">docs/06</span> and
<span class="mono">docs/00</span> — docs only, no authorisation needed — plus an owner decision on
whether one-sidedness in trades should ever be a failure.</p></div>

<h3>5 · Coverage matrix<span class="tag">per venue, and per asset class</span></h3>
<div class="card">{venue_matrix()}</div>
<div class="card" style="margin-top:12px">{asset_matrix()}</div>

<h3>6 · What retiring the two rows actually requires<span class="tag">five levers, all $0</span></h3>
<div class="card">{retirement_table()}</div>
<p class="cap">Order matters: L-E decides the vocabulary, L-B makes FX representable, L-A retires the
dukascopy row, L-C makes coverage real, and L-D waits on a machine. None of them costs anything; four
of the five need an authorisation this batch does not have.</p>

<h3>7 · Reproducibility<span class="tag">every command behind a claim above</span></h3>
<div class="ev"><span class="k"># the live evidence at HEAD (annotation, since logs and artifacts are unreachable)</span>
gh api repos/:owner/:repo/actions/runs/45756716181/jobs --jq '.jobs[0].id'   -> 139696937355
gh api repos/:owner/:repo/check-runs/139696937355/annotations --jq '.[].message'
gh api repos/:owner/:repo/actions/runs/45756716181 --jq '.head_sha'          -> b67ab39… (= HEAD)
<span class="k"># the run at HEAD, and the ones before it</span>
gh api repos/:owner/:repo/actions/runs/45759709313/jobs --jq '.jobs[0].id'   -> 139706589069
gh api repos/:owner/:repo/check-runs/139706589069/annotations --jq '.[].message'
gh api repos/:owner/:repo/actions/runs/45758610197/jobs --jq '.jobs[0].id'   -> 139703054396
gh api repos/:owner/:repo/check-runs/139703054396/annotations --jq '.[].message'
gh api repos/:owner/:repo/check-runs/139690278846/annotations --jq '.[].message'
<span class="k"># CI on both commits of this batch</span>
gh api repos/:owner/:repo/actions/runs/45759700949/jobs --jq '.jobs[].conclusion'  -> 5x success
gh api repos/:owner/:repo/actions/runs/45758603745/jobs --jq '.jobs[].conclusion'  -> 5x success'
<span class="k"># what the 29 checks actually are</span>
NEXUS_LIVE_VERIFY=1 pytest tests/test_live_endpoints.py --collect-only -v    -> 29, by class
<span class="k"># what a real boot reports for coverage</span>
NEXUS_AUDIT_BACKEND=memory NEXUS_ENVIRONMENT=DISABLED python -c "create_app() + TestClient
  -> GET /v1/instruments/coverage ; GET /v1/data/coverage"                   -> both quoted in F-3
<span class="k"># the ladder and the venue enum, executed</span>
python -c "Venue('DUKASCOPY'); VenueMapping(venue='DUKASCOPY', …); register(); certify() ×3;
  coverage_report()"                                                         -> quoted in F-4, F-7
<span class="k"># who calls register/certify in production</span>
grep -rnE "registry\\.(register|certify)\\(" src/nexus --include=*.py       -> no matches
grep -nE "@app\\.(get|post|put|delete)" src/nexus/api/app.py              -> instruments are GET-only</div>

<h3>8 · Limitations of this batch<span class="tag">stated before the ask, not after</span></h3>
<div class="card">{limits_table()}</div>

<h3>9 · Decision requested<span class="tag">Stage 7.1 is research; nothing below is done yet</span></h3>
<div class="ask">
<p>Stage 7 cannot retire either honesty row without touching <span class="mono">backend/</span>, and
the authorisation for that was scoped to Stage 6.2. Four questions, in the order they depend on each
other:</p>
<ol>
<li><b>Authorise the code changes for Stage 7.2?</b> The smallest useful batch is L-A + L-B + L-E:
flip <span class="mono">LAYOUT_VERIFIED</span> on the evidence CI already produced, make
<span class="mono">DUKASCOPY</span> a venue and refuse out-of-scope venues with a classified error,
and settle what <span class="mono">CONNECTED</span> means for a credential-free source. All $0, all
testable offline, no new dependency.</li>
<li><b>The <span class="mono">CONNECTED</span> ruling (L-E).</b> Either (a) redefine it as
&ldquo;the endpoint answered and normalised; auth not applicable for public data&rdquo;, or (b) insert
a rung for credential-free sources. Option (a) is one comment and no enum change; option (b) is more
honest but touches every rank comparison and the audit vocabulary. My recommendation is (a) with the
evidence label required to state <i>why</i> auth is not applicable — the registry cannot judge the
label, so the label must carry the reason.</li>
<li><b>Seed the master (L-C) in Stage 7.2 or later?</b> This is what makes coverage non-zero and the
archive gate reachable (F-3), but it also decides what the whole UI shows, and it should be seeded
<i>only</i> with instruments whose evidence exists — okx BTC-USDT-SWAP, binance vision spot dumps,
dukascopy EURUSD — each citing its run id. It is a larger batch than L-A/L-B/L-E and could be its own
7.3.</li>
<li><b>Bybit (L-D) stays open and recorded as blocked.</b> It needs the D-021 VM as a self-hosted
runner; no code change and no money, but nothing can be done from this sandbox. Confirm that the row
stays <span class="mono">GEO-BLOCKED / SUPPORTED</span> until the VM exists, rather than being
dropped from sight.</li>
</ol>
<p class="cap">Also corrected in this commit, because a record that disagrees with itself cannot be
used: the Stage 3 narrative header in <span class="mono">docs/07</span> (stale since D-037, and
carrying a spliced fragment of the Stage 2 paragraph), the status headers of
<span class="mono">docs/12</span> and <span class="mono">docs/13</span> (both still
&ldquo;IN PROGRESS&rdquo; after approval), every &ldquo;awaiting review&rdquo; line in
<span class="mono">design/index.html</span>, and the footer of the approved Stage 6.2 board, which
still said gate 975/2/0 after the verified number became 976/2/0.</p>
</div>

<footer>Stage 7.1 &middot; research &middot; no production code changed &middot; evidence: four live
runs — 45759709313 (25e314e, HEAD), 45758610197 (fa74748), 45756716181 (b67ab39), 45754638978
(a77865e) &middot; CI runs 45759700949 and 45758603745, all five jobs green each &middot; a real
in-process boot &middot; executed probes of the registry and domain types</footer>
</div></body></html>"""
    out = HERE / "stage7-1-market-venue-coverage.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    p = main()
    print(f"wrote {p} ({p.stat().st_size/1024:.0f} KB)")
