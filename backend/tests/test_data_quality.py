"""Data-quality gate tests (Section 4.4, Section 15.2).

Property under test: bad, stale, crossed, missing or future-dated data never permits new
risk. Reads may continue, labelled — new entries may not.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from nexus.core.errors import RejectReason
from nexus.core.ids import utc_now
from nexus.data.freshness import DataQualityGate, DataStatus, MarketSnapshot, OrderBookSnapshot

D = Decimal


class TestQuoteGate:
    def test_fresh_quote_allows_new_risk(
        self, data_gate: DataQualityGate, fresh_btc_quote: MarketSnapshot
    ) -> None:
        result = data_gate.check_quote(fresh_btc_quote)
        assert result.ok
        assert result.status is DataStatus.LIVE
        assert result.new_risk_allowed

    def test_missing_snapshot_is_unavailable(self, data_gate: DataQualityGate) -> None:
        result = data_gate.check_quote(None)
        assert not result.ok
        assert not result.new_risk_allowed
        assert result.status is DataStatus.UNAVAILABLE
        assert any(RejectReason.DATA_UNAVAILABLE.value in r for r in result.reasons)

    def test_missing_observation_time_is_unavailable(self, data_gate: DataQualityGate) -> None:
        snapshot = MarketSnapshot(
            instrument_id="INS-X", venue="BYBIT", bid=D("1"), ask=D("2"), observed_at=None
        )
        result = data_gate.check_quote(snapshot)
        assert not result.new_risk_allowed
        assert result.status is DataStatus.UNAVAILABLE

    def test_stale_quote_blocks_new_risk(
        self, data_gate: DataQualityGate, stale_btc_quote: MarketSnapshot
    ) -> None:
        result = data_gate.check_quote(stale_btc_quote)
        assert not result.ok
        assert result.status is DataStatus.STALE
        assert not result.new_risk_allowed
        assert any(RejectReason.DATA_STALE.value in r for r in result.reasons)

    def test_future_timestamp_is_a_fault_not_fresh(
        self, data_gate: DataQualityGate, future_btc_quote: MarketSnapshot
    ) -> None:
        result = data_gate.check_quote(future_btc_quote)
        assert not result.ok
        assert result.status is DataStatus.FAULT
        assert not result.new_risk_allowed
        assert any("future" in r for r in result.reasons)

    def test_crossed_market_blocks(
        self, data_gate: DataQualityGate, crossed_btc_quote: MarketSnapshot
    ) -> None:
        result = data_gate.check_quote(crossed_btc_quote)
        assert result.status is DataStatus.FAULT
        assert not result.new_risk_allowed
        assert any(RejectReason.DATA_CROSSED_MARKET.value in r for r in result.reasons)

    def test_locked_market_blocks(self, data_gate: DataQualityGate) -> None:
        snapshot = MarketSnapshot(
            instrument_id="INS-X", venue="BYBIT", bid=D("100"), ask=D("100"), observed_at=utc_now()
        )
        assert not data_gate.check_quote(snapshot).new_risk_allowed

    def test_delayed_feed_is_readable_but_not_tradeable(self, data_gate: DataQualityGate) -> None:
        snapshot = MarketSnapshot(
            instrument_id="INS-X",
            venue="MT5",
            bid=D("1.1"),
            ask=D("1.2"),
            observed_at=utc_now(),
            delayed=True,
            delay_seconds=900.0,
        )
        result = data_gate.check_quote(snapshot)
        assert result.ok  # readable, labelled
        assert result.status is DataStatus.DELAYED
        assert not result.new_risk_allowed  # never used for new live risk

    def test_boundary_age_is_allowed(self, data_gate: DataQualityGate) -> None:
        snapshot = MarketSnapshot(
            instrument_id="INS-X",
            venue="BYBIT",
            bid=D("1"),
            ask=D("2"),
            observed_at=utc_now() - timedelta(seconds=4.9),
        )
        assert data_gate.check_quote(snapshot).new_risk_allowed

    def test_mid_and_spread_computed(self, fresh_btc_quote: MarketSnapshot) -> None:
        assert fresh_btc_quote.mid == D("100000")
        assert fresh_btc_quote.spread == D("20")

    def test_incomplete_quote_has_no_mid(self) -> None:
        snapshot = MarketSnapshot(
            instrument_id="INS-X", venue="BYBIT", bid=D("1"), ask=None, observed_at=utc_now()
        )
        assert snapshot.mid is None
        assert snapshot.spread is None


class TestBookGate:
    def test_entitled_fresh_book_allows_risk(
        self, data_gate: DataQualityGate, entitled_book: OrderBookSnapshot
    ) -> None:
        result = data_gate.check_book(entitled_book)
        assert result.ok
        assert result.new_risk_allowed
        assert result.status is DataStatus.LIVE

    def test_unentitled_depth_is_reported_honestly(
        self, data_gate: DataQualityGate, unentitled_book: OrderBookSnapshot
    ) -> None:
        result = data_gate.check_book(unentitled_book)
        assert result.ok  # not a fault — we simply are not entitled
        assert result.status is DataStatus.UNAVAILABLE
        assert not result.new_risk_allowed
        assert any("DEPTH_UNENTITLED" in r for r in result.reasons)

    def test_missing_book_is_unavailable(self, data_gate: DataQualityGate) -> None:
        result = data_gate.check_book(None)
        assert not result.ok
        assert not result.new_risk_allowed

    def test_stale_book_blocks(self, data_gate: DataQualityGate) -> None:
        book = OrderBookSnapshot(
            instrument_id="INS-X",
            venue="BYBIT",
            bids=((D("99"), D("1")),),
            asks=((D("101"), D("1")),),
            observed_at=utc_now() - timedelta(seconds=120),
            entitlement="LIVE",
        )
        result = data_gate.check_book(book)
        assert result.status is DataStatus.STALE
        assert not result.new_risk_allowed

    def test_crossed_book_blocks(self, data_gate: DataQualityGate) -> None:
        book = OrderBookSnapshot(
            instrument_id="INS-X",
            venue="BYBIT",
            bids=((D("101"), D("1")),),
            asks=((D("99"), D("1")),),
            observed_at=utc_now(),
            entitlement="LIVE",
        )
        result = data_gate.check_book(book)
        assert result.status is DataStatus.FAULT
        assert not result.new_risk_allowed

    def test_book_without_timestamp_is_unavailable(self, data_gate: DataQualityGate) -> None:
        book = OrderBookSnapshot(
            instrument_id="INS-X",
            venue="BYBIT",
            bids=((D("99"), D("1")),),
            asks=((D("101"), D("1")),),
            observed_at=None,
            entitlement="LIVE",
        )
        assert not data_gate.check_book(book).new_risk_allowed


class TestAccountSnapshotGate:
    def test_fresh_account_snapshot_ok(self, data_gate: DataQualityGate) -> None:
        assert data_gate.check_account_snapshot_age(utc_now()).new_risk_allowed

    def test_missing_time_is_unavailable(self, data_gate: DataQualityGate) -> None:
        result = data_gate.check_account_snapshot_age(None)
        assert not result.new_risk_allowed
        assert result.status is DataStatus.UNAVAILABLE

    def test_old_snapshot_blocks_sizing(self, data_gate: DataQualityGate) -> None:
        result = data_gate.check_account_snapshot_age(utc_now() - timedelta(seconds=600))
        assert not result.new_risk_allowed
        assert result.status is DataStatus.STALE


class TestGateResult:
    def test_to_dict_is_json_safe(self, data_gate: DataQualityGate, fresh_btc_quote: MarketSnapshot) -> None:
        payload = data_gate.check_quote(fresh_btc_quote).to_dict()
        assert payload["new_risk_allowed"] is True
        assert isinstance(payload["details"], dict)
        assert all(isinstance(v, str) for v in payload["details"].values())
