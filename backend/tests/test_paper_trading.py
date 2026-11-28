"""Stage 11 — the paper trading platform (D-059).

These tests are written to prove the two claims the platform makes, and to fail loudly if either
stops being true:

1. **It cannot trade for real.** Not "is not configured to" — cannot. No adapter, no network client,
   no credential, and the phase gate CI asserts on every push is unchanged by its existence.
2. **Its numbers come from real data.** A fill executes against an observed quote and is never
   invented; when there is nothing real to trade against the order does not fill and says why.

The second claim is the one that makes the first safe to look at: a paper result that could be
mistaken for a live one is the actual risk here, and it is a risk about labelling rather than about
sockets.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus import PHASE_GATE
from nexus.api.app import create_app
from nexus.api.paper import build_paper_platform
from nexus.core.config import Settings
from nexus.data.records import QuoteRecord
from nexus.domain.decision import DecisionVerb
from nexus.execution.halt import HaltManager, HaltScope
from nexus.execution.intent import TradeIntent
from nexus.execution.orders import OrderState
from nexus.paper import CAPABILITY
from nexus.paper.account import PaperAccount, rebuild_from_fills
from nexus.paper.analysis import AnalysisConfig, QuoteFlowAnalyzer
from nexus.paper.engine import PaperEngineStatus, PaperTradingEngine
from nexus.paper.fill_model import (
    FillModelConfig,
    NoFillReason,
    Side,
    SimulatedFillModel,
)
from nexus.paper.realtime import EquityFractionSizer, PaperTradingLoop

MOMENT = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def quote(
    *,
    bid: str | None = "99.00",
    ask: str | None = "101.00",
    last: str | None = "100.00",
    bid_size: str | None = "1000",
    ask_size: str | None = "1000",
    observed_at: datetime | None = None,
    delayed: bool = False,
    source: str = "TEST",
    instrument_id: str = "EQ:TEST",
    venue: str = "SIM",
    #: Defaults to the same value as `venue`'s test symbol. The pipeline resolves a record by
    #: *venue_symbol*, not by instrument_id, so a test that drives the pipeline has to pass the
    #: symbol the seeded registry actually maps — "TEST" resolves to nothing and is silently
    #: rejected, which is how an integration test can pass while proving nothing.
    venue_symbol: str = "TEST",
    #: A real quote always carries the venue's own timestamp (the OKX adapter reads it from the
    #: envelope's `ts`). Omitting it is not a harmless shortcut: the archive refuses to file a row
    #: whose partition key would have to be invented from our receipt clock, so a quote without one
    #: is rejected and never reaches the loop.
    venue_timestamp: datetime | None = None,
) -> QuoteRecord:
    return QuoteRecord(
        instrument_id=instrument_id,
        venue=venue,
        venue_symbol=venue_symbol,
        bid=None if bid is None else Decimal(bid),
        ask=None if ask is None else Decimal(ask),
        bid_size=None if bid_size is None else Decimal(bid_size),
        ask_size=None if ask_size is None else Decimal(ask_size),
        last=None if last is None else Decimal(last),
        observed_at=observed_at or MOMENT,
        venue_timestamp=venue_timestamp or observed_at or MOMENT,
        source=source,
        delayed=delayed,
    )


def intent(
    *,
    intent_id: str = "PPI-1",
    side: str = "LONG",
    quantity: str = "10",
    order_type: str = "MARKET",
    limit_price: str | None = None,
    reduce_only: bool = False,
    instrument_id: str = "EQ:TEST",
    venue: str = "SIM",
) -> TradeIntent:
    return TradeIntent(
        intent_id=intent_id,
        decision_id="ANL-1",
        instrument_id=instrument_id,
        venue=venue,
        account_id="PAPER-MAIN",
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        limit_price=None if limit_price is None else Decimal(limit_price),
        reduce_only=reduce_only,
        environment="PAPER",
    )


def engine(**kwargs: Any) -> PaperTradingEngine:
    kwargs.setdefault("account", PaperAccount(account_id="PAPER-TEST"))
    return PaperTradingEngine(**kwargs)


def rising_market(
    *, ticks: int = 30, step: str = "0.25", start: str = "100"
) -> list[tuple[QuoteRecord, datetime]]:
    """A steadily rising feed with fresh timestamps, for driving the loop end to end."""
    price = Decimal(start)
    out: list[tuple[QuoteRecord, datetime]] = []
    for index in range(ticks):
        price += Decimal(step)
        moment = MOMENT + timedelta(seconds=index)
        out.append(
            (
                quote(
                    bid=str(price - Decimal("0.02")),
                    ask=str(price + Decimal("0.02")),
                    last=str(price),
                    observed_at=moment,
                ),
                moment,
            )
        )
    return out


def permissive_analysis() -> AnalysisConfig:
    """A band loose enough that a rising market produces actionable verdicts."""
    return AnalysisConfig(
        minimum_history=4,
        window=20,
        momentum_threshold_bps=Decimal("5"),
        confidence_low=Decimal("0.20"),
        confidence_high=Decimal("0.60"),
    )


class TestItCannotTradeForReal:
    """Claim 1. If any of these fails, the phase gate CI asserts is no longer telling the truth."""

    def test_the_phase_gate_is_unchanged_by_the_paper_package(self) -> None:
        assert PHASE_GATE["live_trading"] is False
        assert PHASE_GATE["venue_adapters"] is False
        assert PHASE_GATE["real_money_orders_possible"] is False
        assert PHASE_GATE["order_capability"] is False
        assert PHASE_GATE["phase"] == 3

    def test_the_published_capability_matches_the_objects(self) -> None:
        built = engine()
        assert CAPABILITY["can_place_live_orders"] is False
        assert built.can_place_live_orders is False
        assert built.simulated is True
        assert built.is_venue_adapter is False
        assert built.adapter_count == 0

    def test_the_loop_publishes_the_same_refusal(self) -> None:
        loop = PaperTradingLoop(engine=engine())
        assert loop.can_place_live_orders is False
        assert loop.simulated is True
        assert loop.describe()["can_place_live_orders"] is False

    def test_registering_the_paper_engine_as_an_adapter_is_not_a_thing_it_does(self) -> None:
        """The gateway is never handed the paper engine, so its step-7 refusal still stands."""
        from nexus.execution.gateway import ExecutionGateway

        class _Audit:
            # `payload` is unused: the gateway needs a record id back, not an echo of what it sent.
            def record(self, kind: str, payload: dict[str, Any]) -> Any:  # noqa: ARG002
                return type("Entry", (), {"record_id": f"AUD-{kind}"})()

        gateway = ExecutionGateway(settings=Settings(), halt=HaltManager(audit=None), audit=_Audit())
        assert gateway.adapter_count == 0
        result = gateway.submit(intent())
        assert result.refused
        assert any("no adapter for" in reason for reason in result.reasons)

    def test_no_paper_module_imports_a_network_client_or_reads_a_credential(self) -> None:
        """The incapacity is structural, not a matter of configuration.

        Parsed rather than grepped: these docstrings say "there is no socket" in so many words, and a
        text search for `socket` reports the sentence that denies it as an offence.
        """
        import ast
        from pathlib import Path

        package = Path(__file__).resolve().parent.parent / "src" / "nexus" / "paper"
        forbidden_modules = {"httpx", "requests", "urllib", "aiohttp", "socket", "websockets", "http"}
        forbidden_names = {"getenv", "environ", "load_dotenv"}
        offenders: list[str] = []
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_modules:
                            offenders.append(f"{path.name}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[0] in forbidden_modules:
                        offenders.append(f"{path.name}:{node.lineno}: from {node.module}")
                elif isinstance(node, ast.Name) and node.id in forbidden_names:
                    offenders.append(f"{path.name}:{node.lineno}: {node.id}")
                elif isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                    offenders.append(f"{path.name}:{node.lineno}: .{node.attr}")
        assert offenders == [], f"the paper package must not reach a network or read env: {offenders}"

    def test_every_result_and_snapshot_is_labelled_simulated(self) -> None:
        built = engine()
        result = built.run(intent(), quote=quote(), now=MOMENT)
        assert result.simulated is True
        assert result.environment == "PAPER"
        payload = result.to_audit_payload()
        assert payload["simulated"] is True
        assert payload["environment"] == "PAPER"
        snapshot = built.snapshot()
        assert snapshot.simulated is True
        assert snapshot.environment == "PAPER"


class TestTheFillModelNeverInventsAPrice:
    """Claim 2, at the level where a lie would be cheapest to tell."""

    def test_a_buy_crosses_to_the_ask_and_a_sell_to_the_bid(self) -> None:
        model = SimulatedFillModel(FillModelConfig(slippage_bps=Decimal("0")))
        bought = model.simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(bid="99", ask="101"),
            now=MOMENT,
        )
        sold = model.simulate(
            order_id="PPO-2",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.SELL,
            quantity=Decimal("10"),
            quote=quote(bid="99", ask="101"),
            now=MOMENT,
        )
        assert bought.fills[0].price == Decimal("101.00000000")
        assert sold.fills[0].price == Decimal("99.00000000")
        # Filling at the mid would be a gift no venue gives; both sides paid the spread.
        assert bought.average_price is not None and bought.average_price > Decimal("100")
        assert sold.average_price is not None and sold.average_price < Decimal("100")

    def test_slippage_is_never_favourable_over_many_draws(self) -> None:
        """A favourable draw would let a strategy look profitable because the simulator was kind."""
        model = SimulatedFillModel(FillModelConfig(slippage_bps=Decimal("25"), seed=7))
        for index in range(200):
            outcome = model.simulate(
                order_id=f"PPO-{index}",
                instrument_id="EQ:TEST",
                venue="SIM",
                side=Side.BUY,
                quantity=Decimal("1"),
                quote=quote(bid="99", ask="101"),
                now=MOMENT,
            )
            fill = outcome.fills[0]
            assert fill.price >= Decimal("101"), f"draw {index} filled below the ask"

    def test_a_fixed_seed_replays_the_same_fills(self) -> None:
        def run(seed: int) -> tuple[str, ...]:
            model = SimulatedFillModel(FillModelConfig(seed=seed))
            return tuple(
                str(
                    model.simulate(
                        order_id=f"PPO-{i}",
                        instrument_id="EQ:TEST",
                        venue="SIM",
                        side=Side.BUY,
                        quantity=Decimal("1"),
                        quote=quote(),
                        now=MOMENT,
                    )
                    .fills[0]
                    .price
                )
                for i in range(20)
            )

        assert run(42) == run(42)
        assert run(42) != run(43)

    def test_no_quote_means_no_fill_rather_than_a_guess(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=None,
            now=MOMENT,
        )
        assert not outcome.filled
        assert outcome.no_fill_reason is NoFillReason.NO_QUOTE
        assert outcome.remaining_quantity == Decimal("10")

    def test_a_one_sided_quote_cannot_be_crossed(self) -> None:
        one_sided = quote(ask=None)
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=one_sided,
            now=MOMENT,
        )
        assert outcome.no_fill_reason is NoFillReason.NO_EXECUTABLE_SIDE

    def test_a_stale_quote_is_refused_not_traded(self) -> None:
        outcome = SimulatedFillModel(FillModelConfig(max_quote_age_seconds=Decimal("30"))).simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(observed_at=MOMENT - timedelta(seconds=120)),
            now=MOMENT,
        )
        assert outcome.no_fill_reason is NoFillReason.STALE_QUOTE
        assert outcome.quote_age_seconds == Decimal("120.000")

    def test_a_crossed_book_is_a_data_problem_not_a_price(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(bid="102", ask="101"),
            now=MOMENT,
        )
        assert outcome.no_fill_reason is NoFillReason.CROSSED_OR_LOCKED

    def test_a_delayed_feed_is_refused_because_the_edge_is_not_ours(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(delayed=True),
            now=MOMENT,
        )
        assert outcome.no_fill_reason is NoFillReason.DELAYED_DATA_REFUSED

    def test_a_limit_the_market_never_reached_stays_working(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(bid="99", ask="101"),
            limit_price=Decimal("95"),
            now=MOMENT,
        )
        assert outcome.no_fill_reason is NoFillReason.LIMIT_NOT_MARKETABLE
        assert not outcome.filled

    def test_displayed_size_caps_the_fill_and_reports_the_remainder(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("500"),
            quote=quote(ask_size="120"),
            now=MOMENT,
        )
        assert outcome.partially_filled
        assert outcome.filled_quantity == Decimal("120")
        assert outcome.remaining_quantity == Decimal("380")

    def test_assuming_infinite_depth_is_a_choice_and_it_is_off_by_default(self) -> None:
        unlimited = SimulatedFillModel(FillModelConfig(respect_displayed_size=False))
        outcome = unlimited.simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("500"),
            quote=quote(ask_size="120"),
            now=MOMENT,
        )
        assert outcome.filled_quantity == Decimal("500")

    def test_commission_has_a_floor_so_small_fills_are_not_free(self) -> None:
        outcome = SimulatedFillModel(
            FillModelConfig(commission_bps=Decimal("5"), minimum_commission=Decimal("0.10"))
        ).simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("0.0001"),
            quote=quote(),
            now=MOMENT,
        )
        assert outcome.total_commission == Decimal("0.10000000")

    def test_a_fill_carries_the_real_quote_it_executed_against(self) -> None:
        outcome = SimulatedFillModel().simulate(
            order_id="PPO-1",
            instrument_id="EQ:TEST",
            venue="SIM",
            side=Side.BUY,
            quantity=Decimal("10"),
            quote=quote(bid="99", ask="101", source="BYBIT-PUBLIC"),
            now=MOMENT,
        )
        fill = outcome.fills[0]
        assert fill.reference_price == Decimal("101")
        assert fill.bid_at_fill == Decimal("99")
        assert fill.ask_at_fill == Decimal("101")
        assert fill.quote_source == "BYBIT-PUBLIC"
        assert fill.quote_observed_at is not None
        assert fill.simulated is True

    def test_an_absurd_slippage_refuses_instead_of_booking_a_free_position(self) -> None:
        model = SimulatedFillModel(FillModelConfig(slippage_bps=Decimal("200000")))
        with pytest.raises(ValueError, match="refusing to guess"):
            model.simulate(
                order_id="PPO-1",
                instrument_id="EQ:TEST",
                venue="SIM",
                side=Side.SELL,
                quantity=Decimal("1"),
                quote=quote(bid="1", ask="2"),
                now=MOMENT,
            )

    def test_a_configuration_that_would_flatter_the_simulation_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            FillModelConfig(slippage_bps=Decimal("-1")).validated()
        with pytest.raises(ValueError, match="must be positive"):
            FillModelConfig(max_quote_age_seconds=Decimal("0")).validated()


class TestTheAccountKeepsHonestBooks:
    def test_buying_spends_cash_and_selling_returns_it(self) -> None:
        account = PaperAccount(
            account_id="P", simulated_cash=Decimal("10000"), starting_cash=Decimal("10000")
        )
        after_buy = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("1"),
        )
        assert after_buy.simulated_cash == Decimal("8999.00")
        after_sell = after_buy.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="SELL",
            quantity=Decimal("10"),
            price=Decimal("110"),
            commission=Decimal("1"),
        )
        assert after_sell.simulated_cash == Decimal("10098.00")
        assert after_sell.realized_pnl == Decimal("100.00")
        assert after_sell.position("EQ:T", "SIM").is_flat

    def test_the_receiver_is_never_mutated(self) -> None:
        account = PaperAccount(account_id="P")
        account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("0"),
        )
        assert account.simulated_cash == Decimal("100000")
        assert account.positions == ()

    def test_adding_to_a_position_averages_the_entry(self) -> None:
        account = PaperAccount(account_id="P")
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("0"),
        )
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("200"),
            commission=Decimal("0"),
        )
        held = account.position("EQ:T", "SIM")
        assert held is not None
        assert held.quantity == Decimal("20.00000000")
        assert held.average_entry == Decimal("150.00000000")

    def test_reducing_without_closing_leaves_the_entry_alone(self) -> None:
        account = PaperAccount(account_id="P")
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("0"),
        )
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="SELL",
            quantity=Decimal("4"),
            price=Decimal("120"),
            commission=Decimal("0"),
        )
        held = account.position("EQ:T", "SIM")
        assert held is not None
        assert held.quantity == Decimal("6.00000000")
        assert held.average_entry == Decimal("100.00000000")
        assert account.realized_pnl == Decimal("80.00")

    def test_flipping_through_flat_books_both_legs(self) -> None:
        account = PaperAccount(account_id="P")
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("0"),
        )
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="SELL",
            quantity=Decimal("25"),
            price=Decimal("120"),
            commission=Decimal("0"),
        )
        held = account.position("EQ:T", "SIM")
        assert held is not None
        assert held.quantity == Decimal("-15.00000000")
        assert held.side == "SHORT"
        assert held.average_entry == Decimal("120.00000000")
        assert account.realized_pnl == Decimal("200.00")

    def test_an_account_can_be_rebuilt_from_its_fill_ledger(self) -> None:
        """The ledger is the record; the account is a projection. This proves the projection is safe."""
        account = PaperAccount(account_id="P", starting_cash=Decimal("5000"), simulated_cash=Decimal("5000"))
        ledger: list[dict[str, Any]] = []
        for side, qty, price in (("BUY", "10", "100"), ("BUY", "5", "110"), ("SELL", "12", "130")):
            account = account.apply_fill(
                instrument_id="EQ:T",
                venue="SIM",
                side=side,
                quantity=Decimal(qty),
                price=Decimal(price),
                commission=Decimal("0.50"),
                at="2026-11-25T12:00:00+00:00",
            )
            ledger.append(
                {
                    "instrument_id": "EQ:T",
                    "venue": "SIM",
                    "side": side,
                    "quantity": qty,
                    "price": price,
                    "commission": "0.50",
                    "filled_at": "2026-11-25T12:00:00+00:00",
                }
            )
        rebuilt = rebuild_from_fills(account_id="P", fills=ledger, starting_cash=Decimal("5000"))
        assert rebuilt.simulated_cash == account.simulated_cash
        assert rebuilt.realized_pnl == account.realized_pnl
        assert rebuilt.commission_paid == account.commission_paid
        assert rebuilt.position("EQ:T", "SIM").quantity == account.position("EQ:T", "SIM").quantity
        assert rebuilt.position("EQ:T", "SIM").average_entry == account.position("EQ:T", "SIM").average_entry

    def test_equity_without_a_mark_is_carried_at_entry_and_says_so(self) -> None:
        account = PaperAccount(account_id="P")
        account = account.apply_fill(
            instrument_id="EQ:T",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("0"),
        )
        unmarked = account.snapshot()
        assert unmarked.unrealized_pnl == Decimal("0")
        assert unmarked.positions_carried_at_entry == ("EQ:T@SIM",)
        assert unmarked.positions_marked_with_real_data == 0

        marked = account.snapshot(marks={("EQ:T", "SIM"): Decimal("130")})
        assert marked.unrealized_pnl == Decimal("300.00")
        assert marked.positions_carried_at_entry == ()
        assert marked.positions_marked_with_real_data == 1
        assert marked.equity > unmarked.equity

    def test_a_zero_or_negative_fill_is_refused(self) -> None:
        account = PaperAccount(account_id="P")
        with pytest.raises(ValueError, match="positive quantity"):
            account.apply_fill(
                instrument_id="EQ:T",
                venue="SIM",
                side="BUY",
                quantity=Decimal("0"),
                price=Decimal("1"),
                commission=Decimal("0"),
            )
        with pytest.raises(ValueError, match="positive price"):
            account.apply_fill(
                instrument_id="EQ:T",
                venue="SIM",
                side="BUY",
                quantity=Decimal("1"),
                price=Decimal("-5"),
                commission=Decimal("0"),
            )


class TestTheEngineRunsTheRehearsal:
    def test_an_intent_fills_and_moves_the_account(self) -> None:
        built = engine()
        result = built.run(intent(), quote=quote(), now=MOMENT)
        assert result.status is PaperEngineStatus.SIMULATED
        assert result.order_state is OrderState.FILLED
        assert result.filled_quantity == Decimal("10")
        assert built.account.simulated_cash < Decimal("100000")
        assert built.orders(limit=10)[0]["status"] == "SIMULATED"
        assert len(built.fills(limit=10)) == 1

    def test_the_same_intent_is_never_simulated_twice(self) -> None:
        built = engine()
        first = built.run(intent(intent_id="PPI-DUP"), quote=quote(), now=MOMENT)
        second = built.run(intent(intent_id="PPI-DUP"), quote=quote(), now=MOMENT)
        assert first.status is PaperEngineStatus.SIMULATED
        assert second.order_id == first.order_id
        assert any("IDEMPOTENCY_CONFLICT" in reason for reason in second.reasons)
        assert len(built.fills(limit=10)) == 1

    def test_an_unfilled_order_is_reported_as_unfilled_not_as_a_fill(self) -> None:
        built = engine()
        result = built.run(intent(), quote=None, now=MOMENT)
        assert result.status is PaperEngineStatus.UNFILLED
        assert result.order_state is OrderState.EXPIRED
        assert result.filled_quantity == Decimal("0")
        assert built.account.simulated_cash == Decimal("100000")

    def test_a_resting_limit_is_working_not_expired(self) -> None:
        built = engine()
        result = built.run(intent(limit_price="95"), quote=quote(bid="99", ask="101"), now=MOMENT)
        assert result.status is PaperEngineStatus.UNFILLED
        assert result.order_state is OrderState.WORKING

    def test_a_partial_fill_is_labelled_partial(self) -> None:
        built = engine()
        result = built.run(intent(quantity="500"), quote=quote(ask_size="120"), now=MOMENT)
        assert result.status is PaperEngineStatus.SIMULATED_PARTIAL
        assert result.order_state is OrderState.PARTIALLY_FILLED
        assert result.filled_quantity == Decimal("120")

    def test_refused_risk_sizing_stops_the_trade(self) -> None:
        built = engine()
        result = built.run(
            intent(), quote=quote(), sizing_ok=False, sizing_reasons=("MAX_NOTIONAL",), now=MOMENT
        )
        assert result.refused
        assert result.order_state is OrderState.REJECTED_BY_GOVERNANCE
        assert "RISK:MAX_NOTIONAL" in result.reasons
        assert result.filled_quantity == Decimal("0")

    def test_a_refusal_without_a_supplied_reason_still_names_one(self) -> None:
        """`list.extend` returns None: an `or` fallback here would have been silently discarded."""
        built = engine()
        result = built.run(intent(), quote=quote(), sizing_ok=False, now=MOMENT)
        assert result.refused
        assert "RISK:sizing refused" in result.reasons

    def test_an_approval_bound_to_a_different_intent_is_rejected(self) -> None:
        class Approval:
            intent_id = "PPI-SOMETHING-ELSE"

        built = engine()
        result = built.run(intent(), quote=quote(), approval=Approval(), now=MOMENT)
        assert result.refused
        assert any("APPROVAL_MISMATCH" in reason for reason in result.reasons)

    def test_a_halt_blocks_a_new_entry_but_not_a_risk_reducing_close(self) -> None:
        halt = HaltManager(audit=None)
        halt.engage(scope=HaltScope.NEW_ENTRIES, reason="incident", triggered_by="OWNER")
        held = PaperAccount(account_id="P").apply_fill(
            instrument_id="EQ:TEST",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("101"),
            commission=Decimal("0.1"),
        )
        built = engine(account=held, halt=halt)
        opening = built.run(intent(intent_id="PPI-OPEN"), quote=quote(), now=MOMENT)
        assert opening.refused
        assert any("HALT_BLOCKS_NEW_ENTRIES" in reason for reason in opening.reasons)

        closing = built.run(
            intent(intent_id="PPI-CLOSE", side="CLOSE", reduce_only=True), quote=quote(), now=MOMENT
        )
        assert closing.status is PaperEngineStatus.SIMULATED
        assert built.account.position("EQ:TEST", "SIM").is_flat

    def test_a_kill_switch_also_permits_closing(self) -> None:
        """`allows_risk_reducing()` is unconditionally true: a halt must not trap a position."""
        halt = HaltManager(audit=None)
        halt.engage(scope=HaltScope.ALL_TRADING, reason="kill switch", triggered_by="OWNER")
        held = PaperAccount(account_id="P").apply_fill(
            instrument_id="EQ:TEST",
            venue="SIM",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("101"),
            commission=Decimal("0.1"),
        )
        built = engine(account=held, halt=halt)
        assert built.run(intent(intent_id="PPI-KS"), quote=quote(), now=MOMENT).refused
        closing = built.run(
            intent(intent_id="PPI-KS2", side="CLOSE", reduce_only=True), quote=quote(), now=MOMENT
        )
        assert closing.status is PaperEngineStatus.SIMULATED

    def test_closing_a_position_that_does_not_exist_is_refused_not_invented(self) -> None:
        built = engine()
        result = built.run(intent(side="CLOSE"), quote=quote(), now=MOMENT)
        assert result.refused
        assert any("SIDE_UNRESOLVED" in reason for reason in result.reasons)

    def test_crossing_a_wide_spread_loses_money_and_the_result_shows_it(self) -> None:
        """The lesson the platform exists to teach before real money is at stake."""
        halt_free = engine()
        halt_free.run(intent(intent_id="PPI-IN", quantity="10"), quote=quote(bid="99", ask="101"), now=MOMENT)
        closed = halt_free.run(
            intent(intent_id="PPI-OUT", side="CLOSE", reduce_only=True, quantity="10"),
            quote=quote(bid="99", ask="101"),
            now=MOMENT,
        )
        assert closed.status is PaperEngineStatus.SIMULATED
        assert halt_free.account.realized_pnl < Decimal("0")
        assert halt_free.account.commission_paid > Decimal("0")

    def test_reset_returns_the_capital_and_forgets_the_history(self) -> None:
        built = engine()
        built.run(intent(), quote=quote(), now=MOMENT)
        assert built.account.fills_applied == 1
        snapshot = built.reset()
        assert snapshot.simulated_cash == Decimal("100000")
        assert snapshot.fills_applied == 0
        # After a reset the same intent id may run again: it is a new machine.
        assert built.run(intent(), quote=quote(), now=MOMENT).status is PaperEngineStatus.SIMULATED


class TestRealTimeAnalysis:
    def test_it_abstains_when_nothing_has_been_observed(self) -> None:
        analyzer = QuoteFlowAnalyzer()
        verdict = analyzer.verdict("EQ:TEST", "SIM")
        assert verdict.verb is DecisionVerb.ABSTAIN
        assert not verdict.actionable
        assert any("NO_OBSERVATIONS" in reason for reason in verdict.reasons)

    def test_it_abstains_rather_than_guessing_from_too_little_history(self) -> None:
        analyzer = QuoteFlowAnalyzer(AnalysisConfig(minimum_history=12))
        for index in range(3):
            analyzer.observe(quote(observed_at=MOMENT + timedelta(seconds=index)))
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=2))
        assert verdict.verb is DecisionVerb.ABSTAIN
        assert verdict.observations_used == 3
        assert any("INSUFFICIENT_HISTORY" in reason for reason in verdict.reasons)

    def test_a_rising_market_produces_an_actionable_verdict_with_its_evidence(self) -> None:
        analyzer = QuoteFlowAnalyzer(permissive_analysis())
        for tick, moment in rising_market():
            analyzer.observe(tick, now=moment)
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=29))
        assert verdict.verb is DecisionVerb.ACCEPT
        assert verdict.actionable
        assert verdict.confidence >= analyzer.config.confidence_high
        assert Decimal(verdict.evidence["momentum_bps"]) > 0
        assert verdict.evidence["source"] == "TEST"

    def test_a_falling_market_says_exit_not_accept(self) -> None:
        analyzer = QuoteFlowAnalyzer(permissive_analysis())
        for tick, moment in rising_market(step="-0.25"):
            analyzer.observe(tick, now=moment)
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=29))
        assert verdict.verb is DecisionVerb.EXIT
        assert Decimal(verdict.evidence["momentum_bps"]) < 0

    def test_a_flat_market_waits(self) -> None:
        analyzer = QuoteFlowAnalyzer(permissive_analysis())
        for tick, moment in rising_market(step="0.00"):
            analyzer.observe(tick, now=moment)
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=29))
        assert verdict.verb is DecisionVerb.WAIT
        assert not verdict.actionable
        assert any("NO_SIGNAL" in reason for reason in verdict.reasons)

    def test_a_verdict_inside_the_band_waits_and_says_it_was_in_the_band(self) -> None:
        """D-057: the band is the point. A single threshold would trade every marginal observation."""
        analyzer = QuoteFlowAnalyzer(
            AnalysisConfig(
                minimum_history=4,
                momentum_threshold_bps=Decimal("5"),
                confidence_low=Decimal("0.99"),
                confidence_high=Decimal("1.00"),
            )
        )
        for tick, moment in rising_market(step="0.05"):
            analyzer.observe(tick, now=moment)
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=29))
        assert verdict.verb is DecisionVerb.WAIT
        assert not verdict.actionable

    def test_a_wide_spread_is_refused_before_momentum_is_consulted(self) -> None:
        analyzer = QuoteFlowAnalyzer(
            AnalysisConfig(
                minimum_history=4, momentum_threshold_bps=Decimal("5"), max_spread_bps=Decimal("10")
            )
        )
        for index in range(10):
            analyzer.observe(
                quote(bid="90", ask="110", last="100", observed_at=MOMENT + timedelta(seconds=index))
            )
        verdict = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=9))
        assert verdict.verb is DecisionVerb.WAIT
        assert any("SPREAD_TOO_WIDE" in reason for reason in verdict.reasons)

    def test_stale_data_waits_and_a_delayed_feed_abstains(self) -> None:
        analyzer = QuoteFlowAnalyzer(permissive_analysis())
        for tick, _ in rising_market():
            analyzer.observe(tick)
        stale = analyzer.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(hours=2))
        assert stale.verb is DecisionVerb.WAIT
        assert any("STALE_DATA" in reason for reason in stale.reasons)

        delayed = QuoteFlowAnalyzer(permissive_analysis())
        for tick, moment in rising_market():
            delayed.observe(dataclasses.replace(tick, delayed=True), now=moment)
        verdict = delayed.verdict("EQ:TEST", "SIM", now=MOMENT + timedelta(seconds=29))
        assert verdict.verb is DecisionVerb.ABSTAIN
        assert any("DELAYED_FEED" in reason for reason in verdict.reasons)

    def test_a_quote_with_one_side_missing_is_dropped_not_repaired(self) -> None:
        analyzer = QuoteFlowAnalyzer()
        one_sided = quote(ask=None)
        analyzer.observe(one_sided)
        assert analyzer.observations("EQ:TEST", "SIM") == 0

    def test_the_mark_is_a_real_last_price_and_reports_when_it_fell_back_to_the_mid(self) -> None:
        analyzer = QuoteFlowAnalyzer()
        analyzer.observe(quote(last="123.45"))
        assert analyzer.mark("EQ:TEST", "SIM") == Decimal("123.45")
        assert analyzer.mark_is_mid("EQ:TEST", "SIM") is False

        no_last = QuoteFlowAnalyzer()
        no_last.observe(quote(last=None, bid="99", ask="101"))
        assert no_last.mark("EQ:TEST", "SIM") == Decimal("100.00000000")
        assert no_last.mark_is_mid("EQ:TEST", "SIM") is True

    def test_a_band_that_cannot_be_a_band_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="confidence band"):
            AnalysisConfig(confidence_low=Decimal("0.8"), confidence_high=Decimal("0.3")).validated()
        with pytest.raises(ValueError, match="at least 2"):
            AnalysisConfig(minimum_history=1).validated()


class TestTheLoopRunsTheMachine:
    def test_quotes_are_analysed_and_traded_end_to_end(self) -> None:
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("0"),
            post_trade_cooldown_seconds=Decimal("0"),
        )
        for tick, moment in rising_market():
            loop.on_quote(tick, now=moment)
        stats = loop.stats()
        assert stats.quotes_observed == 30
        assert stats.analyses_run == 30
        assert stats.actionable_verdicts > 0
        assert stats.trades_simulated > 0
        assert built.account.fills_applied == stats.trades_simulated
        assert loop.stats().to_dict()["simulated"] is True

    def test_the_cooldown_turns_thirty_ticks_into_separate_decisions(self) -> None:
        """Without it a rising market pyramids one idea into a curve that flatters the strategy."""
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("0"),
            post_trade_cooldown_seconds=Decimal("10"),
        )
        for tick, moment in rising_market():
            loop.on_quote(tick, now=moment)
        stats = loop.stats()
        assert stats.actionable_verdicts > stats.trades_simulated
        assert stats.blocked_by_cooldown > 0
        assert stats.trades_simulated < 10

    def test_throttling_bounds_how_often_one_instrument_is_analysed(self) -> None:
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("5"),
        )
        for tick, moment in rising_market():
            loop.on_quote(tick, now=moment)
        stats = loop.stats()
        assert stats.quotes_observed == 30
        assert stats.analyses_run < 30
        assert stats.analyses_throttled > 0

    def test_the_position_limit_is_enforced(self) -> None:
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("0"),
            post_trade_cooldown_seconds=Decimal("0"),
            max_open_positions=1,
        )
        instruments = [f"EQ:T{i}" for i in range(3)]
        for index, (tick, moment) in enumerate(rising_market(ticks=40)):
            instrument = instruments[index % len(instruments)]
            loop.on_quote(
                dataclasses.replace(tick, instrument_id=instrument, venue_symbol=instrument),
                now=moment,
            )
        assert len(built.account.open_positions) <= 1
        assert loop.stats().blocked_by_position_limit > 0

    def test_an_instrument_off_the_watchlist_is_ignored(self) -> None:
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("0"),
            watchlist=("EQ:OTHER",),
        )
        for tick, moment in rising_market():
            assert loop.on_quote(tick, now=moment) is None
        assert loop.stats().quotes_observed == 0
        assert built.account.fills_applied == 0

    def test_the_sizer_never_returns_more_than_the_account_can_pay_for(self) -> None:
        built = engine()
        sizer = EquityFractionSizer(risk_fraction=Decimal("0.02"), max_position_notional=Decimal("25000"))
        quantity = sizer.quantity(price=Decimal("100"), engine=built, instrument_id="EQ:T", venue="SIM")
        assert quantity > 0
        assert quantity * Decimal("100") <= Decimal("25000")
        assert quantity * Decimal("100") <= built.account.equity()

    def test_the_sizer_returns_nothing_when_there_is_no_price(self) -> None:
        built = engine()
        sizer = EquityFractionSizer()
        assert sizer.quantity(price=Decimal("0"), engine=built, instrument_id="EQ:T", venue="SIM") == 0

    def test_the_background_worker_can_be_started_and_stopped(self) -> None:
        built = engine()
        loop = PaperTradingLoop(
            engine=built,
            analyzer=QuoteFlowAnalyzer(permissive_analysis()),
            min_analysis_interval_seconds=Decimal("0"),
            post_trade_cooldown_seconds=Decimal("0"),
        )
        loop.start()
        loop.start()  # idempotent
        assert loop.stats().running is True
        for tick, _ in rising_market():
            assert loop.submit(tick)
        loop.stop()
        assert loop.stats().running is False

    def test_a_full_queue_is_reported_rather_than_blocking_the_feed(self) -> None:
        loop = PaperTradingLoop(engine=engine(), max_queue=2)
        assert loop.submit(quote())
        assert loop.submit(quote())
        assert loop.submit(quote()) is False


class TestTheApiSurfaceIsLabelled:
    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        settings = Settings(
            paper_minimum_history=4,
            paper_momentum_threshold_bps=Decimal("5"),
            paper_confidence_low=Decimal("0.20"),
            paper_confidence_high=Decimal("0.60"),
            paper_min_analysis_interval_seconds=Decimal("0"),
            paper_post_trade_cooldown_seconds=Decimal("0"),
        )
        return TestClient(create_app(settings=settings))

    def test_every_paper_route_answers_and_is_labelled(self, client: TestClient) -> None:
        for path in (
            "/v1/paper",
            "/v1/paper/account",
            "/v1/paper/orders",
            "/v1/paper/fills",
            "/v1/paper/positions",
            "/v1/paper/analysis",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            body = response.json()
            assert body["simulated"] is True, path
            assert body["environment"] == "PAPER", path

    def test_the_status_endpoint_publishes_paper_beside_live_authority(self, client: TestClient) -> None:
        """Shown together because they look similar and mean opposite things."""
        body = client.get("/v1/status").json()
        assert body["paper"]["can_place_live_orders"] is False
        assert body["paper"]["simulated"] is True
        assert body["paper"]["environment"] == "PAPER"
        assert body["live_authority"]["status"] == "DENIED"
        assert body["phase_gate"]["venue_adapters"] is False
        assert body["phase_gate"]["order_capability"] is False

    def test_the_loop_can_be_driven_through_the_platform_and_seen_in_the_api(
        self, client: TestClient
    ) -> None:
        app = client.app
        platform = app.state.paper
        assert platform.enabled is True
        for tick, moment in rising_market():
            platform.loop.on_quote(tick, now=moment)

        account = client.get("/v1/paper/account").json()
        assert (
            Decimal(account["fills_applied"])
            if isinstance(account["fills_applied"], str)
            else account["fills_applied"] > 0
        )
        fills = client.get("/v1/paper/fills").json()
        assert fills["count"] > 0
        assert Decimal(fills["total_commission"]) > 0
        for fill in fills["fills"]:
            assert fill["simulated"] is True
            assert fill["quote_source"] == "TEST"
        orders = client.get("/v1/paper/orders").json()
        assert orders["count"] > 0
        analysis = client.get("/v1/paper/analysis").json()
        assert analysis["count"] > 0
        assert analysis["confidence_band"] == ["0.20", "0.60"]

    def test_start_and_stop_report_their_effect(self, client: TestClient) -> None:
        assert client.post("/v1/paper/start").json()["started"] is True
        assert client.post("/v1/paper/stop").json()["stopped"] is True

    def test_reset_restores_the_capital(self, client: TestClient) -> None:
        platform = client.app.state.paper
        for tick, moment in rising_market():
            platform.loop.on_quote(tick, now=moment)
        assert Decimal(client.get("/v1/paper/account").json()["fills_applied"] or "0") >= 0
        body = client.post("/v1/paper/reset").json()
        assert body["reset"] is True
        assert body["starting_cash"] == "100000"
        assert body["account"]["simulated_cash"] == "100000"
        assert body["account"]["fills_applied"] == 0

    def test_a_disabled_platform_says_so_instead_of_pretending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        settings = Settings(paper_enabled=False)
        client = TestClient(create_app(settings=settings))
        body = client.post("/v1/paper/start").json()
        assert body["started"] is False
        assert body["reason"].startswith("PAPER_DISABLED")
        assert client.get("/v1/paper/account").json()["disabled"] is True

    def test_the_stream_frame_is_labelled_before_it_streams(self) -> None:
        """SSE cannot be asserted frame-by-frame in a test client without hanging, so the builder is."""
        platform = build_paper_platform(Settings(paper_enabled=True))
        assert platform.stream_interval > 0
        description = platform.describe()
        assert description["can_place_live_orders"] is False
        assert description["network_access"] is False
        assert description["credentials_required"] is False
        assert description["engine"]["fill_model"]["simulated"] is True

    def test_the_paper_namespace_does_not_weaken_the_no_order_route_rule(self) -> None:
        """CI's lexical ban still applies everywhere outside /v1/paper, and inside it the semantic
        check above is what does the work: a route that cannot send an order is not one that is
        merely named as though it cannot."""
        app = create_app(settings=Settings())
        forbidden = ("order", "trade", "execute", "position", "withdraw")
        for route in app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/v1/paper"):
                continue
            for verb in forbidden:
                assert verb not in path.lower(), f"API exposes a trading route: {path}"


class TestTheRunnerIsAMachineNotAScaffold:
    """The composition root. Without it the loop is only ever driven by a test."""

    def test_a_feed_spec_is_parsed(self) -> None:
        from nexus.paper.runner import parse_feed

        feeds = parse_feed("bybit-public:BTCUSDT,ETHUSDT;okx-public:BTC-USDT")
        assert len(feeds) == 2
        assert feeds[0].source == "bybit-public"
        assert feeds[0].symbols == ("BTCUSDT", "ETHUSDT")
        assert feeds[1].symbols == ("BTC-USDT",)

    def test_a_source_label_is_not_used_where_a_venue_name_is_needed(self) -> None:
        """The registry resolves symbols against a venue; a source label resolves to nothing.

        Getting this wrong does not raise. It polls a live feed, receives real quotes, rejects every
        one as INSTRUMENT_UNKNOWN, and reports a flat curve that looks like a strategy that made no
        mistakes — which is why it is asserted rather than assumed.
        """
        from nexus.paper.runner import SOURCE_VENUE, parse_feed

        feeds = parse_feed("okx-public:BTC-USDT-SWAP;bybit-public:BTCUSDT")
        assert feeds[0].venue == "OKX"
        assert feeds[1].venue == "BYBIT"
        assert all(spec.venue != spec.source for spec in feeds)
        assert set(SOURCE_VENUE.values()) <= {"OKX", "BYBIT"}

    def test_a_historical_source_is_refused_because_it_cannot_serve_a_live_quote(self) -> None:
        """Feeding an archive to a real-time loop analyses a market that has already moved."""
        from nexus.paper.runner import parse_feed

        for source in ("binance-vision", "dukascopy"):
            with pytest.raises(ValueError, match="historical archive"):
                parse_feed(f"{source}:BTCUSDT")

    def test_an_unknown_source_is_refused_rather_than_ignored(self) -> None:
        from nexus.paper.runner import parse_feed

        with pytest.raises(ValueError, match="not a real-time source"):
            parse_feed("coinbase:BTC-USD")

    def test_an_empty_or_malformed_spec_is_refused(self) -> None:
        """A loop that polls nothing reports a flat curve — which looks like a strategy that made
        no mistakes at all."""
        from nexus.paper.runner import parse_feed

        for bad in ("", "   ", "bybit-public", "bybit-public:", "okx-public:  ,  "):
            with pytest.raises(ValueError):
                parse_feed(bad)

    def test_the_runner_refuses_to_start_if_the_phase_gate_would_allow_trading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus.paper import runner as runner_module

        monkeypatch.setitem(runner_module.PHASE_GATE, "live_trading", True)
        built = runner_module.PaperRunner(
            settings=Settings(), feeds=runner_module.parse_feed("okx-public:BTC-USDT-SWAP")
        )
        with pytest.raises(SystemExit, match="refusing to start the paper runner"):
            built.assert_cannot_trade_live()

    def test_the_runner_refuses_if_live_trading_is_enabled_in_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus.paper import runner as runner_module

        monkeypatch.setenv("NEXUS_LIVE_TRADING_ENABLED", "true")
        settings = Settings()
        assert settings.live_trading_enabled is True
        built = runner_module.PaperRunner(
            settings=settings, feeds=runner_module.parse_feed("okx-public:BTC-USDT-SWAP")
        )
        with pytest.raises(SystemExit, match="NEXUS_LIVE_TRADING_ENABLED"):
            built.assert_cannot_trade_live()

    def test_the_runner_starts_clean_on_the_shipped_configuration(self) -> None:
        from nexus.paper.runner import PaperRunner, parse_feed

        built = PaperRunner(settings=Settings(), feeds=parse_feed(Settings().paper_feed))
        built.assert_cannot_trade_live()  # must not raise
        report = built.report()
        assert report["simulated"] is True
        assert report["environment"] == "PAPER"
        assert report["cycles"] == 0
        assert report["quotes_seen"] == 0
        assert report["account"]["simulated_cash"] == "100000"

    async def test_accepted_quotes_reach_the_loop_through_the_pipeline_observer(self, tmp_path: Path) -> None:
        """The observer is the integration point; if it is wrong nothing ever trades in production."""
        from nexus.paper.runner import PaperRunner, parse_feed

        built = PaperRunner(
            settings=Settings(
                archive_root=str(tmp_path / "archive"),
                paper_minimum_history=2,
                paper_momentum_threshold_bps=Decimal("5"),
                paper_confidence_low=Decimal("0.20"),
                paper_confidence_high=Decimal("0.60"),
                paper_min_analysis_interval_seconds=Decimal("0"),
                paper_post_trade_cooldown_seconds=Decimal("0"),
            ),
            feeds=parse_feed("okx-public:BTC-USDT-SWAP"),
        )
        price = Decimal("50000")
        for index in range(6):
            price += Decimal("25")
            moment = MOMENT + timedelta(seconds=index)
            await built._pipeline.run(
                venue="OKX",
                quotes=(
                    quote(
                        instrument_id="INS-BTC-USDT-USDT",
                        venue="OKX",
                        venue_symbol="BTC-USDT-SWAP",
                        bid=str(price - Decimal("1")),
                        ask=str(price + Decimal("1")),
                        last=str(price),
                        observed_at=moment,
                        source="OKX-PUBLIC",
                    ),
                ),
                emit_events=False,
            )
        stats = built._loop.stats()
        assert stats.quotes_observed == 6, "the observer never received the accepted quotes"
        assert stats.analyses_run > 0
        assert built.quotes_seen == 6

    async def test_a_rejected_record_never_reaches_the_loop(self, tmp_path: Path) -> None:
        """Archive-first: the loop analyses accepted records, not everything that arrived."""
        from nexus.paper.runner import PaperRunner, parse_feed

        built = PaperRunner(
            settings=Settings(archive_root=str(tmp_path / "archive")),
            feeds=parse_feed("okx-public:BTC-USDT-SWAP"),
        )
        # Two independent reasons to reject, both of which must keep the record away from the loop:
        # a symbol the registry has never heard of, and a real symbol on a mapping whose status sits
        # below the pipeline's archive floor.
        unknown = quote(instrument_id="INS-NOPE", venue="OKX", venue_symbol="NOT-A-SYMBOL")
        report = await built._pipeline.run(venue="OKX", quotes=(unknown,), emit_events=False)
        assert report.quotes_accepted == 0
        assert built.quotes_seen == 0

        # Bybit's BTCUSDT mapping is SUPPORTED, below MINIMUM_STATUS_FOR_ARCHIVE: a real symbol,
        # still rejected. This is the case that made the original default feed accept nothing.
        below_floor = quote(venue="BYBIT", venue_symbol="BTCUSDT", source="BYBIT-PUBLIC")
        report = await built._pipeline.run(venue="BYBIT", quotes=(below_floor,), emit_events=False)
        assert report.quotes_accepted == 0, "a SUPPORTED mapping must not reach the archive or the loop"
        assert built.quotes_seen == 0

    def test_a_bounded_run_that_observed_nothing_is_a_failure(self) -> None:
        """Exit 0 for a pass in which no venue answered would report success for an outage."""
        import subprocess
        import sys

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "nexus.paper.runner",
                "--feed",
                "binance-vision:BTCUSDT",
                "--cycles",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 2
        assert "historical archive" in completed.stderr
