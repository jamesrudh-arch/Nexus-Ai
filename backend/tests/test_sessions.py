"""Market calendars (Phase 3): DST correctness, honest confidence, fail-closed unknowns.

The property that matters: a feed going quiet on a Saturday must be labelled *closed by
calendar*, while the same silence on a Tuesday must be labelled *stale*. Getting that wrong
either cries wolf every weekend or hides a real outage.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexus.domain.instrument import AssetClass
from nexus.instruments.sessions import (
    EXCHANGE_HOURS,
    CalendarConfidence,
    ExchangeHours,
    HolidaySet,
    MarketCalendar,
    SessionKind,
    asset_class_sessions,
    describe_exchange,
    fx_week_is_open,
)

NY = ZoneInfo("America/New_York")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.fixture
def calendar() -> MarketCalendar:
    return MarketCalendar()


class TestAssetClassSessions:
    @pytest.mark.parametrize(
        "asset_class",
        [
            AssetClass.CRYPTO_SPOT,
            AssetClass.CRYPTO_PERP,
            AssetClass.CRYPTO_FUTURES,
            AssetClass.CRYPTO_OPTIONS,
        ],
    )
    def test_crypto_is_continuous(self, asset_class: AssetClass) -> None:
        assert asset_class_sessions(asset_class) is SessionKind.CONTINUOUS_24_7

    @pytest.mark.parametrize("asset_class", [AssetClass.FX_SPOT, AssetClass.FX_CFD, AssetClass.METALS])
    def test_fx_and_metals_are_24x5(self, asset_class: AssetClass) -> None:
        assert asset_class_sessions(asset_class) is SessionKind.FX_24X5

    @pytest.mark.parametrize(
        "asset_class",
        [
            AssetClass.EQUITIES,
            AssetClass.ETF,
            AssetClass.INDICES,
            AssetClass.FUTURES,
            AssetClass.OPTIONS,
            AssetClass.COMMODITIES,
        ],
    )
    def test_exchange_traded_classes_need_a_session_table(self, asset_class: AssetClass) -> None:
        assert asset_class_sessions(asset_class) is SessionKind.EXCHANGE_REGULAR

    def test_fixed_income_has_no_session_table_and_is_closed(self) -> None:
        """An asset class with no rule is treated as closed, never as open."""
        assert asset_class_sessions(AssetClass.FIXED_INCOME) is SessionKind.CLOSED


class TestCryptoSession:
    @pytest.mark.parametrize(
        "moment",
        [
            utc(2026, 11, 21, 12, 0),  # Saturday
            utc(2026, 11, 22, 3, 0),  # Sunday
            utc(2026, 11, 25, 12, 0),  # Wednesday
            utc(2026, 1, 1, 0, 0),  # New Year — crypto does not care
            utc(2026, 12, 25, 23, 59),  # Christmas
        ],
    )
    def test_crypto_is_always_open(self, calendar: MarketCalendar, moment: datetime) -> None:
        status = calendar.status(
            instrument_id="INS-BTC-USDT-USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            exchange="BYBIT",
            now=moment,
        )
        assert status.is_open is True
        assert status.confidence is CalendarConfidence.FULL
        assert status.kind is SessionKind.CONTINUOUS_24_7

    def test_crypto_has_no_next_close(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-BTC-USDT-USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            now=utc(2026, 11, 25, 12, 0),
        )
        assert status.next_close is None


class TestFxWeeklyWindow:
    def test_midweek_is_open(self) -> None:
        assert fx_week_is_open(utc(2026, 11, 25, 12, 0)) is True  # Wednesday

    def test_saturday_is_closed(self) -> None:
        assert fx_week_is_open(utc(2026, 11, 21, 12, 0)) is False

    def test_sunday_before_new_york_open_is_closed(self) -> None:
        # Sunday 21:00 UTC in November is 16:00 New York — one hour before the 17:00 open.
        assert fx_week_is_open(utc(2026, 11, 22, 21, 0)) is False

    def test_sunday_after_new_york_open_is_open(self) -> None:
        # Sunday 22:30 UTC in November is 17:30 New York — after the open.
        assert fx_week_is_open(utc(2026, 11, 22, 22, 30)) is True

    def test_friday_before_close_is_open(self) -> None:
        assert fx_week_is_open(utc(2026, 11, 20, 21, 0)) is True  # Friday 16:00 NY

    def test_friday_after_close_is_closed(self) -> None:
        assert fx_week_is_open(utc(2026, 11, 20, 23, 0)) is False  # Friday 18:00 NY


class TestFxDstCorrectness:
    """The window is defined in New York time, so the UTC instant must shift with DST."""

    def test_winter_open_is_22_utc(self) -> None:
        # 22 Nov 2026 is EST (UTC-5): 17:00 NY == 22:00 UTC.
        assert fx_week_is_open(utc(2026, 11, 22, 21, 59)) is False
        assert fx_week_is_open(utc(2026, 11, 22, 22, 0)) is True

    def test_summer_open_is_21_utc(self) -> None:
        # 21 Jun 2026 is EDT (UTC-4): 17:00 NY == 21:00 UTC.
        assert fx_week_is_open(utc(2026, 6, 21, 20, 59)) is False
        assert fx_week_is_open(utc(2026, 6, 21, 21, 0)) is True

    def test_summer_friday_close_is_21_utc(self) -> None:
        # Friday 19 Jun 2026: closes 17:00 NY == 21:00 UTC.
        assert fx_week_is_open(utc(2026, 6, 19, 20, 59)) is True
        assert fx_week_is_open(utc(2026, 6, 19, 21, 0)) is False

    def test_winter_friday_close_is_22_utc(self) -> None:
        # Friday 20 Nov 2026: closes 17:00 NY == 22:00 UTC.
        assert fx_week_is_open(utc(2026, 11, 20, 21, 59)) is True
        assert fx_week_is_open(utc(2026, 11, 20, 22, 0)) is False

    def test_the_utc_instant_actually_moves_between_seasons(self) -> None:
        """Guards against a regression to a hard-coded UTC offset."""
        june_close = utc(2026, 6, 19, 21, 0)
        november_close = utc(2026, 11, 20, 21, 0)
        assert fx_week_is_open(june_close) is False
        assert fx_week_is_open(november_close) is True


class TestFxStatusReporting:
    def test_weekend_silence_is_closed_by_calendar_not_stale(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-EUR-USD",
            asset_class=AssetClass.FX_SPOT,
            exchange="MT5",
            now=utc(2026, 11, 21, 12, 0),  # Saturday
        )
        assert status.is_open is False
        assert status.is_closed_by_calendar is True
        assert "outside FX weekly window" in status.reasons[0]

    def test_fx_confidence_is_partial_without_bank_holidays(self, calendar: MarketCalendar) -> None:
        """Honest: the weekday rule is known, the bank-holiday list is not."""
        status = calendar.status(
            instrument_id="INS-EUR-USD",
            asset_class=AssetClass.FX_SPOT,
            now=utc(2026, 11, 25, 12, 0),
        )
        assert status.is_open is True
        assert status.confidence is CalendarConfidence.PARTIAL
        assert any("holiday coverage: none" in r for r in status.reasons)

    def test_closed_fx_reports_a_next_open(self, calendar: MarketCalendar) -> None:
        saturday = utc(2026, 11, 21, 12, 0)
        status = calendar.status(
            instrument_id="INS-EUR-USD",
            asset_class=AssetClass.FX_SPOT,
            now=saturday,
        )
        assert status.next_open is not None
        assert status.next_open > saturday
        # The next open is Sunday 17:00 New York == 22:00 UTC in November.
        assert status.next_open == utc(2026, 11, 22, 22, 0)
        assert status.next_close is None

    def test_open_fx_reports_a_next_close(self, calendar: MarketCalendar) -> None:
        wednesday = utc(2026, 11, 25, 12, 0)
        status = calendar.status(
            instrument_id="INS-EUR-USD",
            asset_class=AssetClass.FX_SPOT,
            now=wednesday,
        )
        assert status.is_open is True
        assert status.next_close is not None
        assert status.next_close == utc(2026, 11, 20 + 0, 22, 0) or status.next_close > wednesday
        assert status.next_open is None


class TestExchangeSessions:
    def test_nyse_open_during_regular_hours(self, calendar: MarketCalendar) -> None:
        # 25 Nov 2026 14:30 UTC == 09:30 New York, the open.
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 11, 25, 14, 30),
        )
        assert status.is_open is True
        assert status.kind is SessionKind.EXCHANGE_REGULAR

    def test_nyse_closed_before_open(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 11, 25, 14, 29),
        )
        assert status.is_open is False
        assert status.next_open == utc(2026, 11, 25, 14, 30)

    def test_nyse_closed_at_and_after_the_close(self, calendar: MarketCalendar) -> None:
        # 21:00 UTC == 16:00 New York; the close is exclusive.
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 11, 25, 21, 0),
        )
        assert status.is_open is False

    def test_nyse_weekend_closed(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 11, 21, 15, 0),  # Saturday
        )
        assert status.is_open is False
        assert status.next_open == utc(2026, 11, 23, 14, 30)  # Monday open

    def test_ngx_uses_lagos_time(self, calendar: MarketCalendar) -> None:
        """Nigeria's own exchange: Lagos is UTC+1 year-round, no DST."""
        hours = EXCHANGE_HOURS["NGX"]
        assert hours.timezone == "Africa/Lagos"
        # 09:30 Lagos == 08:30 UTC.
        open_status = calendar.status(
            instrument_id="INS-GTC-NG",
            asset_class=AssetClass.EQUITIES,
            exchange="NGX",
            now=utc(2026, 11, 25, 8, 30),
        )
        assert open_status.is_open is True
        before = calendar.status(
            instrument_id="INS-GTC-NG",
            asset_class=AssetClass.EQUITIES,
            exchange="NGX",
            now=utc(2026, 11, 25, 8, 29),
        )
        assert before.is_open is False

    def test_unknown_exchange_fails_closed(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-MYSTERY",
            asset_class=AssetClass.EQUITIES,
            exchange="NOT_A_REAL_EXCHANGE",
            now=utc(2026, 11, 25, 15, 0),
        )
        assert status.is_open is False
        assert status.confidence is CalendarConfidence.UNKNOWN
        assert status.is_closed_by_calendar is False  # unknown is NOT a trustworthy "closed"
        assert "no session table" in status.reasons[0]

    def test_missing_exchange_fails_closed(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-MYSTERY",
            asset_class=AssetClass.EQUITIES,
            exchange=None,
            now=utc(2026, 11, 25, 15, 0),
        )
        assert status.is_open is False
        assert status.confidence is CalendarConfidence.UNKNOWN
        assert "no exchange recorded" in status.reasons[0]

    def test_unsupported_asset_class_fails_closed(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-BOND",
            asset_class=AssetClass.FIXED_INCOME,
            exchange="NYSE",
            now=utc(2026, 11, 25, 15, 0),
        )
        assert status.is_open is False
        assert status.confidence is CalendarConfidence.UNKNOWN
        assert status.kind is SessionKind.CLOSED


class TestHolidays:
    def test_holiday_closes_the_exchange_and_is_full_confidence(self) -> None:
        holidays = HolidaySet([("NYSE", date(2026, 11, 26))])  # Thanksgiving
        calendar = MarketCalendar(holidays=holidays)
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 11, 26, 15, 0),  # a Thursday, normally open
        )
        assert status.is_open is False
        assert status.confidence is CalendarConfidence.FULL
        assert "holiday" in status.reasons[0]
        assert status.next_open == utc(2026, 11, 27, 14, 30)  # Friday open

    def test_holiday_set_skips_to_the_next_non_holiday(self) -> None:
        holidays = HolidaySet(
            [
                ("NYSE", date(2026, 12, 24)),
                ("NYSE", date(2026, 12, 25)),
            ],
        )
        calendar = MarketCalendar(holidays=holidays)
        status = calendar.status(
            instrument_id="INS-AAPL",
            asset_class=AssetClass.EQUITIES,
            exchange="NYSE",
            now=utc(2026, 12, 24, 15, 0),
        )
        assert status.is_open is False
        # 24 and 25 are holidays; 26-27 are the weekend; next open is Monday 28th.
        assert status.next_open == utc(2026, 12, 28, 14, 30)

    def test_coverage_is_declared_not_assumed(self) -> None:
        holidays = HolidaySet([("NYSE", date(2026, 11, 26))])
        assert holidays.covers("NYSE") is True
        assert holidays.covers("LSE") is False
        assert holidays.covers("nyse") is True  # case-insensitive exchange key
        assert holidays.count("NYSE") == 1
        assert holidays.count("LSE") == 0

    def test_from_mapping_parses_iso_dates(self) -> None:
        holidays = HolidaySet.from_mapping({"NYSE": ["2026-01-01", "2026-07-03"], "LSE": ["2026-12-25"]})
        assert holidays.is_holiday("NYSE", date(2026, 1, 1)) is True
        assert holidays.is_holiday("NYSE", date(2026, 1, 2)) is False
        assert holidays.is_holiday("LSE", date(2026, 12, 25)) is True
        assert holidays.exchanges() == ("LSE", "NYSE")

    def test_add_extends_an_existing_exchange(self) -> None:
        holidays = HolidaySet()
        assert holidays.covers("NYSE") is False
        holidays.add("NYSE", [date(2026, 11, 26)])
        assert holidays.covers("NYSE") is True
        assert holidays.count("NYSE") == 1


class TestExchangeHours:
    def test_contains_respects_weekdays_and_times(self) -> None:
        hours = ExchangeHours("TEST", "UTC", time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}))
        wednesday_open = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)
        wednesday_close = datetime(2026, 11, 25, 17, 0, tzinfo=UTC)
        saturday = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
        assert hours.contains(wednesday_open) is True
        assert hours.contains(wednesday_open + timedelta(hours=4)) is True
        assert hours.contains(wednesday_close) is False  # close is exclusive
        assert hours.contains(saturday) is False

    def test_tz_property_resolves(self) -> None:
        assert EXCHANGE_HOURS["LSE"].tz == ZoneInfo("Europe/London")


class TestSerialization:
    def test_status_to_dict_is_utc_and_json_safe(self, calendar: MarketCalendar) -> None:
        status = calendar.status(
            instrument_id="INS-BTC-USDT-USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            now=utc(2026, 11, 25, 12, 0),
        )
        payload = status.to_dict()
        assert payload["is_open"] is True
        assert payload["kind"] == "CONTINUOUS_24_7"
        assert payload["confidence"] == "FULL"
        assert payload["checked_at"].endswith("Z")
        assert payload["next_open"] is None

    def test_describe_exchange_reports_unknown_honestly(self) -> None:
        known = describe_exchange("NYSE")
        assert known["known"] is True
        assert known["open"] == "09:30"
        assert known["close"] == "16:00"
        assert known["timezone"] == "America/New_York"

        unknown = describe_exchange("NOT_REAL")
        assert unknown == {"exchange": "NOT_REAL", "known": False}

    def test_describe_exchange_is_case_insensitive(self) -> None:
        assert describe_exchange("nyse")["known"] is True
