"""Live verification of the four free public feeds — O-009 and O-010.

Why this file exists
--------------------
Every adapter test in this repository runs against a ``RecordingTransport`` holding synthetic
responses written from published API contracts. That proves the normalisation logic is internally
consistent and proves nothing about the world: it cannot notice that a venue renamed a field,
changed a divisor, started returning strings where it returned numbers, or that a URL shape was
misread. For Dukascopy the gap was wider still — the bi5 binary layout was implemented from
documentation alone, and ``LAYOUT_VERIFIED`` stayed ``False`` until this module downloaded a real
hour file and ``verify_layout`` passed against it (twelve consecutive CI runs on 2026-11-26,
``2026-11-24T12:00Z``; the flag is ``True`` now and cites that evidence — ``docs/14`` §1.4 F-1 and
§2.1, ``docs/00`` O-010).

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

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

import pytest

from nexus.data.records import (
    BackoffPolicy,
    BookLevel,
    BookRecord,
    HttpTransport,
    IngestFault,
    QuoteRecord,
    TickRecord,
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


T = TypeVar("T")


# --------------------------------------------------------------------- unavailable vs defect
def _classify(exc: BaseException) -> str:
    """``"unavailable"`` / ``"geo-blocked"`` when the source did not answer us; ``"defect"`` else.

    Deliberately narrow. ``HttpTransport`` wraps network-level errors as
    ``IngestFault("<url> failed: <repr>")`` once its retries are exhausted, and reports HTTP status
    as ``"<url> returned HTTP <code>"``; those two shapes are the only things treated as the
    source's problem rather than ours.

    A 403 is its own case, and the reasoning only holds because nothing here is authenticated —
    every adapter under test declares ``requires_credentials = False`` and the hygiene suite
    asserts this module mentions no credential-shaped string. So a 403 cannot mean "your key lacks
    permission"; it means the request was refused at the edge before reaching the API. Bybit
    geo-blocks the jurisdictions GitHub's hosted runners sit in and answers 403 from CloudFront on
    public endpoints, which is a property of *where this check runs*, not of the code it checks.
    Failing the build for it would leave a permanently red gate, and a permanently red gate is
    ignored.

    A 404 stays a defect. It means our request addressed nothing, which is precisely the failure
    live verification exists to catch: the bi5 URL carried an invented ``BID`` segment and the
    Binance Vision dumps were missing their ``daily``/``monthly`` segment (defects 38 and 39), and
    both presented as 404s.
    """
    if not isinstance(exc, IngestFault):
        return "defect"
    text = str(exc)
    if " failed: " in text:  # DNS, connect, read timeout, TLS — the host never answered
        return "unavailable"
    match = re.search(r"returned HTTP (\d{3})", text)
    if match is not None:
        status = int(match.group(1))
        if status == 403:
            return "geo-blocked"
        if status == 429 or status >= 500:  # rate-limited or the venue is down
            return "unavailable"
    return "defect"


@contextmanager
def _live(source: str) -> Iterator[None]:
    """Turn an unreachable source into a skip, and leave every other failure alone."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - classified below, re-raised unless unavailable
        verdict = _classify(exc)
        if verdict == "geo-blocked":
            pytest.skip(
                f"GEO-BLOCKED {source}: the runner's IP is restricted, so this endpoint answered "
                f"403 at the edge and nothing about it was verified: {exc!r}"
            )
        if verdict == "unavailable":
            pytest.skip(f"{source} did not answer, so nothing is verified either way: {exc!r}")
        raise


async def _with_patience(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str,
    attempts: int = 6,
    delay_seconds: float = 8.0,
    network_attempts: int = 2,
    network_delay_seconds: float = 2.0,
) -> T:
    """Retry a source that answers intermittently, with the attempts spaced apart.

    Dukascopy's datafeed throttles in bursts: in one run the *same* URL returned 25,761 bytes twice
    and HTTP 503 twice, and a probe with no retries at all succeeded where the shared transport's
    four retries failed. So 503 here is not "the host is down" and not "the host refuses us" — the
    diagnostic settled that, finding the production User-Agent works — it is "ask again, more slowly".

    Retrying immediately makes a throttle worse, which is why the shared transport's own backoff did
    not help: its attempts land close together. Spacing them out is the thing that works.

    Two kinds of failure get two different budgets, because waiting means different things for each.
    An HTTP 429 or 5xx is a throttle and genuinely clears with patience, so it gets the full budget.
    A network-level failure — DNS, connect refusal, a TLS-level block — is not usually going to clear
    in eight seconds, and giving it the full budget turned a run that verified nothing into four
    minutes of sleeping. It gets a short budget, enough for a transient timeout to recover.

    Only `unavailable` is retried at all. A 404 is a defect in our URL and must surface at once
    rather than be retried into a skip, and a geo-block will not change however long we wait.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except IngestFault as exc:
            verdict = _classify(exc)
            if verdict == "defect":
                raise
            if verdict == "geo-blocked":
                pytest.skip(
                    f"GEO-BLOCKED {label}: the runner's IP is restricted, so this endpoint answered "
                    f"403 at the edge and nothing about it was verified: {exc!r}"
                )
            throttled = "returned HTTP" in str(exc)
            budget = attempts if throttled else network_attempts
            delay = delay_seconds if throttled else network_delay_seconds
            if attempt >= budget:
                pytest.skip(
                    f"{label} answered only with {'throttle' if throttled else 'network'} errors "
                    f"across {attempt} attempts spaced {delay:.0f}s apart, so nothing is verified "
                    f"either way: {exc!r}"
                )
            await asyncio.sleep(delay)


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
    sides = [str(tick.side) for tick in ticks]
    # P-7, the owner's ruling at Stage 7.3: one-sidedness in a trade list is **never** a failure.
    # A 50-trade window in a quiet minute can legitimately be all buys — run 45759709313 was — and
    # failing on it would manufacture an outage out of normal market behaviour. The distribution is
    # therefore recorded as evidence in counts, not merely as the set of sides that happened to
    # appear, so a future run can be compared instead of re-argued. The asymmetry with
    # `_assert_book` below is deliberate: a one-sided *book* does indicate a broken feed, because a
    # book with no bids or no asks cannot be crossed, quoted or traded against.
    _evidence(
        f"{label}.trades",
        count=len(ticks),
        price_min=min(prices),
        price_max=max(prices),
        sides=sorted(set(sides)),
        buy=sides.count("BUY"),
        sell=sides.count("SELL"),
        unspecified=sides.count("None"),
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
        # P-8: the timestamp was the missing half of that finding. `.quotes` has always recorded
        # `observed_at` and this line did not, so a gap between the two mids could not be attributed
        # to elapsed time rather than to disagreement — and a tolerance chosen without that is
        # invented. Recording it makes the gap measurable from one run's annotation. It does **not**
        # assert agreement: the tolerance remains the owner's call, and nothing here fails on a gap.
        observed_at=book.observed_at.isoformat(),
    )


# ------------------------------------------------------- P-9: the cross-endpoint pair, recorded not judged
def _mid(bid: Decimal, ask: Decimal) -> Decimal:
    return (bid + ask) / 2


def _gap_bps(quotes_mid: Decimal, book_mid: Decimal) -> Decimal:
    """F-8's convention, stated wherever it is published: ``|qm - bm| / qm * 1e4``.

    A statistic with an unstated denominator is a defect (that is what F-8 was), so the convention
    lives in exactly one function and every published number comes from it.
    """
    return abs(quotes_mid - book_mid) / quotes_mid * Decimal(10_000)


def _rate_bps_per_second(gap_bps: Decimal, elapsed_seconds: float) -> float | None:
    """P-9's quantity of interest: how fast the two mids diverged, not how far apart they ended up.

    ``None`` when the interval is not measurable, because a rate with no denominator is the same
    defect as a statistic with no convention — and dividing by a zero or negative interval would
    invent one.
    """
    if elapsed_seconds <= 0:
        return None
    return round(float(gap_bps) / elapsed_seconds, 3)


def _record_cross_endpoint(
    quotes: Any,
    book: Any,
    *,
    label: str,
    wall_seconds: float,
) -> None:
    """Record one quotes/book pair and assert **nothing** about whether they agree.

    P-9, the owner's ruling at Stage 7.3: the two endpoints are not simultaneous, so a constant bps
    tolerance would measure market movement rather than disagreement. Four runs put the interval at
    1.287-1.435 s and the implied rate at 0.000-0.904 bps/s, and a sample that small cannot bound a
    rate's upper end. So the pair is recorded — both mids, both timestamps, the interval measured two
    ways, the gap and the rate — and accumulation is left to do the rest.

    This function contains no assertion about the gap on purpose. Adding one would re-litigate a
    question the owner has answered, and would fail on ordinary volatility.
    """
    quotes_mid = _mid(quotes.bid, quotes.ask)
    book_mid = _mid(book.best_bid, book.best_ask)
    observed_seconds = (book.observed_at - quotes.observed_at).total_seconds()
    gap = _gap_bps(quotes_mid, book_mid)
    _evidence(
        f"{label}.cross_endpoint",
        quotes_mid=quotes_mid,
        book_mid=book_mid,
        gap_bps=round(float(gap), 3),
        # Two independent readings of the same interval: the adapters' own timestamps, and the wall
        # clock around the two calls. If they ever disagree materially, something is stamping a
        # timestamp that is not the fetch time — which would quietly invalidate every gap published
        # so far, so the disagreement is recorded rather than averaged away.
        dt_observed_s=round(observed_seconds, 3),
        dt_wall_s=round(wall_seconds, 3),
        bps_per_s_observed=_rate_bps_per_second(gap, observed_seconds),
        bps_per_s_wall=_rate_bps_per_second(gap, wall_seconds),
        quoted_spread_bps=round(float((quotes.ask - quotes.bid) / quotes.bid * 10_000), 3),
        asserts_agreement=False,
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

    async def test_the_quotes_and_book_pair_is_recorded_and_not_judged(self, transport: Any) -> None:
        """P-9: fetch the pair back-to-back and record the rate. Assert nothing about agreement.

        The interval measured across the whole class was 1.287-1.435 s, but that spanned the trades
        and candles fetches between the two calls. Fetching them adjacently measures the endpoints
        themselves, which is the interval the rate needs as its denominator.
        """
        adapter = OkxPublicAdapter(transport=transport)
        with _live("okx"):
            before = datetime.now(UTC)
            quotes = await adapter.quotes([OKX_INST_ID])
            book = await adapter.book(OKX_INST_ID, depth=20)
            wall_seconds = (datetime.now(UTC) - before).total_seconds()
        assert quotes, "okx: no quotes came back"
        _record_cross_endpoint(quotes[0], book, label="okx", wall_seconds=wall_seconds)


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
        # Defect 40 was found by this test: the dump parsed to `year 58852 is out of range` because
        # spot dumps moved to microsecond timestamps from 2025-01-01 and the parser assumed
        # milliseconds. Asserting the year is the regression guard, and reporting the detected unit
        # keeps the venue's choice visible instead of quietly absorbed.
        years = {bar.open_time.year for bar in bars}
        assert years == {day.year}, (
            f"bars are dated {sorted(years)} but the dump is for {day.date()} — a mis-scaled "
            f"timestamp produces dates thousands of years out, and one that slips through poisons "
            f"every aggregate built on it"
        )
        assert parsed.timestamp_units, "the parser did not report which epoch unit the dump used"
        _evidence(
            "binance-vision.parse",
            rows=parsed.rows_read,
            accepted=parsed.records_accepted,
            rejected=parsed.records_rejected,
            had_header=parsed.had_header,
            timestamp_units=",".join(parsed.timestamp_units),
        )


# --------------------------------------------------------------------- Dukascopy
class TestDukascopyLiveLayout:
    """O-010: the bi5 layout, checked against a real download for the first time."""

    async def test_the_bi5_url_shape_is_correct(self, transport: Any) -> None:
        """The 0-indexed month is the trap; a 404 here is the finding, not an outage."""
        hour = _recent_weekday_hour()
        url = hour_url(DUKASCOPY_PAIR, hour)
        assert url.startswith(DUKASCOPY_BASE), f"unexpected base in {url}"
        payload = await _with_patience(lambda: transport.get_bytes(url), label="dukascopy")
        assert payload, f"{url} came back empty"
        _evidence("dukascopy.url", hour=hour.isoformat(), bytes=len(payload), month_segment=url.split("/")[6])

    async def test_verify_layout_passes_against_a_real_file(self, transport: Any) -> None:
        """This is the evidence ``LAYOUT_VERIFIED`` requires: a real hour file, structurally sound."""
        hour = _recent_weekday_hour()
        url = hour_url(DUKASCOPY_PAIR, hour)
        payload = await _with_patience(lambda: transport.get_bytes(url), label="dukascopy")

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
            f"assumption (LZMA, 20 bytes per tick, big-endian) is wrong or the hour was empty. "
            f"LAYOUT_VERIFIED is True on the strength of this check, so a failure here means the "
            f"flag goes back to False — the check is what makes the flag falsifiable."
        )
        assert result.get("tick_count", 0) > 0, "a real mid-week hour contained no ticks"

    async def test_parsed_ticks_are_in_the_right_price_band(self, transport: Any) -> None:
        """The divisor check: 100000 for EURUSD. Wrong by 100x is the catastrophic silent failure."""
        hour = _recent_weekday_hour()
        source = DukascopyHistorical(transport=transport)
        parsed = await _with_patience(lambda: source.fetch_hour(DUKASCOPY_PAIR, hour), label="dukascopy")

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
            # F-13: this is the CONSTANT, echoed — not a verification performed in this run. It used
            # to be published as `layout_verified=`, so run 45822394958 printed
            # `layout_verified=True` on this line while its own layout check sat in the skipped
            # column, having never fetched anything. The key is now named for what it is.
            layout_flag=LAYOUT_VERIFIED,
        )


def _diagnose_dukascopy(baseline: str, browser: str, other_hour: str) -> tuple[str, str]:
    """Choose a verdict from three probe outcomes, varying one thing at a time.

    Pure so it can be pinned without network access: each branch is a different claim about the
    world and only one of them is reachable from a sandbox with no egress. `baseline` is the
    production User-Agent against the requested hour, `browser` the same URL with a browser
    User-Agent, `other_hour` the production User-Agent against a different hour.
    """
    if baseline == "ok":
        return (
            "nothing to diagnose: the production User-Agent works",
            "none",
        )
    if baseline.startswith("network-"):
        # "Never reached" is only true if nothing reached it. This branch used to fire first and
        # unconditionally, so three runs published a verdict their own measurements refuted: in
        # 45756716181 the production User-Agent on a different hour returned 25,313 bytes of valid
        # LZMA, and in 45758610197 and 45784665370 a browser User-Agent on the *same* hour returned
        # 25,761 - all while the verdict said the host was never reached (docs/14 F-10).
        # F-11, found in run 45787399434: a probe that comes back with an HTTP status *reached*
        # the host, because 503 is a reply and not a silence. The first fix for F-10 counted only
        # successes, so that run still published "never reached" while its own other-hour probe
        # recorded http-503 from the very host the verdict called unreachable.
        reached: list[str] = []
        if browser == "ok":
            reached.append("a browser User-Agent on the same hour (a valid file came back)")
        elif browser.startswith("http-"):
            reached.append(f"a browser User-Agent on the same hour, which answered {browser}")
        if other_hour == "ok":
            reached.append("the production User-Agent on a different hour (a valid file came back)")
        elif other_hour.startswith("http-"):
            reached.append(f"the production User-Agent on a different hour, which answered {other_hour}")
        if reached:
            served = (
                ""
                if any("valid file" in r for r in reached)
                else (
                    "; every reply was an HTTP status rather than a file, so the host is reachable "
                    "but not serving"
                )
            )
            return (
                f"the production attempt got no reply ({baseline}) but the host did answer "
                f"{' and '.join(reached)} in the same minute, so this is not an unreachable host"
                f"{served}; one attempt per variant cannot separate a transient network fault "
                "from a rejection",
                "re-run: a production User-Agent success on retry makes the fault transient rather "
                "than policy; a repeat failure while a variant keeps working is an OWNER DECISION "
                "about how this project presents itself, not an engineering fix",
            )
        # A host that never answered is a different fact from a host that answered 503, and
        # conflating them would make a sandbox with no egress look like a finding about Dukascopy.
        return (
            f"the host was never reached ({baseline}), so no cause can be distinguished",
            "re-run from a host with egress; this environment cannot answer the question",
        )
    if browser == "ok":
        return (
            "the host rejects this project's User-Agent and accepts a browser one",
            "OWNER DECISION: adopting a browser User-Agent is circumvention, not engineering",
        )
    if other_hour == "ok":
        return (
            "the hour requested has no file; another hour answers",
            "widen the hour search in the live layout checks",
        )
    if baseline.startswith("http-5") and browser.startswith("http-5"):
        return (
            f"both User-Agents get {baseline}; the feed is throttling or unwell",
            "retry on the weekly schedule; consider a lower request rate",
        )
    return (
        f"no single variable explains it (ua={baseline}/{browser}, hour={other_hour})",
        "needs a runner outside this network; record as unresolved",
    )


# --------------------------------------------------------------------- Dukascopy reachability
class TestDukascopyReachabilityDiagnostic:
    """Why does the bi5 endpoint answer 503? Measured, not guessed.

    History: with the corrected URL (defect 39) the host answered HTTP 503 on all four attempts in
    run `45726585354`, so `verify_layout` had still never seen a real file. It has since — twelve
    consecutive runs on 2026-11-26 passed and `LAYOUT_VERIFIED` is True. What this diagnostic has
    *not* settled is why the feed answers intermittently: across those twelve runs the probes
    produced **five** different patterns — production ok (seven runs); both UAs faulted with another
    hour ok; production faulted with a browser UA ok; production faulted with *both* a browser UA
    and another hour ok; and, in `45787399434`, both UAs faulted while another hour answered
    **http-503** — while the patient layout fetch succeeded in every one, so no single variable
    explains it (`docs/14` §1.4 F-5).

    Four of those runs (`45756716181`, `45758610197`, `45784665370`, `45784657260`) also published
    the verdict "the host was never reached" next to probes showing the host answering, which is
    `docs/14` F-10 and is why the branch order below is pinned by tests. The fix for F-10 counted
    only *successes* as proof the host was reached, so `45787399434` published the same false
    verdict on the strength of an http-503 reply — a status code is a reply from the host, not a
    silence. That is `docs/14` F-11, and it is why the cross-product below is enumerated in a test
    rather than one case per branch. Three explanations are plausible and they imply different responses:

    * the feed throttles, and 503 is one of its throttle responses alongside 429 — then patience and
      a lower request rate fix it;
    * the host rejects a non-browser `User-Agent` — then the fix is a policy decision about what this
      project is willing to present itself as, and it belongs to the owner, not to this module;
    * the hour requested genuinely has no file — then a different hour works.

    Guessing between those would put an unverified claim in the docs. This varies **one thing at a
    time** and reports what happened, which is the only way to tell them apart. It deliberately does
    not change any production path: a browser `User-Agent` is used here to *measure* whether it
    matters, and adopting one in the adapters would be circumvention of a host's stated preference
    rather than engineering, so that choice is left to the owner with the evidence in front of them.

    If the production path simply works, there is nothing to diagnose and this says so.
    """

    BROWSER_UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    @staticmethod
    def _transport(user_agent: str) -> HttpTransport:
        """A minimal transport: no retries, so one attempt yields exactly one status.

        Retries are what make a throttle indistinguishable from a block — four attempts that all
        fail look the same whether the host is busy or refusing us. One attempt, one answer.
        """
        return HttpTransport(
            timeout_seconds=20.0,
            limiter=TokenBucket(rate_per_second=1.0, burst=1),
            backoff=BackoffPolicy(base_seconds=1.0, max_seconds=1.0, max_attempts=0),
            headers={"User-Agent": user_agent},
        )

    @staticmethod
    def _describe(exc: BaseException) -> str:
        match = re.search(r"returned HTTP (\d{3})", str(exc))
        if match is not None:
            return f"http-{match.group(1)}"
        if " failed: " in str(exc):
            return "network-" + type(exc).__name__
        return f"other-{type(exc).__name__}"

    async def _probe(self, url: str, user_agent: str, label: str) -> str:
        transport = self._transport(user_agent)
        try:
            payload = await transport.get_bytes(url)
            _evidence(
                f"dukascopy.probe.{label}",
                outcome="ok",
                bytes=len(payload),
                lzma=payload[:1] == bytes([0x5D]) or len(payload) == 0,
                url=url,
            )
            return "ok"
        except IngestFault as exc:
            outcome = self._describe(exc)
            _evidence(f"dukascopy.probe.{label}", outcome=outcome, url=url)
            return outcome
        finally:
            await transport.aclose()

    async def test_what_the_503_actually_is(self) -> None:
        hour = _recent_weekday_hour()
        url = hour_url(DUKASCOPY_PAIR, hour)

        # 1. the production posture: this project's own descriptive User-Agent, one attempt
        production_ua = "NEXUS/0.1 (personal research; free public data)"
        baseline = await self._probe(url, production_ua, "production_ua")
        if baseline == "ok":
            _evidence(
                "dukascopy.diagnosis",
                verdict="nothing to diagnose: the production User-Agent works",
                action="none",
            )
            return

        # 2. vary only the User-Agent, same URL, same instant
        browser = await self._probe(url, self.BROWSER_UA, "browser_ua")

        # 3. vary only the hour, back to the production User-Agent: is this hour simply absent?
        older = _recent_weekday_hour(hour=10)
        older_url = hour_url(DUKASCOPY_PAIR, older)
        other_hour = (
            await self._probe(older_url, production_ua, "production_ua_other_hour")
            if older_url != url
            else "same-hour-not-probed"
        )

        verdict, action = _diagnose_dukascopy(baseline, browser, other_hour)
        _evidence("dukascopy.diagnosis", verdict=verdict, action=action)
        # Deliberately no assertion on the verdict. This test exists to produce evidence, and
        # failing it would turn a diagnosis into a red build without telling anyone anything.
        # What it does assert is that the diagnosis ran and distinguished the cases it claims to.
        assert baseline != "ok"
        assert browser in {"ok"} or browser.startswith(("http-", "network-", "other-"))


class TestDukascopyDiagnosisLogic:
    """Every branch of the 503 diagnosis, pinned without network access.

    Only one branch is reachable from a sandbox with no egress, so without this the other four are
    unexecuted code making claims about the world that nobody has checked.
    """

    def test_a_working_production_path_needs_no_diagnosis(self) -> None:
        verdict, action = _diagnose_dukascopy("ok", "ok", "ok")
        assert "nothing to diagnose" in verdict and action == "none"

    def test_an_unreachable_host_is_not_reported_as_a_finding_about_dukascopy(self) -> None:
        verdict, action = _diagnose_dukascopy(
            "network-IngestFault", "network-IngestFault", "network-IngestFault"
        )
        assert "never reached" in verdict
        assert "egress" in action

    def test_a_browser_success_refutes_never_reached(self) -> None:
        """The shape runs `45758610197` and `45784665370` actually produced (docs/14 F-10).

        The production attempt got no reply while a browser User-Agent fetched 25,761 bytes of valid
        LZMA from the same URL in the same minute. Reporting "the host was never reached" there is
        contradicted by the diagnostic's own second measurement, and it was published three times
        before anything checked the verdict against the probes next to it.
        """
        verdict, action = _diagnose_dukascopy("network-IngestFault", "ok", "network-IngestFault")
        assert "never reached" not in verdict
        assert "browser User-Agent" in verdict
        assert "cannot separate a transient network fault" in verdict
        assert "OWNER DECISION" in action  # a UA change is a policy choice, never automatic

    def test_another_hour_answering_also_refutes_never_reached(self) -> None:
        """The shape run `45756716181` produced: both User-Agents faulted, a different hour answered."""
        verdict, action = _diagnose_dukascopy("network-IngestFault", "network-IngestFault", "ok")
        assert "never reached" not in verdict
        assert "different hour" in verdict
        assert "re-run" in action

    def test_never_reached_still_holds_when_nothing_answered(self) -> None:
        """The claim this branch exists to make, now scoped to the case where it is true."""
        verdict, _ = _diagnose_dukascopy("network-IngestFault", "network-IngestFault", "network-X")
        assert "never reached" in verdict

    def test_an_http_reply_from_a_variant_also_refutes_never_reached(self) -> None:
        """F-11, pinned on the exact inputs run 45787399434 produced.

        Both User-Agent attempts on the requested hour faulted at the network layer, and the
        production User-Agent on a different hour came back `http-503`. A 503 is a reply from the
        host, so "never reached" was false in that run too - the first F-10 fix counted only
        successes and missed it.
        """
        verdict, action = _diagnose_dukascopy("network-IngestFault", "network-IngestFault", "http-503")
        assert "never reached" not in verdict
        assert "http-503" in verdict, "the reply it measured must be the reply it reports"
        assert "reachable but not serving" in verdict
        assert "re-run" in action

    def test_a_browser_http_reply_refutes_never_reached_too(self) -> None:
        """The same gap on the other probe, so neither variant can slip through again."""
        verdict, _ = _diagnose_dukascopy("network-IngestFault", "http-503", "network-IngestFault")
        assert "never reached" not in verdict
        assert "browser User-Agent" in verdict and "http-503" in verdict

    def test_a_variant_that_returned_a_file_is_not_described_as_not_serving(self) -> None:
        """The "reachable but not serving" clause must fire only when nothing came back."""
        verdict, _ = _diagnose_dukascopy("network-IngestFault", "ok", "network-IngestFault")
        assert "valid file came back" in verdict
        assert "not serving" not in verdict

    def test_never_reached_is_claimed_only_when_all_three_probes_got_no_reply(self) -> None:
        """The whole cross-product, because a branch-order bug hides in unpinned combinations.

        F-10 and F-11 were both this shape: a branch that fires on one input while a later
        measurement in the same run contradicts it. Enumerating every combination is the only
        pin that cannot be satisfied by the cases someone happened to think of.
        """
        outcomes = ["ok", "network-IngestFault", "network-X", "http-503", "http-403"]
        combinations = 0
        for baseline in outcomes:
            for browser in outcomes:
                for other_hour in outcomes:
                    combinations += 1
                    verdict, _ = _diagnose_dukascopy(baseline, browser, other_hour)
                    nothing_answered = all(o.startswith("network-") for o in (baseline, browser, other_hour))
                    assert ("never reached" in verdict) is nothing_answered, (
                        f"({baseline}, {browser}, {other_hour}) -> {verdict}"
                    )
        assert combinations == len(outcomes) ** 3

    def test_a_user_agent_block_is_escalated_not_silently_worked_around(self) -> None:
        verdict, action = _diagnose_dukascopy("http-503", "ok", "http-503")
        assert "User-Agent" in verdict
        assert "OWNER DECISION" in action, (
            "adopting a browser User-Agent is a policy choice about how this project presents "
            "itself to a host, not an engineering fix, so it must not be taken automatically"
        )

    def test_a_missing_hour_is_distinguished_from_a_block(self) -> None:
        verdict, action = _diagnose_dukascopy("http-404", "http-404", "ok")
        assert "no file" in verdict and "widen the hour search" in action

    def test_persistent_server_errors_read_as_throttling(self) -> None:
        verdict, action = _diagnose_dukascopy("http-503", "http-503", "http-503")
        assert "throttling or unwell" in verdict and "weekly schedule" in action

    def test_an_unexplained_combination_says_so(self) -> None:
        verdict, action = _diagnose_dukascopy("http-403", "http-503", "network-X")
        assert "no single variable" in verdict and "unresolved" in action

    def test_no_branch_invents_a_cause_it_did_not_measure(self) -> None:
        """A 403 with no successful variant must not be reported as a User-Agent problem."""
        verdict, _ = _diagnose_dukascopy("http-403", "http-403", "http-403")
        assert "User-Agent" not in verdict, (
            "nothing succeeded with the browser User-Agent, so blaming it is unsupported"
        )


class TestPatienceBehaviour:
    """The retry policy, pinned without network access.

    It has three branches and none of them is reachable from a sandbox with no egress, so without
    this they are unexecuted code deciding what counts as worth retrying.
    """

    async def test_a_throttle_error_is_retried_until_it_clears(self) -> None:
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise IngestFault("DATA_UNAVAILABLE: https://x/y.bi5 returned HTTP 503", retryable=True)
            return "payload"

        result = await _with_patience(flaky, label="dukascopy", attempts=5, delay_seconds=0.0)
        assert result == "payload"
        assert calls["n"] == 3, "it should stop as soon as the source answers"

    async def test_a_404_is_not_retried_because_it_is_our_defect(self) -> None:
        """Retrying a wrong URL into a skip would hide exactly the finding this module exists for."""
        calls = {"n": 0}

        async def wrong_url() -> str:
            calls["n"] += 1
            raise IngestFault("DATA_UNAVAILABLE: https://x/BID/y.bi5 returned HTTP 404", retryable=False)

        with pytest.raises(IngestFault, match="404"):
            await _with_patience(wrong_url, label="dukascopy", attempts=5, delay_seconds=0.0)
        assert calls["n"] == 1, "a defect must surface on the first attempt, not be retried away"

    async def test_a_geo_block_is_not_retried_because_waiting_will_not_help(self) -> None:
        calls = {"n": 0}

        async def blocked() -> str:
            calls["n"] += 1
            raise IngestFault("DATA_UNAVAILABLE: https://x/y returned HTTP 403", retryable=False)

        with pytest.raises(pytest.skip.Exception, match="GEO-BLOCKED"):
            await _with_patience(blocked, label="bybit", attempts=5, delay_seconds=0.0)
        assert calls["n"] == 1

    async def test_exhausted_patience_skips_and_says_how_hard_it_tried(self) -> None:
        calls = {"n": 0}

        async def always_throttled() -> str:
            calls["n"] += 1
            raise IngestFault("DATA_UNAVAILABLE: https://x/y.bi5 returned HTTP 503", retryable=True)

        with pytest.raises(pytest.skip.Exception, match="6 attempts spaced") as info:
            await _with_patience(always_throttled, label="dukascopy", attempts=6, delay_seconds=0.0)
        assert calls["n"] == 6
        assert "nothing is verified either way" in str(info.value), (
            "an exhausted retry must not read as a pass"
        )

    async def test_a_network_failure_is_also_worth_waiting_out(self) -> None:
        calls = {"n": 0}

        async def timeouts() -> str:
            calls["n"] += 1
            if calls["n"] < 2:
                raise IngestFault("DATA_UNAVAILABLE: https://x/y.bi5 failed: ConnectTimeout('')")
            return "payload"

        assert await _with_patience(timeouts, label="dukascopy", attempts=3, delay_seconds=0.0) == "payload"

    async def test_an_assertion_failure_is_never_retried(self) -> None:
        """A failed invariant is a finding, not a flake, and must not be softened by retrying."""
        calls = {"n": 0}

        async def bad_invariant() -> str:
            calls["n"] += 1
            raise AssertionError("crossed book")

        with pytest.raises(AssertionError, match="crossed book"):
            await _with_patience(bad_invariant, label="dukascopy", attempts=5, delay_seconds=0.0)
        assert calls["n"] == 1


# ------------------------------------------------------------------ P-7 / P-8: what the harness asserts
class TestTradeSideRuling:
    """P-7, the owner's ruling at Stage 7.3: a one-sided trade list is **evidence, never a failure**.

    Offline, like the diagnosis-logic class above — these pin a decision about what the harness
    asserts, and a decision that needed the network to verify would not be a decision. The history
    is F-9: ``docs/06`` recorded okx's first live verification as "50 trades with both sides
    present", which read as an invariant but never was one, and run ``45759709313`` returned 50 buys
    and passed. The documentation was corrected in Stage 7.2; this pins the ruling itself.
    """

    NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

    def _tick(self, side: str | None, price: str = "60900.0") -> TickRecord:
        return TickRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="OKX",
            venue_symbol="BTC-USDT-SWAP",
            price=Decimal(price),
            quantity=Decimal("0.01"),
            observed_at=self.NOW,
            side=side,
            source=OKX_SOURCE,
        )

    def _book(self, *, bids: int = 3, asks: int = 3) -> BookRecord:
        return BookRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="OKX",
            venue_symbol="BTC-USDT-SWAP",
            bids=tuple(BookLevel(Decimal("60900.0") - Decimal(i), Decimal("0.5")) for i in range(bids)),
            asks=tuple(BookLevel(Decimal("60900.1") + Decimal(i), Decimal("0.5")) for i in range(asks)),
            observed_at=self.NOW,
            entitlement="LIVE",
            source=OKX_SOURCE,
        )

    def test_fifty_buys_and_no_sells_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Run 45759709313's real shape, reproduced offline: a quiet minute can be all buys."""
        _assert_ticks(tuple(self._tick("BUY") for _ in range(50)), source=OKX_SOURCE, label="okx")
        line = next(x for x in capsys.readouterr().out.splitlines() if ".trades" in x)
        assert "count=50" in line
        assert "buy=50" in line and "sell=0" in line
        assert "sides=['BUY']" in line

    def test_the_distribution_is_recorded_as_counts_and_not_only_as_a_set(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Why counts and not just the set of sides: ``sides=['BUY','SELL']`` is identical for a
        49/1 minute and a 25/25 minute, so the set alone cannot be compared between runs."""
        ticks = [self._tick("BUY")] * 37 + [self._tick("SELL")] * 13
        _assert_ticks(tuple(ticks), source=OKX_SOURCE, label="okx")
        line = next(x for x in capsys.readouterr().out.splitlines() if ".trades" in x)
        assert "buy=37" in line and "sell=13" in line

    def test_a_feed_that_publishes_no_side_is_recorded_not_failed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``side=None`` is inside the vocabulary: some feeds do not say. That is a fact about the
        feed, not a defect in it."""
        _assert_ticks(tuple(self._tick(None) for _ in range(5)), source=OKX_SOURCE, label="okx")
        line = next(x for x in capsys.readouterr().out.splitlines() if ".trades" in x)
        assert "unspecified=5" in line and "buy=0" in line and "sell=0" in line

    def test_a_one_sided_book_still_fails_because_the_asymmetry_is_deliberate(self) -> None:
        """The ruling is about *trades*. A book with no asks cannot be crossed, quoted or traded
        against, so ``_assert_book`` keeps failing one — and that difference is the ruling, not an
        inconsistency."""
        with pytest.raises(AssertionError, match="one-sided book"):
            _assert_book(self._book(asks=0), source=OKX_SOURCE, label="okx")
        with pytest.raises(AssertionError, match="one-sided book"):
            _assert_book(self._book(bids=0), source=OKX_SOURCE, label="okx")

    def test_the_book_evidence_carries_its_own_timestamp(self, capsys: pytest.CaptureFixture[str]) -> None:
        """P-8's missing half. ``.quotes`` always recorded ``observed_at`` and ``.book`` did not, so
        a gap between the two mids could not be attributed to elapsed time rather than to
        disagreement — and a tolerance chosen without that is invented. This makes the gap
        measurable; it still asserts no agreement, because the tolerance is the owner's call."""
        _assert_book(self._book(), source=OKX_SOURCE, label="okx")
        line = next(x for x in capsys.readouterr().out.splitlines() if ".book" in x)
        assert f"observed_at={self.NOW.isoformat()}" in line
        assert "spread_bps=" in line and "entitlement=LIVE" in line


class TestCrossEndpointRateArithmetic:
    """P-9, offline: the arithmetic behind the rate, and the fact that nothing judges it.

    These pin the helper rather than the venue, so the convention that produced every published
    `gap_bps` cannot drift from the code that computes the next one. F-8 was a statistic with an
    unstated denominator; the defence against that recurrence is a single function and a test that
    re-derives a number already on the record from it.
    """

    #: Run 45819539643's published evidence, verbatim from its annotation.
    RUN_19_QUOTES = (Decimal("60591.2"), Decimal("60591.3"))
    RUN_19_BOOK = (Decimal("60587.0"), Decimal("60587.1"))
    RUN_19_DT = 1.287

    def _quote(self, bid: Decimal, ask: Decimal, at: datetime) -> QuoteRecord:
        return QuoteRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="OKX",
            venue_symbol="BTC-USDT-SWAP",
            bid=bid,
            ask=ask,
            observed_at=at,
            source=OKX_SOURCE,
        )

    def _book(self, bid: Decimal, ask: Decimal, at: datetime) -> BookRecord:
        return BookRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="OKX",
            venue_symbol="BTC-USDT-SWAP",
            bids=(BookLevel(bid, Decimal("0.5")),),
            asks=(BookLevel(ask, Decimal("0.5")),),
            observed_at=at,
            entitlement="LIVE",
            source=OKX_SOURCE,
        )

    def test_the_convention_re_derives_a_number_already_on_the_record(self) -> None:
        """Run 19 published gap 0.693 bps over 1.287 s. Recomputing it from the helper must agree,
        or the helper and the record have drifted apart."""
        qm = _mid(*self.RUN_19_QUOTES)
        bm = _mid(*self.RUN_19_BOOK)
        assert qm == Decimal("60591.25") and bm == Decimal("60587.05")
        gap = _gap_bps(qm, bm)
        assert round(float(gap), 3) == 0.693
        assert _rate_bps_per_second(gap, self.RUN_19_DT) == 0.539

    def test_the_denominator_is_the_quotes_mid_not_the_book_mid(self) -> None:
        """`|qm - bm| / qm`, as stated in §2.5. Swapping the denominator changes the answer, so the
        asymmetry is pinned rather than left to whoever reads the formula next."""
        qm, bm = Decimal("60591.25"), Decimal("60587.05")
        assert round(float(_gap_bps(qm, bm)), 6) != round(float(abs(qm - bm) / bm * 10_000), 6)

    def test_a_gap_is_symmetric_in_sign_but_not_in_magnitude(self) -> None:
        """The book above the quotes and below it are the same distance, and neither is a failure."""
        qm = Decimal("60000")
        assert _gap_bps(qm, Decimal("60006")) == _gap_bps(qm, Decimal("59994"))

    def test_a_rate_with_no_interval_is_not_invented(self) -> None:
        """Dividing by zero or a negative interval would fabricate a denominator, which is the same
        defect F-8 named. `None` says "not measurable" instead."""
        assert _rate_bps_per_second(Decimal("1.5"), 0.0) is None
        assert _rate_bps_per_second(Decimal("1.5"), -0.4) is None

    def test_an_absurd_gap_is_recorded_and_not_judged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The whole of P-9 in one test: a 5,064 bps divergence — the book at half the price — must pass.

        If this ever fails, somebody has re-litigated a question the owner answered, and the fix is
        to remove their assertion, not to raise the threshold.
        """
        at = datetime(2026, 11, 26, 13, 5, 9, 75000, tzinfo=UTC)
        quotes = self._quote(Decimal("60784.9"), Decimal("60785.0"), at)
        book = self._book(Decimal("30000.0"), Decimal("30000.1"), at + timedelta(seconds=1.383))
        _record_cross_endpoint(quotes, book, label="okx", wall_seconds=1.400)
        line = next(x for x in capsys.readouterr().out.splitlines() if "cross_endpoint" in x)
        assert "asserts_agreement=False" in line
        # |60784.95 - 30000.05| / 60784.95 * 1e4 = 5064.56, computed by the helper and verified
        # against that arithmetic. Hardcoded on purpose: a magic number that matches the convention
        # today is the thing that fails when somebody changes the denominator.
        assert "gap_bps=5064.56" in line, line
        assert "bps_per_s_observed=3662.01" in line, line
        assert "dt_observed_s=1.383" in line and "dt_wall_s=1.4" in line

    def test_both_readings_of_the_interval_are_recorded(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The adapters' timestamps and the wall clock around the calls are independent readings of
        one interval. A material disagreement would mean a timestamp is not the fetch time, which
        would quietly invalidate every gap published so far — so it is recorded, not averaged away."""
        at = datetime(2026, 11, 26, 13, 5, 2, 973000, tzinfo=UTC)
        quotes = self._quote(Decimal("60780.0"), Decimal("60780.1"), at)
        book = self._book(Decimal("60777.2"), Decimal("60777.3"), at + timedelta(seconds=1.435))
        _record_cross_endpoint(quotes, book, label="okx", wall_seconds=9.999)
        line = next(x for x in capsys.readouterr().out.splitlines() if "cross_endpoint" in x)
        assert "dt_observed_s=1.435" in line and "dt_wall_s=9.999" in line
        assert "bps_per_s_observed=0.321" in line, line
        assert "bps_per_s_wall=0.046" in line, line

    def test_an_identical_pair_records_a_zero_rate(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Run 18's shape: same interval, no movement, gap exactly zero. Zero is a measurement."""
        at = datetime(2026, 11, 26, 12, 26, 10, 568000, tzinfo=UTC)
        quotes = self._quote(Decimal("60606.2"), Decimal("60606.3"), at)
        book = self._book(Decimal("60606.2"), Decimal("60606.3"), at + timedelta(seconds=1.338))
        _record_cross_endpoint(quotes, book, label="okx", wall_seconds=1.350)
        line = next(x for x in capsys.readouterr().out.splitlines() if "cross_endpoint" in x)
        assert "gap_bps=0.0" in line and "bps_per_s_observed=0.0" in line
