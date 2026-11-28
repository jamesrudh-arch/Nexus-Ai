"""Data-quality gate tests (Section 4.4, Section 15.2).

Property under test: bad, stale, crossed, missing or future-dated data never permits new
risk. Reads may continue, labelled — new entries may not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

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


# ---------------------------------------------------------------- F-14 / batch 8.4: two clocks in one gate
#
# These tests need exact numbers, so they build their own gate on a fixed clock instead of using the
# `data_gate` fixture (whose clock is the real one, which is right for a threshold test and wrong for
# an arithmetic test). `max_quote_age_seconds` is 5.0 throughout — pinned by
# `TestQuoteGate::test_boundary_age_is_allowed` above, which allows 4.9 s.
NOW = datetime(2026, 11, 27, 6, 43, 35, tzinfo=UTC)


def _gate(limits: Any) -> DataQualityGate:
    return DataQualityGate(limits, now_fn=lambda: NOW)


def _quote(*, received: datetime, venue: datetime | None) -> MarketSnapshot:
    return MarketSnapshot(
        instrument_id="INS-X",
        venue="BYBIT",
        bid=D("1"),
        ask=D("2"),
        observed_at=received,
        venue_timestamp=venue,
    )


def _book(*, received: datetime, venue: datetime | None) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id="INS-X",
        venue="BYBIT",
        bids=((D("1"), D("1")),),
        asks=((D("2"), D("1")),),
        observed_at=received,
        venue_timestamp=venue,
        entitlement="LIVE",
    )


class TestTheGateAgesOurClockAndReportsTheVenues:
    """F-14's staleness consequence, pinned: the threshold is applied to *our* receipt time.

    Before batch 8.4 ``observed_at`` held the venue's stamp, so ``age_seconds(observed_at)`` measured
    the venue's clock while the gate called the number ours. A venue running ahead made fresh data
    look stale — or tripped the future-timestamp fault outright — and a venue running behind made
    stale data look fresh, which is the dangerous direction because it is the one that allows new
    risk. Neither direction can even be constructed now without naming both clocks, which is the
    point of the four tests below: they are the two failure modes F-14 described, made checkable.
    """

    def test_a_venue_running_behind_does_not_make_stale_data_look_fresh(self, data_gate_limits: Any) -> None:
        """The dangerous direction: our receipt is 30 s old, the venue's stamp is 2 s old.

        Aging the venue's stamp would call this LIVE and allow new risk on data we received half a
        minute ago. The gate ages the receipt time, so it is STALE, and the venue's much younger
        stamp is published beside the verdict rather than substituted into it.
        """
        gate = _gate(data_gate_limits)
        result = gate.check_quote(
            _quote(received=NOW - timedelta(seconds=30), venue=NOW - timedelta(seconds=2))
        )
        assert result.status is DataStatus.STALE
        assert not result.new_risk_allowed
        assert result.details["age_seconds"] == 30.0
        assert result.details["venue_age_seconds"] == 2.0
        # Ours minus theirs, and it is negative: the venue stamped this quote 28 s *after* the moment
        # we received it, which is what a clock 28 s ahead of ours looks like. Had the gate aged the
        # venue's stamp it would have seen 2.0 s against a 5.0 s threshold and called 30 s old data
        # LIVE — new risk allowed on a quote nobody has heard from in half a minute.
        assert result.details["receipt_minus_venue_s"] == -28.0

    def test_a_venue_running_ahead_does_not_make_fresh_data_look_stale(self, data_gate_limits: Any) -> None:
        """The other direction, and the one that also used to trip the clock fault.

        The venue stamped the quote 9 s before we received it — an old quote by its own clock — but we
        received it 1 s ago, so it is LIVE. Pre-8.4 this same pair would have aged 10 s against a 5 s
        threshold and been refused as STALE; with the venue's clock ahead of ours instead,
        ``observed_at > now`` would have been true and the gate would have reported a *clock fault in
        our system* caused entirely by someone else's clock.
        """
        gate = _gate(data_gate_limits)
        result = gate.check_quote(
            _quote(received=NOW - timedelta(seconds=1), venue=NOW - timedelta(seconds=10))
        )
        assert result.status is DataStatus.LIVE
        assert result.new_risk_allowed
        assert result.details["age_seconds"] == 1.0
        assert result.details["venue_age_seconds"] == 10.0
        # Positive: the venue's stamp predates our receipt of it by 9 s, the ordinary case for a quote
        # that sat in a feed's queue before we fetched it.
        assert result.details["receipt_minus_venue_s"] == 9.0

    def test_a_venue_stamp_in_the_future_is_their_clock_and_not_our_fault(
        self, data_gate_limits: Any
    ) -> None:
        """The future check reads our receipt time only.

        A venue stamp ahead of our own clock is evidence that the venue's clock runs fast — worth
        recording, and recorded as a negative ``receipt_minus_venue_s``. It is not a fault in this
        system, and refusing the quote for it would hide the skew behind a rejection.
        """
        gate = _gate(data_gate_limits)
        result = gate.check_quote(
            _quote(received=NOW - timedelta(seconds=1), venue=NOW + timedelta(seconds=3))
        )
        assert result.status is DataStatus.LIVE
        assert result.new_risk_allowed
        assert result.details["receipt_minus_venue_s"] == -4.0
        # Negative, and deliberately not clamped to zero: `age_seconds` clamps on the contract that a
        # future stamp is flagged as a clock fault, and that flag reads our receipt time only. On the
        # venue's clock there is no such flag, so clamping would report a stamp that has not happened
        # yet as brand new. -3.0 says what it is.
        assert result.details["venue_age_seconds"] == -3.0

    def test_our_own_clock_in_the_future_is_still_a_fault(self, data_gate_limits: Any) -> None:
        """The check that the previous test must not have weakened."""
        gate = _gate(data_gate_limits)
        result = gate.check_quote(_quote(received=NOW + timedelta(seconds=1), venue=NOW))
        assert result.status is DataStatus.FAULT
        assert not result.new_risk_allowed
        assert any("future" in reason for reason in result.reasons)

    def test_a_quote_with_no_venue_stamp_is_gated_on_our_clock_and_says_what_is_missing(
        self, data_gate_limits: Any
    ) -> None:
        """Not every feed publishes a stamp, and inventing one from ours would restart F-14."""
        gate = _gate(data_gate_limits)
        result = gate.check_quote(_quote(received=NOW - timedelta(seconds=1), venue=None))
        assert result.status is DataStatus.LIVE
        assert result.details["age_seconds"] == 1.0
        assert result.details["venue_age_seconds"] is None
        assert result.details["receipt_minus_venue_s"] is None

    def test_the_venue_numbers_never_gate_anything(self, data_gate_limits: Any) -> None:
        """D-052 scoped 8.4 to making the receipt time real, not to adding thresholds.

        A threshold on the venue's clock would fail closed whenever a venue drifted, and a venue's
        clock is not ours to police. So the two extra numbers are swept across a wide range and the
        verdict must not move: the only thing that changes it is our own receipt time.
        """
        gate = _gate(data_gate_limits)
        received = NOW - timedelta(seconds=1)
        verdicts = {
            gate.check_quote(_quote(received=received, venue=venue)).new_risk_allowed
            for venue in (
                None,
                NOW - timedelta(seconds=0.5),
                NOW - timedelta(seconds=60),
                NOW - timedelta(seconds=3600),
                NOW + timedelta(seconds=60),
            )
        }
        assert verdicts == {True}

    def test_the_book_gate_publishes_the_same_two_clocks(self, data_gate_limits: Any) -> None:
        gate = _gate(data_gate_limits)
        result = gate.check_book(_book(received=NOW - timedelta(seconds=2), venue=NOW - timedelta(seconds=5)))
        assert result.status is DataStatus.LIVE
        assert result.details["age_seconds"] == 2.0
        assert result.details["venue_age_seconds"] == 5.0
        assert result.details["receipt_minus_venue_s"] == 3.0
        # And the venue's 5.0 s — exactly at the threshold, so a gate that aged this clock would have
        # to decide a boundary case about someone else's clock — did not make the verdict STALE.
        assert result.new_risk_allowed

    def test_a_stale_book_is_stale_by_our_receipt_of_it(self, data_gate_limits: Any) -> None:
        gate = _gate(data_gate_limits)
        result = gate.check_book(
            _book(received=NOW - timedelta(seconds=120), venue=NOW - timedelta(seconds=1))
        )
        assert result.status is DataStatus.STALE
        assert not result.new_risk_allowed
        assert result.details["venue_age_seconds"] == 1.0

    def test_the_clock_numbers_survive_serialisation_as_strings(self, data_gate_limits: Any) -> None:
        """`to_dict` stringifies every detail, so a `None` must not reach a consumer as a float."""
        gate = _gate(data_gate_limits)
        payload = gate.check_quote(
            _quote(received=NOW - timedelta(seconds=1), venue=NOW - timedelta(seconds=4))
        ).to_dict()
        assert payload["details"]["venue_age_seconds"] == "4.0"
        assert payload["details"]["receipt_minus_venue_s"] == "3.0"
        absent = gate.check_quote(_quote(received=NOW - timedelta(seconds=1), venue=None)).to_dict()
        assert absent["details"]["venue_age_seconds"] == "None"
        assert all(isinstance(value, str) for value in absent["details"].values())
