"""The dossier writer (L-E, Stage 8.3) and the four decisions it makes on the record's behalf.

``dossier`` was built in Stage 6, given back its foreign key by migration ``0004_memory_fidelity`` in
Stage 8.2, and never written to. What is asserted here is not merely that a row lands: it is that the
defaults are the ABSTAIN side, that a stance is one of the seven words the repository already declares,
that a sufficiency claim has to say what it rests on and what it is sufficient *for*, that a parent the
database would silently accept is refused anyway, and that opening a case twice is refused rather than
treated as an edit.

Each of those is a decision, and each decision is pinned by a test that would fail if the decision were
quietly reversed — including the ones that *permit* something (``instrument_id=None``, a venue the
instrument is not mapped on, a non-ABSTAIN stance with no uncertainty), because a gate nobody has tested
for permissiveness is a gate nobody can tell from a bug.
"""

from __future__ import annotations

import inspect
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, SecretMaterialDetected, SqliteAuditStore
from nexus.core.ids import new_id
from nexus.domain.decision import DecisionVerb
from nexus.domain.instrument import Venue
from nexus.instruments.projection import project_master
from nexus.instruments.registry import InstrumentRegistry
from nexus.instruments.seed import seed_master
from nexus.intelligence.dossier import (
    DOSSIER_EVENT_TYPE,
    DOSSIER_PREFIX,
    SUFFICIENCY_BASIS_KEY,
    SUFFICIENCY_INSUFFICIENT,
    SUFFICIENCY_TARGET_KEY,
    VENUE_MAPS_INSTRUMENT_KEY,
    DossierReceipt,
    open_dossier,
    sufficiency_of,
)
from nexus.intelligence.evidence import record_evidence
from nexus.store.operational import PersistenceError, SqliteOperationalStore
from nexus.store.writeahead import PROJECTABLE, reproject_missing

SUMMARY = "Perp basis widening into the US session; watching for a funding flip."
UNCERTAINTY = "Sixty seconds of ticker data only, so the regime is unknown."
BTC_PERP = "INS-BTC-USDT-USDT"
EUR_USD = "INS-EUR-USD"


def _durable(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    """Audit store first, then the operational store — the ordering migration 0003 requires."""
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


def _booted(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    """A store holding the seeded master, which is what Stage 8.2's L-B made possible."""
    audit, store = _durable(tmp_path)
    registry = InstrumentRegistry()
    seed_master(registry)
    project_master(registry, audit=audit, store=store)
    return audit, store


def seed_master_into() -> InstrumentRegistry:
    registry = InstrumentRegistry()
    seed_master(registry)
    return registry


def _open(audit: AuditLog, store: SqliteOperationalStore, **overrides: Any) -> DossierReceipt:
    base: dict[str, Any] = {
        "summary": SUMMARY,
        "uncertainty": UNCERTAINTY,
        "instrument_id": BTC_PERP,
        "venue": "OKX",
    }
    base.update(overrides)
    return open_dossier(audit=audit, store=store, **base)


def _connect(tmp_path: Path) -> sqlite3.Connection:
    # isolation_level=None so a PRAGMA is not swallowed by an implicit transaction, which is how a
    # foreign-key pragma comes to look like a no-op.
    return sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)


class TestADossierIsOpenedAndStored:
    def test_the_row_lands_with_the_abstain_side_defaults(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        assert row["stance"] == "ABSTAIN", "the schema's own default, and the fail-closed side"
        assert row["state"] == "DRAFT"
        assert row["sufficiency"] == SUFFICIENCY_INSUFFICIENT
        assert row["instrument_id"] == BTC_PERP
        assert row["venue"] == "OKX"
        assert row["summary"] == SUMMARY
        assert row["uncertainty"] == UNCERTAINTY
        assert row["audit_ref"] == receipt.audit_ref
        assert store.counts()["dossier"] == 1
        store.close()

    def test_the_id_spends_the_prefix_the_repository_declared_for_a_research_case(self) -> None:
        """``core.ids.new_id``'s own table has listed ``CASE research case`` since Phase 2 and nothing
        had ever spent it; ``docs/03`` J-04 calls these "Research Dossiers → selects case"."""
        assert DOSSIER_PREFIX == "CASE"
        declared = inspect.getdoc(new_id) or ""
        assert "CASE research case" in declared, "the convention this writer spends is the declared one"
        assert new_id(DOSSIER_PREFIX).startswith("CASE-")

    def test_the_event_is_audited_and_projectable(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        assert PROJECTABLE[DOSSIER_EVENT_TYPE] == "dossier"
        record = next(r for r in audit.records() if r.record_id == receipt.audit_ref)
        assert record.event_type == DOSSIER_EVENT_TYPE
        assert record.payload["dossier_id"] == receipt.dossier_id
        assert record.payload["summary"] == SUMMARY
        store.close()

    def test_both_timestamps_ride_inside_the_event(self, tmp_path: Path) -> None:
        """The applied schema has no ``DEFAULT now()`` for either column, so a projection that filled
        them at write time would restamp a replay with the replay's clock."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        record = next(r for r in audit.records() if r.record_id == receipt.audit_ref)
        assert record.payload["created_at"] == receipt.created_at
        assert record.payload["updated_at"] == receipt.updated_at
        assert record.payload["created_at"] == record.payload["updated_at"], "an open is one moment"
        store.close()

    def test_a_replay_reproduces_the_row_including_its_clock(self, tmp_path: Path) -> None:
        """The property the timestamps-in-the-event decision exists for, tested across a real gap."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        evidence = record_evidence(
            audit=audit,
            store=store,
            source="okx.ticker",
            observed_at=datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC),
            retrieved_at=datetime(2026, 11, 26, 12, 0, 1, tzinfo=UTC),
            dossier_id=receipt.dossier_id,
        )
        original = store.get_dossier(receipt.dossier_id)
        assert original is not None

        conn = _connect(tmp_path)
        conn.execute("DELETE FROM dossier")
        conn.execute("DELETE FROM evidence_ref")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        assert store.counts()["dossier"] == 0

        time.sleep(1.05)  # long enough that a restamped created_at could not match by rounding
        reapplied = reproject_missing(audit=audit, store=store)
        assert len(reapplied) >= 2

        replayed = store.get_dossier(receipt.dossier_id)
        assert replayed is not None
        assert replayed["created_at"] == original["created_at"], "chronology survives a replay"
        assert replayed["updated_at"] == original["updated_at"]
        assert replayed["stance"] == original["stance"]
        assert replayed["payload"] == original["payload"]
        assert store.counts()["evidence_ref"] == 1
        assert store.evidence_refs(dossier_id=receipt.dossier_id)[0]["evidence_id"] == evidence.evidence_id
        store.close()

    def test_the_dossier_and_evidence_writers_compose(self, tmp_path: Path) -> None:
        """L-C was built usable before a dossier existed; L-E makes the other direction work too."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        for source in ("okx.ticker", "okx.books"):
            record_evidence(
                audit=audit,
                store=store,
                source=source,
                observed_at=datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC),
                retrieved_at=datetime(2026, 11, 26, 12, 0, 1, tzinfo=UTC),
                dossier_id=receipt.dossier_id,
            )
        attached = store.evidence_refs(dossier_id=receipt.dossier_id)
        assert len(attached) == 2
        assert {row["source"] for row in attached} == {"okx.ticker", "okx.books"}
        assert all(row["dossier_id"] == receipt.dossier_id for row in attached)
        store.close()

    def test_the_receipt_reports_what_was_written(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        as_dict = receipt.to_dict()
        for key in ("dossier_id", "instrument_id", "venue", "state", "stance", "summary", "uncertainty"):
            assert as_dict[key] == row[key], key
        assert as_dict[SUFFICIENCY_BASIS_KEY] == receipt.payload[SUFFICIENCY_BASIS_KEY]
        assert as_dict[SUFFICIENCY_TARGET_KEY] == receipt.payload[SUFFICIENCY_TARGET_KEY]
        assert as_dict[VENUE_MAPS_INSTRUMENT_KEY] is True
        store.close()


class TestTheStanceVocabularyIsTheOneTheRepositoryAlreadyDeclares:
    """Not the treatment ``evidence_ref.kind`` got, which is free text because no vocabulary for it
    exists anywhere. Here one does: the schema's default ``'ABSTAIN'`` is a ``DecisionVerb`` member, and
    ``docs/03`` §7 with ``docs/10`` §3.1 both name that seven-word vocabulary for the intelligence
    layer's disposition."""

    @pytest.mark.parametrize("verb", list(DecisionVerb))
    def test_all_seven_verbs_are_accepted(self, tmp_path: Path, verb: DecisionVerb) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, stance=verb)
        assert receipt.stance == verb.value
        store.close()

    def test_the_schema_default_is_a_member_of_the_vocabulary(self) -> None:
        assert DecisionVerb.ABSTAIN.value == "ABSTAIN"
        assert len(list(DecisionVerb)) == 7

    @pytest.mark.parametrize("word", ["MAYBE", "ABSTAINING", "abstain", "", "HOLD"])
    def test_an_eighth_word_is_refused(self, tmp_path: Path, word: str) -> None:
        """Including ``'abstain'``: a vocabulary is case-sensitive or it is not a vocabulary."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="stance must be one of"):
            _open(audit, store, stance=word)
        assert store.counts()["dossier"] == 0, "a refused open writes nothing"
        store.close()

    def test_the_column_is_still_text_so_the_writer_is_what_enforces_it(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        columns = {row[1]: row[2] for row in _connect(tmp_path).execute("PRAGMA table_info(dossier)")}
        assert columns["stance"] == "TEXT"
        assert columns["sufficiency"] == "TEXT"
        store.close()


class TestSufficiencyStaysAStringUntilStage10DefinesTheMeter:
    def test_insufficient_needs_neither_basis_nor_target(self, tmp_path: Path) -> None:
        """It claims nothing, so there is nothing to justify."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, sufficiency=SUFFICIENCY_INSUFFICIENT)
        assert receipt.sufficiency_basis == ""
        assert receipt.sufficiency_target == ""
        store.close()

    @pytest.mark.parametrize(
        ("basis", "target"),
        [("", ""), ("two LIVE snapshots", ""), ("", "V1 evidence sufficiency")],
    )
    def test_a_claim_above_insufficient_needs_both_qualifiers(
        self, tmp_path: Path, basis: str, target: str
    ) -> None:
        """``docs/10`` §3.1's rail carries "stated basis and what it is sufficient for"; §3.2's warning
        is that a bare enum leaves nowhere for V1's outcome to live."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="claims a judgement"):
            _open(
                audit,
                store,
                sufficiency="SUFFICIENT_FOR_REVIEW",
                sufficiency_basis=basis,
                sufficiency_target=target,
            )
        store.close()

    def test_a_claim_with_both_qualifiers_is_stored_with_them(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(
            audit,
            store,
            sufficiency="SUFFICIENT_FOR_REVIEW",
            sufficiency_basis="one okx ticker and one order-book snapshot, both LIVE",
            sufficiency_target="V1 evidence and data sufficiency for a research case, not for a trade",
        )
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        assert sufficiency_of(row) == {
            "sufficiency": "SUFFICIENT_FOR_REVIEW",
            SUFFICIENCY_BASIS_KEY: "one okx ticker and one order-book snapshot, both LIVE",
            SUFFICIENCY_TARGET_KEY: "V1 evidence and data sufficiency for a research case, not for a trade",
        }
        store.close()

    @pytest.mark.parametrize("value", ["0.85", "12", "1e-9", "-0.5", "0", "1.0"])
    def test_a_numeric_sufficiency_is_refused(self, tmp_path: Path, value: str) -> None:
        """``docs/12`` §1.3's law (A-02+A-08): no gate can be satisfied by a confidence value. A number
        in this column is a confidence value wearing a judgement's name."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="must be a judgement, not a number"):
            _open(audit, store, sufficiency=value)
        store.close()

    def test_a_whitespace_sufficiency_falls_back_to_insufficient(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, sufficiency="   ")
        assert receipt.sufficiency == SUFFICIENCY_INSUFFICIENT
        store.close()

    def test_a_caller_payload_cannot_overwrite_the_pinned_keys(self, tmp_path: Path) -> None:
        """The keys are written last, so a payload cannot talk a claim out of its own basis."""
        audit, store = _booted(tmp_path)
        receipt = _open(
            audit,
            store,
            sufficiency_basis="the real basis",
            sufficiency_target="the real target",
            payload={SUFFICIENCY_BASIS_KEY: "LIES", SUFFICIENCY_TARGET_KEY: "LIES", "extra": 1},
        )
        assert receipt.payload[SUFFICIENCY_BASIS_KEY] == "the real basis"
        assert receipt.payload[SUFFICIENCY_TARGET_KEY] == "the real target"
        assert receipt.payload["extra"] == 1, "everything else the caller passed is kept"
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        assert row["payload"][VENUE_MAPS_INSTRUMENT_KEY] is True
        store.close()


class TestAbstainIsADefaultAndNotAFallback:
    def test_abstain_without_uncertainty_is_refused(self, tmp_path: Path) -> None:
        """The schema's comment is that ABSTAIN is the default and not a fallback; an abstention that
        does not say what is unresolved is a fallback. ``docs/03`` J-04's exit condition is that the
        owner learns what would invalidate the thesis."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="needs a non-empty uncertainty"):
            _open(audit, store, uncertainty="   ")
        store.close()

    @pytest.mark.parametrize("verb", [v for v in DecisionVerb if v is not DecisionVerb.ABSTAIN])
    def test_a_non_abstain_stance_needs_no_uncertainty(self, tmp_path: Path, verb: DecisionVerb) -> None:
        """Pins the rule as being about ABSTAIN specifically, not a general demand for prose."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, stance=verb, uncertainty="")
        assert receipt.uncertainty == ""
        store.close()

    @pytest.mark.parametrize("summary", ["", "   ", "\n\t "])
    def test_a_summary_is_required(self, tmp_path: Path, summary: str) -> None:
        """It is the thesis in one line — the "concise rationale" ``docs/03`` §7 permits and the first
        thing J-04 step 1 renders. ``state='DRAFT'`` means not yet dispositioned, not not described."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="a dossier needs a summary"):
            _open(audit, store, summary=summary)
        store.close()

    def test_the_summary_and_uncertainty_are_stored_trimmed(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, summary=f"  {SUMMARY}  ", uncertainty=f"  {UNCERTAINTY}  ")
        assert receipt.summary == SUMMARY
        assert receipt.uncertainty == UNCERTAINTY
        store.close()


class TestTheParentMustExistBecauseTheDatabaseWillNotSaySo:
    def test_the_pragma_is_off_and_the_database_accepts_a_dangling_parent(self, tmp_path: Path) -> None:
        """The condition the writer's refusal exists for, demonstrated rather than asserted from docs."""
        audit, store = _booted(tmp_path)
        conn = _connect(tmp_path)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        assert list(conn.execute("PRAGMA foreign_key_list(dossier)"))[0][2] == "instrument"
        conn.execute(
            "INSERT INTO dossier (dossier_id, instrument_id, created_at, updated_at) "
            "VALUES ('CASE-DANGLING','INS-NOPE','2026-01-01T00:00:00.000Z','2026-01-01T00:00:00.000Z')"
        )
        assert conn.execute("SELECT count(*) FROM dossier WHERE dossier_id='CASE-DANGLING'").fetchone()[0]
        conn.execute("DELETE FROM dossier WHERE dossier_id='CASE-DANGLING'")
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO dossier (dossier_id, instrument_id, created_at, updated_at) "
                "VALUES ('CASE-DANGLING','INS-NOPE','2026-01-01T00:00:00.000Z',"
                "'2026-01-01T00:00:00.000Z')"
            )
        conn.close()
        store.close()

    def test_a_dangling_instrument_is_refused_by_the_writer_anyway(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="is not in the system of record") as exc:
            _open(audit, store, instrument_id="INS-NOPE")
        message = str(exc.value)
        assert "INS-NOPE" in message and "3" in message, "it names the id and what the store does hold"
        assert store.counts()["dossier"] == 0
        store.close()

    def test_nothing_can_be_opened_against_an_instrument_before_the_master_is_projected(
        self, tmp_path: Path
    ) -> None:
        """What makes Stage 8.2's L-B load-bearing rather than decorative: with no projection there is
        no parent row, and before this writer the honest failure would have been silent."""
        audit, store = _durable(tmp_path)
        assert store.counts()["instrument"] == 0
        with pytest.raises(ValueError, match="which holds 0"):
            _open(audit, store, instrument_id=BTC_PERP)
        project_master(seed_master_into(), audit=audit, store=store)
        receipt = _open(audit, store, instrument_id=BTC_PERP)
        assert receipt.instrument_id == BTC_PERP
        store.close()

    def test_instrument_id_none_is_allowed(self, tmp_path: Path) -> None:
        """A case that is not about one instrument is a statement; an unrecognised id is not one."""
        audit, store = _durable(tmp_path)
        receipt = _open(audit, store, instrument_id=None, venue=None)
        assert receipt.instrument_id is None
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None and row["instrument_id"] is None
        store.close()

    def test_an_empty_instrument_id_is_refused(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="a real id or None"):
            _open(audit, store, instrument_id="")
        store.close()


class TestTheVenueIsRecordedRatherThanGuessed:
    @pytest.mark.parametrize("venue", list(Venue))
    def test_all_ten_venues_are_accepted(self, tmp_path: Path, venue: Venue) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, instrument_id=None, venue=venue)
        assert receipt.venue == venue.value
        store.close()

    @pytest.mark.parametrize("venue", ["NASDAQ", "okx", "Okx", ""])
    def test_a_venue_outside_the_enum_is_refused(self, tmp_path: Path, venue: str) -> None:
        """Lower case included: normalising it silently would hide a caller that does not know the
        vocabulary. ``None`` is the way to say "not one venue"."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="venue must be one of"):
            _open(audit, store, instrument_id=None, venue=venue)
        store.close()

    def test_a_mapped_pair_is_recorded_as_mapped(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, instrument_id=BTC_PERP, venue="OKX")
        assert receipt.venue_maps_instrument is True
        store.close()

    def test_an_unmapped_pair_is_recorded_not_refused(self, tmp_path: Path) -> None:
        """``INS-EUR-USD`` on ``OANDA`` is a legitimate case today — the master maps EUR/USD at
        DUKASCOPY only — and refusing it would block the research the Intelligence Centre exists to
        hold. So the gap is recorded where a reviewer can see it."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, instrument_id=EUR_USD, venue="OANDA")
        assert receipt.venue_maps_instrument is False
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        assert row["payload"][VENUE_MAPS_INSTRUMENT_KEY] is False
        assert [m["venue"] for m in store.venue_mappings(instrument_id=EUR_USD)] == ["DUKASCOPY"]
        store.close()

    @pytest.mark.parametrize(("instrument_id", "venue"), [(None, "OKX"), (BTC_PERP, None), (None, None)])
    def test_the_flag_is_none_when_either_side_is_absent(
        self, tmp_path: Path, instrument_id: str | None, venue: str | None
    ) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, instrument_id=instrument_id, venue=venue)
        assert receipt.venue_maps_instrument is None
        store.close()

    def test_a_caller_cannot_forge_the_flag(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(
            audit,
            store,
            instrument_id=EUR_USD,
            venue="OANDA",
            payload={VENUE_MAPS_INSTRUMENT_KEY: True},
        )
        assert receipt.venue_maps_instrument is False, "computed from the master, not from the caller"
        store.close()


class TestOpeningIsNotEditing:
    def test_a_second_open_of_the_same_id_is_refused(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        first = _open(audit, store)
        with pytest.raises(ValueError, match="already exists, and opening is not editing"):
            _open(audit, store, dossier_id=first.dossier_id, summary="a restated thesis")
        store.close()

    def test_the_refusal_leaves_the_first_row_alone(self, tmp_path: Path) -> None:
        """The store writes with ``INSERT OR REPLACE`` because it is a projection, so without the
        refusal the read model would silently restate the row while the chain kept both events."""
        audit, store = _booted(tmp_path)
        first = _open(audit, store)
        with pytest.raises(ValueError):
            _open(audit, store, dossier_id=first.dossier_id, summary="a restated thesis", stance="WAIT")
        row = store.get_dossier(first.dossier_id)
        assert row is not None
        assert row["summary"] == SUMMARY
        assert row["stance"] == "ABSTAIN"
        assert store.counts()["dossier"] == 1
        store.close()

    def test_the_store_itself_would_have_replaced_the_row(self, tmp_path: Path) -> None:
        """Why the refusal is in the writer: the projection's replace semantics are correct for a
        projection and wrong for a verb called "open"."""
        audit, store = _booted(tmp_path)
        store.save_dossier({"dossier_id": "CASE-1", "summary": "first"})
        store.save_dossier({"dossier_id": "CASE-1", "summary": "second"})
        assert store.counts()["dossier"] == 1
        row = store.get_dossier("CASE-1")
        assert row is not None and row["summary"] == "second"
        store.close()

    def test_generated_ids_are_never_checked_against_the_store(self, tmp_path: Path) -> None:
        """Two opens with no id both succeed, and the lookup that guards a supplied id is not on the
        path that generates one."""
        audit, store = _booted(tmp_path)
        first = _open(audit, store)
        second = _open(audit, store)
        assert first.dossier_id != second.dossier_id
        assert store.counts()["dossier"] == 2
        store.close()


class TestTheStoreWriterFollowsTheAuditContract:
    def test_a_missing_id_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(PersistenceError, match="without a dossier_id"):
            store.save_dossier({"summary": "no id"})
        store.close()

    def test_secret_material_is_refused_by_the_store_and_by_the_writer(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(SecretMaterialDetected):
            store.save_dossier({"dossier_id": "CASE-X", "api_secret": "hunter2"})
        before = audit.length
        with pytest.raises(SecretMaterialDetected):
            _open(audit, store, payload={"api_secret": "hunter2"})
        assert audit.length == before, "a refused write does not extend the chain"
        assert store.counts()["dossier"] == 0
        store.close()

    def test_a_bare_payload_gets_the_schemas_own_defaults(self, tmp_path: Path) -> None:
        """The store fills what the applied schema has no ``DEFAULT`` for, and defaults the judgement
        columns to their ABSTAIN side — the writer's refusals do not exist down here, because a replay
        has to be able to write what the chain already holds."""
        audit, store = _durable(tmp_path)
        store.save_dossier({"dossier_id": "CASE-BARE"})
        row = store.get_dossier("CASE-BARE")
        assert row is not None
        assert (row["state"], row["stance"], row["sufficiency"]) == ("DRAFT", "ABSTAIN", "INSUFFICIENT")
        assert row["created_at"] and row["updated_at"]
        assert row["payload"] == {}
        store.close()

    def test_the_row_is_booked_into_the_projection_ledger(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        before = store.counts()["op_projection"]
        receipt = _open(audit, store)
        assert store.counts()["op_projection"] == before + 1
        assert receipt.audit_ref in store.projected_refs()
        store.close()

    def test_a_replay_is_not_refused_by_the_writers_parent_check(self, tmp_path: Path) -> None:
        """The parent check reads the store, which is why it lives in the writer and not in the
        projection: a replay must be able to write what the chain holds without a read-dependent
        refusal getting in the way."""
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store)
        conn = _connect(tmp_path)
        conn.execute("DELETE FROM dossier")
        conn.execute("DELETE FROM op_projection WHERE entity_type = 'dossier'")
        conn.close()
        assert reproject_missing(audit=audit, store=store)
        assert store.get_dossier(receipt.dossier_id) is not None
        store.close()


class TestReadsOrderingAndFiltering:
    def test_dossiers_come_back_newest_first(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        for day in ("2026-01-01", "2026-01-03", "2026-01-02"):
            store.save_dossier(
                {
                    "dossier_id": f"CASE-{day[-2:]}",
                    "created_at": f"{day}T00:00:00.000Z",
                    "updated_at": f"{day}T00:00:00.000Z",
                }
            )
        assert [row["dossier_id"] for row in store.dossiers()] == ["CASE-03", "CASE-02", "CASE-01"]
        store.close()

    def test_a_tie_on_the_clock_is_broken_by_id_so_the_order_is_deterministic(self, tmp_path: Path) -> None:
        """Two dossiers opened inside one millisecond are not a hypothetical: the writer stamps both
        columns from one ``utc_now()`` call."""
        audit, store = _durable(tmp_path)
        for dossier_id in ("CASE-Z", "CASE-A", "CASE-M"):
            store.save_dossier(
                {
                    "dossier_id": dossier_id,
                    "created_at": "2026-01-01T00:00:00.000Z",
                    "updated_at": "2026-01-01T00:00:00.000Z",
                }
            )
        assert [row["dossier_id"] for row in store.dossiers()] == ["CASE-A", "CASE-M", "CASE-Z"]
        store.close()

    def test_the_limit_and_the_filter_both_narrow(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        for instrument_id, venue in ((BTC_PERP, "OKX"), (BTC_PERP, "BYBIT"), (EUR_USD, "DUKASCOPY")):
            _open(audit, store, instrument_id=instrument_id, venue=venue)
        assert len(store.dossiers()) == 3
        assert len(store.dossiers(limit=2)) == 2
        perp = store.dossiers(instrument_id=BTC_PERP)
        assert len(perp) == 2 and {row["venue"] for row in perp} == {"OKX", "BYBIT"}
        assert len(store.dossiers(instrument_id=EUR_USD)) == 1
        assert store.dossiers(instrument_id="INS-NOPE") == ()
        store.close()

    def test_get_dossier_returns_none_for_an_unknown_id(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        assert store.get_dossier("CASE-NOPE") is None
        store.close()

    def test_the_payload_reads_back_as_a_dict_not_as_text(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _open(audit, store, payload={"catalyst": "funding flip", "tiers": [1, 2]})
        row = store.get_dossier(receipt.dossier_id)
        assert row is not None
        assert row["payload"]["catalyst"] == "funding flip"
        assert row["payload"]["tiers"] == [1, 2]
        assert store.dossiers()[0]["payload"]["catalyst"] == "funding flip"
        store.close()


class TestWhatThisWriterDoesNotDo:
    def test_nothing_in_src_calls_it_yet(self) -> None:
        """The same limitation Stage 8.2 recorded for ``record_evidence``, stated as a property of the
        tree rather than as a count that goes stale: the writer exists and is unwired on purpose,
        because wiring it means deciding what the system should research."""
        root = Path(__file__).resolve().parents[1] / "src" / "nexus"
        callers = [
            path.relative_to(root).as_posix()
            for path in sorted(root.rglob("*.py"))
            if "intelligence/dossier.py" not in path.as_posix()
            and "intelligence/__init__.py" not in path.as_posix()
            and "open_dossier(" in path.read_text(encoding="utf-8")
        ]
        assert callers == [], callers

    def test_no_counter_thesis_or_tier_column_was_invented(self, tmp_path: Path) -> None:
        """``docs/03`` J-04 asks the view for a counter-thesis and ``docs/10`` §3.1 for research depth
        Tier 0-4. Neither has a column, and this batch added none: the route names both as gaps instead
        of serving ``uncertainty`` as though it were the case against."""
        audit, store = _booted(tmp_path)
        columns = {row[1] for row in _connect(tmp_path).execute("PRAGMA table_info(dossier)")}
        assert columns == {
            "dossier_id",
            "instrument_id",
            "venue",
            "created_at",
            "updated_at",
            "state",
            "summary",
            "stance",
            "uncertainty",
            "sufficiency",
            "payload",
            "audit_ref",
        }
        assert not {"counter_thesis", "tier", "research_tier"} & columns
        receipt = _open(audit, store)
        assert not {"counter_thesis", "tier"} & set(receipt.payload)
        store.close()

    def test_memory_item_is_still_schema_only(self, tmp_path: Path) -> None:
        """D-051 deferred F-18's columns to the stage-10 batch that writes this table, so the table
        stays empty and its three missing columns stay missing."""
        audit, store = _booted(tmp_path)
        _open(audit, store)
        assert store.counts()["memory_item"] == 0
        columns = {row[1] for row in _connect(tmp_path).execute("PRAGMA table_info(memory_item)")}
        assert not {"valid_from", "valid_until", "change_conditions"} & columns
        store.close()
