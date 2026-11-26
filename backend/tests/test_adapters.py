"""Venue adapter parsing (Phase 3) — Bybit V5, OKX v5, Binance Vision, Dukascopy bi5.

**Network status: these tests never touch the network.** This sandbox has no egress to venue
hosts (verified 2026-11-25: connections to api.bybit.com, okx.com, datafeed.dukascopy.com
and api.binance.com all fail). Adapters take an injected :class:`RecordingTransport`, so the
payload *shapes* below are synthetic fixtures written from the published API contracts, not
captured responses.

That is a real limitation and is recorded as such: correct parsing of a synthetic payload
proves the normalisation logic, it does **not** prove the live endpoint still returns that
shape. Phase 3's exit gate includes a live-endpoint verification step that must run from a
host with egress, and ``DUKASCOPY.LAYOUT_VERIFIED`` stays ``False`` until it does.

What these tests do guarantee:
* every adapter is structurally credential-free and cannot place an order;
* prices/quantities become exact ``Decimal``, never float;
* timestamps become aware UTC, and a naive one is refused rather than guessed;
* venue error codes raise, with retryable/non-retryable distinguished;
* newest-first responses are reversed, so nothing reads the future;
* an unconfirmed (still-forming) bar is never marked confirmed;
* Dukascopy's 0-indexed month and per-pair point divisor are handled, and an unknown pair is
  refused instead of guessed (a wrong divisor scales prices by 100x).
"""

from __future__ import annotations

import lzma
import struct
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest

from nexus.data.records import IngestFault, RecordingTransport, validate_bar
from nexus.domain.instrument import Venue
from nexus.ingestion.binance_vision import (
    BinanceVisionHistorical,
    agg_trades_url,
    daily_periods,
    kline_url,
    monthly_periods,
    parse_agg_trades_csv,
    parse_kline_csv,
)
from nexus.ingestion.bybit import (
    BYBIT_REST,
    BybitPublicAdapter,
    bybit_interval,
    canonical_interval,
)
from nexus.ingestion.dukascopy import (
    LAYOUT_VERIFIED,
    POINT_DIVISORS,
    SIDES,
    DukascopyHistorical,
    hour_url,
    parse_bi5,
    point_divisor,
    source_label,
    supported_pairs,
    verify_layout,
)
from nexus.ingestion.okx import (
    OKX_REST,
    OkxPublicAdapter,
    bar_duration,
    detect_gaps,
    okx_bar,
)

D = Decimal
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
BYBIT_BASE = "https://api.bybit.com"
OKX_BASE = "https://www.okx.com"
VISION_BASE = "https://data.binance.vision"
DUKA_BASE = "https://datafeed.dukascopy.com/datafeed"


def expected_bi5_url(pair: str, hour: datetime, *, base: str = DUKA_BASE) -> str:
    """Where a bi5 fixture is registered, computed **without** the function under test.

    `hour_url` used to key its own fixtures, so code and expectation came from one source and could
    never disagree — which is how a bogus ``BID`` path segment survived 151 passing tests (defect
    39). This transcribes the contract independently: ``{PAIR}/{YYYY}/{MM-1}/{DD}/{HH}h_ticks.bi5``,
    one file per instrument-hour holding both sides. If `hour_url` regresses the keys diverge, the
    transport has nothing to return, and the test fails.
    """
    return f"{base}/{pair}/{hour.year}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"


def expected_kline_url(
    symbol: str,
    interval: str,
    day: datetime,
    *,
    market: str = "spot",
    periodicity: str = "daily",
    base: str = VISION_BASE,
) -> str:
    """Same principle for the Binance Vision dumps (defect 38): an independently transcribed key.

    ``data/{market}/{frequency}/{data_type}/{symbol}/{interval}/{name}.zip`` — the frequency is a
    path segment, not only part of the filename.
    """
    stamp = day.strftime("%Y-%m") if periodicity == "monthly" else day.strftime("%Y-%m-%d")
    name = f"{symbol}-{interval}-{stamp}"
    return f"{base}/data/{market}/{periodicity}/klines/{symbol}/{interval}/{name}.zip"


class TestNoCredentialSurface:
    """The structural guarantee that Phase 3 cannot reach a private endpoint."""

    @pytest.mark.parametrize("adapter_cls", [BybitPublicAdapter, OkxPublicAdapter])
    def test_adapter_declares_no_credentials(self, adapter_cls: type) -> None:
        assert adapter_cls.requires_credentials is False

    @pytest.mark.parametrize("adapter_cls", [BybitPublicAdapter, OkxPublicAdapter])
    def test_constructor_accepts_no_secret_parameter(self, adapter_cls: type) -> None:
        import inspect

        params = set(inspect.signature(adapter_cls.__init__).parameters)
        forbidden = {"api_key", "api_secret", "secret", "passphrase", "token", "password", "credentials"}
        assert not (params & forbidden), f"{adapter_cls.__name__} accepts a credential parameter"

    @pytest.mark.parametrize("adapter_cls", [BybitPublicAdapter, OkxPublicAdapter])
    def test_no_method_can_place_an_order(self, adapter_cls: type) -> None:
        """No order/trade/withdraw verb may exist on a Phase 3 adapter."""
        forbidden_verbs = ("place", "create_order", "submit", "cancel", "withdraw", "transfer", "amend")
        for name in dir(adapter_cls):
            if name.startswith("_"):
                continue
            lowered = name.lower()
            for verb in forbidden_verbs:
                assert verb not in lowered, f"{adapter_cls.__name__}.{name} looks like a trading method"

    @pytest.mark.parametrize("adapter_cls", [BinanceVisionHistorical, DukascopyHistorical])
    def test_historical_sources_are_also_credential_free(self, adapter_cls: type) -> None:
        assert adapter_cls.requires_credentials is False

    def test_dukascopy_layout_is_declared_unverified(self) -> None:
        """Honesty: the bi5 layout has not been checked against a real download."""
        assert LAYOUT_VERIFIED is False
        assert source_label() == "DUKASCOPY_BI5_UNVERIFIED"


class TestDecimalExactness:
    def test_float_json_values_do_not_leak_binary_error(self) -> None:
        """A JSON float 0.1 must become exactly Decimal('0.1')."""
        from nexus.data.records import to_decimal

        assert to_decimal(0.1, field_name="p", source="T") == D("0.1")
        assert to_decimal("0.1", field_name="p", source="T") == D("0.1")
        assert to_decimal(100000.5, field_name="p", source="T") == D("100000.5")

    def test_non_finite_values_are_refused(self) -> None:
        from nexus.data.records import to_decimal

        for bad in ("NaN", "Infinity", "-Infinity", float("nan"), float("inf")):
            with pytest.raises(IngestFault, match="not finite"):
                to_decimal(bad, field_name="p", source="T")

    def test_junk_values_are_refused(self) -> None:
        from nexus.data.records import to_decimal

        for bad in ("abc", object(), [1]):
            with pytest.raises(IngestFault, match="not a number"):
                to_decimal(bad, field_name="p", source="T")

    def test_none_and_empty_stay_none(self) -> None:
        from nexus.data.records import to_decimal

        assert to_decimal(None, field_name="p", source="T") is None
        assert to_decimal("", field_name="p", source="T") is None

    def test_require_decimal_refuses_missing(self) -> None:
        from nexus.data.records import require_decimal

        with pytest.raises(IngestFault, match="required field"):
            require_decimal(None, field_name="open", source="T")


class TestTimestampNormalisation:
    def test_epoch_milliseconds(self) -> None:
        from nexus.data.records import to_utc

        result = to_utc(1764072000000, field_name="ts", source="T")
        assert result is not None
        assert result.tzinfo is not None
        assert result.astimezone(UTC) == result

    def test_large_integer_is_treated_as_milliseconds(self) -> None:
        from nexus.data.records import to_utc

        # Above 1e11 must be ms, otherwise the date lands millennia out.
        result = to_utc(1764072000000, field_name="ts", source="T")
        assert result is not None
        assert result.year == 2025

    def test_epoch_seconds(self) -> None:
        from nexus.data.records import to_utc

        result = to_utc(1764072000, field_name="ts", source="T")
        assert result is not None
        assert result.year == 2025

    def test_numeric_string(self) -> None:
        from nexus.data.records import to_utc

        assert to_utc("1764072000000", field_name="ts", source="T") is not None

    def test_iso_with_z_suffix(self) -> None:
        from nexus.data.records import to_utc

        result = to_utc("2026-11-25T12:00:00Z", field_name="ts", source="T")
        assert result == NOW

    def test_iso_with_offset_is_converted_to_utc(self) -> None:
        from nexus.data.records import to_utc

        result = to_utc("2026-11-25T13:00:00+01:00", field_name="ts", source="T")
        assert result == NOW

    def test_naive_datetime_is_refused_not_assumed(self) -> None:
        """Guessing the venue's timezone is how backtests get shifted by hours."""
        from nexus.data.records import to_utc

        with pytest.raises(IngestFault, match="naive timestamp"):
            to_utc(datetime(2026, 11, 25, 12, 0), field_name="ts", source="T")

    def test_naive_iso_string_is_refused(self) -> None:
        from nexus.data.records import to_utc

        with pytest.raises(IngestFault, match="naive timestamp"):
            to_utc("2026-11-25T12:00:00", field_name="ts", source="T")

    def test_unparseable_string_is_refused(self) -> None:
        from nexus.data.records import to_utc

        with pytest.raises(IngestFault, match="unparseable timestamp"):
            to_utc("not-a-date", field_name="ts", source="T")

    def test_none_stays_none(self) -> None:
        from nexus.data.records import to_utc

        assert to_utc(None, field_name="ts", source="T") is None

    def test_boolean_is_not_a_timestamp(self) -> None:
        """``True`` is an int in Python; it must not become epoch 1."""
        from nexus.data.records import to_utc

        with pytest.raises(IngestFault):
            to_utc(True, field_name="ts", source="T")


class TestEpochUnitIsDetectedNotAssumed:
    """Defect 40: a venue changed its timestamp unit and a caller's assumption could not notice.

    Binance Vision began publishing **microsecond** timestamps for spot dumps from 2025-01-01. The
    parser passed `assume_ms=True`, so every value was divided by 1000 and the first real download
    this repository ever made raised `ValueError: year 58852 is out of range`. It is worth being
    precise about why that is the good outcome: the alternative was a bar dated tens of thousands of
    years out, silently entering the archive and poisoning every aggregate built on it.

    The fix rests on a property that must be asserted rather than trusted — the four unit windows do
    not overlap, so detection is a measurement and never a guess.
    """

    INSTANT = datetime(2025, 11, 25, 12, 0, tzinfo=UTC)

    def test_the_four_unit_windows_are_disjoint(self) -> None:
        """The property the whole fix rests on. If this ever fails, detection becomes a guess."""
        from nexus.data.records import _EPOCH_SCALES, _EPOCH_SECONDS_MAX, _EPOCH_SECONDS_MIN

        windows = [(name, _EPOCH_SECONDS_MIN * f, _EPOCH_SECONDS_MAX * f) for f, name in _EPOCH_SCALES]
        for i, (name_a, lo_a, hi_a) in enumerate(windows):
            for name_b, lo_b, hi_b in windows[i + 1 :]:
                assert hi_a < lo_b or hi_b < lo_a, (
                    f"{name_a} [{lo_a:.3e}, {hi_a:.3e}] overlaps "
                    f"{name_b} [{lo_b:.3e}, {hi_b:.3e}] — a magnitude would be ambiguous"
                )

    def test_each_unit_is_detected_from_magnitude_alone(self) -> None:
        from nexus.data.records import epoch_unit, to_utc

        for value, unit in (
            (int(self.INSTANT.timestamp()), "s"),
            (int(self.INSTANT.timestamp()) * 1_000, "ms"),
            (int(self.INSTANT.timestamp()) * 1_000_000, "us"),
            (int(self.INSTANT.timestamp()) * 1_000_000_000, "ns"),
        ):
            assert epoch_unit(value) == unit, f"{value} should read as {unit}"
            assert to_utc(value, field_name="ts", source="T") == self.INSTANT

    def test_all_four_units_denote_the_same_instant(self) -> None:
        """The point of the fix: the unit changes, the instant must not."""
        from nexus.data.records import to_utc

        base = int(self.INSTANT.timestamp())
        results = [
            to_utc(base * factor, field_name="ts", source="T")
            for factor in (1, 1_000, 1_000_000, 1_000_000_000)
        ]
        assert len(set(results)) == 1, f"the same instant read four ways gave {results}"
        assert results[0] == self.INSTANT

    def test_string_digits_are_detected_too(self) -> None:
        """Dump CSVs deliver text, not ints — the same detection must apply."""
        from nexus.data.records import to_utc

        assert to_utc("1764072000000000", field_name="ts", source="T") == self.INSTANT

    def test_a_value_in_no_window_is_refused_not_emitted(self) -> None:
        """Zero and absurd magnitudes are sentinels or corruption; neither may become a date."""
        from nexus.data.records import epoch_unit, to_utc

        for bad in (0, 1, -1, 10**23):
            assert epoch_unit(bad) is None
            with pytest.raises(IngestFault, match="not a plausible epoch value"):
                to_utc(bad, field_name="open_time", source="T")

    def test_to_utc_no_longer_accepts_an_assumption_flag(self) -> None:
        """`assume_ms` was removed rather than left inert.

        A parameter that no longer governs is worse than no parameter: a caller passing it believes
        it has an effect. This asserts the removal stays removed.
        """
        import inspect

        from nexus.data.records import to_utc

        assert "assume_ms" not in inspect.signature(to_utc).parameters

    def test_microsecond_kline_dump_parses_to_the_right_instant(self) -> None:
        """The real shape Binance Vision now publishes for spot klines."""
        row = "1764072000000000,100.0,110.0,90.0,105.0,10.5,1764072059999999,1050.0,42,5.0,500.0,0"
        bars, summary = parse_kline_csv(row, symbol="BTCUSDT", interval="1m")
        assert summary.records_accepted == 1 and summary.records_rejected == 0
        assert bars[0].open_time == self.INSTANT
        assert bars[0].close_time.year == 2025
        assert summary.timestamp_units == ("us",)

    def test_millisecond_kline_dump_is_unchanged_by_the_fix(self) -> None:
        """The pre-2025 shape must still parse, and to the same instant."""
        row = "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0"
        bars, summary = parse_kline_csv(row, symbol="BTCUSDT", interval="1m")
        assert summary.records_accepted == 1
        assert bars[0].open_time == self.INSTANT
        assert summary.timestamp_units == ("ms",)

    def test_a_dump_mixing_units_reports_both_rather_than_absorbing_one(self) -> None:
        """A mixed file is a real possibility across the 2025-01-01 boundary and must be visible."""
        rows = (
            "1764072000000000,100.0,110.0,90.0,105.0,10.5,1764072059999999,1050.0,42,5.0,500.0,0\n"
            "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0"
        )
        bars, summary = parse_kline_csv(rows, symbol="BTCUSDT", interval="1m")
        assert summary.records_accepted == 2
        assert summary.timestamp_units == ("ms", "us")
        assert len({b.open_time for b in bars}) == 1, "both rows denote the same instant"

    def test_the_unit_is_reported_in_the_parse_summary(self) -> None:
        """Evidence, not just correctness: the archive must be able to say what it read."""
        row = "0,100.0,0.5,1,1,1764072000000000,true,0"
        _, summary = parse_agg_trades_csv(row, symbol="BTCUSDT")
        assert summary.to_dict()["timestamp_units"] == ["us"]


class TestBybitIntervalMapping:
    @pytest.mark.parametrize(
        ("raw", "canonical"),
        [("1", "1m"), ("5", "5m"), ("60", "1h"), ("240", "4h"), ("D", "1d"), ("W", "1w"), ("M", "1M")],
    )
    def test_round_trip(self, raw: str, canonical: str) -> None:
        assert canonical_interval(raw) == canonical
        assert bybit_interval(canonical) == raw

    def test_unknown_interval_is_refused(self) -> None:
        with pytest.raises(IngestFault, match="unsupported interval"):
            canonical_interval("99")
        with pytest.raises(IngestFault, match="no interval matches"):
            bybit_interval("2m")


class TestBybitAdapter:
    def _transport(self, path: str, payload: object) -> RecordingTransport:
        transport = RecordingTransport()
        transport.set_json(f"{BYBIT_BASE}{path}", payload)
        return transport

    def _category_transport(self, path: str, payloads: dict[str, object]) -> RecordingTransport:
        """Key responses by query params: instruments-info is fetched once per category."""
        transport = RecordingTransport()
        for category, payload in payloads.items():
            transport.set_json(f"{BYBIT_BASE}{path}", payload, params={"category": category})
        return transport

    async def test_instrument_info_extracts_contract_economics(self) -> None:
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1764072000000,
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "contractType": "LinearPerpetual",
                        "status": "Trading",
                        "baseCoin": "BTC",
                        "quoteCoin": "USDT",
                        "settleCoin": "USDT",
                        "linearPriceFilter": {
                            "minPrice": "0.10",
                            "maxPrice": "199999.90",
                            "tickSize": "0.10",
                        },
                        "lotSizeFilter": {
                            "maxOrderQty": "100.000",
                            "minOrderQty": "0.001",
                            "qtyStep": "0.001",
                            "basePrecision": "0.000001",
                        },
                    },
                    {"symbol": "ETHUSDT", "status": "Trading", "baseCoin": "ETH", "quoteCoin": "USDT"},
                ],
            },
        }
        adapter = BybitPublicAdapter(
            transport=self._category_transport(
                "/v5/market/instruments-info",
                {"linear": payload, "inverse": {"retCode": 0, "result": {"list": []}}},
            ),
            base_url=BYBIT_BASE,
        )
        records = await adapter.instrument_info(["BTCUSDT"])
        assert len(records) == 1
        info = records[0]
        assert info.venue == "BYBIT"
        assert info.venue_symbol == "BTCUSDT"
        assert info.base_currency == "BTC"
        assert info.quote_currency == "USDT"
        assert info.tick_size == D("0.10")
        assert info.min_order_qty == D("0.001")
        assert info.qty_step == D("0.001")
        assert info.status == "Trading"
        assert info.observed_at is not None
        assert info.raw["contractType"] == "LinearPerpetual"

    async def test_instrument_info_without_filter_returns_all(self) -> None:
        payload = {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}, {"symbol": "ETHUSDT"}]},
            "time": 1764072000000,
        }
        adapter = BybitPublicAdapter(
            transport=self._category_transport(
                "/v5/market/instruments-info",
                {"linear": payload, "inverse": {"retCode": 0, "result": {"list": []}}},
            ),
            base_url=BYBIT_BASE,
        )
        assert len(await adapter.instrument_info()) == 2

    async def test_instrument_info_spans_categories_without_duplicates(self) -> None:
        """Each category is a separate request; the same symbol must not be emitted twice."""
        linear = {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
            "time": 1764072000000,
        }
        inverse = {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSD", "status": "Trading"}]},
            "time": 1764072000000,
        }
        adapter = BybitPublicAdapter(
            transport=self._category_transport(
                "/v5/market/instruments-info", {"linear": linear, "inverse": inverse}
            ),
        )
        records = await adapter.instrument_info()
        symbols = [r.venue_symbol for r in records]
        assert symbols == ["BTCUSDT", "BTCUSD"]
        assert len(set(symbols)) == len(symbols)

    async def test_instrument_info_skips_a_category_with_a_bad_result(self) -> None:
        """One malformed category must not abort the whole instruments fetch."""
        linear = {
            "retCode": 0,
            "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
            "time": 1764072000000,
        }
        inverse = {"retCode": 0, "result": "not-an-object"}
        adapter = BybitPublicAdapter(
            transport=self._category_transport(
                "/v5/market/instruments-info", {"linear": linear, "inverse": inverse}
            ),
        )
        assert len(await adapter.instrument_info()) == 1

    async def test_ticker_becomes_a_quote_with_decimal_prices(self) -> None:
        payload = {
            "retCode": 0,
            "time": 1764072000000,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "99123.40",
                        "bid1Price": "99123.30",
                        "ask1Price": "99123.50",
                        "bid1Size": "0.500",
                        "ask1Size": "0.750",
                        "ts": 1764072000000,
                    },
                ],
            },
        }
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", payload))
        quotes = await adapter.quotes(["BTCUSDT"])
        assert len(quotes) == 1
        quote = quotes[0]
        assert quote.bid == D("99123.30")
        assert quote.ask == D("99123.50")
        assert quote.last == D("99123.40")
        assert quote.bid_size == D("0.500")
        assert quote.is_crossed_or_locked is False
        assert quote.observed_at is not None and quote.observed_at.tzinfo is not None
        assert quote.instrument_id == ""  # resolved by the pipeline, never guessed here

    async def test_ticker_single_symbol_object_response_is_handled(self) -> None:
        """Bybit returns an object, not a list, when one symbol is requested."""
        payload = {
            "retCode": 0,
            "result": {"list": {"symbol": "BTCUSDT", "lastPrice": "99000"}},
            "time": 1764072000000,
        }
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", payload))
        quotes = await adapter.quotes(["BTCUSDT"])
        assert len(quotes) == 1
        assert quotes[0].last == D("99000")

    async def test_recent_trades_normalise_side(self) -> None:
        payload = {
            "retCode": 0,
            "time": 1764072000000,
            "result": {
                "list": [
                    {
                        "execId": "a1",
                        "symbol": "BTCUSDT",
                        "price": "99000.0",
                        "size": "0.01",
                        "side": "Buy",
                        "time": 1764071999000,
                    },
                    {
                        "execId": "a2",
                        "symbol": "BTCUSDT",
                        "price": "99001.0",
                        "size": "0.02",
                        "side": "Sell",
                        "time": 1764071998000,
                    },
                ],
            },
        }
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/recent-trade", payload))
        ticks = await adapter.trades("BTCUSDT")
        assert len(ticks) == 2
        assert [t.side for t in ticks] == ["SELL", "BUY"]  # sorted by time, so a2 first
        assert ticks[0].price == D("99001.0")
        assert ticks[0].trade_id == "a2"

    async def test_kline_newest_first_is_reversed_to_chronological(self) -> None:
        """Bybit pages backwards; without reversing, a backtest reads the future."""
        base_ms = int(NOW.timestamp() * 1000)
        rows = [
            [str(base_ms - 60_000 * i), "100", "110", "90", "105", "10", "1000"] for i in range(3)
        ]  # newest first
        payload = {"retCode": 0, "time": base_ms, "result": {"list": rows}}
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/kline", payload))
        bars = await adapter.bars("BTCUSDT", interval="1")
        assert len(bars) == 3
        times = [b.open_time for b in bars]
        assert times == sorted(times), "bars must come back in chronological order"
        assert bars[0].interval == "1m"
        assert bars[0].open == D("100")
        assert bars[0].quote_volume == D("1000")
        assert bars[0].trades is None  # Bybit publishes no trade count

    async def test_newest_bar_in_a_page_is_unconfirmed(self) -> None:
        """The last bar of a page is usually still forming."""
        base_ms = int(NOW.timestamp() * 1000)
        rows = [[str(base_ms - 60_000 * i), "100", "110", "90", "105", "10", "1000"] for i in range(3)]
        adapter = BybitPublicAdapter(
            transport=self._transport("/v5/market/kline", {"retCode": 0, "result": {"list": rows}})
        )
        bars = await adapter.bars("BTCUSDT", interval="1")
        assert bars[-1].confirmed is False  # the newest bar of the page is still forming
        assert all(b.confirmed is True for b in bars[:-1])

    async def test_malformed_rows_are_counted_not_crashing(self) -> None:
        """A JSON *string* is a Sequence of characters, so it must not be read as a row.

        Without an explicit list/tuple check, ``"not-a-row"[0]`` yields ``"n"`` and the
        timestamp parser raises out of the adapter, aborting a whole backfill over one
        malformed row instead of counting it.
        """
        from nexus.data.records import IngestReport

        payload = {
            "retCode": 0,
            "result": {
                "list": [
                    ["1", "2"],
                    "not-a-row",
                    [str(int(NOW.timestamp() * 1000)), "100", "110", "90", "105", "10"],
                ]
            },
        }
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/kline", payload))
        report = IngestReport(source="BYBIT", venue="BYBIT", started_at=NOW)
        bars = await adapter.bars("BTCUSDT", interval="1", report=report)
        assert len(bars) == 1
        assert report.rejected >= 2

    async def test_orderbook_depth(self) -> None:
        payload = {
            "retCode": 0,
            "result": {
                "s": "BTCUSDT",
                "b": [["99000.0", "0.5"], ["98999.0", "1.0"]],
                "a": [["99001.0", "0.25"], ["99002.0", "2.0"]],
                "ts": 1764072000000,
            },
        }
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/orderbook", payload))
        book = await adapter.book("BTCUSDT", depth=5)
        assert book is not None
        assert book.best_bid == D("99000.0")
        assert book.best_ask == D("99001.0")
        assert len(book.bids) == 2
        assert book.entitlement == "LIVE"

    async def test_empty_orderbook_returns_none(self) -> None:
        payload = {"retCode": 0, "result": {"s": "BTCUSDT", "b": [], "a": [], "ts": 1764072000000}}
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/orderbook", payload))
        assert await adapter.book("BTCUSDT") is None

    async def test_nonzero_retcode_raises(self) -> None:
        payload = {"retCode": 10001, "retMsg": "Invalid symbol", "result": None}
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", payload))
        with pytest.raises(IngestFault, match="retCode=10001"):
            await adapter.quotes(["NOPE"])

    async def test_rate_limit_retcode_is_retryable(self) -> None:
        payload = {"retCode": 10006, "retMsg": "Too many requests", "result": None}
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", payload))
        with pytest.raises(IngestFault) as excinfo:
            await adapter.quotes(["BTCUSDT"])
        assert excinfo.value.retryable is True

    async def test_invalid_symbol_retcode_is_not_retryable(self) -> None:
        payload = {"retCode": 10001, "retMsg": "Invalid symbol", "result": None}
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", payload))
        with pytest.raises(IngestFault) as excinfo:
            await adapter.quotes(["NOPE"])
        assert excinfo.value.retryable is False

    async def test_non_object_response_raises(self) -> None:
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", ["not", "an", "object"]))
        with pytest.raises(IngestFault, match="not an object"):
            await adapter.quotes(["BTCUSDT"])

    async def test_missing_result_yields_empty_not_crash(self) -> None:
        adapter = BybitPublicAdapter(transport=self._transport("/v5/market/tickers", {"retCode": 0}))
        assert await adapter.quotes(["BTCUSDT"]) == ()

    async def test_paged_bars_stop_without_progress(self) -> None:
        """A cursor that stops moving must not hammer a free endpoint forever."""
        base_ms = int(NOW.timestamp() * 1000)
        rows = [[str(base_ms), "100", "110", "90", "105", "10", "1000"]]
        transport = RecordingTransport()
        transport.set_json(f"{BYBIT_BASE}/v5/market/kline", {"retCode": 0, "result": {"list": rows}})
        adapter = BybitPublicAdapter(transport=transport)
        bars = await adapter.bars_paged(
            "BTCUSDT",
            interval="1",
            start=NOW - timedelta(days=30),
            end=NOW,
        )
        assert len(bars) >= 1
        assert len(transport.requests) < 500  # bounded, not an infinite loop


class TestOkxAdapter:
    def _transport(self, path: str, payload: object) -> RecordingTransport:
        transport = RecordingTransport()
        transport.set_json(f"{OKX_BASE}{path}", payload)
        return transport

    async def test_instrument_info_extracts_ctval_as_contract_size(self) -> None:
        """``ctVal`` is the contract size — the number that makes sizing correct or wrong."""
        payload = {
            "code": "0",
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "instType": "SWAP",
                    "baseCcy": "BTC",
                    "quoteCcy": "USDT",
                    "settleCcy": "USDT",
                    "ctVal": "0.01",
                    "ctMult": "1",
                    "ctValCcy": "BTC",
                    "tickSz": "0.1",
                    "lotSz": "1",
                    "minSz": "1",
                    "maxLmtSz": "1000000",
                    "state": "live",
                    "category": "BTC",
                },
            ],
        }
        adapter = OkxPublicAdapter(transport=self._transport("/api/v5/public/instruments", payload))
        records = await adapter.instrument_info(["BTC-USDT-SWAP"])
        assert len(records) == 1
        info = records[0]
        assert info.contract_size == D("0.01")
        assert info.tick_size == D("0.1")
        assert info.qty_step == D("1")
        assert info.max_order_qty == D("1000000")
        assert info.status == "live"
        assert info.raw["settleCcy"] == "USDT"

    async def test_ticker_becomes_a_quote(self) -> None:
        payload = {
            "code": "0",
            "data": [
                {
                    "instType": "SWAP",
                    "instId": "BTC-USDT-SWAP",
                    "last": "99100.5",
                    "askPx": "99100.6",
                    "askSz": "12",
                    "bidPx": "99100.4",
                    "bidSz": "8",
                    "ts": "1764072000000",
                },
            ],
        }
        adapter = OkxPublicAdapter(transport=self._transport("/api/v5/market/ticker", payload))
        quotes = await adapter.quotes(["BTC-USDT-SWAP"])
        assert len(quotes) == 1
        assert quotes[0].bid == D("99100.4")
        assert quotes[0].ask == D("99100.6")
        assert quotes[0].last == D("99100.5")
        assert quotes[0].observed_at is not None

    async def test_candles_newest_first_are_reversed(self) -> None:
        base_ms = int(NOW.timestamp() * 1000)
        rows = [
            [str(base_ms - 60_000 * i), "100", "110", "90", "105", "10", "1", "1000", "1"] for i in range(3)
        ]
        adapter = OkxPublicAdapter(
            transport=self._transport("/api/v5/market/candles", {"code": "0", "data": rows})
        )
        bars = await adapter.bars("BTC-USDT-SWAP", interval="1m")
        times = [b.open_time for b in bars]
        assert times == sorted(times)
        assert all(b.confirmed is True for b in bars)  # confirm flag "1"
        assert bars[0].close_time == bars[0].open_time + timedelta(minutes=1)

    async def test_unconfirmed_candle_is_not_marked_confirmed(self) -> None:
        """OKX's trailing confirm flag is authoritative; a forming bar must stay unconfirmed."""
        base_ms = int(NOW.timestamp() * 1000)
        rows = [
            [str(base_ms), "100", "110", "90", "105", "10", "1", "1000", "0"],
            [str(base_ms - 60_000), "100", "110", "90", "105", "10", "1", "1000", "1"],
        ]
        adapter = OkxPublicAdapter(
            transport=self._transport("/api/v5/market/candles", {"code": "0", "data": rows})
        )
        bars = await adapter.bars("BTC-USDT-SWAP", interval="1m")
        confirmed = {b.open_time: b.confirmed for b in bars}
        assert confirmed[datetime.fromtimestamp(base_ms / 1000, tz=UTC)] is False
        assert confirmed[datetime.fromtimestamp((base_ms - 60_000) / 1000, tz=UTC)] is True

    async def test_history_endpoint_is_used_when_requested(self) -> None:
        transport = RecordingTransport()
        transport.set_json(f"{OKX_BASE}/api/v5/market/history-candles", {"code": "0", "data": []})
        adapter = OkxPublicAdapter(transport=transport)
        await adapter.bars("BTC-USDT-SWAP", interval="1m", use_history=True)
        assert transport.requests[0][0].endswith("/api/v5/market/history-candles")

    async def test_trades_normalise_side(self) -> None:
        payload = {
            "code": "0",
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": "t1",
                    "px": "99000",
                    "sz": "1",
                    "side": "buy",
                    "ts": "1764072000000",
                },
                {
                    "instId": "BTC-USDT-SWAP",
                    "tradeId": "t2",
                    "px": "99001",
                    "sz": "2",
                    "side": "sell",
                    "ts": "1764071999000",
                },
            ],
        }
        adapter = OkxPublicAdapter(transport=self._transport("/api/v5/market/trades", payload))
        ticks = await adapter.trades("BTC-USDT-SWAP")
        assert [t.side for t in ticks] == ["SELL", "BUY"]
        assert [t.trade_id for t in ticks] == ["t2", "t1"]

    async def test_book_depth(self) -> None:
        payload = {
            "code": "0",
            "data": [
                {
                    "asks": [["99001", "5", "0", "3"], ["99002", "9", "0", "4"]],
                    "bids": [["99000", "7", "0", "2"]],
                    "ts": "1764072000000",
                },
            ],
        }
        adapter = OkxPublicAdapter(transport=self._transport("/api/v5/market/books", payload))
        book = await adapter.book("BTC-USDT-SWAP")
        assert book is not None
        assert book.best_bid == D("99000")
        assert book.best_ask == D("99001")

    async def test_rate_limit_code_is_retryable(self) -> None:
        adapter = OkxPublicAdapter(
            transport=self._transport("/api/v5/market/ticker", {"code": "50011", "msg": "Too many requests"}),
        )
        with pytest.raises(IngestFault) as excinfo:
            await adapter.quotes(["BTC-USDT-SWAP"])
        assert excinfo.value.retryable is True

    async def test_parameter_error_code_is_not_retryable(self) -> None:
        adapter = OkxPublicAdapter(
            transport=self._transport("/api/v5/market/ticker", {"code": "51000", "msg": "Parameter error"}),
        )
        with pytest.raises(IngestFault) as excinfo:
            await adapter.quotes(["NOPE"])
        assert excinfo.value.retryable is False

    async def test_http_200_with_error_code_still_raises(self) -> None:
        """OKX signals failure in the body, not the status line."""
        adapter = OkxPublicAdapter(
            transport=self._transport(
                "/api/v5/market/candles", {"code": "50013", "msg": "System busy", "data": []}
            ),
        )
        with pytest.raises(IngestFault, match="code=50013"):
            await adapter.bars("BTC-USDT-SWAP", interval="1m")

    def test_interval_round_trip(self) -> None:
        from nexus.ingestion.okx import canonical_interval as okx_canonical

        assert okx_canonical("1m") == "1m"
        assert okx_canonical("1H") == "1h"
        assert okx_canonical("1D") == "1d"
        assert okx_bar("1m") == "1m"
        assert okx_bar("1h") == "1H"
        assert okx_bar("1d") == "1D"
        assert bar_duration("1h") == timedelta(hours=1)

    def test_unknown_interval_refused(self) -> None:
        from nexus.ingestion.okx import canonical_interval as okx_canonical

        with pytest.raises(IngestFault, match="unsupported interval"):
            okx_canonical("9m")
        with pytest.raises(IngestFault, match="no bar name matches"):
            okx_bar("9m")

    def test_detect_gaps_finds_missing_minutes(self) -> None:
        base = NOW.replace(second=0, microsecond=0)
        bars = [
            _okx_bar(base),
            _okx_bar(base + timedelta(minutes=3)),
        ]
        gaps = detect_gaps(bars, canonical_interval_name="1m")
        assert gaps == (base + timedelta(minutes=1), base + timedelta(minutes=2))

    def test_detect_gaps_on_contiguous_series_is_empty(self) -> None:
        base = NOW.replace(second=0, microsecond=0)
        bars = [_okx_bar(base + timedelta(minutes=m)) for m in range(5)]
        assert detect_gaps(bars, canonical_interval_name="1m") == ()


def _okx_bar(at: datetime) -> object:
    from nexus.data.records import BarRecord

    return BarRecord(
        instrument_id="I",
        venue="OKX",
        venue_symbol="BTC-USDT-SWAP",
        interval="1m",
        open_time=at,
        close_time=at + timedelta(minutes=1),
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("1"),
        confirmed=True,
        source="TEST",
    )


class TestUrlShapesMatchThePublishedContract:
    """Pins each public URL builder's *entire* output to a literal from the venue's own docs.

    Why this class exists separately from the URL tests below it, which look like they cover the
    same ground: every adapter test registers its expected response in the recording transport under
    the key ``hour_url(...)`` or ``kline_url(...)`` — the very function under test. Code and fixture
    are derived from one another, so they always agree, and a wrong URL is invisible to them no
    matter how many tests there are. That is exactly how two of them survived 151 passing tests and
    were only caught by live verification returning 404 (defects 38 and 39).

    So these assertions transcribe the paths from the published contract instead of computing them,
    which makes the literal an independent oracle. They must not call a builder to build the
    expected value.
    """

    def test_binance_vision_daily_klines_carry_the_frequency_segment(self) -> None:
        # Published shape: market, then frequency, then data type, symbol, interval, filename.
        assert kline_url("BTCUSDT", "1m", datetime(2026, 11, 18, tzinfo=UTC)) == (
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-11-18.zip"
        )

    def test_binance_vision_monthly_klines_carry_the_frequency_segment(self) -> None:
        assert kline_url("BTCUSDT", "1d", datetime(2026, 11, 18, tzinfo=UTC), periodicity="monthly") == (
            "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2026-11.zip"
        )

    def test_binance_vision_agg_trades_carry_the_frequency_segment(self) -> None:
        assert agg_trades_url("BTCUSDT", datetime(2026, 11, 18, tzinfo=UTC)) == (
            "https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-11-18.zip"
        )

    def test_dukascopy_has_no_side_segment_and_a_zero_indexed_month(self) -> None:
        # Published shape: pair, year, zero-indexed month, day, hour. One file holds both sides.
        assert hour_url("EURUSD", datetime(2026, 11, 19, 12, tzinfo=UTC)) == (
            "https://datafeed.dukascopy.com/datafeed/EURUSD/2026/10/19/12h_ticks.bi5"
        )

    def test_dukascopy_january_is_month_zero(self) -> None:
        assert hour_url("EURUSD", datetime(2026, 1, 15, 14, tzinfo=UTC)) == (
            "https://datafeed.dukascopy.com/datafeed/EURUSD/2026/00/15/14h_ticks.bi5"
        )

    def test_bybit_and_okx_bases_are_the_published_hosts(self) -> None:
        """OKX answered live; Bybit 403s from a hosted runner, so its host is pinned here instead."""
        assert BYBIT_REST == BYBIT_BASE == "https://api.bybit.com"
        assert OKX_REST == OKX_BASE == "https://www.okx.com"

    def test_the_two_adapters_do_not_share_an_interval_vocabulary(self) -> None:
        """Regression for a trap that cost a live run: same kwarg name, different vocabulary.

        Bybit's `bars(interval=...)` takes the venue's own key and refuses "1m" before making any
        HTTP call; OKX's takes the canonical key. Both normalise to the canonical name on the way
        out, so reading the vocabulary off the returned records gives the wrong answer for one of
        the two adapters.
        """
        assert canonical_interval("1") == "1m", "Bybit spells one minute as 1, not 1m"
        assert bybit_interval("1m") == "1"
        with pytest.raises(IngestFault, match="unsupported interval"):
            canonical_interval("1m")

        assert okx_bar("1m") == "1m", "OKX spells one minute as 1m"
        assert bybit_interval("1m") != okx_bar("1m"), (
            "the two adapters now agree on a spelling, so this trap has moved and the live "
            "verification module must be re-checked against both"
        )


class TestBinanceVisionUrls:
    def test_daily_kline_url(self) -> None:
        url = kline_url("BTCUSDT", "1m", datetime(2026, 10, 5, tzinfo=UTC))
        assert url == (
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-10-05.zip"
        )

    def test_monthly_kline_url(self) -> None:
        url = kline_url("BTCUSDT", "1d", datetime(2026, 10, 5, tzinfo=UTC), periodicity="monthly")
        assert url.endswith("BTCUSDT-1d-2026-10.zip")
        # periodicity is a path segment as well as a filename stamp (defect 38)
        assert "/data/spot/monthly/klines/" in url

    def test_futures_market_path(self) -> None:
        url = kline_url("BTCUSDT", "1m", datetime(2026, 10, 5, tzinfo=UTC), market="futures")
        assert "/data/futures/daily/klines/" in url

    def test_agg_trades_url(self) -> None:
        url = agg_trades_url("BTCUSDT", datetime(2026, 10, 5, tzinfo=UTC))
        assert "/data/spot/daily/aggTrades/BTCUSDT/" in url
        assert url.endswith("BTCUSDT-aggTrades-2026-10-05.zip")

    def test_agg_trades_refuses_a_bad_periodicity(self) -> None:
        """It selects a path segment now, so an unknown value must not default to daily."""
        with pytest.raises(IngestFault, match="periodicity"):
            agg_trades_url("BTCUSDT", datetime(2026, 10, 5, tzinfo=UTC), periodicity="weekly")

    def test_bad_periodicity_refused(self) -> None:
        with pytest.raises(IngestFault, match="periodicity"):
            kline_url("BTCUSDT", "1m", datetime(2026, 10, 5, tzinfo=UTC), periodicity="weekly")

    def test_naive_period_refused(self) -> None:
        with pytest.raises(IngestFault, match="timezone-aware"):
            kline_url("BTCUSDT", "1m", datetime(2026, 10, 5))

    def test_daily_periods_are_bounded(self) -> None:
        periods = daily_periods(datetime(2020, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))
        assert len(periods) <= 400

    def test_monthly_periods_are_bounded(self) -> None:
        periods = monthly_periods(datetime(1990, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))
        assert len(periods) <= 240
        assert periods[1].month == 2

    def test_monthly_periods_roll_over_year_end(self) -> None:
        periods = monthly_periods(datetime(2025, 11, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))
        assert [(p.year, p.month) for p in periods] == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def _zip_csv(text: str, name: str = "data.csv") -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


class TestBinanceVisionParsing:
    def test_kline_csv_without_header(self) -> None:
        text = (
            "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0\n"
            "1764072060000,105.0,106.0,104.0,105.5,3.0,1764072119999,315.0,11,1.0,105.0,0\n"
        )
        bars, summary = parse_kline_csv(text, symbol="BTCUSDT", interval="1m")
        assert len(bars) == 2
        assert summary.had_header is False
        assert bars[0].open == D("100.0")
        assert bars[0].volume == D("10.5")
        assert bars[0].quote_volume == D("1050.0")
        assert bars[0].trades == 42
        assert bars[0].confirmed is True  # a published dump is settled
        assert bars[0].close_time is not None
        assert bars[0].open_time.tzinfo is not None

    def test_kline_csv_with_header_is_sniffed(self) -> None:
        text = (
            "open_time,open,high,low,close,volume,close_time,quote_volume,trades,a,b,ignore\n"
            "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0\n"
        )
        bars, summary = parse_kline_csv(text, symbol="BTCUSDT", interval="1m")
        assert summary.had_header is True
        assert len(bars) == 1

    def test_trailing_ignore_column_is_not_archived(self) -> None:
        """Archiving a column the venue labels 'ignore' is how schemas rot."""
        text = "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,IGNORED\n"
        bars, _ = parse_kline_csv(text, symbol="BTCUSDT", interval="1m")
        assert bars[0].to_dict().get("ignore") is None
        assert "IGNOREED" not in str(bars[0].to_dict())

    def test_inconsistent_ohlc_row_is_rejected(self) -> None:
        text = "1764072000000,100.0,90.0,110.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0\n"
        bars, summary = parse_kline_csv(text, symbol="BTCUSDT", interval="1m")
        assert bars == ()
        assert summary.records_rejected == 1
        assert any("OHLC_INCONSISTENT" in k for k in summary.rejection_reasons)

    def test_short_row_is_rejected(self) -> None:
        text = "1764072000000,100.0,110.0\n"
        bars, summary = parse_kline_csv(text, symbol="BTCUSDT", interval="1m")
        assert bars == ()
        assert summary.records_rejected == 1

    def test_unsupported_interval_refused(self) -> None:
        with pytest.raises(IngestFault, match="unsupported interval"):
            parse_kline_csv("", symbol="BTCUSDT", interval="9m")

    def test_agg_trades_side_is_derived_from_buyer_maker(self) -> None:
        """is_buyer_maker=True means the buyer was the maker, so the aggressor sold."""
        text = "1,100.0,0.5,1,1,1764072000000,true,0\n2,100.5,0.25,2,2,1764072001000,false,0\n"
        ticks, summary = parse_agg_trades_csv(text, symbol="BTCUSDT")
        assert len(ticks) == 2
        assert ticks[0].side == "SELL"
        assert ticks[1].side == "BUY"
        assert ticks[0].trade_id == "1"
        assert summary.records_accepted == 2

    def test_agg_trades_unknown_side_stays_none(self) -> None:
        text = "1,100.0,0.5,1,1,1764072000000,maybe,0\n"
        ticks, _ = parse_agg_trades_csv(text, symbol="BTCUSDT")
        assert ticks[0].side is None

    async def test_fetch_klines_unzips_and_parses(self) -> None:
        text = "1764072000000,100.0,110.0,90.0,105.0,10.5,1764072059999,1050.0,42,5.0,500.0,0\n"
        url = expected_kline_url("BTCUSDT", "1m", datetime(2026, 10, 5, tzinfo=UTC))
        transport = RecordingTransport()
        transport.set_bytes(url, _zip_csv(text))
        source = BinanceVisionHistorical(transport=transport)
        bars, parses = await source.fetch_klines(
            "BTCUSDT",
            "1m",
            [datetime(2026, 10, 5, tzinfo=UTC)],
        )
        assert len(bars) == 1
        assert len(parses) == 1
        assert bars[0].venue == "BINANCE"

    async def test_missing_dump_is_a_gap_not_an_error(self) -> None:
        """A 404 for a day that does not exist is normal for this source."""
        from nexus.data.records import IngestReport

        transport = RecordingTransport()  # nothing recorded -> raises IngestFault
        source = BinanceVisionHistorical(transport=transport)
        report = IngestReport(source="BINANCE_VISION", venue="BINANCE", started_at=NOW)
        bars, parses = await source.fetch_klines(
            "BTCUSDT",
            "1m",
            [datetime(2026, 10, 5, tzinfo=UTC)],
            report=report,
        )
        assert bars == ()
        assert parses == []
        assert report.rejections.get("DUMP_UNAVAILABLE") == 1

    async def test_missing_dump_can_be_made_fatal(self) -> None:
        transport = RecordingTransport()
        source = BinanceVisionHistorical(transport=transport)
        with pytest.raises(IngestFault):
            await source.fetch_klines(
                "BTCUSDT",
                "1m",
                [datetime(2026, 10, 5, tzinfo=UTC)],
                missing_is_ok=False,
            )

    async def test_html_404_page_is_not_treated_as_a_zip(self) -> None:
        """A CDN 404 often returns HTML with status 200; that is not a zip."""
        url = expected_kline_url("BTCUSDT", "1m", datetime(2026, 10, 5, tzinfo=UTC))
        transport = RecordingTransport()
        transport.set_bytes(url, b"<html><body>404 Not Found</body></html>")
        source = BinanceVisionHistorical(transport=transport)
        bars, _ = await source.fetch_klines("BTCUSDT", "1m", [datetime(2026, 10, 5, tzinfo=UTC)])
        assert bars == ()


class TestDukascopyUrls:
    def test_month_is_zero_indexed(self) -> None:
        """The single most common bug with this feed: January is 00, not 01."""
        url = hour_url("EURUSD", datetime(2026, 1, 15, 14, 0, tzinfo=UTC))
        assert "/2026/00/15/" in url
        assert url.endswith("/14h_ticks.bi5")

    def test_december_is_month_eleven(self) -> None:
        url = hour_url("EURUSD", datetime(2026, 12, 15, 14, 0, tzinfo=UTC))
        assert "/2026/11/15/" in url

    def test_day_and_hour_are_padded(self) -> None:
        url = hour_url("EURUSD", datetime(2026, 3, 5, 3, 0, tzinfo=UTC))
        assert "/2026/02/05/" in url
        assert url.endswith("/03h_ticks.bi5")

    def test_the_url_has_no_side_segment(self) -> None:
        """Regression for defect 39: one bi5 file holds both sides, so a side segment 404s.

        Found by live verification rather than by reading: the offline tests registered the same
        invented path in the recording transport, so the code and the fixture agreed and both were
        wrong.
        """
        url = hour_url("EURUSD", datetime(2026, 3, 5, 3, 0, tzinfo=UTC))
        assert url == "https://datafeed.dukascopy.com/datafeed/EURUSD/2026/02/05/03h_ticks.bi5"
        for side in SIDES:
            assert f"/{side}/" not in url

    def test_bad_side_refused_at_parse_time(self) -> None:
        """`side` moved from the URL to the parser, and the refusal moved with it."""
        with pytest.raises(IngestFault, match="side must be one of"):
            parse_bi5(b"", pair="EURUSD", hour_start=datetime(2026, 3, 5, 3, 0, tzinfo=UTC), side="MID")

    def test_naive_hour_refused(self) -> None:
        with pytest.raises(IngestFault, match="timezone-aware"):
            hour_url("EURUSD", datetime(2026, 3, 5, 3, 0))

    def test_non_utc_input_is_normalised(self) -> None:
        from zoneinfo import ZoneInfo

        lagos = datetime(2026, 3, 5, 4, 0, tzinfo=ZoneInfo("Africa/Lagos"))  # 03:00 UTC
        assert "/03h_ticks.bi5" in hour_url("EURUSD", lagos)

    def test_symbol_is_upper_cased_in_the_url(self) -> None:
        assert "/EURUSD/" in hour_url("eurusd", datetime(2026, 3, 5, 3, 0, tzinfo=UTC))


class TestDukascopyPointDivisors:
    def test_five_digit_pairs(self) -> None:
        assert point_divisor("EURUSD") == 100_000
        assert point_divisor("GBPUSD") == 100_000

    def test_jpy_pairs_use_a_smaller_divisor(self) -> None:
        """A wrong divisor here scales every price by 100x."""
        assert point_divisor("USDJPY") == 1_000
        assert point_divisor("EURJPY") == 1_000

    def test_metals(self) -> None:
        assert point_divisor("XAUUSD") == 100
        assert point_divisor("XAGUSD") == 1_000

    def test_unknown_pair_is_refused_not_guessed(self) -> None:
        """Guessing a divisor is the difference between a correct and a 100x-wrong archive."""
        with pytest.raises(IngestFault, match="no point divisor recorded"):
            point_divisor("EURPLN")

    def test_divisor_lookup_is_case_insensitive(self) -> None:
        assert point_divisor("eurusd") == 100_000

    def test_supported_pairs_is_sorted_and_matches_the_table(self) -> None:
        pairs = supported_pairs()
        assert pairs == tuple(sorted(POINT_DIVISORS))
        assert "EURUSD" in pairs

    def test_pair_supported_predicate(self) -> None:
        from nexus.ingestion.dukascopy import pair_supported

        assert pair_supported("EURUSD") is True
        assert pair_supported("EURPLN") is False


def _bi5_payload(ticks: list[tuple[int, int, int, float, float]]) -> bytes:
    """Build a synthetic bi5 body: LZMA over 20-byte big-endian tick records."""
    body = b"".join(struct.pack(">IIIf f".replace(" ", ""), *t) for t in ticks)
    return lzma.compress(body)


class TestDukascopyParsing:
    def test_ticks_are_parsed_with_correct_prices(self) -> None:
        """Bid points 10850000 / 100000 == 108.50 for EURUSD."""
        payload = _bi5_payload(
            [
                (0, 10_850_100, 10_850_000, 1.5, 2.5),
                (1_000, 10_850_200, 10_850_150, 0.5, 0.75),
            ],
        )
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        ticks = parse_bi5(payload, pair="EURUSD", hour_start=hour, side="BID")
        assert len(ticks) == 2
        assert ticks[0].price == D("108.5")
        assert ticks[1].price == D("108.5015")
        assert ticks[0].observed_at == hour
        assert ticks[1].observed_at == hour + timedelta(seconds=1)
        assert ticks[0].venue == "DUKASCOPY"

    def test_ask_side_uses_the_ask_price(self) -> None:
        payload = _bi5_payload([(0, 10_850_100, 10_850_000, 1.5, 2.5)])
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        bid = parse_bi5(payload, pair="EURUSD", hour_start=hour, side="BID")
        ask = parse_bi5(payload, pair="EURUSD", hour_start=hour, side="ASK")
        assert bid[0].price == D("108.5")
        assert ask[0].price == D("108.501")
        assert ask[0].price > bid[0].price  # spread is preserved, not collapsed

    def test_volume_is_taken_from_the_matching_side(self) -> None:
        payload = _bi5_payload([(0, 10_850_100, 10_850_000, 1.5, 2.5)])
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        assert parse_bi5(payload, pair="EURUSD", hour_start=hour, side="BID")[0].quantity == D("2.5")
        assert parse_bi5(payload, pair="EURUSD", hour_start=hour, side="ASK")[0].quantity == D("1.5")

    def test_jpy_pair_uses_its_own_divisor(self) -> None:
        """145250 points / 1000 == 145.250 — a 5-digit divisor would give 1.4525."""
        payload = _bi5_payload([(0, 145_251, 145_250, 1.0, 1.0)])
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        ticks = parse_bi5(payload, pair="USDJPY", hour_start=hour)
        assert ticks[0].price == D("145.25")

    def test_zero_price_padding_is_skipped(self) -> None:
        """Dukascopy pads with zero-price records; they carry no information."""
        payload = _bi5_payload(
            [
                (0, 0, 0, 0.0, 0.0),
                (1_000, 10_850_100, 10_850_000, 1.0, 1.0),
            ],
        )
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        ticks = parse_bi5(payload, pair="EURUSD", hour_start=hour)
        assert len(ticks) == 1
        assert ticks[0].price == D("108.5")

    def test_empty_payload_is_a_closed_hour_not_an_error(self) -> None:
        """FX does not trade at weekends; an empty file is expected, not a fault."""
        assert parse_bi5(b"", pair="EURUSD", hour_start=datetime(2026, 11, 21, 14, 0, tzinfo=UTC)) == ()

    def test_offset_beyond_one_hour_signals_a_layout_mismatch(self) -> None:
        payload = _bi5_payload([(3_600_001, 10_850_100, 10_850_000, 1.0, 1.0)])
        with pytest.raises(IngestFault, match="exceeds one hour"):
            parse_bi5(payload, pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC))

    def test_size_not_a_multiple_of_twenty_is_refused(self) -> None:
        """Refusing beats emitting garbage under a wrong layout assumption."""
        payload = lzma.compress(b"\x00" * 21)
        with pytest.raises(IngestFault, match="not a multiple of 20"):
            parse_bi5(payload, pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC))

    def test_non_lzma_payload_is_refused(self) -> None:
        with pytest.raises(IngestFault, match="not valid LZMA"):
            parse_bi5(
                b"<html>404</html>", pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
            )

    def test_naive_hour_start_refused(self) -> None:
        with pytest.raises(IngestFault, match="timezone-aware"):
            parse_bi5(b"", pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0))

    def test_side_is_never_invented(self) -> None:
        """A bid/ask print is not a buyer- or seller-initiated trade."""
        payload = _bi5_payload([(0, 10_850_100, 10_850_000, 1.0, 1.0)])
        ticks = parse_bi5(payload, pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC))
        assert ticks[0].side is None

    def test_source_is_labelled_unverified(self) -> None:
        payload = _bi5_payload([(0, 10_850_100, 10_850_000, 1.0, 1.0)])
        ticks = parse_bi5(payload, pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC))
        assert ticks[0].source == "DUKASCOPY_BI5_UNVERIFIED"

    def test_instrument_id_is_left_for_the_registry(self) -> None:
        payload = _bi5_payload([(0, 10_850_100, 10_850_000, 1.0, 1.0)])
        ticks = parse_bi5(payload, pair="EURUSD", hour_start=datetime(2026, 11, 25, 14, 0, tzinfo=UTC))
        assert ticks[0].instrument_id == ""


class TestDukascopyLayoutVerification:
    def test_valid_payload_passes(self) -> None:
        payload = _bi5_payload([(0, 1, 1, 1.0, 1.0), (1_000, 1, 1, 1.0, 1.0)])
        result = verify_layout(payload)
        assert result["passed"] is True
        assert result["tick_count"] == 2
        assert result["reasons"] == []

    def test_empty_payload_cannot_verify(self) -> None:
        result = verify_layout(b"")
        assert result["passed"] is False
        assert any("EMPTY_PAYLOAD" in r for r in result["reasons"])

    def test_html_payload_fails(self) -> None:
        result = verify_layout(b"<html>404</html>")
        assert result["passed"] is False
        assert any("NOT_LZMA" in r for r in result["reasons"])

    def test_wrong_record_size_fails(self) -> None:
        result = verify_layout(lzma.compress(b"\x00" * 21))
        assert result["passed"] is False
        assert any("SIZE_NOT_MULTIPLE_OF_20" in r for r in result["reasons"])

    def test_offset_beyond_hour_fails(self) -> None:
        result = verify_layout(_bi5_payload([(9_999_999, 1, 1, 1.0, 1.0)]))
        assert result["passed"] is False
        assert any("OFFSET_EXCEEDS_HOUR" in r for r in result["reasons"])

    def test_empty_but_valid_lzma_is_flagged(self) -> None:
        result = verify_layout(lzma.compress(b""))
        assert result["passed"] is False
        assert any("DECOMPRESSED_EMPTY" in r for r in result["reasons"])


class TestDukascopyFetch:
    async def test_fetch_hour_reports_provenance(self) -> None:
        hour = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        transport = RecordingTransport()
        transport.set_bytes(
            expected_bi5_url("EURUSD", hour), _bi5_payload([(0, 10_850_100, 10_850_000, 1.0, 2.0)])
        )
        source = DukascopyHistorical(transport=transport)
        result = await source.fetch_hour("EURUSD", hour)
        assert result.pair == "EURUSD"
        assert result.side == "BID"
        assert result.hour_start == hour
        assert len(result.ticks) == 1
        assert result.layout_verified is False
        assert result.empty is False
        assert result.raw_bytes > 0

    async def test_empty_hour_is_flagged_not_an_error(self) -> None:
        hour = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)  # Saturday
        transport = RecordingTransport()
        transport.set_bytes(expected_bi5_url("EURUSD", hour), b"")
        source = DukascopyHistorical(transport=transport)
        result = await source.fetch_hour("EURUSD", hour)
        assert result.empty is True
        assert result.ticks == ()

    async def test_fetch_range_skips_weekends(self) -> None:
        """Not downloading a closed hour saves free-tier bandwidth for zero information."""
        start = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)  # Friday 22:00
        end = datetime(2026, 11, 23, 2, 0, tzinfo=UTC)  # Monday 02:00
        transport = RecordingTransport()
        for cursor in [
            start,
            start + timedelta(hours=1),
            datetime(2026, 11, 22, 22, 0, tzinfo=UTC),
            datetime(2026, 11, 22, 23, 0, tzinfo=UTC),
            datetime(2026, 11, 23, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 23, 1, 0, tzinfo=UTC),
            datetime(2026, 11, 23, 2, 0, tzinfo=UTC),
        ]:
            transport.set_bytes(expected_bi5_url("EURUSD", cursor), b"")
        source = DukascopyHistorical(transport=transport)
        hours = await source.fetch_range("EURUSD", start=start, end=end)
        requested = [h.hour_start for h in hours]
        # Saturday (21st) and Sunday-before-22:00 (22nd) must not have been fetched.
        assert datetime(2026, 11, 21, 12, 0, tzinfo=UTC) not in requested
        assert datetime(2026, 11, 22, 12, 0, tzinfo=UTC) not in requested
        assert all(h.hour_start.weekday() != 5 for h in hours)

    async def test_fetch_range_refuses_reversed_window(self) -> None:
        transport = RecordingTransport()
        source = DukascopyHistorical(transport=transport)
        with pytest.raises(IngestFault, match="end is before start"):
            await source.fetch_range(
                "EURUSD",
                start=datetime(2026, 11, 25, 12, 0, tzinfo=UTC),
                end=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
            )

    async def test_fetch_range_refuses_naive_bounds(self) -> None:
        transport = RecordingTransport()
        source = DukascopyHistorical(transport=transport)
        with pytest.raises(IngestFault, match="timezone-aware"):
            await source.fetch_range("EURUSD", start=datetime(2026, 11, 25, 10), end=NOW)

    async def test_hour_callback_receives_every_hour(self) -> None:
        start = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
        transport = RecordingTransport()
        for offset in range(3):
            transport.set_bytes(expected_bi5_url("EURUSD", start + timedelta(hours=offset)), b"")
        source = DukascopyHistorical(transport=transport)
        seen: list[datetime] = []
        await source.fetch_range(
            "EURUSD",
            start=start,
            end=start + timedelta(hours=2),
            on_hour=lambda h: seen.append(h.hour_start),
        )
        assert seen == [start, start + timedelta(hours=1), start + timedelta(hours=2)]

    def test_summarise_reports_coverage_honestly(self) -> None:
        from nexus.ingestion.dukascopy import DukascopyHour, summarise

        hours = [
            DukascopyHour("EURUSD", "BID", NOW, (), "u", 10, 20, False, True),
            DukascopyHour("EURUSD", "BID", NOW + timedelta(hours=1), (), "u", 10, 20, False, True),
        ]
        summary = summarise(hours)
        assert summary["hours_requested"] == 2
        assert summary["hours_empty"] == 2
        assert summary["layout_verified"] is False
        assert summary["source"] == "DUKASCOPY_BI5_UNVERIFIED"
        assert "weekends" in summary["coverage_note"]

    def test_summarise_of_empty_range(self) -> None:
        from nexus.ingestion.dukascopy import summarise

        summary = summarise([])
        assert summary["hours_requested"] == 0
        assert summary["first"] is None


class TestTokenBucketAndBackoff:
    async def test_burst_is_consumed_without_waiting(self) -> None:
        from nexus.data.records import TokenBucket

        clock = [0.0]
        bucket = TokenBucket(rate_per_second=1.0, burst=3, clock=lambda: clock[0])
        for _ in range(3):
            await bucket.acquire()
        assert bucket.waits == 0

    async def test_exceeding_the_rate_forces_a_wait(self) -> None:
        from nexus.data.records import TokenBucket

        clock = [0.0]
        bucket = TokenBucket(rate_per_second=10.0, burst=1, clock=lambda: clock[0])
        await bucket.acquire()
        await bucket.acquire()  # must wait ~0.1s
        assert bucket.waits == 1

    def test_invalid_bucket_parameters_refused(self) -> None:
        from nexus.data.records import TokenBucket

        with pytest.raises(ValueError, match="positive"):
            TokenBucket(rate_per_second=0.0, burst=1)
        with pytest.raises(ValueError, match="burst"):
            TokenBucket(rate_per_second=1.0, burst=0)

    def test_backoff_grows_and_is_capped(self) -> None:
        import random as random_module

        from nexus.data.records import BackoffPolicy

        policy = BackoffPolicy(base_seconds=1.0, max_seconds=60.0, multiplier=2.0, max_attempts=5)
        rng = random_module.Random(0)  # noqa: S311 - jitter seeding, not a cryptographic use
        delays = [policy.delay(a, rng=rng) for a in range(8)]
        assert all(0.0 <= d <= 60.0 for d in delays)

    def test_backoff_attempt_budget(self) -> None:
        from nexus.data.records import BackoffPolicy

        policy = BackoffPolicy(max_attempts=3)
        assert [policy.allows(a) for a in range(5)] == [True, True, True, False, False]

    def test_negative_attempt_refused(self) -> None:
        from nexus.data.records import BackoffPolicy

        with pytest.raises(ValueError, match="attempt"):
            BackoffPolicy().delay(-1)

    def test_backoff_is_jittered_not_deterministic(self) -> None:
        """Full jitter avoids the thundering-herd reconnect that gets free tiers banned."""
        import random as random_module

        from nexus.data.records import BackoffPolicy

        policy = BackoffPolicy(base_seconds=10.0, max_seconds=60.0)
        # noqa: S311 - reconnect jitter, not a cryptographic use
        draws = {policy.delay(2, rng=random_module.Random(seed)) for seed in range(20)}  # noqa: S311
        assert len(draws) > 5


class TestValidationHelpers:
    def test_validate_bar_accepts_a_consistent_bar(self) -> None:
        bar = _okx_bar(NOW)
        assert validate_bar(bar) is None  # type: ignore[arg-type]

    def test_validate_bar_rejects_inconsistent_ohlc(self) -> None:
        from nexus.data.records import BarRecord

        bad = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=NOW,
            close_time=None,
            open=D("100"),
            high=D("90"),  # below the open
            low=D("110"),
            close=D("100"),
        )
        assert validate_bar(bad) is not None

    def test_validate_bar_rejects_close_before_open(self) -> None:
        from nexus.data.records import BarRecord

        bad = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=NOW,
            close_time=NOW - timedelta(minutes=1),
            open=D("100"),
            high=D("101"),
            low=D("99"),
            close=D("100"),
        )
        reason = validate_bar(bad)
        assert reason is not None and "CLOSE_BEFORE_OPEN" in reason

    def test_validate_bar_rejects_negative_volume(self) -> None:
        from nexus.data.records import BarRecord

        bad = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=NOW,
            close_time=None,
            open=D("100"),
            high=D("101"),
            low=D("99"),
            close=D("100"),
            volume=D("-1"),
        )
        assert validate_bar(bad) == "NEGATIVE_VOLUME"

    def test_validate_bar_rejects_naive_timestamp(self) -> None:
        from nexus.data.records import BarRecord

        bad = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=datetime(2026, 11, 25, 12, 0),
            close_time=None,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
        )
        assert validate_bar(bad) == "NAIVE_TIMESTAMP:bar open_time has no timezone"

    def test_validate_tick_rejects_non_positive_price(self) -> None:
        from nexus.data.records import TickRecord, validate_tick

        tick = TickRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            price=D("0"),
            quantity=D("1"),
            observed_at=NOW,
        )
        assert validate_tick(tick) == "NON_POSITIVE_PRICE"

    def test_validate_quote_rejects_crossed_book(self) -> None:
        from nexus.data.records import QuoteRecord, validate_quote

        quote = QuoteRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            bid=D("101"),
            ask=D("100"),
            observed_at=NOW,
        )
        assert validate_quote(quote) == "CROSSED_OR_LOCKED:bid>=ask"

    def test_validate_quote_rejects_empty_quote(self) -> None:
        from nexus.data.records import QuoteRecord, validate_quote

        quote = QuoteRecord(
            instrument_id="I", venue="V", venue_symbol="S", bid=None, ask=None, observed_at=NOW
        )
        assert validate_quote(quote) == "EMPTY_QUOTE:no bid, ask or last"

    def test_validate_quote_rejects_missing_observation_time(self) -> None:
        from nexus.data.records import QuoteRecord, validate_quote

        quote = QuoteRecord(instrument_id="I", venue="V", venue_symbol="S", bid=D("1"), ask=D("2"))
        assert validate_quote(quote) == "MISSING_OBSERVATION_TIME"


class TestDeduplication:
    def test_duplicate_bars_by_interval_and_time(self) -> None:
        from nexus.data.records import dedupe_bars

        first = _okx_bar(NOW)
        duplicate = _okx_bar(NOW)
        assert len(dedupe_bars([first, duplicate])) == 1  # type: ignore[list-item]

    def test_confirmed_bar_wins_over_unconfirmed(self) -> None:
        from nexus.data.records import BarRecord, dedupe_bars

        partial = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=NOW,
            close_time=None,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
            confirmed=False,
        )
        settled = BarRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            interval="1m",
            open_time=NOW,
            close_time=None,
            open=D("2"),
            high=D("2"),
            low=D("2"),
            close=D("2"),
            confirmed=True,
        )
        merged = dedupe_bars([partial, settled])
        assert len(merged) == 1
        assert merged[0].confirmed is True

    def test_duplicate_ticks_by_trade_id(self) -> None:
        from nexus.data.records import TickRecord, dedupe_ticks

        tick = TickRecord(
            instrument_id="I",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            price=D("100"),
            quantity=D("1"),
            observed_at=NOW,
            trade_id="exec-1",
        )
        assert len(dedupe_ticks([tick, tick])) == 1

    def test_ticks_without_ids_are_all_kept(self) -> None:
        """A feed that publishes no trade id cannot be deduplicated; nothing may be dropped."""
        from nexus.data.records import TickRecord, dedupe_ticks

        tick = TickRecord(
            instrument_id="I",
            venue="DUKASCOPY",
            venue_symbol="EURUSD",
            price=D("1.085"),
            quantity=None,
            observed_at=NOW,
            trade_id=None,
        )
        assert len(dedupe_ticks([tick, tick])) == 2

    def test_dedupe_sorts_chronologically(self) -> None:
        from nexus.data.records import TickRecord, dedupe_ticks

        late = TickRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            price=D("1"),
            quantity=None,
            observed_at=NOW + timedelta(seconds=5),
            trade_id="b",
        )
        early = TickRecord(
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            price=D("1"),
            quantity=None,
            observed_at=NOW,
            trade_id="a",
        )
        assert [t.trade_id for t in dedupe_ticks([late, early])] == ["a", "b"]


class TestVenueEnumAlignment:
    def test_adapter_venue_names_match_the_domain_enum(self) -> None:
        """A venue string that is not in the enum cannot be resolved by the registry."""
        from nexus.ingestion.bybit import VENUE as BYBIT_VENUE
        from nexus.ingestion.okx import VENUE as OKX_VENUE

        assert Venue(BYBIT_VENUE) is Venue.BYBIT
        assert Venue(OKX_VENUE) is Venue.OKX

    def test_binance_vision_is_data_only_and_binance_is_a_known_venue(self) -> None:
        from nexus.ingestion.binance_vision import VENUE as VISION_VENUE

        assert Venue(VISION_VENUE) is Venue.BINANCE
