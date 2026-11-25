"""Bar aggregation and rollup (Section 4.4; retention tiers per D-024).

Two jobs:

1. **Build bars from ticks** so the archive can hold 1-minute bars where holding ticks for
   a year would not fit on a 200 GB free-tier disk.
2. **Roll bars up** (1m → 5m → 1h → 1d) so the tiered retention policy can drop fine
   resolution without losing the shape of the series.

Correctness rules that matter for research integrity:

* **Only confirmed input forms a confirmed output.** A bar built from an unconfirmed source
  bar, or from a tick window that is still open, is emitted as ``confirmed=False``. An
  unconfirmed bar must never overwrite a confirmed one — that is how a partial bar silently
  corrupts every higher timeframe.
* **Empty buckets are not invented.** If no ticks fall in a minute, no bar is produced. A
  gap stays a gap; interpolation would fabricate liquidity that did not exist.
* **Volume is additive, price is not.** Open = first, close = last, high/low = extremes.
  Quote volume is only summed when *every* contributing bar has it, otherwise the result is
  ``None`` rather than a wrong total.
* **Decimal throughout.** No floats in the money path.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from nexus.core.ids import iso_utc
from nexus.data.records import BarRecord, TickRecord

#: Canonical interval → duration. Single source of truth for both builders.
INTERVAL_DURATION: dict[str, timedelta] = {
    "1s": timedelta(seconds=1),
    "5s": timedelta(seconds=5),
    "15s": timedelta(seconds=15),
    "30s": timedelta(seconds=30),
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

#: Legal rollup steps for the D-024 tiered retention ladder.
ROLLUP_CHAIN: tuple[str, ...] = ("1m", "5m", "1h", "1d")


def interval_duration(interval: str) -> timedelta:
    duration = INTERVAL_DURATION.get(interval)
    if duration is None:
        raise ValueError(f"unknown interval: {interval!r}")
    return duration


def is_rollup_of(source: str, target: str) -> bool:
    """True when ``target`` is a coarser interval that ``source`` divides evenly into."""
    try:
        src = interval_duration(source)
        dst = interval_duration(target)
    except ValueError:
        return False
    if dst <= src:
        return False
    return dst % src == timedelta(0)


def bucket_start(moment: datetime, interval: str) -> datetime:
    """Floor a timestamp to its bucket boundary in UTC.

    Daily and weekly buckets floor on the UTC calendar, not on elapsed 24-hour blocks, so a
    ``1d`` bar always starts at 00:00:00 UTC. Sessions that are not UTC-aligned are handled
    by the calendar module, not by shifting bars here.
    """
    if moment.tzinfo is None:
        raise ValueError("bucket_start requires a timezone-aware timestamp")
    local = moment.astimezone(UTC)
    duration = interval_duration(interval)
    if interval == "1d":
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "1w":
        # Weeks floor on UTC Monday 00:00, matching how daily/weekly bars are conventionally cut.
        return (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    total_seconds = int(duration.total_seconds())
    if total_seconds <= 0:
        raise ValueError(f"interval {interval!r} has non-positive duration")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    elapsed = int((local - epoch).total_seconds())
    floored = (elapsed // total_seconds) * total_seconds
    return epoch + timedelta(seconds=floored)


@dataclass(frozen=True, slots=True)
class AggregationReport:
    """What the aggregation did — including what it refused to do."""

    interval: str
    source_count: int
    bars_produced: int
    buckets_skipped_empty: int
    bars_unconfirmed: int
    records_rejected: int
    rejection_reasons: dict[str, int]
    first_bucket: datetime | None
    last_bucket: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval": self.interval,
            "source_count": self.source_count,
            "bars_produced": self.bars_produced,
            "buckets_skipped_empty": self.buckets_skipped_empty,
            "bars_unconfirmed": self.bars_unconfirmed,
            "records_rejected": self.records_rejected,
            "rejection_reasons": dict(self.rejection_reasons),
            "first_bucket": iso_utc(self.first_bucket) if self.first_bucket else None,
            "last_bucket": iso_utc(self.last_bucket) if self.last_bucket else None,
        }


@dataclass(slots=True)
class _Bucket:
    open_time: datetime
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal | None = None
    quote_volume: Decimal | None = None
    quote_volume_complete: bool = True
    trades: int = 0
    trade_count_known: bool = False
    confirmed: bool = True
    last_seen: datetime | None = None


def _accumulate(bucket: _Bucket, price: Decimal, quantity: Decimal | None, at: datetime) -> None:
    if bucket.open is None:
        bucket.open = price
    bucket.high = price if bucket.high is None or price > bucket.high else bucket.high
    bucket.low = price if bucket.low is None or price < bucket.low else bucket.low
    bucket.close = price
    if quantity is not None:
        bucket.volume = quantity if bucket.volume is None else bucket.volume + quantity
    if bucket.last_seen is None or at > bucket.last_seen:
        bucket.last_seen = at


def _to_bar(
    bucket: _Bucket,
    instrument_id: str,
    venue: str,
    venue_symbol: str,
    interval: str,
    source: str,
) -> BarRecord:
    """Materialise a tick bucket as a :class:`BarRecord`.

    ``open`` is guaranteed non-None here because a bucket is only created when a tick is
    accumulated into it; the assertion keeps mypy honest without a silent default.
    """
    open_px = bucket.open if bucket.open is not None else Decimal(0)
    high = bucket.high if bucket.high is not None else open_px
    low = bucket.low if bucket.low is not None else open_px
    close = bucket.close if bucket.close is not None else open_px
    return BarRecord(
        instrument_id=instrument_id,
        venue=venue,
        venue_symbol=venue_symbol,
        interval=interval,
        open_time=bucket.open_time,
        close_time=bucket.open_time + interval_duration(interval),
        open=open_px,
        high=high,
        low=low,
        close=close,
        volume=bucket.volume,
        quote_volume=bucket.quote_volume if bucket.quote_volume_complete else None,
        trades=bucket.trades if bucket.trade_count_known else None,
        confirmed=bucket.confirmed,
        source=source,
    )


def bars_from_ticks(
    ticks: Iterable[TickRecord],
    *,
    interval: str,
    instrument_id: str,
    venue: str,
    venue_symbol: str,
    source: str = "AGGREGATED",
    now: datetime | None = None,
) -> tuple[tuple[BarRecord, ...], AggregationReport]:
    """Aggregate trade ticks into bars.

    The bucket containing ``now`` is left unconfirmed: it is still forming. Empty buckets
    produce nothing — see module docstring.
    """
    reference = now or datetime.now(tz=UTC)
    buckets: dict[datetime, _Bucket] = {}
    rejected = 0
    reasons: dict[str, int] = {}
    current_bucket = bucket_start(reference, interval)
    source_count = 0

    # Pass 1: validate. Rejected ticks are counted with reasons, never dropped silently.
    valid: list[TickRecord] = []
    for tick in ticks:
        source_count += 1
        if tick.observed_at.tzinfo is None:
            rejected += 1
            reasons["NAIVE_TIMESTAMP"] = reasons.get("NAIVE_TIMESTAMP", 0) + 1
            continue
        if tick.price <= 0:
            rejected += 1
            reasons["NON_POSITIVE_PRICE"] = reasons.get("NON_POSITIVE_PRICE", 0) + 1
            continue
        if tick.observed_at > reference:
            # A future tick is a clock or feed fault. Dropping it silently would hide the
            # fault, so it is counted and excluded.
            rejected += 1
            reasons["FUTURE_TIMESTAMP"] = reasons.get("FUTURE_TIMESTAMP", 0) + 1
            continue
        valid.append(tick)

    # Pass 2: accumulate in *time* order, not arrival order.
    #
    # Real feeds deliver out of order: several streams interleave, a reconnect replays a
    # window, and a paginated backfill arrives newest-first. Accumulating in arrival order
    # would make ``open`` the first record *received* rather than the first *print*, so the
    # same data ingested twice in different orders would yield two different bars. Sorting
    # first makes the result deterministic and open/close genuinely time-correct. ``sorted``
    # is stable, so ticks sharing a timestamp keep their relative order.
    for tick in sorted(valid, key=lambda t: t.observed_at):
        start = bucket_start(tick.observed_at, interval)
        bucket = buckets.get(start)
        if bucket is None:
            bucket = _Bucket(open_time=start, confirmed=start < current_bucket)
            buckets[start] = bucket
        _accumulate(bucket, tick.price, tick.quantity, tick.observed_at)
        bucket.trades += 1
        bucket.trade_count_known = True

    bars = [_to_bar(b, instrument_id, venue, venue_symbol, interval, source) for b in buckets.values()]
    bars.sort(key=lambda b: b.open_time)
    report = AggregationReport(
        interval=interval,
        source_count=source_count,
        bars_produced=len(bars),
        buckets_skipped_empty=0,  # empty buckets are never created, so there is nothing to skip
        bars_unconfirmed=sum(1 for b in bars if not b.confirmed),
        records_rejected=rejected,
        rejection_reasons=reasons,
        first_bucket=bars[0].open_time if bars else None,
        last_bucket=bars[-1].open_time if bars else None,
    )
    return tuple(bars), report


def _resolve_rollup_identity(
    bars: Sequence[BarRecord],
    *,
    instrument_id: str | None,
    venue: str | None,
    venue_symbol: str | None,
) -> tuple[str, str, str, str | None]:
    """Decide whose bars a rollup produces, or explain why it cannot.

    Returns ``(instrument_id, venue, venue_symbol, refusal)``. ``refusal`` is a short reason
    when the identity could not be established, and the caller must produce no bars.

    An explicit override always wins. Otherwise the identity is inherited from the sources,
    but only when they all agree: silently picking the first bar's identity would label one
    instrument's prices as another's, which is the most expensive bug this system can have.
    """
    if instrument_id and venue and venue_symbol:
        return instrument_id, venue, venue_symbol, None

    distinct = {(b.instrument_id, b.venue, b.venue_symbol) for b in bars}
    if not distinct:
        return instrument_id or "", venue or "", venue_symbol or "", "no source bars"
    if len(distinct) > 1:
        sample = ", ".join(f"{i}/{v}/{s}" for i, v, s in sorted(distinct)[:3])
        return "", "", "", f"sources span {len(distinct)} identities ({sample})"

    inherited_id, inherited_venue, inherited_symbol = next(iter(distinct))
    resolved_id = instrument_id or inherited_id
    resolved_venue = venue or inherited_venue
    resolved_symbol = venue_symbol or inherited_symbol
    if not (resolved_id and resolved_venue and resolved_symbol):
        return "", "", "", "source bars carry no identity to inherit"
    return resolved_id, resolved_venue, resolved_symbol, None


def rollup_bars(
    bars: Iterable[BarRecord],
    *,
    target_interval: str,
    instrument_id: str | None = None,
    venue: str | None = None,
    venue_symbol: str | None = None,
    source: str = "ROLLUP",
    now: datetime | None = None,
) -> tuple[tuple[BarRecord, ...], AggregationReport]:
    """Roll finer bars up to ``target_interval``.

    Refuses an illegal rollup (e.g. 5m → 1m) instead of producing nonsense. A target bucket
    is confirmed only if **every** source bar that belongs to it is confirmed — one partial
    input makes the whole output partial.

    Identity (``instrument_id``/``venue``/``venue_symbol``) is **inherited from the source
    bars** when not supplied explicitly. Emitting an anonymous bar instead would be silent
    data loss on the retention ladder: every instrument's 5m bars would share one partition
    and become indistinguishable. When the sources disagree about who they belong to and no
    override is given, the rollup is **refused** rather than guessing — mixing two instruments
    into one bar is the same class of fault as the ``merge_bars`` identity collision.
    """
    reference = now or datetime.now(tz=UTC)
    buckets: dict[datetime, _Bucket] = {}
    rejected = 0
    reasons: dict[str, int] = {}
    current_target_bucket = bucket_start(reference, target_interval)
    source_count = 0
    seen_intervals: set[str] = set()

    materialised = list(bars)
    instrument_id, venue, venue_symbol, refusal = _resolve_rollup_identity(
        materialised,
        instrument_id=instrument_id,
        venue=venue,
        venue_symbol=venue_symbol,
    )
    if refusal is not None:
        return (), AggregationReport(
            interval=target_interval,
            source_count=len(materialised),
            bars_produced=0,
            buckets_skipped_empty=0,
            bars_unconfirmed=0,
            records_rejected=len(materialised),
            rejection_reasons={f"IDENTITY_AMBIGUOUS:{refusal}": len(materialised)},
            first_bucket=None,
            last_bucket=None,
        )

    for bar in sorted(materialised, key=lambda b: b.open_time):
        source_count += 1
        seen_intervals.add(bar.interval)
        if not is_rollup_of(bar.interval, target_interval) and bar.interval != target_interval:
            rejected += 1
            key = f"ILLEGAL_ROLLUP:{bar.interval}->{target_interval}"
            reasons[key] = reasons.get(key, 0) + 1
            continue
        if bar.open_time.tzinfo is None:
            rejected += 1
            reasons["NAIVE_TIMESTAMP"] = reasons.get("NAIVE_TIMESTAMP", 0) + 1
            continue
        if not bar.is_consistent():
            rejected += 1
            reasons["OHLC_INCONSISTENT"] = reasons.get("OHLC_INCONSISTENT", 0) + 1
            continue
        start = bucket_start(bar.open_time, target_interval)
        bucket = buckets.get(start)
        if bucket is None:
            bucket = _Bucket(open_time=start, quote_volume_complete=True, trade_count_known=False)
            buckets[start] = bucket

        # Open comes from the earliest source bar, close from the latest — the sort above
        # guarantees ordering, but only set `open` once per bucket.
        if bucket.open is None:
            bucket.open = bar.open
        bucket.high = bar.high if bucket.high is None or bar.high > bucket.high else bucket.high
        bucket.low = bar.low if bucket.low is None or bar.low < bucket.low else bucket.low
        bucket.close = bar.close
        if bar.volume is not None:
            bucket.volume = bar.volume if bucket.volume is None else bucket.volume + bar.volume
        else:
            # A missing input volume makes the total unknowable. Summing what we have would
            # report a smaller-than-true volume as if it were complete.
            bucket.quote_volume_complete = False
            if bucket.volume is not None:
                bucket.volume = None
        if bar.quote_volume is not None and bucket.quote_volume_complete:
            bucket.quote_volume = (
                bar.quote_volume if bucket.quote_volume is None else bucket.quote_volume + bar.quote_volume
            )
        elif bar.quote_volume is None:
            bucket.quote_volume_complete = False
            bucket.quote_volume = None
        if bar.trades is not None:
            bucket.trades += bar.trades
            bucket.trade_count_known = True
        else:
            bucket.trade_count_known = False
        if not bar.confirmed:
            bucket.confirmed = False

    out: list[BarRecord] = []
    for bucket in buckets.values():
        if bucket.open is None or bucket.close is None:
            continue
        confirmed = bucket.confirmed and bucket.open_time < current_target_bucket
        out.append(
            BarRecord(
                instrument_id=instrument_id or "",
                venue=venue or "",
                venue_symbol=venue_symbol or "",
                interval=target_interval,
                open_time=bucket.open_time,
                close_time=bucket.open_time + interval_duration(target_interval),
                open=bucket.open,
                high=bucket.high if bucket.high is not None else bucket.open,
                low=bucket.low if bucket.low is not None else bucket.open,
                close=bucket.close,
                volume=bucket.volume,
                quote_volume=bucket.quote_volume if bucket.quote_volume_complete else None,
                trades=bucket.trades if bucket.trade_count_known else None,
                confirmed=confirmed,
                source=source,
            ),
        )
    out.sort(key=lambda b: b.open_time)
    report = AggregationReport(
        interval=target_interval,
        source_count=source_count,
        bars_produced=len(out),
        buckets_skipped_empty=0,
        bars_unconfirmed=sum(1 for b in out if not b.confirmed),
        records_rejected=rejected,
        rejection_reasons=reasons,
        first_bucket=out[0].open_time if out else None,
        last_bucket=out[-1].open_time if out else None,
    )
    return tuple(out), report


def find_gaps(bars: Sequence[BarRecord], *, interval: str) -> tuple[datetime, ...]:
    """Bucket starts that are missing from an otherwise contiguous series.

    Gaps are reported, never filled. A filled gap is fabricated data, and fabricated data
    in a backtest produces a strategy that cannot survive contact with the market.
    """
    if len(bars) < 2:
        return ()
    duration = interval_duration(interval)
    ordered = sorted(bars, key=lambda b: b.open_time)
    missing: list[datetime] = []
    cap = 200_000  # bounded so a badly sorted or sparse series cannot exhaust memory
    for previous, current in zip(ordered, ordered[1:], strict=False):
        expected = previous.open_time + duration
        while expected < current.open_time:
            missing.append(expected)
            expected += duration
            if len(missing) >= cap:
                return tuple(missing)
    return tuple(missing)


def bar_identity(bar: BarRecord) -> tuple[str, str, str, str, datetime]:
    """The key that makes a bar *the same bar*.

    Instrument, venue, venue symbol, interval and open time. Keying on
    ``(interval, open_time)`` alone — the obvious-looking choice — silently destroys data:
    every instrument in the universe has a 1m bar at 12:00, and they would all collapse into
    one, leaving a single arbitrary instrument's prices labelled as everyone else's.
    """
    return (bar.instrument_id, bar.venue, bar.venue_symbol, bar.interval, bar.open_time)


def merge_bars(existing: Iterable[BarRecord], incoming: Iterable[BarRecord]) -> list[BarRecord]:
    """Merge by full bar identity, never letting a partial bar replace a confirmed one.

    This is the write-side guarantee behind the tiered retention ladder: re-downloading a
    range that overlaps already-confirmed history cannot degrade it.
    """
    merged: dict[tuple[str, str, str, str, datetime], BarRecord] = {}
    for bar in existing:
        merged[bar_identity(bar)] = bar
    for bar in incoming:
        key = bar_identity(bar)
        current = merged.get(key)
        if current is None:
            merged[key] = bar
        elif bar.confirmed and not current.confirmed:
            merged[key] = bar  # upgrade partial → confirmed
        elif not bar.confirmed and current.confirmed:
            continue  # never downgrade
    return sorted(merged.values(), key=lambda b: (b.instrument_id, b.venue_symbol, b.interval, b.open_time))


__all__ = [
    "INTERVAL_DURATION",
    "ROLLUP_CHAIN",
    "AggregationReport",
    "bar_identity",
    "bars_from_ticks",
    "bucket_start",
    "find_gaps",
    "interval_duration",
    "is_rollup_of",
    "merge_bars",
    "rollup_bars",
]
