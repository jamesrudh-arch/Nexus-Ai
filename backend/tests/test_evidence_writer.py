"""The first ``evidence_ref`` writer (L-C, Stage 8.2) and the two timestamps it keeps apart.

Finding F-14 was that ``observed_at`` held venue time in all four adapters and no receipt time was
recorded anywhere, so latency was not measurable. The owner's ruling for this batch was the cheap half —
write both columns separately and leave F-14 open — so what is asserted here is not that latency is now
measurable. It is that the columns cannot be conflated by accident, that a missing venue timestamp says
so instead of being papered over, and that the number the row does carry is labelled with what it
actually conflates.

*Stage 8.4 later closed F-14 at the adapters, and this file's assertions are unchanged by it: they were
about the two columns of ``evidence_ref``, which 8.4 did not touch (D-052 scoped it to the adapters, with
no new columns and no writer wiring). ``retrieved_at`` is still supplied by the caller; what changed
upstream is that a receipt time worth supplying now exists.*
"""

from __future__ import annotations

import inspect
import sqlite3
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
    CHECKSUMMED_FIELDS,
    EVENT_TYPE,
    ObservedAtSource,
    evidence_checksum,
    record_evidence,
    record_snapshot,
    snapshot_payload,
    verify_evidence_checksum,
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


def _pragma(tmp_path: Path, what: str) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(tmp_path / "nexus.db")
    try:
        return list(conn.execute(f"PRAGMA {what}"))
    finally:
        conn.close()


def _rowid(tmp_path: Path, evidence_id: str) -> int:
    """The row's rowid, so a tampered primary key cannot orphan the write that restores it."""
    conn = sqlite3.connect(tmp_path / "nexus.db")
    try:
        rows = list(conn.execute("SELECT rowid FROM evidence_ref WHERE evidence_id = ?", (evidence_id,)))
    finally:
        conn.close()
    assert len(rows) == 1, rows
    return int(rows[0][0])


def _update(tmp_path: Path, column: str, value: Any, rowid: int) -> None:
    """Write past every writer, which is the only way a stored row gets altered."""
    conn = sqlite3.connect(tmp_path / "nexus.db")
    try:
        # The column name comes from CHECKSUMMED_FIELDS or a literal in the test, never from a caller;
        # the value is still bound.
        sql = f"UPDATE evidence_ref SET {column} = ? WHERE rowid = ?"  # noqa: S608
        conn.execute(sql, (value, rowid))
        conn.commit()
    finally:
        conn.close()


def _okx(audit: AuditLog, store: SqliteOperationalStore, **extra: Any) -> Any:
    """One OKX evidence row at the module's pinned clocks, so a test can change one thing at a time."""
    return record_evidence(
        audit=audit,
        store=store,
        source="okx",
        observed_at=OBSERVED,
        retrieved_at=RETRIEVED,
        **extra,
    )


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


class TestTheChecksumCoversTheRow:
    """F-21 — found by Stage 8.3's route probe, fixed here.

    Stage 8.2 hashed ``payload`` alone and documented the result as "an integrity checksum over the
    recorded row". The test that pinned it asserted the payload-only behaviour while its own name and
    docstring said row, so the defect was enshrined rather than caught. Two evidence rows recorded with
    different ``source``, ``observed_at``, ``retrieved_at`` and ``locator`` values but no caller payload
    produced the *same* checksum, because the only material hashed was the two provenance keys the writer
    adds. Eleven of the row's stored fields could change undetected — ``observed_at`` among them, the
    field F-14 is about.

    What is asserted now: the checksum is recomputable from the row, it differs when any covered field
    differs, the covered set is derived from the live table so a new column cannot join the row
    uncovered, and ``audit_ref`` is excluded on purpose because the chain's own hash linkage covers that
    link and because the ref does not exist yet when the writer hashes (L-2 writes the audit entry first).
    """

    def test_the_checksum_is_recomputable_from_the_stored_row(self, tmp_path: Path) -> None:
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
        assert evidence_checksum(row) == row["checksum"], "a reader can recompute it from the row alone"
        assert verify_evidence_checksum(row)
        store.close()

    def test_two_rows_differing_only_in_their_columns_do_not_share_a_checksum(self, tmp_path: Path) -> None:
        """The exact case the probe hit: same payload, different everything else."""
        audit, store = _durable(tmp_path)
        first = record_evidence(
            audit=audit,
            store=store,
            source="okx.books",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            locator="https://www.okx.com/api/v5/market/books",
        )
        second = record_evidence(
            audit=audit,
            store=store,
            source="okx.ticker",
            observed_at=OBSERVED + timedelta(seconds=2),
            retrieved_at=RETRIEVED + timedelta(seconds=2),
            locator="https://www.okx.com/api/v5/market/ticker",
        )
        rows = {row["evidence_id"]: row for row in store.evidence_refs()}
        assert rows[first.evidence_id]["payload"] == rows[second.evidence_id]["payload"]
        assert first.checksum != second.checksum, "F-21: equal payloads are not equal rows"
        # What Stage 8.2 hashed would have been identical for both, which is the defect stated plainly.
        assert sha256_hex(dumps_canonical(rows[first.evidence_id]["payload"])) == sha256_hex(
            dumps_canonical(rows[second.evidence_id]["payload"])
        )
        store.close()

    @pytest.mark.parametrize("field", sorted(CHECKSUMMED_FIELDS))
    def test_altering_any_covered_field_is_detected(self, tmp_path: Path, field: str) -> None:
        """Tampering is written straight into SQLite, past every writer, which is the only way it happens."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            payload={"bid": "60736.2"},
        )
        original = store.evidence_refs()[0]
        rowid = _rowid(tmp_path, receipt.evidence_id)
        tampered = {"payload": '{"bid": "1.0"}', "kind": "RUMOUR", "dossier_id": "CASE-FORGED"}.get(
            field, "TAMPERED"
        )
        _update(tmp_path, field, tampered, rowid)
        assert not verify_evidence_checksum(store.evidence_refs()[0]), field
        # The payload is stored as canonical TEXT and read back as a dict, so restoring it means
        # re-serialising it — writing the dict back would store a Python repr and never verify again.
        restored = dumps_canonical(original[field]) if field == "payload" else original[field]
        _update(tmp_path, field, restored, rowid)
        assert verify_evidence_checksum(store.evidence_refs()[0]), f"{field} restored"
        store.close()

    def test_the_covered_set_is_derived_from_the_live_table(self, tmp_path: Path) -> None:
        """So a column added to ``evidence_ref`` fails here until somebody decides whether to cover it."""
        audit, store = _durable(tmp_path)
        columns = {row[1] for row in _pragma(tmp_path, "table_info(evidence_ref)")}
        assert columns - set(CHECKSUMMED_FIELDS) == {"checksum", "audit_ref"}
        assert set(CHECKSUMMED_FIELDS) <= columns, "no covered field that the table does not have"
        store.close()

    def test_audit_ref_is_excluded_and_the_chain_covers_that_link_instead(self, tmp_path: Path) -> None:
        """Deliberate, and pinned so it reads as a decision rather than an oversight.

        The writer hashes before the audit entry exists (L-2), so ``audit_ref`` cannot be covered; and
        the audit chain is hash-linked end to end, so re-pointing a row at a different record is a change
        the chain's own verification can see. A row's ``audit_ref`` therefore does not affect this value.
        """
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        row = store.evidence_refs()[0]
        assert row["audit_ref"] == receipt.audit_ref
        _update(tmp_path, "audit_ref", "AUD-FORGED", _rowid(tmp_path, receipt.evidence_id))
        assert verify_evidence_checksum(store.evidence_refs()[0])
        breaks = audit.verify()
        assert not breaks, "the chain itself is still intact; only the row's pointer moved"
        store.close()

    def test_a_reader_can_add_keys_but_cannot_change_the_payload(self, tmp_path: Path) -> None:
        """The route lifts provenance keys out beside the row; that must not look like tampering."""
        audit, store = _durable(tmp_path)
        record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            payload={"bid": "60736.2"},
        )
        row = store.evidence_refs()[0]
        annotated = dict(row)
        annotated["served_by"] = "/v1/intelligence/dossiers"
        assert verify_evidence_checksum(annotated), "keys outside the covered set are ignored"
        mutated = dict(row)
        mutated["payload"] = {**row["payload"], "bid": "1.0"}
        assert not verify_evidence_checksum(mutated), "a covered field changed by value is tampering"
        store.close()

    @pytest.mark.parametrize("stored", [None, ""])
    def test_a_missing_checksum_does_not_verify(self, tmp_path: Path, stored: str | None) -> None:
        """``checksum`` is nullable, so absence has to fail closed: no evidence of tampering is not
        evidence of integrity."""
        audit, store = _durable(tmp_path)
        receipt = record_evidence(
            audit=audit, store=store, source="okx", observed_at=OBSERVED, retrieved_at=RETRIEVED
        )
        _update(tmp_path, "checksum", stored, _rowid(tmp_path, receipt.evidence_id))
        assert not verify_evidence_checksum(store.evidence_refs()[0])
        store.close()


class TestIntegrityAndProvenance:
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


class TestAContradictionIsRecordedAndNotResolved:
    """``evidence_ref.contradicts``, added by migration ``0005_memory_beliefs`` (F-18's fourth gap).

    ``docs/10`` §3.1 asks the dossier view for *"contradictions highlighted and linked"* and ``docs/03``
    J-04 step 4 for *"corroborating/contradictory sources"*; before this column nothing could record that
    two sources disagree, so nothing could be highlighted. What is asserted here is the link, and — just as
    hard — that the link is all it is: a claim by whoever wrote the row, pointing one way, settling nothing.
    """

    def test_a_recorded_disagreement_is_stored_and_reads_back(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        first = _okx(audit, store)
        second = record_evidence(
            audit=audit,
            store=store,
            source="bybit",
            observed_at=OBSERVED + timedelta(seconds=1),
            retrieved_at=RETRIEVED + timedelta(seconds=1),
            contradicts=first.evidence_id,
        )
        assert second.contradicts == first.evidence_id
        row = store.get_evidence_ref(second.evidence_id)
        assert row is not None
        assert row["contradicts"] == first.evidence_id
        assert store.counts()["evidence_ref"] == 2
        store.close()

    def test_no_contradiction_is_stored_as_null_and_not_as_a_claim(self, tmp_path: Path) -> None:
        """``None`` means no disagreement was claimed, which is not the same as claiming that none exists —
        nothing in this system can establish that, and the column does not pretend to."""
        audit, store = _durable(tmp_path)
        receipt = _okx(audit, store)
        assert receipt.contradicts is None
        row = store.get_evidence_ref(receipt.evidence_id)
        assert row is not None
        assert row["contradicts"] is None
        store.close()

    def test_a_row_that_does_not_exist_cannot_be_contradicted(self, tmp_path: Path) -> None:
        """``PRAGMA foreign_keys`` is off, so SQLite would store the dangling pointer without comment and
        the dossier route would serve a link whose other side is absent."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                contradicts="EV-NOPE",
            )
        message = str(excinfo.value)
        assert "EV-NOPE" in message
        assert "foreign_keys" in message, "the refusal says why the database will not catch this one"
        assert "0005_memory_beliefs" in message, "and which migration declared the clause"
        assert store.counts()["evidence_ref"] == 0, "nothing is written when the link cannot be made"
        store.close()

    def test_a_row_cannot_contradict_itself(self, tmp_path: Path) -> None:
        """A contradiction is a disagreement between two observations, and a pointer at the row's own id
        records neither. Only reachable with a caller-supplied id, since a generated one is not known
        before the call — which is itself the reason the check runs after the id is resolved."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                evidence_id="EV-SELF",
                contradicts="EV-SELF",
            )
        assert "cannot contradict itself" in str(excinfo.value)
        assert store.counts()["evidence_ref"] == 0
        store.close()

    @pytest.mark.parametrize("value", ["", "   "])
    def test_a_contradiction_nobody_can_identify_is_not_a_link(self, tmp_path: Path, value: str) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="must name an evidence row or be None"):
            record_evidence(
                audit=audit,
                store=store,
                source="okx",
                observed_at=OBSERVED,
                retrieved_at=RETRIEVED,
                contradicts=value,
            )
        store.close()

    def test_the_link_points_one_way_and_nothing_back_links_it(self, tmp_path: Path) -> None:
        """``evidence_ref`` has no reverse column, so the contradicted row never learns about the row that
        contradicts it. The dossier route derives the reverse direction by scanning one dossier's rows and
        says so; a reader going straight to the database has to scan too."""
        audit, store = _durable(tmp_path)
        first = _okx(audit, store)
        record_evidence(
            audit=audit,
            store=store,
            source="bybit",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            contradicts=first.evidence_id,
        )
        untouched = store.get_evidence_ref(first.evidence_id)
        assert untouched is not None
        assert untouched["contradicts"] is None, "the earlier row was not updated by the later one"
        assert not {
            row[1] for row in _pragma(tmp_path, "table_info(evidence_ref)") if "contradict" in str(row[1])
        } - {"contradicts"}, "one column, one direction"
        store.close()

    def test_recording_a_contradiction_resolves_nothing(self, tmp_path: Path) -> None:
        """Both rows stay readable, neither is downgraded, and no winner is computed.

        ``docs/12`` §1.3's law (A-02+A-08) is that no gate can be satisfied by a confidence value and
        ``docs/10`` §3.2 that confidence never overrides a failed stage, so a contradiction is an input to a
        review — which is a person — and this batch builds no reviewer. What is asserted is that the earlier
        row is byte-identical afterwards, including the checksum that F-21 widened: a writer that quietly
        marked the contradicted row STALE would be deciding something nobody asked it to.
        """
        audit, store = _durable(tmp_path)
        first = record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            data_status=DataStatus.LIVE,
            payload={"bid": "60736.2"},
        )
        before = store.get_evidence_ref(first.evidence_id)
        assert before is not None
        record_evidence(
            audit=audit,
            store=store,
            source="bybit",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            data_status=DataStatus.LIVE,
            payload={"bid": "1.0"},
            contradicts=first.evidence_id,
        )
        after = store.get_evidence_ref(first.evidence_id)
        assert after == before, "the contradicted row did not change in any column"
        assert after["data_status"] == "LIVE"
        assert verify_evidence_checksum(after)
        assert store.counts()["evidence_ref"] == 2, "neither row was removed"
        store.close()

    def test_a_mutual_disagreement_takes_two_calls_and_neither_row_is_edited(self, tmp_path: Path) -> None:
        """The ordering rule the refusal creates, stated as behaviour: the contradicted row must exist
        first, so the second row carries the link and the first does not. Making it mutual would mean
        re-recording the first id, which ``INSERT OR REPLACE`` permits and which is a restatement of an
        observation — 8.2's own test pins that the chain keeps both entries when it happens."""
        audit, store = _durable(tmp_path)
        first = _okx(audit, store)
        second = record_evidence(
            audit=audit,
            store=store,
            source="bybit",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            contradicts=first.evidence_id,
        )
        rows = {row["evidence_id"]: row for row in store.evidence_refs()}
        assert rows[first.evidence_id]["contradicts"] is None
        assert rows[second.evidence_id]["contradicts"] == first.evidence_id
        assert len(store.evidence_refs()) == 2
        store.close()

    def test_a_contradiction_survives_a_replay_from_the_chain_alone(self, tmp_path: Path) -> None:
        """L-2's payoff for the new column: it rides in the event, so boot recovery reproduces the link."""
        audit, store = _durable(tmp_path)
        first = _okx(audit, store)
        second = record_evidence(
            audit=audit,
            store=store,
            source="bybit",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            contradicts=first.evidence_id,
        )
        conn = sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)
        conn.execute("DELETE FROM evidence_ref")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        assert store.counts()["evidence_ref"] == 0

        assert len(reproject_missing(audit=audit, store=store)) >= 2
        replayed = store.get_evidence_ref(second.evidence_id)
        assert replayed is not None
        assert replayed["contradicts"] == first.evidence_id
        assert verify_evidence_checksum(replayed), "the recomputed checksum survives the round trip"
        store.close()

    def test_the_new_column_joined_the_covered_set(self) -> None:
        """F-21 one column at a time: a stored field the checksum does not cover is a field that can change
        undetected, and neither of the two documented exclusions applies to ``contradicts`` — it is known at
        write time and is not the value being computed. The guard that derives the covered set from
        ``PRAGMA table_info`` is what made this one decision rather than two."""
        assert "contradicts" in CHECKSUMMED_FIELDS
        assert len(CHECKSUMMED_FIELDS) == 10
        assert CHECKSUMMED_FIELDS.count("contradicts") == 1
        assert "checksum" not in CHECKSUMMED_FIELDS and "audit_ref" not in CHECKSUMMED_FIELDS


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
