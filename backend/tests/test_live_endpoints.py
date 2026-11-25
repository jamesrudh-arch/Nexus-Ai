"""Live verification of the four free public feeds — O-009 and O-010.

Why this file exists
--------------------
Every adapter test in this repository runs against a ``RecordingTransport`` holding synthetic
responses written from published API contracts. That proves the normalisation logic is internally
consistent and proves nothing about the world: it cannot notice that a venue renamed a field,
changed a divisor, started returning strings where it returned numbers, or that a URL shape was
misread. For Dukascopy the gap is wider — the bi5 binary layout was implemented from documentation
alone and ``LAYOUT_VERIFIED`` is ``False`` because no real file has ever been downloaded.

This module closes that gap by running the **real adapters** against the **real endpoints** over a
real ``HttpTransport``. It is not part of the ordinary suite: it needs network egress, which the
development sandbox does not have, and a test that cannot run is worse than one that is clearly
labelled as gated. Set ``NEXUS_LIVE_VERIFY=1`` on a host with egress; the CI workflow
``venue-verification.yml`` does exactly that.

The rule that governs every test here
-------------------------------------
A source that does not answer is **not** a defect in this repository, and an adapter that
mis-normalises a live response **is**. The two must not be reported the same way, or either an
upstream outage or a real breakage would look like the other. So:

* DNS failure, connect refusal, timeout, TLS error, HTTP 429 or 5xx → ``pytest.skip``, with the
  reason recorded. Nothing is verified either way and the report says so.
* Anything else — a 4xx (which means *our* URL or parameters are wrong), a missing field, a
  conversion failure, an invariant violation → the test fails.

That asymmetry is deliberate and narrow. A 404 from Dukascopy is the single most interesting result
this module can produce, because it means the 0-indexed-month URL shape is wrong; treating it as
"unavailable" would hide exactly the finding O-010 exists to make.

No credentials are used or needed. Every endpoint here is public (D-026), and the workflow that
runs this has no secrets in its environment.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from nexus.data.records import (
    BackoffPolicy,
    HttpTransport,
    IngestFault,
    TokenBucket,
)
from nexus.ingestion.binance_vision import SOURCE as BINANCE_VISION_SOURCE
from nexus.ingestion.binance_vision import BinanceVisionHistorical, kline_url
from nexus.ingestion.bybit import SOURCE as BYBIT_SOURCE
from nexus.ingestion.bybit import BybitPublicAdapter
from nexus.ingestion.dukascopy import (
    DUKASCOPY_BASE,
    LAYOUT_VERIFIED,
    SOURCE_UNVERIFIED,
    SOURCE_VERIFIED,
    DukascopyHistorical,
    hour_url,
    verify_layout,
)
from nexus.ingestion.okx import SOURCE as OKX_SOURCE
from nexus.ingestion.okx import OkxPublicAdapter

pytestmark = pytest.mark.live

if os.environ.get("NEXUS_LIVE_VERIFY", "") != "1":
    pytest.skip(
        "live endpoint verification needs network egress; set NEXUS_LIVE_VERIFY=1 on a host that "
        "has it (the venue-verification workflow does). Nothing here is verified by skipping.",
        allow_module_level=True,
    )

# --------------------------------------------------------------------- symbols under test
# One instrument per venue, chosen because it is the most liquid listing on both and therefore the
# least likely to be delisted, suspended or thinly quoted enough to produce an empty book.
BYBIT_SYMBOL = "BTCUSDT"
OKX_INST_ID = "BTC-USDT-SWAP"
BINANCE_SYMBOL = "BTCUSDT"
DUKASCOPY_PAIR = "EURUSD"

#: Plausible band for EURUSD. A parsed price outside it means the point divisor is wrong, which is
#: the catastrophic-and-silent failure the parser refuses to guess about: 100000 vs 1000 is 100x.
EURUSD_BAND = (Decimal("0.5"), Decimal("2.5"))


# --------------------------------------------------------------------- unavailable vs defect
def _classify(exc: BaseException) -> str:
    """``"unavailable"`` when the source did not answer; ``"defect"`` for anything else.

    Deliberately narrow. ``HttpTransport`` wraps network-level errors as
    ``IngestFault("<url> failed: <repr>")`` once its retries are exhausted, and reports HTTP status
    as ``"<url> returned HTTP <code>"``; those two shapes are the only things treated as the
    source's problem.
    """
    if not isinstance(exc, IngestFault):
        return "defect"
    text = str(exc)
    if " failed: " in text:  # DNS, connect, read timeout, TLS — the host never answered
        return "unavailable"
    match = re.search(r"returned HTTP (\d{3})", text)
    if match is not None:
        status = int(match.group(1))
        if status == 429 or status >= 500:  # rate-limited or the venue is down
            return "unavailable"
    return "defect"


@contextmanager
def _live(source: str) -> Iterator[None]:
    """Turn an unreachable source into a skip, and leave every other failure alone."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - classified below, re-raised unless unavailable
        if _classify(exc) == "unavailable":
            pytest.skip(f"{source} did not answer, so nothing is verified either way: {exc!r}")
        raise


def _evidence(label: str, **fields: Any) -> None:
    """Print one machine-readable line.

    The verification workflow collects these from the JUnit XML and republishes them as a check
    annotation, because job logs are served from a host outside the sandbox's egress allowlist.
    Without this the run would be a green or red mark with no content, and the measurements are the
    whole point: they are the evidence that closes O-009 and O-010.
    """
    rendered = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"EVIDENCE {label} {rendered}")


def _recent_weekday_hour(*, hour: int = 12) -> datetime:
    """An hour when the FX market was certainly open: Tue/Wed/Thu, at least two days back."""
    now = datetime.now(UTC)
    for days_back in range(2, 15):
        candidate = (now - timedelta(days=days_back)).replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate.weekday() in (1, 2, 3):
            return candidate
    raise AssertionError("could not select a recent mid-week hour")  # pragma: no cover - calendar


def _recent_dump_day(*, days_back: int = 7) -> datetime:
    """A day whose Binance Vision dump has certainly been published (they lag by hours)."""
    now = datetime.now(UTC)
    return (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------- transport
class _CapturingTransport:
    """A real transport that also writes every response to disk.

    The captures are the durable prize here: they are real payloads, which is what the offline
    suite has never had. Committing a trimmed set would let every adapter test run against shapes
    that actually occurred, instead of shapes inferred from documentation.
    """

    def __init__(self, inner: HttpTransport, directory: Path | None) -> None:
        self._inner = inner
        self._dir = directory
        self._count = 0
        self.saved: list[str] = []

    def _save(self, url: str, params: dict[str, Any] | None, body: bytes) -> None:
        if self._dir is None:
            return
        self._count += 1
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[-1])[:120]
        query = ""
        if params:
            query = "_" + re.sub(r"[^A-Za-z0-9._-]+", "_", json.dumps(params, sort_keys=True))[:60]
        suffix = ".json" if body.lstrip()[:1] in (b"{", b"[") else ".bin"
        path = self._dir / f"{self._count:03d}_{slug}{query}{suffix}"
        path.write_bytes(body)
        self.saved.append(path.name)

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        result = await self._inner.get_json(url, params=params)
        self._save(url, params, json.dumps(result).encode("utf-8"))
        return result

    async def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        result = await self._inner.get_bytes(url, params=params)
        self._save(url, params, result)
        return result

    @property
    def calls(self) -> int:
        return self._inner.calls

    async def aclose(self) -> None:
        await self._inner.aclose()


@pytest.fixture
async def transport() -> Any:
    """One real transport for the whole module, rate-limited to be a polite free-tier guest.

    The budget is tighter than the adapters' own defaults: this run makes about twenty requests
    against services that are free, unauthenticated and shared, and being throttled would produce
    skips that look like findings.
    """
    configured = os.environ.get("NEXUS_LIVE_FIXTURE_DIR", "").strip()
    directory = Path(configured) if configured else None
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
    inner = HttpTransport(
        timeout_seconds=20.0,
        limiter=TokenBucket(rate_per_second=2.0, burst=4),
        backoff=BackoffPolicy(base_seconds=1.0, max_seconds=20.0, max_attempts=3),
    )
    capturing = _CapturingTransport(inner, directory)
    try:
        yield capturing
    finally:
        await capturing.aclose()
        _evidence("capture", saved=len(capturing.saved), calls=capturing.calls, dir=str(directory or "-"))


# --------------------------------------------------------------------- shared invariants
def _assert_aware(value: datetime | None, what: str) -> None:
    assert value is not None, f"{what} is missing"
    assert value.tzinfo is not None, f"{what} is naive; every timestamp in this system is aware UTC"


def _assert_bars(bars: tuple[Any, ...], *, interval: str, source: str, label: str) -> None:
    assert bars, f"{label}: no bars came back, so nothing about the live shape is verified"
    times = [bar.open_time for bar in bars]
    for bar in bars:
        _assert_aware(bar.open_time, f"{label}: open_time")
        assert bar.interval == interval, f"{label}: interval {bar.interval!r} != requested {interval!r}"
        assert bar.source == source, f"{label}: source {bar.source!r} != {source!r}"
        assert bar.high >= bar.low, f"{label}: high {bar.high} below low {bar.low}"
        assert bar.high >= max(bar.open, bar.close), f"{label}: high {bar.high} below the body"
        assert bar.low <= min(bar.open, bar.close), f"{label}: low {bar.low} above the body"
        assert bar.volume is None or bar.volume >= 0, f"{label}: negative volume {bar.volume}"
    assert times == sorted(times), f"{label}: bars are not ordered by open_time"
    assert len(set(times)) == len(times), f"{label}: duplicate open_time values — bars would collide"

    prices = [bar.close for bar in bars]
    _evidence(
        f"{label}.bars",
        count=len(bars),
        interval=interval,
        span_hours=round((times[-1] - times[0]).total_seconds() / 3600, 2),
        close_min=min(prices),
        close_max=max(prices),
        first=times[0].isoformat(),
        last=times[-1].isoformat(),
    )


def _assert_quotes(quotes: tuple[Any, ...], *, source: str, label: str) -> None:
    assert quotes, f"{label}: no quotes came back"
    for quote in quotes:
        _assert_aware(quote.observed_at, f"{label}: observed_at")
        assert quote.source == source, f"{label}: source {quote.source!r} != {source!r}"
        assert quote.bid is not None and quote.ask is not None, f"{label}: one-sided quote"
        assert quote.bid > 0 and quote.ask > 0, f"{label}: non-positive price"
        # A crossed book from a public top-of-book feed is either a parse error or a stale
        # timestamp, and both matter: sizing uses the distance to the stop, not the mid.
        assert quote.bid <= quote.ask, f"{label}: crossed book bid={quote.bid} ask={quote.ask}"
    _evidence(
        f"{label}.quotes",
        count=len(quotes),
        bid=quotes[0].bid,
        ask=quotes[0].ask,
        spread_bps=round((quotes[0].ask - quotes[0].bid) / quotes[0].bid * 10_000, 3),
        observed_at=quotes[0].observed_at.isoformat(),
    )


def _assert_ticks(ticks: tuple[Any, ...], *, source: str, label: str) -> None:
    assert ticks, f"{label}: no trades came back"
    for tick in ticks:
        _assert_aware(tick.observed_at, f"{label}: observed_at")
        assert tick.source == source, f"{label}: source {tick.source!r} != {source!r}"
        assert tick.price > 0, f"{label}: non-positive price {tick.price}"
        assert tick.quantity is None or tick.quantity > 0, f"{label}: non-positive quantity"
        assert tick.side in (None, "BUY", "SELL"), f"{label}: side {tick.side!r} outside the vocabulary"
        if tick.venue_timestamp is not None:
            _assert_aware(tick.venue_timestamp, f"{label}: venue_timestamp")
    prices = [tick.price for tick in ticks]
    _evidence(
        f"{label}.trades",
        count=len(ticks),
        price_min=min(prices),
        price_max=max(prices),
        sides=sorted({str(tick.side) for tick in ticks}),
        newest=max(tick.observed_at for tick in ticks).isoformat(),
    )


def _assert_book(book: Any, *, source: str, label: str) -> None:
    assert book is not None, f"{label}: no book came back"
    assert book.bids and book.asks, f"{label}: one-sided book"
    bid_prices = [level.price for level in book.bids]
    ask_prices = [level.price for level in book.asks]
    assert bid_prices == sorted(bid_prices, reverse=True), f"{label}: bids are not descending"
    assert ask_prices == sorted(ask_prices), f"{label}: asks are not ascending"
    assert bid_prices[0] <= ask_prices[0], (
        f"{label}: crossed book, best bid {bid_prices[0]} above best ask {ask_prices[0]}"
    )
    for level in (*book.bids, *book.asks):
        assert level.price > 0 and level.quantity > 0, f"{label}: non-positive level"
    _assert_aware(book.observed_at, f"{label}: observed_at")
    assert book.source == source, f"{label}: source {book.source!r} != {source!r}"
    _evidence(
        f"{label}.book",
        depth=len(book.bids) + len(book.asks),
        best_bid=bid_prices[0],
        best_ask=ask_prices[0],
        spread_bps=round((ask_prices[0] - bid_prices[0]) / bid_prices[0] * 10_000, 3),
        entitlement=book.entitlement,
    )


def _assert_instruments(records: tuple[Any, ...], *, label: str, wanted: str) -> None:
    assert records, f"{label}: no instruments came back"
    by_symbol = {record.venue_symbol: record for record in records}
    assert wanted in by_symbol, (
        f"{label}: {wanted} is not in {len(records)} live instruments, so the venue mapping the "
        f"registry holds for it is stale — found e.g. {sorted(by_symbol)[:6]}"
    )
    target = by_symbol[wanted]
    assert target.raw, f"{label}: the raw venue payload was not retained as evidence"
    if target.contract_size is not None:
        assert target.contract_size > 0, f"{label}: non-positive contract size {target.contract_size}"
    if target.tick_size is not None:
        assert target.tick_size > 0, f"{label}: non-positive tick size {target.tick_size}"
    _evidence(
        f"{label}.instruments",
        count=len(records),
        symbol=wanted,
        contract_size=str(target.contract_size),
        tick_size=str(target.tick_size),
        min_qty=str(target.min_order_qty),
        qty_step=str(target.qty_step),
        status=str(target.status),
        raw_fields=len(target.raw),
    )


# --------------------------------------------------------------------- Bybit
class TestBybitLiveEndpoints:
    """O-009 for Bybit: the public V5 REST endpoints, exactly as the adapter calls them."""

    async def test_instrument_info_matches_the_live_listing(self, transport: Any) -> None:
        adapter = BybitPublicAdapter(transport=transport)
        with _live("bybit"):
            records = await adapter.instrument_info()
        _assert_instruments(records, label="bybit", wanted=BYBIT_SYMBOL)

    async def test_quotes_are_uncrossed_and_current(self, transport: Any) -> None:
        adapter = BybitPublicAdapter(transport=transport)
        with _live("bybit"):
            quotes = await adapter.quotes([BYBIT_SYMBOL])
        _assert_quotes(quotes, source=BYBIT_SOURCE, label="bybit")

    async def test_public_trades_normalise(self, transport: Any) -> None:
        adapter = BybitPublicAdapter(transport=transport)
        with _live("bybit"):
            ticks = await adapter.trades(BYBIT_SYMBOL, limit=50)
        _assert_ticks(ticks, source=BYBIT_SOURCE, label="bybit")

    async def test_klines_are_ordered_and_self_consistent(self, transport: Any) -> None:
        adapter = BybitPublicAdapter(transport=transport)
        # Bybit's `bars` takes the venue's own interval vocabulary ("1" for one minute), while
        # OKX's takes "1m" — the two adapters do not share one, and the records that come back
        # carry the canonical name either way. Asking Bybit for "1m" is refused before any HTTP
        # call is made, which is the correct behaviour and the wrong thing for this test to do.
        with _live("bybit"):
            bars = await adapter.bars(BYBIT_SYMBOL, interval="1", limit=100)
        _assert_bars(bars, interval="1m", source=BYBIT_SOURCE, label="bybit")

    async def test_order_book_is_ordered_and_uncrossed(self, transport: Any) -> None:
        adapter = BybitPublicAdapter(transport=transport)
        with _live("bybit"):
            book = await adapter.book(BYBIT_SYMBOL, depth=20)
        _assert_book(book, source=BYBIT_SOURCE, label="bybit")


# --------------------------------------------------------------------- OKX
class TestOkxLiveEndpoints:
    """O-009 for OKX: the public v5 endpoints, exactly as the adapter calls them."""

    async def test_instrument_info_matches_the_live_listing(self, transport: Any) -> None:
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            records = await adapter.instrument_info([OKX_INST_ID])
        _assert_instruments(records, label="okx", wanted=OKX_INST_ID)

    async def test_tickers_are_uncrossed_and_current(self, transport: Any) -> None:
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            quotes = await adapter.quotes([OKX_INST_ID])
        _assert_quotes(quotes, source=OKX_SOURCE, label="okx")

    async def test_public_trades_normalise(self, transport: Any) -> None:
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            ticks = await adapter.trades(OKX_INST_ID, limit=50)
        _assert_ticks(ticks, source=OKX_SOURCE, label="okx")

    async def test_candles_are_ordered_and_self_consistent(self, transport: Any) -> None:
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            bars = await adapter.bars(OKX_INST_ID, interval="1m", limit=100)
        _assert_bars(bars, interval="1m", source=OKX_SOURCE, label="okx")

    async def test_order_book_is_ordered_and_uncrossed(self, transport: Any) -> None:
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            book = await adapter.book(OKX_INST_ID, depth=20)
        _assert_book(book, source=OKX_SOURCE, label="okx")


# --------------------------------------------------------------------- Binance Vision
class TestBinanceVisionLiveDumps:
    """O-009 for the bulk dumps: the URL shape first, then the CSV inside it."""

    async def test_the_dump_url_shape_is_correct(self, transport: Any) -> None:
        """Isolated from the parser: a 404 here means the URL shape is wrong, not the CSV."""
        day = _recent_dump_day()
        url = kline_url(BINANCE_SYMBOL, "1m", day, periodicity="daily")
        with _live("binance-vision"):
            payload = await transport.get_bytes(url)
        assert payload, f"the dump at {url} came back empty"
        # ZIP local file header. Binance Vision publishes zip-wrapped CSV; anything else means the
        # path resolved to something that is not the dump (an error page, a listing, a redirect).
        assert payload[:2] == b"PK", f"{url} did not return a ZIP archive (starts {payload[:8]!r})"
        _evidence("binance-vision.url", day=day.date().isoformat(), bytes=len(payload), zip=True)

    async def test_kline_dump_parses_into_consistent_bars(self, transport: Any) -> None:
        source = BinanceVisionHistorical(transport=transport)
        day = _recent_dump_day()
        # `missing_is_ok=False` is essential here, not a preference. With the default True the
        # adapter records a gap and returns empty bars, which absorbs the transport fault before
        # `_live` can classify it — so an unreachable host and a wrong URL both present as "no
        # data" and the test fails for the wrong reason. Verification needs the distinction the
        # backfill path deliberately does not: a dump seven days old certainly exists, so a 404
        # means the URL shape is wrong, and a connection failure means the source did not answer.
        with _live("binance-vision"):
            bars, results = await source.fetch_klines(BINANCE_SYMBOL, "1m", [day], missing_is_ok=False)
        _assert_bars(bars, interval="1m", source=BINANCE_VISION_SOURCE, label="binance-vision")

        assert len(results) == 1, f"expected one dump result, got {len(results)}"
        parsed = results[0]
        assert parsed.rows_read > 0, "the dump was read but contained no rows"
        assert parsed.records_rejected == 0, (
            f"the live dump produced {parsed.records_rejected} rejected rows "
            f"({parsed.rejection_reasons}) — the real CSV has columns or values the parser does not "
            f"accept, which is exactly what synthetic fixtures cannot reveal"
        )
        _evidence(
            "binance-vision.parse",
            rows=parsed.rows_read,
            accepted=parsed.records_accepted,
            rejected=parsed.records_rejected,
            had_header=parsed.had_header,
        )


# --------------------------------------------------------------------- Dukascopy
class TestDukascopyLiveLayout:
    """O-010: the bi5 layout, checked against a real download for the first time."""

    async def test_the_bi5_url_shape_is_correct(self, transport: Any) -> None:
        """The 0-indexed month is the trap; a 404 here is the finding, not an outage."""
        hour = _recent_weekday_hour()
        url = hour_url(DUKASCOPY_PAIR, hour)
        assert url.startswith(DUKASCOPY_BASE), f"unexpected base in {url}"
        with _live("dukascopy"):
            payload = await transport.get_bytes(url)
        assert payload, f"{url} came back empty"
        _evidence("dukascopy.url", hour=hour.isoformat(), bytes=len(payload), month_segment=url.split("/")[6])

    async def test_verify_layout_passes_against_a_real_file(self, transport: Any) -> None:
        """This is the evidence ``LAYOUT_VERIFIED`` requires: a real hour file, structurally sound."""
        hour = _recent_weekday_hour()
        url = hour_url(DUKASCOPY_PAIR, hour)
        with _live("dukascopy"):
            payload = await transport.get_bytes(url)

        result = verify_layout(payload)
        _evidence(
            "dukascopy.layout",
            passed=result.get("passed"),
            payload_bytes=result.get("payload_bytes"),
            decompressed_bytes=result.get("decompressed_bytes"),
            tick_count=result.get("tick_count"),
            reasons=";".join(str(r) for r in result.get("reasons") or []) or "-",
        )
        assert result["passed"], (
            f"the real bi5 file failed the layout check: {result['reasons']}. Either the layout "
            f"assumption (LZMA, 20 bytes per tick, big-endian) is wrong or the hour was empty — "
            f"and LAYOUT_VERIFIED must stay False until this passes."
        )
        assert result.get("tick_count", 0) > 0, "a real mid-week hour contained no ticks"

    async def test_parsed_ticks_are_in_the_right_price_band(self, transport: Any) -> None:
        """The divisor check: 100000 for EURUSD. Wrong by 100x is the catastrophic silent failure."""
        hour = _recent_weekday_hour()
        source = DukascopyHistorical(transport=transport)
        with _live("dukascopy"):
            parsed = await source.fetch_hour(DUKASCOPY_PAIR, hour)

        low, high = EURUSD_BAND
        assert parsed.ticks, f"no ticks parsed from {parsed.url}"
        prices = [tick.price for tick in parsed.ticks]
        assert all(low <= price <= high for price in prices), (
            f"EURUSD prices outside {low}–{high}: min={min(prices)} max={max(prices)}. The point "
            f"divisor is almost certainly wrong, and this is the error the parser exists to refuse."
        )
        expected_source = SOURCE_VERIFIED if LAYOUT_VERIFIED else SOURCE_UNVERIFIED
        assert all(tick.source == expected_source for tick in parsed.ticks), (
            "records are not labelled with the source their verification status implies"
        )
        assert parsed.layout_verified is LAYOUT_VERIFIED, "the parse report disagrees with the constant"
        _evidence(
            "dukascopy.ticks",
            count=len(parsed.ticks),
            price_min=min(prices),
            price_max=max(prices),
            raw_bytes=parsed.raw_bytes,
            decompressed_bytes=parsed.decompressed_bytes,
            source=expected_source,
            layout_verified=LAYOUT_VERIFIED,
        )
