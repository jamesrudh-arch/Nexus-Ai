"""The first writer for the intelligence-memory tables: ``evidence_ref`` (L-C, Stage 8.2).

Stage 6 built the table and left it empty. Nothing in ``src/`` had ever inserted into it, so the shape
was a promise nobody had kept: an evidence row that cannot say where it came from, when it was observed
and what its data status was cannot support a decision anyone can audit. This module keeps the promise
for one table, audited as ``evidence.recorded`` and projected through the existing write-ahead path, so
a crash between the audit entry and the row is a hole :func:`reproject_missing` can fill.

**The two timestamps are the point.** ``observed_at`` is the venue's own timestamp for the observation;
``retrieved_at`` is this system's clock at the moment it received it. Finding F-14 is that all four
adapters put *venue* time into ``observed_at`` and record no receipt time anywhere, so the interval
between the two — the only thing that would make latency measurable — does not currently exist in the
system. The owner's ruling for this batch was the cheap half: write both columns separately and leave
F-14 open rather than change four adapters inside a batch that is also rebuilding two tables. So:

* ``retrieved_at`` is a **required** argument with no default. Defaulting it to ``observed_at`` — or to
  "now" at write time, which is later than receipt — would manufacture a latency figure out of nothing,
  and a fabricated zero is worse than a missing number because it looks like a measurement.
* ``observed_at_source`` records whether the observation time really came from the venue. When it did
  not, the two timestamps are equal by construction, the row says so, and no consumer can read a latency
  off it. Passing ``LOCAL_FALLBACK`` with two *different* timestamps is refused: the flag would then be
  claiming something the row contradicts.
* The apparent interval is stored beside them as ``apparent_latency_seconds``. It is **not** a latency
  measurement. It is ``retrieved_at - observed_at``, which conflates network delay with the offset
  between the venue's clock and ours, and the venue's clock runs both ahead of and behind ours —
  run 27 measured 1.089 s of venue time against 0.298 s of wall clock. A negative value is not an error
  either; it is evidence that the venue's clock is ahead. Treating this number as latency is exactly the
  mistake F-14 exists to prevent, which is why it is written down next to the flag that qualifies it.

``kind`` is passed through as free text with the schema's default. No vocabulary for it is declared
anywhere in the repository — the only thing the schema says is ``DEFAULT 'DATA'`` — and inventing one
here would put a plausible-looking enum in front of a distinction nobody has yet drawn.

The refusals in this module raise ``ValueError``, following ``core.time.iso_utc``, which refuses a naive
datetime the same way. These are programmer errors at an internal boundary, not operational conditions,
so they get no ``RejectReason``: a reason code is vocabulary the audit log and the UI both consume, and
spending it on a call that should never have been written that way would dilute it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from nexus.audit.chain import sha256_hex
from nexus.core.ids import iso_utc, new_id
from nexus.data.freshness import DataStatus, MarketSnapshot
from nexus.store.serialise import dumps_canonical, to_jsonable
from nexus.store.writeahead import write_with_audit

__all__ = [
    "EVENT_TYPE",
    "EvidenceReceipt",
    "ObservedAtSource",
    "record_evidence",
    "record_snapshot",
    "snapshot_payload",
]

#: The audited event this writer emits. In ``writeahead.PROJECTABLE`` since Stage 8.2.
EVENT_TYPE = "evidence.recorded"

#: Evidence ids. The repository's test fixtures already used this prefix for evidence rows.
EVIDENCE_PREFIX = "EV"


class ObservedAtSource(StrEnum):
    """Where ``observed_at`` came from. The distinction is the whole content of finding F-14."""

    #: The venue published this timestamp. ``retrieved_at - observed_at`` then means something, up to
    #: the clock offset between the venue and us, which is not bounded anywhere in the system.
    VENUE = "VENUE"
    #: The venue published none, so the local clock stands in. The two timestamps are equal by
    #: construction and the row carries no latency information at all.
    LOCAL_FALLBACK = "LOCAL_FALLBACK"


def _aware(moment: datetime, name: str) -> datetime:
    """Refuse a naive datetime before any arithmetic is done with it.

    :func:`iso_utc` refuses one too, but it runs *after* the two timestamps have been subtracted, and a
    naive ``observed_at`` against an aware ``retrieved_at`` raises a bare ``TypeError`` from the
    subtraction — an unclassified crash at a point where nothing names the condition (the failure mode
    finding F-4 was about). Checking here puts the refusal at the boundary, with the argument named.
    """
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be an aware UTC datetime; got a naive {moment.isoformat()!r}")
    return moment


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    """What one write produced. Returned so the caller can cite the evidence it just recorded."""

    evidence_id: str
    audit_ref: str
    source: str
    kind: str
    observed_at: datetime
    retrieved_at: datetime
    observed_at_source: ObservedAtSource
    #: ``retrieved_at - observed_at`` in seconds. Conflates network delay with clock offset; may be
    #: negative. Not a latency measurement — see the module docstring.
    apparent_latency_seconds: float
    data_status: str
    checksum: str
    dossier_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "audit_ref": self.audit_ref,
            "source": self.source,
            "kind": self.kind,
            "observed_at": iso_utc(self.observed_at),
            "retrieved_at": iso_utc(self.retrieved_at),
            "observed_at_source": self.observed_at_source.value,
            "apparent_latency_seconds": self.apparent_latency_seconds,
            "data_status": self.data_status,
            "checksum": self.checksum,
            "dossier_id": self.dossier_id,
        }


def snapshot_payload(snapshot: MarketSnapshot) -> dict[str, Any]:
    """A market observation as evidence: the prices, and both of the snapshot's own time fields.

    ``MarketSnapshot`` carries ``observed_at`` *and* ``venue_timestamp``. Where the two disagree, that
    disagreement is evidence about the venue's clock and is preserved rather than resolved here.
    """
    return {
        "instrument_id": snapshot.instrument_id,
        "venue": snapshot.venue,
        "bid": str(snapshot.bid) if snapshot.bid is not None else None,
        "ask": str(snapshot.ask) if snapshot.ask is not None else None,
        "last": str(snapshot.last) if snapshot.last is not None else None,
        "mid": str(snapshot.mid) if snapshot.mid is not None else None,
        "spread": str(snapshot.spread) if snapshot.spread is not None else None,
        "delayed": snapshot.delayed,
        "delay_seconds": snapshot.delay_seconds,
        "source": snapshot.source,
        "venue_timestamp": (
            iso_utc(snapshot.venue_timestamp) if snapshot.venue_timestamp is not None else None
        ),
    }


def record_evidence(
    *,
    audit: Any,
    store: Any,
    source: str,
    observed_at: datetime,
    retrieved_at: datetime,
    payload: Mapping[str, Any] | None = None,
    kind: str = "DATA",
    data_status: DataStatus | str = DataStatus.UNAVAILABLE,
    locator: str = "",
    dossier_id: str | None = None,
    observed_at_source: ObservedAtSource = ObservedAtSource.VENUE,
    evidence_id: str | None = None,
    actor: str = "EVIDENCE",
) -> EvidenceReceipt:
    """Record one piece of evidence, audit entry first and projection second (L-2).

    ``audit`` and ``store`` are typed loosely to match :func:`write_with_audit`, which takes the same
    seam. ``data_status`` defaults to ``UNAVAILABLE`` — the fail-closed value, and the schema's own
    default: a writer that assumed ``LIVE`` would be asserting freshness it has not checked.
    """
    if not source:
        raise ValueError("evidence needs a source: an observation from nowhere cannot be audited")
    try:
        status = DataStatus(str(data_status))
    except ValueError as exc:
        raise ValueError(
            f"data_status must be one of {[member.value for member in DataStatus]}; got {data_status!r}"
        ) from exc

    observed_at = _aware(observed_at, "observed_at")
    retrieved_at = _aware(retrieved_at, "retrieved_at")
    latency = (retrieved_at - observed_at).total_seconds()
    if observed_at_source is ObservedAtSource.LOCAL_FALLBACK and latency != 0.0:
        raise ValueError(
            "observed_at_source=LOCAL_FALLBACK means the observation time is our own clock, so it "
            f"cannot differ from retrieved_at; got {latency:+.6f}s apart, which means the venue "
            "timestamp exists and should be passed with observed_at_source=VENUE"
        )

    # The provenance fields are written last so a caller's payload cannot overwrite them: they are what
    # makes the row interpretable, and a row that can be talked out of its own qualifications is a row
    # that will be.
    body: dict[str, Any] = dict(to_jsonable(dict(payload or {})))
    body.update(
        {
            "observed_at_source": observed_at_source.value,
            "apparent_latency_seconds": round(latency, 6),
        }
    )

    event: dict[str, Any] = {
        "evidence_id": evidence_id or new_id(EVIDENCE_PREFIX),
        "dossier_id": dossier_id,
        "source": source,
        "kind": kind,
        # iso_utc refuses a naive datetime, so an ambiguous timestamp cannot be recorded at all.
        "observed_at": iso_utc(observed_at),
        "retrieved_at": iso_utc(retrieved_at),
        "data_status": status.value,
        "locator": locator,
        # Computed here, over exactly what is stored, so the checksum cannot disagree with the payload.
        # This is an integrity checksum over the recorded row, not an authenticity signature over the
        # bytes the venue sent: nothing in this system can yet attest to those.
        "checksum": sha256_hex(dumps_canonical(body)),
        "payload": body,
    }

    entry = write_with_audit(audit=audit, store=store, event_type=EVENT_TYPE, payload=event, actor=actor)

    return EvidenceReceipt(
        evidence_id=str(event["evidence_id"]),
        audit_ref=str(entry.record_id),
        source=source,
        kind=kind,
        observed_at=observed_at,
        retrieved_at=retrieved_at,
        observed_at_source=observed_at_source,
        apparent_latency_seconds=round(latency, 6),
        data_status=status.value,
        checksum=str(event["checksum"]),
        dossier_id=dossier_id,
    )


def record_snapshot(
    *,
    audit: Any,
    store: Any,
    snapshot: MarketSnapshot,
    retrieved_at: datetime,
    kind: str = "DATA",
    data_status: DataStatus | str = DataStatus.UNAVAILABLE,
    locator: str = "",
    dossier_id: str | None = None,
    observed_at_source: ObservedAtSource = ObservedAtSource.VENUE,
    actor: str = "EVIDENCE",
) -> EvidenceReceipt:
    """Record one market observation as evidence.

    A snapshot with no ``observed_at`` is refused unless the caller says out loud that the local clock
    is standing in for the venue's. Substituting silently is the failure F-14 describes: the row would
    look like a measurement of latency and be a measurement of nothing.
    """
    retrieved_at = _aware(retrieved_at, "retrieved_at")
    observed = snapshot.observed_at
    if observed is None:
        if observed_at_source is not ObservedAtSource.LOCAL_FALLBACK:
            raise ValueError(
                "the snapshot carries no observed_at, so the venue published no timestamp for it; "
                "record it with observed_at_source=LOCAL_FALLBACK to say that the observation time is "
                "our own clock, or pass the venue's timestamp"
            )
        observed = retrieved_at
    return record_evidence(
        audit=audit,
        store=store,
        source=snapshot.source or snapshot.venue,
        observed_at=observed,
        retrieved_at=retrieved_at,
        payload=snapshot_payload(snapshot),
        kind=kind,
        data_status=data_status,
        locator=locator,
        dossier_id=dossier_id,
        observed_at_source=observed_at_source,
        actor=actor,
    )
