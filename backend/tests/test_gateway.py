"""Execution gateway, intent immutability and approval-binding tests (Section 12, 24).

The Phase 2 property that matters most: **nothing can be sent**. Every intent terminates
in governance with an explicit reason, and the refusal is audited.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from nexus.audit.log import AuditLog
from nexus.core.config import Settings
from nexus.core.errors import RejectReason
from nexus.core.ids import iso_utc, new_idempotency_key, utc_now
from nexus.data.freshness import DataQualityGate
from nexus.execution.gateway import ExecutionGateway, GatewayStatus
from nexus.execution.halt import HaltManager, HaltScope
from nexus.execution.intent import ApprovalRecord, TradeIntent, build_intent_digest, new_intent
from nexus.execution.orders import OrderState
from nexus.risk.engine import RiskEngine

D = Decimal


def make_intent(**overrides: object) -> TradeIntent:
    payload: dict[str, object] = {
        "decision_id": "DEC-TEST",
        "instrument_id": "INS-BTCUSDT-PERP-BYBIT",
        "venue": "BYBIT",
        "account_id": "BYBIT-UNI-001",
        "side": "LONG",
        "order_type": "LIMIT",
        "quantity": D("0.25"),
        "limit_price": D("100000"),
        "entry_price": D("100000"),
        "protective_stop": D("99000"),
        "take_profit": D("102000"),
        "quote_currency": "USDT",
        "max_loss_usd": D("250"),
        "strategy_id": "STR-TEST",
        "evidence_summary": "funding neutral, trend intact on 1h",
        "counter_case": "resistance overhead; liquidity thin into US close",
        "exit_plan": "stop at 99000; time exit after 6h without progress",
        "idempotency_key": new_idempotency_key(),
        "environment": "PAPER",
    }
    payload.update(overrides)
    return new_intent(**payload)  # type: ignore[arg-type]


def make_approval(
    intent: TradeIntent, *, step_up: bool = True, expires_in: timedelta | None = None
) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id="APR-TEST",
        intent_id=intent.intent_id,
        intent_digest=intent.digest(),
        approved_by="OWNER",
        approved_at=iso_utc(utc_now()),
        expires_at=iso_utc(utc_now() + expires_in) if expires_in else None,
        step_up_verified=step_up,
    )


@pytest.fixture
def gateway(
    settings: Settings,
    audit_log: AuditLog,
    halt_manager: HaltManager,
    conservative_engine: RiskEngine,
    data_gate: DataQualityGate,
) -> ExecutionGateway:
    return ExecutionGateway(
        settings=settings,
        halt=halt_manager,
        audit=audit_log,
        data_gate=data_gate,
        risk_engine=conservative_engine,
        adapters={},  # Phase 2: no venue adapters exist
    )


class TestIntentImmutability:
    def test_intent_is_frozen(self) -> None:
        intent = make_intent()
        with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass
            intent.quantity = D("99")  # type: ignore[misc]

    def test_digest_is_stable(self) -> None:
        intent = make_intent()
        assert intent.digest() == intent.digest()

    def test_digest_changes_with_quantity(self) -> None:
        a = make_intent()
        b = make_intent(quantity=D("0.26"))
        assert a.digest() != b.digest()

    def test_digest_changes_with_stop(self) -> None:
        a = make_intent()
        b = make_intent(protective_stop=D("98900"))
        assert a.digest() != b.digest()

    def test_digest_ignores_narrative_fields(self) -> None:
        a = make_intent(evidence_summary="one")
        b = make_intent(evidence_summary="completely different narrative")
        assert a.digest() == b.digest()

    def test_digest_matches_material_dict(self) -> None:
        intent = make_intent()
        assert intent.digest() == build_intent_digest(intent.to_material_dict())

    def test_zero_quantity_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_intent(quantity=D("0"))

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_intent(quantity=D("-1"))

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_intent(side="FLAT")

    def test_non_finite_decimal_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_intent(quantity=Decimal("NaN"))

    def test_to_dict_omits_secret_material(self) -> None:
        payload = make_intent().to_dict()
        assert "idempotency_key" not in payload
        assert payload["idempotency_key_present"] is True

    def test_expiry_detection(self) -> None:
        expired = make_intent(expires_at=iso_utc(utc_now() - timedelta(minutes=1)))
        assert expired.is_expired()
        live = make_intent(expires_at=iso_utc(utc_now() + timedelta(minutes=5)))
        assert not live.is_expired()
        assert not make_intent().is_expired()  # no expiry set


class TestApprovalBinding:
    def test_matching_digest_binds(self) -> None:
        intent = make_intent()
        assert make_approval(intent).binds(intent)

    def test_changed_intent_invalidates_approval(self) -> None:
        intent = make_intent()
        approval = make_approval(intent)
        mutated = make_intent(quantity=D("0.5"))
        assert not approval.binds(mutated)

    def test_different_intent_id_does_not_bind(self) -> None:
        approval = make_approval(make_intent())
        assert not approval.binds(make_intent())

    def test_expired_approval_detected(self) -> None:
        intent = make_intent()
        approval = make_approval(intent, expires_in=timedelta(seconds=-1))
        assert approval.is_expired()


class TestGatewayRefusal:
    def test_phase2_refuses_everything(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        result = gateway.submit(
            intent,
            approval=make_approval(intent),
            portfolio=empty_portfolio,
            quote=fresh_btc_quote,
        )
        assert result.status is GatewayStatus.REFUSED
        assert result.order_state is OrderState.REJECTED_BY_GOVERNANCE
        assert result.order_id is None

    def test_refusal_names_missing_adapter(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert any(RejectReason.VENUE_NOT_SUPPORTED.value in r for r in result.reasons)

    def test_refusal_names_live_trading_disabled(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert any("LIVE_TRADING_DISABLED" in r for r in result.reasons)

    def test_refusal_is_audited(
        self, gateway: ExecutionGateway, audit_log: AuditLog, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert audit_log.length >= 1
        assert audit_log.verify() == []

    def test_halt_blocks_non_reduce_only(
        self,
        gateway: ExecutionGateway,
        halt_manager: HaltManager,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        halt_manager.engage(reason="incident")
        intent = make_intent()
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert any(RejectReason.HALT_ACTIVE.value in r for r in result.reasons)

    def test_kill_switch_blocks_even_reduce_only(
        self,
        gateway: ExecutionGateway,
        halt_manager: HaltManager,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        halt_manager.engage(scope=HaltScope.ALL_TRADING, reason="kill switch")
        intent = make_intent(reduce_only=True)
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert any(RejectReason.KILL_SWITCH_ACTIVE.value in r for r in result.reasons)

    def test_stale_quote_blocks(
        self, gateway: ExecutionGateway, empty_portfolio: object, stale_btc_quote: object
    ) -> None:
        intent = make_intent()
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=stale_btc_quote
        )
        assert any(RejectReason.DATA_STALE.value in r for r in result.reasons)

    def test_missing_quote_blocks(self, gateway: ExecutionGateway, empty_portfolio: object) -> None:
        intent = make_intent()
        result = gateway.submit(intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=None)
        assert any(RejectReason.DATA_UNAVAILABLE.value in r for r in result.reasons)

    def test_missing_portfolio_blocks(self, gateway: ExecutionGateway, fresh_btc_quote: object) -> None:
        intent = make_intent()
        result = gateway.submit(intent, approval=make_approval(intent), portfolio=None, quote=fresh_btc_quote)
        assert any(RejectReason.DATA_UNAVAILABLE.value in r for r in result.reasons)

    def test_approval_digest_mismatch_blocks(
        self,
        audit_log: AuditLog,
        halt_manager: HaltManager,
        conservative_engine: RiskEngine,
        data_gate: DataQualityGate,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        gw = ExecutionGateway(
            settings=Settings(
                _env_file=None,
                environment="LIVE",  # type: ignore[arg-type]
                live_trading_enabled=True,
                legal_review_complete=True,
                owner_live_authority_granted=True,
            ),
            halt=halt_manager,
            audit=audit_log,
            data_gate=data_gate,
            risk_engine=conservative_engine,
        )
        intent = make_intent()
        stale_approval = make_approval(make_intent(quantity=D("9")))  # different digest
        result = gw.submit(
            intent,
            approval=stale_approval,
            portfolio=empty_portfolio,
            quote=fresh_btc_quote,
            mandate_active=True,
            venue_live_verified=True,
            phase_gate_complete=True,
        )
        assert result.status is GatewayStatus.REFUSED
        assert any(RejectReason.APPROVAL_INTENT_MISMATCH.value in r for r in result.reasons)

    def test_missing_approval_blocks_when_authority_granted(
        self,
        live_capable_settings: Settings,
        audit_log: AuditLog,
        halt_manager: HaltManager,
        conservative_engine: RiskEngine,
        data_gate: DataQualityGate,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        gw = ExecutionGateway(
            settings=live_capable_settings,
            halt=halt_manager,
            audit=audit_log,
            data_gate=data_gate,
            risk_engine=conservative_engine,
        )
        result = gw.submit(
            make_intent(),
            approval=None,
            portfolio=empty_portfolio,
            quote=fresh_btc_quote,
            mandate_active=True,
            venue_live_verified=True,
            phase_gate_complete=True,
        )
        assert result.status is GatewayStatus.REFUSED
        assert any(RejectReason.APPROVAL_MISSING.value in r for r in result.reasons)

    def test_live_approval_requires_step_up(
        self,
        live_capable_settings: Settings,
        audit_log: AuditLog,
        halt_manager: HaltManager,
        conservative_engine: RiskEngine,
        data_gate: DataQualityGate,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        gw = ExecutionGateway(
            settings=live_capable_settings,
            halt=halt_manager,
            audit=audit_log,
            data_gate=data_gate,
            risk_engine=conservative_engine,
        )
        intent = make_intent()
        result = gw.submit(
            intent,
            approval=make_approval(intent, step_up=False),
            portfolio=empty_portfolio,
            quote=fresh_btc_quote,
            mandate_active=True,
            venue_live_verified=True,
            phase_gate_complete=True,
        )
        assert result.status is GatewayStatus.REFUSED
        assert any("STEP_UP_REQUIRED" in r for r in result.reasons)

    def test_expired_intent_blocks(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent(expires_at=iso_utc(utc_now() - timedelta(seconds=30)))
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert any(RejectReason.APPROVAL_EXPIRED.value in r for r in result.reasons)

    def test_risk_refusal_propagates(
        self, gateway: ExecutionGateway, drawdown_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        result = gateway.submit(
            intent, approval=make_approval(intent), portfolio=drawdown_portfolio, quote=fresh_btc_quote
        )
        assert result.status is GatewayStatus.REFUSED


class TestIdempotency:
    def test_replay_returns_original_result(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        approval = make_approval(intent)
        first = gateway.submit(intent, approval=approval, portfolio=empty_portfolio, quote=fresh_btc_quote)
        second = gateway.submit(intent, approval=approval, portfolio=empty_portfolio, quote=fresh_btc_quote)
        assert second.idempotent_replay
        assert second.status is first.status
        assert any(RejectReason.IDEMPOTENCY_CONFLICT.value in r for r in second.reasons)

    def test_replay_does_not_create_a_second_order(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        intent = make_intent()
        approval = make_approval(intent)
        gateway.submit(intent, approval=approval, portfolio=empty_portfolio, quote=fresh_btc_quote)
        replay = gateway.submit(intent, approval=approval, portfolio=empty_portfolio, quote=fresh_btc_quote)
        assert replay.order_id is None

    def test_distinct_intents_are_processed_separately(
        self, gateway: ExecutionGateway, empty_portfolio: object, fresh_btc_quote: object
    ) -> None:
        a = make_intent()
        b = make_intent()
        gateway.submit(a, approval=make_approval(a), portfolio=empty_portfolio, quote=fresh_btc_quote)
        result_b = gateway.submit(
            b, approval=make_approval(b), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        assert not result_b.idempotent_replay


class TestAdapterRegistration:
    def test_no_adapters_in_phase_two(self, gateway: ExecutionGateway) -> None:
        assert gateway.adapter_count == 0

    def test_adapter_registration_is_explicit(self, gateway: ExecutionGateway) -> None:
        class _Stub:
            pass

        gateway.register_adapter("bybit", _Stub())
        assert gateway.adapter_count == 1

    def test_registered_stub_still_cannot_send_in_phase_two(
        self,
        settings: Settings,
        audit_log: AuditLog,
        halt_manager: HaltManager,
        conservative_engine: RiskEngine,
        data_gate: DataQualityGate,
        empty_portfolio: object,
        fresh_btc_quote: object,
    ) -> None:
        gw = ExecutionGateway(
            settings=settings,
            halt=halt_manager,
            audit=audit_log,
            data_gate=data_gate,
            risk_engine=conservative_engine,
        )
        gw.register_adapter("BYBIT", object())
        intent = make_intent()
        result = gw.submit(
            intent, approval=make_approval(intent), portfolio=empty_portfolio, quote=fresh_btc_quote
        )
        # Live authority is still denied, so the adapter is never reached.
        assert result.status is GatewayStatus.REFUSED
        assert any("LIVE_TRADING_DISABLED" in r for r in result.reasons)
