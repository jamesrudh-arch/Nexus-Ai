"""API tests: the status endpoint must tell the truth about what this build can do."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus import __phase__
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
        # Bound to the module constant so the assertion tracks the phase instead of drifting
        # every time the phase advances (it silently broke at the Phase 2 -> 3 transition).
        assert body["phase"] == __phase__
        assert body["phase"].startswith("3-")

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
        """No route outside the paper namespace can place, amend or cancel an order.

        ``/v1/paper/*`` is exempt from the *word* check, because a simulated blotter genuinely is a
        list of orders — of orders that cannot be sent. The exemption is paid for in this same test
        rather than in a comment: the namespace has to state, from the running app, that it holds no
        adapter and can place nothing live. Renaming the routes to dodge the substring check would
        have passed the old assertion while proving less than this does.
        """
        paths = set(client.get("/openapi.json").json()["paths"])
        live_paths = {p for p in paths if not p.startswith("/v1/paper")}
        assert not any("order" in p or "trade" in p or "position" in p for p in live_paths)
        paper = client.get("/v1/paper").json()
        assert paper["can_place_live_orders"] is False
        assert paper["simulated"] is True
        assert paper["is_venue_adapter"] is False
        assert paper["adapter_count"] == 0


class TestAuditStoreSelectionFailsClosed:
    """`_default_store` must refuse a scheme it cannot honour, not quietly substitute memory.

    The audit log is the system's evidence trail. Before this, any `NEXUS_DATABASE_URL` that was
    not `sqlite:///` returned an `InMemoryAuditStore` with no warning — so an operator who followed
    `.env.example` and pointed core at the TimescaleDB the compose stack ships got an audit log
    that vanished on every restart while `/healthz` and `/readyz` both kept reporting success.
    `NatsEventBus` already states the rule for the same situation: events are never silently
    discarded. This holds the audit store to it.
    """

    @staticmethod
    def _store(url: str) -> Any:
        from nexus.api.app import _default_store

        return _default_store(Settings(_env_file=None, database_url=url))

    def test_sqlite_url_builds_the_durable_store(self, tmp_path: Any, monkeypatch: Any) -> None:
        from nexus.audit.log import SqliteAuditStore

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        store = self._store(f"sqlite:///{tmp_path}/audit.db")
        assert isinstance(store, SqliteAuditStore)
        assert (tmp_path / "audit.db").exists(), "the durable store must actually create its file"

    def test_memory_is_available_when_explicitly_chosen(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "memory")
        assert isinstance(self._store("sqlite:///./data/nexus.db"), InMemoryAuditStore)

    @pytest.mark.parametrize(
        "url",
        [
            # Both PostgreSQL spellings used to sit in this list, and `.env.example` advertised the
            # first of them until the scheme was refused. F-31 made them supported, so they moved
            # out rather than being deleted: an unreachable server is still refused at startup, and
            # the test below that one pins it, including that the DSN does not leak on the way.
            "mysql://nexus@db/nexus",
            "sqlite://relative-without-slash",
            "",
        ],
    )
    def test_an_unsupported_scheme_is_refused_not_downgraded(self, monkeypatch: Any, url: str) -> None:
        from nexus.core.errors import NexusError, RejectReason

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        with pytest.raises(NexusError) as exc:
            self._store(url)
        assert exc.value.reason is RejectReason.CONFIG_INVALID
        assert exc.value.retryable is False, "a config fault is not worth retrying unchanged"
        assert "sqlite" in exc.value.detail, "the refusal must name the scheme that does work"
        assert "NEXUS_AUDIT_BACKEND=memory" in exc.value.detail, (
            "the refusal must say how to choose an ephemeral log deliberately"
        )

    def test_the_refusal_does_not_leak_the_url_credentials(self, monkeypatch: Any) -> None:
        """The refusal is persisted and surfaced in the UI, so it travels further than the log."""
        from nexus.core.errors import NexusError

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        url = "mysql://nexus:Sup3rSecretPassword@db-host:3306/nexus"
        with pytest.raises(NexusError) as exc:
            self._store(url)
        err = exc.value
        for surface in (err.detail, str(err), repr(err.context), repr(err)):
            assert "Sup3rSecretPassword" not in surface, f"credential leaked into {surface!r}"
            assert "db-host" not in surface, f"hostname leaked into {surface!r}"
        assert err.context == {"scheme": "mysql"}, "only the scheme is safe to keep from a database URL"

    def test_create_app_refuses_to_start_rather_than_serve_without_an_audit_trail(
        self, monkeypatch: Any
    ) -> None:
        """The failure must happen at startup, not at the first write or the first restart."""
        from nexus.core.errors import NexusError, RejectReason

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        with pytest.raises(NexusError) as exc:
            create_app(
                settings=Settings(
                    _env_file=None,
                    database_url="mysql://nexus:pw@db:3306/nexus",
                )
            )
        assert exc.value.reason is RejectReason.CONFIG_INVALID

    def test_an_unreachable_postgres_server_is_refused_without_leaking_the_dsn(
        self, monkeypatch: Any
    ) -> None:
        """A supported scheme that cannot be reached is still a startup refusal, not a runtime one.

        F-31 made ``postgresql://`` a scheme this build implements, which removed the cheap
        guarantee the refusal used to have: an unparseable URL fails before anything is contacted.
        A URL that parses and points at nothing now reaches a real connection attempt, and psycopg
        answers with the hostname in the message. So the same two things are pinned on the new path
        — the failure happens at ``create_app``, and it carries neither the password nor the host.
        """
        from nexus.core.errors import NexusError, RejectReason

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        url = "postgresql+psycopg://nexus:Sup3rSecretPassword@db-host:5432/nexus"
        with pytest.raises(NexusError) as exc:
            self._store(url)
        err = exc.value
        assert err.reason is RejectReason.CONFIG_INVALID
        assert err.retryable is False, "a server that is not there is not worth retrying unchanged"
        for surface in (err.detail, str(err), repr(err.context), repr(err)):
            assert "Sup3rSecretPassword" not in surface, f"credential leaked into {surface!r}"
            assert "db-host" not in surface, f"hostname leaked into {surface!r}"
        assert err.context == {"scheme": "postgresql+psycopg"}, (
            "only the scheme is safe to keep from a database URL"
        )

    def test_the_production_default_is_the_documented_sqlite_path(self) -> None:
        """Pinned here so isolating the suite's cwd cannot silently change the shipped default."""
        assert Settings(_env_file=None).database_url == "sqlite:///./data/nexus.db"

    def test_the_default_audit_path_is_relative_to_the_process_cwd(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        """Which is why the suite runs each test in its own directory.

        `sqlite:///./data/nexus.db` resolves against the *cwd*, so before the isolation fixture in
        conftest every test that built the app with defaults appended to one shared database in
        `backend/data/` — shared between tests and between runs, and invisible to git because the
        path is ignored. For an append-only hash-chained log that is not isolation.
        """
        from pathlib import Path

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        monkeypatch.chdir(tmp_path)
        create_app(settings=Settings(_env_file=None))
        assert (Path(tmp_path) / "data" / "nexus.db").exists(), (
            "the default store did not create its database under the cwd — either the default "
            "changed or the store is no longer durable"
        )
