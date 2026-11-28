"""Bybit V5 public market data (Section 11, Nigeria: ADOPT per feasibility report §2).

**Public endpoints only.** Nothing in this module reads an API key, signs a request, or can
place an order. The class has no credentials parameter at all — that is the structural
guarantee, and CI asserts it.

Free-tier conduct (D-019, Z-08): Bybit's public rate limits are per-IP and shared with the
whole free VM, so the transport is rate-limited locally and backed off with jitter. There
is no SLA: a 429 or a silent gap is expected, and the archive records it rather than
pretending the data is complete.

Endpoints used (all unauthenticated):
``/v5/market/instruments-info``, ``/v5/market/tickers``, ``/v5/market/recent-trade``,
``/v5/market/kline``, ``/v5/market/orderbook``.

**Two clocks, kept apart (F-14, batch 8.4).** Bybit is the one venue here that publishes its
own clock in the response envelope (``time``), and before 8.4 that value was written into
``observed_at`` — sometimes directly, sometimes as the fallback when an entry carried no
``ts``/``time`` of its own. So the field named for our observation held the venue's clock, and
the fallback made it hold the venue's clock even when the entry said nothing. Now
``observed_at`` is this process's receipt time, stamped by the transport at the wire, and
``venue_timestamp`` is the venue's: the entry's own stamp where it has one, the envelope's
``time`` where it does not. The fallback survives, but it falls back to *their* clock and is
recorded in *their* field, which is what it always was.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from nexus.ingestion.base import (
    BackoffPolicy,
    BarRecord,
    BookLevel,
    BookRecord,
    HttpTransport,
    IngestFault,
    IngestReport,
    InstrumentInfoRecord,
    QuoteRecord,
    TickRecord,
    TokenBucket,
    Transport,
    dedupe_bars,
    event_time,
    require_decimal,
    to_decimal,
    to_utc,
    validate_bar,
)

BYBIT_REST = "https://api.bybit.com"
VENUE = "BYBIT"
SOURCE = "BYBIT_V5_PUBLIC_REST"

#: Bybit publishes intervals as bare minute counts (plus D/W/M). NEXUS canonicalises.
_INTERVAL_TO_CANONICAL = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "360": "6h",
    "720": "12h",
    "D": "1d",
    "W": "1w",
    "M": "1M",
}

#: Categories Bybit exposes. ``linear`` covers USDT-margined perps, which is the Phase 3
#: focus; ``inverse`` and ``spot`` are included because the instrument master must not
#: conflate them with linear contracts.
CATEGORIES = ("linear", "inverse", "spot", "option")


def canonical_interval(interval: str) -> str:
    """Map a Bybit interval onto the canonical one used in the archive."""
    mapped = _INTERVAL_TO_CANONICAL.get(interval)
    if mapped is None:
        raise IngestFault(f"BYBIT: unsupported interval {interval!r}", retryable=False)
    return mapped


def bybit_interval(canonical: str) -> str:
    """Reverse mapping, for requesting bars in canonical terms."""
    for raw, name in _INTERVAL_TO_CANONICAL.items():
        if name == canonical:
            return raw
    raise IngestFault(f"BYBIT: no interval matches {canonical!r}", retryable=False)


class BybitPublicAdapter:
    """Read-only Bybit V5 market data adapter."""

    name = "bybit-public"
    venue = VENUE
    requires_credentials = False  # structural: no credential parameter exists

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        base_url: str = BYBIT_REST,
        rate_per_second: float = 5.0,
        burst: int = 10,
    ) -> None:
        self._transport = transport or HttpTransport(
            limiter=TokenBucket(rate_per_second=rate_per_second, burst=burst),
            backoff=BackoffPolicy(base_seconds=1.0, max_seconds=30.0, max_attempts=4),
        )
        self._base = base_url.rstrip("/")
        self._owns_transport = transport is None

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    # ------------------------------------------------------------------ plumbing

    async def _get(self, path: str, params: dict[str, Any]) -> tuple[Any, datetime | None, datetime]:
        """Return ``(result, server_time, received_at)``.

        ``server_time`` is Bybit's own clock from the envelope and stays optional, because the
        venue may omit it. ``received_at`` is not optional: a response that arrived has an
        arrival time, and that is the one the records carry as ``observed_at``.
        """
        url = f"{self._base}{path}"
        fetched = await self._transport.fetch_json(url, params=params)
        payload = fetched.payload
        if not isinstance(payload, dict):
            raise IngestFault(f"BYBIT {path}: response is not an object", retryable=False)
        ret_code = payload.get("retCode")
        if ret_code not in (0, None):
            # retMsg is Bybit's own text; it never contains our credentials.
            raise IngestFault(
                f"BYBIT {path}: retCode={ret_code} retMsg={payload.get('retMsg')!r}",
                retryable=ret_code in (10006, 10016, 10018),
            )
        result = payload.get("result")
        server_time = to_utc(payload.get("time"), field_name="time", source=SOURCE)
        return result, server_time, fetched.received_at

    # ------------------------------------------------------------------ instruments

    async def instrument_info(
        self,
        symbols: Sequence[str] | None = None,
        *,
        categories: Sequence[str] = CATEGORIES[:2],
    ) -> tuple[InstrumentInfoRecord, ...]:
        """Fetch published trading rules — the authoritative source for registry mappings.

        Contract size, tick size, min/max quantity and quantity step come from here rather
        than from a hard-coded table, because venues change them without notice.
        """
        wanted = {s.strip().upper() for s in symbols} if symbols else None
        records: list[InstrumentInfoRecord] = []
        for category in categories:
            result, server_time, received_at = await self._get(
                "/v5/market/instruments-info",
                {"category": category},
            )
            if not isinstance(result, dict):
                continue
            listing = result.get("list") or []
            if not isinstance(listing, list):
                continue
            for entry in listing:
                if not isinstance(entry, dict):
                    continue
                symbol = str(entry.get("symbol") or "").strip()
                if not symbol or (wanted is not None and symbol.upper() not in wanted):
                    continue
                records.append(_parse_instrument(entry, category, server_time, received_at))
        return tuple(records)

    # ------------------------------------------------------------------ tickers

    async def quotes(self, symbols: Sequence[str], *, category: str = "linear") -> tuple[QuoteRecord, ...]:
        """Top-of-book for the requested symbols. One call when no symbol filter is needed."""
        params: dict[str, Any] = {"category": category}
        if len(symbols) == 1:
            params["symbol"] = symbols[0]
        result, server_time, received_at = await self._get("/v5/market/tickers", params)
        if not isinstance(result, dict):
            return ()
        listing = result.get("list") or []
        if isinstance(listing, dict):  # single-symbol responses come back as an object
            listing = [listing]
        if not isinstance(listing, list):
            return ()
        wanted = {s.strip().upper() for s in symbols} if symbols else None
        out: list[QuoteRecord] = []
        for entry in listing:
            if not isinstance(entry, dict):
                continue
            symbol = str(entry.get("symbol") or "").strip().upper()
            if not symbol or (wanted is not None and symbol not in wanted):
                continue
            out.append(_parse_ticker(entry, symbol, server_time, received_at))
        return tuple(out)

    # ------------------------------------------------------------------ trades

    async def trades(
        self, symbol: str, *, category: str = "linear", limit: int = 60
    ) -> tuple[TickRecord, ...]:
        """Recent public trades. Bybit caps this endpoint's history, so it is a top-up
        source, never the primary archive filler."""
        result, server_time, received_at = await self._get(
            "/v5/market/recent-trade",
            {"category": category, "symbol": symbol, "limit": min(int(limit), 1000)},
        )
        if not isinstance(result, dict):
            return ()
        listing = result.get("list") or []
        if not isinstance(listing, list):
            return ()
        out: list[TickRecord] = []
        for entry in listing:
            if not isinstance(entry, dict):
                continue
            tick = _parse_trade(entry, symbol, server_time, received_at)
            if tick is not None:
                out.append(tick)
        # Ordered by the venue's trade time: one response has one receipt instant, so sorting
        # on it would call arrival order trade order.
        return tuple(sorted(out, key=event_time))

    # ------------------------------------------------------------------ klines

    async def bars(
        self,
        symbol: str,
        *,
        interval: str,
        category: str = "linear",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
        report: IngestReport | None = None,
    ) -> tuple[BarRecord, ...]:
        """Historical klines, paginated backwards.

        Bybit returns at most 1,000 bars per call and pages *backwards in time*, so the
        loop walks ``end`` → ``start``. The final bar of a page is usually still forming;
        it is marked unconfirmed and the caller must not treat it as settled.
        """
        canonical = canonical_interval(interval)
        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "interval": bybit_interval(canonical),
            "limit": min(int(limit), 1000),
        }
        if end is not None:
            params["end"] = int(end.timestamp() * 1000)
        if start is not None:
            params["start"] = int(start.timestamp() * 1000)

        result, _server_time, received_at = await self._get("/v5/market/kline", params)
        if not isinstance(result, dict):
            return ()
        listing = result.get("list") or []
        if not isinstance(listing, list):
            return ()

        bars: list[BarRecord] = []
        newest_first = (
            listing and _as_millis(listing[0][0]) >= _as_millis(listing[-1][0]) if listing else False
        )
        rows = list(reversed(listing)) if newest_first else list(listing)
        for index, row in enumerate(rows):
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                if report is not None:
                    report.reject("MALFORMED_ROW:expected at least 6 fields")
                continue
            bar = _parse_kline(row, symbol, canonical)
            if bar is None:
                if report is not None:
                    report.reject("UNPARSEABLE_ROW")
                continue
            is_last = index == len(rows) - 1
            bars.append(
                BarRecord(
                    instrument_id=bar.instrument_id,
                    venue=bar.venue,
                    venue_symbol=bar.venue_symbol,
                    interval=bar.interval,
                    open_time=bar.open_time,
                    close_time=bar.close_time,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    quote_volume=bar.quote_volume,
                    trades=bar.trades,
                    # The newest bar in a page is typically still forming. Marking it
                    # confirmed would let a partial bar poison every rollup above it.
                    confirmed=not is_last,
                    source=SOURCE,
                    # This rebuild copies every field by hand, so the receipt time has to be
                    # named here too: a field left out of an explicit copy is a field silently
                    # dropped, which is how the book's venue stamp went missing in records.py.
                    observed_at=received_at,
                ),
            )
        if report is not None:
            report.fetched += len(listing)
            for bar in bars:
                if validate_bar(bar, report=report) is None:
                    report.accepted += 1
        return tuple(dedupe_bars(bars))

    async def bars_paged(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime,
        end: datetime,
        category: str = "linear",
        page_limit: int = 1000,
        report: IngestReport | None = None,
    ) -> tuple[BarRecord, ...]:
        """Walk a date range backwards in pages until ``start`` is reached.

        The loop is bounded by both the date range and ``max_pages`` so a mis-parsed
        timestamp cannot spin forever against a free endpoint.
        """
        canonical_interval(interval)  # validate eagerly; an unknown interval must fail here
        collected: list[BarRecord] = []
        cursor = end
        max_pages = 500
        for _ in range(max_pages):
            page_start = max(start, cursor)
            batch = await self.bars(
                symbol,
                interval=interval,
                category=category,
                start=page_start,
                end=cursor,
                limit=page_limit,
                report=report,
            )
            if not batch:
                break
            collected.extend(batch)
            oldest = min(b.open_time for b in batch)
            if oldest <= start:
                break
            next_cursor = oldest
            if next_cursor >= cursor:
                break  # no progress: stop rather than hammer the endpoint
            cursor = next_cursor
        return tuple(dedupe_bars(collected))

    # ------------------------------------------------------------------ order book

    async def book(self, symbol: str, *, category: str = "linear", depth: int = 20) -> BookRecord | None:
        result, server_time, received_at = await self._get(
            "/v5/market/orderbook",
            {"category": category, "symbol": symbol, "limit": min(int(depth), 500)},
        )
        if not isinstance(result, dict):
            return None
        bids = _parse_levels(result.get("b"), limit=depth)
        asks = _parse_levels(result.get("a"), limit=depth)
        if not bids and not asks:
            return None
        venue_ts = to_utc(result.get("ts"), field_name="ts", source=SOURCE) or server_time
        if venue_ts is None:
            raise IngestFault(f"BYBIT orderbook for {symbol}: no timestamp", retryable=True)
        return BookRecord(
            instrument_id="",  # resolved by the caller through the registry
            venue=VENUE,
            venue_symbol=symbol.upper(),
            bids=bids,
            asks=asks,
            observed_at=received_at,
            venue_timestamp=venue_ts,
            entitlement="LIVE",  # Bybit publishes public depth without entitlement checks
            source=SOURCE,
        )


# --------------------------------------------------------------------------- parsing


def _as_millis(value: Any) -> int:
    text = str(value)
    return int(text) if text.isdigit() else 0


def _parse_instrument(
    entry: dict[str, Any], category: str, server_time: datetime | None, received_at: datetime
) -> InstrumentInfoRecord:
    symbol = str(entry.get("symbol") or "").strip().upper()
    price_filter = (
        entry.get("linearPriceFilter")
        or entry.get("inversePriceFilter")
        or entry.get("spotPriceFilter")
        or {}
    )
    lot_filter = entry.get("lotSizeFilter") or entry.get("spotLotSizeFilter") or {}
    contract_type = entry.get("contractType") or category
    return InstrumentInfoRecord(
        venue=VENUE,
        venue_symbol=symbol,
        base_currency=str(entry.get("baseCoin") or "") or None,
        quote_currency=str(entry.get("quoteCoin") or "") or None,
        # Bybit linear perps are quoted per base coin, so the contract size is 1. This is
        # taken from the published lot filter where present rather than assumed.
        contract_size=to_decimal(
            lot_filter.get("basePrecision") or 1, field_name="contract_size", source=SOURCE
        ),
        tick_size=to_decimal(price_filter.get("tickSize"), field_name="tickSize", source=SOURCE),
        min_order_qty=to_decimal(lot_filter.get("minOrderQty"), field_name="minOrderQty", source=SOURCE),
        max_order_qty=to_decimal(lot_filter.get("maxOrderQty"), field_name="maxOrderQty", source=SOURCE),
        qty_step=to_decimal(lot_filter.get("qtyStep"), field_name="qtyStep", source=SOURCE),
        status=str(entry.get("status") or "") or None,
        observed_at=received_at,
        venue_timestamp=server_time,
        raw={
            "category": category,
            "contractType": contract_type,
            "settleCoin": entry.get("settleCoin"),
            "launchTime": entry.get("launchTime"),
            "deliveryTime": entry.get("deliveryTime"),
        },
    )


def _parse_ticker(
    entry: dict[str, Any], symbol: str, server_time: datetime | None, received_at: datetime
) -> QuoteRecord:
    # The entry's own ``ts`` first, the envelope's ``time`` as the fallback — both are Bybit's
    # clock, so both belong in ``venue_timestamp``. Neither is our receipt time.
    venue_ts = to_utc(entry.get("ts"), field_name="ts", source=SOURCE) or server_time
    return QuoteRecord(
        instrument_id="",  # resolved by the caller through the registry
        venue=VENUE,
        venue_symbol=symbol,
        bid=to_decimal(entry.get("bid1Price"), field_name="bid1Price", source=SOURCE),
        ask=to_decimal(entry.get("ask1Price"), field_name="ask1Price", source=SOURCE),
        bid_size=to_decimal(entry.get("bid1Size"), field_name="bid1Size", source=SOURCE),
        ask_size=to_decimal(entry.get("ask1Size"), field_name="ask1Size", source=SOURCE),
        last=to_decimal(entry.get("lastPrice"), field_name="lastPrice", source=SOURCE),
        observed_at=received_at,
        venue_timestamp=venue_ts,
        delayed=False,
        source=SOURCE,
    )


def _parse_trade(
    entry: dict[str, Any], symbol: str, server_time: datetime | None, received_at: datetime
) -> TickRecord | None:
    price = to_decimal(entry.get("price"), field_name="price", source=SOURCE)
    if price is None:
        return None
    side_raw = entry.get("side")
    side = str(side_raw).upper() if side_raw in ("Buy", "Sell", "buy", "sell", "BUY", "SELL") else None
    venue_ts = to_utc(entry.get("time"), field_name="time", source=SOURCE) or server_time
    if venue_ts is None:
        # No event time from either the entry or the envelope: the trade cannot be ordered or
        # archived, and substituting our receipt clock would put a fake trade time in the record.
        return None
    return TickRecord(
        instrument_id="",
        venue=VENUE,
        venue_symbol=symbol.upper(),
        price=price,
        quantity=to_decimal(entry.get("size"), field_name="size", source=SOURCE),
        observed_at=received_at,
        venue_timestamp=venue_ts,
        side=side,
        trade_id=str(entry.get("execId") or "") or None,
        source=SOURCE,
    )


def _parse_kline(row: Sequence[Any], symbol: str, canonical: str) -> BarRecord | None:
    """Bybit kline row: ``[start, open, high, low, close, volume, turnover]`` as strings.

    Returns ``None`` for any row that cannot be parsed. Raising instead would abort a whole
    backfill because one row was malformed, and the caller would lose the rejection count
    that makes a degrading feed visible.
    """
    try:
        open_time = to_utc(row[0], field_name="start", source=SOURCE)
    except IngestFault:
        return None
    if open_time is None:
        return None
    try:
        open_px = require_decimal(row[1], field_name="open", source=SOURCE)
        high = require_decimal(row[2], field_name="high", source=SOURCE)
        low = require_decimal(row[3], field_name="low", source=SOURCE)
        close = require_decimal(row[4], field_name="close", source=SOURCE)
    except IngestFault:
        return None
    volume = to_decimal(row[5] if len(row) > 5 else None, field_name="volume", source=SOURCE)
    turnover = to_decimal(row[6] if len(row) > 6 else None, field_name="turnover", source=SOURCE)
    return BarRecord(
        instrument_id="",
        venue=VENUE,
        venue_symbol=symbol.upper(),
        interval=canonical,
        open_time=open_time,
        close_time=None,  # derived by the archiver from the interval, not trusted from the feed
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=turnover,
        trades=None,  # Bybit klines do not publish a trade count
        confirmed=False,
        source=SOURCE,
    )


def _parse_levels(raw: Any, *, limit: int) -> tuple[BookLevel, ...]:
    if not isinstance(raw, list):
        return ()
    levels: list[BookLevel] = []
    for row in raw[:limit]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            price = to_decimal(row[0], field_name="price", source=SOURCE)
            size = to_decimal(row[1], field_name="size", source=SOURCE)
        except IngestFault:
            continue
        if price is None or size is None:
            continue
        levels.append(BookLevel(price=price, quantity=size))
    return tuple(levels)


def describe_endpoint(path: str) -> dict[str, Any]:
    """Documentation helper for the Connections page: public, unauthenticated, $0."""
    return {
        "venue": VENUE,
        "path": path,
        "base_url": BYBIT_REST,
        "authenticated": False,
        "requires_credentials": False,
        "cost_usd": 0,
    }


__all__ = [
    "BYBIT_REST",
    "CATEGORIES",
    "SOURCE",
    "VENUE",
    "BybitPublicAdapter",
    "bybit_interval",
    "canonical_interval",
    "describe_endpoint",
]
