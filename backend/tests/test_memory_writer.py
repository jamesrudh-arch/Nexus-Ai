"""The memory writer (Stage 8.5) and the decisions it makes on the record's behalf.

``memory_item`` was built in Stage 6, given a ``CHECK`` on ``confidence`` by migration
``0004_memory_fidelity`` in Stage 8.2, and never written to. D-051's ruling 2 declined to add F-18's
columns early for a reason that turned out to be the right one — *"columns no writer populates are columns
no test can exercise, and a nullable column nobody fills is indistinguishable from one that was dropped"*
— and D-053's ruling 4 named this batch as the one that writes the table. So the columns and the writer
are tested together, and what is asserted here is not merely that a row lands.

It is that the defaults claim as little as the schema allows; that a confidence cannot arrive without the
validity interval, the change conditions and the provenance ``docs/10`` §3.1 and ``docs/03`` §7 ask for;
that a confidence which PostgreSQL would reject or silently round is refused at the boundary instead; that
the interval is about the world and not about this system's clock; that a belief whose validity has already
ended is dated rather than refused; that nothing cites itself and nothing is superseded by a writer that
only records; and that the columns this batch was **not** ruled into — an expiry, a band — are absent from
the writer's signature as well as from the table, so their absence is a decision a reader can argue with.

Each of those is pinned by a test that would fail if the decision were quietly reversed, including the ones
that *permit* something (no confidence at all, a negative confidence, an expired interval, an open-ended
one, a duplicated citation), because a gate nobody has tested for permissiveness is a gate nobody can tell
from a bug.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import time
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, SqliteAuditStore
from nexus.core.errors import RejectReason
from nexus.core.ids import new_id
from nexus.intelligence.dossier import open_dossier
from nexus.intelligence.evidence import record_evidence
from nexus.intelligence.memory import (
    CONFIDENCE_PRECISION,
    CONFIDENCE_SCALE,
    EVIDENCE_IDS_KEY,
    MEMORY_EVENT_TYPE,
    MEMORY_KIND_OBSERVATION,
    MEMORY_PREFIX,
    MEMORY_SCOPE_GLOBAL,
    VALIDITY_OPEN_ENDED_KEY,
    MemoryReceipt,
    confidence_text,
    record_memory_item,
    validity_of,
)
from nexus.store.operational import PersistenceError, SqliteOperationalStore
from nexus.store.writeahead import PROJECTABLE, reproject_missing

BODY = "Perp basis on OKX runs wide into the US session and narrows again at the London close."
CONDITIONS = "A funding flip, or a basis inside 2 bps for three consecutive hours."
SUBJECT = "INS-BTC-USDT-USDT"
VALID_FROM = datetime(2026, 11, 27, 6, 0, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 12, 4, 6, 0, 0, tzinfo=UTC)
OBSERVED = datetime(2026, 11, 27, 6, 43, 35, tzinfo=UTC)
EXPIRES_AT = VALID_UNTIL + timedelta(days=30)
RETRIEVED = OBSERVED + timedelta(milliseconds=400)


def _durable(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    """Audit store first, then the operational store — the ordering migration 0003 requires."""
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


def _connect(tmp_path: Path) -> sqlite3.Connection:
    # isolation_level=None so a PRAGMA is not swallowed by an implicit transaction, which is how a
    # foreign-key pragma comes to look like a no-op.
    return sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)


def _evidence(audit: AuditLog, store: SqliteOperationalStore, count: int = 2) -> tuple[str, ...]:
    """Real evidence rows, because provenance is checked against the store rather than assumed."""
    return tuple(
        record_evidence(
            audit=audit,
            store=store,
            source=source,
            observed_at=OBSERVED + timedelta(seconds=index),
            retrieved_at=RETRIEVED + timedelta(seconds=index),
        ).evidence_id
        for index, source in enumerate(["okx.ticker", "bybit.ticker", "binance-vision.kline"][:count])
    )


def _record(audit: AuditLog, store: SqliteOperationalStore, **overrides: Any) -> MemoryReceipt:
    """A belief that satisfies every requirement, so a test can change one thing and mean one thing."""
    base: dict[str, Any] = {
        "body": BODY,
        "kind": "BELIEF",
        "subject": SUBJECT,
        "confidence": "0.72",
        "valid_from": VALID_FROM,
        "valid_until": VALID_UNTIL,
        "change_conditions": CONDITIONS,
    }
    base.update(overrides)
    if "evidence_ids" not in base:
        base["evidence_ids"] = _evidence(audit, store)
    return record_memory_item(audit=audit, store=store, **base)


class TestAMemoryItemIsRecordedAndStored:
    def test_the_row_lands_with_the_least_claiming_defaults(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(audit=audit, store=store, body=BODY)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["body"] == BODY
        assert row["kind"] == MEMORY_KIND_OBSERVATION, (
            "the schema's own default, and the least a row can claim"
        )
        assert row["scope"] == MEMORY_SCOPE_GLOBAL
        assert row["subject"] == ""
        assert row["confidence"] is None
        assert row["valid_from"] is None
        assert row["valid_until"] is None
        assert row["change_conditions"] == ""
        assert row["superseded_by"] is None
        assert row["cited_by"] == ()
        assert row["audit_ref"] == receipt.audit_ref
        assert store.counts()["memory_item"] == 1
        store.close()

    def test_a_belief_stores_all_three_of_the_columns_this_batch_added(self, tmp_path: Path) -> None:
        """F-18's first gap, closed: the interval and the conditions arrive beside the confidence."""
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["confidence"] == "0.72"
        assert row["valid_from"] == "2026-11-27T06:00:00.000Z"
        assert row["valid_until"] == "2026-12-04T06:00:00.000Z"
        assert row["change_conditions"] == CONDITIONS
        assert validity_of(row) == {
            "valid_from": "2026-11-27T06:00:00.000Z",
            "valid_until": "2026-12-04T06:00:00.000Z",
            VALIDITY_OPEN_ENDED_KEY: False,
            "change_conditions": CONDITIONS,
            EVIDENCE_IDS_KEY: list(receipt.evidence_ids),
        }
        store.close()

    def test_the_event_is_audited_and_projectable(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        assert PROJECTABLE[MEMORY_EVENT_TYPE] == "memory_item"
        record = next(r for r in audit.records() if r.record_id == receipt.audit_ref)
        assert record.event_type == MEMORY_EVENT_TYPE
        assert record.payload["memory_id"] == receipt.memory_id
        assert record.payload["body"] == BODY
        assert record.payload["change_conditions"] == CONDITIONS
        store.close()

    def test_created_at_rides_inside_the_event(self, tmp_path: Path) -> None:
        """The applied schema has no ``DEFAULT now()`` for it (``docs/15`` §9.1's four lost defaults), so a
        projection that filled it at write time would restamp a replay with the replay's clock."""
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        record = next(r for r in audit.records() if r.record_id == receipt.audit_ref)
        assert record.payload["created_at"] == receipt.created_at
        store.close()

    def test_a_replay_reproduces_the_row_including_its_clock(self, tmp_path: Path) -> None:
        """L-2's payoff, tested across a real gap: the row is rebuilt from the chain alone."""
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        receipt = _record(audit, store, evidence_ids=ids)
        original = store.get_memory_item(receipt.memory_id)
        assert original is not None

        conn = _connect(tmp_path)
        conn.execute("DELETE FROM memory_item")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        assert store.counts()["memory_item"] == 0

        time.sleep(1.05)  # long enough that a restamped created_at could not match by rounding
        reapplied = reproject_missing(audit=audit, store=store)
        assert receipt.audit_ref in reapplied

        replayed = store.get_memory_item(receipt.memory_id)
        assert replayed is not None
        assert replayed["created_at"] == original["created_at"], "the record time survives a replay"
        assert replayed["confidence"] == original["confidence"]
        assert replayed["valid_from"] == original["valid_from"]
        assert replayed["valid_until"] == original["valid_until"]
        assert replayed["change_conditions"] == original["change_conditions"]
        assert replayed["payload"] == original["payload"]
        assert replayed["cited_by"] == ()
        store.close()

    def test_the_payload_reads_back_as_a_dict_not_as_text(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, payload={"catalyst": "funding flip", "windows": [1, 2]})
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["payload"]["catalyst"] == "funding flip"
        assert row["payload"]["windows"] == [1, 2]
        assert store.memory_items()[0]["payload"]["catalyst"] == "funding flip"
        store.close()

    def test_kind_and_scope_filter_the_list_and_kind_is_indexed(self, tmp_path: Path) -> None:
        """``docs/10`` §3.1 asks the region for "type tabs"; ``ix_memory_kind`` has existed since 0002 and
        nothing had ever queried it."""
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        record_memory_item(audit=audit, store=store, body=BODY, kind="BELIEF", scope="INSTRUMENT")
        record_memory_item(audit=audit, store=store, body="An observation.", kind="OBSERVATION")
        record_memory_item(
            audit=audit,
            store=store,
            body=BODY,
            kind="BELIEF",
            confidence="0.4",
            valid_from=VALID_FROM,
            change_conditions=CONDITIONS,
            evidence_ids=ids,
        )
        assert len(store.memory_items()) == 3
        assert len(store.memory_items(kind="BELIEF")) == 2
        assert len(store.memory_items(kind="OBSERVATION")) == 1
        assert len(store.memory_items(scope="INSTRUMENT")) == 1
        assert len(store.memory_items(kind="BELIEF", scope="INSTRUMENT")) == 1
        assert store.memory_items(kind="NOPE") == ()
        indexes = {row[1] for row in _connect(tmp_path).execute("PRAGMA index_list(memory_item)")}
        assert {"ix_memory_kind", "ix_memory_created"} <= indexes
        store.close()

    def test_the_list_is_newest_first_and_bounded(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        for offset in range(3):
            record_memory_item(audit=audit, store=store, body=f"item {offset}")
        stamps = [row["created_at"] for row in store.memory_items()]
        assert stamps == sorted(stamps, reverse=True)
        assert len(store.memory_items(limit=2)) == 2
        store.close()

    def test_the_id_spends_the_prefix_the_repository_was_already_using(self) -> None:
        """``core.ids.new_id``'s convention table lists neither ``MEM`` nor ``EV``, and that is not an
        oversight this batch fixes: the table names prefixes, it does not register them. ``MEM`` is the
        prefix ``tests/test_schema_fidelity.py`` has written ``memory_item`` rows under since Stage 8.2's
        migration-0004 rebuild test, which is the same justification ``EVIDENCE_PREFIX`` gives for ``EV``.
        """
        assert MEMORY_PREFIX == "MEM"
        assert new_id(MEMORY_PREFIX).startswith("MEM-")
        declared = inspect.getdoc(new_id) or ""
        assert "CASE research case" in declared, "the convention table this prefix is absent from"
        assert "MEM" not in declared and "EV" not in declared
        fidelity = (Path(__file__).resolve().parent / "test_schema_fidelity.py").read_text(encoding="utf-8")
        assert '"MEM-1"' in fidelity, "the prefix this writer spends was already the repository's"


class TestAConfidenceIsAClaimAndCarriesItsQualifiers:
    """``docs/10`` §3.1: *"a point estimate without them is a defect."* Both halves are pinned."""

    def test_a_confidence_with_no_change_conditions_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, change_conditions="")
        message = str(excinfo.value)
        assert "change_conditions" in message
        assert "point estimate" in message, "the refusal names the sentence it comes from"
        assert store.counts()["memory_item"] == 0
        store.close()

    def test_whitespace_only_conditions_are_the_same_as_none(self, tmp_path: Path) -> None:
        """A column that is ``NOT NULL DEFAULT ''`` accepts a space, and a space is not a condition."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="change_conditions"):
            _record(audit, store, change_conditions="   \n\t ")
        store.close()

    def test_a_confidence_with_no_valid_from_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, valid_from=None)
        message = str(excinfo.value)
        assert "valid_from" in message
        assert "validity interval" in message
        assert "created_at" in message, "the refusal says what is not being substituted, not only what is"
        store.close()

    def test_a_confidence_with_no_provenance_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, evidence_ids=())
        message = str(excinfo.value)
        assert "evidence_ids" in message
        assert "provenance" in message
        assert "A-02+A-08" in message, "the law the requirement rests on is named in the refusal"
        store.close()

    def test_the_three_refusals_are_three_messages_not_one(self, tmp_path: Path) -> None:
        """A caller missing all three is told about the first, and each message names one condition.

        Folding them into one string would send somebody to fix the interval when the real problem is the
        provenance — the reason ``docs/15`` §5.1's refusals are kept apart elsewhere in this package.
        """
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as first:
            record_memory_item(audit=audit, store=store, body=BODY, confidence="0.72")
        assert "change_conditions" in str(first.value)
        with pytest.raises(ValueError) as second:
            record_memory_item(
                audit=audit, store=store, body=BODY, confidence="0.72", change_conditions=CONDITIONS
            )
        assert "valid_from" in str(second.value)
        with pytest.raises(ValueError) as third:
            record_memory_item(
                audit=audit,
                store=store,
                body=BODY,
                confidence="0.72",
                change_conditions=CONDITIONS,
                valid_from=VALID_FROM,
            )
        assert "evidence_ids" in str(third.value)
        assert store.counts()["memory_item"] == 0
        store.close()

    def test_an_item_with_no_confidence_needs_none_of_the_three(self, tmp_path: Path) -> None:
        """The permissive half, pinned because it is the half that proves the rule is about a claim.

        The schema's own default ``kind`` is ``OBSERVATION`` and an observation of what happened has
        ``created_at`` and needs no validity interval. Requiring the three unconditionally would make the
        writer refuse the table's default row, which is not what ``docs/10`` §3.1 says.
        """
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(audit=audit, store=store, body="Funding turned negative at 04:00Z.")
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["confidence"] is None
        assert row["valid_from"] is None
        assert row["change_conditions"] == ""
        assert receipt.evidence_ids == ()
        store.close()

    def test_conditions_and_an_interval_are_allowed_without_a_confidence(self, tmp_path: Path) -> None:
        """The requirement runs one way only: a confidence needs its qualifiers, and qualifiers do not need
        a confidence. An observation that says when it stopped being true is more informative, not less."""
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(
            audit=audit,
            store=store,
            body="Funding turned negative at 04:00Z.",
            valid_from=VALID_FROM,
            valid_until=VALID_UNTIL,
            change_conditions=CONDITIONS,
        )
        assert receipt.confidence is None
        assert receipt.validity_open_ended is False
        assert receipt.change_conditions == CONDITIONS
        store.close()

    def test_an_empty_body_is_refused_with_or_without_a_confidence(self, tmp_path: Path) -> None:
        """``body`` is the one column the schema makes ``NOT NULL`` with no default, and ``docs/03`` §7
        permits "structured findings + concise rationale only" — a finding with no text is neither."""
        audit, store = _durable(tmp_path)
        for candidate in ("", "   ", "\n\t "):
            with pytest.raises(ValueError, match="body"):
                record_memory_item(audit=audit, store=store, body=candidate)
        assert store.counts()["memory_item"] == 0
        store.close()


class TestTheConfidenceFitsTheTypeTheTargetDeclares:
    """``NUMERIC(6, 5)`` in ``migrations/0002_memory.sql``, ``TEXT`` plus an unbounded ``CHECK`` in SQLite.

    Nothing between the writer and the database can enforce the target's declared type, so a value
    PostgreSQL would reject or silently round would be stored here and fail at promotion under R-1's
    triggers. The writer is where the two schemas are made to agree.
    """

    @pytest.mark.parametrize(
        "value",
        ["0", "0.72", "1", "-0.5", "9.99999", "0.00001", "9.999990", Decimal("0.7"), Decimal("1E-5"), 1],
    )
    def test_a_value_the_target_can_hold_is_accepted(self, tmp_path: Path, value: Any) -> None:
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, confidence=value)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["confidence"] == confidence_text(value)
        store.close()

    @pytest.mark.parametrize("value", ["10", "123", "1E+2", "-10", "99.99999"])
    def test_a_magnitude_the_target_would_overflow_is_refused(self, value: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            confidence_text(value)
        message = str(excinfo.value)
        assert f"NUMERIC({CONFIDENCE_PRECISION},{CONFIDENCE_SCALE})" in message
        assert "digits before the decimal point" in message
        assert "overflow" in message, "the refusal says what PostgreSQL would do, not only what we do"

    @pytest.mark.parametrize("value", ["0.123456", "0.000001", "1.0000009"])
    def test_a_scale_the_target_would_round_is_refused(self, value: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            confidence_text(value)
        message = str(excinfo.value)
        assert f"{CONFIDENCE_SCALE} decimal places" not in message or "carries" in message
        assert "round" in message, "PostgreSQL would round it; this schema's rule is that it does not"

    def test_a_trailing_zero_is_not_a_sixth_decimal_place(self) -> None:
        """The check is on the value and the stored text is the caller's own.

        ``9.999990`` and ``9.99999`` are the same number and PostgreSQL stores the same ``NUMERIC(6,5)``
        for both, so refusing the first would be a strictness with no rule behind it — and rewriting it
        would be a precision change with a tidy name, which ``store/serialise.py``'s first rule is about.
        """
        assert confidence_text("9.999990") == "9.999990"
        assert confidence_text("9.99999") == "9.99999"
        assert Decimal(confidence_text("9.999990")) == Decimal(confidence_text("9.99999"))

    def test_a_float_is_refused_because_a_decimal_never_becomes_one(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            confidence_text(0.72)
        assert "float" in str(excinfo.value)
        assert "serialise" in str(excinfo.value), "the refusal names the rule it is enforcing"

    def test_a_bool_is_refused_because_python_says_it_is_an_int(self) -> None:
        """``Decimal(True)`` is ``Decimal('1')``, so without this refusal ``True`` would be stored as a
        confidence of one — the highest value the column can hold, from a caller that meant a flag."""
        for value in (True, False):
            with pytest.raises(ValueError, match="bool"):
                confidence_text(value)

    @pytest.mark.parametrize("value", ["", "   ", "abc", "0.7.2", "NaN", "Infinity", "-Infinity"])
    def test_junk_is_refused(self, value: str) -> None:
        with pytest.raises(ValueError):
            confidence_text(value)

    def test_the_range_is_not_bounded_and_that_is_recorded(self, tmp_path: Path) -> None:
        """A negative confidence and a confidence above one are both accepted, on purpose.

        No approved document declares a range for confidence, ``NUMERIC(6,5)`` does not imply ``[0, 1]``,
        and ``test_the_check_does_not_bound_the_range_and_that_is_recorded`` pins the schema's unboundedness
        as a decision. Bounding it here would invent a semantic and would disagree with the column's own
        recorded rationale — so the writer bounds what the target declares and no more, and ``docs/15`` §12
        asks whether that should stay true.
        """
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        low = _record(audit, store, confidence="-0.5", evidence_ids=ids)
        high = _record(audit, store, confidence="9.99999", evidence_ids=ids)
        assert store.get_memory_item(low.memory_id)["confidence"] == "-0.5"  # type: ignore[index]
        assert store.get_memory_item(high.memory_id)["confidence"] == "9.99999"  # type: ignore[index]
        assert Decimal(str(low.confidence)) < Decimal("0")
        assert Decimal(str(high.confidence)) > Decimal("1")
        store.close()

    def test_the_writer_agrees_with_0004s_check_rather_than_leaving_it_to_the_database(
        self, tmp_path: Path
    ) -> None:
        """Every value the writer accepts is a value the ``CHECK`` accepts, so the two never disagree in
        the direction that matters: nothing is stored that the schema would have refused."""
        audit, store = _durable(tmp_path)
        conn = _connect(tmp_path)
        for value in ("0", "0.72", "1", "-0.5", "9.99999", "0.00001"):
            receipt = _record(audit, store, confidence=value, subject=value)
            stored = conn.execute(
                "SELECT confidence FROM memory_item WHERE memory_id = ?", (receipt.memory_id,)
            ).fetchone()[0]
            assert stored == value
        store.close()


class TestTheIntervalIsAboutTheWorldAndNotTheRecord:
    def test_valid_from_is_not_created_at(self, tmp_path: Path) -> None:
        """The distinction the whole decision rests on, asserted as two different values.

        ``created_at`` says when this system wrote the row; ``valid_from`` says from when the claim is
        asserted to hold. Defaulting the second to the first would make every belief exactly as fresh as
        the moment it was recorded, which is F-14's mistake in a different pair of columns.
        """
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["valid_from"] == "2026-11-27T06:00:00.000Z"
        assert row["created_at"] != row["valid_from"], "one is our clock, the other is the claim's"
        assert receipt.created_at == row["created_at"]
        store.close()

    def test_an_open_ended_interval_says_so_instead_of_leaving_a_hole(self, tmp_path: Path) -> None:
        """``valid_until=None`` means no end was stated, which is not the same as no end — and a nullable
        column nobody fills is indistinguishable from one that was dropped (D-051's ruling 2)."""
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, valid_until=None)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["valid_until"] is None
        assert receipt.validity_open_ended is True
        assert row["payload"][VALIDITY_OPEN_ENDED_KEY] is True
        assert validity_of(row)[VALIDITY_OPEN_ENDED_KEY] is True
        store.close()

    def test_a_closed_interval_is_not_reported_as_open(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        assert receipt.validity_open_ended is False
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["payload"][VALIDITY_OPEN_ENDED_KEY] is False
        store.close()

    def test_an_interval_that_ends_before_it_starts_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, valid_from=VALID_UNTIL, valid_until=VALID_FROM)
        assert "must follow valid_from" in str(excinfo.value)
        store.close()

    def test_an_interval_of_zero_length_is_refused_too(self, tmp_path: Path) -> None:
        """An instant bounds nothing, and a belief that holds at exactly one millisecond is not a belief
        anybody can act on or review."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="must follow valid_from"):
            _record(audit, store, valid_until=VALID_FROM)
        store.close()

    def test_a_validity_that_has_already_ended_is_accepted(self, tmp_path: Path) -> None:
        """An expired belief is a record of what this system used to hold. Refusing it would date history
        by deleting it, and nothing in this batch re-evaluates an interval against the current clock."""
        audit, store = _durable(tmp_path)
        past_from = datetime(2020, 1, 1, tzinfo=UTC)
        past_until = datetime(2020, 1, 8, tzinfo=UTC)
        receipt = _record(audit, store, valid_from=past_from, valid_until=past_until)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["valid_until"] == "2020-01-08T00:00:00.000Z"
        assert receipt.validity_open_ended is False
        store.close()

    def test_a_validity_starting_in_the_future_is_accepted(self, tmp_path: Path) -> None:
        """A belief about a window that has not opened yet is a statement, and ``core.time.age_seconds``
        clamps a future stamp to zero for *our* clock only — the same distinction Stage 8.4 drew between
        ``age_seconds`` and ``venue_age_seconds``."""
        audit, store = _durable(tmp_path)
        future = datetime(2030, 1, 1, tzinfo=UTC)
        receipt = _record(audit, store, valid_from=future, valid_until=future + timedelta(days=1))
        assert receipt.valid_from == "2030-01-01T00:00:00.000Z"
        store.close()

    @pytest.mark.parametrize("name", ["valid_from", "valid_until"])
    def test_a_naive_datetime_is_refused_before_anything_compares_it(self, tmp_path: Path, name: str) -> None:
        """Comparing a naive datetime with an aware one raises a bare ``TypeError``, which is an
        unclassified crash at a point where nothing names the condition — the failure mode F-4 was about.
        """
        audit, store = _durable(tmp_path)
        naive = datetime(2026, 11, 27, 6, 0, 0)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, **{name: naive})
        assert name in str(excinfo.value)
        assert "naive" in str(excinfo.value)
        store.close()


class TestProvenanceIsCheckedRatherThanAssumed:
    def test_an_evidence_id_the_store_has_never_held_is_refused(self, tmp_path: Path) -> None:
        """``PRAGMA foreign_keys`` is off, so SQLite would store the dangling id without comment and a
        reviewer would read a citation with nothing behind it."""
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, evidence_ids=["EV-NOPE"])
        message = str(excinfo.value)
        assert "EV-NOPE" in message
        assert "provenance" in message
        assert "foreign_keys" in message, "the refusal says why the database will not catch this one"
        assert store.counts()["memory_item"] == 0
        store.close()

    def test_one_real_id_beside_one_fake_one_is_refused_too(self, tmp_path: Path) -> None:
        """A provenance list is not partly true: a reviewer cannot tell which citation to follow."""
        audit, store = _durable(tmp_path)
        real = _evidence(audit, store, count=1)
        with pytest.raises(ValueError, match="EV-NOPE"):
            _record(audit, store, evidence_ids=[*real, "EV-NOPE"])
        store.close()

    def test_an_empty_entry_is_refused(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        real = _evidence(audit, store, count=1)
        for blank in ("", "   "):
            with pytest.raises(ValueError, match="names none"):
                _record(audit, store, evidence_ids=[*real, blank])
        store.close()

    def test_the_ids_are_pinned_and_a_caller_cannot_overwrite_them(self, tmp_path: Path) -> None:
        """The pinned keys are written last, so a payload that argues with its own provenance loses."""
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        receipt = _record(
            audit,
            store,
            evidence_ids=ids,
            payload={EVIDENCE_IDS_KEY: ["EV-FORGED"], VALIDITY_OPEN_ENDED_KEY: True},
        )
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["payload"][EVIDENCE_IDS_KEY] == list(ids)
        assert row["payload"][VALIDITY_OPEN_ENDED_KEY] is False
        assert receipt.payload[EVIDENCE_IDS_KEY] == list(ids)
        store.close()

    def test_a_duplicated_citation_is_kept_rather_than_silently_corrected(self, tmp_path: Path) -> None:
        """A citation list is the caller's statement. De-duplicating it would be a change nobody asked for,
        and the writer's rule for payload keys is that it overwrites only what it owns."""
        audit, store = _durable(tmp_path)
        one = _evidence(audit, store, count=1)
        receipt = _record(audit, store, evidence_ids=[*one, *one])
        assert receipt.evidence_ids == (one[0], one[0])
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["payload"][EVIDENCE_IDS_KEY] == [one[0], one[0]]
        store.close()

    def test_provenance_reaches_a_research_case_through_its_evidence(self, tmp_path: Path) -> None:
        """``memory_item`` has no ``dossier_id`` column and this batch added none, so the path from a belief
        to the case it belongs to runs through the evidence rows, which do carry one."""
        audit, store = _durable(tmp_path)
        case = open_dossier(audit=audit, store=store, summary="A thesis.", uncertainty="What is unresolved.")
        evidence = record_evidence(
            audit=audit,
            store=store,
            source="okx.ticker",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            dossier_id=case.dossier_id,
        )
        receipt = _record(audit, store, evidence_ids=[evidence.evidence_id])
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        cited = row["payload"][EVIDENCE_IDS_KEY][0]
        assert store.get_evidence_ref(cited)["dossier_id"] == case.dossier_id  # type: ignore[index]
        store.close()


class TestNothingCitesItAndNothingIsSuperseded:
    def test_cited_by_is_always_empty_because_an_item_cannot_cite_itself(self, tmp_path: Path) -> None:
        """A caller who could set ``cited_by`` could fabricate the citation graph ``docs/10`` §3.1 asks the
        view to render, so the key is pinned even against a payload that supplies it."""
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, payload={"cited_by": ["DEC-FORGED"]})
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert receipt.cited_by == ()
        assert row["cited_by"] == ()
        assert row["payload"]["cited_by"] == []
        store.close()

    def test_superseded_by_is_never_set_because_setting_it_means_editing_a_row(self, tmp_path: Path) -> None:
        """``docs/15`` §5.1: *"memory is superseded, never edited in place."* The pointer runs from the old
        row to the new one, so writing it is an update to a row that already exists — a second verb with its
        own audit event, which no ruling has authorised. ``docs/10`` §3.1's "corrections as first-class
        entries" is therefore still unbuilt, and §12 asks about it."""
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, payload={"superseded_by": "MEM-FORGED"})
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert receipt.superseded_by is None
        assert row["superseded_by"] is None, "the column exists and this writer never fills it"
        store.close()

    def test_the_store_will_persist_a_supersession_the_writer_will_not_make(self, tmp_path: Path) -> None:
        """The projection stays capable of it, so the second verb is a writer and not a migration.

        A projection that refused the column would fail the replay of an event the chain already holds,
        which is the reason ``save_dossier`` gives for not checking its own foreign key.
        """
        audit, store = _durable(tmp_path)
        first = _record(audit, store)
        second = _record(audit, store)
        store.save_memory_item(
            {
                "memory_id": first.memory_id,
                "body": BODY,
                "created_at": first.created_at,
                "superseded_by": second.memory_id,
            },
            audit_ref=None,
        )
        row = store.get_memory_item(first.memory_id)
        assert row is not None
        assert row["superseded_by"] == second.memory_id
        store.close()


class TestRecordingIsNotEditing:
    def test_a_second_record_under_the_same_id_is_refused(self, tmp_path: Path) -> None:
        """The store writes with ``INSERT OR REPLACE`` because it is a projection, so a second record would
        restate the first row's body and confidence in the read model."""
        audit, store = _durable(tmp_path)
        first = _record(audit, store)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, memory_id=first.memory_id, body="A restated finding.")
        message = str(excinfo.value)
        assert first.memory_id in message
        assert "INSERT OR REPLACE" in message
        assert "superseded" in message, "the refusal names the mechanism that exists instead"
        row = store.get_memory_item(first.memory_id)
        assert row is not None
        assert row["body"] == BODY, "the first row is unchanged"
        assert store.counts()["memory_item"] == 1
        store.close()

    def test_a_generated_id_is_never_checked_against_the_store(self, tmp_path: Path) -> None:
        """``memory_id=None`` means "a new item", and refusing it would be refusing the only way to write
        one. The existence check runs only for a caller-supplied id, which is a claim about a row."""
        audit, store = _durable(tmp_path)
        receipts = [_record(audit, store) for _ in range(3)]
        assert len({r.memory_id for r in receipts}) == 3
        assert store.counts()["memory_item"] == 3
        store.close()

    def test_the_projection_refuses_a_row_with_no_id_and_no_body(self, tmp_path: Path) -> None:
        """Two refusals the store does make, because neither can depend on a read: a replay that could not
        reproduce a row would leave a hole ``reproject_missing`` believes is filled."""
        audit, store = _durable(tmp_path)
        with pytest.raises(PersistenceError, match="memory_id"):
            store.save_memory_item({"body": BODY})
        with pytest.raises(PersistenceError, match="body"):
            store.save_memory_item({"memory_id": "MEM-X"})
        store.close()


class TestAnExpiryIsAFourthClockAndNotACorrection:
    """Stage 8.7: ``expires_at``, stored — and acted on by nothing.

    D-055's ruling 4 ordered one nullable column on ``memory_item`` only, on the distinction the migration
    carries: ``valid_until`` says until when a claim holds *in the world*, while an expiry says when *this
    system* should stop serving the row. So the assertions here are of two kinds. That the column is stored
    faithfully, rides in the audited event, and survives a replay byte-identically. And that the writer
    refuses **less** than it looks like it should: an expiry in the past is accepted, and an expiry is never
    compared with a clock on the other axis, because a refusal built on ordering two clocks the schema keeps
    apart would assert a relationship that does not exist. Each of those permissions is pinned, since a gate
    nobody has tested for permissiveness is a gate nobody can tell from a bug.
    """

    def test_an_expiry_is_stored_as_the_exact_text_the_writer_derived(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, expires_at=EXPIRES_AT)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["expires_at"] == "2027-01-03T06:00:00.000Z"
        assert receipt.expires_at == row["expires_at"]
        assert receipt.to_dict()["expires_at"] == row["expires_at"]
        store.close()

    def test_an_unstated_expiry_is_null_and_is_not_defaulted_from_another_clock(self, tmp_path: Path) -> None:
        """``NULL`` means "no expiry was stated", which is not the claim "never expires".

        The same distinction ``validity_open_ended`` keeps for the interval, and the reason there is no
        ``DEFAULT`` in the migration: a default computed from ``created_at`` would make an unstated expiry
        into a stated one, silently, in the schema.
        """
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["expires_at"] is None
        assert receipt.expires_at is None
        assert receipt.created_at != "", "the row has a record time; it is simply not the expiry"
        columns = {r[1]: r for r in _connect(tmp_path).execute("PRAGMA table_info(memory_item)")}
        assert columns["expires_at"][4] is None, "no default, so an unstated expiry stays NULL"
        store.close()

    def test_a_naive_expiry_is_refused_before_anything_is_compared_with_it(self, tmp_path: Path) -> None:
        """The one refusal this column earns, and it is the refusal every clock here gets.

        ``_aware`` runs before any comparison, so a naive datetime is refused as naive rather than raising
        a bare ``TypeError`` from being compared with an aware one — an unclassified crash at a point where
        nothing names the condition, which is the failure mode F-4 was about. Nothing is written and, per
        L-2, nothing is audited: the audit length is captured *before* the refused call, because the
        evidence rows the call would cite are themselves audited and a fresh ``_evidence`` here would write
        two more of them and move the number being asserted against.
        """
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        before = audit.length
        naive = datetime(2027, 1, 3, 6, 0, 0)
        with pytest.raises(ValueError, match="expires_at must be an aware UTC datetime") as caught:
            _record(audit, store, evidence_ids=ids, expires_at=naive)
        assert "naive" in str(caught.value)
        assert naive.isoformat() in str(caught.value), "the refusal names the value it was given"
        assert store.counts()["memory_item"] == 0, "no row was written"
        assert audit.length == before, "and no audit entry was written for a row that does not exist"
        store.close()

    def test_an_expiry_already_in_the_past_is_dated_rather_than_refused(self, tmp_path: Path) -> None:
        """An item whose expiry has passed is legitimate: refusing it would make the writer the thing that
        decides an expired belief should never have been recorded. Same treatment the interval got in 8.5 —
        a belief whose validity has already ended is dated, not deleted."""
        audit, store = _durable(tmp_path)
        past = VALID_FROM - timedelta(days=400)
        receipt = _record(audit, store, expires_at=past)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["expires_at"] == "2025-10-23T06:00:00.000Z"
        store.close()

    @pytest.mark.parametrize(
        ("expiry", "why"),
        [
            (VALID_FROM - timedelta(days=1), "before the claim starts holding in the world"),
            (VALID_FROM, "exactly when the claim starts holding"),
            (VALID_UNTIL, "exactly when the claim stops holding"),
            (VALID_UNTIL + timedelta(days=3650), "a decade after the claim ends"),
        ],
    )
    def test_an_expiry_is_never_compared_with_a_clock_on_the_other_axis(
        self, tmp_path: Path, expiry: datetime, why: str
    ) -> None:
        """Four orderings that look like errors and are not, because the two clocks are on different axes.

        ``valid_from``/``valid_until`` bound the claim in the world; ``expires_at`` bounds this system's
        serving of the row. A belief can hold until 2027 and be expired for our purposes tomorrow, and the
        disagreement is information rather than a conflict. Refusing any of these would assert a
        relationship the schema deliberately does not have — F-14's mistake in reverse, since two clocks
        kept apart in the columns have to stay apart in the rules too.
        """
        audit, store = _durable(tmp_path)
        receipt = _record(audit, store, expires_at=expiry, valid_from=VALID_FROM, valid_until=VALID_UNTIL)
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None, why
        assert row["expires_at"] == receipt.expires_at, why
        assert row["valid_until"] == "2026-12-04T06:00:00.000Z", why
        store.close()

    def test_the_expiry_rides_in_the_event_so_a_replay_reproduces_it(self, tmp_path: Path) -> None:
        """L-2's payoff for the fourth clock: a timestamp that lived outside the audited event would be
        restamped by the replay, which is the defect ``created_at`` was moved inside the event to avoid."""
        audit, store = _durable(tmp_path)
        ids = _evidence(audit, store)
        receipt = _record(audit, store, evidence_ids=ids, expires_at=EXPIRES_AT)
        original = store.get_memory_item(receipt.memory_id)
        assert original is not None

        conn = _connect(tmp_path)
        conn.execute("DELETE FROM memory_item")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        assert store.counts()["memory_item"] == 0

        time.sleep(1.05)
        assert receipt.audit_ref in reproject_missing(audit=audit, store=store)
        replayed = store.get_memory_item(receipt.memory_id)
        assert replayed is not None
        assert replayed["expires_at"] == original["expires_at"], "the expiry survives a replay"
        assert replayed["created_at"] == original["created_at"]
        store.close()

    def test_no_sql_in_src_filters_on_the_column_yet(self) -> None:
        """The ruling's second half: stored, and acted on by nothing.

        A ``WHERE expires_at > now()`` anywhere in ``src/`` would be an expiry **policy** decided in a
        query — invisible to a caller, hiding rows a reader has no way to ask for, and arriving before
        ``docs/10`` §3.2's V1–V3 gates finalise at Stage 11.

        Asserted with an AST walk over string literals rather than a grep over lines, and the reason is
        measured rather than principled: a first version grepped lines and failed against a *docstring
        continuation line* in ``store/operational.py`` — the sentence explaining why there is no such
        clause, which names it in order to refuse it. A second version parsed but did not strip SQL
        comments, and failed against migration 0005's DDL for the same reason at one level down: its
        comment names ``expires_at`` in its list of what it deliberately did not add. Prose that names a
        thing is not code that does it, whether the prose is Python's or SQL's, and only a parse plus a
        comment strip can tell the two apart. That is F-23's lesson about a protocol growing a method,
        applied to a column growing a reader.

        Docstrings and ``--`` lines are excluded, and so is the writer's own ``payload.get("expires_at")``:
        this asserts that no **executable SQL** filters on the column, which is the claim the ruling makes.
        """
        root = Path(__file__).resolve().parents[1] / "src" / "nexus"
        offenders: list[str] = []
        sql_literals = 0
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            docstrings = {
                node.body[0].value
                for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if node in docstrings:
                    continue
                # Strip SQL comment lines before looking. A second version of this test flagged
                # `store/schema.py` twice, for the DDL of migrations 0004 and 0005 — not because either
                # filters on the column, but because 0005's comment *names* `expires_at` in its list of
                # what it deliberately did not add. A `--` line inside a SQL literal is prose exactly as
                # much as a docstring is, and `applied_statements` in `tests/test_schema_fidelity.py`
                # strips it for the same reason.
                text = "\n".join(
                    line for line in node.value.splitlines() if not line.strip().startswith("--")
                )
                if "SELECT" not in text.upper() and "WHERE" not in text.upper():
                    continue
                sql_literals += 1
                if "expires_at" in text:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
        assert offenders == [], offenders
        assert sql_literals > 20, (
            f"only {sql_literals} SQL literals were inspected, so the scan is not seeing the store's "
            "queries — a scan that inspects nothing passes, which is the silent-pass shape 8.6 had to fix"
        )
        # And the scan is not simply blind to the column name: the trading path has had an expiry since
        # Phase 2 and reads it in code, so the literal appears in src/ where a reader really exists.
        intent = (root / "execution" / "intent.py").read_text(encoding="utf-8")
        assert "expires_at" in intent and "def is_expired" in intent


class TestWhatThisWriterDoesNotDo:
    def test_nothing_in_src_calls_it_yet(self) -> None:
        """The same limitation Stage 8.2 recorded for ``record_evidence`` and 8.3 for ``open_dossier``,
        stated as a property of the tree rather than as a count that goes stale. Wiring it means deciding
        what the system should remember, and no ruling has made that decision."""
        root = Path(__file__).resolve().parents[1] / "src" / "nexus"
        callers = [
            path.relative_to(root).as_posix()
            for path in sorted(root.rglob("*.py"))
            if "intelligence/memory.py" not in path.as_posix()
            and "intelligence/__init__.py" not in path.as_posix()
            and "record_memory_item(" in path.read_text(encoding="utf-8")
        ]
        assert callers == [], callers

    def test_no_route_serves_a_memory_item(self) -> None:
        """Recordable and not readable over HTTP, which is why the beliefs ``view_gap`` stays open after
        this batch instead of closing. A route was not ruled into scope; ``docs/15`` §12 asks."""
        app = (Path(__file__).resolve().parents[1] / "src" / "nexus" / "api" / "app.py").read_text(
            encoding="utf-8"
        )
        assert "memory_items(" not in app
        assert "get_memory_item(" not in app
        assert "/v1/intelligence/memory" not in app

    def test_the_expiry_arrived_as_one_name_and_not_as_a_second_spelling(self) -> None:
        """Re-aimed by Stage 8.7, not deleted. This test used to assert that no expiry existed — F-18's
        second gap, which ``docs/15`` §5.3 made cheap and D-051's ruling 2 declined to spend early. D-054's
        ruling 4 ordered the column and D-055's ruling 4 scoped it, so the absence it pinned is now a
        presence. What is still true, and what the test is now about, is that the expiry arrived as **one**
        name on **one** table: a second spelling (``ttl``, ``expires_on``, ``valid_for_seconds``) would be
        two names for one clock, which is the mistake F-14 spent a batch separating."""
        parameters = set(inspect.signature(record_memory_item).parameters)
        assert "expires_at" in parameters, "D-055's ruling 4 ordered this column and it is here"
        assert {name for name in parameters if "expir" in name or "ttl" in name} == {"expires_at"}
        assert inspect.signature(record_memory_item).parameters["expires_at"].default is None, (
            "the ABSTAIN side: an unstated expiry is NULL, never a default computed from another clock"
        )
        receipt_fields = {item.name for item in fields(MemoryReceipt)}
        assert {"created_at", "valid_until", "confidence", "expires_at"} <= receipt_fields
        assert {name for name in receipt_fields if "expir" in name or "ttl" in name} == {"expires_at"}

    def test_the_expiry_is_not_folded_into_validity_of(self) -> None:
        """``validity_of`` reports the interval — the world's axis. An expiry is this system's axis, so
        adding it there would collapse the two clocks the migration comment separates, and every reader of
        that helper would inherit the collapse without seeing it."""
        returned = set(validity_of({"payload": {}}))
        assert returned == {
            "valid_from",
            "valid_until",
            VALIDITY_OPEN_ENDED_KEY,
            "change_conditions",
            EVIDENCE_IDS_KEY,
        }, returned
        assert not any("expir" in key for key in returned)

    def test_no_band_was_invented_and_that_is_f_24(self) -> None:
        """``docs/10`` §3.1 asks for confidence "as a band" and D-035 approved "beliefs as bands". A band is
        an interval on the confidence axis; the three columns this batch adds are on the time axis, so a
        belief still carries exactly one number. Recorded as F-24 rather than fixed, because two more
        columns are not this batch's ruling."""
        parameters = set(inspect.signature(record_memory_item).parameters)
        assert "confidence" in parameters
        assert not {
            name
            for name in parameters
            if any(part in name for part in ("band", "low", "high", "min", "max", "interval"))
        }, parameters
        receipt_fields = {item.name for item in fields(MemoryReceipt)}
        assert "confidence" in receipt_fields
        assert not {name for name in receipt_fields if "band" in name or "confidence_" in name}

    def test_confidence_is_an_input_to_no_gate(self) -> None:
        """``docs/12`` §1.3's law (A-02+A-08): no gate can be satisfied by a confidence value. The writer
        reads ``confidence`` to validate it and never to decide anything, and it spends no reason code —
        these are programmer errors at an internal boundary, not operational conditions."""
        writer = Path(__file__).resolve().parents[1] / "src" / "nexus" / "intelligence" / "memory.py"
        source = writer.read_text(encoding="utf-8")
        assert "from nexus.core.errors" not in source, "the writer imports no reason vocabulary"
        assert "RejectReason." not in source, "and spends no reason code"
        assert not any("MEMORY" in member.name for member in RejectReason)
        assert not any("BELIEF" in member.name for member in RejectReason)
        assert not any("CONFIDENCE" in member.name for member in RejectReason)

    def test_the_table_has_exactly_the_columns_the_migrations_declare(self, tmp_path: Path) -> None:
        """A writer that quietly grew the schema would make the ruling's scope unreadable from the tree.

        Re-aimed by Stage 8.7 from "the columns this batch added are the only ones it added", which named
        8.5's four: the set is now fifteen because ``0006_memory_expiry`` added ``expires_at``. The purpose
        is unchanged and is the reason this is an equality rather than a subset — a column that arrives
        without a ruling behind it turns this test red, and so does one that disappears."""
        audit, store = _durable(tmp_path)
        columns = {row[1] for row in _connect(tmp_path).execute("PRAGMA table_info(memory_item)")}
        assert columns == {
            "memory_id",
            "kind",
            "scope",
            "subject",
            "body",
            "created_at",
            "superseded_by",
            "cited_by",
            "confidence",
            "payload",
            "audit_ref",
            "valid_from",
            "valid_until",
            "change_conditions",
            "expires_at",
        }
        assert len(columns) == 15, sorted(columns)
        store.close()

    def test_kind_and_scope_are_free_text_because_no_vocabulary_is_declared(self, tmp_path: Path) -> None:
        """The schema says only ``DEFAULT 'OBSERVATION'`` and ``DEFAULT 'GLOBAL'``, and ``docs/10`` §3.1's
        "type tabs" names a control rather than a word list. This is the treatment ``evidence_ref.kind`` got
        in Stage 8.2: inventing an enum would put a plausible-looking vocabulary in front of a distinction
        nobody has drawn."""
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(
            audit=audit, store=store, body=BODY, kind="A_KIND_NOTHING_DECLARES", scope="A_SCOPE_NEITHER"
        )
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["kind"] == "A_KIND_NOTHING_DECLARES"
        assert row["scope"] == "A_SCOPE_NEITHER"
        store.close()

    def test_an_empty_kind_or_scope_falls_back_to_the_default_not_to_a_blank(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(audit=audit, store=store, body=BODY, kind="", scope="")
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["kind"] == MEMORY_KIND_OBSERVATION
        assert row["scope"] == MEMORY_SCOPE_GLOBAL
        store.close()

    def test_subject_is_not_checked_against_the_master_and_that_is_recorded(self, tmp_path: Path) -> None:
        """``subject`` is free text and no referent is declared for it — ``test_schema_fidelity.py``'s own
        fixture uses ``"BTC"``, not an instrument id. Validating it against the master would be a rule
        nobody wrote down, so an id that does not exist is stored as given."""
        audit, store = _durable(tmp_path)
        receipt = record_memory_item(audit=audit, store=store, body=BODY, subject="INS-NOT-REAL")
        row = store.get_memory_item(receipt.memory_id)
        assert row is not None
        assert row["subject"] == "INS-NOT-REAL"
        store.close()
