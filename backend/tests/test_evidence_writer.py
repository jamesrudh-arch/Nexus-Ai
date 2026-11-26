"""The first ``evidence_ref`` writer (L-C, Stage 8.2) and the two timestamps it keeps apart.

Finding F-14 is that ``observed_at`` holds venue time in all four adapters and no receipt time is
recorded anywhere, so latency is not measurable. The owner's ruling for this batch was the cheap half —
write both columns separately and leave F-14 open — so what is asserted here is not that latency is now
measurable. It is that the columns cannot be conflated by accident, that a missing venue timestamp says
so instead of being papered over, and that the number the row does carry is labelled with what it
actually conflates.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.chain import sha256_hex
from nexus.audit.log import AuditLog, SqliteAuditStore
from nexus.core.errors import RejectReason
from nexus.data.freshness import DataStatus, MarketSnapshot
from nexus.intelligence.evidence import (
    EVENT_TYPE,
    ObservedAtSource,
    record_evidence,
    record_snapshot,
    snapshot_payload,
)
from nexus.store.operational import PersistenceError, SqliteOperationalStore
from nexus.store.serialise import dumps_canonical
from nexus.store.writeahead import PROJECTABLE, reproject_missing

OBSERVED = datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC)
RETRIEVED = OBSERVED + timedelta(seconds=1, milliseconds=170)


def _durable(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


def _snapshot(**overrides: Any) -> MarketSnapshot:
    base: dict[str, Any] = {
        "instrument_id": "INS-BTC-USDT-USDT",
        "venue": "OKX",
        "bid": Decimal("60736.2"),
        "ask": Decimal("60736.3"),
        "observed_at": OBSERVED,
        "source": "okx.ticker",
    }
    base.update(overrides)
    return MarketSnapshot(**base)


class TestBothTimestampsAreWritten:
    def test_observed_and_retrieved_land_in_their_own_columns(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        record_snapshot(
            audit=audit,
            store=store,
            snapshot=_snapshot(),
            retrieved_at=RETRIEVED,
            data_status=DataStatus.LIVE,
            locator="https://www.okx.com/api/v5/market/ticker",
        )
        row = store.evidence_refs()[0]
        assert row["observed_at"] == "2026-11-26T12:00:00.000Z"
        assert row["retrieved_at"] == "2026-11-26T12:00:01.170Z"
        assert row["observed_at"] != row["retrieved_at"], "the two are the point of the table"
        assert row["data_status"] == "LIVE"
        assert row["source"] == "okx.ticker"
        assert row["locator"] == "https://www.okx.com/api/v5/market/ticker"
        store.close()

    def test_retrieved_at_is_required_and_has_no_default(self) -> None:
        """Pinned structurally. A default of ``observed_at`` would manufacture a zero latency and a
        default of "now" would record write time as receipt time; both look like measurements."""
        parameters = inspect.signature(record_evidence).parameters
        assert parameters["retrieved_at"].default is inspect.Parameter.empty
        assert parameters["observed_at"].default is inspect.Parameter.empty
        assert parameters["retrieved_at"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_the_apparent_interval_is_recorded_and_labelled(self, tmp_path: Path) -> None:
        """1.170s is ``retrieved_at - observed_at``. It is not latency: it also contains the offset
        between the venue's clock and ours. The row carries the flag that says so."""
        audit, store = _durable(tmp_path)
        receipt = record_snapshot(audit=audit, store=store, snapshot=_snapshot(), retrieved_at=RETRIEVED)
        assert receipt.apparent_latency_seconds == pytest.approx(1.170)
        row = store.evidence_refs()[0]
        assert row["payload"]["apparent_latency_seconds"] == pytest.approx(1.170)
        assert row["payload"]["observed_at_source"] == "VENUE"
        store.close()

    def test_a_venue_clock_ahead_of_ours_is_recorded_not_refused(self, tmp_path: Path) -> None:
        """Run 27 measured 1.089s of venue time against 0.298s of wall clock, so venue clocks run both
        ways. A negative interval is evidence about the clock, not an error to reject."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit,
            store=store,
            source="okx.book",
            observed_at=RETRIEVED + timedelta(seconds=2),
            retrieved_at=RETRIEVED,
            payload={"bids": [["60736.2", "1"]]},
        )
        assert receipt.apparent_latency_seconds == pytest.approx(-2.0)
        assert store.evidence_refs()[0]["payload"]["apparent_latency_seconds"] == pytest.approx(-2.0)
        store.close()


class TestAMissingVenueTimestampIsNeverPaperedOver:
    def test_a_snapshot_with_no_observed_at_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="carries no observed_at"):
            record_snapshot(
                audit=audit,
                store=store,
                retrieved_at=RETRIEVED,
                snapshot=_snapshot(observed_at=None),
            )
        assert store.counts()["evidence_ref"] == 0, "nothing is written on a refusal"
        store.close()

    def test_the_fallback_may_be_declared_and_is_then_recorded_as_such(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = record_snapshot(
            audit=audit,
            store=store,
            retrieved_at=RETRIEVED,
            snapshot=_snapshot(observed_at=None),
            observed_at_source=ObservedAtSource.LOCAL_FALLBACK,
        )
        assert receipt.observed_at_source is ObservedAtSource.LOCAL_FALLBACK
        assert receipt.apparent_latency_seconds == 0.0
        row = store.evidence_refs()[0]
        assert row["observed_at"] == row["retrieved_at"]
        assert row["payload"]["observed_at_source"] == "LOCAL_FALLBACK", (
            "a row whose two timestamps are equal by construction must say so, or a reader will take "
            "the zero for a measurement"
        )
        store.close()

    def test_a_fallback_claim_contradicted_by_the_timestamps_is_refused(self, tmp_path: Path) -> None:
        """The flag has to mean something. Claiming the local clock stood in while passing two different
        timestamps would let a real venue time hide behind a disclaimer."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="LOCAL_FALLBACK"):
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                observed_at_source=ObservedAtSource.LOCAL_FALLBACK,
            )
        store.close()

    def test_a_naive_datetime_is_refused_by_name(self, tmp_path: Path) -> None:
        """Not a bare ``TypeError`` from the subtraction: an unclassified crash at a boundary names
        nothing, which is what finding F-4 was about."""
        audit, store = _durable(tmp_path)
        naive = datetime(2026, 11, 26, 12, 0, 0)
        with pytest.raises(ValueError, match="observed_at must be an aware UTC datetime"):
            record_evidence(audit=audit, store=store, source="okx", observed_at=naive, retrieved_at=RETRIEVED)
        with pytest.raises(ValueError, match="retrieved_at must be an aware UTC datetime"):
            record_evidence(audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=naive)
        store.close()


class TestTheStoreRefusesAnUnusableRow:
    @pytest.mark.parametrize("missing", ["observed_at", "retrieved_at"])
    def test_an_empty_timestamp_is_refused(self, tmp_path: Path, missing: str) -> None:
        """``NOT NULL`` still accepts an empty string, and an evidence row that cannot say when it was
        observed cannot support a decision anyone can audit."""
        audit, store = _durable(tmp_path)
        payload = {
            "evidence_id": "EV-1",
            "source": "okx",
            "observed_at": "2026-11-26T12:00:00.000Z",
            "retrieved_at": "2026-11-26T12:00:01.000Z",
        }
        payload[missing] = ""
        with pytest.raises(PersistenceError, match="observed_at"):
            store.save_evidence_ref(payload)
        store.close()

    def test_an_evidence_row_needs_an_id_and_a_source(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        stamp = "2026-11-26T12:00:00.000Z"
        with pytest.raises(PersistenceError, match="evidence_id"):
            store.save_evidence_ref({"source": "okx", "observed_at": stamp, "retrieved_at": stamp})
        with pytest.raises(PersistenceError, match="source"):
            store.save_evidence_ref({"evidence_id": "EV-1", "observed_at": stamp, "retrieved_at": stamp})
        store.close()

    def test_secret_material_in_the_payload_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(Exception) as excinfo:
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                payload={"api_key": "AKIA" + "A" * 16},
            )
        assert excinfo.value.__class__.__name__ == "SecretMaterialDetected"
        assert store.counts()["evidence_ref"] == 0
        store.close()


class TestVocabularyAndDefaults:
    def test_data_status_outside_the_declared_vocabulary_is_refused(self, tmp_path: Path) -> None:
        """``DataStatus`` (A-06) is the vocabulary; the writer does not get to extend it silently."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="data_status must be one of"):
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                data_status="FRESH",
            )
        store.close()

    def test_the_default_data_status_is_the_fail_closed_one(self, tmp_path: Path) -> None:
        """``UNAVAILABLE`` is the schema default and the fail-closed value: a writer that assumed LIVE
        would be asserting a freshness it has not checked."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        assert receipt.data_status == DataStatus.UNAVAILABLE.value
        assert store.evidence_refs()[0]["data_status"] == "UNAVAILABLE"
        store.close()

    def test_an_empty_source_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="needs a source"):
            record_evidence(audit=audit, store=store, source="", observed_at=OBSERVED, retrieved_at=RETRIEVED)
        store.close()

    def test_kind_is_passed_through_because_no_vocabulary_is_declared(self, tmp_path: Path) -> None:
        """The repository declares no set of evidence kinds — the schema says only ``DEFAULT 'DATA'`` —
        so the writer invents none. Pinned so that a future enum here is a decision, not a drift."""
        audit, store = _durable(tmp_path)
        record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            kind="RESEARCH",
        )
        assert store.evidence_refs()[0]["kind"] == "RESEARCH"
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        assert receipt.kind == "DATA"
        store.close()


class TestIntegrityAndProvenance:
    def test_the_checksum_is_over_exactly_what_was_stored(self, tmp_path: Path) -> None:
        """An integrity checksum over the recorded row, computed by the writer so it cannot disagree
        with the payload. Not an authenticity signature over the venue's bytes — nothing here can
        attest to those yet."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            payload={"bid": "60736.2"},
        )
        row = store.evidence_refs()[0]
        assert row["checksum"] == receipt.checksum
        assert row["checksum"] == sha256_hex(dumps_canonical(row["payload"]))
        store.close()

    def test_a_caller_cannot_overwrite_the_provenance_fields(self, tmp_path: Path) -> None:
        """The qualifications are written last on purpose: a payload that could talk a row out of its own
        provenance would make the flag decorative."""
        audit, store = _durable(tmp_path)
        record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            payload={"apparent_latency_seconds": 999.0, "observed_at_source": "SOMEBODY_ELSE"},
        )
        body = store.evidence_refs()[0]["payload"]
        assert body["apparent_latency_seconds"] == pytest.approx(1.170)
        assert body["observed_at_source"] == "VENUE"
        store.close()

    def test_the_snapshot_payload_keeps_prices_exact_and_both_time_fields(self) -> None:
        payload = snapshot_payload(_snapshot(venue_timestamp=OBSERVED - timedelta(seconds=3)))
        assert payload["bid"] == "60736.2"
        assert payload["mid"] == "60736.25", "the mid is derived, not rounded through a float"
        assert payload["spread"] == "0.1"
        assert payload["venue_timestamp"] == "2026-11-26T11:59:57.000Z"
        assert "observed_at" not in payload, (
            "observed_at is the writer's column, not a payload field: duplicating it inside the payload "
            "would give a reader two copies of the observation time that could disagree"
        )

    def test_evidence_can_be_recorded_before_any_dossier_exists(self, tmp_path: Path) -> None:
        """``dossier_id`` is nullable in both schemas, so the first writer does not depend on the one
        Stage 8.3 has not built yet."""
        audit, store = _durable(tmp_path)
        assert store.counts()["dossier"] == 0
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        assert receipt.dossier_id is None
        assert store.evidence_refs()[0]["dossier_id"] is None
        store.close()


class TestAuditFirst:
    def test_the_event_is_projectable(self) -> None:
        assert PROJECTABLE[EVENT_TYPE] == "evidence_ref"

    def test_the_write_is_audited_and_the_row_beside_it(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        records = [record for record in audit.records() if record.event_type == EVENT_TYPE]
        assert len(records) == 1
        assert records[0].record_id == receipt.audit_ref
        assert receipt.audit_ref in store.projected_refs()
        assert audit.verify() == []
        store.close()

    def test_a_missing_projection_is_refilled_from_the_chain(self, tmp_path: Path) -> None:
        """L-2's recovery property, on the new event type: delete the row, leave the chain, and boot
        recovery restores it — the chain is the record and the table is a projection of it."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            payload={"bid": "60736.2"},
        )
        assert store.counts()["evidence_ref"] == 1

        # a fresh store over the same file, with the projection bookkeeping cleared, as a half-finished
        # boot would leave it
        path = tmp_path / "nexus.db"
        audit2 = AuditLog(SqliteAuditStore(path))
        store2 = SqliteOperationalStore(path, audit=audit2)
        store2._conn.execute("DELETE FROM evidence_ref")
        store2._conn.execute("DELETE FROM op_projection WHERE audit_ref = ?", (receipt.audit_ref,))
        store2._conn.commit()
        assert store2.counts()["evidence_ref"] == 0

        reapplied = reproject_missing(audit=audit2, store=store2)
        assert receipt.audit_ref in reapplied
        row = store2.evidence_refs()[0]
        assert row["evidence_id"] == receipt.evidence_id
        assert row["observed_at"] == "2026-11-26T12:00:00.000Z"
        assert row["retrieved_at"] == "2026-11-26T12:00:01.170Z"
        assert row["payload"]["bid"] == "60736.2"
        store.close()
        store2.close()

    def test_the_row_is_not_an_edit_of_a_previous_one(self, tmp_path: Path) -> None:
        """``INSERT OR REPLACE`` keyed on ``evidence_id``: re-recording the same evidence replaces the
        projection, while the chain keeps both entries. The store is a projection, never the record."""
        audit, store = _durable(tmp_path)
        first = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            evidence_id="EV-FIXED",
            data_status=DataStatus.LIVE,
        )
        second = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            evidence_id="EV-FIXED",
            data_status=DataStatus.STALE,
        )
        assert first.evidence_id == second.evidence_id == "EV-FIXED"
        assert first.audit_ref != second.audit_ref, "two writes, two chain entries"
        rows = store.evidence_refs()
        assert len(rows) == 1
        assert rows[0]["data_status"] == "STALE"
        assert audit.verify() == []
        store.close()


class TestReadsAreOrdered:
    def test_the_most_recent_retrieval_comes_first(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        for offset in (0, 30, 10):
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED + timedelta(seconds=offset),
                retrieved_at=RETRIEVED + timedelta(seconds=offset),
            )
        stamps = [row["retrieved_at"] for row in store.evidence_refs()]
        assert stamps == sorted(stamps, reverse=True)
        assert len(store.evidence_refs(limit=2)) == 2
        store.close()

    def test_a_dossier_filter_returns_only_its_own_evidence(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            dossier_id="DOS-1",
        )
        record_evidence(
            audit=audit, store=store, source="binance", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        assert len(store.evidence_refs(dossier_id="DOS-1")) == 1
        assert len(store.evidence_refs()) == 2
        store.close()


def test_the_reason_vocabulary_was_not_extended() -> None:
    """The writer's refusals raise ``ValueError``, following ``core.time.iso_utc``: they are programmer
    errors at an internal boundary, not operational conditions, so no ``RejectReason`` was spent on
    them. Pinned because a reason code is vocabulary the audit log and the UI both consume."""
    assert not any(
        "EVIDENCE" in member.name and member.name != "EVIDENCE_INSUFFICIENT" for member in RejectReason
    )
    assert RejectReason.EVIDENCE_INSUFFICIENT.value == "EVIDENCE_INSUFFICIENT"
