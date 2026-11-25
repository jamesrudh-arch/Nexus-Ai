"""Shared fixtures.

Two limit profiles are used throughout:
- ``conservative`` — the owner's PROVISIONAL profile (D-006/O-002): 1% per trade, ≤2x,
  2% daily halt, plus the default notional/concentration caps.
- ``formula_only`` — deliberately permissive caps so the *sizing formula* itself can be
  asserted against the specification's test vectors without limit interference.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from nexus.audit.log import AuditLog, InMemoryAuditStore
from nexus.core.config import RiskLimits, Settings
from nexus.core.environment import EnvironmentState
from nexus.core.ids import utc_now
from nexus.data.freshness import DataQualityGate, MarketSnapshot, OrderBookSnapshot
from nexus.execution.halt import HaltManager
from nexus.risk.engine import RiskEngine
from nexus.risk.portfolio import PortfolioSnapshot, PositionSnapshot

D = Decimal


@pytest.fixture
def conservative_limits() -> RiskLimits:
    """Owner's provisional conservative profile (defaults, stated explicitly)."""
    return RiskLimits(
        max_risk_per_trade_pct=1.0,
        max_leverage=2.0,
        daily_drawdown_halt_pct=2.0,
        max_open_positions=10,
        max_notional_per_position_usd=25_000.0,
        max_portfolio_notional_usd=100_000.0,
        max_single_instrument_exposure_pct=10.0,
        max_correlated_exposure_pct=25.0,
        min_stop_distance_pct=0.05,
        max_participation_of_adv_pct=1.0,
    )


@pytest.fixture
def formula_only_limits() -> RiskLimits:
    """Permissive caps: isolates the sizing formula from portfolio limits."""
    return RiskLimits(
        max_risk_per_trade_pct=1.0,
        max_leverage=2.0,
        daily_drawdown_halt_pct=2.0,
        max_open_positions=50,
        max_notional_per_position_usd=1_000_000.0,
        max_portfolio_notional_usd=2_000_000.0,
        max_single_instrument_exposure_pct=250.0,
        max_correlated_exposure_pct=250.0,
        min_stop_distance_pct=0.0,
        max_participation_of_adv_pct=100.0,
    )


@pytest.fixture
def settings() -> Settings:
    """Restrictive default settings: DISABLED environment, live trading off."""
    return Settings(_env_file=None)


@pytest.fixture
def live_capable_settings() -> Settings:
    """Every static gate true — used only to prove the *runtime* gates still block."""
    return Settings(
        _env_file=None,
        environment=EnvironmentState.LIVE,
        live_trading_enabled=True,
        legal_review_complete=True,
        owner_live_authority_granted=True,
    )


@pytest.fixture
def audit_log() -> AuditLog:
    return AuditLog(InMemoryAuditStore())


@pytest.fixture
def halt_manager(audit_log: AuditLog) -> HaltManager:
    return HaltManager(audit=audit_log)


@pytest.fixture
def empty_portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        equity_usd=D("100000"),
        cash_available_usd=D("100000"),
        starting_equity_today_usd=D("100000"),
        positions=(),
        observed_at=_iso_now(),
        source="TEST",
        complete=True,
    )


@pytest.fixture
def drawdown_portfolio() -> PortfolioSnapshot:
    """2.5% intraday drawdown — above the 2% halt threshold."""
    return PortfolioSnapshot(
        equity_usd=D("97500"),
        cash_available_usd=D("97500"),
        starting_equity_today_usd=D("100000"),
        realized_pnl_today_usd=D("-2500"),
        positions=(),
        observed_at=_iso_now(),
        source="TEST",
        complete=True,
    )


@pytest.fixture
def incomplete_portfolio() -> PortfolioSnapshot:
    """An account failed to report — sizing must refuse."""
    return PortfolioSnapshot(
        equity_usd=D("100000"),
        cash_available_usd=D("100000"),
        starting_equity_today_usd=D("100000"),
        positions=(),
        observed_at=_iso_now(),
        source="TEST",
        complete=False,
    )


@pytest.fixture
def portfolio_with_btc() -> PortfolioSnapshot:
    position = PositionSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        account_id="BYBIT-UNI-001",
        side="LONG",
        quantity=D("0.1"),
        entry_price=D("100000"),
        mark_price=D("100000"),
        contract_size=D("1"),
        quote_currency="USDT",
        leverage=D("2"),
        stop_price=D("99000"),
        protective_orders_confirmed=True,
        observed_at=_iso_now(),
        source="VENUE",
    )
    return PortfolioSnapshot(
        equity_usd=D("100000"),
        cash_available_usd=D("90000"),
        starting_equity_today_usd=D("100000"),
        positions=(position,),
        fx_rates={"USDT": D("1")},
        observed_at=_iso_now(),
        source="VENUE",
        complete=True,
    )


@pytest.fixture
def fresh_btc_quote() -> MarketSnapshot:
    return MarketSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        bid=D("99990"),
        ask=D("100010"),
        last=D("100000"),
        observed_at=utc_now(),
        source="WS",
    )


@pytest.fixture
def stale_btc_quote() -> MarketSnapshot:
    return MarketSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        bid=D("99990"),
        ask=D("100010"),
        last=D("100000"),
        observed_at=utc_now() - timedelta(seconds=30),
        source="WS",
    )


@pytest.fixture
def crossed_btc_quote() -> MarketSnapshot:
    return MarketSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        bid=D("100010"),
        ask=D("99990"),  # bid >= ask: crossed market
        observed_at=utc_now(),
        source="WS",
    )


@pytest.fixture
def future_btc_quote() -> MarketSnapshot:
    return MarketSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        bid=D("99990"),
        ask=D("100010"),
        observed_at=utc_now() + timedelta(seconds=120),  # clock fault
        source="WS",
    )


@pytest.fixture
def entitled_book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id="INS-BTCUSDT-PERP-BYBIT",
        venue="BYBIT",
        bids=((D("99990"), D("1.5")), (D("99980"), D("2.0"))),
        asks=((D("100010"), D("1.2")), (D("100020"), D("3.0"))),
        observed_at=utc_now(),
        entitlement="LIVE",
        source="WS",
    )


@pytest.fixture
def unentitled_book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument_id="INS-XAUUSD-MT5",
        venue="MT5",
        bids=(),
        asks=(),
        observed_at=utc_now(),
        entitlement="NONE",
        source="TERMINAL",
    )


@pytest.fixture
def data_gate(settings: Settings) -> DataQualityGate:
    return DataQualityGate(settings.data_quality)


@pytest.fixture
def conservative_engine(conservative_limits: RiskLimits) -> RiskEngine:
    return RiskEngine(conservative_limits)


@pytest.fixture
def formula_engine(formula_only_limits: RiskLimits) -> RiskEngine:
    return RiskEngine(formula_only_limits)


def _iso_now() -> str:
    from nexus.core.ids import iso_utc

    return iso_utc(utc_now())


def btc_request(**overrides: Any) -> Any:
    """BTCUSDT perpetual sizing request matching feasibility vector T-01."""
    from nexus.risk.engine import PositionSizeRequest

    payload: dict[str, Any] = {
        "instrument_id": "INS-BTCUSDT-PERP-BYBIT",
        "venue": "BYBIT",
        "side": "LONG",
        "entry_price": D("100000"),
        "stop_price": D("99000"),
        "contract_size": D("1"),
        "quote_currency": "USDT",
        "margin_rate": D("0.5"),  # 2x
        "fx_to_usd": D("1"),
    }
    payload.update(overrides)
    return PositionSizeRequest(**payload)


def eurusd_request(**overrides: Any) -> Any:
    """EURUSD sizing request matching feasibility vector T-02 (standard lot = 100k units)."""
    from nexus.risk.engine import PositionSizeRequest

    payload: dict[str, Any] = {
        "instrument_id": "INS-EURUSD-SPOT-MT5",
        "venue": "MT5",
        "side": "LONG",
        "entry_price": D("1.1000"),
        "stop_price": D("1.0950"),  # 50 pips
        "contract_size": D("100000"),  # one standard lot
        "quote_currency": "USD",
        "margin_rate": D("1"),
        "fx_to_usd": D("1"),
        "quantity_step": D("0.01"),
        "min_quantity": D("0.01"),
    }
    payload.update(overrides)
    return PositionSizeRequest(**payload)
