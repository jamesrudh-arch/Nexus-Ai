"""API tests: the status endpoint must tell the truth about what this build can do."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus.api.app import create_app
from nexus.audit.log import AuditLog, InMemoryAuditStore
from nexus.core.config import Settings
from nexus.execution.halt import HaltManager, HaltScope
from nexus.secrets.provider import reset_secret_provider_cache


@pytest.fixture
def client(settings: Settings, audit_log: AuditLog, halt_manager: HaltManager) -> TestClient:
    app = create_app(settings=settings, audit=audit_log, halt=halt_manager)
    return TestClient(app)


class TestOpsEndpoints:
    def test_healthz(self, client: TestClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["phase"] == "2-core-foundation"

    def test_readyz_reports_environment(self, client: TestClient) -> None:
        response = client.get("/readyz")
        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["environment"] == "DISABLED"

    def test_readyz_writes_an_audit_record(self, client: TestClient, audit_log: AuditLog) -> None:
        before = audit_log.length
        client.get("/readyz")
        assert audit_log.length > before

    def test_metrics_endpoint_exposes_prometheus_text(self, client: TestClient) -> None:
        client.get("/v1/status")  # populates gauges
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "nexus_environment_state" in response.text


class TestStatusTruthfulness:
    def test_live_trading_is_reported_disabled(self, client: TestClient) -> None:
        body = client.get("/v1/status").json()
        assert body["phase_gate"]["live_trading"] is False
        assert body["phase_gate"]["real_money_orders_possible"] is False
        assert body["phase_gate"]["venue_adapters"] is False

    def test_environment_defaults_to_disabled(self, client: TestClient) -> None:
        assert client.get("/v1/status").json()["environment"] == "DISABLED"

    def test_live_authority_is_denied(self, client: TestClient) -> None:
        authority = client.get("/v1/status").json()["live_authority"]
        assert authority["status"] == "DENIED"
        assert authority["granted"] is False
        assert "LIVE_TRADING_DISABLED" in authority["blocking_reasons"]

    def test_no_venue_adapters_are_listed(self, client: TestClient) -> None:
        assert client.get("/v1/status").json()["venue_adapters"] == []

    def test_halt_state_is_reported(self, client: TestClient) -> None:
        assert client.get("/v1/status").json()["halt"]["active"] is False

    def test_risk_limits_flagged_provisional(self, client: TestClient) -> None:
        assert client.get("/v1/status").json()["risk_limits_provisional"] is True

    def test_sms_and_whatsapp_reported_unavailable(self, client: TestClient) -> None:
        channels = client.get("/v1/status").json()["alert_channels"]
        assert channels["sms"] is False
        assert channels["whatsapp"] is False
        assert channels["telegram"] is True
        assert channels["in_app"] is True

    def test_zero_cost_constraint_is_stated(self, client: TestClient) -> None:
        assert "D-019" in client.get("/v1/status").json()["cost_constraint"]

    def test_status_reflects_live_capable_settings(self, live_capable_settings: Settings) -> None:
        app = create_app(
            settings=live_capable_settings, audit=AuditLog(InMemoryAuditStore()), halt=HaltManager()
        )
        body = TestClient(app).get("/v1/status").json()
        assert body["environment"] == "LIVE"
        # Even with every static gate true, runtime gates are unmet in Phase 2.
        assert body["live_authority"]["granted"] is False
        assert "PHASE_GATE_INCOMPLETE" in body["live_authority"]["blocking_reasons"]
        assert body["phase_gate"]["real_money_orders_possible"] is False


class TestAuditEndpoint:
    def test_verify_reports_intact_chain(self, client: TestClient, audit_log: AuditLog) -> None:
        audit_log.record("test.event", {"a": 1})
        body = client.get("/v1/audit/verify").json()
        assert body["intact"] is True
        assert body["breaks"] == []
        assert body["records"] == audit_log.length

    def test_verify_exposes_chain_head(self, client: TestClient, audit_log: AuditLog) -> None:
        record = audit_log.record("test.event")
        body = client.get("/v1/audit/verify").json()
        assert body["chain_head"] == record.record_hash


class TestControlEndpointAuth:
    def test_halt_requires_a_configured_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEXUS_SECRET_OWNER_API_TOKEN", raising=False)
        reset_secret_provider_cache()
        response = client.post("/v1/halt", json={"reason": "incident"}, headers={"Authorization": "Bearer x"})
        assert response.status_code == 503  # refuses rather than allowing unauthenticated control

    def test_halt_requires_bearer_header(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        assert client.post("/v1/halt", json={"reason": "incident"}).status_code == 401

    def test_halt_rejects_wrong_token(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        response = client.post(
            "/v1/halt", json={"reason": "incident"}, headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401

    def test_halt_engages_with_valid_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, halt_manager: HaltManager
    ) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        response = client.post(
            "/v1/halt",
            json={"reason": "daily drawdown breach", "scope": "NEW_ENTRIES"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert response.status_code == 200
        assert response.json()["engaged"] is True
        assert halt_manager.active

    def test_halt_release_requires_token(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, halt_manager: HaltManager
    ) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        halt_manager.engage(reason="incident")
        response = client.post(
            "/v1/halt/release",
            json={"reason": "resolved and reconciled"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert response.status_code == 200
        assert response.json()["released"] is True
        assert not halt_manager.active

    def test_kill_switch_scope_via_api(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, halt_manager: HaltManager
    ) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        client.post(
            "/v1/halt",
            json={"reason": "suspected compromise", "scope": HaltScope.ALL_TRADING.value},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert halt_manager.state.blocks_all_trading()

    def test_short_reason_is_rejected(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        response = client.post(
            "/v1/halt", json={"reason": "x"}, headers={"Authorization": "Bearer test-owner-token"}
        )
        assert response.status_code == 422

    def test_halt_action_is_audited(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, audit_log: AuditLog
    ) -> None:
        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        reset_secret_provider_cache()
        client.post(
            "/v1/halt",
            json={"reason": "incident drill"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert audit_log.length >= 1
        assert audit_log.verify() == []


class TestAppWiring:
    def test_app_state_holds_dependencies(self, settings: Settings) -> None:
        app = create_app(settings=settings)
        assert isinstance(app.state.audit, AuditLog)
        assert isinstance(app.state.halt, HaltManager)
        assert app.state.settings is settings

    def test_openapi_is_served(self, client: TestClient) -> None:
        body: Any = client.get("/openapi.json").json()
        assert body["info"]["title"] == "NEXUS Core API"
        assert "/v1/status" in body["paths"]

    def test_no_trading_endpoints_exist(self, client: TestClient) -> None:
        paths = set(client.get("/openapi.json").json()["paths"])
        assert not any("order" in p or "trade" in p or "position" in p for p in paths)
