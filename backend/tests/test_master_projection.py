"""The instrument master reaches the system of record (L-B, finding F-16).

Stage 7.3 seeded three instruments and four venue mappings, and the count beside it was
``instrument_master = 3`` against ``persistence.counts.instrument = 0`` under both backends. The
projector, the event type and the replay path all existed; nothing emitted the event. These tests pin
the emitter, and the two properties that make it safe to call at every boot: an unchanged master
appends nothing, and a half-finished projection leaves a hole that recovery can see.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from nexus.api.app import create_app
from nexus.audit.log import AuditLog, SqliteAuditStore
from nexus.core.config import Settings
from nexus.domain.instrument import AssetClass, Venue, VenueMapping, VenueStatus
from nexus.instruments.projection import (
    EVENT_TYPE,
    instrument_payload,
    mapping_payload,
    project_master,
)
from nexus.instruments.registry import InstrumentRegistry, build_instrument
from nexus.instruments.seed import seed_master
from nexus.store.operational import OperationalStore, SqliteOperationalStore
from nexus.store.writeahead import PROJECTABLE, project, reproject_missing

AUTH_NOT_APPLICABLE = "AUTH_NOT_APPLICABLE"


def _durable(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    """Audit store first, then the operational store — the ordering migration 0003 requires."""
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


def _seeded() -> InstrumentRegistry:
    registry = InstrumentRegistry()
    seed_master(registry)
    return registry


class TestTheMasterIsProjected:
    def test_the_seeded_instruments_and_mappings_land_in_the_tables(self, tmp_path: Path) -> None:
        """The exact counts F-16 recorded, inverted: 3 instruments and 4 mappings, not 3 and 0."""
        audit, store = _durable(tmp_path)
        registry = _seeded()
        assert store.counts()["instrument"] == 0, "the master starts in the registry, not in the store"

        result = project_master(registry, audit=audit, store=store)

        assert result.projected == ("INS-BTC-USDT", "INS-BTC-USDT-USDT", "INS-EUR-USD")
        assert result.mappings == 4
        assert result.changed is True
        counts = store.counts()
        assert counts["instrument"] == 3
        assert counts["venue_instrument_mapping"] == 4
        store.close()

    def test_the_projected_rows_carry_the_seeded_ranks(self, tmp_path: Path) -> None:
        """Stage 7.3's ruling was that bybit's row stays open *and visible*; a projection that dropped
        the status or the note would make it invisible again."""
        audit, store = _durable(tmp_path)
        project_master(_seeded(), audit=audit, store=store)
        perp = store.venue_mappings(instrument_id="INS-BTC-USDT-USDT")
        assert {(row["venue"], row["status"]) for row in perp} == {
            ("BYBIT", "SUPPORTED"),
            ("OKX", "DATA_AVAILABLE"),
        }
        note = next(row["notes"] for row in perp if row["venue"] == "BYBIT")
        assert note.startswith("GEO-BLOCKED"), "the rank must arrive with its reason, not bare"
        assert "F-2" in note and "D-021" in note, (
            "the owner's ruling at Stage 7 closure was that bybit's row stays open *and visible*; the "
            "finding it is blocked by and the lever that would unblock it are what make it visible"
        )
        venues = {row["venue"]: row["status"] for row in store.venue_mappings()}
        assert venues == {
            "BINANCE": "DATA_AVAILABLE",
            "BYBIT": "SUPPORTED",
            "OKX": "DATA_AVAILABLE",
            "DUKASCOPY": "DATA_AVAILABLE",
        }
        store.close()

    def test_the_event_type_was_already_projectable(self) -> None:
        """L-B is an emitter, not a mechanism: the dispatcher had this branch before anything called it."""
        assert PROJECTABLE[EVENT_TYPE] == "instrument"


class TestIdempotence:
    def test_a_second_call_appends_nothing_to_the_chain(self, tmp_path: Path) -> None:
        """A projection that re-audited an unchanged master would grow the chain every boot without
        describing anything, which is worse than not projecting at all."""
        audit, store = _durable(tmp_path)
        registry = _seeded()
        first = project_master(registry, audit=audit, store=store)
        length = audit.length

        second = project_master(registry, audit=audit, store=store)

        assert second.projected == ()
        assert second.audit_refs == ()
        assert second.mappings == 0
        assert second.changed is False
        assert sorted(second.unchanged) == sorted(first.projected)
        assert audit.length == length, "no audit record for an instrument that did not change"
        assert store.counts()["venue_instrument_mapping"] == 4, "re-projection replaces, never duplicates"
        store.close()

    def test_the_payload_carries_no_timestamp_of_its_own(self) -> None:
        """Pinned because it is what makes the test above possible. A payload stamped at call time has a
        different digest every boot, so the digest comparison would never match and every boot would
        look like a change."""
        instrument = _seeded().require("INS-EUR-USD")
        payload = instrument_payload(instrument)
        assert "created_at" not in payload
        assert "updated_at" not in payload
        assert instrument_payload(instrument) == payload, "the payload is a function of the instrument"

    def test_a_climbed_rank_is_re_projected_and_re_audited(self, tmp_path: Path) -> None:
        """The digest comparison must notice a real change, or the projection goes stale the first time
        an instrument is certified further."""
        audit, store = _durable(tmp_path)
        registry = _seeded()
        project_master(registry, audit=audit, store=store)
        before = audit.length
        assert store.venue_mappings(instrument_id="INS-BTC-USDT-USDT")[0]["status"] == "SUPPORTED"

        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.OKX,
            VenueStatus.CONNECTED,
            evidence="probe: public endpoints reachable",
            auth=AUTH_NOT_APPLICABLE,
            requested_by="TEST-L-B",
        )
        result = project_master(registry, audit=audit, store=store)

        assert result.projected == ("INS-BTC-USDT-USDT",)
        assert result.unchanged == ("INS-BTC-USDT", "INS-EUR-USD")
        assert audit.length == before + 1, "one change, one record"
        statuses = {
            row["venue"]: row["status"] for row in store.venue_mappings(instrument_id="INS-BTC-USDT-USDT")
        }
        assert statuses["OKX"] == "CONNECTED"
        store.close()


class TestThePayloadIsFaithful:
    def test_margin_rate_and_fees_survive_the_projection(self, tmp_path: Path) -> None:
        """The reason this writer does not reuse ``registry._mapping_to_dict``: that serialiser is an API
        read-model and omits both fields. Projecting through it would have written these columns empty
        for every mapping, and nothing would have failed, because both are nullable."""
        audit, store = _durable(tmp_path)
        registry = InstrumentRegistry()
        registry.register(
            build_instrument(
                canonical_symbol="XAU/USD",
                asset_class=AssetClass.METALS,
                base_currency="XAU",
                quote_currency="USD",
                settlement_currency="USD",
                mappings=(
                    VenueMapping(
                        venue=Venue.DUKASCOPY,
                        venue_symbol="XAU/USD",
                        status=VenueStatus.DATA_AVAILABLE,
                        contract_size=Decimal("100"),
                        tick_size=Decimal("0.01"),
                        margin_rate=Decimal("0.05"),
                        fees={"maker": Decimal("0.0001"), "taker": Decimal("0.0002")},
                        notes="100oz per contract",
                    ),
                ),
            ),
            source="TEST",
            requested_by="TEST-L-B",
        )

        project_master(registry, audit=audit, store=store)
        row = store.venue_mappings()[0]

        assert row["margin_rate"] == Decimal("0.05")
        assert row["fees"] == {"maker": "0.0001", "taker": "0.0002"}
        assert row["contract_size"] == Decimal("100")
        assert row["notes"] == "100oz per contract"
        store.close()

    def test_mapping_payload_names_every_field_the_column_set_holds(self) -> None:
        """A field added to ``VenueMapping`` must be added here on purpose. Without this, a new economic
        field would be silently dropped from the projection and the columns would sit empty."""
        import dataclasses

        declared = {field.name for field in dataclasses.fields(VenueMapping)}
        written = set(mapping_payload(VenueMapping(venue=Venue.OKX, venue_symbol="BTC-USDT-SWAP")))
        assert declared - written == set(), f"VenueMapping fields the projection drops: {declared - written}"

    def test_the_seeded_mappings_have_no_margin_rate_or_fees_to_project(self, tmp_path: Path) -> None:
        """Recorded so the empty columns are not mistaken for a dropped field. Stage 7.3's seed specs
        never carried ``margin_rate`` or ``fees`` — the words do not appear in ``instruments/seed.py`` —
        so the four projected rows are NULL and ``{}`` because the evidence did not include them. Filling
        them in would mean inventing numbers with nothing behind them."""
        audit, store = _durable(tmp_path)
        project_master(_seeded(), audit=audit, store=store)
        rows = store.venue_mappings()
        assert len(rows) == 4
        assert all(row["margin_rate"] is None for row in rows)
        assert all(row["fees"] == {} for row in rows)
        store.close()


class TestRecoverability:
    """L-2: the audit entry commits first, the projection second, and the hole between them is visible."""

    def test_the_event_replays_from_the_chain_alone(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        registry = _seeded()
        project_master(registry, audit=audit, store=store)
        records = [record for record in audit.records() if record.event_type == EVENT_TYPE]
        assert len(records) == 3

        # a second store over a fresh database, rebuilt from nothing but the chain
        path2 = tmp_path / "rebuilt.db"
        audit2 = AuditLog(SqliteAuditStore(path2))
        store2 = SqliteOperationalStore(path2, audit=audit2)
        for record in records:
            project(store2, record.event_type, record.payload, audit_ref=record.record_id)
        assert store2.counts()["instrument"] == 3
        assert store2.counts()["venue_instrument_mapping"] == 4
        store.close()
        store2.close()

    def test_a_crash_between_the_instrument_and_its_mappings_leaves_a_hole_recovery_fills(
        self, tmp_path: Path
    ) -> None:
        """Why the projection marks itself complete once, after every write, rather than handing
        ``audit_ref`` to each save. ``op_projection`` is keyed on ``audit_ref`` alone: marking early
        would record the event as done the moment the instrument row landed, and the missing mappings
        would never be noticed."""
        audit, store = _durable(tmp_path)
        registry = _seeded()

        class CrashingStore:
            """Delegates everything, and fails on the first mapping write."""

            def __init__(self, inner: SqliteOperationalStore) -> None:
                self._inner = inner
                self.mapping_calls = 0

            def __getattr__(self, name: str) -> Any:
                return getattr(self._inner, name)

            def save_venue_mapping(self, payload: Any, *, audit_ref: str | None = None) -> None:
                self.mapping_calls += 1
                if self.mapping_calls == 1:
                    raise RuntimeError("simulated crash between the instrument row and its mappings")
                self._inner.save_venue_mapping(payload, audit_ref=audit_ref)

        crashing = CrashingStore(store)
        with pytest.raises(RuntimeError, match="simulated crash"):
            project_master(registry, audit=audit, store=cast(OperationalStore, crashing))

        # The crash propagates out of the loop, so only the first instrument was ever audited. Its row
        # landed, its mappings did not, and the projection was not booked as complete.
        assert store.counts()["instrument"] == 1
        assert store.counts()["venue_instrument_mapping"] == 0
        pending = [
            record.record_id
            for record in audit.records()
            if record.event_type == EVENT_TYPE and record.record_id not in store.projected_refs()
        ]
        assert len(pending) == 1, "the hole must be visible to recovery"

        reapplied = reproject_missing(audit=audit, store=store)
        assert set(pending) <= set(reapplied)
        assert store.projected_refs() >= frozenset(pending), "recovery books what it finished"
        assert store.counts()["venue_instrument_mapping"] == 1, (
            "the interrupted instrument's mapping is restored from the chain alone"
        )

        # and the emitter finishes the master on the next call, because the other two instruments were
        # never audited at all — recovery can only replay what the chain actually holds
        project_master(registry, audit=audit, store=store)
        assert store.counts()["instrument"] == 3
        assert store.counts()["venue_instrument_mapping"] == 4
        assert audit.verify() == []
        store.close()

    def test_the_audit_chain_stays_intact(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        project_master(_seeded(), audit=audit, store=store)
        assert audit.verify() == []
        store.close()

    def test_no_projection_is_booked_without_an_audit_ref(self, tmp_path: Path) -> None:
        """The store stays usable without the chain, but then nothing is claimed as projected — the same
        rule every other writer follows, and the reason ``_mark`` is a no-op without a ref."""
        audit, store = _durable(tmp_path)
        instrument = _seeded().require("INS-EUR-USD")
        project(store, EVENT_TYPE, instrument_payload(instrument), audit_ref=None)
        assert store.counts()["instrument"] == 1
        assert store.projected_refs() == frozenset()
        store.close()


class TestBootProjectsTheSeededMaster:
    """F-16 through the API: the pair of numbers the finding was found by, now equal."""

    def test_a_seeded_boot_projects_the_master_into_the_system_of_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "sqlite")
        path = tmp_path / "nexus.db"
        app = create_app(settings=Settings(_env_file=None, database_url=f"sqlite:///{path}"))
        with TestClient(app) as client:
            body = client.get("/v1/status").json()
        assert body["instrument_master"] == {"count": 3, "active": 0, "projected": 3}
        assert body["persistence"]["counts"]["instrument"] == 3
        assert body["persistence"]["counts"]["venue_instrument_mapping"] == 4
        projection = app.state.master_projection
        assert projection is not None
        assert projection.projected == ("INS-BTC-USDT", "INS-BTC-USDT-USDT", "INS-EUR-USD")
        assert projection.mappings == 4

    def test_a_restart_projects_nothing_and_grows_the_chain_by_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Idempotence across process restarts, not just across two calls in one process: a boot that
        re-audited an unchanged master would add three records to the chain every restart.

        Counted by event type rather than by chain length, because a boot legitimately appends
        ``api.app_created`` and ``boot.recovery`` of its own. Comparing totals would fail for a reason
        that has nothing to do with this projection — and would tempt somebody to "fix" it.
        """
        monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "sqlite")
        path = tmp_path / "nexus.db"
        settings = Settings(_env_file=None, database_url=f"sqlite:///{path}")

        def event_counts() -> dict[str, int]:
            log = AuditLog(SqliteAuditStore(path))
            counts: dict[str, int] = {}
            for record in log.records():
                counts[record.event_type] = counts.get(record.event_type, 0) + 1
            log.store.close()
            return counts

        first = create_app(settings=settings)
        with TestClient(first) as client:
            assert client.get("/v1/status").json()["instrument_master"]["projected"] == 3
        before = event_counts()

        second = create_app(settings=settings)
        with TestClient(second) as client:
            body = client.get("/v1/status").json()
            assert client.get("/v1/audit/verify").json()["intact"] is True
        after = event_counts()

        projection = second.state.master_projection
        assert projection is not None
        assert projection.projected == ()
        assert sorted(projection.unchanged) == ["INS-BTC-USDT", "INS-BTC-USDT-USDT", "INS-EUR-USD"]
        assert before["instrument.registered"] == after["instrument.registered"] == 3
        assert body["instrument_master"] == {"count": 3, "active": 0, "projected": 3}
        assert body["persistence"]["counts"]["venue_instrument_mapping"] == 4, (
            "re-projection replaces rows; it never duplicates them"
        )
        # the boot events that *do* grow, named so the difference is not mistaken for a leak
        assert after["api.app_created"] == before["api.app_created"] + 1
        assert after["boot.recovery"] == before["boot.recovery"] + 1


def test_the_projection_is_a_function_of_the_registry_not_of_the_clock() -> None:
    """Two calls at different wall-clock times produce the same payload."""
    instrument = _seeded().require("INS-BTC-USDT-USDT")
    first = instrument_payload(instrument)
    datetime.now(UTC)
    assert instrument_payload(instrument) == first
