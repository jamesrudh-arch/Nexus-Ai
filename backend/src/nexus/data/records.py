"""Canonical market-data records and normalisation (Section 4, Section 22.1).

Every free feed is different: Bybit returns ``retCode``/``result``, OKX returns
``code``/``data``, Dukascopy returns LZMA-compressed binary. What must **not** differ is
what lands in the archive. This module defines that canonical shape and the rules for
getting there.

Rules enforced here:

* **Prices and quantities are ``Decimal``.** A venue float is converted via ``str()`` so
  binary representation error never enters the archive. NaN/Infinity is rejected.
* **Timestamps are aware UTC.** A naive venue timestamp is a fault, not an assumption.
* **Nothing is invented.** A missing bid stays missing. A venue that publishes no volume
  yields ``volume=None``, never ``0`` — zero volume is a claim, absence is not.
* **Rejections are counted and reasoned**, never dropped silently. The archive reports
  how many records it refused so a broken feed is visible.
* **Free-tier politeness.** A token-bucket rate limiter and exponential backoff with
  jitter are built into the transport: getting throttled or IP-banned from a free endpoint
  would cost the project its data source.
* **Two timestamps, two owners.** ``observed_at`` is *ours*: the instant this process had the
  response in hand, stamped by the transport at the wire. ``venue_timestamp`` is *theirs*:
  the stamp the venue published for the datum. F-14 (ledger ``O-012``) was that all four
  adapters wrote the venue's value into both, so the field named for our observation carried
  somebody else's clock, the two were indistinguishable, and latency was unmeasurable — any
  staleness gate computed against venue time while calling it ours. Fixed in batch 8.4 under
  D-052's ruling that F-14's expensive half gets its own batch. Neither field is derived from
  the other and no fallback silently mixes them: a consumer that needs event time asks for
  ``venue_timestamp`` and refuses a record that has none.
"""

from __future__ import annotations

import asyncio
import random
import time as time_mod
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol, cast, runtime_checkable

# This module deliberately lives in ``nexus.data`` rather than ``nexus.ingestion``: the
# archiver, the ingestion pipeline and the venue adapters all depend on these record types,
# and putting them in ``ingestion`` created an import cycle
# (archive.bars -> ingestion.base -> ingestion/__init__ -> ingestion.pipeline -> archive.bars).
# Records are the shared vocabulary; ``ingestion.base`` re-exports them so existing import
# paths keep working.
from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc
from nexus.core.time import utc_now


class IngestFault(NexusError):
    """A feed could not be read or its payload could not be trusted."""

    def __init__(
        self, detail: str, *, retryable: bool = True, reason: RejectReason = RejectReason.DATA_UNAVAILABLE
    ) -> None:
        super().__init__(reason, detail, retryable=retryable)


class RateLimited(IngestFault):
    """Local rate limiter refused the call to protect the free-tier relationship."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail, retryable=True, reason=RejectReason.MODEL_RATE_LIMITED)


class FeedKind(StrEnum):
    INSTRUMENT_INFO = "INSTRUMENT_INFO"
    TICKER = "TICKER"
    TRADE = "TRADE"
    BOOK = "BOOK"
    BAR = "BAR"
    FUNDING = "FUNDING"


# --------------------------------------------------------------------------- decimals


def to_decimal(value: Any, *, field_name: str, source: str) -> Decimal | None:
    """Convert a venue value to ``Decimal``. ``None`` stays ``None``; junk raises.

    Conversion goes through ``str()`` so ``0.1`` from a JSON float becomes exactly
    ``Decimal("0.1")`` rather than ``0.1000000000000000055511151231257827``.
    """
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise IngestFault(
            f"{source}: field {field_name!r} is not a number: {value!r}",
            retryable=False,
            reason=RejectReason.CONFIG_INVALID,
        ) from exc
    if not result.is_finite():
        raise IngestFault(
            f"{source}: field {field_name!r} is not finite: {value!r}",
            retryable=False,
            reason=RejectReason.CONFIG_INVALID,
        )
    return result


def require_decimal(value: Any, *, field_name: str, source: str) -> Decimal:
    """Like :func:`to_decimal` but the field is mandatory."""
    result = to_decimal(value, field_name=field_name, source=source)
    if result is None:
        raise IngestFault(
            f"{source}: required field {field_name!r} is missing",
            retryable=False,
            reason=RejectReason.DATA_UNAVAILABLE,
        )
    return result


#: Epoch magnitudes are unambiguous across any plausible trading window. Seconds, milliseconds,
#: microseconds and nanoseconds for 2010-01-01..2100-01-01 occupy **disjoint** ranges — three orders
#: of magnitude apart — so a timestamp's unit can be read off its magnitude instead of guessed from
#: what the caller assumed. Verified numerically: 1764072000 can only be seconds, 1764072000000 only
#: milliseconds, 1764072000000000 only microseconds.
_EPOCH_SECONDS_MIN = 1_262_304_000.0  # 2010-01-01T00:00:00Z
_EPOCH_SECONDS_MAX = 4_102_444_800.0  # 2100-01-01T00:00:00Z
_EPOCH_SCALES: tuple[tuple[float, str], ...] = ((1.0, "s"), (1e3, "ms"), (1e6, "us"), (1e9, "ns"))


def epoch_unit(value: float) -> str | None:
    """The unit an integer epoch is expressed in, from its magnitude alone, or ``None``.

    Returns the only unit that lands the value inside the plausible window. Because those windows do
    not overlap this is a measurement, not a preference — there is never a tie to break.
    """
    for scale, unit in _EPOCH_SCALES:
        if _EPOCH_SECONDS_MIN <= value / scale <= _EPOCH_SECONDS_MAX:
            return unit
    return None


def _epoch_to_utc(value: float, *, field_name: str, source: str) -> datetime:
    """Convert a numeric epoch to aware UTC, refusing a value that fits no unit.

    A mis-scaled timestamp is the dangerous kind of bug: it does not fail loudly at the venue, it
    produces a bar dated thousands of years out that then poisons every aggregate built on it.
    Binance Vision began publishing **microsecond** timestamps for spot dumps from 2025-01-01, and
    reading those as milliseconds produced `year 58852 is out of range` on the first real download
    this repository ever made (defect 40). Refusing is cheaper than that.
    """
    unit = epoch_unit(value)
    if unit is None:
        raise IngestFault(
            f"{source}: timestamp {value!r} in {field_name!r} is not a plausible epoch value in any "
            f"unit (s, ms, us or ns) between 2010 and 2100 — refusing rather than emitting a date "
            f"thousands of years out",
            retryable=False,
            reason=RejectReason.CONFIG_INVALID,
        )
    scale = {name: factor for factor, name in _EPOCH_SCALES}[unit]
    return datetime.fromtimestamp(value / scale, tz=UTC)


def to_utc(value: Any, *, field_name: str, source: str) -> datetime | None:
    """Convert a venue timestamp to aware UTC.

    Accepted forms: an integer epoch in seconds, milliseconds, microseconds or nanoseconds,
    ISO-8601 with offset, or an ISO-8601 string ending in ``Z``. A naive datetime is **rejected** —
    guessing the venue's timezone is how backtests get silently shifted by hours.

    Numeric epochs are scaled by the unit their **magnitude** implies (:func:`epoch_unit`), not by
    a caller's standing assumption. An earlier signature took ``assume_ms`` for that purpose and the
    parameter has been removed rather than left inert: a venue can change its unit under us, and
    Binance Vision did — spot dumps moved from milliseconds to microseconds from 2025-01-01, which
    read as milliseconds produced `year 58852 is out of range` on the first real download this
    repository ever made (defect 40). A flag that says "trust me, it's milliseconds" is precisely
    the thing that cannot notice, and keeping it in the signature would invite callers to believe it
    still governs.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise IngestFault(
                f"{source}: naive timestamp in {field_name!r} (timezone is unknown, refusing to guess)",
                retryable=False,
                reason=RejectReason.CONFIG_INVALID,
            )
        return value.astimezone(UTC)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _epoch_to_utc(float(value), field_name=field_name, source=source)
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return _epoch_to_utc(float(int(text)), field_name=field_name, source=source)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestFault(
            f"{source}: unparseable timestamp in {field_name!r}: {text!r}",
            retryable=False,
            reason=RejectReason.CONFIG_INVALID,
        ) from exc
    if parsed.tzinfo is None:
        raise IngestFault(
            f"{source}: naive timestamp in {field_name!r}: {text!r} (refusing to guess timezone)",
            retryable=False,
            reason=RejectReason.CONFIG_INVALID,
        )
    return parsed.astimezone(UTC)


# --------------------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class TickRecord:
    """One canonical trade/tick observation.

    ``observed_at`` is when *this process* received the response carrying the tick; for a
    historical dump that is the download instant, shared by every row the file produced, and
    that is a fact about bulk retrieval rather than a defect. ``venue_timestamp`` is the
    venue's own time for the trade, and it is what ordering, bucketing and archiving use.
    """

    instrument_id: str
    venue: str
    venue_symbol: str
    price: Decimal
    quantity: Decimal | None
    # Optional in the type, guaranteed on the live path: every adapter gets its receipt time from
    # the transport, which always has one, and a test asserts that for all four. It is optional
    # because parsing bytes read from disk — a captured fixture, a replay, the layout verifier —
    # genuinely has no receipt instant, and inventing one from the local clock would be the same
    # lie F-14 was, told in the other direction.
    observed_at: datetime | None = None
    venue_timestamp: datetime | None = None
    side: str | None = None  # BUY | SELL | None when the feed does not say
    trade_id: str | None = None
    source: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "price": str(self.price),
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "observed_at": iso_utc(self.observed_at) if self.observed_at else None,
            "venue_timestamp": iso_utc(self.venue_timestamp) if self.venue_timestamp else None,
            "side": self.side,
            "trade_id": self.trade_id,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class QuoteRecord:
    """Top-of-book observation. ``observed_at`` is our receipt time, ``venue_timestamp`` the
    venue's stamp for the quote — see :class:`TickRecord`."""

    instrument_id: str
    venue: str
    venue_symbol: str
    bid: Decimal | None
    ask: Decimal | None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last: Decimal | None = None
    observed_at: datetime | None = None
    venue_timestamp: datetime | None = None
    delayed: bool = False
    source: str = "UNKNOWN"

    @property
    def is_crossed_or_locked(self) -> bool:
        if self.bid is None or self.ask is None:
            return False
        return self.bid >= self.ask

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "bid": str(self.bid) if self.bid is not None else None,
            "ask": str(self.ask) if self.ask is not None else None,
            "bid_size": str(self.bid_size) if self.bid_size is not None else None,
            "ask_size": str(self.ask_size) if self.ask_size is not None else None,
            "last": str(self.last) if self.last is not None else None,
            "observed_at": iso_utc(self.observed_at) if self.observed_at else None,
            "venue_timestamp": iso_utc(self.venue_timestamp) if self.venue_timestamp else None,
            "delayed": self.delayed,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class BarRecord:
    """One OHLCV bar. ``volume=None`` means the feed published no volume."""

    instrument_id: str
    venue: str
    venue_symbol: str
    interval: str  # canonical form: "1m", "5m", "1h", "1d"
    open_time: datetime
    close_time: datetime | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    quote_volume: Decimal | None = None
    trades: int | None = None
    confirmed: bool = False
    source: str = "UNKNOWN"
    # Our receipt time — when the response carrying this bar arrived. Appended after the
    # defaulted fields rather than placed beside ``open_time`` so positional construction of
    # the eleven fields above keeps working. ``open_time`` remains the event time and the
    # archive's partition key; a bar has no ``venue_timestamp`` because ``open_time`` *is* the
    # venue's stamp for it, and a second name for one value is how F-14 started.
    observed_at: datetime | None = None

    def is_consistent(self) -> bool:
        """OHLC must satisfy low <= open,close <= high. A violation is a feed fault."""
        extremes = (self.open, self.close)
        return self.low <= min(extremes) and self.high >= max(extremes) and self.low <= self.high

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "interval": self.interval,
            "open_time": iso_utc(self.open_time),
            "close_time": iso_utc(self.close_time) if self.close_time else None,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume) if self.volume is not None else None,
            "quote_volume": str(self.quote_volume) if self.quote_volume is not None else None,
            "trades": self.trades,
            "confirmed": self.confirmed,
            "source": self.source,
            "observed_at": iso_utc(self.observed_at) if self.observed_at else None,
        }


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class BookRecord:
    """Order-book snapshot, plus the entitlement we actually hold. ``observed_at`` is our
    receipt time, ``venue_timestamp`` the venue's stamp for the snapshot."""

    instrument_id: str
    venue: str
    venue_symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    observed_at: datetime
    venue_timestamp: datetime | None = None
    entitlement: str = "NONE"  # NONE | DELAYED | LIVE
    source: str = "UNKNOWN"

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "levels": len(self.bids) + len(self.asks),
            "best_bid": str(self.best_bid) if self.best_bid is not None else None,
            "best_ask": str(self.best_ask) if self.best_ask is not None else None,
            "observed_at": iso_utc(self.observed_at),
            # Was missing entirely, so the venue's own stamp for the book was dropped from the
            # serialised form — the one place a reader could have compared the two clocks. Found
            # while giving this record a receipt time; the field existed and was never published.
            "venue_timestamp": iso_utc(self.venue_timestamp) if self.venue_timestamp else None,
            "entitlement": self.entitlement,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class InstrumentInfoRecord:
    """Trading rules as published by the venue — the source for registry mappings.

    ``observed_at`` is our receipt time. ``venue_timestamp`` is the venue's own clock where the
    envelope publishes one (Bybit returns ``time``; OKX's market-data envelope does not), and is
    ``None`` where it does not — never a copy of ours, because a copied stamp is the defect.
    """

    venue: str
    venue_symbol: str
    base_currency: str | None = None
    quote_currency: str | None = None
    contract_size: Decimal | None = None
    tick_size: Decimal | None = None
    min_order_qty: Decimal | None = None
    max_order_qty: Decimal | None = None
    qty_step: Decimal | None = None
    status: str | None = None  # venue's own listing status string
    observed_at: datetime | None = None
    venue_timestamp: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "contract_size": str(self.contract_size) if self.contract_size is not None else None,
            "tick_size": str(self.tick_size) if self.tick_size is not None else None,
            "min_order_qty": str(self.min_order_qty) if self.min_order_qty is not None else None,
            "max_order_qty": str(self.max_order_qty) if self.max_order_qty is not None else None,
            "qty_step": str(self.qty_step) if self.qty_step is not None else None,
            "status": self.status,
            "observed_at": iso_utc(self.observed_at) if self.observed_at else None,
            "venue_timestamp": iso_utc(self.venue_timestamp) if self.venue_timestamp else None,
        }


# --------------------------------------------------------------------------- rate limit


class TokenBucket:
    """Async token-bucket limiter.

    Free endpoints are a privilege, not a right. The limiter is intentionally local and
    conservative: it is better to ingest slightly slower than to be throttled or banned.
    """

    def __init__(
        self, *, rate_per_second: float, burst: int, clock: Callable[[], float] = time_mod.monotonic
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        if burst < 1:
            raise ValueError("burst must be >= 1")
        self._rate = float(rate_per_second)
        self._burst = float(burst)
        self._tokens = float(burst)
        self._clock = clock
        self._last = clock()
        self._lock = asyncio.Lock()
        self._waits = 0

    @property
    def waits(self) -> int:
        """How many calls had to wait. A rising count means the plan is too aggressive."""
        return self._waits

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            deficit = tokens - self._tokens
            wait = deficit / self._rate
            self._waits += 1
        await asyncio.sleep(wait)
        async with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - tokens)


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """Exponential backoff with full jitter (the AWS-recommended shape, no cost)."""

    base_seconds: float = 1.0
    max_seconds: float = 60.0
    multiplier: float = 2.0
    max_attempts: int = 5

    def delay(self, attempt: int, *, rng: random.Random | None = None) -> float:
        if attempt < 0:
            raise ValueError("attempt must be >= 0")
        ceiling = min(self.max_seconds, self.base_seconds * (self.multiplier**attempt))
        draw = rng.random() if rng is not None else random.random()  # noqa: S311 - jitter, not crypto
        return ceiling * draw

    def allows(self, attempt: int) -> bool:
        return attempt < self.max_attempts


# --------------------------------------------------------------------------- transport


@dataclass(frozen=True, slots=True)
class Fetched:
    """One response, and the instant this process had it in hand.

    The receipt time is stamped **at the wire** rather than where a payload is parsed, and the
    difference is not pedantry: a Dukascopy hour file is LZMA-compressed and a Binance Vision
    daily dump is a zip, so parsing can take longer than the fetch. Stamping after parsing
    would charge our own CPU time to the venue's latency and reproduce F-14's error in the
    opposite direction — a number that looks like a measurement of the network and is not.

    ``attempts`` is carried because a retry is part of the receipt story: the timestamp is the
    last attempt's, and a response that took four tries to arrive is not the same fact as one
    that took one.
    """

    payload: Any
    received_at: datetime
    url: str
    attempts: int = 1


@runtime_checkable
class Transport(Protocol):
    """Minimal HTTP surface adapters need. Injected so tests need no network.

    ``fetch_json`` and ``fetch_bytes`` are the methods an adapter must use: they return the
    receipt time with the payload. ``get_json`` and ``get_bytes`` return the payload alone, so
    a caller that reaches for them has no way to record when the response arrived — which is
    precisely what F-14 was. They are kept for callers that genuinely do not need a receipt
    time (a reachability probe, a layout check) and not for adapters building records.
    """

    async def fetch_json(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched: ...

    async def fetch_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched: ...

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any: ...

    async def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes: ...

    async def aclose(self) -> None: ...


class HttpTransport:
    """httpx-backed transport with timeout, rate limiting and bounded retries."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        limiter: TokenBucket | None = None,
        backoff: BackoffPolicy | None = None,
        headers: dict[str, str] | None = None,
        client: Any = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._limiter = limiter or TokenBucket(rate_per_second=5.0, burst=10)
        self._backoff = backoff or BackoffPolicy()
        self._headers = headers or {"User-Agent": "NEXUS/0.1 (personal research; free public data)"}
        self._client = client
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def _ensure_client(self) -> Any:
        if self._client is None:
            import httpx  # local import: keeps the package importable without httpx installed

            self._client = httpx.AsyncClient(
                timeout=self._timeout, headers=self._headers, follow_redirects=True
            )
        return self._client

    async def _request(self, url: str, params: dict[str, Any] | None, *, want_bytes: bool) -> Fetched:
        client = self._ensure_client()
        attempt = 0
        while True:
            await self._limiter.acquire()
            self._calls += 1
            try:
                response = await client.get(url, params=params)
                status = int(getattr(response, "status_code", 0))
                if status == 429 or status >= 500:
                    raise IngestFault(f"{url} returned HTTP {status}", retryable=True)
                if status >= 400:
                    raise IngestFault(f"{url} returned HTTP {status}", retryable=False)
                # Stamped before the body is decoded, so the receipt time is the moment the
                # response was in hand and not the moment we finished reading it.
                received_at = utc_now()
                payload = response.content if want_bytes else response.json()
                return Fetched(payload=payload, received_at=received_at, url=url, attempts=attempt + 1)
            except IngestFault:
                if not self._backoff.allows(attempt):
                    raise
                await asyncio.sleep(self._backoff.delay(attempt))
                attempt += 1
            except Exception as exc:  # network-level faults are retryable
                if not self._backoff.allows(attempt):
                    raise IngestFault(f"{url} failed: {exc!r}", retryable=False) from exc
                await asyncio.sleep(self._backoff.delay(attempt))
                attempt += 1

    async def fetch_json(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched:
        return await self._request(url, params, want_bytes=False)

    async def fetch_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched:
        fetched = await self._request(url, params, want_bytes=True)
        if not isinstance(fetched.payload, bytes):
            raise IngestFault(f"{url} did not return bytes", retryable=False)
        return fetched

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return (await self.fetch_json(url, params=params)).payload

    async def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        # `fetch_bytes` has already refused anything that is not bytes, so the cast restates a
        # guarantee that was checked one line earlier rather than asserting an unchecked one.
        return cast(bytes, (await self.fetch_bytes(url, params=params)).payload)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class RecordingTransport:
    """In-memory transport for tests and for replay. No network is ever touched.

    Responses may be registered either by URL alone (matching any query params) or by
    ``(url, params)`` when a test needs to distinguish calls to the same endpoint with
    different arguments — e.g. Bybit ``instruments-info`` per category. Param-keyed entries
    take precedence over URL-keyed ones.
    """

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        now_fn: Callable[[], datetime] = utc_now,
    ) -> None:
        self._responses: dict[str, Any] = dict(responses or {})
        self._by_params: dict[tuple[str, tuple[tuple[str, Any], ...]], Any] = {}
        self.requests: list[tuple[str, dict[str, Any] | None]] = []
        # Injectable so a test can pin the receipt time and assert that a record carries *it*
        # rather than the venue's stamp. Without a controllable clock the two are only
        # distinguishable by luck, and "the adapter copied the venue time into observed_at" is
        # exactly the defect an assertion has to be able to see.
        self._now_fn = now_fn
        self.received_at: list[datetime] = []

    @staticmethod
    def _key(url: str, params: dict[str, Any] | None) -> tuple[str, tuple[tuple[str, Any], ...]]:
        return (url, tuple(sorted((params or {}).items())))

    def set_json(self, url: str, payload: Any, *, params: dict[str, Any] | None = None) -> None:
        if params is None:
            self._responses[url] = payload
        else:
            self._by_params[self._key(url, params)] = payload

    def set_bytes(self, url: str, payload: bytes, *, params: dict[str, Any] | None = None) -> None:
        if params is None:
            self._responses[url] = payload
        else:
            self._by_params[self._key(url, params)] = payload

    def _lookup(self, url: str, params: dict[str, Any] | None) -> Any:
        self.requests.append((url, params))
        keyed = self._by_params.get(self._key(url, params))
        if keyed is not None:
            return keyed
        if url in self._responses:
            return self._responses[url]
        raise IngestFault(f"no recorded response for {url} params={params}", retryable=False)

    async def fetch_json(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched:
        payload = self._lookup(url, params)
        if isinstance(payload, BaseException):
            raise payload
        return self._fetched(url, payload)

    async def fetch_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> Fetched:
        payload = self._lookup(url, params)
        if isinstance(payload, BaseException):
            raise payload
        if not isinstance(payload, bytes):
            raise IngestFault(f"recorded response for {url} is not bytes", retryable=False)
        return self._fetched(url, payload)

    def _fetched(self, url: str, payload: Any) -> Fetched:
        received_at = self._now_fn()
        self.received_at.append(received_at)
        return Fetched(payload=payload, received_at=received_at, url=url, attempts=1)

    async def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        return (await self.fetch_json(url, params=params)).payload

    async def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        return cast(bytes, (await self.fetch_bytes(url, params=params)).payload)

    async def aclose(self) -> None:
        return None


# --------------------------------------------------------------------------- results


@dataclass(slots=True)
class IngestReport:
    """What happened during one ingestion pass. Refusals are counted, not swallowed."""

    source: str
    venue: str
    started_at: datetime
    finished_at: datetime | None = None
    fetched: int = 0
    accepted: int = 0
    rejected: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        self.rejected += 1
        self.rejections[reason] = self.rejections.get(reason, 0) + 1

    def finish(self, at: datetime | None = None) -> None:
        self.finished_at = at or utc_now()

    @property
    def rejection_rate(self) -> float:
        total = self.accepted + self.rejected
        return (self.rejected / total) if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "venue": self.venue,
            "started_at": iso_utc(self.started_at),
            "finished_at": iso_utc(self.finished_at) if self.finished_at else None,
            "fetched": self.fetched,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "rejection_rate": round(self.rejection_rate, 4),
            "rejections": dict(self.rejections),
            "errors": list(self.errors)[:20],  # bounded: an error storm must not blow up audit
        }


@runtime_checkable
class MarketDataAdapter(Protocol):
    """The contract every venue feed implements.

    Adapters are **public-data only** in Phase 3: no method takes credentials, and none
    may place an order. That is a structural guarantee, not a comment.
    """

    name: str
    venue: str
    requires_credentials: bool

    async def instrument_info(
        self, symbols: Sequence[str] | None = None
    ) -> tuple[InstrumentInfoRecord, ...]: ...

    async def quotes(self, symbols: Sequence[str]) -> tuple[QuoteRecord, ...]: ...

    async def trades(self, symbol: str, *, limit: int = 100) -> tuple[TickRecord, ...]: ...

    async def bars(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> tuple[BarRecord, ...]: ...

    async def book(self, symbol: str, *, depth: int = 20) -> BookRecord | None: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class HistoricalSource(Protocol):
    """Bulk historical download (e.g. exchange data dumps, Dukascopy bi5)."""

    name: str

    async def fetch_range(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
        on_record: Callable[[Any], Awaitable[None]] | None = None,
    ) -> tuple[Any, ...]: ...


# --------------------------------------------------------------------------- validation


# A record with neither clock sorts last rather than raising: ordering must stay total for
# hand-built records, and a tick with no event time is refused by the archive anyway.
_SORT_FLOOR = datetime.min.replace(tzinfo=UTC)


def event_time(tick: TickRecord) -> datetime:
    """The tick's **event** time, total over every tick that can exist.

    Since F-14's fix a tick has two clocks and either may be absent: the venue's stamp is missing
    when a feed published none, and the receipt time is missing when the bytes came from disk
    rather than from a fetch. Ordering, bucketing and partitioning all need one comparable value,
    and each of those call sites was writing its own ``or`` chain — four copies of a rule that has
    to mean the same thing everywhere. So the rule lives here: the venue's stamp first, because it
    is the event time; ours next, because a tick with no venue stamp still happened before we
    received it; and the sort floor last, so a record with neither sorts rather than raising.

    Returning the floor is not a claim that the tick happened at the beginning of time. It is a
    way of being total, and every consumer that *acts* on the value — the archive's partition key,
    the rollup's bucket — refuses a tick with no venue stamp under its own reason before it gets
    here.
    """
    return tick.venue_timestamp or tick.observed_at or _SORT_FLOOR


def validate_bar(bar: BarRecord, *, report: IngestReport | None = None) -> str | None:
    """Return a rejection reason for a bad bar, or ``None`` when it is acceptable."""
    reason: str | None = None
    if not bar.is_consistent():
        reason = "OHLC_INCONSISTENT:low>open/close or high<open/close"
    elif bar.open_time.tzinfo is None:
        reason = "NAIVE_TIMESTAMP:bar open_time has no timezone"
    elif bar.high < bar.low:
        reason = "HIGH_BELOW_LOW"
    elif bar.volume is not None and bar.volume < 0:
        reason = "NEGATIVE_VOLUME"
    elif bar.close_time is not None and bar.close_time < bar.open_time:
        reason = "CLOSE_BEFORE_OPEN"
    if reason is not None and report is not None:
        report.reject(reason)
    return reason


def validate_tick(tick: TickRecord, *, report: IngestReport | None = None) -> str | None:
    reason: str | None = None
    if tick.price <= 0:
        reason = "NON_POSITIVE_PRICE"
    elif tick.quantity is not None and tick.quantity < 0:
        reason = "NEGATIVE_QUANTITY"
    elif tick.observed_at is not None and tick.observed_at.tzinfo is None:
        reason = "NAIVE_TIMESTAMP:tick observed_at has no timezone"
    # The event time is checked too, and separately: since F-14's fix it is the field ordering,
    # bucketing and the archive's partition key read, so a naive one corrupts a partition rather
    # than merely looking odd. A missing one is refused downstream, not here — ``None`` means the
    # feed published no stamp, which the archiver reports as its own reason.
    elif tick.venue_timestamp is not None and tick.venue_timestamp.tzinfo is None:
        reason = "NAIVE_TIMESTAMP:tick venue_timestamp has no timezone"
    elif tick.side is not None and tick.side not in {"BUY", "SELL"}:
        reason = f"UNKNOWN_SIDE:{tick.side}"
    if reason is not None and report is not None:
        report.reject(reason)
    return reason


def validate_quote(quote: QuoteRecord, *, report: IngestReport | None = None) -> str | None:
    """Crossed and locked books are recorded as faults, never silently stored as truth."""
    reason: str | None = None
    if quote.bid is None and quote.ask is None and quote.last is None:
        reason = "EMPTY_QUOTE:no bid, ask or last"
    elif quote.is_crossed_or_locked:
        reason = "CROSSED_OR_LOCKED:bid>=ask"
    elif quote.observed_at is None:
        reason = "MISSING_OBSERVATION_TIME"
    elif quote.observed_at.tzinfo is None:
        reason = "NAIVE_TIMESTAMP"
    if reason is not None and report is not None:
        report.reject(reason)
    return reason


def sort_bars(bars: Iterable[BarRecord]) -> list[BarRecord]:
    """Chronological order, required before archiving and before bar rollups."""
    return sorted(bars, key=lambda b: b.open_time)


def dedupe_bars(bars: Iterable[BarRecord]) -> list[BarRecord]:
    """Drop duplicate bars, keeping a confirmed one over a partial one.

    Free feeds overlap page boundaries; without dedupe the archive double-counts volume and
    backtests become fiction. The identity key includes instrument, venue and venue symbol:
    keying on ``(interval, open_time)`` alone would collapse distinct instruments that all
    have a bar at the same instant, which is silent data loss rather than deduplication.
    """
    seen: dict[tuple[str, str, str, str, datetime], BarRecord] = {}
    for bar in bars:
        key = (bar.instrument_id, bar.venue, bar.venue_symbol, bar.interval, bar.open_time)
        existing = seen.get(key)
        # Keep the first sighting, but let a confirmed bar upgrade a partial one — never the
        # reverse. Parentheses are explicit: `and` binds tighter than `or`, and a precedence
        # subtlety in the dedupe key path is not worth the four saved characters.
        if existing is None or (bar.confirmed and not existing.confirmed):
            seen[key] = bar
    return sort_bars(seen.values())


def dedupe_ticks(ticks: Iterable[TickRecord]) -> list[TickRecord]:
    """Drop duplicate trades by ``(venue_symbol, trade_id)`` when the feed supplies an id."""
    seen: set[tuple[str, str]] = set()
    out: list[TickRecord] = []
    for tick in ticks:
        if tick.trade_id is None:
            out.append(tick)
            continue
        key = (tick.venue_symbol, tick.trade_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(tick)
    # Ordered by the venue's event time, not by our receipt time: since F-14's fix every row of a
    # downloaded dump shares one receipt instant, so sorting on it would leave thousands of ticks
    # in whatever order the parser emitted them and call that chronological. The fallback to
    # ``observed_at`` is for a feed that published no stamp at all; such a tick cannot be archived
    # (the partition key refuses it), and ordering must not raise on a record the validators will
    # reject anyway.
    return sorted(out, key=event_time)


__all__ = [
    "BackoffPolicy",
    "BarRecord",
    "BookLevel",
    "BookRecord",
    "FeedKind",
    "Fetched",
    "HistoricalSource",
    "HttpTransport",
    "IngestFault",
    "IngestReport",
    "InstrumentInfoRecord",
    "MarketDataAdapter",
    "QuoteRecord",
    "RateLimited",
    "RecordingTransport",
    "TickRecord",
    "TokenBucket",
    "Transport",
    "dedupe_bars",
    "dedupe_ticks",
    "event_time",
    "require_decimal",
    "sort_bars",
    "to_decimal",
    "epoch_unit",
    "to_utc",
    "validate_bar",
    "validate_quote",
    "validate_tick",
]
