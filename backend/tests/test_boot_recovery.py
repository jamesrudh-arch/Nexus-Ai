"""Fail-closed boot recovery (Stage 6: findings F-3 and F-7, laws L-1, L-2, L-6).

The behaviour under test is the one the system must never get wrong: what happens at restart. A
halt must still be a halt, an order whose fate is unknown must still be unknown, and a chain that
does not verify must stop the system rather than be trusted.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus.api.app import create_app
from nexus.audit.chain import AuditRecord
from nexus.audit.log import AuditLog, InMemoryAuditStore, SqliteAuditStore
from nexus.core.config import Settings
from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.execution.gateway import ExecutionGateway, GatewayStatus
from nexus.execution.halt import HaltManager, HaltScope
from nexus.execution.intent import TradeIntent
from nexus.execution.orders import OrderState
from nexus.store.operational import PersistenceError, SqliteOperationalStore
from nexus.store.recovery import BootRefused, derive_halt_state, indeterminate_halt_state, recover
from nexus.store.schema import MIGRATIONS
from nexus.store.writeahead import reproject_missing, write_with_audit


class TamperedStore(InMemoryAuditStore):
    """An audit store whose chain does not verify: one record's hash is wrong."""

    def read_all(self) -> list[AuditRecord]:
        records = super().read_all()
        if len(records) > 1:
            original = records[1]
            records[1] = AuditRecord(
                seq=original.seq,
                event_type=original.event_type,
                actor=original.actor,
                payload=dict(original.payload),
                timestamp=original.timestamp,
                record_id=original.record_id,
                prev_hash=original.prev_hash,
                record_hash="0" * 64,
            )
        return records


class FlakyStore:
    """Delegates to a real store, but the first decision projection fails — a simulated crash."""

    def __init__(self, inner: SqliteOperationalStore) -> None:
        self._inner = inner
        self.fail_next = True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def save_decision_payload(self, payload: Any, *, audit_ref: str | None = None) -> None:
        if self.fail_next:
            self.fail_next = False
            raise PersistenceError("simulated crash between the audit write and the projection")
        self._inner.save_decision_payload(payload, audit_ref=audit_ref)


class HaltBlindStore:
    """Delegates to a real store, but cannot read the halt history."""

    def __init__(self, inner: SqliteOperationalStore) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def halt_events(self) -> Any:
        raise PersistenceError("simulated unreadable halt history")


def _durable(tmp_path: Path) -> tuple[Path, AuditLog, SqliteOperationalStore]:
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return path, audit, SqliteOperationalStore(path, audit=audit)


def _reopen(path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


def _intent(**overrides: Any) -> TradeIntent:
    payload: dict[str, Any] = {
        "intent_id": new_id("INT"),
        "decision_id": "DEC-1",
        "instrument_id": "INS-BTCUSDT-PERP-OKX",
        "venue": "OKX",
        "account_id": "OKX-DEMO-001",
        "side": "LONG",
        "order_type": "MARKET",
        "quantity": Decimal("0.1"),
        "idempotency_key": new_id("IDK"),
    }
    payload.update(overrides)
    return TradeIntent(**payload)


class TestHaltSurvivesRestart:
    def test_active_halt_is_restored_with_its_original_identity(self, tmp_path: Path) -> None:
        """Finding F-3: a restart used to clear an active halt. Law L-1 forbids it."""
        path, audit, store = _durable(tmp_path)
        manager = HaltManager(audit=audit, store=store)
        engaged = manager.engage(
            scope=HaltScope.ALL_TRADING,
            reason="venue fault",
            triggered_by="OWNER",
            affected_accounts=("OKX-DEMO-001",),
        )
        store.close()

        audit2, store2 = _reopen(path)
        report = recover(audit=audit2, store=store2)
        assert report.halted is True
        assert report.halt_state is not None
        assert report.halt_state.scope is HaltScope.ALL_TRADING
        assert report.halt_state.reason == "venue fault"
        assert report.halt_state.incident_id == engaged.incident_id
        assert report.halt_state.affected_accounts == ("OKX-DEMO-001",)
        assert report.halt_indeterminate is False

        restored = HaltManager(audit=audit2, store=store2, restored_state=report.halt_state)
        assert restored.active is True
        assert restored.state.blocks_all_trading() is True
        assert restored.history()[0]["action"] == "RESTORED"

    def test_release_then_restart_boots_unhalted(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        manager = HaltManager(audit=audit, store=store)
        manager.engage(scope=HaltScope.NEW_ENTRIES, reason="probe", triggered_by="OWNER")
        manager.release(reason="reconciled", released_by="OWNER")
        store.close()

        audit2, store2 = _reopen(path)
        report = recover(audit=audit2, store=store2)
        assert report.halted is False
        assert report.halt_state is None

    def test_widening_is_preserved_across_a_restart(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        manager = HaltManager(audit=audit, store=store)
        manager.engage(scope=HaltScope.NEW_ENTRIES, reason="first", triggered_by="OWNER")
        manager.engage(scope=HaltScope.ALL_TRADING, reason="widened", triggered_by="OWNER")
        store.close()

        audit2, store2 = _reopen(path)
        report = recover(audit=audit2, store=store2)
        assert report.halt_state is not None
        assert report.halt_state.scope is HaltScope.ALL_TRADING
        assert len(store2.halt_events()) == 2

    def test_unreadable_halt_history_fails_closed(self, tmp_path: Path) -> None:
        """An indeterminate halt state is exactly the case where guessing is unsafe."""
        path, audit, store = _durable(tmp_path)
        report = recover(audit=audit, store=HaltBlindStore(store))
        assert report.halt_indeterminate is True
        assert report.halted is True
        assert report.halt_state is not None
        assert report.halt_state.scope is HaltScope.ALL_TRADING
        assert report.halt_state.triggered_by == "BOOT_RECOVERY"

    def test_derive_halt_state_replays_in_order(self) -> None:
        store = SqliteOperationalStore(":memory:")
        for action in ("ENGAGE", "RELEASE", "ENGAGE"):
            store.save_halt_event(
                action=action,
                scope="NEW_ENTRIES",
                reason="probe",
                triggered_by="OWNER",
                at=iso_utc(utc_now()),
            )
        state = derive_halt_state(store.halt_events())
        assert state is not None and state.active is True

    def test_indeterminate_helper_is_the_kill_switch(self) -> None:
        state = indeterminate_halt_state("probe")
        assert state.scope is HaltScope.ALL_TRADING and state.active is True


class TestOrdersAtBoot:
    def test_non_terminal_orders_are_resolved_without_guessing(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        cases = {
            "ORD-SUBMITTING": OrderState.SUBMITTING,
            "ORD-WORKING": OrderState.WORKING,
            "ORD-PENDING": OrderState.PENDING_APPROVAL,
            "ORD-DRAFT": OrderState.DRAFT,
            "ORD-FILLED": OrderState.FILLED,
        }
        for order_id, state in cases.items():
            store.save_order(
                order_id=order_id,
                venue="OKX",
                account_id="OKX-DEMO-001",
                state=state,
                idempotency_key=f"IDK-{order_id}",
            )

        report = recover(audit=audit, store=store)
        assert set(report.orders_marked_unknown) == {"ORD-SUBMITTING", "ORD-WORKING"}
        assert report.orders_expired == ("ORD-PENDING",)
        assert report.orders_rejected == ("ORD-DRAFT",)
        assert report.blocks_new_risk is True

        states = {row.order_id: row.state for row in store.orders()}
        assert states["ORD-SUBMITTING"] is OrderState.UNKNOWN
        assert states["ORD-WORKING"] is OrderState.UNKNOWN
        assert states["ORD-PENDING"] is OrderState.EXPIRED
        assert states["ORD-DRAFT"] is OrderState.REJECTED_BY_GOVERNANCE
        assert states["ORD-FILLED"] is OrderState.FILLED

        reason = store.get_order("ORD-SUBMITTING")
        assert reason is not None and "reconciliation required" in str(reason["reject_reason"])

    def test_recovery_is_stable_when_run_twice(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        store.save_order(
            order_id="ORD-1",
            venue="OKX",
            account_id="A1",
            state=OrderState.SUBMITTING,
            idempotency_key="IDK-1",
        )
        first = recover(audit=audit, store=store)
        second = recover(audit=audit, store=store)
        assert first.orders_marked_unknown == ("ORD-1",)
        assert second.orders_marked_unknown == ("ORD-1",)  # UNKNOWN stays UNKNOWN, never resolved
        assert second.orders_expired == ()

    def test_recovery_is_audited(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        recover(audit=audit, store=store)
        events = [record.event_type for record in audit.records()]
        assert "boot.recovery" in events


class TestChainTrust:
    def test_broken_chain_refuses_boot(self) -> None:
        """Law L-6: state derived from a record that does not verify cannot be served."""
        store_backend = TamperedStore()
        audit = AuditLog(store_backend)
        audit.record("first", {"a": 1})
        audit.record("second", {"b": 2})
        operational = SqliteOperationalStore(":memory:")
        assert audit.verify()  # the chain is genuinely broken
        with pytest.raises(BootRefused) as excinfo:
            recover(audit=audit, store=operational)
        assert excinfo.value.reason.value == "AUDIT_CHAIN_INVALID"
        assert excinfo.value.retryable is False

    def test_broken_chain_is_not_written_to(self) -> None:
        store_backend = TamperedStore()
        audit = AuditLog(store_backend)
        audit.record("first", {"a": 1})
        audit.record("second", {"b": 2})
        before = audit.length
        with pytest.raises(BootRefused):
            recover(audit=audit, store=SqliteOperationalStore(":memory:"))
        assert audit.length == before


class TestWriteAheadRepair:
    def test_a_crash_between_audit_and_projection_is_repaired_at_boot(self, tmp_path: Path) -> None:
        """Law L-2: the audit entry commits first, so the hole is visible and fillable."""
        path, audit, store = _durable(tmp_path)
        flaky: Any = FlakyStore(store)
        payload = {"decision_id": "DEC-77", "verb": "ABSTAIN", "state": "PROPOSED"}

        with pytest.raises(PersistenceError):
            write_with_audit(audit=audit, store=flaky, event_type="decision.recorded", payload=payload)
        assert store.decisions() == ()  # the projection never landed
        assert audit.length >= 1  # but the record did

        reapplied = reproject_missing(audit=audit, store=store)
        assert len(reapplied) == 1
        decisions = store.decisions()
        assert len(decisions) == 1
        assert decisions[0]["decision_id"] == "DEC-77"
        assert reproject_missing(audit=audit, store=store) == ()  # and it does not repeat

    def test_recovery_finishes_an_unprojected_audit_entry(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        audit.record("decision.recorded", {"decision_id": "DEC-88", "verb": "ABSTAIN"})
        report = recover(audit=audit, store=store)
        assert len(report.reprojected) == 1
        assert store.get_decision("DEC-88") is not None


class TestDurableIdempotency:
    def test_gateway_ledger_survives_a_restart(self, tmp_path: Path) -> None:
        """Finding F-7: without a durable ledger, a restart is when a duplicate order becomes possible."""
        path, audit, store = _durable(tmp_path)
        settings = Settings(_env_file=None)
        halt = HaltManager(audit=audit, store=store)
        gateway = ExecutionGateway(settings=settings, halt=halt, audit=audit, store=store)
        intent = _intent()

        first = gateway.submit(intent)
        assert first.status is GatewayStatus.REFUSED  # live trading is disabled by construction
        assert first.idempotent_replay is False
        assert gateway.rehydrated_count == 0
        store.close()

        audit2, store2 = _reopen(path)
        halt2 = HaltManager(
            audit=audit2, store=store2, restored_state=recover(audit=audit2, store=store2).halt_state
        )
        restarted = ExecutionGateway(settings=settings, halt=halt2, audit=audit2, store=store2)
        assert restarted.rehydrated_count == 1

        replay = restarted.submit(intent)
        assert replay.idempotent_replay is True
        assert replay.status is first.status
        assert any("IDEMPOTENCY_CONFLICT" in reason for reason in replay.reasons)


class TestApiSurface:
    def test_status_reports_the_system_of_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # This test is about the durable path, so it says so: CI runs the whole suite with
        # NEXUS_AUDIT_BACKEND=memory, which deliberately makes both stores ephemeral.
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "sqlite")
        path = tmp_path / "nexus.db"
        app = create_app(
            settings=Settings(_env_file=None, database_url=f"sqlite:///{path}"),
        )
        body = TestClient(app).get("/v1/status").json()["persistence"]
        assert body["engine"] == "sqlite"
        assert body["ephemeral"] is False
        assert body["path"] == str(path)
        # Derived from the declared sequence: this asserts the API reports every migration the boot
        # applied, not that the sequence stops at a version that happened to be last when it was written.
        assert [item["version"] for item in body["migrations"]["applied"]] == [
            migration.version for migration in MIGRATIONS
        ]
        assert body["migrations"]["skipped"] == []
        assert body["boot_recovery"]["halt_active"] is False
        assert body["boot_error"] is None
        assert body["counts"]["orders"] == 0

    def test_api_fails_closed_when_the_chain_does_not_verify(self) -> None:
        backend = TamperedStore()
        audit = AuditLog(backend)
        store = SqliteOperationalStore(":memory:", audit=audit)
        audit.record("probe.event", {"a": 1})

        app = create_app(settings=Settings(_env_file=None), audit=audit, store=store)
        client = TestClient(app)

        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert any("AUDIT_CHAIN_INVALID" in item for item in ready.json()["problems"])

        body = client.get("/v1/status").json()
        assert body["halt"]["active"] is True
        assert body["halt"]["scope"] == "ALL_TRADING"  # failed closed into the kill switch
        assert body["persistence"]["boot_error"]["reason"] == "AUDIT_CHAIN_INVALID"
        assert body["persistence"]["boot_recovery"] is None

    def test_ephemeral_audit_backend_keeps_operational_state_ephemeral(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Matching footings, and no silent file.

        With an explicitly ephemeral audit log the operational store is ephemeral too, even when
        ``database_url`` names a file: a durable record of state beside a volatile record of why it
        changed would be worse than either choice alone. Nothing may be written behind the
        operator's back.
        """
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "memory")
        path = tmp_path / "nexus.db"
        app = create_app(settings=Settings(_env_file=None, database_url=f"sqlite:///{path}"))
        body = TestClient(app).get("/v1/status").json()["persistence"]
        assert body["ephemeral"] is True
        assert body["path"] is None
        assert not path.exists()

    def test_readyz_reports_orders_awaiting_reconciliation(self, tmp_path: Path) -> None:
        path, audit, store = _durable(tmp_path)
        store.save_order(
            order_id="ORD-1",
            venue="OKX",
            account_id="A1",
            state=OrderState.SUBMITTING,
            idempotency_key="IDK-1",
        )
        app = create_app(
            settings=Settings(_env_file=None, database_url=f"sqlite:///{path}"),
            audit=audit,
            store=store,
        )
        ready = TestClient(app).get("/readyz")
        assert ready.status_code == 503
        assert any("UNKNOWN pending reconciliation" in item for item in ready.json()["problems"])

    def test_halt_engaged_over_the_api_survives_a_rebuild(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The control endpoint writes through the same durable path as everything else."""
        from nexus.secrets.provider import reset_secret_provider_cache

        monkeypatch.setenv("NEXUS_SECRET_OWNER_API_TOKEN", "test-owner-token")
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "sqlite")  # durability is the subject of this test
        reset_secret_provider_cache()

        path = tmp_path / "nexus.db"
        settings = Settings(_env_file=None, database_url=f"sqlite:///{path}")
        client = TestClient(create_app(settings=settings))
        engaged = client.post(
            "/v1/halt",
            json={"scope": "NEW_ENTRIES", "reason": "api probe"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert engaged.status_code == 200
        assert engaged.json()["engaged"] is True

        # A rebuild is a restart: new audit store, new operational store, same file.
        rebuilt = TestClient(create_app(settings=settings))
        body = rebuilt.get("/v1/status").json()
        assert body["halt"]["active"] is True
        assert body["halt"]["scope"] == "NEW_ENTRIES"
        assert body["halt"]["reason"] == "api probe"
        assert body["persistence"]["boot_recovery"]["halt_active"] is True
