"""The second writer for the intelligence-memory tables: ``dossier`` (L-E, Stage 8.3).

Stage 6 built the table, Stage 8.2 gave ``dossier.instrument_id`` back its ``REFERENCES`` clause and
wrote the first of the three writers (``evidence_ref``), and nothing had ever opened a dossier. This
module does that, audited as ``dossier.opened`` and projected through the existing write-ahead path, so
a crash between the audit entry and the row is a hole :func:`reproject_missing` can fill.

**What a dossier is, from the documents that were approved before it existed.** ``docs/03`` J-04 is the
journey this table serves — "Research Case Review: understand why NEXUS is watching an instrument and
what would change its view" — and its exit condition is *"Owner understands what is known, what is
uncertain, and what would invalidate the thesis. Research completion ≠ trade signal."* ``docs/10`` §3.1
fixes the view: evidence graph, chronology, counter-thesis, quant result with run id, disposition plus
reason code, freshness, and a context rail carrying a *"knowledge-sufficiency meter with stated basis
and what it is sufficient for"*. ``docs/03`` §7 forbids hidden chain-of-thought: *"Auditable evidence +
structured findings + concise rationale only."* So the columns are used as designed — ``summary`` for
the thesis, ``stance`` for the disposition, ``uncertainty`` for what would change the view — and no
prose reasoning is smuggled into ``payload``.

**Three decisions this writer makes, each grounded rather than invented:**

* ``stance`` is validated against :class:`~nexus.domain.decision.DecisionVerb`, the seven-word
  vocabulary ACCEPT/REJECT/WAIT/REDUCE/EXIT/ESCALATE/ABSTAIN. Two things point at it: the schema's own
  default is ``'ABSTAIN'``, which is a ``DecisionVerb`` member and not a member of any other enum in the
  repository, and both ``docs/03`` §7 and ``docs/10`` §3.1 name that exact vocabulary for the
  intelligence layer's disposition. This is deliberately *not* the treatment ``evidence_ref.kind`` got
  in Stage 8.2, which is free text because no vocabulary for it is declared anywhere: where a vocabulary
  exists and the default belongs to it, using it is not invention, and leaving the column open would
  invite a second word for ABSTAIN. The column stays ``TEXT`` — the schema does not enforce this, the
  writer does.
* ``sufficiency`` stays a **string** until stage 10 defines the meter, because a judgement this system
  cannot yet compute should not be dressed as one. But the two payload keys ``sufficiency_basis`` and
  ``sufficiency_target`` are pinned, since that is what the approved rail asks for: the basis, and what
  it is sufficient *for*. Claiming anything other than ``INSUFFICIENT`` without both is refused —
  ``docs/10`` §3.2's warning is that *"a dossier that records sufficiency as a bare enum leaves nowhere
  for V1's outcome to live"* — and a **numeric** sufficiency is refused outright, because ``docs/12``
  §1.3's law (A-02+A-08) is that *no gate can be satisfied by a confidence value*, and ``"0.85"`` in
  this column is a confidence value wearing a judgement's name.
* A venue the instrument is **not** mapped on is *recorded, not refused*. ``venue_maps_instrument`` is
  computed from the master at open time and pinned into the payload, because the two cases mean
  different things to a reviewer: a case about a mapped pair is about something this system can observe,
  and a case about an unmapped pair is about a gap. Refusing the second would block the research the
  Intelligence Centre exists to hold — ``INS-EUR-USD`` on ``OANDA`` is a legitimate case today and the
  master maps EUR/USD at ``DUKASCOPY`` only. The flag is a snapshot: nothing re-checks it if the master
  moves afterwards.
* A dossier whose ``instrument_id`` is not in the system of record is refused. Migration
  ``0004_memory_fidelity`` declared the foreign key, but ``PRAGMA foreign_keys`` is deliberately off
  (``store/schema.py``'s module docstring), so SQLite would accept a dangling parent without comment.
  This is what makes Stage 8.2's L-B load-bearing rather than decorative: before the seeded master was
  projected there was no parent row for a dossier to point at, and the honest failure would have been
  silent. ``instrument_id=None`` is allowed and means the case is not about one instrument.

**Opening is not editing.** A caller-supplied ``dossier_id`` that already exists is refused. The store
writes with ``INSERT OR REPLACE`` because it is a *projection*, so a second "open" would restate the
first row's stance and summary in the read model; the audit chain would still hold both events, so
nothing is lost durably, but the row a reviewer reads would no longer be the row that was opened.
``docs/15`` §5.1 records the principle — *"memory is superseded, never edited in place"* — which is why
``memory_item.superseded_by`` exists. Changing a stance is a later batch's verb with its own audit
event, not a second call to this one.

``created_at`` and ``updated_at`` travel **inside** the audited event. The applied schema has no
``DEFAULT now()`` for either (one of the four defaults ``docs/15`` §9.1 classifies as a house
convention), so a projection that filled them at write time would restamp a replayed event with the
replay's clock — and boot recovery would quietly rewrite the chronology J-04 asks the view to show.

What this module does **not** do, named rather than left to be discovered: J-04 step 2 asks the evidence
table for a **publication time** and ``evidence_ref`` holds observation and receipt time only, so a
source's own publication moment is not recordable anywhere; J-04 step 1 asks for a **counter-thesis**
and no column exists for one; ``docs/10`` §3.1 asks for research depth **Tier 0–4** and **contradictions
highlighted and linked**, and the first has no column while the second needs ``evidence_ref.contradicts``,
which D-051 deferred to the stage-10 batch. None of those is invented here to make the row look complete.

*(Pointer added by Stage 8.5, which is that batch: ``evidence_ref.contradicts`` now exists — migration
``0005_memory_beliefs``, F-18's fourth gap — and ``record_evidence`` accepts it, refuses a dangling one and
covers it with the row checksum. The paragraph above is left as this module was ruled, because what it says
about **this** writer is unchanged: ``open_dossier`` still invents no contradiction, no counter-thesis and no
tier, and it still has no column of its own for any of them. What Stage 8.5 changes is that a case's evidence
rows can now disagree on the record, and the route serves both directions of that link. Publication time,
counter-thesis and Tier 0–4 remain exactly as unrecordable as they were.)*
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionVerb
from nexus.domain.instrument import Venue
from nexus.store.serialise import to_jsonable
from nexus.store.writeahead import write_with_audit

__all__ = [
    "DOSSIER_EVENT_TYPE",
    "DOSSIER_PREFIX",
    "SUFFICIENCY_BASIS_KEY",
    "SUFFICIENCY_INSUFFICIENT",
    "SUFFICIENCY_TARGET_KEY",
    "VENUE_MAPS_INSTRUMENT_KEY",
    "DossierReceipt",
    "open_dossier",
    "sufficiency_of",
]

#: The audited event this writer emits. In ``writeahead.PROJECTABLE`` since Stage 8.3.
DOSSIER_EVENT_TYPE = "dossier.opened"

#: ``core.ids.new_id``'s own prefix table has declared ``CASE research case`` since Phase 2 and nothing
#: had ever spent it; ``docs/03`` J-04 calls these "Research Dossiers → selects case".
DOSSIER_PREFIX = "CASE"

#: The schema's default, and the only value that needs no basis: it claims nothing.
SUFFICIENCY_INSUFFICIENT = "INSUFFICIENT"

#: The pinned payload keys, named once so the writer and the route cannot drift apart.
SUFFICIENCY_BASIS_KEY = "sufficiency_basis"
SUFFICIENCY_TARGET_KEY = "sufficiency_target"
#: Computed at open, not supplied by the caller: whether the master really maps this instrument on this
#: venue. See :func:`open_dossier`.
VENUE_MAPS_INSTRUMENT_KEY = "venue_maps_instrument"

#: The default state. ``DRAFT`` means not yet dispositioned, not "not yet described" — see ``summary``.
DOSSIER_STATE_DRAFT = "DRAFT"


def _is_numeric(text: str) -> bool:
    """True when ``text`` is a number wearing a judgement's name."""
    try:
        float(text)
    except ValueError:
        return False
    return True


def sufficiency_of(row: Mapping[str, Any]) -> dict[str, Any]:
    """Lift the sufficiency judgement and its two pinned qualifiers out of one dossier row.

    The keys live in exactly one place so the writer that pins them and the route that serves them
    cannot disagree about their names — the same reason ``_gap_bps`` exists once for P-9. A row whose
    payload predates this writer (there are none today, and the route says so when it meets one) yields
    empty qualifiers rather than invented ones.
    """
    payload = row.get("payload")
    body = payload if isinstance(payload, Mapping) else {}
    return {
        "sufficiency": str(row.get("sufficiency") or SUFFICIENCY_INSUFFICIENT),
        SUFFICIENCY_BASIS_KEY: str(body.get(SUFFICIENCY_BASIS_KEY) or ""),
        SUFFICIENCY_TARGET_KEY: str(body.get(SUFFICIENCY_TARGET_KEY) or ""),
    }


@dataclass(frozen=True, slots=True)
class DossierReceipt:
    """What one open produced. Returned so the caller can cite the case it just opened."""

    dossier_id: str
    audit_ref: str
    instrument_id: str | None
    venue: str | None
    state: str
    #: The thesis in one line — required, and the first thing ``docs/03`` J-04 step 1 renders.
    summary: str
    stance: str
    #: What is unresolved. Required whenever ``stance`` is ``ABSTAIN``.
    uncertainty: str
    sufficiency: str
    sufficiency_basis: str
    sufficiency_target: str
    #: Computed from the master at open: does this venue really map this instrument? ``None`` when
    #: either is absent. A snapshot — nothing re-checks it if the master moves.
    venue_maps_instrument: bool | None
    created_at: str
    updated_at: str
    #: Caller payload plus the two pinned sufficiency keys, which the writer always wins.
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "audit_ref": self.audit_ref,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "state": self.state,
            "summary": self.summary,
            "stance": self.stance,
            "uncertainty": self.uncertainty,
            "sufficiency": self.sufficiency,
            SUFFICIENCY_BASIS_KEY: self.sufficiency_basis,
            SUFFICIENCY_TARGET_KEY: self.sufficiency_target,
            VENUE_MAPS_INSTRUMENT_KEY: self.venue_maps_instrument,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "payload": dict(self.payload),
        }


def open_dossier(
    *,
    audit: Any,
    store: Any,
    summary: str,
    instrument_id: str | None = None,
    venue: Venue | str | None = None,
    stance: DecisionVerb | str = DecisionVerb.ABSTAIN,
    state: str = DOSSIER_STATE_DRAFT,
    uncertainty: str = "",
    sufficiency: str = SUFFICIENCY_INSUFFICIENT,
    sufficiency_basis: str = "",
    sufficiency_target: str = "",
    payload: Mapping[str, Any] | None = None,
    dossier_id: str | None = None,
    actor: str = "INTELLIGENCE",
) -> DossierReceipt:
    """Open one research dossier, audit entry first and projection second (L-2).

    ``audit`` and ``store`` are typed loosely to match :func:`write_with_audit`, which takes the same
    seam. Every default is the ABSTAIN side: ``stance=ABSTAIN``, ``state='DRAFT'``,
    ``sufficiency='INSUFFICIENT'``, because this package's rule is that an intelligence record which can
    be created without a basis is a record that will be.

    Raises ``ValueError`` for a call that should not have been written that way, following
    :mod:`nexus.intelligence.evidence` and :func:`nexus.core.time.iso_utc`. No ``RejectReason`` is
    spent: these are programmer errors at an internal boundary, not operational conditions, and a reason
    code is vocabulary the audit log and the UI both consume.
    """
    if not summary.strip():
        raise ValueError(
            "a dossier needs a summary: it is the thesis in one line, the 'concise rationale' docs/03 §7 "
            "permits and the first thing J-04 step 1 renders. A case that cannot say what it is about "
            "cannot be reviewed, and state='DRAFT' means not yet dispositioned, not not yet described"
        )

    try:
        resolved_stance = DecisionVerb(str(stance))
    except ValueError as exc:
        raise ValueError(
            f"stance must be one of {[member.value for member in DecisionVerb]}; got {stance!r}. The "
            "schema's own default 'ABSTAIN' is a DecisionVerb member, and docs/03 §7 and docs/10 §3.1 "
            "both name that vocabulary for the intelligence layer's disposition"
        ) from exc

    if venue is not None:
        try:
            resolved_venue: str | None = Venue(str(venue)).value
        except ValueError as exc:
            raise ValueError(
                f"venue must be one of {[member.value for member in Venue]} or None; got {venue!r}. None "
                "means the case is not about one venue, which is a statement — an unrecognised string is "
                "not one"
            ) from exc
    else:
        resolved_venue = None

    resolved_sufficiency = str(sufficiency or "").strip()
    if not resolved_sufficiency:
        resolved_sufficiency = SUFFICIENCY_INSUFFICIENT
    if _is_numeric(resolved_sufficiency):
        raise ValueError(
            f"sufficiency must be a judgement, not a number; got {resolved_sufficiency!r}. docs/12 §1.3's "
            "law (A-02+A-08) is that no gate can be satisfied by a confidence value, and a numeric "
            "sufficiency is a confidence value in a judgement's column — the meter stage 10 defines will "
            "read this string, not the other way round"
        )
    if resolved_sufficiency != SUFFICIENCY_INSUFFICIENT and not (
        sufficiency_basis.strip() and sufficiency_target.strip()
    ):
        raise ValueError(
            f"sufficiency={resolved_sufficiency!r} claims a judgement, so it needs both "
            f"{SUFFICIENCY_BASIS_KEY} (what it rests on) and {SUFFICIENCY_TARGET_KEY} (what it is "
            "sufficient FOR) — docs/10 §3.1's rail carries 'stated basis and what it is sufficient for', "
            "and §3.2's warning is that a bare enum leaves nowhere for V1's outcome to live. "
            f"{SUFFICIENCY_INSUFFICIENT!r} needs neither, because it claims nothing"
        )

    if resolved_stance is DecisionVerb.ABSTAIN and not uncertainty.strip():
        raise ValueError(
            "stance=ABSTAIN needs a non-empty uncertainty: the schema's comment is that ABSTAIN is the "
            "default and not a fallback, and an abstention that does not say what is unresolved is a "
            "fallback. J-04's exit condition is that the owner learns what would invalidate the thesis"
        )

    if instrument_id is not None:
        wanted = str(instrument_id)
        if not wanted:
            raise ValueError("instrument_id must be a real id or None; an empty string is neither")
        held = frozenset(str(row.get("instrument_id") or "") for row in store.instruments())
        if wanted not in held:
            raise ValueError(
                f"instrument {wanted!r} is not in the system of record, which holds {len(held)}: "
                f"{sorted(held)}. dossier.instrument_id REFERENCES instrument since migration "
                "0004_memory_fidelity, but PRAGMA foreign_keys is deliberately off, so SQLite would "
                "accept this dangling parent without comment — project the instrument first (Stage 8.2's "
                "L-B) or open the case with instrument_id=None"
            )
        resolved_instrument: str | None = wanted
    else:
        resolved_instrument = None

    resolved_id = str(dossier_id or "") or new_id(DOSSIER_PREFIX)
    if dossier_id is not None and store.get_dossier(resolved_id) is not None:
        raise ValueError(
            f"dossier {resolved_id!r} already exists, and opening is not editing: the store writes with "
            "INSERT OR REPLACE because it is a projection, so a second open would restate the first "
            "row's stance and summary. The audit chain would keep both events, but the row a reviewer "
            "reads would no longer be the row that was opened. Memory is superseded, never edited in "
            "place (docs/15 §5.1); changing a stance is a later verb with its own event"
        )

    if resolved_instrument is None or resolved_venue is None:
        mapped: bool | None = None
    else:
        mapped = resolved_venue in frozenset(
            str(row.get("venue") or "") for row in store.venue_mappings(instrument_id=resolved_instrument)
        )

    # The pinned keys are written last so a caller's payload cannot overwrite them: they are what makes
    # the sufficiency claim interpretable, and a claim that can be talked out of its own basis is a
    # claim that will be.
    body: dict[str, Any] = dict(to_jsonable(dict(payload or {})))
    body.update(
        {
            SUFFICIENCY_BASIS_KEY: sufficiency_basis.strip(),
            SUFFICIENCY_TARGET_KEY: sufficiency_target.strip(),
            VENUE_MAPS_INSTRUMENT_KEY: mapped,
        }
    )

    # Both timestamps ride in the event, so a replay reproduces the row it first wrote instead of
    # restamping it with the replay's clock.
    now = iso_utc(utc_now())
    event: dict[str, Any] = {
        "dossier_id": resolved_id,
        "instrument_id": resolved_instrument,
        "venue": resolved_venue,
        "created_at": now,
        "updated_at": now,
        "state": state,
        "summary": summary.strip(),
        "stance": resolved_stance.value,
        "uncertainty": uncertainty.strip(),
        "sufficiency": resolved_sufficiency,
        "payload": body,
    }

    entry = write_with_audit(
        audit=audit, store=store, event_type=DOSSIER_EVENT_TYPE, payload=event, actor=actor
    )

    return DossierReceipt(
        dossier_id=resolved_id,
        audit_ref=str(entry.record_id),
        instrument_id=resolved_instrument,
        venue=resolved_venue,
        state=state,
        summary=str(event["summary"]),
        stance=resolved_stance.value,
        uncertainty=str(event["uncertainty"]),
        sufficiency=resolved_sufficiency,
        sufficiency_basis=str(body[SUFFICIENCY_BASIS_KEY]),
        sufficiency_target=str(body[SUFFICIENCY_TARGET_KEY]),
        venue_maps_instrument=mapped,
        created_at=now,
        updated_at=now,
        payload=body,
    )
