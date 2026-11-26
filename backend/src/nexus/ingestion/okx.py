"""OKX v5 public market data (Section 11; Nigeria: ADOPT — removed from the restricted
list on 8 July 2026, per feasibility report §2, to be re-verified before any live phase).

**Public endpoints only.** No API key, no passphrase, no signature, no order capability.
OKX *does* require a passphrase for private endpoints; this adapter never touches them, so
no such configuration exists here.

OKX specifics handled below:

* Responses are ``{"code": "0", "msg": "", "data": [...]}`` — ``code`` is a **string**, and
  a non-zero code is a real failure even when HTTP status is 200.
* ``/api/v5/market/candles`` returns rows **newest first**, so the archiver must reverse
  them before writing or every backtest reads the future.
* ``/api/v5/market/history-candles`` is the deeper archive and is rate-limited far more
  tightly; it is only used when the caller asks for a range older than the recent window.
* Candle rows carry a trailing ``confirm`` flag (``"0"``/``"1"``). An unconfirmed row is a
  bar still forming and must never be treated as settled.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
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
    require_decimal,
    to_decimal,
    to_utc,
    validate_bar,
)

OKX_REST = "https://www.okx.com"
VENUE = "OKX"
SOURCE = "OKX_V5_PUBLIC_REST"

#: OKX bar names → canonical interval names.
_INTERVAL_TO_CANONICAL = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1H": "1h",
    "2H": "2h",
    "4H": "4h",
    "6H": "6h",
    "12H": "12h",
    "1D": "1d",
    "1W": "1w",
    "1M": "1M",
}

#: Canonical interval → how long one bar lasts. Used to derive close times and to detect
#: gaps, because OKX does not return a close timestamp.
_BAR_DURATION = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

#: Instrument types OKX exposes publicly. ``SWAP`` is the perpetual market Phase 3 targets.
INST_TYPES = ("SPOT", "MARGIN", "SWAP", "FUTURES", "OPTION")


def canonical_interval(interval: str) -> str:
    mapped = _INTERVAL_TO_CANONICAL.get(interval)
    if mapped is None:
        raise IngestFault(f"OKX: unsupported interval {interval!r}", retryable=False)
    return mapped


def okx_bar(canonical: str) -> str:
    for raw, name in _INTERVAL_TO_CANONICAL.items():
        if name == canonical:
            return raw
    raise IngestFault(f"OKX: no bar name matches {canonical!r}", retryable=False)


def bar_duration(canonical: str) -> timedelta:
    duration = _BAR_DURATION.get(canonical)
    if duration is None:
        raise IngestFault(f"OKX: unknown duration for interval {canonical!r}", retryable=False)
    return duration


class OkxPublicAdapter:
    """Read-only OKX v5 market data adapter."""

    name = "okx-public"
    venue = VENUE
    requires_credentials = False  # structural: no credential parameter exists

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        base_url: str = OKX_REST,
        rate_per_second: float = 3.0,
        burst: int = 6,
    ) -> None:
        # OKX public endpoints are limited per-IP and shared with the whole free VM, so the
        # local budget is deliberately tighter than Bybit's.
        self._transport = transport or HttpTransport(
            limiter=TokenBucket(rate_per_second=rate_per_second, burst=burst),
            backoff=BackoffPolicy(base_seconds=1.5, max_seconds=45.0, max_attempts=4),
        )
        self._base = base_url.rstrip("/")
        self._owns_transport = transport is None

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> tuple[Any, datetime | None]:
        url = f"{self._base}{path}"
        payload = await self._transport.get_json(url, params=params)
        if not isinstance(payload, dict):
            raise IngestFault(f"OKX {path}: response is not an object", retryable=False)
        code = str(payload.get("code", ""))
        if code not in ("0", ""):
            raise IngestFault(
                f"OKX {path}: code={code} msg={payload.get('msg')!r}",
                # 50011 = too many requests; 50013 = server busy. Both are transient.
                retryable=code in ("50011", "50013", "50004", "50026"),
            )
        data = payload.get("data")
        return data, None

    # ------------------------------------------------------------------ instruments

    async def instrument_info(
        self,
        symbols: Sequence[str] | None = None,
        *,
        inst_type: str = "SWAP",
    ) -> tuple[InstrumentInfoRecord, ...]:
        """Published trading rules. ``ctVal`` is the contract size — critical for sizing."""
        wanted = {s.strip().upper() for s in symbols} if symbols else None
        data, _ = await self._get("/api/v5/public/instruments", {"instType": inst_type})
        if not isinstance(data, list):
            return ()
        out: list[InstrumentInfoRecord] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            inst_id = str(entry.get("instId") or "").strip().upper()
            if not inst_id or (wanted is not None and inst_id not in wanted):
                continue
            out.append(
                InstrumentInfoRecord(
                    venue=VENUE,
                    venue_symbol=inst_id,
                    base_currency=str(entry.get("baseCcy") or "") or None,
                    quote_currency=str(entry.get("quoteCcy") or "") or None,
                    contract_size=to_decimal(entry.get("ctVal"), field_name="ctVal", source=SOURCE),
                    tick_size=to_decimal(entry.get("tickSz"), field_name="tickSz", source=SOURCE),
                    min_order_qty=to_decimal(entry.get("minSz"), field_name="minSz", source=SOURCE),
                    max_order_qty=to_decimal(
                        entry.get("maxMktSz") or entry.get("maxLmtSz"), field_name="maxSz", source=SOURCE
                    ),
                    qty_step=to_decimal(entry.get("lotSz"), field_name="lotSz", source=SOURCE),
                    status=str(entry.get("state") or "") or None,
                    observed_at=to_utc(entry.get("ts"), field_name="ts", source=SOURCE),
                    raw={
                        "instType": entry.get("instType"),
                        "settleCcy": entry.get("settleCcy"),
                        "ctMult": entry.get("ctMult"),
                        "ctValCcy": entry.get("ctValCcy"),
                        "listTime": entry.get("listTime"),
                        "category": entry.get("category"),
                    },
                ),
            )
        return tuple(out)

    # ------------------------------------------------------------------ tickers

    async def quotes(self, symbols: Sequence[str]) -> tuple[QuoteRecord, ...]:
        """One call per instrument — OKX's ticker endpoint takes a single ``instId``.

        No ``instType`` parameter: the instId (e.g. ``BTC-USDT-SWAP``) already encodes it,
        and passing both invites a mismatch the endpoint would silently resolve for us.
        """
        out: list[QuoteRecord] = []
        for symbol in symbols:
            inst_id = symbol.strip().upper()
            data, _ = await self._get("/api/v5/market/ticker", {"instId": inst_id})
            if not isinstance(data, list) or not data:
                continue
            entry = data[0]
            if not isinstance(entry, dict):
                continue
            observed = to_utc(entry.get("ts"), field_name="ts", source=SOURCE)
            out.append(
                QuoteRecord(
                    instrument_id="",
                    venue=VENUE,
                    venue_symbol=inst_id,
                    bid=to_decimal(entry.get("bidPx"), field_name="bidPx", source=SOURCE),
                    ask=to_decimal(entry.get("askPx"), field_name="askPx", source=SOURCE),
                    bid_size=to_decimal(entry.get("bidSz"), field_name="bidSz", source=SOURCE),
                    ask_size=to_decimal(entry.get("askSz"), field_name="askSz", source=SOURCE),
                    last=to_decimal(entry.get("last"), field_name="last", source=SOURCE),
                    observed_at=observed,
                    venue_timestamp=observed,
                    delayed=False,
                    source=SOURCE,
                ),
            )
        return tuple(out)

    # ------------------------------------------------------------------ trades

    async def trades(self, symbol: str, *, limit: int = 100) -> tuple[TickRecord, ...]:
        data, _ = await self._get(
            "/api/v5/market/trades",
            {"instId": symbol.strip().upper(), "limit": str(min(int(limit), 500))},
        )
        if not isinstance(data, list):
            return ()
        out: list[TickRecord] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            price = to_decimal(entry.get("px"), field_name="px", source=SOURCE)
            observed = to_utc(entry.get("ts"), field_name="ts", source=SOURCE)
            if price is None or observed is None:
                continue
            side_raw = entry.get("side")
            out.append(
                TickRecord(
                    instrument_id="",
                    venue=VENUE,
                    venue_symbol=symbol.strip().upper(),
                    price=price,
                    quantity=to_decimal(entry.get("sz"), field_name="sz", source=SOURCE),
                    observed_at=observed,
                    venue_timestamp=observed,
                    side=str(side_raw).upper() if side_raw in ("buy", "sell", "Buy", "Sell") else None,
                    trade_id=str(entry.get("tradeId") or "") or None,
                    source=SOURCE,
                ),
            )
        return tuple(sorted(out, key=lambda t: t.observed_at))

    # ------------------------------------------------------------------ candles

    async def bars(
        self,
        symbol: str,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 300,
        use_history: bool = False,
        report: IngestReport | None = None,
    ) -> tuple[BarRecord, ...]:
        """Fetch candles and normalise them.

        ``use_history=True`` targets ``/api/v5/market/history-candles``, which reaches
        further back but is rate-limited harder. Callers should default to the recent
        endpoint and only fall back deliberately.
        """
        canonical = canonical_interval(interval)
        duration = bar_duration(canonical)
        inst_id = symbol.strip().upper()
        params: dict[str, Any] = {
            "instId": inst_id,
            "bar": okx_bar(canonical),
            "limit": str(min(int(limit), 300)),
        }
        if end is not None:
            params["end"] = str(int(end.timestamp() * 1000))
        if start is not None:
            params["after"] = str(int(start.timestamp() * 1000))
        path = "/api/v5/market/history-candles" if use_history else "/api/v5/market/candles"
        data, _ = await self._get(path, params)
        if not isinstance(data, list):
            return ()

        bars: list[BarRecord] = []
        for row in data:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                if report is not None:
                    report.reject("MALFORMED_ROW:expected at least 6 fields")
                continue
            bar = _parse_candle(row, inst_id, canonical, duration)
            if bar is None:
                if report is not None:
                    report.reject("UNPARSEABLE_ROW")
                continue
            bars.append(bar)
        # OKX returns newest first; the archive and every rollup need chronological order.
        bars.reverse()
        if report is not None:
            report.fetched += len(data)
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
        page_limit: int = 300,
        report: IngestReport | None = None,
        max_pages: int = 400,
    ) -> tuple[BarRecord, ...]:
        """Walk ``end`` → ``start`` in pages using OKX's ``after`` cursor semantics.

        Bounded by ``max_pages`` and by a no-progress check, so a cursor that stops moving
        cannot loop against a free endpoint.
        """
        collected: list[BarRecord] = []
        cursor = end
        for _ in range(max_pages):
            batch = await self.bars(
                symbol,
                interval=interval,
                start=start,
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
            if oldest >= cursor:
                break  # no progress
            cursor = oldest - timedelta(milliseconds=1)
        return tuple(dedupe_bars(collected))

    # ------------------------------------------------------------------ order book

    async def book(self, symbol: str, *, depth: int = 20) -> BookRecord | None:
        inst_id = symbol.strip().upper()
        data, _ = await self._get(
            "/api/v5/market/books", {"instId": inst_id, "sz": str(min(int(depth), 400))}
        )
        if not isinstance(data, list) or not data:
            return None
        entry = data[0]
        if not isinstance(entry, dict):
            return None
        bids = _parse_levels(entry.get("bids"), limit=depth)
        asks = _parse_levels(entry.get("asks"), limit=depth)
        if not bids and not asks:
            return None
        observed = to_utc(entry.get("ts"), field_name="ts", source=SOURCE)
        if observed is None:
            raise IngestFault(f"OKX book for {inst_id}: no timestamp", retryable=True)
        return BookRecord(
            instrument_id="",
            venue=VENUE,
            venue_symbol=inst_id,
            bids=bids,
            asks=asks,
            observed_at=observed,
            venue_timestamp=observed,
            entitlement="LIVE",
            source=SOURCE,
        )


# --------------------------------------------------------------------------- parsing


def _parse_candle(row: Sequence[Any], inst_id: str, canonical: str, duration: timedelta) -> BarRecord | None:
    """OKX candle row: ``[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]``.

    ``vol`` is in base currency for SPOT and in contracts for derivatives; ``volCcy`` is
    the contract-currency volume. Both are kept so nothing is silently reinterpreted.
    """
    try:
        open_time = to_utc(row[0], field_name="ts", source=SOURCE)
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
    confirm_raw = row[8] if len(row) > 8 else None
    confirmed = str(confirm_raw) == "1" if confirm_raw is not None else False
    return BarRecord(
        instrument_id="",
        venue=VENUE,
        venue_symbol=inst_id,
        interval=canonical,
        open_time=open_time,
        close_time=open_time + duration,  # derived, not trusted from the feed
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=to_decimal(row[5], field_name="vol", source=SOURCE),
        quote_volume=to_decimal(row[7] if len(row) > 7 else None, field_name="volCcyQuote", source=SOURCE),
        trades=None,  # OKX candles do not publish a trade count
        confirmed=confirmed,
        source=SOURCE,
    )


def _parse_levels(raw: Any, *, limit: int) -> tuple[BookLevel, ...]:
    """OKX level row: ``[price, size, liquidationOrders, numOrders]``."""
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


def detect_gaps(bars: Sequence[BarRecord], *, canonical_interval_name: str) -> tuple[datetime, ...]:
    """Return the open times of bars that are missing from an otherwise continuous series.

    Free feeds have no SLA (Z-08): gaps happen. Recording them is what keeps a backtest
    honest — a gap filled by interpolation is fabricated data.
    """
    if len(bars) < 2:
        return ()
    duration = bar_duration(canonical_interval_name)
    ordered = sorted(bars, key=lambda b: b.open_time)
    missing: list[datetime] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        expected = previous.open_time + duration
        while expected < current.open_time:
            missing.append(expected)
            expected += duration
            if len(missing) > 100_000:  # bounded: a bad feed must not exhaust memory
                return tuple(missing)
    return tuple(missing)


__all__ = [
    "INST_TYPES",
    "OKX_REST",
    "SOURCE",
    "VENUE",
    "OkxPublicAdapter",
    "bar_duration",
    "canonical_interval",
    "detect_gaps",
    "okx_bar",
]
