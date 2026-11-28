"""The Stage 9 writer: the candidate thesis, and the first code that writes a ``decision`` row.

``decision`` was built in Stage 6 with nineteen columns and has never been written to. ``PROJECTABLE``
has carried ``"decision.recorded": "decision"`` since the write-ahead path was built and
``save_decision_payload`` has read that event's keys since Phase 2, but nothing in ``src/nexus`` has ever
emitted the event: the only two references outside the store are ``writeahead.py``'s registration and
projection, and two tests in ``test_boot_recovery.py`` that drive the projection by hand. So the table
has been a projection looking for a producer for eight stages. ``design/build_board52.py:73`` — the only
stage map in the repository — puts this batch at step 1 of the intelligence-to-execution path:
*"Candidate thesis · intelligence dossier (stage 9) · evidence set + uncertainty · ABSTAIN is the
default record"*, with steps 2 and 3 (``docs/12`` §1.3's sufficiency bar and A-08's three gates) drawn
dashed until stages 10 and 11 deliver them. D-056's ruling 3 opened Stage 9 and ordered F-26's seam
settled inside it *as its first deliverable*, because this is the code the seam question was about.

**The seam, settled (F-26's answer: no signature changes anywhere).** ``save_decision(record)`` is not a
second seam competing with ``save_decision_payload(payload)``: it is a four-line enricher —
``asdict(record)``, two enum ``.value`` conversions, then a call to the payload method
(``operational.py:404-408``) — as ``save_intent`` and ``save_approval`` are to theirs, and all three
payload siblings are already what ``project()`` calls. So there is one seam and two doors onto it, and
this writer goes through the write-ahead path exactly as ``open_dossier``, ``record_evidence`` and
``record_memory_item`` do: build a complete payload, hand it to
:func:`~nexus.store.writeahead.write_with_audit`, and let the projection land the row. No store method's
signature moves. Nor could a change have broken a conformer silently: the protocol has exactly two *full*
implementations, itself and ``SqliteOperationalStore``, and the two structural fakes in the tree —
``FlakyStore`` and ``HaltBlindStore`` in ``tests/test_boot_recovery.py`` — each override one method and
forward every other attribute through ``__getattr__`` to a real store, which is why the blind spot F-23
was about does not bite here. A wrapper that forwards cannot lack a method the protocol grows.

**What this writer had to add to the protocol (F-29).** ``get_decision`` was the one single-row getter
``OperationalStore`` did not declare, although ``SqliteOperationalStore.get_decision`` has existed since
Phase 2 and ``get_intent``, ``get_dossier``, ``get_evidence_ref`` and ``get_memory_item`` are all
declared. Nothing noticed because nothing wrote a decision: it is a writer that has to ask whether an id
is already taken, and this one is the first. Declaring it moves no signature and adds no behaviour — the
method already existed with exactly that shape — and the protocol now declares 37 methods where it
declared 36.

**F-28, which this writer exists to not have.** ``decision.recorded`` has two producers and they disagree
about what the event carries. ``save_decision`` reaches the projection through ``asdict(record)``, which
supplies all eighteen of ``DecisionRecord``'s fields. ``DecisionRecord.to_audit_payload()`` — the method
whose name says it is for the audit log, and which has zero call sites in ``src`` or ``tests`` — supplies
fourteen, withholding ``rationale``, ``risk_check``, ``created_at`` and ``updated_at``, all four of which
``save_decision_payload`` reads. The first is deliberate and *pinned*: ``test_core_guarantees.py:498``
asserts ``"rationale" not in payload``. The other three are not, and their absence is measurable —
project a decision through that payload, drop the row, wait, and let ``reproject_missing`` replay the
durable audit entry, and ``created_at`` comes back restamped with the replay's clock rather than the
write's. ``write_with_audit`` audits and projects *the same* payload, so a caller that audits the
fourteen-key one has written an audit entry that cannot reproduce its own row.
``intelligence/memory.py:456`` carries the remedy as a comment: *"The timestamp rides in the event, so a
replay reproduces the row it first wrote instead of restamping it with the replay's clock."* This writer
does that, and ``rationale`` rides in the event too, because ``docs/03`` §7 permits a *concise rationale*
and forbids only hidden chain-of-thought — which is also why ``open_dossier`` has audited free-form
``summary`` and ``uncertainty`` since Stage 8.3.

**What this writer refuses, and the one law behind each refusal.** ``docs/12`` §1.3's A-08 is that
*intelligence reaches execution only through the verification engine's three gates*, and A-02 that
*confidence is never a satisfied requirement*; ``design/build_board52.py``'s P-2 failure text adds that
*ABSTAIN is a complete outcome, not an error state*; ``docs/03`` J-04's exit condition ends *research
completion ≠ trade signal*; ``docs/10`` §3.2 says the three verification stages' *definitions finalise at
Stage 11* and that *confidence never overrides a failed stage*. Those five say the same thing about a
record written at step 1 of the path: it may propose, wait, escalate, abstain or reject, and it may not
claim anything a gate downstream of it has not yet been built to grant. So three of the seven
:data:`~nexus.domain.decision.DecisionVerb` members and six of the twelve
:data:`~nexus.domain.decision.DecisionState` members are refused here, and ``intent_id``, ``risk_check``
and ``expires_at`` are absent from the signature as well as from the payload — an absence a reader can
argue with, which is why :mod:`tests.test_thesis_writer` pins the signature and not merely the behaviour.

**F-30, which this writer cannot fix.** The stage map asks for *evidence set + uncertainty*. The evidence
set has two columns (``evidence_refs``, ``counter_evidence_refs``). The uncertainty has none: ``decision``
is the only one of the three tables on this path with neither an ``uncertainty`` column nor a ``payload``
column to pin a key into — ``dossier`` has both and ``trade_intent`` has a ``payload``, an
``evidence_summary`` and a ``counter_case``. Its only free-form columns are ``rationale`` and
``risk_check``, and the second is the risk engine's, which A-02 keeps intelligence out of. So this writer
requires a reason code on every ABSTAIN — ``docs/10`` §3.1's *disposition + reason code* and §3.2's *any
FAIL ends the candidate with a reason code* — and publishes that a reason code is a label, not a
statement of what is unresolved. Adding the column is a migration, and a migration is the one artifact
this repository cannot take back: F-27's count is a row written at apply time and never rewritten, so a
shape chosen here and ruled differently later would split production into two populations. That is why
F-30 is recorded and asked rather than decided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionState, DecisionVerb
from nexus.domain.instrument import Venue
from nexus.intelligence.memory import confidence_text
from nexus.store.writeahead import write_with_audit

__all__ = [
    "GATED_STATES",
    "GATED_VERBS",
    "THESIS_EVENT_TYPE",
    "THESIS_PREFIX",
    "THESIS_STATES",
    "THESIS_VERBS",
    "ThesisReceipt",
    "record_thesis",
]

#: Already registered in ``store/writeahead.py``'s ``PROJECTABLE`` as ``"decision.recorded": "decision"``,
#: so this writer adds an event type to no registry — it supplies the producer a projection has waited for.
THESIS_EVENT_TYPE = "decision.recorded"

#: ``DecisionRecord.decision_id`` has been minted with ``new_id("DEC")`` since Phase 2 and
#: ``test_core_guarantees.py`` asserts the prefix, so like ``MEMORY_PREFIX`` and ``EVIDENCE_PREFIX`` this
#: is the repository's prefix rather than one invented here.
THESIS_PREFIX = "DEC"

#: The four verbs a candidate thesis may carry at step 1 of the path. ABSTAIN is the default record
#: (``build_board52.py:73``) and a complete outcome rather than an error state (P-2's failure text).
THESIS_VERBS: tuple[DecisionVerb, ...] = (
    DecisionVerb.ABSTAIN,
    DecisionVerb.REJECT,
    DecisionVerb.WAIT,
    DecisionVerb.ESCALATE,
)

#: The three it may not, each for its own reason rather than as one folded refusal.
GATED_VERBS: tuple[DecisionVerb, ...] = (
    DecisionVerb.ACCEPT,
    DecisionVerb.REDUCE,
    DecisionVerb.EXIT,
)

#: The six states a thesis may occupy: proposed, waiting on data, rejected, cancelled, abstained, failed.
#: None of them asserts that something downstream of this record happened.
THESIS_STATES: tuple[DecisionState, ...] = (
    DecisionState.PROPOSED,
    DecisionState.WAITING_DATA,
    DecisionState.REJECTED,
    DecisionState.CANCELLED,
    DecisionState.ABSTAINED,
    DecisionState.FAILED,
)

#: The six it may not. Five are past A-08's gates or are the risk engine's own outcome; the sixth needs a
#: reader that does not exist — Stage 8.7 added ``memory_item.expires_at`` and no expiry reader with it,
#: and published that as limitation 1 rather than letting an inert column imply a policy.
GATED_STATES: tuple[DecisionState, ...] = (
    DecisionState.WAITING_APPROVAL,
    DecisionState.APPROVED,
    DecisionState.REDUCED,
    DecisionState.EXECUTED,
    DecisionState.PARTIALLY_EXECUTED,
    DecisionState.EXPIRED,
)


@dataclass(frozen=True, slots=True)
class ThesisReceipt:
    """What one recorded thesis produced. Returned so the caller can cite the record it just wrote."""

    decision_id: str
    audit_ref: str
    instrument_id: str | None
    venue: str | None
    verb: str
    state: str
    #: The concise rationale ``docs/03`` §7 permits. Required, and it rides in the audited event so a
    #: replay reproduces it instead of projecting the column's empty default.
    rationale: str
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    counter_evidence_refs: tuple[str, ...]
    #: The exact string the store holds, or ``None``. Normalised by
    #: :func:`~nexus.intelligence.memory.confidence_text` against the ``NUMERIC(6, 5)`` the portable
    #: target declares at ``migrations/0001_core.sql:112``.
    confidence: str | None
    horizon: str | None
    strategy_id: str | None
    model_id: str | None
    #: Rides in the event, which is the whole of F-28's remedy: without it the projection falls back to
    #: its own clock and a replayed row is not the row that was written.
    created_at: str
    updated_at: str
    #: The three columns this writer is not ruled into, echoed so a reader can see they were left out on
    #: purpose rather than forgotten.
    intent_id: None = None
    risk_check: Mapping[str, Any] = field(default_factory=dict)
    expires_at: None = None


def _aware(moment: datetime, name: str) -> datetime:
    """Refuse a naive datetime before any comparison is done with it.

    The third copy of this helper, after ``intelligence.evidence._aware`` and ``intelligence.memory._aware``,
    and mirrored rather than imported for the reason ``memory.py`` gives: a private helper is not a shared
    one, and promoting it to ``core.time`` would touch a Phase-2 module inside a batch whose scope was named
    by a ruling. Three copies is a cost and is recorded as one; the alternative was a wider diff than
    D-056's ruling 3 authorised. Nothing in this writer currently takes a datetime — the refusal is here so
    that the expiry this writer deliberately omits cannot be added later without it.
    """
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be an aware UTC datetime; got a naive {moment.isoformat()!r}")
    return moment


def _resolve_verb(verb: DecisionVerb | str) -> DecisionVerb:
    """Resolve the proposed verb, refusing the three that belong to gates this batch does not have."""
    try:
        resolved = DecisionVerb(str(verb))
    except ValueError as exc:
        raise ValueError(
            f"verb must be one of {[member.value for member in DecisionVerb]}; got {verb!r}. The "
            "vocabulary is the repository's — docs/03 §7 and docs/10 §3.1 both name it, and §3.1's "
            "decision-state strip carries all seven words"
        ) from exc

    if resolved is DecisionVerb.ACCEPT:
        raise ValueError(
            "verb=ACCEPT is refused at Stage 9: ACCEPT is the verb by which intelligence reaches "
            "execution, and docs/12 §1.3's A-08 is that intelligence reaches execution only through the "
            "verification engine's three gates — which docs/10 §3.2 says finalise at Stage 11 and "
            "build_board52.py draws dashed until then. docs/03 J-04's exit condition ends 'research "
            "completion ≠ trade signal'. Record the thesis as PROPOSED, WAIT or ABSTAIN and let the "
            "gates accept it"
        )
    if resolved is DecisionVerb.REDUCE:
        raise ValueError(
            "verb=REDUCE is refused at Stage 9: REDUCE proposes a smaller size, and sizing is the risk "
            "engine's — DecisionState.REDUCED's own comment in domain/decision.py is 'risk engine cut "
            "size to fit limits'. docs/12 §1.3's A-02 keeps the risk engine deterministic and "
            "fail-closed, and build_board52.py's P-2 law is that the risk engine sees no model I/O, so "
            "a size proposed by intelligence is the one input it must not receive"
        )
    if resolved is DecisionVerb.EXIT:
        raise ValueError(
            "verb=EXIT is refused at Stage 9: EXIT closes an open position, and nothing is open — this "
            "writer writes no trade_intent row and A-08 is why. decision.intent_id stays NULL here for "
            "the same reason, and it is absent from this signature rather than accepted and ignored"
        )
    return resolved


def _resolve_state(state: DecisionState | str) -> DecisionState:
    """Resolve the machine state, refusing the six that assert something downstream happened."""
    try:
        resolved = DecisionState(str(state))
    except ValueError as exc:
        raise ValueError(
            f"state must be one of {[member.value for member in DecisionState]}; got {state!r}"
        ) from exc

    if resolved in GATED_STATES:
        # Named in the message rather than described, so a reviewer can see the boundary and argue with
        # it: six states refused, and the six permitted are listed too because a refusal that does not
        # say what it would have accepted is a refusal nobody can check.
        downstream = ", ".join(state.value for state in GATED_STATES[:5])
        permitted = ", ".join(state.value for state in THESIS_STATES)
        raise ValueError(
            f"state={resolved.value} is refused at Stage 9. Five of the six gated states are past "
            f"A-08's three gates or are the risk engine's own outcome ({downstream}), and docs/10 §3.2 "
            "puts those gates at Stage 11. EXPIRED is the sixth and is refused for a different reason: "
            "it needs an expiry reader, and Stage 8.7 added memory_item.expires_at with no reader and "
            "published the column as inert rather than implying a policy. A thesis occupies one of "
            f"{permitted}"
        )
    return resolved


def _resolve_instrument(store: Any, instrument_id: str | None) -> str | None:
    """Check the instrument the thesis is about, or return ``None`` when it is about none.

    Two claims are refused separately because they are different mistakes, following
    :func:`nexus.intelligence.evidence._resolve_dossier`: an empty string is neither an instrument nor
    ``None``, and a name the master has never held is a dangling parent. ``decision.instrument_id`` has
    carried ``REFERENCES instrument`` since the table was built, but ``PRAGMA foreign_keys`` is
    deliberately off (``docs/13`` §2.5), so SQLite would store a dangling id without comment and the row
    would be orphaned rather than corrupt — which is F-25, measured in Stage 8.5 and fixed alone on
    D-054's ruling 3. The guard belongs in the writer and not in ``store.save_decision_payload``, because
    the store is a projection: it applies what the audit chain already accepted, and re-litigating a
    parent there would make a replay fail on data the chain has committed to.
    """
    if instrument_id is None:
        return None
    wanted = str(instrument_id)
    if not wanted.strip():
        raise ValueError(
            "instrument_id must name an instrument or be None; an empty string is neither, and None — "
            "not '' — is how this writer records a thesis about no instrument in particular"
        )
    held = frozenset(str(row.get("instrument_id") or "") for row in store.instruments())
    if wanted not in held:
        raise ValueError(
            f"instrument {wanted!r} is not in the system of record, which holds {len(held)}: "
            f"{sorted(held)}. decision.instrument_id REFERENCES instrument, but PRAGMA foreign_keys is "
            "deliberately off, so SQLite would accept this dangling parent without comment and the row "
            "would verify its own checksum while naming nothing — project the instrument first (Stage "
            "8.2's L-B) or record the thesis with instrument_id=None"
        )
    return wanted


def _resolve_evidence(store: Any, ids: Sequence[str], name: str) -> tuple[str, ...]:
    """Check every cited evidence id against the store, and refuse the two ways a citation can be wrong.

    ``record_memory_item`` has checked its ``evidence_ids`` this way since Stage 8.5. An id the store has
    never held is a dangling citation: ``evidence_refs`` is a JSON list on ``decision`` with no foreign
    key to check, so nothing below this function can refuse it, and a thesis citing a source that does
    not exist is the exact defect ``docs/10`` §3.1's *contradictions highlighted and linked* cannot
    render — the link would point at nothing.
    """
    resolved: list[str] = []
    for raw in ids:
        wanted = str(raw)
        if not wanted.strip():
            raise ValueError(
                f"{name} must hold evidence ids; got an empty string, which cites nothing and is not "
                "the same as citing no evidence at all — omit the argument for that"
            )
        if store.get_evidence_ref(wanted) is None:
            raise ValueError(
                f"{name} cites evidence {wanted!r}, which the store does not hold. decision's evidence "
                "columns are JSON lists with no foreign key, so nothing below this writer can refuse a "
                "dangling citation and the thesis would look complete while pointing at nothing — "
                "record the evidence first (Stage 8.2's record_evidence)"
            )
        resolved.append(wanted)
    return tuple(resolved)


def _resolve_confidence(confidence: str | Decimal | int | float | None) -> str | None:
    """Normalise a confidence to the exact string the store will hold, or refuse it.

    ``decision.confidence`` is ``TEXT`` on SQLite and ``NUMERIC(6, 5)`` in the portable target
    (``migrations/0001_core.sql:112``), which is the same pair ``memory_item.confidence`` has, so the
    boundary check is the one Stage 8.5 built and Stage 8.7 tested with 27 inputs rather than a second
    opinion about the same type. It refuses a magnitude PostgreSQL would reject and a scale it would
    silently round, and — as D-054 ruled for ``memory_item`` — it bounds no range: ``-0.4`` and ``9.99999``
    both store. ``domain/decision.py:59`` comments this column *0..1, calibrated*, and nothing in the
    repository enforces that comment on either table; this writer does not start.

    A ``float`` is accepted because ``DecisionRecord.confidence`` is typed ``float | None`` and a caller
    holding one should not have to stringify it, but it is stringified through ``Decimal`` before the
    check so the value that lands is the one that was checked.
    """
    if confidence is None:
        return None
    if isinstance(confidence, float):
        return confidence_text(Decimal(repr(confidence)))
    return confidence_text(confidence)


def _resolve_codes(codes: Sequence[str]) -> tuple[str, ...]:
    """Normalise reason codes, refusing an empty one and keeping the caller's order and duplicates.

    No vocabulary for these exists yet: ``docs/10`` §3.2 says the three verification stages' *definitions
    finalise at Stage 11*, so the codes are free text here for the same reason ``evidence_ref.kind`` was
    left free text in Stage 8.2 — where no vocabulary is declared anywhere, inventing one is the larger
    mistake. Duplicates are kept because ``DecisionRecord.transition`` appends without deduplicating, and
    a code that appears twice records that two checks failed the same way.
    """
    resolved: list[str] = []
    for raw in codes:
        code = str(raw).strip()
        if not code:
            raise ValueError(
                "reason_codes must hold non-empty codes; an empty string is not a reason and the "
                "vocabulary these eventually draw from finalises at Stage 11 (docs/10 §3.2), so a blank "
                "one cannot be excused as a placeholder for a word that does not exist yet"
            )
        resolved.append(code)
    return tuple(resolved)


def record_thesis(
    *,
    audit: Any,
    store: Any,
    rationale: str,
    instrument_id: str | None = None,
    venue: Venue | str | None = None,
    verb: DecisionVerb | str = DecisionVerb.ABSTAIN,
    state: DecisionState | str = DecisionState.PROPOSED,
    reason_codes: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    counter_evidence_refs: Sequence[str] = (),
    confidence: str | Decimal | int | float | None = None,
    horizon: str | None = None,
    strategy_id: str | None = None,
    model_id: str | None = None,
    decision_id: str | None = None,
    actor: str = "INTELLIGENCE",
) -> ThesisReceipt:
    """Record one candidate thesis, audit entry first and projection second (L-2).

    ``audit`` and ``store`` are typed loosely to match :func:`~nexus.store.writeahead.write_with_audit`,
    which takes the same seam. Every default is the ABSTAIN side — ``verb=ABSTAIN``, ``state=PROPOSED``,
    no evidence, no confidence — because this package's rule is that an intelligence record which can be
    created without a basis is a record that will be, and a thesis is the record the rest of the path
    reads.

    ``intent_id``, ``risk_check`` and ``expires_at`` are not parameters. All three are columns on
    ``decision`` and all three are left at what the projection's own defaults produce: ``intent_id``
    because A-08 keeps intelligence out of execution and this writer creates no intent to name,
    ``risk_check`` because it is the risk engine's column and A-02 keeps the risk engine's inputs
    deterministic, ``expires_at`` because Stage 8.7 measured what an expiry column with no reader is
    worth. ``ThesisReceipt`` echoes all three so the omission is visible in what the caller gets back.

    Raises ``ValueError`` for a call that should not have been written that way, following
    :mod:`nexus.intelligence.dossier` and :mod:`nexus.intelligence.memory`. No ``RejectReason`` is spent:
    these are programmer errors at an internal boundary, not operational conditions, and a reason code is
    vocabulary the audit log and the UI both consume.
    """
    if not rationale.strip():
        raise ValueError(
            "a thesis needs a rationale: it is the 'concise rationale' docs/03 §7 permits and the only "
            "place this record can carry one, because decision is the one table on this path with no "
            "payload column. The schema's DEFAULT '' would store an empty one without comment, and a "
            "thesis that cannot say why is not a thesis — J-04's exit condition is that the owner learns "
            "what is known, what is uncertain and what would invalidate the view"
        )

    resolved_verb = _resolve_verb(verb)
    resolved_state = _resolve_state(state)
    resolved_instrument = _resolve_instrument(store, instrument_id)

    if venue is not None:
        try:
            resolved_venue: str | None = Venue(str(venue)).value
        except ValueError as exc:
            raise ValueError(
                f"venue must be one of {[member.value for member in Venue]} or None; got {venue!r}. "
                "None means the thesis is not about one venue, which is a statement — an unrecognised "
                "string is not one"
            ) from exc
    else:
        resolved_venue = None

    resolved_support = _resolve_evidence(store, evidence_refs, "evidence_refs")
    resolved_counter = _resolve_evidence(store, counter_evidence_refs, "counter_evidence_refs")
    both = sorted(set(resolved_support) & set(resolved_counter))
    if both:
        raise ValueError(
            f"{both!r} is cited as both evidence and counter-evidence on the same thesis. That is not a "
            "contradiction the system can hold: docs/10 §3.1 asks for contradictions 'highlighted and "
            "linked', and a source listed on both sides renders as a source arguing with itself, which "
            "tells a reviewer less than either citation alone. Record the disagreement between two "
            "sources — evidence_ref.contradicts has existed since Stage 8.6 — or cite this one on the "
            "side it supports"
        )

    resolved_codes = _resolve_codes(reason_codes)
    if resolved_verb is DecisionVerb.ABSTAIN and not resolved_codes:
        raise ValueError(
            "verb=ABSTAIN needs at least one reason code. build_board52.py:73 makes ABSTAIN the default "
            "record and P-2's failure text makes it a complete outcome rather than an error state, so it "
            "has to say what it is complete ABOUT: docs/10 §3.1 asks for 'disposition + reason code' and "
            "§3.2 that any FAIL ends the candidate with a reason code. This writer asks for a code and "
            "not for an uncertainty because decision has no uncertainty column — F-30 — and a code is a "
            "label, not a statement of what is unresolved"
        )

    resolved_confidence = _resolve_confidence(confidence)

    resolved_id = str(decision_id or "").strip() or new_id(THESIS_PREFIX)
    if decision_id is not None and store.get_decision(resolved_id) is not None:
        raise ValueError(
            f"decision {resolved_id!r} already exists, and recording a thesis is not editing one: the "
            "store writes with INSERT OR REPLACE because it is a projection, so a second record would "
            "restate the first row's verb, state and rationale. The audit chain would keep both events, "
            "but the row a reviewer reads would no longer be the row that was written. Changing a "
            "decision is DecisionRecord.transition's job and a later event with its own type, neither of "
            "which exists yet"
        )

    # The timestamps ride in the event, so a replay reproduces the row it first wrote instead of
    # restamping it with the replay's clock — the remedy memory.py:457 names and the one F-28 measures
    # `to_audit_payload()` lacking. `rationale` rides for the same reason: the projection reads it from
    # the payload, so a payload without it projects the column's empty default and the thesis loses the
    # only place it can carry one.
    now = iso_utc(utc_now())
    event: dict[str, Any] = {
        "decision_id": resolved_id,
        "created_at": now,
        "updated_at": now,
        "state": resolved_state.value,
        "verb": resolved_verb.value,
        "instrument_id": resolved_instrument,
        "venue": resolved_venue,
        "strategy_id": str(strategy_id).strip() or None if strategy_id is not None else None,
        "model_id": str(model_id).strip() or None if model_id is not None else None,
        "horizon": str(horizon).strip() or None if horizon is not None else None,
        "confidence": resolved_confidence,
        "rationale": rationale.strip(),
        "reason_codes": list(resolved_codes),
        "evidence_refs": list(resolved_support),
        "counter_evidence_refs": list(resolved_counter),
        "intent_id": None,
        "risk_check": {},
        "expires_at": None,
    }

    entry = write_with_audit(
        audit=audit, store=store, event_type=THESIS_EVENT_TYPE, payload=event, actor=actor
    )

    return ThesisReceipt(
        decision_id=resolved_id,
        audit_ref=str(entry.record_id),
        instrument_id=resolved_instrument,
        venue=resolved_venue,
        verb=resolved_verb.value,
        state=resolved_state.value,
        rationale=str(event["rationale"]),
        reason_codes=resolved_codes,
        evidence_refs=resolved_support,
        counter_evidence_refs=resolved_counter,
        confidence=resolved_confidence,
        horizon=event["horizon"],
        strategy_id=event["strategy_id"],
        model_id=event["model_id"],
        created_at=now,
        updated_at=now,
    )
