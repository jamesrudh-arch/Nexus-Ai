"""Bar aggregation and rollup (Phase 3, retention tiers per D-024).

The properties that protect research integrity:
* empty buckets produce no bar — gaps stay gaps, never interpolated;
* an unconfirmed (still-forming) bar can never overwrite a confirmed one;
* volume is additive but a missing input volume makes the total unknowable, not zero;
* Decimal only — no float ever touches a price;
* illegal rollups are refused rather than producing nonsense.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.archive.bars import (
    INTERVAL_DURATION,
    ROLLUP_CHAIN,
    bar_identity,
    bars_from_ticks,
    bucket_start,
    find_gaps,
    interval_duration,
    is_rollup_of,
    merge_bars,
    rollup_bars,
)
from nexus.data.records import BarRecord, TickRecord

D = Decimal
BASE = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def tick(price: str, at: datetime, *, qty: str | None = "1", symbol: str = "BTCUSDT") -> TickRecord:
    return TickRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue="BYBIT",
        venue_symbol=symbol,
        price=D(price),
        quantity=D(qty) if qty is not None else None,
        observed_at=at,
        venue_timestamp=at,
        source="TEST",
    )


def bar(
    open_time: datetime,
    o: str,
    h: str,
    low: str,
    c: str,
    *,
    interval: str = "1m",
    volume: str | None = "10",
    quote_volume: str | None = "1000",
    trades: int | None = 5,
    confirmed: bool = True,
    symbol: str = "BTCUSDT",
) -> BarRecord:
    return BarRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue="BYBIT",
        venue_symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=open_time + interval_duration(interval),
        open=D(o),
        high=D(h),
        low=D(low),
        close=D(c),
        volume=D(volume) if volume is not None else None,
        quote_volume=D(quote_volume) if quote_volume is not None else None,
        trades=trades,
        confirmed=confirmed,
        source="TEST",
    )


class TestIntervalModel:
    @pytest.mark.parametrize(
        ("interval", "seconds"),
        [("1s", 1), ("1m", 60), ("5m", 300), ("1h", 3600), ("1d", 86400), ("1w", 604800)],
    )
    def test_durations(self, interval: str, seconds: int) -> None:
        assert interval_duration(interval) == timedelta(seconds=seconds)

    def test_unknown_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown interval"):
            interval_duration("7m")

    def test_rollup_chain_is_the_d024_ladder(self) -> None:
        assert ROLLUP_CHAIN == ("1m", "5m", "1h", "1d")

    @pytest.mark.parametrize(
        ("source", "target", "expected"),
        [
            ("1m", "5m", True),
            ("1m", "1h", True),
            ("1m", "1d", True),
            ("5m", "1h", True),
            ("5m", "1d", True),
            ("1h", "1d", True),
            ("5m", "1m", False),  # finer, not coarser
            ("1m", "1m", False),  # same
            ("1m", "3m", True),
            ("1m", "7m", False),  # not an even multiple
            ("1h", "1d", True),
            ("1d", "1w", True),  # 7 days is an exact multiple of 1 day
        ],
    )
    def test_is_rollup_of(self, source: str, target: str, expected: bool) -> None:
        if target not in INTERVAL_DURATION:
            pytest.skip(f"{target} is not a modelled interval")
        assert is_rollup_of(source, target) is expected

    def test_weekly_rollup_from_daily_is_even(self) -> None:
        assert is_rollup_of("1d", "1w") is True

    def test_unknown_intervals_are_not_rollups(self) -> None:
        assert is_rollup_of("1m", "nonsense") is False
        assert is_rollup_of("nonsense", "1m") is False


class TestBucketStart:
    def test_minute_floor(self) -> None:
        assert bucket_start(BASE + timedelta(seconds=37), "1m") == BASE

    def test_five_minute_floor(self) -> None:
        assert bucket_start(BASE + timedelta(minutes=7), "5m") == BASE + timedelta(minutes=5)

    def test_hour_floor(self) -> None:
        assert bucket_start(BASE + timedelta(minutes=59, seconds=59), "1h") == BASE

    def test_daily_floor_is_utc_midnight(self) -> None:
        moment = datetime(2026, 11, 25, 17, 43, 12, tzinfo=UTC)
        assert bucket_start(moment, "1d") == datetime(2026, 11, 25, 0, 0, 0, tzinfo=UTC)

    def test_weekly_floor_is_utc_monday_midnight(self) -> None:
        wednesday = datetime(2026, 11, 25, 17, 43, tzinfo=UTC)
        assert bucket_start(wednesday, "1w") == datetime(2026, 11, 23, 0, 0, tzinfo=UTC)

    def test_naive_timestamp_is_refused(self) -> None:
        """A naive timestamp would be floored against an unknown timezone."""
        with pytest.raises(ValueError, match="timezone-aware"):
            bucket_start(datetime(2026, 11, 25, 12, 0), "1m")

    def test_non_utc_input_is_converted_first(self) -> None:
        from zoneinfo import ZoneInfo

        lagos = datetime(2026, 11, 25, 13, 0, 30, tzinfo=ZoneInfo("Africa/Lagos"))  # 12:00:30 UTC
        assert bucket_start(lagos, "1m") == BASE


class TestBarsFromTicks:
    def test_ohlc_and_volume_from_ticks(self) -> None:
        ticks = [
            tick("100", BASE + timedelta(seconds=1)),
            tick("105", BASE + timedelta(seconds=10)),
            tick("95", BASE + timedelta(seconds=20)),
            tick("102", BASE + timedelta(seconds=30), qty="2"),
        ]
        bars, report = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert len(bars) == 1
        built = bars[0]
        assert built.open == D("100")
        assert built.high == D("105")
        assert built.low == D("95")
        assert built.close == D("102")
        assert built.volume == D("5")  # 1+1+1+2
        assert built.trades == 4
        assert built.confirmed is True
        assert report.bars_produced == 1
        assert report.source_count == 4
        assert report.records_rejected == 0

    def test_empty_bucket_produces_no_bar(self) -> None:
        """A gap must stay a gap. Inventing a bar fabricates liquidity."""
        ticks = [
            tick("100", BASE),
            tick("101", BASE + timedelta(minutes=3)),
        ]
        bars, _ = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=10),
        )
        assert len(bars) == 2
        assert [b.open_time for b in bars] == [BASE, BASE + timedelta(minutes=3)]
        # The two empty minutes between them are absent, not zero-filled.
        assert BASE + timedelta(minutes=1) not in [b.open_time for b in bars]

    def test_current_bucket_is_unconfirmed(self) -> None:
        """The bar still forming must not be presented as settled."""
        now = BASE + timedelta(seconds=30)
        ticks = [tick("100", BASE + timedelta(seconds=5))]
        bars, report = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=now,
        )
        assert len(bars) == 1
        assert bars[0].confirmed is False
        assert report.bars_unconfirmed == 1

    def test_future_ticks_are_rejected_and_counted(self) -> None:
        """A future tick is a clock fault, not data. Silent acceptance would hide it."""
        now = BASE
        ticks = [tick("100", now - timedelta(seconds=10)), tick("999", now + timedelta(minutes=5))]
        bars, report = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=now,
        )
        assert report.records_rejected == 1
        assert report.rejection_reasons == {"FUTURE_TIMESTAMP": 1}
        assert len(bars) == 1
        assert bars[0].high == D("100")  # the future price never entered the bar

    def test_non_positive_prices_are_rejected(self) -> None:
        ticks = [
            tick("0", BASE),
            tick("-5", BASE + timedelta(seconds=1)),
            tick("100", BASE + timedelta(seconds=2)),
        ]
        _, report = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert report.records_rejected == 2
        assert report.rejection_reasons == {"NON_POSITIVE_PRICE": 2}

    def test_naive_tick_timestamps_are_rejected(self) -> None:
        """Naive in the field the rollup buckets by, which since F-14's fix is the venue's."""
        naive = TickRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            price=D("100"),
            quantity=D("1"),
            observed_at=datetime(2026, 11, 25, 12, 0, tzinfo=UTC),
            venue_timestamp=datetime(2026, 11, 25, 12, 0),  # naive event time
            source="TEST",
        )
        _, report = bars_from_ticks(
            [naive],
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert report.rejection_reasons == {"NAIVE_TIMESTAMP": 1}

    def test_a_tick_with_no_event_time_is_rejected_under_its_own_reason(self) -> None:
        """Not `NAIVE_TIMESTAMP`: there is no timestamp to be naive, and the reason is read by
        whoever has to fix the feed. A rollup buckets by the venue's event time, so a tick
        carrying only our receipt time cannot join a bar at all."""
        no_event = TickRecord(
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            price=D("100"),
            quantity=D("1"),
            observed_at=datetime(2026, 11, 25, 12, 0, tzinfo=UTC),
            source="TEST",
        )
        _, report = bars_from_ticks(
            [no_event],
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert report.rejection_reasons == {"MISSING_EVENT_TIME": 1}

    def test_missing_volume_is_none_not_zero(self) -> None:
        """Zero volume is a claim; absence is not."""
        ticks = [tick("100", BASE, qty=None), tick("101", BASE + timedelta(seconds=5), qty=None)]
        bars, _ = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert bars[0].volume is None

    def test_partial_volume_knowledge_yields_none(self) -> None:
        ticks = [tick("100", BASE, qty=None), tick("101", BASE + timedelta(seconds=5), qty="3")]
        bars, _ = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert bars[0].volume == D("3")

    def test_out_of_order_ticks_still_produce_correct_ohlc(self) -> None:
        ticks = [
            tick("102", BASE + timedelta(seconds=30)),
            tick("100", BASE + timedelta(seconds=1)),
            tick("95", BASE + timedelta(seconds=20)),
            tick("105", BASE + timedelta(seconds=10)),
        ]
        bars, _ = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        built = bars[0]
        # open/close are time-ordered by the accumulator; high/low are true extremes.
        assert built.open == D("100")
        assert built.close == D("102")
        assert built.high == D("105")
        assert built.low == D("95")

    def test_no_ticks_produces_no_bars(self) -> None:
        bars, report = bars_from_ticks(
            [],
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE,
        )
        assert bars == ()
        assert report.bars_produced == 0
        assert report.source_count == 0

    def test_prices_stay_exact_decimals(self) -> None:
        """0.1 + 0.2 must be 0.3, not 0.30000000000000004."""
        ticks = [tick("0.1", BASE, qty="0.1"), tick("0.2", BASE + timedelta(seconds=1), qty="0.2")]
        bars, _ = bars_from_ticks(
            ticks,
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        assert bars[0].volume == D("0.3")
        assert isinstance(bars[0].volume, Decimal)

    def test_report_is_json_safe(self) -> None:
        _, report = bars_from_ticks(
            [tick("100", BASE)],
            interval="1m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(minutes=5),
        )
        payload = report.to_dict()
        assert payload["interval"] == "1m"
        assert payload["first_bucket"].endswith("Z")
        assert payload["rejection_reasons"] == {}


class TestRollup:
    def test_five_minutes_from_one_minute(self) -> None:
        source = [
            bar(BASE + timedelta(minutes=m), "100", "110", "90", "105", volume="10", trades=5)
            for m in range(5)
        ]
        rolled, report = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(hours=1),
        )
        assert len(rolled) == 1
        assert rolled[0].interval == "5m"
        assert rolled[0].open == D("100")
        assert rolled[0].close == D("105")
        assert rolled[0].high == D("110")
        assert rolled[0].low == D("90")
        assert rolled[0].volume == D("50")
        assert rolled[0].trades == 25
        assert rolled[0].confirmed is True
        assert report.bars_produced == 1

    def test_open_comes_from_earliest_close_from_latest(self) -> None:
        source = [
            bar(BASE, "100", "101", "99", "100.5"),
            bar(BASE + timedelta(minutes=1), "100.5", "120", "100", "119"),
            bar(BASE + timedelta(minutes=2), "119", "119.5", "80", "81"),
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].open == D("100")
        assert rolled[0].close == D("81")
        assert rolled[0].high == D("120")
        assert rolled[0].low == D("80")

    def test_one_unconfirmed_input_makes_the_whole_output_unconfirmed(self) -> None:
        source = [
            bar(BASE, "100", "101", "99", "100", confirmed=True),
            bar(BASE + timedelta(minutes=1), "100", "101", "99", "100", confirmed=False),
        ]
        rolled, report = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].confirmed is False
        assert report.bars_unconfirmed == 1

    def test_current_target_bucket_is_unconfirmed_even_from_confirmed_inputs(self) -> None:
        now = BASE + timedelta(minutes=2)
        source = [bar(BASE, "100", "101", "99", "100", confirmed=True)]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=now,
        )
        assert rolled[0].confirmed is False  # the 5m bucket containing `now` is still forming

    def test_missing_volume_poisons_the_total(self) -> None:
        """Summing what we have would report a smaller-than-true volume as complete."""
        source = [
            bar(BASE, "100", "101", "99", "100", volume="10"),
            bar(BASE + timedelta(minutes=1), "100", "101", "99", "100", volume=None),
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].volume is None

    def test_missing_quote_volume_poisons_the_total(self) -> None:
        source = [
            bar(BASE, "100", "101", "99", "100", quote_volume="1000"),
            bar(BASE + timedelta(minutes=1), "100", "101", "99", "100", quote_volume=None),
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].quote_volume is None

    def test_missing_trade_count_poisons_the_total(self) -> None:
        source = [
            bar(BASE, "100", "101", "99", "100", trades=5),
            bar(BASE + timedelta(minutes=1), "100", "101", "99", "100", trades=None),
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].trades is None

    def test_illegal_rollup_is_refused_and_counted(self) -> None:
        """5m -> 1m is not a rollup; producing bars would be fiction."""
        source = [bar(BASE, "100", "101", "99", "100", interval="5m")]
        rolled, report = rollup_bars(
            source,
            target_interval="1m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled == ()
        assert report.records_rejected == 1
        assert any(k.startswith("ILLEGAL_ROLLUP") for k in report.rejection_reasons)

    def test_inconsistent_ohlc_is_refused(self) -> None:
        source = [bar(BASE, "100", "99", "101", "100")]  # high below low
        rolled, report = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled == ()
        assert report.rejection_reasons == {"OHLC_INCONSISTENT": 1}

    def test_unsorted_input_still_rolls_up_correctly(self) -> None:
        source = [
            bar(BASE + timedelta(minutes=2), "119", "119.5", "80", "81"),
            bar(BASE, "100", "101", "99", "100.5"),
            bar(BASE + timedelta(minutes=1), "100.5", "120", "100", "119"),
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].open == D("100")
        assert rolled[0].close == D("81")

    def test_empty_input_produces_nothing(self) -> None:
        rolled, report = rollup_bars(
            [],
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE,
        )
        assert rolled == ()
        assert report.bars_produced == 0

    def test_naive_bar_timestamp_is_refused(self) -> None:
        naive = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=datetime(2026, 11, 25, 12, 0),  # naive
            close_time=None,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
        )
        rolled, report = rollup_bars(
            [naive],
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert rolled == ()
        assert report.rejection_reasons == {"NAIVE_TIMESTAMP": 1}

    def test_multi_bucket_rollup_keeps_buckets_separate(self) -> None:
        source = [bar(BASE + timedelta(minutes=m), "100", "101", "99", "100", volume="1") for m in range(10)]
        rolled, report = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(hours=1),
        )
        assert len(rolled) == 2
        assert [b.open_time for b in rolled] == [BASE, BASE + timedelta(minutes=5)]
        assert all(b.volume == D("5") for b in rolled)
        assert report.bars_produced == 2

    def test_daily_rollup_buckets_on_utc_calendar_not_24h_blocks(self) -> None:
        """BASE is 12:00 UTC, so 24 hourly bars straddle two UTC days.

        Daily bars must cut on the UTC calendar (00:00), not on elapsed 24-hour blocks from
        the first bar. A 24h-block cut would silently shift every daily bar by 12 hours and
        misalign them against every other data source.
        """
        source = [
            bar(BASE + timedelta(hours=h), "100", "101", "99", "100", interval="1h", volume="1")
            for h in range(24)
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="1d",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=BASE + timedelta(days=2),
        )
        assert len(rolled) == 2
        assert [b.open_time for b in rolled] == [
            datetime(2026, 11, 25, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 26, 0, 0, tzinfo=UTC),
        ]
        # 12 hours fall in each UTC day: 12:00-23:00 on the 25th, 00:00-11:00 on the 26th.
        assert [b.volume for b in rolled] == [D("12"), D("12")]

    def test_daily_rollup_of_a_full_utc_day_is_one_bar(self) -> None:
        midnight = datetime(2026, 11, 25, 0, 0, tzinfo=UTC)
        source = [
            bar(midnight + timedelta(hours=h), "100", "101", "99", "100", interval="1h", volume="1")
            for h in range(24)
        ]
        rolled, _ = rollup_bars(
            source,
            target_interval="1d",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=midnight + timedelta(days=2),
        )
        assert len(rolled) == 1
        assert rolled[0].volume == D("24")
        assert rolled[0].open_time == midnight


class TestMerge:
    def test_confirmed_bar_never_downgraded_by_partial(self) -> None:
        """Re-downloading a range must not degrade settled history."""
        existing = [bar(BASE, "100", "101", "99", "100", confirmed=True)]
        incoming = [bar(BASE, "999", "999", "999", "999", confirmed=False)]
        merged = merge_bars(existing, incoming)
        assert len(merged) == 1
        assert merged[0].close == D("100")
        assert merged[0].confirmed is True

    def test_partial_upgraded_by_confirmed(self) -> None:
        existing = [bar(BASE, "999", "999", "999", "999", confirmed=False)]
        incoming = [bar(BASE, "100", "101", "99", "100", confirmed=True)]
        merged = merge_bars(existing, incoming)
        assert merged[0].close == D("100")
        assert merged[0].confirmed is True

    def test_distinct_intervals_coexist(self) -> None:
        existing = [bar(BASE, "100", "101", "99", "100", interval="1m")]
        incoming = [bar(BASE, "100", "101", "99", "100", interval="5m")]
        merged = merge_bars(existing, incoming)
        assert len(merged) == 2

    def test_merge_is_sorted_by_interval_then_time(self) -> None:
        existing = [bar(BASE + timedelta(minutes=5), "1", "1", "1", "1")]
        incoming = [bar(BASE, "1", "1", "1", "1")]
        merged = merge_bars(existing, incoming)
        assert [b.open_time for b in merged] == [BASE, BASE + timedelta(minutes=5)]


class TestGapDetection:
    def test_contiguous_series_has_no_gaps(self) -> None:
        bars = [bar(BASE + timedelta(minutes=m), "1", "1", "1", "1") for m in range(5)]
        assert find_gaps(bars, interval="1m") == ()

    def test_missing_minutes_are_reported(self) -> None:
        bars = [
            bar(BASE, "1", "1", "1", "1"),
            bar(BASE + timedelta(minutes=3), "1", "1", "1", "1"),
        ]
        gaps = find_gaps(bars, interval="1m")
        assert gaps == (BASE + timedelta(minutes=1), BASE + timedelta(minutes=2))

    def test_single_bar_has_no_gaps(self) -> None:
        assert find_gaps([bar(BASE, "1", "1", "1", "1")], interval="1m") == ()

    def test_empty_series_has_no_gaps(self) -> None:
        assert find_gaps([], interval="1m") == ()

    def test_unsorted_input_is_handled(self) -> None:
        bars = [
            bar(BASE + timedelta(minutes=3), "1", "1", "1", "1"),
            bar(BASE, "1", "1", "1", "1"),
        ]
        assert len(find_gaps(bars, interval="1m")) == 2

    def test_gaps_are_reported_never_filled(self) -> None:
        """The archive must not manufacture the missing bars."""
        bars = [
            bar(BASE, "1", "1", "1", "1"),
            bar(BASE + timedelta(minutes=2), "1", "1", "1", "1"),
        ]
        merged = merge_bars(bars, [])
        assert len(merged) == 2  # still two bars, not three


class TestRollupIdentity:
    """Regression: `rollup_bars` emitted `instrument_id or ""` when identity was not passed.

    The retention ladder (D-024) rolls 1m -> 5m -> 1d. Anonymous output would put every
    instrument's coarser bars in one shared `venue=/symbol=` partition — indistinguishable,
    unfindable by filter, and it would break the per-instrument coverage check that decides
    whether old ticks may be deleted.
    """

    def test_identity_is_inherited_from_the_source_bars(self) -> None:
        source = [bar(BASE + timedelta(minutes=m), "100", "110", "90", "105") for m in range(5)]
        rolled, report = rollup_bars(source, target_interval="5m", now=BASE + timedelta(hours=1))
        assert report.bars_produced == 1
        assert rolled[0].instrument_id == "INS-BTC-USDT-USDT"
        assert rolled[0].venue == "BYBIT"
        assert rolled[0].venue_symbol == "BTCUSDT"

    def test_inherited_identity_makes_the_bar_findable_by_its_own_key(self) -> None:
        """The whole point: a rolled-up bar must still answer to who it belongs to."""
        source = [bar(BASE + timedelta(minutes=m), "100", "110", "90", "105") for m in range(5)]
        (rolled,) = rollup_bars(source, target_interval="5m", now=BASE + timedelta(hours=1))[0]
        assert bar_identity(rolled) == (
            "INS-BTC-USDT-USDT",
            "BYBIT",
            "BTCUSDT",
            "5m",
            BASE,
        )

    def test_an_explicit_override_still_wins(self) -> None:
        source = [bar(BASE + timedelta(minutes=m), "100", "110", "90", "105") for m in range(5)]
        rolled, _ = rollup_bars(
            source,
            target_interval="5m",
            instrument_id="INS-OVERRIDE",
            venue="OTHER",
            venue_symbol="OTHERSYM",
            now=BASE + timedelta(hours=1),
        )
        assert rolled[0].instrument_id == "INS-OVERRIDE"
        assert rolled[0].venue == "OTHER"
        assert rolled[0].venue_symbol == "OTHERSYM"

    def test_a_partial_override_fills_only_the_missing_field(self) -> None:
        source = [bar(BASE + timedelta(minutes=m), "100", "110", "90", "105") for m in range(5)]
        rolled, _ = rollup_bars(
            source, target_interval="5m", venue_symbol="RENAMED", now=BASE + timedelta(hours=1)
        )
        assert rolled[0].venue_symbol == "RENAMED"
        assert rolled[0].instrument_id == "INS-BTC-USDT-USDT"  # inherited
        assert rolled[0].venue == "BYBIT"  # inherited

    def test_sources_spanning_two_instruments_are_refused_not_merged(self) -> None:
        """Guessing here would label one instrument's prices as another's."""
        source = [
            bar(BASE, "100", "110", "90", "105"),
            dataclasses.replace(
                bar(BASE + timedelta(minutes=1), "50", "55", "45", "52"),
                instrument_id="INS-ETH-USDT-USDT",
                venue_symbol="ETHUSDT",
            ),
        ]
        rolled, report = rollup_bars(source, target_interval="5m", now=BASE + timedelta(hours=1))
        assert rolled == ()
        assert report.bars_produced == 0
        assert report.records_rejected == 2
        assert any(k.startswith("IDENTITY_AMBIGUOUS") for k in report.rejection_reasons)
        assert "2 identities" in next(iter(report.rejection_reasons))

    def test_two_venues_for_the_same_instrument_are_also_refused(self) -> None:
        """Same instrument, different venue = different price series. Never blend them."""
        source = [
            bar(BASE, "100", "110", "90", "105"),
            dataclasses.replace(bar(BASE + timedelta(minutes=1), "50", "55", "45", "52"), venue="OKX"),
        ]
        rolled, report = rollup_bars(source, target_interval="5m", now=BASE + timedelta(hours=1))
        assert rolled == ()
        assert any(k.startswith("IDENTITY_AMBIGUOUS") for k in report.rejection_reasons)

    def test_anonymous_sources_are_refused_rather_than_rolled_up(self) -> None:
        source = [
            dataclasses.replace(
                bar(BASE + timedelta(minutes=m), "100", "110", "90", "105"),
                instrument_id="",
                venue="",
                venue_symbol="",
            )
            for m in range(5)
        ]
        rolled, report = rollup_bars(source, target_interval="5m", now=BASE + timedelta(hours=1))
        assert rolled == ()
        assert any("no identity to inherit" in k for k in report.rejection_reasons)

    def test_an_empty_source_produces_no_bars_and_no_crash(self) -> None:
        rolled, report = rollup_bars([], target_interval="5m", now=BASE + timedelta(hours=1))
        assert rolled == ()
        assert report.bars_produced == 0
        assert report.source_count == 0

    def test_retention_rollup_still_produces_identified_bars(self) -> None:
        """The D-024 ladder path passes identity explicitly, so it is unaffected."""
        from nexus.archive.retention import RetentionPolicy

        policy = RetentionPolicy()
        source = [bar(BASE + timedelta(minutes=m), "100", "110", "90", "105") for m in range(5)]
        rolled, action = policy.rollup(
            source,
            target_interval="5m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=BASE + timedelta(hours=1),
        )
        assert action.action == "ROLLUP"
        assert rolled[0].instrument_id == "INS-BTC-USDT-USDT"
        assert rolled[0].venue == "BYBIT"
