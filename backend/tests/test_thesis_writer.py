"""The Stage 9 writer: the candidate thesis, the seam it settled, and the three findings it measured.

D-056's ruling 3 opened Stage 9 and ordered F-26's seam settled inside it *as its first deliverable*,
because this is the first code that would write a ``decision`` row. So the seam is asserted here before
the writer's behaviour is: that ``save_decision`` was never a second seam but a delegator to
``save_decision_payload``; that no store method's signature moved; that the write-ahead path — and not a
direct store call — is what lands the row; and that ``OperationalStore`` now declares ``get_decision``,
the one single-row getter it lacked (F-29), which this writer's duplicate-id guard is the first code to
need.

Then the writer. What is asserted is not that a row lands but that the row that lands is the row the
audit event describes: F-28 measured that ``DecisionRecord.to_audit_payload()`` — the only other producer
of a decision payload in the repository, and one with zero call sites — withholds four keys
``save_decision_payload`` reads, and that a decision projected through it comes back from
``reproject_missing`` with ``created_at`` restamped by the replay's clock. Both halves of that are pinned
here, the defect and the remedy, so the remedy cannot be quietly dropped and the defect cannot be quietly
assumed fixed elsewhere.

And then the refusals. Three of the seven verbs and six of the twelve states are refused, each with its
own message and its own citation, because ``docs/12`` §1.3's A-08 puts the three verification gates
between intelligence and execution and ``docs/10`` §3.2 puts their definitions at Stage 11. Every refusal
is paired with the assertion that its neighbours are *permitted*, since a gate nobody has tested for
permissiveness is a gate nobody can tell from a bug. ``intent_id``, ``risk_check`` and ``expires_at`` are
absent from the signature as well as from the payload, and that absence is pinned against the signature
itself rather than only against behaviour — a parameter added later would be a scope change, and
``docs/15`` §14.8's discipline is that an absence should be a decision a reader can argue with.

F-30 is pinned last and is not fixed here: ``decision`` is the only table on this path with neither an
``uncertainty`` column nor a ``payload`` column, so the stage map's *evidence set + uncertainty* has
nowhere to put its second half. Adding one is a migration, and a migration is the artifact F-27 proved
this repository cannot take back.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
import textwrap
import time
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, SqliteAuditStore
from nexus.domain.decision import DecisionRecord, DecisionState, DecisionVerb
from nexus.instruments.projection import project_master
from nexus.instruments.registry import InstrumentRegistry
from nexus.instruments.seed import seed_master
from nexus.intelligence import thesis as thesis_module
from nexus.intelligence.evidence import record_evidence
from nexus.intelligence.thesis import (
    GATED_STATES,
    GATED_VERBS,
    THESIS_EVENT_TYPE,
    THESIS_PREFIX,
    THESIS_STATES,
    THESIS_VERBS,
    ThesisReceipt,
    record_thesis,
)
from nexus.store.operational import SqliteOperationalStore
from nexus.store.writeahead import PROJECTABLE, project, reproject_missing, write_with_audit

RATIONALE = "Perp basis on INS-BTC-USDT runs wide into the US session and narrows at the London close."
UNCERTAIN_CODE = "EVIDENCE_ONE_VENUE_DEEP"
#: ``tests/test_repo_hygiene.py:33-35``'s convention: resolved from this file, never from the cwd, so a
#: suite run from anywhere in the repository reads the same tree it asserts about.
BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
SOURCE_ROOT = BACKEND / "src"
MIGRATIONS = BACKEND / "migrations"
DESIGN = REPO_ROOT / "design"

OBSERVED = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 1, 9, 35, tzinfo=UTC)


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


def _connect(tmp_path: Path) -> sqlite3.Connection:
    # isolation_level=None so a PRAGMA is not swallowed by an implicit transaction.
    return sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)


def _evidence(audit: AuditLog, store: SqliteOperationalStore, count: int = 2) -> tuple[str, ...]:
    """Real evidence rows, because a citation is checked against the store rather than assumed."""
    return tuple(
        record_evidence(
            audit=audit,
            store=store,
            source="okx",
            observed_at=OBSERVED,
            retrieved_at=RETRIEVED,
            kind="DATA",
            locator=f"okx:perp-basis:{index}",
        ).evidence_id
        for index in range(count)
    )


def _record(audit: AuditLog, store: SqliteOperationalStore, **overrides: Any) -> ThesisReceipt:
    base: dict[str, Any] = {
        "rationale": RATIONALE,
        "reason_codes": (UNCERTAIN_CODE,),
    }
    base.update(overrides)
    return record_thesis(audit=audit, store=store, **base)


def _row(tmp_path: Path, decision_id: str) -> dict[str, Any]:
    conn = _connect(tmp_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM decision WHERE decision_id = ?", (decision_id,)).fetchall()
        return dict(rows[0]) if rows else {}
    finally:
        conn.close()


def _columns(tmp_path: Path, table: str) -> tuple[str, ...]:
    conn = _connect(tmp_path)
    try:
        return tuple(str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})"))
    finally:
        conn.close()


def _body_of(method: Any) -> list[str]:
    """A method's statements as normalised source, without its signature and without its docstring.

    Via AST rather than line filtering, so a docstring cannot be mistaken for a statement and the
    assertion survives a reformat. ``ast.unparse`` normalises quoting, which is what makes comparing a
    body to a literal list of source lines safe at all.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    statements = [
        node
        for node in function.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    return [ast.unparse(node) for node in statements]


def _protocol_methods() -> set[str]:
    """The methods ``OperationalStore`` declares, read from source.

    Not from ``__protocol_attrs__``, which arrived in 3.12 and is an empty set on the 3.11 this suite runs
    on — a check built on it would have passed by asserting that nothing is declared.
    """
    tree = ast.parse((SOURCE_ROOT / "nexus/store/operational.py").read_text(encoding="utf-8"))
    protocol = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OperationalStore")
    return {item.name for item in protocol.body if isinstance(item, ast.FunctionDef)}


def _definitions_of(names: set[str]) -> dict[str, int]:
    """How many classes in the tree define each name — the scan F-23's blind spot needs."""
    counts: dict[str, int] = dict.fromkeys(names, 0)
    scanned = 0
    for root in (SOURCE_ROOT, BACKEND / "tests"):
        for path in sorted(root.rglob("*.py")):
            scanned += 1
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name in counts:
                            counts[item.name] += 1
    assert scanned > 60, f"only {scanned} files scanned — the scan cannot see the tree it asserts about"
    return counts


def _docstring() -> str:
    """The module docstring unwrapped, so a phrase split across lines still matches."""
    return " ".join((thesis_module.__doc__ or "").split())


def _signature_docstring() -> str:
    """``record_thesis``'s own docstring unwrapped — where the three omitted parameters justify themselves.

    Separate from :func:`_docstring` because the two docstrings say different things: the module's states
    the batch's findings, the function's states what a caller may not pass. Asserting a phrase against the
    wrong one passes nothing and fails misleadingly.
    """
    return " ".join((thesis_module.record_thesis.__doc__ or "").split())


class TestTheSeamIsSettledAndNothingMoved:
    """F-26's answer, asserted before the writer's behaviour because ruling 3 ordered it first."""

    def test_save_decision_was_never_a_second_seam(self) -> None:
        """The delegator is one line, so the seam was a question about a choice that did not exist.

        F-26 asked whether Stage 9 should write through the domain-object methods or the payload methods,
        as though they were two seams. ``save_decision``'s *last* statement is a call to
        ``save_decision_payload``, and the three before it only turn a ``DecisionRecord`` into the mapping
        that call takes, so there is one seam and two doors onto it and nothing to choose between.

        Recorded here as four statements and not one because the first draft of this batch called it a
        one-line delegator on the strength of reading only its last line. The distinction matters: it is
        ``asdict(record)`` that makes the domain door carry all eighteen fields while
        ``to_audit_payload()`` carries fourteen, which is F-28.
        """
        assert _body_of(SqliteOperationalStore.save_decision) == [
            "payload = asdict(record)",
            "payload['state'] = record.state.value",
            "payload['verb'] = record.verb.value",
            "self.save_decision_payload(payload, audit_ref=audit_ref)",
        ], "save_decision no longer ends in the payload method, so the seam has become two"

    def test_the_intent_and_approval_doors_have_the_same_shape(self) -> None:
        """All three pairs, so the seam's shape is a property of the store and not of one method."""
        shapes = {
            "save_decision": "save_decision_payload",
            "save_intent": "save_intent_payload",
            "save_approval": "save_approval_payload",
        }
        lengths: dict[str, int] = {}
        for name, sibling in shapes.items():
            body = _body_of(getattr(SqliteOperationalStore, name))
            lengths[name] = len(body)
            # The two properties all three share, and the only two the seam's answer rests on: the domain
            # object is flattened with `asdict`, so the door carries every field, and the last statement
            # is the payload sibling, so there is one write and not two.
            assert any("asdict(" in statement for statement in body), (name, body)
            assert body[-1].startswith(f"self.{sibling}("), (name, body)
            assert body[-1].endswith("audit_ref=audit_ref)"), (name, body)
        # Not the same shape, and pinning one body for all three would have been a false measurement:
        # `save_decision` converts two enums, `save_intent` adds a digest, `save_approval` inlines the
        # `asdict` into the call itself and is a genuine one-liner.
        assert lengths == {"save_decision": 4, "save_intent": 3, "save_approval": 1}, lengths

    def test_no_store_signature_moved(self) -> None:
        """The posture F-26 was settled on costs nothing, and this is the assertion that it did.

        Pinned as exact strings because the point is the *shape*: the domain door takes the dataclass,
        the payload door takes a mapping, and both take one keyword-only audit ref. A batch that later
        widens either would be moving the seam F-26 closed, and this is where that shows up first.
        """

        def domain_door(kind: str, argument: str) -> str:
            return f"(self, {argument}: '{kind}', *, audit_ref: 'str | None' = None) -> 'None'"

        payload_door = "(self, payload: 'Mapping[str, Any]', *, audit_ref: 'str | None' = None) -> 'None'"
        expected = {
            "save_decision": domain_door("DecisionRecord", "record"),
            "save_intent": domain_door("TradeIntent", "intent"),
            "save_approval": domain_door("ApprovalRecord", "approval"),
            "save_decision_payload": payload_door,
            "save_intent_payload": payload_door,
            "save_approval_payload": payload_door,
        }
        actual = {n: str(inspect.signature(getattr(SqliteOperationalStore, n))) for n in expected}
        assert actual == expected, {n: (expected[n], actual[n]) for n in expected if expected[n] != actual[n]}

    def test_the_seam_has_two_full_implementations_and_two_forwarding_wrappers(self) -> None:
        """F-23's blind spot, re-scanned — and the reason declaring ``get_decision`` broke nothing.

        The scan counts *definitions across all classes* rather than searching for subclasses: a
        ``Protocol`` is conformed to structurally, so a fake implementing every method would never appear
        in a subclass search. Two of these names are defined twice, the protocol's declaration and the
        SQLite implementation. ``save_decision_payload`` is defined three times, and the third is the
        reason an earlier draft of this batch recorded the wrong answer: it claimed there were no
        structural fakes in the tree at all.
        """
        assert _definitions_of(
            {
                "save_decision",
                "save_decision_payload",
                "save_intent",
                "save_intent_payload",
                "save_approval",
                "save_approval_payload",
                "get_decision",
            }
        ) == {
            "save_decision": 2,
            "save_decision_payload": 3,
            "save_intent": 2,
            "save_intent_payload": 2,
            "save_approval": 2,
            "save_approval_payload": 2,
            "get_decision": 2,
        }

    def test_the_third_definition_is_a_wrapper_that_forwards_what_it_does_not_override(self) -> None:
        """Which is what makes the count above safe rather than merely observed.

        ``FlakyStore`` and ``HaltBlindStore`` each override exactly one method and forward every other
        attribute through ``__getattr__`` to a real ``SqliteOperationalStore``, so a method the protocol
        grows resolves through them without either being edited. A fake that enumerated the protocol
        instead would have to be updated, and a batch that forgot to would fail in a module the offline
        suite skips — F-23 exactly.
        """
        tree = ast.parse((BACKEND / "tests/test_boot_recovery.py").read_text(encoding="utf-8"))
        wrappers = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name in {"FlakyStore", "HaltBlindStore"}
        ]
        assert len(wrappers) == 2, [w.name for w in wrappers]
        for wrapper in wrappers:
            names = {i.name for i in wrapper.body if isinstance(i, ast.FunctionDef)}
            assert "__getattr__" in names, f"{wrapper.name} does not forward"
            assert len(names - {"__init__", "__getattr__"}) == 1, (wrapper.name, sorted(names))

    def test_the_event_type_was_already_registered(self) -> None:
        """This writer adds an event type to no registry; it supplies a producer a projection waited for."""
        assert PROJECTABLE[THESIS_EVENT_TYPE] == "decision"

    def test_the_writer_reads_the_store_and_never_writes_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Audit first, projection second, and never a direct ``store.save_*`` from the writer.

        A writer that called the store itself would leave the audit chain and the row able to disagree,
        which is the hole L-2 and ``reproject_missing`` exist to close. Asserted against the writer's own
        AST rather than by patching the store, because patching the store cannot tell the writer's call
        from the projection's — ``project()`` calls ``save_decision_payload`` on purpose, and that call is
        the seam working rather than being bypassed.
        """
        tree = ast.parse((SOURCE_ROOT / "nexus/intelligence/thesis.py").read_text(encoding="utf-8"))
        touched = sorted(
            {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "store"
            }
        )
        assert touched == ["get_decision", "get_evidence_ref", "instruments"], touched
        assert not [name for name in touched if name.startswith("save_")]

        audit, store = _booted(tmp_path)
        seen: list[str] = []
        real = thesis_module.write_with_audit

        def spy(**kwargs: Any) -> Any:
            seen.append(str(kwargs["event_type"]))
            return real(**kwargs)

        monkeypatch.setattr(thesis_module, "write_with_audit", spy)
        receipt = _record(audit, store)
        assert seen == [THESIS_EVENT_TYPE], seen
        assert receipt.decision_id and _row(tmp_path, receipt.decision_id)

    def test_f29_get_decision_is_declared_on_the_protocol(self) -> None:
        """The one single-row getter the protocol lacked, and the guard that needed it.

        ``get_dossier``, ``get_evidence_ref``, ``get_memory_item`` and ``get_intent`` are all declared and
        ``get_decision`` was not, although the implementation has existed since Phase 2. A fake conforming
        to the protocol would have type-checked and raised ``AttributeError`` at the first guard.
        """
        declared = _protocol_methods()
        for name in ("get_decision", "get_dossier", "get_evidence_ref", "get_memory_item", "get_intent"):
            assert name in declared, f"{name} is not declared on OperationalStore"
        assert len(declared) == 37, f"the protocol declares {len(declared)} methods, not the 36 it had "
        "before F-29's addition"

    def test_f29_the_declared_getter_answers_the_guard_it_was_declared_for(self, tmp_path: Path) -> None:
        """Declaring a method that returns the wrong thing would be worse than not declaring it."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store)
        assert store.get_decision(receipt.decision_id)["verb"] == DecisionVerb.ABSTAIN.value
        assert store.get_decision("DEC-NOT-MINTED") is None


class TestThePayloadCarriesWhatTheProjectionReads:
    """F-28: the defect, the remedy, and the pinned test that makes the defect deliberate in one place."""

    def test_the_event_carries_every_key_the_projection_reads(self, tmp_path: Path) -> None:
        """Nineteen columns, one of which the projection supplies, so eighteen must ride in the event."""
        audit, store = _booted(tmp_path)
        captured: dict[str, Any] = {}
        real = write_with_audit

        def spy(**kwargs: Any) -> Any:
            captured.update(kwargs["payload"])
            return real(**kwargs)

        import nexus.intelligence.thesis as thesis_module

        original = thesis_module.write_with_audit
        thesis_module.write_with_audit = spy  # type: ignore[assignment]
        try:
            _record(audit, store)
        finally:
            thesis_module.write_with_audit = original  # type: ignore[assignment]

        projected = _columns(tmp_path, "decision")
        assert len(projected) == 19
        missing = [c for c in projected if c not in captured and c != "audit_ref"]
        assert not missing, f"the event omits {missing}, so the projection falls back to its own defaults"

    def test_a_replay_reproduces_the_row_byte_for_byte(self, tmp_path: Path) -> None:
        """The crash between the audit entry and the row, and the row that comes back is the same row.

        This is the assertion ``to_audit_payload()`` fails: measured, a decision projected through it
        returns from ``reproject_missing`` with ``created_at`` and ``updated_at`` restamped by the replay's
        clock, because the payload carries neither and the projection falls back to ``iso_utc(utc_now())``.
        """
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store, confidence="0.42")
        before = _row(tmp_path, receipt.decision_id)
        assert before["rationale"] == RATIONALE, "the rationale did not reach the row it is the only home for"

        conn = _connect(tmp_path)
        conn.execute("DELETE FROM decision")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        time.sleep(1.05)

        replayed = reproject_missing(audit=audit, store=store)
        assert receipt.audit_ref in replayed, replayed
        after = _row(tmp_path, receipt.decision_id)
        assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        assert after["created_at"] == receipt.created_at

    def test_the_remedy_is_the_comment_memory_py_already_carries(self) -> None:
        """Two writers, one rule, and the rule is written down where the first of them learned it."""
        memory = (SOURCE_ROOT / "nexus/intelligence/memory.py").read_text(encoding="utf-8")
        thesis = (SOURCE_ROOT / "nexus/intelligence/thesis.py").read_text(encoding="utf-8")
        assert "so a replay reproduces the row it first wrote" in memory
        assert "so a replay reproduces the row it first wrote" in thesis

    def test_f28_the_domain_payload_still_lacks_what_the_projection_reads(self) -> None:
        """Pinned as a live finding, not fixed: ``test_core_guarantees.py:498`` rules out the easy fix.

        ``rationale`` is withheld on purpose and a test asserts it, so F-28 cannot be closed by adding the
        four keys. What can be said is exactly which four the projection reads and the payload omits.
        """
        payload = DecisionRecord(rationale="x", confidence=0.5).to_audit_payload()
        read_by_projection = ("rationale", "risk_check", "created_at", "updated_at")
        assert [k for k in read_by_projection if k not in payload] == list(read_by_projection)
        assert len(payload) == 14

    def test_f28_projected_from_the_domain_payload_the_row_is_not_reproducible(self, tmp_path: Path) -> None:
        """The measurement behind the finding, kept as a test so the finding cannot go stale silently.

        Deliberately drives ``project()`` rather than ``record_thesis``: this is what a caller holding a
        ``DecisionRecord`` would do, and it is the path Stage 9's writer exists so that nobody has to.
        """
        audit, store = _booted(tmp_path)
        payload = DecisionRecord(
            rationale="the concise rationale the domain object will not audit",
            reason_codes=("C",),
        ).to_audit_payload()
        entry = write_with_audit(
            audit=audit, store=store, event_type=THESIS_EVENT_TYPE, payload=payload, actor="INTELLIGENCE"
        )
        first = _row(tmp_path, str(payload["decision_id"]))
        assert first["rationale"] == "", "F-28's first half has changed: the rationale now survives"
        assert first["risk_check"] == "{}"

        conn = _connect(tmp_path)
        conn.execute("DELETE FROM decision")
        conn.execute("DELETE FROM op_projection")
        conn.close()
        time.sleep(1.05)
        assert entry.record_id in reproject_missing(audit=audit, store=store)
        second = _row(tmp_path, str(payload["decision_id"]))
        differing = {k for k in first if first[k] != second[k]}
        assert differing == {"created_at", "updated_at"}, differing

    def test_the_writer_does_not_call_the_domain_payload_at_all(self) -> None:
        """Because the pinned refusal above and this writer's completeness cannot both hold otherwise."""
        source = (SOURCE_ROOT / "nexus/intelligence/thesis.py").read_text(encoding="utf-8")
        assert "to_audit_payload" in source, "F-28's docstring cites it, so the citation has gone stale"
        tree = ast.parse(source)
        called = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        assert "to_audit_payload" not in called, "the writer builds its payload from the domain object"


class TestTheGatedVerbsAreRefusedSeparately:
    """Three refusals, three laws, three messages — never folded into one."""

    @pytest.mark.parametrize("verb", [v.value for v in GATED_VERBS])
    def test_the_gated_verb_is_refused(self, tmp_path: Path, verb: str) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match=f"verb={verb} is refused at Stage 9"):
            _record(audit, store, verb=verb)

    def test_each_refusal_cites_its_own_law_and_not_a_shared_one(self, tmp_path: Path) -> None:
        """ACCEPT cites A-08, REDUCE cites A-02 and the risk engine, EXIT cites the absent position."""
        audit, store = _booted(tmp_path)
        expected = {
            "ACCEPT": "A-08",
            "REDUCE": "risk engine",
            "EXIT": "nothing is open",
        }
        seen: dict[str, str] = {}
        for verb, needle in expected.items():
            with pytest.raises(ValueError) as excinfo:
                _record(audit, store, verb=verb)
            message = str(excinfo.value)
            assert needle in message, f"{verb}'s refusal does not cite {needle}: {message}"
            seen[verb] = message
        assert len(set(seen.values())) == 3, "the three refusals share a message, so they share a reason"

    @pytest.mark.parametrize("verb", [v.value for v in THESIS_VERBS])
    def test_the_permitted_verb_is_accepted(self, tmp_path: Path, verb: str) -> None:
        """Permissiveness is asserted too: four of the seven verbs are proposals, not gate outcomes."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store, verb=verb)
        assert receipt.verb == verb
        assert _row(tmp_path, receipt.decision_id)["verb"] == verb

    def test_the_two_sets_partition_the_vocabulary(self) -> None:
        """Seven words, four permitted, three refused, none in both and none in neither."""
        assert set(THESIS_VERBS) | set(GATED_VERBS) == set(DecisionVerb)
        assert not set(THESIS_VERBS) & set(GATED_VERBS)
        assert len(THESIS_VERBS) == 4 and len(GATED_VERBS) == 3

    def test_a_word_outside_the_vocabulary_is_refused_differently(self, tmp_path: Path) -> None:
        """Not a gated verb — an unrecognised one, which is a different mistake with a different message."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="verb must be one of") as excinfo:
            _record(audit, store, verb="MAYBE")
        assert "is refused at Stage 9" not in str(excinfo.value)

    def test_the_enum_member_and_its_string_are_the_same_call(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        assert _record(audit, store, verb=DecisionVerb.WAIT).verb == _record(audit, store, verb="WAIT").verb


class TestTheGatedStatesAreRefused:
    """Six states assert something downstream happened; Stage 9 is upstream of all of them."""

    @pytest.mark.parametrize("state", [s.value for s in GATED_STATES])
    def test_the_gated_state_is_refused(self, tmp_path: Path, state: str) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match=f"state={state} is refused at Stage 9"):
            _record(audit, store, state=state)

    def test_expired_is_refused_for_a_different_reason_than_the_other_five(self, tmp_path: Path) -> None:
        """The five are past A-08's gates; EXPIRED needs a reader Stage 8.7 measured as absent."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, state="EXPIRED")
        message = str(excinfo.value)
        assert "expiry reader" in message
        assert "Stage 8.7" in message

    @pytest.mark.parametrize("state", [s.value for s in THESIS_STATES])
    def test_the_permitted_state_is_accepted(self, tmp_path: Path, state: str) -> None:
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store, state=state)
        assert receipt.state == state
        assert _row(tmp_path, receipt.decision_id)["state"] == state

    def test_the_two_sets_partition_the_states(self) -> None:
        assert set(THESIS_STATES) | set(GATED_STATES) == set(DecisionState)
        assert not set(THESIS_STATES) & set(GATED_STATES)
        assert len(THESIS_STATES) == 6 and len(GATED_STATES) == 6

    def test_an_unrecognised_state_is_refused_differently(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="state must be one of"):
            _record(audit, store, state="PENDING")


class TestTheParentGuardsAreInTheWriter:
    """``PRAGMA foreign_keys`` is deliberately off, so every parent is checked here or nowhere."""

    def test_a_dangling_instrument_is_refused(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="is not in the system of record") as excinfo:
            _record(audit, store, instrument_id="INS-NOT-MINTED")
        assert "PRAGMA foreign_keys" in str(excinfo.value)

    def test_the_refusal_names_what_the_master_actually_holds(self, tmp_path: Path) -> None:
        """F-25's lesson: a guard that says 'not found' tells a caller less than the writer knows."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            _record(audit, store, instrument_id="INS-NOT-MINTED")
        for held in ("INS-BTC-USDT", "INS-BTC-USDT-USDT", "INS-EUR-USD"):
            assert held in str(excinfo.value)

    def test_nothing_can_be_recorded_before_the_master_is_projected(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        with pytest.raises(ValueError, match="which holds 0"):
            _record(audit, store, instrument_id="INS-BTC-USDT")

    def test_instrument_id_none_is_allowed(self, tmp_path: Path) -> None:
        """A thesis about no instrument in particular is a statement, and None is how it is made."""
        audit, store = _booted(tmp_path)
        assert _record(audit, store).instrument_id is None

    def test_an_empty_instrument_id_is_refused_as_neither(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="an empty string is neither"):
            _record(audit, store, instrument_id="")

    def test_a_whitespace_instrument_id_is_refused_as_neither(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="an empty string is neither"):
            _record(audit, store, instrument_id="   ")

    def test_a_dangling_evidence_ref_is_refused(self, tmp_path: Path) -> None:
        """No foreign key reaches into a JSON list, so this is the only place a citation is checked."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match=r"evidence_refs cites evidence 'EV-NOT-RECORDED'"):
            _record(audit, store, evidence_refs=("EV-NOT-RECORDED",))

    def test_a_dangling_counter_evidence_ref_is_refused_and_says_which_column(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="counter_evidence_refs cites evidence") as excinfo:
            _record(audit, store, counter_evidence_refs=("EV-NOT-RECORDED",))
        assert str(excinfo.value).startswith("counter_evidence_refs cites")

    def test_an_empty_citation_is_not_the_same_as_no_citation(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="got an empty string, which cites nothing"):
            _record(audit, store, evidence_refs=("",))
        assert _record(audit, store, evidence_refs=()).evidence_refs == ()

    def test_real_evidence_on_both_sides_is_accepted(self, tmp_path: Path) -> None:
        """The point of the guard: two distinct sources may disagree, and that is what §3.1 renders."""
        audit, store = _booted(tmp_path)
        support, counter = _evidence(audit, store, 2)
        receipt = _record(audit, store, evidence_refs=(support,), counter_evidence_refs=(counter,))
        assert receipt.evidence_refs == (support,)
        assert receipt.counter_evidence_refs == (counter,)
        row = _row(tmp_path, receipt.decision_id)
        assert row["evidence_refs"] == f'["{support}"]'
        assert row["counter_evidence_refs"] == f'["{counter}"]'

    def test_one_source_on_both_sides_is_refused(self, tmp_path: Path) -> None:
        """Not a contradiction the system can hold: it renders as a source arguing with itself."""
        audit, store = _booted(tmp_path)
        (both,) = _evidence(audit, store, 1)
        with pytest.raises(ValueError, match="cited as both evidence and counter-evidence") as excinfo:
            _record(audit, store, evidence_refs=(both,), counter_evidence_refs=(both,))
        assert both in str(excinfo.value)
        assert "contradicts" in str(excinfo.value)

    def test_the_refusal_names_every_id_on_both_sides_and_not_just_the_first(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        first, second, third = _evidence(audit, store, 3)
        with pytest.raises(ValueError) as excinfo:
            _record(
                audit,
                store,
                evidence_refs=(first, second),
                counter_evidence_refs=(second, third),
            )
        message = str(excinfo.value)
        assert second in message
        assert first not in message and third not in message

    def test_a_duplicated_citation_on_one_side_is_kept(self, tmp_path: Path) -> None:
        """Not deduplicated, because a source cited twice is a claim the caller made twice."""
        audit, store = _booted(tmp_path)
        (one,) = _evidence(audit, store, 1)
        receipt = _record(audit, store, evidence_refs=(one, one))
        assert receipt.evidence_refs == (one, one)

    def test_an_unrecognised_venue_is_refused(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="venue must be one of"):
            _record(audit, store, venue="NOT-A-VENUE")

    def test_a_real_venue_and_no_venue_are_both_accepted(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        assert _record(audit, store, venue="OKX").venue == "OKX"
        assert _record(audit, store).venue is None

    def test_an_existing_decision_id_cannot_be_recorded_again(self, tmp_path: Path) -> None:
        """F-29's guard: recording is not editing, and the store's INSERT OR REPLACE would not say so."""
        audit, store = _booted(tmp_path)
        first = _record(audit, store)
        with pytest.raises(ValueError, match="already exists, and recording a thesis is not editing"):
            _record(audit, store, decision_id=first.decision_id, rationale="a restated thesis")
        assert _row(tmp_path, first.decision_id)["rationale"] == RATIONALE

    def test_a_minted_id_is_not_checked_against_the_store(self, tmp_path: Path) -> None:
        """The guard is about a *claimed* id; a fresh one cannot collide and is not queried for."""
        audit, store = _booted(tmp_path)
        assert _record(audit, store).decision_id.startswith(f"{THESIS_PREFIX}-")

    def test_an_empty_reason_code_is_refused(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="reason_codes must hold non-empty codes"):
            _record(audit, store, reason_codes=("REAL", "  "))

    def test_duplicate_reason_codes_are_kept_in_order(self, tmp_path: Path) -> None:
        """``DecisionRecord.transition`` appends without deduplicating, so neither does this writer."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store, reason_codes=("B", "A", "B"))
        assert receipt.reason_codes == ("B", "A", "B")


class TestAbstainIsTheDefaultRecordAndNotAFallback:
    """``build_board52.py:73`` makes ABSTAIN the default; P-2's text makes it a complete outcome."""

    def test_the_defaults_are_the_abstain_side(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store)
        assert receipt.verb == DecisionVerb.ABSTAIN.value
        assert receipt.state == DecisionState.PROPOSED.value
        assert receipt.evidence_refs == () and receipt.counter_evidence_refs == ()
        assert receipt.confidence is None
        assert receipt.instrument_id is None and receipt.venue is None

    def test_the_defaults_are_what_the_signature_says_and_not_what_the_schema_says(self) -> None:
        """The schema has no default for ``verb`` at all; the ABSTAIN default is this writer's.

        Every ``DEFAULT 'ABSTAIN'`` in the repository is on a ``stance`` column — ``schema.py:291``,
        ``schema.py:373`` and ``migrations/0002_memory.sql:50`` — and ``decision.verb`` has none in either
        DDL. So a thesis written without one would project ``_text(payload.get("verb")) or "ABSTAIN"``,
        the projection's own fallback, which is exactly the "fallback not default" this test separates.
        """
        signature = inspect.signature(record_thesis)
        assert signature.parameters["verb"].default is DecisionVerb.ABSTAIN
        assert signature.parameters["state"].default is DecisionState.PROPOSED
        ddl = (SOURCE_ROOT / "nexus/store/schema.py").read_text(encoding="utf-8")
        assert "verb" in ddl
        mirror = (MIGRATIONS / "0001_core.sql").read_text(encoding="utf-8")
        for line in mirror.splitlines():
            if line.strip().startswith("verb"):
                assert "DEFAULT" not in line.upper(), line

    def test_abstain_without_a_reason_code_is_refused(self, tmp_path: Path) -> None:
        """A complete outcome has to say what it is complete about — and F-30 is why a code is asked."""
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError, match="verb=ABSTAIN needs at least one reason code") as excinfo:
            record_thesis(audit=audit, store=store, rationale=RATIONALE)
        assert "F-30" in str(excinfo.value)

    @pytest.mark.parametrize("verb", ["REJECT", "WAIT", "ESCALATE"])
    def test_a_non_abstain_verb_needs_no_code(self, tmp_path: Path, verb: str) -> None:
        """The rule is about abstention, not about reason codes in general."""
        audit, store = _booted(tmp_path)
        assert record_thesis(audit=audit, store=store, rationale=RATIONALE, verb=verb).reason_codes == ()

    def test_abstain_with_a_code_is_accepted(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        assert _record(audit, store).reason_codes == (UNCERTAIN_CODE,)

    def test_the_rationale_is_required_and_stripped(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        for empty in ("", "   ", "\n\t "):
            with pytest.raises(ValueError, match="a thesis needs a rationale"):
                record_thesis(audit=audit, store=store, rationale=empty, reason_codes=("C",))
        receipt = _record(audit, store, rationale=f"  {RATIONALE}  ")
        assert receipt.rationale == RATIONALE
        assert _row(tmp_path, receipt.decision_id)["rationale"] == RATIONALE

    def test_the_rationale_refusal_names_the_column_that_makes_it_the_only_home(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            record_thesis(audit=audit, store=store, rationale="", reason_codes=("C",))
        assert "no payload column" in str(excinfo.value)


class TestConfidenceIsAnInputAndNeverAGate:
    """A-02: confidence is never a satisfied requirement. Nothing here lets it become one."""

    def test_confidence_does_not_move_the_verb_or_the_state(self, tmp_path: Path) -> None:
        """The highest confidence the portable target can hold still records an abstention."""
        audit, store = _booted(tmp_path)
        low = _record(audit, store, confidence="0")
        high = _record(audit, store, confidence="9.99999")
        assert low.verb == high.verb == DecisionVerb.ABSTAIN.value
        assert low.state == high.state == DecisionState.PROPOSED.value

    def test_a_confidence_is_not_required(self, tmp_path: Path) -> None:
        """A thesis with no number is not a weaker thesis; the column is nullable in both DDLs."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store)
        assert receipt.confidence is None
        assert _row(tmp_path, receipt.decision_id)["confidence"] is None

    @pytest.mark.parametrize("value", ["10", "47", "-12.5", "1e-6", "0.999999"])
    def test_a_value_the_portable_target_cannot_hold_is_refused(self, tmp_path: Path, value: str) -> None:
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError):
            _record(audit, store, confidence=value)

    @pytest.mark.parametrize("value", ["0", "1", "0.42", "-0.4", "9.99999", "1.1"])
    def test_a_value_it_can_hold_is_accepted_unbounded(self, tmp_path: Path, value: str) -> None:
        """D-054 ruled confidence unbounded; the ceiling is the target's magnitude, not a range rule."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store, confidence=value)
        assert receipt.confidence is not None

    def test_the_boundary_check_is_the_one_stage_8_5_built(self) -> None:
        """One opinion about ``NUMERIC(6, 5)``, not two — and ``decision`` declares the same type."""
        import nexus.intelligence.thesis as thesis_module

        assert thesis_module.confidence_text.__module__ == "nexus.intelligence.memory"
        mirror = (MIGRATIONS / "0001_core.sql").read_text(encoding="utf-8").splitlines()
        decision_at = next(
            i for i, line in enumerate(mirror) if "CREATE TABLE IF NOT EXISTS decision" in line
        )
        confidence_line = next(line for line in mirror[decision_at:] if "confidence" in line)
        assert "NUMERIC(6, 5)" in confidence_line, confidence_line

    def test_a_float_is_accepted_and_stringified_before_it_is_checked(self, tmp_path: Path) -> None:
        """``DecisionRecord.confidence`` is ``float | None``, so a caller holding one should not stringify."""
        audit, store = _booted(tmp_path)
        assert _record(audit, store, confidence=0.42).confidence == "0.42"
        with pytest.raises(ValueError):
            _record(audit, store, confidence=1e-6)

    def test_an_int_is_accepted(self, tmp_path: Path) -> None:
        audit, store = _booted(tmp_path)
        assert _record(audit, store, confidence=1).confidence == "1"


class TestTheColumnsThisWriterIsNotRuledInto:
    """Three columns exist, none is a parameter, and the omission is pinned against the signature."""

    def test_the_signature_has_no_intent_id_no_risk_check_and_no_expires_at(self) -> None:
        """Absent from the signature, not accepted and ignored — so adding one is a visible scope change."""
        parameters = set(inspect.signature(record_thesis).parameters)
        for absent in ("intent_id", "risk_check", "expires_at", "payload", "uncertainty"):
            assert absent not in parameters, f"{absent} became a parameter, which is a scope change"

    def test_the_columns_still_exist_and_still_take_their_own_defaults(self, tmp_path: Path) -> None:
        """The columns are not removed — a writer declining to fill one is not a schema that lost it."""
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store)
        row = _row(tmp_path, receipt.decision_id)
        assert row["intent_id"] is None
        assert row["risk_check"] == "{}"
        assert row["expires_at"] is None
        assert len(row) == 19

    def test_the_receipt_echoes_all_three_so_the_omission_is_visible_to_the_caller(
        self, tmp_path: Path
    ) -> None:
        audit, store = _booted(tmp_path)
        receipt = _record(audit, store)
        assert receipt.intent_id is None
        assert dict(receipt.risk_check) == {}
        assert receipt.expires_at is None
        names = {f.name for f in fields(ThesisReceipt)}
        assert {"intent_id", "risk_check", "expires_at"} <= names

    def test_risk_check_is_the_risk_engines_and_a02_keeps_intelligence_out_of_it(self) -> None:
        """The reason the column is not a parameter, written where a reader will look for it."""
        assert "risk_check`` because it is the risk engine's column and A-02" in _signature_docstring()

    def test_expires_at_is_declined_for_the_reason_stage_8_7_measured(self) -> None:
        """8.7 added an expiry column with no reader and published it as inert; this does not repeat it."""
        assert "Stage 8.7 measured what an expiry column with no reader is worth" in _signature_docstring()

    def test_no_reader_compares_a_stored_expiry_column(self) -> None:
        """The claim the refusal rests on, narrowed twice — to what is true, and to what is a comparison.

        Expiry readers *do* exist in ``src``: ``execution/intent.py`` compares ``TradeIntent.expires_at``
        twice, in ``is_expired`` and in the approval binding. An earlier draft of this test asserted that
        none existed anywhere and was wrong. What is true is narrower and is what the refusal rests on —
        nothing compares an expiry *read back from the store* against a clock, so ``memory_item.expires_at``,
        which Stage 8.7 added, is inert, and ``decision.expires_at`` would be too.

        Restricted to ordering operators because ``memory.py:380`` compares ``expires_at is not None``,
        which is the writer deciding whether an expiry was supplied and not a reader deciding whether one
        has passed. Counting that as a reader would have made this test pass for the wrong reason.
        """
        ordering = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
        readers = []
        for path in sorted(SOURCE_ROOT.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text)):
                if not isinstance(node, ast.Compare) or not any(isinstance(op, ordering) for op in node.ops):
                    continue
                if "expires_at" in (ast.get_source_segment(text, node) or ""):
                    readers.append(f"{path.name}:{node.lineno}")
        assert {reader.split(":")[0] for reader in readers} == {"intent.py"}, readers


class TestF30TheUncertaintyHasNowhereToLive:
    """Measured, recorded, and asked — not fixed, because the fix is a migration."""

    def test_decision_has_neither_an_uncertainty_column_nor_a_payload_column(self, tmp_path: Path) -> None:
        _booted(tmp_path)
        columns = _columns(tmp_path, "decision")
        assert "uncertainty" not in columns
        assert "payload" not in columns
        assert len(columns) == 19

    def test_the_other_two_tables_on_this_path_have_one_or_the_other(self, tmp_path: Path) -> None:
        """So the gap is ``decision``'s and not a property of the schema's conventions."""
        _booted(tmp_path)
        assert "uncertainty" in _columns(tmp_path, "dossier")
        assert "payload" in _columns(tmp_path, "dossier")
        assert "payload" in _columns(tmp_path, "trade_intent")

    def test_its_only_free_form_columns_are_the_rationale_and_the_risk_engines(self, tmp_path: Path) -> None:
        _booted(tmp_path)
        conn = _connect(tmp_path)
        try:
            kinds = {str(r[1]): str(r[2]).upper() for r in conn.execute("PRAGMA table_info(decision)")}
        finally:
            conn.close()
        text_columns = [name for name, kind in kinds.items() if kind == "TEXT"]
        assert "rationale" in text_columns and "risk_check" in text_columns

    def test_the_stage_map_asks_for_the_thing_that_cannot_be_stored(self) -> None:
        """The ask is quoted in the stage map, so the gap is between two approved artifacts."""
        board = (DESIGN / "build_board52.py").read_text(encoding="utf-8")
        assert "evidence set + uncertainty" in board
        assert "stage 9" in board

    def test_the_writer_asks_for_a_reason_code_instead_and_says_it_is_not_the_same(
        self, tmp_path: Path
    ) -> None:
        """Asserted on the message a caller actually receives, not on the source that builds it.

        The source cannot be grepped for the phrase: it is assembled from string literals that wrap at
        110 columns, so the sentence is split across two of them and a substring search for it fails on
        code that says exactly this.
        """
        audit, store = _booted(tmp_path)
        with pytest.raises(ValueError) as excinfo:
            record_thesis(audit=audit, store=store, rationale=RATIONALE)
        message = str(excinfo.value)
        assert "a code is a label, not a statement of what is unresolved" in message
        assert "F-30" in message


class TestWhatThisWriterIsNotWiredTo:
    """Four writers in this package and no caller in ``src/nexus`` for any of them."""

    def test_nothing_in_src_calls_record_thesis(self) -> None:
        """Four writers, no callers — asserted against *calls*, never against the word.

        A substring scan fails here for a reason this repository has already paid for: prose that names
        the thing it forbids. ``operational.py``'s F-29 comment names ``record_thesis`` to say which
        writer needed the getter, and a grep-based version of this test reported that comment as a caller.
        """
        callers = []
        for path in sorted(SOURCE_ROOT.rglob("*.py")):
            if path.name in {"thesis.py", "__init__.py"}:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else None
                name = name or (node.func.attr if isinstance(node.func, ast.Attribute) else None)
                if name == "record_thesis":
                    callers.append(f"{path.name}:{node.lineno}")
        assert not callers, callers

    def test_the_package_still_says_so(self) -> None:
        text = (SOURCE_ROOT / "nexus/intelligence/__init__.py").read_text(encoding="utf-8")
        assert "none is wired" in text
        assert "All four are built" in text

    def test_the_projection_alone_still_lands_the_row(self, tmp_path: Path) -> None:
        """``project()`` is reachable with the same payload, which is what makes replay possible at all."""
        audit, store = _booted(tmp_path)
        payload = {
            "decision_id": "DEC-PROJECTED-DIRECTLY",
            "created_at": "2026-11-01T00:00:00.000Z",
            "updated_at": "2026-11-01T00:00:00.000Z",
            "state": "PROPOSED",
            "verb": "ABSTAIN",
            "rationale": "projected by hand to prove the seam is the projection's, not the writer's",
            "reason_codes": ["C"],
        }
        assert project(store, THESIS_EVENT_TYPE, payload, audit_ref=None) is True
        assert store.get_decision("DEC-PROJECTED-DIRECTLY")["rationale"] == payload["rationale"]
