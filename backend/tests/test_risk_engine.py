"""Risk engine tests, including the specification's numeric vectors (Feasibility §8).

T-01: BTCUSDT perp, $100k equity, 1% risk ($1,000), entry $100,000, stop $99,000
      → size = $1,000 / $1,000 per unit = 1.0 BTC; notional $100k; margin at 2x = $50k.
T-02: EURUSD, $100k equity, 1% risk, 50-pip stop, $10 per pip per lot
      → size = $1,000 / (50 × $10) = 2.0 lots.
"""

from __future__ import annotations

from decimal import Decimal

from nexus.core.errors import RejectReason
from nexus.risk.engine import RiskEngine, size_from_risk
from nexus.risk.portfolio import PortfolioSnapshot
from tests.conftest import D, btc_request, eurusd_request


class TestCoreFormula:
    def test_size_from_risk_basic(self) -> None:
        # $1,000 at risk, $10 loss per unit → 100 units
        assert size_from_risk(D("1000"), D("10")) == D("100")

    def test_zero_stop_distance_refuses(self) -> None:
        assert size_from_risk(D("1000"), D("0")) == Decimal("0")

    def test_negative_stop_distance_refuses(self) -> None:
        assert size_from_risk(D("1000"), D("-5")) == Decimal("0")

    def test_zero_max_loss_refuses(self) -> None:
        assert size_from_risk(D("0"), D("10")) == Decimal("0")

    def test_contract_size_scales_quantity(self) -> None:
        # 10 units of exposure per contract → 10 contracts
        assert size_from_risk(D("1000"), D("10"), D("10")) == D("10")


class TestVectorT01:
    """BTCUSDT perpetual, permissive caps so the formula is asserted exactly."""

    def test_quantity_is_one_btc(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(), empty_portfolio)
        assert result.approved, result.reasons
        assert result.quantity == D("1")

    def test_notional_is_100k(self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot) -> None:
        result = formula_engine.evaluate(btc_request(), empty_portfolio)
        assert result.notional_usd == D("100000")

    def test_risk_amount_is_exactly_one_percent(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(), empty_portfolio)
        assert result.risk_amount_usd == D("1000")

    def test_margin_at_two_x_is_50k(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(margin_rate=D("0.5")), empty_portfolio)
        assert result.effective_leverage == D("2")
        assert result.margin_required_usd == D("50000")


class TestVectorT02:
    """EURUSD 50-pip stop with $10 pip value per standard lot → 2.0 lots."""

    def test_two_lots_when_margin_allows(self, formula_engine: RiskEngine) -> None:
        portfolio = PortfolioSnapshot(
            equity_usd=D("100000"),
            cash_available_usd=D("300000"),  # unhinged cash so margin does not bind
            starting_equity_today_usd=D("100000"),
            source="TEST",
            complete=True,
        )
        result = formula_engine.evaluate(eurusd_request(margin_rate=D("0.5")), portfolio)
        assert result.approved, result.reasons
        assert result.quantity == D("2")
        assert result.risk_amount_usd == D("1000")  # 2 lots × 50 pips × $10

    def test_risk_is_never_above_the_hard_limit(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(eurusd_request(margin_rate=D("0.5")), empty_portfolio)
        assert result.risk_amount_usd <= D("1000")


class TestHardLimits:
    def test_daily_drawdown_halt_blocks_new_entries(
        self, formula_engine: RiskEngine, drawdown_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(), drawdown_portfolio)
        assert not result.approved
        assert any(RejectReason.DAILY_DRAWDOWN_HALT.value in r for r in result.reasons)

    def test_incomplete_snapshot_refuses(
        self, formula_engine: RiskEngine, incomplete_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(), incomplete_portfolio)
        assert not result.approved
        assert any("incomplete" in r for r in result.reasons)

    def test_zero_equity_refuses(self, formula_engine: RiskEngine) -> None:
        portfolio = PortfolioSnapshot(
            equity_usd=D("0"),
            cash_available_usd=D("0"),
            starting_equity_today_usd=D("0"),
            source="TEST",
            complete=True,
        )
        result = formula_engine.evaluate(btc_request(), portfolio)
        assert not result.approved

    def test_leverage_above_cap_refuses(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        # margin_rate 0.2 ⇒ 5x, above the 2x hard cap
        result = formula_engine.evaluate(btc_request(margin_rate=D("0.2")), empty_portfolio)
        assert not result.approved
        assert any(RejectReason.LEVERAGE_EXCEEDED.value in r for r in result.reasons)

    def test_stop_on_wrong_side_refuses(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        # LONG with stop above entry: undefined risk, must refuse rather than flip sign
        result = formula_engine.evaluate(
            btc_request(entry_price=D("100000"), stop_price=D("101000")), empty_portfolio
        )
        assert not result.approved
        assert any(RejectReason.SIZING_UNDETERMINED.value in r for r in result.reasons)

    def test_equal_entry_and_stop_refuses(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(
            btc_request(entry_price=D("100000"), stop_price=D("100000")), empty_portfolio
        )
        assert not result.approved

    def test_max_open_positions_blocks(self, conservative_engine: RiskEngine) -> None:
        from nexus.risk.portfolio import PositionSnapshot

        positions = tuple(
            PositionSnapshot(
                instrument_id=f"INS-X{i}",
                venue="BYBIT",
                account_id="A1",
                side="LONG",
                quantity=D("1"),
                entry_price=D("1"),
                mark_price=D("1"),
                contract_size=D("1"),
                source="TEST",
            )
            for i in range(10)
        )
        portfolio = PortfolioSnapshot(
            equity_usd=D("100000"),
            cash_available_usd=D("100000"),
            starting_equity_today_usd=D("100000"),
            positions=positions,
            source="TEST",
            complete=True,
        )
        result = conservative_engine.evaluate(btc_request(), portfolio)
        assert not result.approved
        assert any(RejectReason.MAX_OPEN_POSITIONS_EXCEEDED.value in r for r in result.reasons)

    def test_notional_cap_reduces_rather_than_refuses(
        self, conservative_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = conservative_engine.evaluate(btc_request(), empty_portfolio)
        # 1 BTC = $100k notional > $25k per-position cap and > 10% concentration,
        # so the engine must cut size, not approve the original.
        assert result.approved
        assert result.notional_usd <= D("25000")
        assert result.quantity < D("1")
        assert any(
            r["reason"] in {"max_notional_per_position", "instrument_concentration"}
            for r in result.reductions
        )

    def test_engine_never_increases_proposed_size(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(proposed_quantity=D("0.25")), empty_portfolio)
        assert result.approved
        assert result.quantity == D("0.25")
        assert any(r["reason"] == "strategy_cap" for r in result.reductions)

    def test_insufficient_margin_refuses_when_no_size_fits(self, conservative_engine: RiskEngine) -> None:
        portfolio = PortfolioSnapshot(
            equity_usd=D("100000"),
            cash_available_usd=D("0"),
            starting_equity_today_usd=D("100000"),
            source="TEST",
            complete=True,
        )
        result = conservative_engine.evaluate(btc_request(), portfolio)
        assert not result.approved
        assert any(RejectReason.INSUFFICIENT_MARGIN.value in r for r in result.reasons)

    def test_liquidity_participation_caps_size(self, formula_only_limits: object) -> None:
        from nexus.core.config import RiskLimits

        # The permissive fixture allows 100% ADV participation; pin it to 1% here so the
        # participation cap itself is what is under test.
        limits = RiskLimits(**{**formula_only_limits.model_dump(), "max_participation_of_adv_pct": 1.0})
        engine = RiskEngine(limits)
        portfolio = PortfolioSnapshot(
            equity_usd=D("1000000"),
            cash_available_usd=D("1000000"),
            starting_equity_today_usd=D("1000000"),
            source="TEST",
            complete=True,
        )
        # ADV $50k × 1% participation ⇒ $500 notional cap
        result = engine.evaluate(btc_request(average_daily_volume_quote=D("50000")), portfolio)
        assert result.approved
        assert result.notional_usd <= D("500")
        assert any(r["reason"] == "liquidity_participation" for r in result.reductions)

    def test_deep_liquidity_does_not_cap(self, formula_engine: RiskEngine) -> None:
        portfolio = PortfolioSnapshot(
            equity_usd=D("1000000"),
            cash_available_usd=D("1000000"),
            starting_equity_today_usd=D("1000000"),
            source="TEST",
            complete=True,
        )
        # ADV $50m at 100% participation ⇒ $50m cap, far above the $1m notional, so the
        # liquidity rule must not bind.
        result = formula_engine.evaluate(btc_request(average_daily_volume_quote=D("50000000")), portfolio)
        assert result.approved
        assert not any(r["reason"] == "liquidity_participation" for r in result.reductions)
        assert result.notional_usd == D("1000000")

    def test_zero_adv_refuses(self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot) -> None:
        result = formula_engine.evaluate(btc_request(average_daily_volume_quote=D("0")), empty_portfolio)
        assert not result.approved
        assert any(RejectReason.LIQUIDITY_INSUFFICIENT.value in r for r in result.reasons)

    def test_venue_minimum_blocks_after_reduction(
        self, conservative_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = conservative_engine.evaluate(btc_request(min_quantity=D("5")), empty_portfolio)
        assert not result.approved
        assert any("below venue minimum" in r for r in result.reasons)

    def test_quantity_step_is_respected(self, formula_engine: RiskEngine) -> None:
        portfolio = PortfolioSnapshot(
            equity_usd=D("100000"),
            cash_available_usd=D("300000"),
            starting_equity_today_usd=D("100000"),
            source="TEST",
            complete=True,
        )
        result = formula_engine.evaluate(
            eurusd_request(margin_rate=D("0.5"), quantity_step=D("0.1")), portfolio
        )
        assert result.approved
        assert (result.quantity / D("0.1")) % 1 == 0  # exact multiple of the step

    def test_short_side_sizes_symmetrically(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(
            btc_request(side="SHORT", entry_price=D("100000"), stop_price=D("101000")), empty_portfolio
        )
        assert result.approved, result.reasons
        assert result.quantity == D("1")
        assert result.risk_amount_usd == D("1000")

    def test_invalid_side_refuses(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        from nexus.risk.engine import PositionSizeRequest

        request = PositionSizeRequest(
            instrument_id="INS-BTCUSDT-PERP-BYBIT",
            venue="BYBIT",
            side="FLAT",  # not LONG/SHORT
            entry_price=D("100000"),
            stop_price=D("99000"),
        )
        result = formula_engine.evaluate(request, empty_portfolio)
        assert not result.approved
        assert any(RejectReason.CONFIG_INVALID.value in r for r in result.reasons)

    def test_non_positive_price_refuses(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(entry_price=D("0")), empty_portfolio)
        assert not result.approved

    def test_result_is_auditable_without_secrets(
        self, formula_engine: RiskEngine, empty_portfolio: PortfolioSnapshot
    ) -> None:
        result = formula_engine.evaluate(btc_request(), empty_portfolio)
        payload = result.to_audit_payload()
        assert payload["approved"] is True
        assert isinstance(payload["reasons"], list)
        assert "quantity" in payload
