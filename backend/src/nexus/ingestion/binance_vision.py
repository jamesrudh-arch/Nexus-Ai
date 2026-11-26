"""data.binance.vision bulk historical dumps (Section 4.4 — free, no key, no SLA).

Binance publishes its own history as ZIP-wrapped CSV at ``data.binance.vision``. It is the
cheapest way to bootstrap years of bars for free, and — importantly for the Nigeria position
in the feasibility report §2 — it is **historical data only**. Using it does not require a
Binance account, does not imply Binance live trading is available (NGN/P2P suspended
February 2024, domain blocked), and is not a venue connection.

CSV specifics handled here:

* Header presence varies by dump vintage, so the first row is sniffed rather than assumed.
* Timestamps are epoch **milliseconds** for klines but ISO-8601 for some aggregate-trade
  files; both are handled, and a naive value is refused.
* Rows are ``[open_time, open, high, low, close, volume, close_time, quote_volume,
  trades, taker_buy_base, taker_buy_quote, ignore]``. The trailing ``ignore`` column is
  dropped rather than archived, because archiving a column the venue labels "ignore" is how
  schemas rot.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from nexus.core.ids import iso_utc
from nexus.ingestion.base import (
    BarRecord,
    IngestFault,
    IngestReport,
    TickRecord,
    Transport,
    epoch_unit,
    to_decimal,
    to_utc,
    validate_bar,
    validate_tick,
)

BINANCE_VISION = "https://data.binance.vision"
VENUE = "BINANCE"
SOURCE = "BINANCE_VISION_PUBLIC_DUMP"

#: Kline CSV columns in dump order. The final column is explicitly ignored by Binance.
KLINE_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
)

#: Aggregate-trade CSV columns.
AGG_TRADE_FIELDS = (
    "agg_trade_id",
    "price",
    "quantity",
    "first_trade_id",
    "last_trade_id",
    "transact_time",
    "is_buyer_maker",
    "ignore",
)

_INTERVAL_DURATION = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "1M": timedelta(days=30),  # monthly dumps; exact length comes from the row itself
}


def kline_url(
    symbol: str,
    interval: str,
    period: datetime,
    *,
    market: str = "spot",
    periodicity: str = "daily",
    base_url: str = BINANCE_VISION,
) -> str:
    """Build a dump URL. ``periodicity`` is ``daily`` or ``monthly``."""
    if period.tzinfo is None:
        raise IngestFault("BINANCE_VISION: period must be timezone-aware", retryable=False)
    local = period.astimezone(UTC)
    symbol_key = symbol.strip().upper()
    if periodicity == "monthly":
        stamp = local.strftime("%Y-%m")
    elif periodicity == "daily":
        stamp = local.strftime("%Y-%m-%d")
    else:
        raise IngestFault(
            f"BINANCE_VISION: periodicity must be daily or monthly, got {periodicity!r}", retryable=False
        )
    name = f"{symbol_key}-{interval}-{stamp}"
    # The {frequency} segment is part of the path, not only of the filename stamp: Binance lays
    # dumps out as data/{market}/{daily|monthly}/{type}/{symbol}/{interval}/{name}.zip. Omitting it
    # 404s on every request, and the offline tests could not notice because they registered the
    # same wrong URL in the recording transport (defect 38, found by live verification).
    return f"{base_url}/data/{market}/{periodicity}/klines/{symbol_key}/{interval}/{name}.zip"


def agg_trades_url(
    symbol: str,
    period: datetime,
    *,
    market: str = "spot",
    periodicity: str = "daily",
    base_url: str = BINANCE_VISION,
) -> str:
    if period.tzinfo is None:
        raise IngestFault("BINANCE_VISION: period must be timezone-aware", retryable=False)
    local = period.astimezone(UTC)
    symbol_key = symbol.strip().upper()
    # Validated rather than defaulted: periodicity now selects a path segment as well as a stamp,
    # so an unrecognised value would silently request a daily file under a monthly name.
    if periodicity == "monthly":
        stamp = local.strftime("%Y-%m")
    elif periodicity == "daily":
        stamp = local.strftime("%Y-%m-%d")
    else:
        raise IngestFault(
            f"BINANCE_VISION: periodicity must be daily or monthly, got {periodicity!r}", retryable=False
        )
    name = f"{symbol_key}-aggTrades-{stamp}"
    return f"{base_url}/data/{market}/{periodicity}/aggTrades/{symbol_key}/{name}.zip"


@dataclass(frozen=True, slots=True)
class DumpParseResult:
    """What one dump contained, including what was refused."""

    url: str
    rows_read: int
    records_accepted: int
    records_rejected: int
    rejection_reasons: dict[str, int]
    first_time: datetime | None
    last_time: datetime | None
    had_header: bool
    #: The epoch unit(s) the dump actually used, as detected from magnitude. Recorded because the
    #: venue changed it: spot dumps moved from milliseconds to microseconds from 2025-01-01
    #: (defect 40). Absorbing that silently would leave nobody able to say which unit a given
    #: archive was read in, and a mixed file would be invisible.
    timestamp_units: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "rows_read": self.rows_read,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "rejection_reasons": dict(self.rejection_reasons),
            "first_time": iso_utc(self.first_time) if self.first_time else None,
            "last_time": iso_utc(self.last_time) if self.last_time else None,
            "had_header": self.had_header,
            "timestamp_units": list(self.timestamp_units),
        }


def _note_unit(units: set[str], raw: Any) -> None:
    """Record the epoch unit a raw dump value used, so the parse summary can report it.

    Detection already scales the value correctly; this only makes the answer *visible*. A venue
    that changes its timestamp unit under us is the kind of change that should be observable in the
    evidence rather than quietly absorbed (defect 40).
    """
    text = "" if raw is None else str(raw).strip()
    if text.lstrip("-").isdigit():
        unit = epoch_unit(float(int(text)))
        if unit is not None:
            units.add(unit)


def _unzip(payload: bytes, *, url: str) -> str:
    """Extract the single CSV inside a dump ZIP. Text, not bytes, because csv wants str."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise IngestFault(f"BINANCE_VISION {url}: zip contains no CSV", retryable=False)
            with archive.open(names[0]) as handle:
                return handle.read().decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise IngestFault(
            f"BINANCE_VISION {url}: payload is not a valid zip (a 404 HTML page often looks like this)",
            retryable=False,
        ) from exc


def _sniff_header(first_field: str) -> bool:
    """Detect whether the first row is a header. Binance changed this between vintages."""
    return not first_field.strip().lstrip("-").isdigit()


def parse_kline_csv(
    text: str, *, symbol: str, interval: str, url: str = ""
) -> tuple[tuple[BarRecord, ...], DumpParseResult]:
    """Parse a klines dump into canonical bars."""
    duration = _INTERVAL_DURATION.get(interval)
    if duration is None:
        raise IngestFault(f"BINANCE_VISION: unsupported interval {interval!r}", retryable=False)

    reader = csv.reader(io.StringIO(text))
    bars: list[BarRecord] = []
    reasons: dict[str, int] = {}
    rows_read = 0
    rejected = 0
    had_header = False
    units: set[str] = set()
    first_time: datetime | None = None
    last_time: datetime | None = None

    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        if rows_read == 0 and _sniff_header(row[0]):
            had_header = True
            rows_read += 1
            continue
        rows_read += 1
        if len(row) < 6:
            rejected += 1
            reasons["MALFORMED_ROW:expected at least 6 columns"] = (
                reasons.get("MALFORMED_ROW:expected at least 6 columns", 0) + 1
            )
            continue
        record = dict(zip(KLINE_FIELDS, row, strict=False))
        _note_unit(units, record.get("open_time"))
        open_time = to_utc(record.get("open_time"), field_name="open_time", source=SOURCE)
        _note_unit(units, record.get("close_time"))
        close_time = to_utc(record.get("close_time"), field_name="close_time", source=SOURCE)
        if open_time is None:
            rejected += 1
            reasons["MISSING_OPEN_TIME"] = reasons.get("MISSING_OPEN_TIME", 0) + 1
            continue
        price_open = to_decimal(record.get("open"), field_name="open", source=SOURCE)
        high = to_decimal(record.get("high"), field_name="high", source=SOURCE)
        low = to_decimal(record.get("low"), field_name="low", source=SOURCE)
        close = to_decimal(record.get("close"), field_name="close", source=SOURCE)
        if price_open is None or high is None or low is None or close is None:
            rejected += 1
            reasons["UNPARSEABLE_OHLC"] = reasons.get("UNPARSEABLE_OHLC", 0) + 1
            continue
        trades_raw = record.get("trades")
        trades = int(trades_raw) if trades_raw and str(trades_raw).strip().lstrip("-").isdigit() else None
        bar = BarRecord(
            instrument_id="",  # resolved by the pipeline through the registry
            venue=VENUE,
            venue_symbol=symbol.strip().upper(),
            interval=interval,
            open_time=open_time,
            close_time=close_time or (open_time + duration),
            open=price_open,
            high=high,
            low=low,
            close=close,
            volume=to_decimal(record.get("volume"), field_name="volume", source=SOURCE),
            quote_volume=to_decimal(record.get("quote_volume"), field_name="quote_volume", source=SOURCE),
            trades=trades,
            # A published historical dump is settled by definition: the period is over.
            confirmed=True,
            source=SOURCE,
        )
        reason = validate_bar(bar)
        if reason is not None:
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        bars.append(bar)
        first_time = open_time if first_time is None or open_time < first_time else first_time
        last_time = open_time if last_time is None or open_time > last_time else last_time

    return tuple(bars), DumpParseResult(
        url=url,
        rows_read=rows_read,
        records_accepted=len(bars),
        records_rejected=rejected,
        rejection_reasons=reasons,
        first_time=first_time,
        last_time=last_time,
        had_header=had_header,
        timestamp_units=tuple(sorted(units)),
    )


def parse_agg_trades_csv(
    text: str, *, symbol: str, url: str = ""
) -> tuple[tuple[TickRecord, ...], DumpParseResult]:
    """Parse an aggregate-trades dump into canonical ticks."""
    reader = csv.reader(io.StringIO(text))
    ticks: list[TickRecord] = []
    reasons: dict[str, int] = {}
    rows_read = 0
    rejected = 0
    had_header = False
    units: set[str] = set()
    first_time: datetime | None = None
    last_time: datetime | None = None

    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        if rows_read == 0 and _sniff_header(row[0]):
            had_header = True
            rows_read += 1
            continue
        rows_read += 1
        if len(row) < 6:
            rejected += 1
            reasons["MALFORMED_ROW:expected at least 6 columns"] = (
                reasons.get("MALFORMED_ROW:expected at least 6 columns", 0) + 1
            )
            continue
        record = dict(zip(AGG_TRADE_FIELDS, row, strict=False))
        _note_unit(units, record.get("transact_time"))
        observed = to_utc(record.get("transact_time"), field_name="transact_time", source=SOURCE)
        price = to_decimal(record.get("price"), field_name="price", source=SOURCE)
        if observed is None or price is None:
            rejected += 1
            reasons["UNPARSEABLE_TIME_OR_PRICE"] = reasons.get("UNPARSEABLE_TIME_OR_PRICE", 0) + 1
            continue
        # ``is_buyer_maker`` is the only aggressor signal in the dump. True means the buyer
        # was the maker, so the aggressor sold.
        maker_flag = str(record.get("is_buyer_maker", "")).strip().lower()
        side = "SELL" if maker_flag in ("true", "1") else ("BUY" if maker_flag in ("false", "0") else None)
        tick = TickRecord(
            instrument_id="",
            venue=VENUE,
            venue_symbol=symbol.strip().upper(),
            price=price,
            quantity=to_decimal(record.get("quantity"), field_name="quantity", source=SOURCE),
            observed_at=observed,
            venue_timestamp=observed,
            side=side,
            trade_id=str(record.get("agg_trade_id") or "") or None,
            source=SOURCE,
        )
        reason = validate_tick(tick)
        if reason is not None:
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        ticks.append(tick)
        first_time = observed if first_time is None or observed < first_time else first_time
        last_time = observed if last_time is None or observed > last_time else last_time

    return tuple(ticks), DumpParseResult(
        url=url,
        rows_read=rows_read,
        records_accepted=len(ticks),
        records_rejected=rejected,
        rejection_reasons=reasons,
        first_time=first_time,
        last_time=last_time,
        had_header=had_header,
        timestamp_units=tuple(sorted(units)),
    )


class BinanceVisionHistorical:
    """Bulk historical downloader. Read-only, unauthenticated, $0."""

    name = "binance-vision-public"
    venue = VENUE
    requires_credentials = False

    def __init__(self, *, transport: Transport, base_url: str = BINANCE_VISION, market: str = "spot") -> None:
        self._transport = transport
        self._base = base_url.rstrip("/")
        self._market = market

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        periods: Iterable[datetime],
        *,
        periodicity: str = "daily",
        report: IngestReport | None = None,
        missing_is_ok: bool = True,
    ) -> tuple[tuple[BarRecord, ...], list[DumpParseResult]]:
        """Download and parse a list of dump periods.

        A 404 (missing day, delisted interval) is normal for this source. It is recorded as
        a gap by default rather than aborting a multi-year backfill — but ``missing_is_ok=False``
        turns it into an error for callers that need to know.
        """
        bars: list[BarRecord] = []
        parses: list[DumpParseResult] = []
        for period in periods:
            url = kline_url(
                symbol, interval, period, market=self._market, periodicity=periodicity, base_url=self._base
            )
            try:
                payload = await self._transport.get_bytes(url)
            except IngestFault as exc:
                if report is not None:
                    report.errors.append(f"missing dump {url}: {exc.detail[:120]}")
                    report.reject("DUMP_UNAVAILABLE")
                if not missing_is_ok:
                    raise
                continue
            try:
                text = _unzip(payload, url=url)
            except IngestFault as exc:
                if report is not None:
                    report.reject("NOT_A_ZIP")
                    report.errors.append(exc.detail[:200])
                if not missing_is_ok:
                    raise
                continue
            parsed, summary = parse_kline_csv(text, symbol=symbol, interval=interval, url=url)
            parses.append(summary)
            bars.extend(parsed)
            if report is not None:
                report.fetched += summary.rows_read
                report.accepted += summary.records_accepted
                report.rejected += summary.records_rejected
                for key, count in summary.rejection_reasons.items():
                    for _ in range(min(count, 100)):  # bounded: reasons, not a million increments
                        report.reject(key)
        bars.sort(key=lambda b: b.open_time)
        return tuple(bars), parses

    async def fetch_agg_trades(
        self,
        symbol: str,
        periods: Iterable[datetime],
        *,
        periodicity: str = "daily",
        report: IngestReport | None = None,
        missing_is_ok: bool = True,
    ) -> tuple[tuple[TickRecord, ...], list[DumpParseResult]]:
        ticks: list[TickRecord] = []
        parses: list[DumpParseResult] = []
        for period in periods:
            url = agg_trades_url(
                symbol, period, market=self._market, periodicity=periodicity, base_url=self._base
            )
            try:
                payload = await self._transport.get_bytes(url)
            except IngestFault as exc:
                if report is not None:
                    report.reject("DUMP_UNAVAILABLE")
                    report.errors.append(f"missing dump {url}: {exc.detail[:120]}")
                if not missing_is_ok:
                    raise
                continue
            try:
                text = _unzip(payload, url=url)
            except IngestFault as exc:
                if report is not None:
                    report.reject("NOT_A_ZIP")
                    report.errors.append(exc.detail[:200])
                if not missing_is_ok:
                    raise
                continue
            parsed, summary = parse_agg_trades_csv(text, symbol=symbol, url=url)
            parses.append(summary)
            ticks.extend(parsed)
            if report is not None:
                report.fetched += summary.rows_read
                report.accepted += summary.records_accepted
                report.rejected += summary.records_rejected
        ticks.sort(key=lambda t: t.observed_at)
        return tuple(ticks), parses


def daily_periods(start: datetime, end: datetime, *, limit: int = 400) -> Sequence[datetime]:
    """Daily period stamps between two instants, bounded so a typo cannot request a decade."""
    if start.tzinfo is None or end.tzinfo is None:
        raise IngestFault("BINANCE_VISION: start/end must be timezone-aware", retryable=False)
    cursor = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    last = end.astimezone(UTC)
    out: list[datetime] = []
    while cursor <= last and len(out) < limit:
        out.append(cursor)
        cursor += timedelta(days=1)
    return tuple(out)


def monthly_periods(start: datetime, end: datetime, *, limit: int = 240) -> Sequence[datetime]:
    """Monthly period stamps, bounded (240 months = 20 years)."""
    if start.tzinfo is None or end.tzinfo is None:
        raise IngestFault("BINANCE_VISION: start/end must be timezone-aware", retryable=False)
    cursor = start.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last = end.astimezone(UTC)
    out: list[datetime] = []
    while cursor <= last and len(out) < limit:
        out.append(cursor)
        year, month = (cursor.year + 1, 1) if cursor.month == 12 else (cursor.year, cursor.month + 1)
        cursor = cursor.replace(year=year, month=month)
    return tuple(out)


__all__ = [
    "AGG_TRADE_FIELDS",
    "BINANCE_VISION",
    "KLINE_FIELDS",
    "SOURCE",
    "VENUE",
    "BinanceVisionHistorical",
    "DumpParseResult",
    "agg_trades_url",
    "daily_periods",
    "kline_url",
    "monthly_periods",
    "parse_agg_trades_csv",
    "parse_kline_csv",
]
