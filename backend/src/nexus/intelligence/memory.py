"""The third writer for the intelligence-memory tables: ``memory_item`` (Stage 8.5).

Stage 6 built the table, migration ``0004_memory_fidelity`` gave its ``confidence`` column a ``CHECK`` in
Stage 8.2, and nothing had ever written a row. ``docs/13`` recorded the reason — *"`memory_item` is still
writer-less, and D-051 deferred F-18's three columns to the stage-10 batch that writes it"* — and D-053's
ruling 4 named this batch as that one. So the writer and the columns arrive together, which is the point
D-051's ruling 2 made when it declined to add the columns early: *"columns no writer populates are columns
no test can exercise, and a nullable column nobody fills is indistinguishable from one that was dropped."*

The writer is audited as ``memory.recorded`` and projected through the existing write-ahead path, so a
crash between the audit entry and the row is a hole :func:`~nexus.store.writeahead.reproject_missing` can
fill.

**What a memory item is, from the documents approved before it existed.** ``docs/03`` §7 lists what the
Intelligence Centre shows, and two of the lines are this table: *"What it learned (memory updates with
provenance)"* and *"What remains uncertain (beliefs with confidence, validity interval, change
conditions)."* ``docs/10`` §3.1 turns the second into a rule — *"confidence as a band with validity
interval and change conditions; a point estimate without them is a defect"* — and asks the same region for
*"memory & knowledge (type tabs, expiring TTLs, corrections as first-class entries)"*. ``docs/03`` §7 also
forbids hidden chain-of-thought: *"Auditable evidence + structured findings + concise rationale only."* So
``body`` holds the structured finding, the pinned payload keys hold what qualifies it, and no prose
reasoning is smuggled into ``payload`` — the same line ``intelligence/dossier.py`` drew for its own
``payload``.

**Six decisions this writer makes, each grounded rather than invented:**

* **A confidence is a claim, and a claim carries its interval, its conditions and its provenance.** When
  ``confidence`` is present, ``valid_from``, ``change_conditions`` and at least one ``evidence_ids`` entry
  are all required, and the refusal names the sentence it comes from. This is the whole content of F-18's
  first gap: the table had the one column those documents call a defect when it stands alone. When
  ``confidence`` is absent none of the three is required, because not every memory item is a belief — the
  schema's own default ``kind`` is ``OBSERVATION``, and an observation of what happened has ``created_at``
  and needs no validity interval. Both halves are pinned by tests, since a gate nobody has tested for
  permissiveness is a gate nobody can tell from a bug.
* **``confidence`` must fit the type the portable target declares.** ``migrations/0002_memory.sql`` says
  ``NUMERIC(6, 5)``: one digit before the decimal point and five after. The applied schema keeps the column
  ``TEXT`` — deliberately, and ``tests/test_schema_fidelity.py`` records why — and migration ``0004``'s
  ``CHECK`` proves numeric-ness but *does not bound the range*, which that same test file pins as a
  decision. So nothing below this writer stops a value that PostgreSQL would reject, and a promotion under
  R-1's triggers would fail on data this system accepted. The writer therefore enforces the declared type
  at the boundary: magnitude and scale. Scale is refused rather than rounded because PostgreSQL would round
  it silently and ``store/serialise.py``'s first rule is that a Decimal never loses precision on the way to
  disk. A ``float`` is refused outright for the same reason. What the writer does **not** do is bound the
  value to ``[0, 1]``: no approved document declares a range for confidence, ``NUMERIC(6, 5)`` does not
  imply one, and ``test_the_check_does_not_bound_the_range_and_that_is_recorded`` pins the unboundedness on
  purpose. A negative confidence is therefore accepted, and §12's decision request asks whether that should
  stay true.
* **``valid_from`` and ``valid_until`` are about the world, not about the record.** They bound the period
  the claim is asserted to hold over. ``created_at`` is when this system wrote the row, and neither of the
  two defaults to it: collapsing a claim's validity into our own clock is the same mistake F-14 named, in a
  different pair of columns, and it would make every belief look exactly as fresh as the moment it was
  recorded. ``valid_until=None`` means no end was stated, which is not the same as no end, so the writer
  pins ``validity_open_ended`` beside it — a derived flag, in the shape of the dossier writer's
  ``venue_maps_instrument``, so a reader cannot mistake an absence for a statement. An item whose
  ``valid_until`` is already past is **accepted**: an expired belief is a record of what this system used
  to hold, and refusing it would delete history instead of dating it.
* **``cited_by`` is always empty, and ``superseded_by`` is never set.** An item cannot cite itself into
  being cited, so a writer that accepted ``cited_by`` would let a caller fabricate the citation graph
  ``docs/10`` §3.1 asks the view to render; the column is pinned to ``[]`` and the key is overwritten in
  the payload even if a caller supplies it. ``superseded_by`` points from a superseded row at the row that
  replaced it, so setting it means updating a row that already exists — a second verb, with its own audit
  event, which no ruling has authorised. ``docs/10`` §3.1 asks for *"corrections as first-class entries"*
  and ``docs/15`` §5.1 for *"memory is superseded, never edited in place"*; both are honoured here by
  building neither, and §12 asks.
* **Provenance is a pinned payload key, not a column.** ``evidence_ids`` names the ``evidence_ref`` rows a
  belief rests on, and every id is checked against the store, because ``PRAGMA foreign_keys`` is off and
  SQLite would accept a dangling one without comment. It lives in ``payload`` because F-18's approved
  column set is three columns and this is not one of them; the cost is that the relation is unindexed and
  unenforced, and §12 records that as a limitation rather than presenting it as a design. A memory item
  reaches a research case through its evidence rows, which carry ``dossier_id``, and not through a column
  of its own.
* **``kind`` and ``scope`` are free text with the schema's defaults.** No vocabulary for either is declared
  anywhere in the repository — the schema says only ``DEFAULT 'OBSERVATION'`` and ``DEFAULT 'GLOBAL'``, and
  ``docs/10`` §3.1's "type tabs" names a control, not a word list. This is exactly the treatment
  ``evidence_ref.kind`` got in Stage 8.2: where no vocabulary exists, inventing one puts a plausible-looking
  enum in front of a distinction nobody has drawn. ``subject`` is free text for the same reason, and no
  referent is declared for it either.

**Recording is not editing.** A caller-supplied ``memory_id`` that already exists is refused. The store
writes with ``INSERT OR REPLACE`` because it is a *projection*, so a second "record" would restate the
first row's body and confidence in the read model; the audit chain would keep both events, so nothing
durable is lost, but the row a reviewer reads would no longer be the row that was written. That is the
principle ``docs/15`` §5.1 states and ``superseded_by`` exists to serve.

``created_at`` travels **inside** the audited event, for the reason ``save_dossier`` gives: the applied
schema has no ``DEFAULT now()`` (one of the four defaults ``docs/15`` §9.1 records as lost between the two
DDLs), so a projection that filled it at write time would restamp a replayed event with the replay's clock.

What this module does **not** do, named rather than left to be discovered. It builds **no band**: ``docs/10``
§3.1 asks for confidence "as a band" and D-035 approved "beliefs as bands", but a band is an interval on
the confidence axis and the three columns this batch adds are on the time axis, so a belief still carries
exactly one number — **F-24**, recorded in §12 and in ledger row ``O-015``, and not fixed here because two
more columns are not this batch's ruling. It sets **no expiry**: F-18's second gap (*"no expiry column
anywhere"*, which ``docs/10`` §3.1's "expiring TTLs" asks for) stays open, because ``expires_at`` is not
one of the three columns D-051 deferred and ``valid_until`` is not a substitute for it. It defines **no
sufficiency** and **no verification stage**: ``docs/10`` §3.2 fixes V1–V3 at Stage 11, and ``docs/12``
§1.3's law (A-02+A-08) is that no gate can be satisfied by a confidence value — so nothing here reads
``confidence`` as an input to any decision, and no caller exists, which the test that scans ``src/nexus``
for one keeps saying.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.store.serialise import to_jsonable
from nexus.store.writeahead import write_with_audit

__all__ = [
    "CONFIDENCE_PRECISION",
    "CONFIDENCE_SCALE",
    "EVIDENCE_IDS_KEY",
    "MEMORY_EVENT_TYPE",
    "MEMORY_KIND_OBSERVATION",
    "MEMORY_PREFIX",
    "MEMORY_SCOPE_GLOBAL",
    "VALIDITY_OPEN_ENDED_KEY",
    "MemoryReceipt",
    "confidence_text",
    "record_memory_item",
    "validity_of",
]

#: The audited event this writer emits. In ``writeahead.PROJECTABLE`` since Stage 8.5.
MEMORY_EVENT_TYPE = "memory.recorded"

#: Memory ids. ``tests/test_schema_fidelity.py`` has used this prefix for ``memory_item`` rows since Stage
#: 8.2 wrote the migration-0004 rebuild test, which is the same justification ``EVIDENCE_PREFIX`` gives:
#: the prefix was already the repository's, not invented here. Neither is in ``core.ids.new_id``'s
#: convention list, which names prefixes rather than registering them.
MEMORY_PREFIX = "MEM"

#: The schema's own defaults, and the only values this writer assumes. Neither has a vocabulary behind it.
MEMORY_KIND_OBSERVATION = "OBSERVATION"
MEMORY_SCOPE_GLOBAL = "GLOBAL"

#: The pinned payload keys, named once so the writer that pins them and any future reader cannot drift.
EVIDENCE_IDS_KEY = "evidence_ids"
#: Derived, not supplied: ``True`` when no ``valid_until`` was stated. See :func:`record_memory_item`.
VALIDITY_OPEN_ENDED_KEY = "validity_open_ended"

#: What ``migrations/0002_memory.sql`` declares for ``memory_item.confidence``: ``NUMERIC(6, 5)``. Six
#: digits in total, five of them after the decimal point, which leaves one before it.
CONFIDENCE_PRECISION = 6
CONFIDENCE_SCALE = 5


def confidence_text(confidence: str | Decimal | int) -> str:
    """Normalise a confidence to the exact string the store will hold, or refuse it.

    The value is checked against the type the portable target declares, because nothing below this
    function can: the applied column is ``TEXT`` on purpose and migration ``0004``'s ``CHECK`` proves
    numeric-ness without bounding the range, so a magnitude PostgreSQL would reject and a scale it would
    silently round both reach the database unchallenged. Refusing them here is what makes the two schemas
    agree at the writer instead of at promotion.

    The caller's own string form is returned rather than a reformatted one, because ``store/serialise.py``'s
    rule is that a Decimal travels as its exact string and a normalisation nobody asked for is a precision
    change with a tidy name.
    """
    if isinstance(confidence, bool):
        raise ValueError(
            f"confidence must be a number, not {confidence!r}: a bool is an int in Python and Decimal "
            "accepts it, so without this refusal True would be stored as a confidence of one"
        )
    if isinstance(confidence, float):
        raise ValueError(
            f"confidence must be a Decimal or its exact string form, not a float ({confidence!r}). "
            "store/serialise.py's first rule is that a Decimal never becomes a float, and a float passed "
            "in is already the lossy half of that mistake"
        )
    text = str(confidence).strip() if not isinstance(confidence, Decimal) else str(confidence)
    if not text:
        raise ValueError("confidence must be a number or None; an empty string is neither")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"confidence {text!r} is not a number. The applied column is TEXT and migration 0004's CHECK "
            "is what makes it numeric, so this refusal is the writer agreeing with the CHECK rather than "
            "leaving the database to say it"
        ) from exc
    if not value.is_finite():
        raise ValueError(
            f"confidence must be finite; got {text!r}. NaN and Infinity are Decimal values, so the CHECK "
            "that casts to REAL would not catch either, and neither is a confidence"
        )
    digits, exponent = _scale_of(value)
    if exponent > CONFIDENCE_SCALE:
        raise ValueError(
            f"confidence {text!r} carries {exponent} decimal places and the portable target declares "
            f"NUMERIC({CONFIDENCE_PRECISION},{CONFIDENCE_SCALE}), which holds {CONFIDENCE_SCALE}. "
            "PostgreSQL would round the rest away silently; this schema's rule is that a Decimal never "
            "loses precision on the way to disk, so the value is refused instead of rounded"
        )
    if digits > CONFIDENCE_PRECISION - CONFIDENCE_SCALE:
        raise ValueError(
            f"confidence {text!r} needs {digits} digits before the decimal point and the portable target "
            f"declares NUMERIC({CONFIDENCE_PRECISION},{CONFIDENCE_SCALE}), which leaves "
            f"{CONFIDENCE_PRECISION - CONFIDENCE_SCALE}. PostgreSQL would raise a numeric field overflow, "
            "so accepting it here would store a row a promotion under R-1's triggers could not carry"
        )
    return text


def _scale_of(value: Decimal) -> tuple[int, int]:
    """Digits before the decimal point, and digits after it, for a finite Decimal.

    Taken from the *normalised* value, so a trailing zero is not a sixth decimal place: ``9.999990`` and
    ``9.99999`` are the same number and PostgreSQL would store the same ``NUMERIC(6,5)`` for both. The text
    the caller passed is still what gets stored — see :func:`confidence_text` — because refusing a value
    that loses nothing would be a strictness with no rule behind it, and rewriting it would be a change
    nobody asked for.
    """
    sign, digits, exponent = value.normalize().as_tuple()
    del sign  # the range is deliberately unbounded; see the module docstring
    if not isinstance(exponent, int):
        # Unreachable from confidence_text, which refuses a non-finite value first. Stated anyway so the
        # helper is total on its own argument rather than only on the one caller's, which is what mypy is
        # really asking about: `as_tuple` types the exponent as `Literal['n', 'N', 'F'] | int`.
        raise ValueError(f"confidence must be finite; got {value!r}")
    return len(digits) + exponent, max(0, -exponent)


def validity_of(row: Mapping[str, Any]) -> dict[str, Any]:
    """Lift one memory item's validity interval and change conditions out of the row.

    The three things ``docs/10`` §3.1 will not accept a confidence without, read from one place, so a
    writer that pins them and a reader that serves them cannot disagree about where they live — the reason
    :func:`~nexus.intelligence.dossier.sufficiency_of` exists for the dossier's two keys. A row written
    before migration ``0005_memory_beliefs`` has no interval at all and yields empty values rather than
    invented ones; there are no such rows today, because nothing had ever written to this table.
    """
    payload = row.get("payload")
    body = payload if isinstance(payload, Mapping) else {}
    valid_until = row.get("valid_until")
    return {
        "valid_from": row.get("valid_from"),
        "valid_until": valid_until,
        VALIDITY_OPEN_ENDED_KEY: bool(body.get(VALIDITY_OPEN_ENDED_KEY, valid_until is None)),
        "change_conditions": str(row.get("change_conditions") or ""),
        EVIDENCE_IDS_KEY: [str(item) for item in (body.get(EVIDENCE_IDS_KEY) or ())],
    }


def _aware(moment: datetime, name: str) -> datetime:
    """Refuse a naive datetime before any comparison is done with it.

    Mirrors ``intelligence.evidence._aware`` on purpose rather than by import: a private helper is not a
    shared one, and promoting it to ``core.time`` would touch a Phase-2 module inside a batch whose scope
    was named by a ruling. ``iso_utc`` refuses a naive datetime too, but it runs *after* the two ends of
    the interval have been compared, and comparing a naive datetime with an aware one raises a bare
    ``TypeError`` from the comparison — an unclassified crash at a point where nothing names the condition,
    which is the failure mode finding F-4 was about.
    """
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be an aware UTC datetime; got a naive {moment.isoformat()!r}")
    return moment


@dataclass(frozen=True, slots=True)
class MemoryReceipt:
    """What one write produced. Returned so the caller can cite the item it just recorded."""

    memory_id: str
    audit_ref: str
    kind: str
    scope: str
    subject: str
    #: The structured finding. Required: it is the one column the schema makes ``NOT NULL`` with no default.
    body: str
    #: The exact string stored, or ``None``. Never a float — see :func:`confidence_text`.
    confidence: str | None
    valid_from: str | None
    valid_until: str | None
    #: ``True`` when no end was stated, which is not the same as no end. Derived, not supplied.
    validity_open_ended: bool
    change_conditions: str
    #: The ``evidence_ref`` rows this item rests on, each checked to exist. Empty unless a confidence was
    #: given, in which case the writer refuses it empty.
    evidence_ids: tuple[str, ...]
    created_at: str
    #: Always ``None``: setting it means editing a row that already exists, which is a second verb.
    superseded_by: str | None
    #: Always empty: an item cannot cite itself into being cited.
    cited_by: tuple[str, ...]
    #: Caller payload plus the pinned keys, which the writer always wins.
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "audit_ref": self.audit_ref,
            "kind": self.kind,
            "scope": self.scope,
            "subject": self.subject,
            "body": self.body,
            "confidence": self.confidence,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            VALIDITY_OPEN_ENDED_KEY: self.validity_open_ended,
            "change_conditions": self.change_conditions,
            EVIDENCE_IDS_KEY: list(self.evidence_ids),
            "created_at": self.created_at,
            "superseded_by": self.superseded_by,
            "cited_by": list(self.cited_by),
            "payload": dict(self.payload),
        }


def record_memory_item(
    *,
    audit: Any,
    store: Any,
    body: str,
    kind: str = MEMORY_KIND_OBSERVATION,
    scope: str = MEMORY_SCOPE_GLOBAL,
    subject: str = "",
    confidence: str | Decimal | int | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    change_conditions: str = "",
    evidence_ids: Sequence[str] = (),
    payload: Mapping[str, Any] | None = None,
    memory_id: str | None = None,
    actor: str = "MEMORY",
) -> MemoryReceipt:
    """Record one memory item, audit entry first and projection second (L-2).

    ``audit`` and ``store`` are typed loosely to match :func:`~nexus.store.writeahead.write_with_audit`,
    which takes the same seam. Every default is the side that claims least: ``kind='OBSERVATION'``,
    ``scope='GLOBAL'``, no confidence, no interval, no provenance — because this package's rule is that an
    intelligence record which can be created without a basis is a record that will be.

    Raises ``ValueError`` for a call that should not have been written that way, following
    :mod:`nexus.intelligence.evidence` and :func:`nexus.core.time.iso_utc`. No ``RejectReason`` is spent:
    these are programmer errors at an internal boundary, not operational conditions, and a reason code is
    vocabulary the audit log and the UI both consume.
    """
    if not body.strip():
        raise ValueError(
            "a memory item needs a body: it is the structured finding docs/03 §7 permits ('auditable "
            "evidence + structured findings + concise rationale only'), and the one column the schema makes "
            "NOT NULL with no default. An item that says nothing cannot be cited by anything, and "
            "confidence without a finding is the point estimate docs/10 §3.1 calls a defect"
        )

    resolved_confidence = confidence_text(confidence) if confidence is not None else None
    resolved_from = _aware(valid_from, "valid_from") if valid_from is not None else None
    resolved_until = _aware(valid_until, "valid_until") if valid_until is not None else None
    if resolved_from is not None and resolved_until is not None and resolved_until <= resolved_from:
        raise ValueError(
            f"valid_until ({iso_utc(resolved_until)}) must follow valid_from ({iso_utc(resolved_from)}): "
            "the pair bounds the period a claim is asserted to hold over, and an interval that ends before "
            "or exactly when it starts bounds nothing. An item whose validity has ended is legitimate and "
            "is accepted — refusing it would date history by deleting it"
        )

    ids = tuple(str(item).strip() for item in evidence_ids)
    for item in ids:
        if not item:
            raise ValueError(
                "every evidence_ids entry must name an evidence row; an empty string names none, and a "
                "provenance list with a blank in it is a provenance list nobody can follow"
            )
        if store.get_evidence_ref(item) is None:
            raise ValueError(
                f"evidence {item!r} does not exist, so nothing can rest on it. docs/03 §7 asks the "
                "Intelligence Centre to show 'memory updates with provenance', and a pointer at a row the "
                "store has never held is not provenance — it renders as a citation with nothing behind it. "
                "PRAGMA foreign_keys is deliberately off, so SQLite would accept this dangling id without "
                "comment; record the evidence first (intelligence.evidence.record_evidence)"
            )

    if resolved_confidence is not None:
        # The refusal F-18's first gap exists for. Three separate conditions, three separate messages: a
        # caller told "the basis is missing" when the real problem is the interval will fix the wrong thing.
        if not change_conditions.strip():
            raise ValueError(
                f"confidence={resolved_confidence!r} is a point estimate, and docs/10 §3.1 is explicit that "
                "'a point estimate without them is a defect': it needs change_conditions, the statement of "
                "what would make this stop being true. docs/03 §7 asks the Intelligence Centre to show "
                "beliefs with 'confidence, validity interval, change conditions', and J-04's exit condition "
                "is that the owner learns what would invalidate the thesis — which a number alone cannot say"
            )
        if resolved_from is None:
            raise ValueError(
                f"confidence={resolved_confidence!r} needs valid_from: docs/10 §3.1 asks for confidence "
                "'with validity interval', and an interval with no start is not one. created_at is not a "
                "substitute and is not used as one — it says when this system wrote the row, not from when "
                "the claim holds, and collapsing the two is F-14's mistake in a different pair of columns"
            )
        if not ids:
            raise ValueError(
                f"confidence={resolved_confidence!r} needs at least one evidence_ids entry: docs/03 §7 asks "
                "for 'memory updates with provenance', and a confidence with nothing behind it is exactly "
                "the fabricated confidence the owner requirements forbid. docs/12 §1.3's law (A-02+A-08) is "
                "that no gate can be satisfied by a confidence value, which only holds if the value itself "
                "rests on something a reviewer can read"
            )

    resolved_id = str(memory_id or "") or new_id(MEMORY_PREFIX)
    if memory_id is not None and store.get_memory_item(resolved_id) is not None:
        raise ValueError(
            f"memory item {resolved_id!r} already exists, and recording is not editing: the store writes "
            "with INSERT OR REPLACE because it is a projection, so a second record would restate the first "
            "row's body and confidence. The audit chain would keep both events, but the row a reviewer "
            "reads would no longer be the row that was written. Memory is superseded, never edited in place "
            "(docs/15 §5.1); a correction is a later verb with its own event"
        )

    open_ended = resolved_until is None
    # The pinned keys are written last so a caller's payload cannot overwrite them: they are what makes the
    # row interpretable, and a claim that can be talked out of its own qualifications is a claim that will
    # be. `cited_by` is pinned empty for the same reason — an item cannot cite itself into being cited, and
    # a caller who could set it could fabricate the graph docs/10 §3.1 asks the view to render.
    stored: dict[str, Any] = dict(to_jsonable(dict(payload or {})))
    stored.update(
        {
            EVIDENCE_IDS_KEY: list(ids),
            VALIDITY_OPEN_ENDED_KEY: open_ended,
            "cited_by": [],
        }
    )

    # The timestamp rides in the event, so a replay reproduces the row it first wrote instead of restamping
    # it with the replay's clock.
    now = iso_utc(utc_now())
    event: dict[str, Any] = {
        "memory_id": resolved_id,
        "kind": str(kind or MEMORY_KIND_OBSERVATION),
        "scope": str(scope or MEMORY_SCOPE_GLOBAL),
        "subject": subject.strip(),
        "body": body.strip(),
        "created_at": now,
        "superseded_by": None,
        "cited_by": [],
        "confidence": resolved_confidence,
        "valid_from": iso_utc(resolved_from) if resolved_from is not None else None,
        "valid_until": iso_utc(resolved_until) if resolved_until is not None else None,
        "change_conditions": change_conditions.strip(),
        "payload": stored,
    }

    entry = write_with_audit(
        audit=audit, store=store, event_type=MEMORY_EVENT_TYPE, payload=event, actor=actor
    )

    return MemoryReceipt(
        memory_id=resolved_id,
        audit_ref=str(entry.record_id),
        kind=str(event["kind"]),
        scope=str(event["scope"]),
        subject=str(event["subject"]),
        body=str(event["body"]),
        confidence=resolved_confidence,
        valid_from=event["valid_from"],
        valid_until=event["valid_until"],
        validity_open_ended=open_ended,
        change_conditions=str(event["change_conditions"]),
        evidence_ids=ids,
        created_at=now,
        superseded_by=None,
        cited_by=(),
        payload=stored,
    )
