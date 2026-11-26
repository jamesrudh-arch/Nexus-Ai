"""Durable operational state (Stage 6: findings F-2 and F-7, laws L-2, L-4, L-5).

These tests exist because the state they cover used to be volatile: a restart lost decisions,
intents, approvals, orders, fills and the gateway's idempotency ledger. Two properties are asserted
throughout — a Decimal survives a round trip exactly, and a payload carrying secret material is
refused at the store boundary rather than written.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, InMemoryAuditStore, SecretMaterialDetected, SqliteAuditStore
from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionRecord, DecisionState, DecisionVerb
from nexus.execution.intent import ApprovalRecord, TradeIntent
from nexus.execution.orders import OrderState
from nexus.store.operational import PersistenceError, SqliteOperationalStore
from nexus.store.writeahead import write_with_audit

D = Decimal


@pytest.fixture
def audit() -> AuditLog:
    return AuditLog(InMemoryAuditStore())


@pytest.fixture
def store(audit: AuditLog) -> SqliteOperationalStore:
    return SqliteOperationalStore(":memory:", audit=audit)


def _intent(**overrides: Any) -> TradeIntent:
    payload: dict[str, Any] = {
        "intent_id": new_id("INT"),
        "decision_id": "DEC-1",
        "instrument_id": "INS-BTCUSDT-PERP-OKX",
        "venue": "OKX",
        "account_id": "OKX-DEMO-001",
        "side": "LONG",
        "order_type": "LIMIT",
        "quantity": D("0.123456789012"),
        "limit_price": D("99990.5"),
        "stop_price": D("98000.25"),
        "protective_stop": D("98000.25"),
        "take_profit": D("105000"),
        "max_loss_usd": D("250.00"),
        "idempotency_key": new_id("IDK"),
        "environment": "SHADOW",
    }
    payload.update(overrides)
    return TradeIntent(**payload)


class TestRoundTrips:
    def test_decision_survives_a_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "nexus.db"
        record = DecisionRecord(
            state=DecisionState.PROPOSED,
            verb=DecisionVerb.ABSTAIN,
            instrument_id="INS-BTCUSDT-PERP-OKX",
            venue="OKX",
            confidence=0.42,
            rationale="insufficient evidence",
            reason_codes=("EVIDENCE_INSUFFICIENT",),
            evidence_refs=("EV-1", "EV-2"),
        )
        first = SqliteOperationalStore(path)
        first.save_decision(record)
        first.close()

        second = SqliteOperationalStore(path)
        loaded = second.get_decision(record.decision_id)
        assert loaded is not None
        assert loaded["verb"] == "ABSTAIN"
        assert loaded["confidence"] == 0.42
        assert loaded["reason_codes"] == ("EVIDENCE_INSUFFICIENT",)
        assert loaded["evidence_refs"] == ("EV-1", "EV-2")

    def test_intent_preserves_decimal_exactly(self, store: SqliteOperationalStore) -> None:
        """Law L-4: NUMERIC semantics. A quantity that changes on the way through is a different order."""
        intent = _intent()
        store.save_intent(intent)
        loaded = store.get_intent(intent.intent_id)
        assert loaded is not None
        assert loaded["quantity"] == D("0.123456789012")
        assert loaded["limit_price"] == D("99990.5")
        assert loaded["max_loss_usd"] == D("250.00")
        assert loaded["digest"] == intent.digest()
        assert loaded["environment"] == "SHADOW"

    def test_intent_is_found_by_idempotency_key(self, store: SqliteOperationalStore) -> None:
        intent = _intent()
        store.save_intent(intent)
        assert store.intents_by_key(intent.idempotency_key) is not None
        assert store.intents_by_key("IDK-NOPE") is None

    def test_approval_binding_survives(self, store: SqliteOperationalStore) -> None:
        intent = _intent()
        store.save_intent(intent)
        approval = ApprovalRecord(
            approval_id=new_id("APR"),
            intent_id=intent.intent_id,
            intent_digest=intent.digest(),
            approved_by="OWNER",
            approved_at=iso_utc(utc_now()),
            scope={"accounts": ["OKX-DEMO-001"]},
            step_up_verified=True,
        )
        store.save_approval(approval)
        loaded = store.get_approval(approval.approval_id)
        assert loaded is not None
        assert loaded["intent_digest"] == intent.digest()
        assert loaded["scope"] == {"accounts": ["OKX-DEMO-001"]}
        assert loaded["step_up_verified"] is True
        assert approval.binds(intent) is True

    def test_order_state_transitions_are_persisted(self, store: SqliteOperationalStore) -> None:
        store.save_order(
            order_id="ORD-1",
            venue="OKX",
            account_id="OKX-DEMO-001",
            state=OrderState.SUBMITTING,
            idempotency_key="IDK-1",
            intent_id="INT-1",
        )
        assert store.update_order_state("ORD-1", OrderState.UNKNOWN, reason="no ack from venue")
        row = store.get_order("ORD-1")
        assert row is not None
        assert row["state"] == "UNKNOWN"
        assert row["reject_reason"] == "no ack from venue"
        assert [item.order_id for item in store.orders(states=["UNKNOWN"])] == ["ORD-1"]
        assert store.orders(states=["FILLED"]) == ()

    def test_update_of_an_unknown_order_reports_false(self, store: SqliteOperationalStore) -> None:
        assert store.update_order_state("ORD-ABSENT", OrderState.FILLED) is False

    def test_fills_and_limit_changes_keep_decimals(self, store: SqliteOperationalStore) -> None:
        store.save_order(
            order_id="ORD-2",
            venue="OKX",
            account_id="OKX-DEMO-001",
            state=OrderState.FILLED,
            idempotency_key="IDK-2",
            filled_qty=D("0.5"),
            average_price=D("100000.10"),
        )
        store.save_fill(
            {
                "fill_id": "FILL-1",
                "order_id": "ORD-2",
                "venue": "OKX",
                "side": "BUY",
                "quantity": D("0.5"),
                "price": D("100000.10"),
                "fee_quote": D("0.025"),
                "is_maker": True,
                "filled_at": iso_utc(utc_now()),
            }
        )
        fills = store.fills("ORD-2")
        assert len(fills) == 1
        assert fills[0]["price"] == D("100000.10")
        assert fills[0]["is_maker"] is True

        store.save_limit_change(
            {
                "change_id": "RLC-1",
                "limit_name": "max_risk_per_trade_pct",
                "old_value": D("1.0"),
                "new_value": D("0.5"),
                "requested_by": "OWNER",
                "status": "PENDING",
            }
        )
        changes = store.limit_changes()
        assert changes[0]["new_value"] == D("0.5")
        assert changes[0]["cooldown_seconds"] == 3600

    def test_instruments_upsert_rather_than_duplicate(self, store: SqliteOperationalStore) -> None:
        payload = {
            "instrument_id": "INS-BTCUSDT-PERP-OKX",
            "canonical_symbol": "BTC/USDT:USDT",
            "asset_class": "CRYPTO_PERP",
            "base_currency": "BTC",
            "quote_currency": "USDT",
            "settlement_currency": "USDT",
            "active": True,
            "data_status": "DELAYED",
        }
        store.save_instrument(payload)
        store.save_instrument({**payload, "data_status": "LIVE"})
        rows = store.instruments()
        assert len(rows) == 1
        assert rows[0]["data_status"] == "LIVE"
        assert rows[0]["active"] is True


class TestStoreBoundary:
    def test_secret_material_is_refused_before_it_is_written(self, store: SqliteOperationalStore) -> None:
        """Law L-5: the store is a boundary, not a sink."""
        with pytest.raises(SecretMaterialDetected):
            store.save_intent_payload(
                {
                    "intent_id": "INT-BAD",
                    "instrument_id": "INS-X",
                    "venue": "OKX",
                    "account_id": "A1",
                    "side": "LONG",
                    "order_type": "MARKET",
                    "quantity": D("1"),
                    "api_key": "0123456789abcdef0123456789abcdef",
                }
            )
        assert store.get_intent("INT-BAD") is None

    def test_rows_without_identity_are_refused(self, store: SqliteOperationalStore) -> None:
        with pytest.raises(PersistenceError, match="decision_id"):
            store.save_decision_payload({"verb": "ABSTAIN"})
        with pytest.raises(PersistenceError, match="intent_id"):
            store.save_intent_payload({"venue": "OKX"})
        with pytest.raises(PersistenceError, match="order_id"):
            store.save_order(
                order_id="",
                venue="OKX",
                account_id="A1",
                state=OrderState.DRAFT,
                idempotency_key="IDK",
            )

    def test_unknown_halt_action_is_refused(self, store: SqliteOperationalStore) -> None:
        with pytest.raises(PersistenceError, match="unknown halt action"):
            store.save_halt_event(
                action="PAUSE",
                scope="NONE",
                reason="x",
                triggered_by="OWNER",
                at=iso_utc(utc_now()),
            )

    def test_counts_reports_every_table(self, store: SqliteOperationalStore) -> None:
        counts = store.counts()
        for table in ("orders", "halt_event", "dossier", "evidence_ref", "memory_item"):
            assert table in counts


class TestWriteAhead:
    def test_audit_entry_lands_with_the_projection(self, audit: AuditLog, store: Any) -> None:
        """Law L-2: the acknowledgement happens only after both writes are committed."""
        intent = _intent()
        entry = write_with_audit(
            audit=audit,
            store=store,
            event_type="intent.created",
            payload=intent.to_dict(),
            actor="OWNER",
        )
        assert store.get_intent(intent.intent_id) is not None
        assert entry.record_id in store.projected_refs()

    def test_non_projectable_events_are_left_alone(self, audit: AuditLog, store: Any) -> None:
        write_with_audit(audit=audit, store=store, event_type="health.readiness_probe", payload={"at": "now"})
        assert store.projected_refs() == frozenset()
        assert store.counts()["op_projection"] == 0

    def test_halt_and_execution_events_project(self, audit: AuditLog, store: Any) -> None:
        write_with_audit(
            audit=audit,
            store=store,
            event_type="halt.engage",
            payload={
                "action": "ENGAGE",
                "scope": "ALL_TRADING",
                "reason": "venue fault",
                "triggered_by": "OWNER",
                "incident_id": "INC-1",
                "since": iso_utc(utc_now()),
                "active": True,
            },
        )
        events = store.halt_events()
        assert len(events) == 1
        assert events[0].scope.value == "ALL_TRADING"
        assert events[0].incident_id == "INC-1"

        write_with_audit(
            audit=audit,
            store=store,
            event_type="execution.refused",
            payload={
                "status": "REFUSED",
                "intent_id": "INT-9",
                "order_id": None,
                "order_state": "DRAFT",
                "reasons": ["LIVE_TRADING_DISABLED"],
                "idempotent_replay": False,
            },
        )
        result = store.get_execution_result("INT-9")
        assert result is not None
        assert result.reasons == ("LIVE_TRADING_DISABLED",)

    def test_halt_sequence_numbers_are_monotonic(self, store: SqliteOperationalStore) -> None:
        for action in ("ENGAGE", "RELEASE", "ENGAGE"):
            store.save_halt_event(
                action=action,
                scope="NEW_ENTRIES",
                reason="probe",
                triggered_by="OWNER",
                at=iso_utc(utc_now()),
            )
        assert [event.seq for event in store.halt_events()] == [1, 2, 3]


class TestDurableFile:
    def test_operational_state_shares_the_audit_file(self, tmp_path: Path) -> None:
        """R-1: one SQLite file holds governance and operational state — one system of record."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        store = SqliteOperationalStore(path, audit=audit)
        store.save_order(
            order_id="ORD-1",
            venue="OKX",
            account_id="A1",
            state=OrderState.WORKING,
            idempotency_key="IDK-1",
        )
        tables = {
            row[0] for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"audit_log", "orders", "halt_event", "schema_migrations"} <= tables
        assert store.path == str(path)
