"""Stage 8.4 board: four adapters get a receipt time, and the run that proved it failed first.

F-14's expensive half, authorised by D-052's ruling 2 as a batch of its own with its own gate and its own
live runs before and after. Nothing else is in scope, and §1 shows the three things ruled out as absent
rather than merely unmentioned.

Every transcript here was captured from `backend/.venv/bin/python` runs, from `pytest` runs, or from CI
check-run annotations read through `gh api` while this board was being written, and pasted verbatim —
including the two tamper experiments that prove the gate and the hygiene scan are load-bearing, and
including the run that failed. Captures: `/tmp/cap84.py` (BLOCKS A–G), `/tmp/tamper84.py` (the faithful
adapter tamper), `/tmp/tamper_adapters.txt`, `/tmp/tamper_hygiene.txt`, `/tmp/live_before.txt`,
`/tmp/live_after.txt`, `/tmp/live_after_pr.txt`, `/tmp/live_after_pushrun.txt`.

Two numbers this board carries are corrections to figures already published in commit messages, and both
corrections are disclosed in the section that carries them rather than applied quietly (§9, §10).

Run:  backend/.venv/bin/python design/build_board84.py
"""

from __future__ import annotations

import html
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
/* `.card` wraps every table here and is undefined in the shared shell (CSS71) — the same gap the 8.2 and
   8.3 boards recorded. Definition copied verbatim from `build_specimen.py`, the approved visual language,
   rather than invented, and added to THIS board's extension only. */
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


def verbatim(title: str, body: str, kind: str = "") -> str:
    """A captured transcript. `kind` is `before` or `after` when the block is one side of a comparison."""
    cls = f"ba {kind}".strip()
    return f'<div class="{cls}"><div class="hd">{title}</div><pre>{html.escape(body.strip())}</pre></div>'
# Captured verbatim by `/tmp/cap84.py` against backend/.venv/bin/python while this board was
# written. Pasted, not retyped: a transcript that is transcribed is a transcript that can be improved.

BLOCK_A = """\
BEFORE (the shape every adapter produced; both fields hold the venue's value):
  TickRecord(observed_at=2025-11-25T12:00:00+00:00,
             venue_timestamp=2025-11-25T12:00:00+00:00)
  -> observed_at - venue_timestamp = 0:00:00   (identically zero, everywhere)

AFTER (one fetch through a transport whose receipt clock is pinned to RECEIPT):
  observed_at     = 2026-11-27T06:43:35.000Z   <- ours, stamped at the wire
  venue_timestamp = 2025-11-25T12:00:00.000Z   <- OKX's own `ts`
  difference      = 31689815.0 s  (a year, because the fixture says so)
  transport.received_at log = ['2026-11-27T06:43:35.000Z']
"""

BLOCK_B = """\
Fetched is frozen and carries four fields:
  Fetched(payload={'a': 1}, received_at=datetime.datetime(2026, 11, 27, 6, 43, 35, tzinfo=datetime.timezone.utc), url='https://example/x', attempts=2)

HttpTransport._request, verbatim from src/nexus/data/records.py:
                        raise IngestFault(f"{url} returned HTTP {status}", retryable=False)
                    # Stamped before the body is decoded, so the receipt time is the moment the
                    # response was in hand and not the moment we finished reading it.
                    received_at = utc_now()
                    payload = response.content if want_bytes else response.json()

The Transport protocol, verbatim (the five methods, two of them receipt-less):
    class Transport(Protocol):
        async def fetch_json(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched: ...
        async def fetch_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched: ...
        async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...
        async def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes: ...
        async def aclose(self) -> None: ...
    class HttpTransport:

No adapter calls the receipt-less pair any more:
   $ grep -rn 'get_json\\|get_bytes' src/nexus/ingestion/
   (no output)
"""

BLOCK_C = """\
  rows parsed                = 4
  distinct observed_at       = 1   -> ['2026-11-27T06:43:35.000Z']
  venue_timestamp span       = 2025-11-25T12:00:00.000Z .. 2025-11-25T12:03:00.000Z
  transport calls            = 1
  DumpParseResult.first_time = 2025-11-25T12:00:00.000Z
  DumpParseResult.last_time  = 2025-11-25T12:03:00.000Z

  min/max of observed_at would publish ONE instant twice and call it a range:
    min(observed_at) = 2026-11-27T06:43:35.000Z
    max(observed_at) = 2026-11-27T06:43:35.000Z
"""

BLOCK_D = """\
  event partition   archive/dataset=ticks/venue=BYBIT/symbol=BTCUSDT/interval=tick/year=2025/month=11
     exists = True
  receipt partition archive/dataset=ticks/venue=BYBIT/symbol=BTCUSDT/interval=tick/year=2026/month=11
     exists = False

  what is on disk:
    dataset=ticks/venue=BYBIT/symbol=BTCUSDT/interval=tick/year=2025/month=11/ticks-20261127T064335Z-0000003.parquet

  and the receipt time is still stored, just not as the key:
     venue_timestamp=2025-11-25 12:00:00+00:00  observed_at=2026-11-27 06:43:35+00:00
     venue_timestamp=2025-11-25 12:01:00+00:00  observed_at=2026-11-27 06:43:35+00:00
     venue_timestamp=2025-11-25 12:02:00+00:00  observed_at=2026-11-27 06:43:35+00:00
"""

BLOCK_E = """\
  venue clock BEHIND ours by 28 s: received 30 s ago, venue stamped 2 s ago
     status=STALE       new_risk_allowed=False age_seconds=30.0 venue_age_seconds=2.0 receipt_minus_venue_s=-28.0
  venue clock AHEAD of the data: received 1 s ago, venue stamped 10 s ago
     status=LIVE        new_risk_allowed=True  age_seconds=1.0 venue_age_seconds=10.0 receipt_minus_venue_s=9.0
  venue stamp in the FUTURE: received 1 s ago, venue stamped 3 s ahead of now
     status=LIVE        new_risk_allowed=True  age_seconds=1.0 venue_age_seconds=-3.0 receipt_minus_venue_s=-4.0
  no venue stamp at all: received 1 s ago
     status=LIVE        new_risk_allowed=True  age_seconds=1.0 venue_age_seconds=None receipt_minus_venue_s=None

  The threshold reads age_seconds ONLY. Sweeping the venue stamp across five values
  spanning an hour either side of now, the verdict does not move:
     venue=None               -> LIVE new_risk_allowed=True
     venue=-0.5s vs now       -> LIVE new_risk_allowed=True
     venue=-60.0s vs now      -> LIVE new_risk_allowed=True
     venue=-3600.0s vs now    -> LIVE new_risk_allowed=True
     venue=+60.0s vs now      -> LIVE new_risk_allowed=True
"""

BLOCK_F = """\
  parse_bi5(payload) — no fetch happened, so there is no receipt:
     tick[0] observed_at=None  venue_timestamp=2026-11-25T14:00:00.000Z
     tick[1] observed_at=None  venue_timestamp=2026-11-25T14:00:01.000Z
     -> the tick's time is DERIVED as hour_start + offset_ms, which is the venue's
        declaration read off the file's own hour, so it is the venue's field.

  parse_agg_trades_csv  observed_at=None  venue_timestamp=2025-11-25T12:00:00.000Z

  DukascopyHistorical.fetch_hour — a real fetch through the same bytes:
     result.received_at              = 2026-11-27T06:43:35.000Z
     result.to_dict()['received_at'] = 2026-11-27T06:43:35.000Z
     tick_count                      = 2
     ticks[0].observed_at            = 2026-11-27T06:43:35.000Z
     ticks[0].venue_timestamp        = 2026-11-25T14:00:00.000Z

  Same payload, two answers, and the difference is whether anything was received.
  Stamp a local clock in the parse case and you assert a receipt that never happened —
  F-14's error told in the other direction.
"""

BLOCK_G = """\
  both clocks   event_time -> 2025-11-25T12:00:00.000Z
  receipt only  event_time -> 2026-11-27T06:43:35.000Z
  neither       event_time -> datetime.min (sort floor)
  dedupe_ticks([both, receipt-only, neither]) -> 3 records, sorted, no TypeError
  validate_tick on the neither-clock record -> None
"""

# ---- CI check-run annotations, read through `gh api .../check-runs/<job>/annotations` ----
# Reproduced with the annotation's own percent-encoding removed for readability (`%3A` -> `:`,
# `%2C` -> `,`) and with the leading `warning:` / `failure:` level prefix kept where it was part of
# the message. Nothing else is edited: a number that is retyped is a number that can be improved.

LIVE_BEFORE_SUMMARY = """\
44 passed / 0 failed / 5 geo-blocked / 0 skipped of 49 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region)
okx.cross_endpoint quotes_mid=61658.75 book_mid=61666.55 gap_bps=1.265 dt_observed_s=1.137 dt_wall_s=0.35 bps_per_s_observed=1.113 bps_per_s_wall=3.617 quoted_spread_bps=0.016 asserts_agreement=False
"""

LIVE_AFTER_A_SUMMARY = """\
warning: 52 passed / 0 failed / 5 geo-blocked / 0 skipped of 57 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region)
okx.cross_endpoint quotes_mid=61925.35 book_mid=61939.75 gap_bps=2.325 dt_observed_s=0.116 dt_venue_s=0.498 dt_wall_s=0.244 skew_venue_over_wall=2.037 bps_per_s_observed=20.093 bps_per_s_venue=4.669 bps_per_s_wall=9.513 receipt_lag_quotes_s=0.436 receipt_lag_book_s=0.053 quoted_spread_bps=0.016 asserts_agreement=False
"""

LIVE_AFTER_B_SUMMARY = """\
warning: 51 passed / 0 failed / 5 geo-blocked / 1 skipped of 57 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region); 1 could not reach their source
okx.cross_endpoint quotes_mid=61963.15 book_mid=61963.15 gap_bps=0.0 dt_observed_s=0.172 dt_venue_s=0.239 dt_wall_s=0.355 skew_venue_over_wall=0.673 bps_per_s_observed=0.0 bps_per_s_venue=0.0 bps_per_s_wall=0.0 receipt_lag_quotes_s=0.153 receipt_lag_book_s=0.086 quoted_spread_bps=0.016 asserts_agreement=False
"""

LIVE_AFTER_C_SUMMARY = """\
warning: 52 passed / 0 failed / 5 geo-blocked / 0 skipped of 57 live checks
PARTIAL - 5 geo-blocked (need a runner outside the restricted region)
okx.cross_endpoint quotes_mid=61650.75 book_mid=61650.75 gap_bps=0.0 dt_observed_s=0.157 dt_venue_s=1.083 dt_wall_s=0.301 skew_venue_over_wall=3.604 bps_per_s_observed=0.0 bps_per_s_venue=0.0 bps_per_s_wall=0.0 receipt_lag_quotes_s=0.989 receipt_lag_book_s=0.062 quoted_spread_bps=0.016 asserts_agreement=False
"""

RUN_C_OKX_TRADES = """\
okx.trades count=50 price_min=61650.7 price_max=61655.2 sides=['BUY', 'SELL'] buy=2 sell=48 unspecified=0 newest=2026-11-27T12:09:00.225000+00:00 received_at=2026-11-27T12:09:01.596110+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=50 venue_time_first=2026-11-27T12:08:59.654000+00:00 venue_time_last=2026-11-27T12:09:00.225000+00:00
"""

RUN_C_OKX_QUOTES = """\
okx.quotes count=1 bid=61650.7 ask=61650.8 spread_bps=0.016 observed_at=2026-11-27T12:09:01.458494+00:00 venue_timestamp=2026-11-27T12:09:00.363000+00:00 receipt_lag_s=1.095 received_at=2026-11-27T12:09:01.458494+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=1 venue_time_first=2026-11-27T12:09:00.363000+00:00 venue_time_last=2026-11-27T12:09:00.363000+00:00
"""

RUN_C_VISION_BARS = """\
binance-vision.bars count=1440 interval=1m span_hours=23.98 close_min=57853.28000000 close_max=62531.01000000 first=2026-11-20T00:00:00+00:00 last=2026-11-20T23:59:00+00:00 received_at=2026-11-27T12:09:03.234070+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=1440 venue_time_first=2026-11-20T00:00:00+00:00 venue_time_last=2026-11-20T23:59:00+00:00
"""

FAILED_RUN_SUMMARY = """\
warning: 43 passed / 13 failed / 0 geo-blocked / 1 skipped of 57 live checks
AttributeError: '_CapturingTransport' object has no attribute 'fetch_json'
"""

RUN_A_OKX_QUOTES = """\
okx.quotes count=1 bid=61924.5 ask=61924.6 spread_bps=0.016 observed_at=2026-11-27T08:21:41.540466+00:00 venue_timestamp=2026-11-27T08:21:41.142000+00:00 receipt_lag_s=0.398 received_at=2026-11-27T08:21:41.540466+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=1 venue_time_first=2026-11-27T08:21:41.142000+00:00 venue_time_last=2026-11-27T08:21:41.142000+00:00
"""

RUN_A_OKX_TRADES = """\
okx.trades count=50 price_min=61937.1 price_max=61938.6 sides=['BUY', 'SELL'] buy=1 sell=49 unspecified=0 newest=2026-11-27T08:21:40.493000+00:00 received_at=2026-11-27T08:21:41.679179+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=50 venue_time_first=2026-11-27T08:21:40.237000+00:00 venue_time_last=2026-11-27T08:21:40.493000+00:00
"""

RUN_A_OKX_BARS = """\
okx.bars count=100 interval=1m span_hours=1.65 close_min=61460.6 close_max=62123.8 first=2026-11-27T06:42:00+00:00 last=2026-11-27T08:21:00+00:00 received_at=2026-11-27T08:21:41.810568+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=100 venue_time_first=2026-11-27T06:42:00+00:00 venue_time_last=2026-11-27T08:21:00+00:00
"""

RUN_A_OKX_BOOK = """\
okx.book depth=40 best_bid=61925.3 best_ask=61925.4 spread_bps=0.016 entitlement=LIVE observed_at=2026-11-27T08:21:41.961004+00:00 venue_timestamp=2026-11-27T08:21:41.905000+00:00 receipt_lag_s=0.056 received_at=2026-11-27T08:21:41.961004+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=1 venue_time_first=2026-11-27T08:21:41.905000+00:00 venue_time_last=2026-11-27T08:21:41.905000+00:00
"""

RUN_A_VISION_BARS = """\
binance-vision.bars count=1440 interval=1m span_hours=23.98 close_min=57853.28000000 close_max=62531.01000000 first=2026-11-20T00:00:00+00:00 last=2026-11-20T23:59:00+00:00 received_at=2026-11-27T08:21:42.878087+00:00 distinct_receipt_times=1 rows_with_a_venue_stamp=1440 venue_time_first=2026-11-20T00:00:00+00:00 venue_time_last=2026-11-20T23:59:00+00:00
"""

FAILED_RUN_DETAIL = """\
warning: 43 passed / 13 failed / 0 geo-blocked / 1 skipped of 57 live checks
failure: Process completed with exit code 1.

FAIL BybitLiveEndpoints.instrument_info_matches_the_live_listing
      capture saved=0 calls=0 dir=../live-captures
      AttributeError: '_CapturingTransport' object has no attribute 'fetch_json'
FAIL BybitLiveEndpoints.quotes_are_uncrossed_and_current
      capture saved=0 calls=0 dir=../live-captures
      AttributeError: '_CapturingTransport' object has no attribute 'fetch_json'
FAIL BybitLiveEndpoints.public_trades_normalise
      capture saved=0 calls=0 dir=../live-captures
      AttributeError: '_CapturingTransport' object has no attribute 'fetch_json'
   ... the same AttributeError on ten more checks

PASS BinanceVisionLiveDumps.the_dump_url_shape_is_correct
      binance-vision.url day=2026-11-20 bytes=73320 zip=True
PASS DukascopyLiveLayout.verify_layout_passes_against_a_real_file
      dukascopy.layout passed=True payload_bytes=41710 decompressed_bytes=181040 tick_count=9052 reasons=-
"""

TAMPER_ADAPTERS = """\
FAILED TestBybitAdapter::test_instrument_info_extracts_contract_economics
FAILED TestBybitAdapter::test_ticker_becomes_a_quote_with_decimal_prices
FAILED TestOkxAdapter::test_ticker_becomes_a_quote - ...
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_quotes_carry_our_receipt_time_and_okxs_own_ts
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_trades_share_one_receipt_time_and_are_ordered_by_venue_time
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_book_separates_the_two_clocks
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_instruments_take_their_stamp_from_the_entry_not_the_envelope
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_instruments_without_a_venue_stamp_do_not_borrow_ours
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_okx_bars_keep_the_event_time_and_gain_a_receipt_time
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_bybit_quotes_carry_our_receipt_time_and_the_entry_ts
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_bybits_server_time_fallback_lands_in_the_venues_field_not_ours
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_bybit_trades_share_one_receipt_time_and_are_ordered_by_venue_time
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_bybit_book_and_instruments_separate_the_two_clocks
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_bybit_bars_survive_the_field_by_field_rebuild
FAILED TestReceiptTimeIsOursAndVenueTimeIsTheirs::test_every_adapter_surface_produced_a_receipt_time

full suite under the same tamper:
15 failed, 1279 passed, 2 skipped in 24.29s
"""

TAMPER_HYGIENE = """\
>       assert incomplete == [], (
            "a Transport implementation does not satisfy the protocol. This is caught by scanning "
            "rather than by importing, because the implementation that failed once lives in a "
            "module the offline suite skips:\n  " + "\n  ".join(incomplete)
        )
E       AssertionError: a Transport implementation does not satisfy the protocol. This is caught by scanning rather than by importing, because the implementation that failed once lives in a module the offline suite skips:
E           backend/tests/test_live_endpoints.py:246 _CapturingTransport is missing ['fetch_json']
E       assert ["backend/tes...fetch_json']"] == []
E         
E         Left contains one more item: "backend/tests/test_live_endpoints.py:246 _CapturingTransport is missing ['fetch_json']"
E         Use -v to get more diff
/home/user/Nexus-Ai/backend/tests/test_repo_hygiene.py:1959: AssertionError
=========================== short test summary info ============================
FAILED tests/test_repo_hygiene.py::TestTransportImplementationsAreComplete::test_every_transport_implementation_offers_every_method
"""


# ------------------------------------------------------------------ §1 the ruling and its edges
def ruled_table() -> str:
    return table(
        ["D-052's ruling 2, as recorded", "What this batch did with it", "Where it is checked"],
        [
            (
                "&ldquo;<b>F-14&rsquo;s expensive half alone.</b> A real receipt time in "
                "<span class='mono'>okx</span>, <span class='mono'>bybit</span>, "
                "<span class='mono'>binance_vision</span> and <span class='mono'>dukascopy</span>, and "
                "nothing else.&rdquo;",
                "All four adapters moved to a transport that returns a receipt time. No adapter calls the "
                "receipt-less pair any more &mdash; and that is a grep, not a claim (&sect;3).",
                "<span class='mono'>TestReceiptTimeIsOursAndVenueTimeIsTheirs</span>, 16 tests, ending by "
                "walking <i>every</i> record-producing surface of all four adapters (&sect;9).",
            ),
            (
                "&ldquo;No dossier work, no new tables, no writer wiring.&rdquo;",
                "None. No migration exists beyond <span class='mono'>0004_memory_fidelity</span>, no "
                "migration checksum moved, and <span class='mono'>evidence_ref.retrieved_at</span> still "
                "has no caller in <span class='mono'>src/</span>. Two modules gained a <i>pointer</i> "
                "saying the receipt time now exists upstream, not a rewrite &mdash; their paragraphs were "
                "ruled on at D-050 and still hold.",
                "The existing test that greps <span class='mono'>src/nexus</span> for callers of either "
                "writer still passes, and still says nothing calls them (&sect;7).",
            ),
            (
                "&ldquo;Its own gate and its own live runs before and after, so a regression is "
                "attributable to it and to nothing else.&rdquo;",
                "The gate is &sect;9 and was proven load-bearing by tampering. The before run was captured "
                "at <span class='mono'>975dc64</span> before a line was changed; the after is <b>two</b> "
                "runs of <span class='mono'>bbfe95f</span>, minutes apart (&sect;12).",
                "The convergence reproduces: <span class='mono'>dt_observed_s / dt_wall_s</span> is "
                "<b>0.48&times;</b> in both after runs, against <b>3.25&times;</b> before.",
            ),
            (
                "&ldquo;<span class='mono'>O-012</span> stays <span class='mono'>OPEN</span> until it "
                "lands.&rdquo;",
                "It has landed. The row records the delivery and the measurements, and its status is "
                "<b>OPEN &mdash; 8.4 DELIVERED, closure requested</b>, because an unapproved batch should "
                "not close a ledger row.",
                "<span class='mono'>docs/00</span> O-012; question 1 in &sect;15 asks for the ruling that "
                "closes it.",
            ),
        ],
    )


def not_done_table() -> str:
    return table(
        ["Ruled out of 8.4", "How its absence is shown, not asserted", "Where it goes"],
        [
            (
                "<b>Any new gate.</b> Two numbers are published beside the freshness verdict and neither "
                "is gated on.",
                "<span class='mono'>test_the_venue_numbers_never_gate_anything</span> sweeps the venue "
                "stamp across five values spanning an hour either side of now and asserts the verdict does "
                "not move. Captured in &sect;7: all five read "
                "<span class='mono'>LIVE new_risk_allowed=True</span>.",
                "Nowhere. A threshold on a venue&rsquo;s clock would fail closed whenever that venue "
                "drifted, and a venue&rsquo;s clock is not ours to police.",
            ),
            (
                "<b>Writer wiring.</b> The receipt time exists and nothing durable consumes it.",
                "<span class='mono'>record_evidence</span> still takes <span class='mono'>retrieved_at</span> "
                "as a required argument with no default, and no caller supplies one. The live harness "
                "publishes it as an annotation and then it is gone.",
                "The stage-10 batch, or a smaller one whose whole job is giving the receipt time a "
                "destination &mdash; limitation 1 of &sect;14, and the alternative named in question 4.",
            ),
            (
                "<b>Dossier work.</b> No route, no projection, no new event type.",
                "The route count is unchanged at <b>13</b> application routes, and the "
                "<span class='mono'>view_gaps</span> list still has nine entries &mdash; one of which "
                "changed <i>kind</i> rather than disappearing (&sect;7).",
                "&mdash;",
            ),
        ],
    )


# ------------------------------------------------------------------ §4 adapters
def adapter_table() -> str:
    return table(
        ["adapter", "what its fetch helper returned before", "now", "where the venue's stamp comes from"],
        [
            (
                "<span class='mono'>okx</span>",
                "<span class='mono'>(data, None)</span> &mdash; the receipt time was <b>hard-coded to "
                "<span class='mono'>None</span></b>, so the field existed and said nothing",
                "<span class='mono'>(data, received_at)</span>",
                "the entry&rsquo;s own <span class='mono'>ts</span>, or <b><span class='mono'>None</span></b>: "
                "OKX&rsquo;s public envelope publishes no server time at all, so there is nothing to fall "
                "back to and borrowing ours would assert something about their clock they never said",
            ),
            (
                "<span class='mono'>bybit</span>",
                "<span class='mono'>(result, server_time)</span>",
                "<span class='mono'>(result, server_time, received_at)</span>",
                "the entry&rsquo;s <span class='mono'>ts</span>, falling back to the envelope&rsquo;s "
                "<span class='mono'>time</span> &mdash; Bybit is the one venue here that publishes its own "
                "envelope clock, so the fallback <b>survives and moves</b>: it lands in "
                "<span class='mono'>venue_timestamp</span>, because a fallback to <i>their</i> clock "
                "belongs in their field",
            ),
            (
                "<span class='mono'>binance_vision</span>",
                "payload only",
                "<span class='mono'>Fetched</span> via <span class='mono'>fetch_bytes</span>",
                "the CSV&rsquo;s own timestamp column, with <span class='mono'>epoch_unit</span> detecting "
                "&micro;s vs ms &mdash; and one receipt instant shared by every row of the dump (&sect;5)",
            ),
            (
                "<span class='mono'>dukascopy</span>",
                "payload only",
                "<span class='mono'>Fetched</span> via <span class='mono'>fetch_bytes</span>, published as "
                "<span class='mono'>DukascopyHour.received_at</span>",
                "<b>derived</b>: <span class='mono'>hour_start + offset_ms</span>. A bi5 tick has no "
                "timestamp of its own, so its time is the venue&rsquo;s declaration read off the "
                "file&rsquo;s own hour (&sect;8)",
            ),
        ],
    )


# ------------------------------------------------------------------ §5 what moved
def moved_table() -> str:
    return table(
        ["site", "what it read before", "now", "what it would have cost"],
        [
            (
                "<span class='mono'>parquet_store._time_of</span>",
                "partition key = <span class='mono'>observed_at</span>",
                "<span class='mono'>open_time</span> for bars, <span class='mono'>venue_timestamp</span> "
                "otherwise",
                "<b>the silent one.</b> A dump fetched today files under today&rsquo;s date, so a day of "
                "2025 trades would have landed in <span class='mono'>year=2026/month=11</span> and every "
                "backfilled day would have collapsed into the day the backfill ran. The rows would write, "
                "read back, and answer a date-range query &mdash; for the wrong dates. Nothing raises on a "
                "partition key that is merely wrong. Measured in &sect;6.",
            ),
            (
                "<span class='mono'>archive/bars.py</span>",
                "naive check, future check, sort key, <span class='mono'>bucket_start</span>, "
                "<span class='mono'>_accumulate</span> &mdash; all five on "
                "<span class='mono'>observed_at</span>",
                "all five on <span class='mono'>venue_timestamp</span>",
                "every bar built from a downloaded dump bucketed into one interval, and a rollup whose "
                "buckets are all the same bucket",
            ),
            (
                "<span class='mono'>pipeline</span> <span class='mono'>market.ticks.archived</span>",
                "<span class='mono'>min</span>/<span class='mono'>max</span> of "
                "<span class='mono'>observed_at</span> published as "
                "<span class='mono'>first</span>/<span class='mono'>last</span>",
                "<span class='mono'>min</span>/<span class='mono'>max</span> of "
                "<span class='mono'>event_time(t)</span>",
                "one instant published twice and called a range: a subscriber would read a one-instant span "
                "as an empty batch and a year of history as nothing",
            ),
            (
                "<span class='mono'>dedupe_ticks</span>",
                "sorted on <span class='mono'>observed_at</span>",
                "sorted on <span class='mono'>event_time</span>, total over "
                "<span class='mono'>None</span>",
                "a bulk download&rsquo;s dedupe order became the file&rsquo;s row order (&sect;8)",
            ),
            (
                "okx / bybit / binance-vision trade ordering",
                "sorted on <span class='mono'>observed_at</span>",
                "sorted on <span class='mono'>event_time</span>",
                "&ldquo;chronological&rdquo; trades in whatever order the venue happened to serve them",
            ),
        ],
    )


# ------------------------------------------------------------------ §11 the harness keys
def key_table() -> str:
    return table(
        ["key", "before 8.4", "after 8.4"],
        [
            (
                "<span class='mono'>dt_observed_s</span>",
                "the <b>venue&rsquo;s</b> interval, read from <span class='mono'>observed_at</span> &mdash; "
                "which held venue stamps",
                "<b>our</b> interval, from two receipt times. <span class='no'>Same key, different clock: "
                "the series changed meaning at <span class='mono'>8cdc871</span></span>",
            ),
            ("<span class='mono'>dt_venue_s</span>", "<i>did not exist</i>",
             "the venue&rsquo;s interval, from two <span class='mono'>venue_timestamp</span> values"),
            ("<span class='mono'>dt_wall_s</span>", "unchanged", "unchanged"),
            (
                "<span class='mono'>skew_venue_over_wall</span>",
                "<i>published as</i> <span class='mono'>dt_observed_s / dt_wall_s</span>",
                "the same quantity, under a key that names the clock it came from",
            ),
            ("<span class='mono'>bps_per_s_venue</span>", "<i>did not exist</i>",
             "the gap over the venue&rsquo;s interval &mdash; the third denominator, so all three readings "
             "of one gap are on the line"),
            (
                "<span class='mono'>receipt_lag_quotes_s</span>, "
                "<span class='mono'>receipt_lag_book_s</span>",
                "<i>did not exist</i>",
                "<b>receipt minus venue, inside a single record</b> &mdash; the measurement F-14 said did "
                "not exist anywhere in the system",
            ),
            (
                "every endpoint line",
                "<span class='mono'>observed_at</span> alone, and it was the venue&rsquo;s",
                "<span class='mono'>venue_timestamp</span>, <span class='mono'>receipt_lag_s</span>, "
                "<span class='mono'>received_at</span>, <span class='mono'>distinct_receipt_times</span>, "
                "<span class='mono'>rows_with_a_venue_stamp</span>",
            ),
            (
                "<span class='mono'>.trades newest</span>",
                "<span class='mono'>max</span> of <span class='mono'>observed_at</span>, which was venue "
                "time and therefore correct by accident",
                "<span class='mono'>max</span> of the venue stamps &mdash; because "
                "<span class='mono'>max</span> of a shared receipt instant publishes one arrival time and "
                "calls it the newest trade. A feed with no stamp gets "
                "<span class='mono'>newest=None</span>, never our arrival substituted",
            ),
        ],
    )


# ------------------------------------------------------------------ §12 before and after
def convergence_table() -> str:
    return table(
        ["reading", "before (<span class='mono'>975dc64</span>)",
         "after, run A", "after, run B", "after, run C"],
        [
            ("<span class='mono'>dt_observed_s / dt_wall_s</span>",
             "<span class='no'><b>3.25&times;</b></span> (1.137 / 0.35)",
             "<span class='ok'><b>0.48&times;</b></span> (0.116 / 0.244)",
             "<span class='ok'><b>0.48&times;</b></span> (0.172 / 0.355)",
             "<span class='ok'><b>0.52&times;</b></span> (0.157 / 0.301)"),
            ("venue interval / wall clock",
             "not separable &mdash; it <i>was</i> <span class='mono'>dt_observed_s</span>",
             "<b>2.037&times;</b> as <span class='mono'>skew_venue_over_wall</span>",
             "<b>0.673&times;</b> &mdash; below the 0.80&times; floor &sect;10.8 published",
             "<b>3.604&times;</b> &mdash; inside its 3.97&times; ceiling"),
            ("receipt minus venue, quote", "not measurable anywhere in the system",
             "<b>0.436 s</b>", "<b>0.153 s</b>", "<b>0.989 s</b>"),
            ("receipt minus venue, book", "not measurable anywhere in the system",
             "<b>0.053 s</b>", "<b>0.086 s</b>", "<b>0.062 s</b>"),
            ("<span class='mono'>gap_bps</span>", "1.265", "2.325", "0.0", "0.0"),
            ("<span class='mono'>buy / sell</span>", "48 / 2", "<b>1 / 49</b>", "<b>50 / 0</b>",
             "2 / 48"),
        ],
    )


def runs_table() -> str:
    return table(
        ["", "before", "failed, in between", "after &mdash; run A", "after &mdash; run B",
         "after &mdash; run C"],
        [
            ("commit", "<span class='mono'>975dc64</span>", "<span class='mono'>8cdc871</span>",
             "<span class='mono'>bbfe95f</span>", "<span class='mono'>bbfe95f</span>",
             "<span class='mono'>ec0dd09</span>"),
            ("backend tree", "&mdash;", "&mdash;", "this batch", "identical to run A&rsquo;s",
             "<b>identical to run A&rsquo;s</b> &mdash; <span class='mono'>git diff bbfe95f ec0dd09 "
             "-- backend/</span> is empty"),
            ("run", "<span class='mono'>45953629348</span>", "<span class='mono'>45963867416</span>",
             "<span class='mono'>45964962991</span>", "<span class='mono'>45964969570</span>",
             "<span class='mono'>45996139111</span>"),
            ("trigger", "<span class='mono'>pull_request</span>", "<span class='mono'>push</span>",
             "<span class='mono'>push</span>", "<span class='mono'>pull_request</span>",
             "<span class='mono'>pull_request</span>"),
            ("job / check-run", "<span class='mono'>140354959639</span>",
             "<span class='mono'>140387781536</span>", "<span class='mono'>140391348401</span>",
             "<span class='mono'>140391370141</span>", "<span class='mono'>140495884665</span>"),
            ("conclusion", "<span class='ok'>success</span>", "<span class='no'>failure</span>",
             "<span class='ok'>success</span>", "<span class='ok'>success</span>",
             "<span class='ok'>success</span>"),
            ("summary", "44 / 0 / 5 / 0 of <b>49</b>", "43 / <b>13</b> / 0 / 1 of <b>57</b>",
             "<b>52</b> / 0 / 5 / 0 of <b>57</b>", "<b>51</b> / 0 / 5 / 1 of <b>57</b>",
             "<b>52</b> / 0 / 5 / 0 of <b>57</b>"),
            ("annotation truncated by", "&mdash;", "&mdash;", "<span class='mono'>4372</span> escaped chars",
             "<span class='mono'>5185</span>", "<span class='mono'>5123</span>"),
        ],
    )


# ------------------------------------------------------------------ §13 the gate
def gate_table() -> str:
    return table(
        ["", "at <span class='mono'>975dc64</span>", "at <span class='mono'>8cdc871</span>",
         "at <span class='mono'>bbfe95f</span>"],
        [
            ("offline suite", "1259 passed / 2 skipped", "1290 passed / 2 skipped",
             "<b>1294 passed / 2 skipped</b>"),
            ("live checks", "49 collected", "57 collected",
             "<b>57 collected, 52 passed / 0 failed / 5 geo-blocked</b>"),
            ("<span class='mono'>test_repo_hygiene.py</span>", "84", "84", "<b>88</b>"),
            ("<span class='mono'>ruff check src tests</span>", "clean", "clean", "<b>clean</b>"),
            ("<span class='mono'>ruff format --check</span>", "91 files", "91 files", "<b>91 files</b>"),
            ("<span class='mono'>mypy src</span>", "Success, 61 files", "Success, 61 files",
             "<b>Success, 61 files</b>"),
            ("source LOC (61 files)", "14,938", "15,312", "<b>15,312</b>"),
            ("test LOC (30 files)", "16,214", "17,597", "<b>17,725</b>"),
        ],
    )


def newtests_table() -> str:
    return table(
        ["file", "new tests", "what they pin"],
        [
            ("<span class='mono'>test_adapters.py</span>", "+16",
             "the gate itself: both halves of both clocks on every adapter surface, one receipt time per "
             "bulk response, event-time ordering, and the opposite requirement from the three parsers"),
            ("<span class='mono'>test_data_quality.py</span>", "+9",
             "the gate ages <i>our</i> clock in both directions F-14 predicted, and the two venue numbers "
             "never gate anything"),
            ("<span class='mono'>test_live_endpoints.py</span>", "+8",
             "the harness&rsquo;s new keys, offline, with pinned arithmetic &mdash; counted by the live run, "
             "not by the offline suite, which skips the module"),
            ("<span class='mono'>test_repo_hygiene.py</span>", "+4",
             "F-23&rsquo;s gate: an AST scan for incomplete <span class='mono'>Transport</span> "
             "implementations, plus a test that the scan finds the four it exists for"),
            ("<span class='mono'>test_parquet_archive.py</span>", "+4 / &minus;1",
             "a dump received today files under the event date; no event time means no partition, not a "
             "borrowed one. One test renamed because its name described the wrong field"),
            ("<span class='mono'>test_pipeline.py</span>", "+2",
             "the published span is a span of event time, and the fallback for a row with none is stated "
             "rather than discovered"),
            ("<span class='mono'>test_archive_bars.py</span>", "+1",
             "<span class='mono'>MISSING_EVENT_TIME</span> is its own reason, not "
             "<span class='mono'>NAIVE_TIMESTAMP</span>"),
        ],
    )


# ------------------------------------------------------------------ §14 limitations
def limitations_table() -> str:
    return table(
        ["#", "limitation", "why it is stated rather than fixed here"],
        [
            ("1", "<span class='mono'>O-012</span> closes on the <b>adapters</b>, not on the system. A "
                  "receipt time now exists in all four and nothing in <span class='mono'>src/</span> writes "
                  "it anywhere durable.",
             "Ruling 2 forbade writer wiring in this batch. The consequence is exact: receipt latency is "
             "now <i>measurable</i> and still not <i>measured</i> outside a live run&rsquo;s annotation. "
             "It is the alternative named in question 4."),
            ("2", "<b>F-22 is untouched.</b> The evidence checksum is still verified only on a read.",
             "Out of scope by ruling, and ruling 4 recorded it as a finding rather than an audit precisely "
             "so it would not be closed by accident."),
            ("3", "The JSON captures are still re-serialised, not byte-faithful.",
             "<span class='mono'>HttpTransport.fetch_json</span> decodes inside "
             "<span class='mono'>_request</span>. Capturing the raw body means decoding outside it, which "
             "would move a malformed body out of the retry loop and stop it being a retryable "
             "<span class='mono'>IngestFault</span>. Byte fidelity of a capture is not worth changing fault "
             "semantics for (&sect;10)."),
            ("4", "<b>No Bybit or Dukascopy number is quoted from any after run.</b>",
             "All three annotations truncate past the cap &mdash; <span class='mono'>4372</span>, "
             "<span class='mono'>5185</span> and <span class='mono'>5123</span> escaped characters over it "
             "&mdash; and those rows fall past the cap in every one, as they did in the before run. The "
             "comparison is like-for-like on that account. Bybit is verified by the offline gate and by "
             "thirteen checks that now pass, not by a published measurement. The Dukascopy LZMA ratios in "
             "&sect;3 come from the <i>before</i> run and from the failed run at <span class='mono'>8cdc871</span>, "
             "and are labelled as doing so there."),
            ("5", "<span class='mono'>receipt_minus_venue_s</span> and "
                  "<span class='mono'>receipt_lag_*_s</span> are <b>not latency</b>.",
             "They conflate network delay with the offset between the venue&rsquo;s clock and ours, exactly "
             "as <span class='mono'>apparent_latency_seconds</span> does, and are labelled as doing so "
             "wherever they appear. A negative value means the venue&rsquo;s clock runs fast; it is "
             "recorded, not refused and not clamped."),
            ("6", "<b>Three readings under the new key are still not a property.</b> They span "
                  "<b>0.673&times; to 3.604&times;</b>, a factor of 5.4, on one backend tree.",
             "&sect;10.8&rsquo;s range came from eight pairs across runs 24&ndash;31. The spread is the "
             "point rather than a weakness &mdash; it is why the quantity is published as a range, and why "
             "P-8&rsquo;s recommendation at Stage 7.3 chose no tolerance &mdash; but three samples cannot "
             "bound anything either, one of the three came from a commit that was not part of the batch, and "
             "geo-blocking still removes Bybit from every hosted run."),
            ("7", "The AST scan gates method <b>presence</b>, not signatures.",
             "A transport whose <span class='mono'>fetch_json</span> took different arguments would satisfy "
             "it. <span class='mono'>mypy src</span> covers <span class='mono'>src/</span>; the live module "
             "is not type-checked because it is not under <span class='mono'>src/</span>. Question 3 asks "
             "whether this posture is right."),
            ("8", "<b>Nothing re-reads &sect;3.5&rsquo;s &Delta;t column.</b>",
             "Its prose was corrected when F-14 was raised and its numbers are now attributable as "
             "venue-timestamp skew, but the section was not rewritten because ruling 2 scoped this batch to "
             "the adapters."),
        ],
    )


# ------------------------------------------------------------------ §15 the four questions
def questions_table() -> str:
    return table(
        ["#", "question", "recommendation", "the alternative, and what it costs"],
        [
            (
                "1",
                "<b>Is Stage 8.4 approved?</b>",
                "<b>Approve, recorded as D-053</b>, with F-23 disclosed (&sect;10) and with <b>all four</b> "
                "of this record&rsquo;s self-corrections disclosed: <span class='mono'>8cdc871</span>&rsquo;s "
                "tamper count (&sect;9), <span class='mono'>bbfe95f</span>&rsquo;s Dukascopy claim "
                "(&sect;10), the LZMA ratio and its run attribution (&sect;3), and the run-count mechanism "
                "(&sect;12). <span class='mono'>O-012</span> moves to <b>CLOSED</b>. Ruling 2&rsquo;s scope "
                "was kept, its gate exists and was proven load-bearing, and its runs show the convergence it "
                "was for &mdash; three times, on one backend tree.",
                "Hold <span class='mono'>O-012</span> open until a writer consumes the receipt time. That "
                "makes the ledger row a statement about limitation 1 &mdash; real, and named &mdash; rather "
                "than about the defect F-14 described, which is four adapters recording nothing about "
                "arrival. It would also leave a closed defect looking open to the next reader.",
            ),
            (
                "2",
                "<b>Does the pre-8.4 skew series continue under the renamed key, and what happens to its "
                "published floor?</b>",
                "<b>It continues</b>, and &sect;10.8&rsquo;s range is restated as "
                "<span class='mono'>skew_venue_over_wall</span> <b>0.673&times;&ndash;3.97&times;</b> with "
                "8.4&rsquo;s three readings admitted as its ninth, tenth and eleventh pairs. Every historical "
                "value was <span class='mono'>dt_observed_s / dt_wall_s</span> where "
                "<span class='mono'>dt_observed_s</span> came from a field holding venue stamps, which is "
                "exactly venue-interval over wall-interval; only the key moved. The three readings do not "
                "pull the same way, and that is what makes the question answerable: run B&rsquo;s "
                "<b>0.673&times;</b> is below the published floor while run C&rsquo;s <b>3.604&times;</b> "
                "sits inside the published ceiling, so only the <b>floor</b> moves.",
                "Stop the series here and record 0.673&times; as a one-off outside it. That leaves a "
                "published floor of 0.80&times; that a run of this repository&rsquo;s own CI has already "
                "gone below, with nothing saying so, while discarding a third reading the same range already "
                "contains. Starting a <i>new</i> series at 8.4 is also defensible &mdash; the pre-8.4 values "
                "were computed by the harness from fields rather than published under this key &mdash; but it "
                "orphans the older range with nothing to compare against, and run C is the argument against "
                "it: a fresh series of one reading, bounded by 3.604&times; and 3.604&times;, states less "
                "than the eleven-pair range it would replace.",
            ),
            (
                "3",
                "<b>Is F-23&rsquo;s gate the right posture &mdash; an AST scan of test-only "
                "implementations, or should the wrapper move where the offline suite imports it?</b>",
                "<b>Keep the scan; do not move the wrapper.</b> It names the file and line of any "
                "incomplete implementation, runs in the ordinary CI job, and was proven load-bearing by "
                "tampering (&sect;10).",
                "Moving <span class='mono'>_CapturingTransport</span> into <span class='mono'>src/</span> "
                "puts test scaffolding in the shipped package. Moving it into an importable test helper "
                "lets it be <i>imported</i> but not exercised &mdash; constructing it needs an "
                "<span class='mono'>HttpTransport</span> and a directory &mdash; and a test that imports a "
                "class without calling it proves only that the class exists, which the scan already proves "
                "more cheaply. A <span class='mono'>runtime_checkable</span> "
                "<span class='mono'>isinstance</span> assertion checks the same thing and cannot run "
                "against a module that skips at import.",
            ),
            (
                "4",
                "<b>What is the next batch?</b>",
                "<b>Stage 10&rsquo;s <span class='mono'>memory_item</span> writer</b>, as ruling 3 already "
                "ordered. Nothing in this batch changes that ordering: 8.4 added no tables and no wiring, "
                "so ruling 3&rsquo;s reason still holds &mdash; a dossier with no beliefs beside it is a "
                "case file with no conclusions in it &mdash; and that batch carries F-18&rsquo;s three "
                "columns plus <span class='mono'>evidence_ref.contradicts</span>.",
                "Wire <span class='mono'>retrieved_at</span> first, closing limitation 1 by giving the "
                "receipt time a destination. Smaller, and it would make 8.4&rsquo;s number durable &mdash; "
                "but it writes evidence rows for data nobody has decided to collect, which is the step "
                "ruling 3 declined.",
            ),
        ],
    )


def rulings_table() -> str:
    return table(
        ["#", "question as put", "ruled", "what it changes"],
        [
            ("1", "Is Stage 8.4 approved?",
             "<b>Approved, recorded as D-053</b>, with F-23 disclosed and with <b>all four</b> of this "
             "record&rsquo;s self-corrections disclosed rather than rewritten.",
             "Both 8.4 rows in <span class='mono'>docs/07</span> move to <span class='ok'>REVIEWED &mdash; "
             "APPROVED 2026-11-27</span>, the Stage 8 header reads 8.4 <span class='ok'>APPROVED</span>, and "
             "<b>F-14 and <span class='mono'>O-012</span> move to CLOSED</b>. The four disclosures are "
             "&sect;9 (the tamper count), &sect;10 (the Dukascopy claim), &sect;3 (the LZMA ratio) and "
             "&sect;12 (the run-count mechanism)."),
            ("2", "Does the skew series continue under the renamed key, and what happens to its floor?",
             "<b>It continues</b>, and &sect;10.8&rsquo;s range is restated as "
             "<span class='mono'>skew_venue_over_wall</span> <b>0.673&times;&ndash;3.97&times;</b> across "
             "<b>eleven</b> pairs.",
             "The restatement is an <b>inserted pointer in &sect;10.8</b>, not a rewrite: those eight rows were "
             "ruled on by D-051 and D-052 and stand as published. 8.4&rsquo;s three readings are its ninth, "
             "tenth and eleventh pairs. <b>The floor moves and the ceiling does not</b> &mdash; the spread "
             "widens from 5.0&times; to <b>5.9&times;</b> and two runs now sit below one. The new pairs are "
             "keyed on <b>commit and run id</b> rather than a sequential run number, because &sect;10.8&rsquo;s "
             "own rule is that a count re-triggering per push is stale on arrival &mdash; and the numbering "
             "already disagrees with itself about which run was 32."),
            ("3", "Is F-23&rsquo;s gate the right posture?",
             "<b>Keep the AST scan; do not move the wrapper.</b>",
             "Nothing changes in the code, which is the point: the scan already names file and line, runs in "
             "the ordinary CI job, and was proven load-bearing by tampering. Both alternatives were declined "
             "on the record &mdash; into <span class='mono'>src/</span> puts test scaffolding in the shipped "
             "package, and into an importable test helper lets <span class='mono'>_CapturingTransport</span> be "
             "imported but not exercised, which proves only that a class exists. A "
             "<span class='mono'>runtime_checkable</span> <span class='mono'>isinstance</span> assertion was "
             "named and declined too: same check, and it cannot run against a module that skips at import."),
            ("4", "What is the next batch?",
             "<b>Stage 10&rsquo;s <span class='mono'>memory_item</span> writer</b>, as D-052&rsquo;s ruling 3 "
             "already ordered.",
             "Nothing in this batch changed the ordering, because 8.4 added no tables and no wiring, so ruling "
             "3&rsquo;s reason still holds. That batch carries F-18&rsquo;s three columns plus "
             "<span class='mono'>evidence_ref.contradicts</span>. Wiring "
             "<span class='mono'>retrieved_at</span> first was offered and <b>not</b> taken."),
        ],
    )


def not_done_by_ruling_table() -> str:
    return table(
        ["what D-053 does <b>not</b> do", "where it stays visible"],
        [
            ("It does <b>not</b> close limitation 1. "
             "<span class='mono'>evidence_ref.retrieved_at</span> still has no caller, so the receipt time this "
             "batch built is still produced and dropped.",
             "Published <i>beside</i> the closure rather than retired by it. <span class='mono'>O-012</span> "
             "closes on the defect F-14 named &mdash; four adapters recording nothing about arrival &mdash; and "
             "not on the system."),
            ("It does <b>not</b> touch F-22 (<span class='mono'>O-014</span>): the evidence checksum is still "
             "verified only when somebody looks.",
             "D-052&rsquo;s ruling 4 recorded it as a finding precisely so it would not be closed by accident, "
             "and it stays <span class='mono'>OPEN</span>."),
            ("It does <b>not</b> fill the <span class='mono'>view_gap</span> that changed kind. A receipt time "
             "says when <i>we got</i> something, not when the source <i>published</i> it.",
             "&sect;7. J-04&rsquo;s first of three times is exactly as unrecordable as it was, and the "
             "route&rsquo;s corrected text says so instead of pointing at a merged batch."),
            ("It does <b>not</b> bound anything &sect;14 left unbounded &mdash; limitations 5, 6, 7 and 8 all "
             "stand as published.",
             "&sect;14. Limitation 6 is <b>widened</b> by run C rather than retired by it: three samples still "
             "cannot bound anything, and one of the three came from a commit that was not part of the batch."),
        ],
    )


def main() -> pathlib.Path:
    tokens = re.sub(r"@font-face \{[^}]*\}", "", (HERE / "tokens.css").read_text())

    html_out = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Nexus-AI &middot; Stage 8.4 Intelligence Memory &mdash; Two Clocks, Kept Apart</title>
<style>{tokens}
{fonts_css()}
{CSS}</style></head><body><div class='wrap'>
<div class="lede">Nexus-AI &middot; Stage 8 of 23 &middot; sub-deliverable 8.4 &middot; authorised by
D-052&rsquo;s ruling 2 as <b>F-14&rsquo;s expensive half alone</b> &middot; <b>approved 2026-11-27
(D-053)</b> &middot; <b>F-14 and O-012 CLOSED</b> &middot; next: stage 10&rsquo;s
<span style="font-family:var(--font-family-mono)">memory_item</span> writer</div>
<h1 style="font-size:var(--font-size-heading);font-weight:var(--font-weight-semibold);margin:6px 0 0">
All four adapters get a receipt time, the archive stops partitioning on it, and the run that was to prove
the fix first failed on a test the offline suite cannot see</h1>
<div class="ribbon">This batch changes <b>13 source files</b> and <b>10 test files</b> across two commits
&mdash; <span class="mono">8cdc871</span> (22 files, +1,901 / &minus;144) and
<span class="mono">bbfe95f</span> (2 files, +134 / &minus;6) &mdash; gate <b>1,294 passed / 2 skipped / 0
failed</b> (+35 offline, +8 live checks), mypy strict clean on <b>61</b> files, ruff and format clean on
<b>91</b>. <span class="mono">Transport</span> grew from three methods to five;
<span class="mono">observed_at</span> is now <b>ours</b> and <span class="mono">venue_timestamp</span> is
<b>the venue&rsquo;s</b>, and five places that ordered, bucketed or partitioned on the receipt clock moved
off it &mdash; the archive&rsquo;s partition key being the one that would have been <b>silent</b> (&sect;6).
It found and closed <b>F-23</b>: the run that was to prove the fix failed 13 of 57 live checks because the
fourth <span class="mono">Transport</span> implementation lives in a module the offline suite skips at
import (&sect;10). Ruling 2&rsquo;s runs are in &sect;12 and the convergence <b>reproduces three times on
one backend tree</b>: <span class="mono">dt_observed_s / dt_wall_s</span> went from <b>3.25&times;</b> to
<b>0.48&times;</b>, <b>0.48&times;</b> and <b>0.52&times;</b>, with the venue&rsquo;s own skew now separable
and labelled at <b>2.037&times;</b>, <b>0.673&times;</b> and <b>3.604&times;</b> &mdash; a 5.4&times; spread
on identical code, so the range&rsquo;s <b>floor</b> and not its ceiling is what question 2 asks about.
<b>Four published numbers are corrected as they are carried</b> rather than rewritten: two sit in commit
messages already pushed (&sect;9, &sect;10) and two in the record commit
<span class="mono">ec0dd09</span> itself (&sect;3, &sect;12). Nothing is wired:
<span class="mono">evidence_ref.retrieved_at</span> still has no caller, by ruling.</div>

<h3>1 &middot; What ruling 2 authorised, and what this batch therefore did not do<span class="tag">D-052 &middot; docs/15 &sect;11.0</span></h3>
<p>One of D-052&rsquo;s four rulings scoped this batch and three constrained it. The scope is narrow on
purpose: four adapters, and nothing else, so that a regression in the live run is attributable to this batch
and to nothing else. That is also why the before run was captured <b>before a line was changed</b> &mdash;
at <span class="mono">975dc64</span>, whose own three runs were all green, so the only difference between
the two measurements is this batch. <i>Three</i> and not four, because that commit touched no adapter and
<span class="mono">venue-verification</span>&rsquo;s <span class="mono">push</span> trigger is path-filtered
&mdash; the mechanism &sect;12 sets out, and a figure this board first got wrong.</p>
<div class="card">{ruled_table()}</div>
<p class="cap">The three things ruled <i>out</i> are shown absent rather than merely unmentioned, because
&ldquo;we did not do it&rdquo; is the claim most easily made and least easily checked.</p>
<div class="card">{not_done_table()}</div>

<h3>2 &middot; The defect: two fields, one value, no record of arrival<span class="tag">F-14 &middot; ledger O-012 &middot; docs/14 &sect;4.2</span></h3>
<p>F-14 named eight sites &mdash; <span class="mono">okx.py:216</span>/<span class="mono">:380</span>,
<span class="mono">bybit.py:353</span>/<span class="mono">:416</span>/<span class="mono">:439</span>,
<span class="mono">binance_vision.py:339</span>, <span class="mono">dukascopy.py:253</span> &mdash; at which
an adapter bound <span class="mono">observed_at</span> to venue-supplied time. <b>All eight were
re-verified against the working tree before a line was changed</b>, and all eight still said what the
finding said. The finding&rsquo;s <i>paths</i> did not: it cites the adapters by bare filename, and they
live in <span class="mono">backend/src/nexus/ingestion/</span>, not in a
<span class="mono">src/nexus/ingest/adapters/</span>. Resolved with <span class="mono">git ls-files</span>,
because a path quoted in a finding can be wrong while its line numbers are right.</p>
{verbatim("CAPTURED — one payload through a transport whose receipt clock is pinned a year away from the venue stamp in it", BLOCK_A, "after")}
<p class="cap">The distance is the test. An assertion that <span class="mono">observed_at is not
None</span>, or that it is timezone-aware, passes just as happily when an adapter copies the venue&rsquo;s
stamp into it &mdash; which is what all four did. Three such assertions already existed in
<span class="mono">test_adapters.py</span> and are strengthened in &sect;8 rather than left to keep passing
for the wrong reason.</p>
<div class="blocked"><b>The consequence is easier to state than to see.</b> A record carried two timestamp
fields and both held the venue&rsquo;s value, so <span class="mono">observed_at</span> &mdash; a field whose
name says <i>we observed this at</i> &mdash; held a number produced by somebody else&rsquo;s clock, and the
interval between the two fields, the only thing that would make receipt latency measurable, was
<b>identically zero everywhere in the system</b>. Two findings followed, both written down when F-14 was
raised: &sect;3.5&rsquo;s &Delta;t column measured venue-timestamp skew while its prose called it the
harness&rsquo;s fetch interval, and any staleness gate computed against the venue&rsquo;s clock while its
details called the number ours.</div>

<h3>3 &middot; The transport grows two methods, and the stamp is taken before the body is decoded<span class="tag">docs/15 &sect;11.1</span></h3>
<p><span class="mono">fetch_json</span>/<span class="mono">fetch_bytes</span> return
<span class="mono">Fetched(payload, received_at, url, attempts)</span>.
<span class="mono">get_json</span>/<span class="mono">get_bytes</span> stay payload-only &mdash; not as
legacy to be removed, but for callers that receive nothing worth timing: reachability probes, and
<span class="mono">verify_layout</span>, which is handed bytes rather than fetching them. That split is what
made &sect;10&rsquo;s failure readable: the checks that survived it are exactly the ones that used the
receipt-less pair.</p>
{verbatim("CAPTURED — Fetched, the stamp site in HttpTransport._request, the protocol verbatim, and the grep that closes it", BLOCK_B)}
<div class="blocked"><b>Before decode, and that is a measurement decision rather than a style one.</b> A
Dukascopy hour expands <b>roughly fourfold</b> under LZMA and a Binance Vision dump unzips before it parses.
Charging that CPU to the receipt time would inflate every latency this system reports by an amount that
depends on the payload&rsquo;s compression ratio, which is a way of measuring the compressor and calling it
the network. The expansion is published four times in this record&rsquo;s own live runs, and it is two
distinct hours rather than one measurement repeated: <span class="mono">25,761 &rarr; 101,480</span> bytes
holding 5,074 ticks in runs 30 and 31 = <b>3.94&times;</b>, and
<span class="mono">41,710 &rarr; 181,040</span> holding 9,052 ticks in the before run and in the failed run
at <span class="mono">8cdc871</span> = <b>4.34&times;</b>. No &ldquo;after&rdquo; run publishes
<span class="mono">dukascopy.layout</span> at all &mdash; every one of their annotations truncates first,
which is &sect;14&rsquo;s limitation 4 &mdash; so this batch&rsquo;s own Dukascopy numbers come from the
before run and from the failed run, and are labelled as doing so.</div>
<p class="cap"><b>A correction to the ratio this board first carried.</b> It said
&ldquo;roughly 2.5&times;&rdquo; and attributed the byte counts to run A. Neither held: no published pair in
this record expands 2.5&times;, and run A publishes only
<span class="mono">dukascopy.url &hellip; bytes=41710</span>, not the decompressed size or the tick count.
The likeliest provenance of 2.5&times; is F-14&rsquo;s own first skew reading &mdash;
<span class="mono">dt_observed_s=0.739</span> against <span class="mono">dt_wall_s=0.294</span>, which is
2.51&times; and is recorded in <span class="mono">docs/07</span>&rsquo;s Stage 7.3 row &mdash; but that is a
ratio of two <i>intervals</i> and not of two byte counts, and nothing licenses carrying it across. Corrected
in <span class="mono">docs/15</span> &sect;11.1 with the four-run table beside it.</p>

<h3>4 &middot; Four adapters, four different shapes of one defect<span class="tag">docs/15 &sect;11.2</span></h3>
<p>The finding read as one defect in four places, and it was four defects that happened to look alike. Two
of them are the whole content of the batch.</p>
<div class="card">{adapter_table()}</div>
<div class="blocked"><b>OKX publishes no envelope time, so its instrument records may have no venue stamp at
all &mdash; and the honest value is <span class="mono">None</span>.</b> Copying our receipt time into
<span class="mono">venue_timestamp</span> would satisfy the type, satisfy any
<span class="mono">is not None</span> assertion, and assert something about OKX&rsquo;s clock that OKX never
said. That is F-14&rsquo;s error told in the other direction, and it is why
<span class="mono">TickRecord.observed_at</span>, <span class="mono">BarRecord.observed_at</span> and
<span class="mono">DukascopyHour.received_at</span> are all optional in the type: <b>optional offline</b>,
where a parse from bytes on disk received nothing, and <b>guaranteed on the live path</b>, where the
transport always has one. The guarantee is asserted rather than trusted &mdash; &sect;9&rsquo;s last test
walks every record-producing surface of all four adapters and requires it from each.</div>

<h3>5 &middot; What had to move off the receipt clock<span class="tag">docs/15 &sect;11.3</span></h3>
<p>A bulk download gives <b>one</b> arrival instant to every row in it. So anywhere that ordered, bucketed
or partitioned on <span class="mono">observed_at</span> was reading a constant and calling it a time. Five
places did, and one of them would never have announced itself.</p>
<div class="card">{moved_table()}</div>
<p class="cap">Four separate <span class="mono">or</span> chains for &ldquo;the event time of this
tick&rdquo; became one named function, <span class="mono">records.event_time</span>, because the rule has to
mean the same thing at every call site and four copies of it will not stay the same. Its floor case returns
<span class="mono">datetime.min</span> rather than raising, so ordering stays total for hand-built records;
every consumer that <i>acts</i> on the value refuses a tick with no venue stamp under its own reason
first.</p>

<h3>6 &middot; The partition key, measured rather than argued<span class="tag">docs/15 &sect;11.3</span></h3>
<p>Three ticks, event times one minute apart in <b>November 2025</b>, all received in one response in
<b>November 2026</b>. Written to a real <span class="mono">ParquetArchive</span> on a temporary directory,
then the directory is walked.</p>
{verbatim("CAPTURED — one write, two candidate partitions, and what is actually on disk", BLOCK_D, "after")}
<p class="cap">The file is under <span class="mono">year=2025/month=11</span> and its rows still carry
<span class="mono">observed_at=2026-11-27</span>: the receipt time is stored, it is simply not the key. A
partition key is the one field whose wrongness does not raise &mdash; the rows write, they read back, and
they answer a date-range query for the wrong dates.</p>
{verbatim("RUN A, verbatim from the CI annotation — a real download rather than a fixture", RUN_A_VISION_BARS, "after")}
<p class="cap">1,440 one-minute bars spanning <b>23.98 hours of 2026-11-20</b>, received in one response at
<b>08:21:42 on 2026-11-27</b>. <span class="mono">distinct_receipt_times=1</span>. Had the archive keyed on
the receipt clock, all 1,440 would have filed under the 27th.</p>

<h3>7 &middot; What this batch does not do<span class="tag">docs/15 &sect;11.4</span></h3>
<p><b>No new gate.</b> <span class="mono">freshness</span> publishes
<span class="mono">venue_age_seconds</span> and <span class="mono">receipt_minus_venue_s</span> beside
<span class="mono">age_seconds</span>, and the threshold reads ours alone. The two directions F-14 predicted
are pinned as tests rather than described &mdash; and they are the two directions that matter, because one
of them allows new risk.</p>
{verbatim("CAPTURED — the gate on a fixed clock, in both directions, and with the venue numbers swept across an hour either side", BLOCK_E)}
<div class="blocked"><b>A venue running behind made stale data look fresh</b> &mdash; the dangerous
direction, because it is the one that allows new risk: our receipt 30 s old, the venue&rsquo;s stamp 2 s
old, and a gate aging the venue&rsquo;s clock says <span class="mono">LIVE</span>. <b>A venue running ahead
made fresh data look stale</b>, and further ahead still tripped the future-timestamp fault &mdash; a
<i>clock fault in our system</i> caused entirely by somebody else&rsquo;s clock. Neither number gates
anything, because a threshold on a venue&rsquo;s clock would fail closed whenever that venue drifted.</div>
<p class="cap"><span class="mono">venue_age_seconds</span> is deliberately <b>not</b> clamped by
<span class="mono">core.time.age_seconds</span>. That helper clamps a future stamp to
<span class="mono">0.0</span> on the contract that the gate flags it separately as a clock fault &mdash; and
the flag reads our receipt time only. Clamping the venue&rsquo;s would report a stamp that has not happened
yet as brand new, which is the one case the number exists to show. Hence <span class="mono">-3.0</span> in
the third line above.</p>
<p><b>One <span class="mono">view_gap</span> changed kind, and the route says so.</b> &sect;10.9 recorded
that one of the nine gaps &ldquo;waits on 8.4&rdquo;: <i>publication time in the evidence table</i>. 8.4 has
now landed without filling it &mdash; a receipt time says when <b>we got</b> something, not when the source
<b>published</b> it, so J-04&rsquo;s first of three times is exactly as unrecordable as it was. The served
text was changed rather than left pointing at a batch the reader can go and find already merged, and
<span class="mono">test_intelligence_routes.py</span> pins the new wording: a gap that says
&ldquo;waiting on 8.4&rdquo; after 8.4 merged sends the reader to a queue that is empty.</p>

<h3>8 &middot; Parsing bytes from disk invents no receipt time<span class="tag">docs/15 &sect;11.2, &sect;11.6</span></h3>
<p>The same bi5 payload, parsed and fetched. Two answers, and the difference is whether anything was
received.</p>
{verbatim("CAPTURED — parse_bi5 and parse_agg_trades_csv against a real fetch_hour of the same bytes", BLOCK_F)}
{verbatim("CAPTURED — event_time is total, so dedupe_ticks sorts a record with neither clock instead of raising", BLOCK_G)}
<p class="cap">A capture replayed, a fixture parsed, a layout verified &mdash; none of them received
anything, and stamping the local clock would assert a receipt that never happened. This is also why making
<span class="mono">TickRecord.observed_at</span> optional was not a convenience: it is the type telling the
truth about the disk path. What it cost is recorded in &sect;14&rsquo;s limitation 7 and in the three
consumer repairs below.</p>
<div class="card">{table(
    ["a test that passed for the wrong reason", "why it passed", "what was done"],
    [
        ("<span class='mono'>test_naive_tick_time_is_refused</span>",
         "still green after the partition key moved &mdash; but now because the row had <b>no</b> event time "
         "at all rather than a naive one",
         "renamed and re-aimed at the venue&rsquo;s field, with a dedicated missing-event-time test beside it"),
        ("<span class='mono'>test_quote_without_observation_time_is_refused</span>",
         "the archive needs the venue&rsquo;s <b>event</b> time, and the name said otherwise",
         "renamed to <span class='mono'>&hellip;without_an_event_time&hellip;</span>"),
        ("the archive&rsquo;s refusal message",
         "named <span class='mono'>observed_at</span> while the check read "
         "<span class='mono'>venue_timestamp</span>",
         "corrected to name the field it checks. A refusal that points at the wrong field sends whoever "
         "reads it to fix a timestamp that was never the problem"),
        ("<span class='mono'>archive/bars.py</span>&rsquo;s rejection reason",
         "a tick with no event time was counted as <span class='mono'>NAIVE_TIMESTAMP</span>",
         "now <span class='mono'>MISSING_EVENT_TIME</span>, because the reason string is read by whoever "
         "must fix the feed, and those are different repairs"),
        ("three adapter pins (<span class='mono'>:473</span>, <span class='mono'>:555</span>, "
         "<span class='mono'>:786</span> at <span class='mono'>975dc64</span>; <span class='mono'>:494</span>, "
         "<span class='mono'>:581</span>, <span class='mono'>:816</span> now)",
         "asserted only <span class='mono'>observed_at is not None</span>, which the pre-8.4 code satisfied "
         "by copying the venue&rsquo;s stamp",
         "now pin an exact receipt clock a year from the venue stamp in the same payload. Every fixture "
         "transport in <span class='mono'>TestBybitAdapter</span> and <span class='mono'>TestOkxAdapter</span> "
         "runs on it, and the six shared <span class='mono'>conftest</span> snapshots gained the venue&rsquo;s "
         "stamp too &mdash; otherwise every fixture in the suite is a pre-8.4 record with one clock"),
    ],
)}</div>

<h3>9 &middot; The gate, and proof that it is load-bearing<span class="tag">D-052 ruling 2 &middot; docs/15 &sect;11.6</span></h3>
<p><span class="mono">TestReceiptTimeIsOursAndVenueTimeIsTheirs</span> is the gate ruling 2 asked this batch
to have of its own: <b>16 tests</b> across all four adapters, each asserting <b>both</b> halves. Asserting
only <span class="mono">observed_at</span> would pass on an adapter that stamped our clock into
<i>both</i> fields &mdash; the same defect with the clocks swapped &mdash; and asserting only
<span class="mono">venue_timestamp</span> passes on the pre-8.4 code.</p>
<p>It was verified by tampering rather than by reading. All <b>ten</b> record-construction sites in
<span class="mono">okx.py</span> and <span class="mono">bybit.py</span> were reverted so
<span class="mono">observed_at</span> takes the venue&rsquo;s own value from the adjacent
<span class="mono">venue_timestamp=</span> argument &mdash; five sites each,
<span class="mono">to_utc(entry.get("ts"), &hellip;)</span>, <span class="mono">venue_ts</span> &times;3,
<span class="mono">open_time</span>, <span class="mono">server_time</span>,
<span class="mono">bar.open_time</span>. That is F-14 restored faithfully in two of the four adapters: both
fields hold one number again.</p>
{verbatim("CAPTURED — the gate under a faithful restoration of F-14 in two adapters", TAMPER_ADAPTERS, "before")}
<div class="blocked"><b>A correction to the figure <span class="mono">8cdc871</span>&rsquo;s commit message
carries.</b> That message says eight tests failed. The eight came from a
<span class="mono">-k</span>-filtered run against a tamper that substituted
<span class="mono">to_utc(entry.get("ts")) or received_at</span> at all five sites of each adapter by blind
string replacement &mdash; an expression that is <b>not valid at two of them</b> (the
<span class="mono">okx</span> and <span class="mono">bybit</span> bar rebuilds, where the variable in scope
is <span class="mono">row</span>/<span class="mono">bar</span>, not <span class="mono">entry</span>), so
those two raised <span class="mono">TypeError</span> instead of failing an assertion, and the filter
excluded the three strengthened pins entirely. The measurement was therefore both <b>undercounted and
partly a crash report</b>. Re-run site by site it gives <b>fifteen</b>: twelve in the new gate and three in
the strengthened pre-existing pins of &sect;8 &mdash; which is the point of strengthening them, because a
pin that only said <span class="mono">observed_at is not None</span> would have stayed green through a
faithful restoration of the defect it was written near. The tamper was reverted and the suite re-run green
at 1,294.</div>

<h3>10 &middot; F-23 &mdash; the run that was to prove the fix, and the blind spot it exposed<span class="tag">NEW &middot; found and closed here &middot; docs/15 &sect;11.7</span></h3>
<p>Run <span class="mono">45963867416</span> (<span class="mono">venue-verification</span>,
<span class="mono">push</span>, at <span class="mono">8cdc871</span>) failed with one cause repeated
thirteen times.</p>
{verbatim("CAPTURED — the annotation, verbatim, with the two checks that survived and why", FAILED_RUN_DETAIL, "before")}
<p>Stage 8.4 grew <span class="mono">Transport</span> to five methods and moved every adapter. There were
<b>four</b> implementations in the repository and <b>three</b> were moved. The fourth was
<span class="mono">_CapturingTransport</span> in
<span class="mono">tests/test_live_endpoints.py</span> &mdash; a wrapper around a real
<span class="mono">HttpTransport</span> that saves every response to disk, because those captures are the
durable prize of a live run and the offline suite has never had a real payload.</p>
<div class="blocked"><b>The finding is not the omission. It is that nothing offline could have caught
it.</b> That module skips at import unless <span class="mono">NEXUS_LIVE_VERIFY=1</span>, so in this sandbox
the class is never constructed and no test among 1,290 touches it. It is the blind spot
<span class="mono">test_repo_hygiene.py</span> was written for, reached from the other side: that file
exists because a <span class="mono">.gitignore</span> pattern hid six modules from a pushed commit and a
suite running against the <i>working tree</i> could not see it. This is a defect invisible to a suite that
can only exercise what it can <i>reach</i>. <span class="mono">8cdc871</span>&rsquo;s own
<span class="mono">ci</span> runs were both <span class="mono">success</span> &mdash; <b>1,290 offline tests
green on a commit whose live run was red</b>, which is the blind spot stated as a pair of conclusions.</div>
<p><b>Which thirteen failed is itself evidence for &sect;3&rsquo;s split.</b> All five Bybit checks, all six
OKX checks, the Binance Vision kline parse and Dukascopy&rsquo;s tick-band check &mdash; every path that
fetches through an adapter. What passed: the URL-shape checks, which call
<span class="mono">transport.get_bytes(url)</span> directly, and
<span class="mono">verify_layout_passes_against_a_real_file</span>, which does the same and hands the bytes
to a pure function. <b>The receipt-less pair worked; the receipt-returning pair did not exist on the
wrapper.</b> The run was therefore not uniformly red, and a summary reading
<span class="mono">43 passed / 13 failed</span> could be mistaken for partial geo-blocking &mdash; which is
why the annotation names each failure&rsquo;s exception.</p>
<div class="blocked"><b>A correction to <span class="mono">bbfe95f</span>&rsquo;s own commit message,
disclosed rather than left standing.</b> That message said Dukascopy&rsquo;s checks passed because they go
through <span class="mono">get_bytes</span>/<span class="mono">verify_layout</span>. Read against the full
annotation that is <b>wrong</b>: <span class="mono">DukascopyLiveLayout.parsed_ticks_are_in_the_price_band</span>
<b>failed</b>, because it goes through <span class="mono">fetch_hour</span> and therefore
<span class="mono">fetch_bytes</span>. Only <span class="mono">verify_layout_passes_against_a_real_file</span>
passed, for the reason given. The claim was written from the first 3,000 characters of the annotation, which
is where that one <span class="mono">PASS</span> line appears and where the <span class="mono">FAIL</span>
does not.</div>
<p><b>The fix is a gate, not only the two methods.</b>
<span class="mono">TestTransportImplementationsAreComplete</span> scans <span class="mono">src/</span> and
<span class="mono">tests/</span> <b>by AST</b> for any class defining one of the four data methods and
requires all five, naming file and line. Scanning rather than importing is the only way to gate a module
that cannot run here. A companion test asserts the scan finds <b>exactly four</b> implementations &mdash;
<span class="mono">Transport</span>, <span class="mono">HttpTransport</span>,
<span class="mono">RecordingTransport</span>, <span class="mono">_CapturingTransport</span> &mdash; because a
scan that silently finds nothing passes forever. A third asserts the wrapper still <b>delegates</b>: a
wrapper that grew its own <span class="mono">httpx</span> client would capture payloads from a different
code path than the one under test, and the captures would stop being evidence about the adapters&rsquo;
transport.</p>
{verbatim("CAPTURED — the scan under tamper: fetch_json renamed away in the wrapper", TAMPER_HYGIENE, "before")}
<p class="cap">Offline, in the ordinary CI job, naming the file and the line. Restoring the method makes it
pass. <span class="mono">test_repo_hygiene.py</span> 84 &rarr; <b>88</b>.</p>

<h3>11 &middot; The live harness measures the skew inside one record now<span class="tag">docs/15 &sect;11.8</span></h3>
<p>Before this batch the skew series was <b>inferred</b>: an interval read from venue stamps, compared
against an interval read from a wall clock, across two runs. The harness now publishes both directly, and
adds the measurement F-14 said did not exist anywhere in the system &mdash; the distance between the two
clocks <b>inside a single record</b>.</p>
<div class="card">{key_table()}</div>
<div class="blocked"><b>The rename is the honest part, and the part most likely to be misread later.</b>
<span class="mono">dt_observed_s</span> measured the venue&rsquo;s interval before 8.4 and measures ours
after it, so the published series <b>changed meaning at <span class="mono">8cdc871</span> without changing
its key</b>. That is stated in the function&rsquo;s docstring rather than left to be discovered by diffing
two annotations, and the offline pins carry both the old literals and the new keys so the arithmetic that
produced &sect;10.8&rsquo;s table is still checkable.</div>

<h3>12 &middot; Before and after: the two runs ruling 2 asked for, and the third that arrived unasked<span class="tag">docs/15 &sect;11.9</span></h3>
<p>A correction to how this record has counted runs, found by reading
<span class="mono">.github/workflows/venue-verification.yml</span> rather than by inferring it from a run
list: that workflow&rsquo;s <span class="mono">push</span> and <span class="mono">pull_request</span>
triggers are <b>path-filtered</b> to <span class="mono">ingestion/**</span>,
<span class="mono">data/records.py</span>, <span class="mono">test_live_endpoints.py</span> and itself
&mdash; but the two filters are evaluated over <b>different scopes</b>, and that is the half this record had
not stated. <span class="mono">push</span> is filtered against the pushed commit;
<span class="mono">pull_request</span> is filtered against the <b>pull request&rsquo;s whole diff versus the
base branch</b>, which this PR has matched since Stage 7.1 built the adapters. So a commit produces
<b>four</b> runs when it touches an adapter or the harness and <b>three</b> when it does not &mdash;
<b>never two</b>. Verified against the run list rather than reasoned about: of the 30 most recent commits
that produced runs, <b>all 30</b> have a <span class="mono">venue-verification</span> /
<span class="mono">pull_request</span> run, and only the nine that touched a filtered path have the fourth.
&sect;10.8&rsquo;s &ldquo;<span class="mono">ffc4128</span> triggered three runs&rdquo; and
&sect;10.11&rsquo;s &ldquo;<span class="mono">8482179</span> produced three runs&rdquo; are both correct and
neither says why, or which of the three contacted the world. <b>A run count is a property of what changed,
not a constant</b> &mdash; the same lesson &sect;10.8 drew about a count that re-triggers per push, applied
to the count of runs themselves, and now with the mechanism and not only the observation.</p>
<div class="blocked"><b>The consequence, stated plainly: a documents-only push spends a live run against
four public venues, and can fail on their drift.</b> That is not a hypothetical &mdash; it is how run C
below exists. <span class="mono">ec0dd09</span> is the commit that carried this batch&rsquo;s record, it
changes documents and design files only, and it still produced a
<span class="mono">venue-verification</span> run, because the PR&rsquo;s diff against
<span class="mono">main</span> contains every adapter. <span class="mono">git diff bbfe95f ec0dd09 --
backend/</span> is empty, so that run measured a backend tree <b>byte-identical</b> to the one runs A and B
measured, hours later instead of minutes later. It is quoted here as a <b>third reading of the same
code</b> and not as a fourth run of the batch: the batch is two commits, and ruling 2 asked for runs before
and after it, which runs A and B are.</div>
<div class="card">{runs_table()}</div>
<p class="cap">Runs A and B are the same commit through the same workflow, minutes apart, and are quoted
separately rather than averaged. Run B&rsquo;s <span class="mono">1 skipped</span> is <b>not attributable
from here</b>: its annotation truncates earlier than run A&rsquo;s (<span class="mono">5185</span> escaped
characters over the cap against <span class="mono">4372</span>) and the skip falls in the Dukascopy section
past it. Naming it would be a guess. Run C returned <span class="mono">0 skipped</span> and truncated by
<span class="mono">5123</span> &mdash; so the skip is not a property of the code either, and the three
summaries are <span class="mono">52/0/5/0</span>, <span class="mono">51/0/5/1</span> and
<span class="mono">52/0/5/0</span>. The cap is not a constant either: identical code produced 4,372 and
5,185 four minutes apart, because the escaped length depends on how many rows each check printed, which
depends on the market.</p>
{verbatim("BEFORE — run 45953629348, job 140354959639, at 975dc64 (captured before a line was changed)", LIVE_BEFORE_SUMMARY, "before")}
{verbatim("AFTER, run A — run 45964962991, job 140391348401, at bbfe95f", LIVE_AFTER_A_SUMMARY, "after")}
{verbatim("AFTER, run B — run 45964969570, job 140391370141, same commit, minutes later", LIVE_AFTER_B_SUMMARY, "after")}
{verbatim("AFTER, run C — run 45996139111, job 140495884665, at ec0dd09: documents only, backend tree identical to bbfe95f, hours later", LIVE_AFTER_C_SUMMARY, "after")}
<div class="card">{convergence_table()}</div>
<div class="blocked"><b>The convergence reproduces three times; the venue&rsquo;s own skew does not
reproduce at all.</b> Three runs against one backend tree put our interval at <b>0.48&times;</b>,
<b>0.48&times;</b> and <b>0.52&times;</b> the wall clock around the same two calls &mdash; two minutes apart
and then hours apart, each computed independently. Before the batch the same ratio was <b>3.25&times;</b>,
and the record could not say whose clock the disagreement belonged to. After it, ours is <i>shorter</i> than
the wall clock, by roughly the harness&rsquo;s own overhead between starting its timer and issuing the first
request &mdash; which is the direction that difference should point, and it points that way <b>three times
out of three</b>. Run C is what turns that from a coincidence of two into a property of the code:
0.48/0.48 could have been one quiet minute measured twice, and 0.52 hours later on an identical tree cannot.
The venue&rsquo;s reading moved by more than <b>5&times;</b> across the same three: <b>2.037&times;</b>,
then <b>0.673&times;</b> four minutes later &mdash; <b>below one</b> &mdash; then <b>3.604&times;</b> hours
after that. That is not a contradiction and it is the reason &sect;10.8 states this quantity as a range:
run 26&rsquo;s 0.80&times; was until run B the only published reading under one, and run C&rsquo;s
3.604&times; sits <i>inside</i> that range&rsquo;s 3.97&times; ceiling rather than beyond it. So the three
readings move the range&rsquo;s <b>floor</b> and leave its <b>ceiling</b> alone &mdash; exactly the asymmetry
question 2 in &sect;15 asks about. What the three runs agree on is not the value but that the value is now
<b>attributable</b>: <span class="mono">skew_venue_over_wall</span> says whose interval it is, which
<span class="mono">dt_observed_s</span> could not. And a quantity that swings 0.673&times;&ndash;3.604&times;
between runs of identical code is one no threshold may be set against &mdash; the same reason P-8&rsquo;s
recommendation at Stage 7.3 chose no tolerance.</div>
{verbatim("RUN A — okx.trades: fifty rows, one arrival instant, event times spanning 0.256 s", RUN_A_OKX_TRADES, "after")}
{verbatim("RUN A — okx.quotes: both clocks on one line, and the distance between them", RUN_A_OKX_QUOTES, "after")}
{verbatim("RUN A — okx.book", RUN_A_OKX_BOOK, "after")}
{verbatim("RUN A — okx.bars: a hundred one-minute candles spanning 1.65 h, one arrival instant", RUN_A_OKX_BARS, "after")}
{verbatim("RUN C — okx.trades: the same fifty-row shape, hours later, sides nearly mirrored against run B", RUN_C_OKX_TRADES, "after")}
{verbatim("RUN C — okx.quotes: receipt_lag_s=1.095, the largest receipt-minus-venue gap this record has published", RUN_C_OKX_QUOTES, "after")}
{verbatim("RUN C — binance-vision.bars: the same 1,440 bars of 2026-11-20, a third receipt instant, still distinct_receipt_times=1", RUN_C_VISION_BARS, "after")}
<p class="cap">The <span class="mono">receipt_lag_*</span> numbers are the measurement F-14 said did not
exist. In run A OKX stamped the ticker <b>0.436 s</b> before we received it and the book <b>0.053 s</b>
before; in run B, <b>0.153 s</b> and <b>0.086 s</b>; in run C, <b>0.989 s</b> and <b>0.062 s</b>. The quote
lag exceeds the book lag in <b>all three</b>, by 8&times;, 1.8&times; and 16&times; &mdash; which is the
ticker endpoint updating less often than the book endpoint, the <i>conclusion</i> run 25 reached indirectly
in <span class="mono">docs/14</span> &sect;4.1, now readable off one row of one annotation instead of
inferred by comparing two runs, and reproduced twice more at gaps from 0.053 s to 0.989 s. Run C&rsquo;s
0.989 s is the largest receipt-minus-venue gap published anywhere in this record and the only one near a
second, which is a further reason limitation 5 insists the number is not latency: it is the venue&rsquo;s
stamp against our clock, and the two are not synchronised.</p>
<div class="blocked"><b>Run A had <span class="mono">buy=1 sell=49</span>; run B had
<span class="mono">buy=50 sell=0</span>; run C had <span class="mono">buy=2 sell=48</span>.</b> Same
endpoint, one backend tree, three readings ranging from entirely one-sided to 48/2. None is a failure, by
P-7&rsquo;s ruling at Stage 7.3, and the triple is the strongest vindication of it this record has: a
threshold on side balance chosen anywhere between 50/0 and 48/2 would have failed at least one of the three
on identical code. The before run had <span class="mono">buy=48 sell=2</span>, so run C lands within one
trade of the pre-batch reading while run B is its exact mirror. The distribution is recorded as
<b>counts</b> rather than as the set of sides that happened to appear precisely so this comparison is
possible &mdash; <span class="mono">sides=['BUY']</span> is identical for a 50/0 minute and a 25/25 one, and
run B published exactly that.</div>

<h3>13 &middot; The gate<span class="tag">docs/15 &sect;11.11</span></h3>
<div class="card">{gate_table()}</div>
<p class="cap">Both skips are pre-existing: <span class="mono">test_live_endpoints.py</span> (egress) and
<span class="mono">test_archive_bars.py</span> (7m not modelled). Net new test functions are <b>43</b>, of
which <b>35</b> are collected offline and <b>8</b> belong to the live module &mdash; which is why the
offline count moved by 35 and the live run&rsquo;s denominator by 8. The LOC figures are counted per
revision from git, not from the working tree, because a figure quoted for a commit has to be the figure that
commit contains; counted that way <span class="mono">975dc64</span>&rsquo;s test tree is 16,214 lines, and
the 16,074 carried forward in this record&rsquo;s working notes was measured against a working tree and was
140 lines low.</p>
<div class="card">{newtests_table()}</div>
<p><b>All four runs at <span class="mono">bbfe95f</span> are <span class="mono">success</span></b>, read job
by job rather than from the run list: <span class="mono">ci</span> push
<span class="mono">45964962941</span> and pull_request <span class="mono">45964969608</span>, each with all
five jobs green including <span class="mono">Container image (amd64 + arm64 build)</span> and
<span class="mono">Runtime smoke test (container actually serves)</span>; and
<span class="mono">venue-verification</span> push <span class="mono">45964962991</span> and pull_request
<span class="mono">45964969570</span>. The image scan&rsquo;s annotation is unchanged from
&sect;10.11&rsquo;s, verbatim, in both <span class="mono">ci</span> runs &mdash;
<span class="mono">notice: no HIGH or CRITICAL fixable vulnerabilities in nexus-core%3Aci</span> &mdash; so
this batch did not disturb the posture O-011&rsquo;s recurrence resolved.</p>
<p><b><span class="mono">ec0dd09</span>, the commit carrying this board, produced three runs</b> &mdash;
<span class="mono">ci</span> push <span class="mono">45996129637</span>, <span class="mono">ci</span>
pull_request <span class="mono">45996139001</span> and <span class="mono">venue-verification</span>
pull_request <span class="mono">45996139111</span> &mdash; and the third is run C in &sect;12. It changed
documents and design files only, so it is &sect;12&rsquo;s mechanism demonstrated on the commit that
describes it. &sect;10.11&rsquo;s warning was that such a push can go red on base-image drift; this one did
not, and its <span class="mono">ci</span> image annotation is the same sentence quoted above.</p>
<p><b>Finding ids consumed: F-23</b> (&sect;10, closed in the batch that found it). <b>The next finding id
remains F-24.</b></p>

<h3>14 &middot; Limitations of this batch<span class="tag">docs/15 &sect;11.12</span></h3>
<div class="card">{limitations_table()}</div>

<h3>15 &middot; Decision requested<span class="tag">four questions, one marked recommendation each</span></h3>
<p>All four are answered on this board rather than in prose, because two of them change what a published
number means and one changes what the next batch is. <b>All four were answered
<span class="ok">Recommend</span></b>, each against exactly one marked recommendation, and are recorded as
<b>D-053</b> in &sect;16. This section is left exactly as it was put.</p>
<div class="card">{questions_table()}</div>

<h3>16 &middot; D-053 &mdash; the four rulings<span class="tag">docs/15 &sect;11.14</span></h3>
<div class="card">{rulings_table()}</div>
<p class="cap"><b>Finding ids.</b> F-14 <span class="ok">CLOSED</span> (delivered by 8.4, approved by D-053).
F-23 <span class="ok">CLOSED</span> (found and closed in the same batch, disclosed in the ruling that
approves it). <span class="mono">O-012</span> <span class="ok">CLOSED</span>.
<span class="mono">O-014</span>/F-22 stays <span class="no">OPEN</span>. <b>The next finding id is
F-24.</b></p>
<div class="card">{not_done_by_ruling_table()}</div>
<div class="blocked"><b>The regress &sect;10.8 predicted arrived at once.</b> <span class="mono">8d3973d</span>
&mdash; the commit carrying &sect;3&rsquo;s and &sect;12&rsquo;s corrections, documents and design files only
&mdash; triggered its own <span class="mono">Live public endpoints</span> run,
<span class="mono">45998848348</span>, <span class="ok">conclusion=success</span>, against a backend tree
byte-identical to <span class="mono">bbfe95f</span>&rsquo;s. Its numbers are <b>not read here</b>, by
&sect;10.8&rsquo;s rule and by the precedent that section set for runs 32 and 33: reading them would need
another commit, which triggers another run, whose numbers would be unread for the same reason. The commit
carrying <i>this</i> section does the same thing again. So the property is stated instead of the count:
<b>every push to this PR produces another live reading of the same adapter code until an adapter changes</b>
&mdash; &sect;12&rsquo;s mechanism seen from the other end, and the reason pair 11 in &sect;10.8&rsquo;s
restatement is the last one this record will number.</div>

<footer>Stage 8.4 &middot; F-14&rsquo;s expensive half &middot; authorised by D-052&rsquo;s ruling 2,
<b>approved 2026-11-27 as D-053</b> &middot; <b>F-14, F-23 and O-012 all CLOSED</b>, F-22 untouched, next
finding id <b>F-24</b> &middot; the skew series continues under its renamed key with &sect;10.8&rsquo;s range
restated to <b>0.673&times;&ndash;3.97&times;</b> across eleven pairs by an inserted pointer rather than a
rewrite, the <b>floor</b> moving and the ceiling not &middot; the AST scan stays and the wrapper does not
move &middot; next: stage 10&rsquo;s <span class="mono">memory_item</span> writer, re-ordered by ruling 4
&middot; <span class="mono">8cdc871</span> (22 files, +1,901 / &minus;144) +
<span class="mono">bbfe95f</span> (2 files, +134 / &minus;6) &middot; gate <b>1,294 passed / 2 skipped / 0
failed</b> (+35 offline, +8 live checks, +43 test functions), mypy strict clean on <b>61</b>, ruff and
format clean on <b>91</b>, hygiene <b>88</b> &middot; <span class="mono">Transport</span> three methods
&rarr; <b>five</b>, the stamp taken <b>before</b> body decode &middot; four adapters, <b>ten</b>
record-construction sites, and <b>five</b> places that ordered, bucketed or partitioned on the receipt clock
moved off it &middot; the archive&rsquo;s partition key was the one that would have been <b>silent</b>, and
is measured instead: 1,440 bars spanning 23.98 h of 2026-11-20, received 2026-11-27,
<span class="mono">distinct_receipt_times=1</span> &middot; <b>no new gate</b>: two venue numbers published
and neither gates anything, swept across five values to prove it &middot; <b>nothing wired</b>:
<span class="mono">evidence_ref.retrieved_at</span> still has no caller, by ruling &middot; one
<span class="mono">view_gap</span> changed kind and the route says so &middot; the gate proven load-bearing
by reverting all ten sites: <b>15 failures</b>, twelve in the gate and three in the strengthened pins
&middot; <b>F-23 found and closed</b>: run <span class="mono">45963867416</span> failed 13 of 57 on one
<span class="mono">AttributeError</span> because the fourth <span class="mono">Transport</span>
implementation lives in a module the offline suite skips at import, now gated by an AST scan proven by
tamper &middot; <b>four published numbers corrected as carried</b> rather than rewritten: the tamper count
(eight &rarr; fifteen) and the Dukascopy claim (one check passed, not all of them), both in pushed commit
messages, plus the LZMA ratio (2.5&times; &rarr; <b>3.94&times;</b> and <b>4.34&times;</b>, the two hours
this record actually measured) and the run-count mechanism, both in the record commit
<span class="mono">ec0dd09</span> &middot; the convergence ruling 2 asked for, <b>reproduced three times on
one backend tree</b>: <span class="mono">dt_observed_s / dt_wall_s</span> from <b>3.25&times;</b> to
<b>0.48&times;</b>, <b>0.48&times;</b> and <b>0.52&times;</b>, the third hours later at
<span class="mono">ec0dd09</span> whose <span class="mono">backend/</span> is byte-identical to
<span class="mono">bbfe95f</span>&rsquo;s &middot; the venue&rsquo;s own skew separable at
<b>2.037&times;</b>, <b>0.673&times;</b> and <b>3.604&times;</b> &mdash; a <b>5.4&times;</b> spread on
identical code, the second below &sect;10.8&rsquo;s published 0.80&times; floor and the third inside its
3.97&times; ceiling, so the floor and not the ceiling is what question 2 asks about &middot;
<span class="mono">receipt_lag_*</span> measures receipt-minus-venue inside one record for the first time
anywhere in the system, and reproduces <span class="mono">docs/14</span> &sect;4.1&rsquo;s run-25 conclusion
off a single row <b>three times</b>, at gaps from 0.053 s to 0.989 s &middot; trade sides
<span class="mono">48/2</span>, <span class="mono">1/49</span>, <b><span class="mono">50/0</span></b> and
<span class="mono">2/48</span> across four runs &mdash; the last three on one backend tree &mdash; so any
side-balance threshold in that span would have failed one of them &mdash; P-7 vindicated &middot; a run count is a property of what changed:
<b>four</b> runs for an adapter commit, <b>three</b> for a documents-only one and <b>never two</b>, because
<span class="mono">push</span> is filtered per commit while <span class="mono">pull_request</span> is
filtered against the whole PR diff &mdash; verified across the 30 most recent commits with runs, all 30 of
which spent a live run &middot; <b>O-012 delivered, closure requested</b> &middot; F-22 untouched &middot;
next: stage 10&rsquo;s <span class="mono">memory_item</span> writer, as ruling 3 ordered</footer>
</div></body></html>"""
    out = HERE / "stage8-4-two-clocks-kept-apart.html"
    out.write_text(html_out)
    return out


if __name__ == "__main__":
    path = main()
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
