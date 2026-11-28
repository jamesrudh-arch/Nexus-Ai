"""Projecting the instrument master into the system of record (L-B, finding F-16).

Stage 7.3 seeded three instruments and four venue mappings into :class:`InstrumentRegistry`, and the
seeding is idempotent, evidenced and tested. None of it ever reached persistence: the count under both
backends was ``instrument_master = 3`` beside ``persistence.counts.instrument = 0``. The reason was not
a missing mechanism. ``instrument.registered`` was already in :data:`PROJECTABLE`, the dispatcher
already routed it to :meth:`save_instrument`, and :func:`reproject_missing` would already have replayed
it from the chain — but nothing ever appended such a record, so there was nothing to replay. What was
missing was the emitter, and this module is it.

Two consequences are worth stating because they follow from the projection being real:

*A dossier written before this existed would have referenced an instrument the system of record had
never heard of, through a constraint that did not exist, and been accepted silently.* Migration 0004
restores the constraint; this module supplies the parent rows it points at.

*The payload is built from the domain objects, not from the registry's serialiser.*
:func:`nexus.instruments.registry._mapping_to_dict` is a read-model for the API and omits
``margin_rate`` and ``fees`` — the two fields that make a mapping an economic description rather than a
symbol translation. Projecting through it would have written the four seeded mappings with the margin
rate and the published fees missing into columns that exist to hold them, and no test would have
noticed, because both are nullable.

The payload also carries **no timestamps of its own**. A projection that stamps itself at call time
produces a different digest every boot, so every boot appends an audit record for an instrument that
has not changed — an audit chain that grows without describing anything. Everything here derives from
the instrument alone, which is what makes "call this at every boot" safe, and
:func:`project_master` compares digests so an unchanged master appends nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.domain.instrument import CanonicalInstrument, VenueMapping
from nexus.instruments.registry import InstrumentRegistry
from nexus.store.serialise import dumps_canonical, to_jsonable
from nexus.store.writeahead import write_with_audit

__all__ = [
    "EVENT_TYPE",
    "MasterProjection",
    "instrument_payload",
    "mapping_payload",
    "project_master",
]

#: The audited event this projection emits. Already in ``writeahead.PROJECTABLE``.
EVENT_TYPE = "instrument.registered"


def _dec(value: Any) -> str | None:
    """A Decimal as its exact string form, or None. Never a float — see ``store.serialise``."""
    return None if value is None else str(value)


def mapping_payload(mapping: VenueMapping) -> dict[str, Any]:
    """One venue mapping as it will be audited and projected: every field, in enum-value form."""
    return {
        "venue": mapping.venue.value,
        "venue_symbol": mapping.venue_symbol,
        "status": mapping.status.value,
        "contract_size": _dec(mapping.contract_size),
        "tick_size": _dec(mapping.tick_size),
        "tick_value": _dec(mapping.tick_value),
        "min_order_qty": _dec(mapping.min_order_qty),
        "max_order_qty": _dec(mapping.max_order_qty),
        "qty_step": _dec(mapping.qty_step),
        "quote_currency": mapping.quote_currency,
        "settlement_currency": mapping.settlement_currency,
        "trading_hours": mapping.trading_hours,
        "margin_rate": _dec(mapping.margin_rate),
        "fees": to_jsonable(dict(mapping.fees)),
        "notes": mapping.notes,
    }


def instrument_payload(instrument: CanonicalInstrument) -> dict[str, Any]:
    """The whole projection of one instrument: its identity, and how each venue trades it.

    No ``created_at``: :meth:`save_instrument` stamps the row on write, and putting a fresh timestamp
    in the payload would make the digest differ on every call.
    """
    return {
        "instrument_id": instrument.instrument_id,
        "canonical_symbol": instrument.canonical_symbol,
        "asset_class": instrument.asset_class.value,
        "base_currency": instrument.base_currency,
        "quote_currency": instrument.quote_currency,
        "settlement_currency": instrument.settlement_currency,
        "underlying": instrument.underlying,
        "expiry": instrument.expiry,
        "strike": _dec(instrument.strike),
        "option_type": instrument.option_type,
        "active": instrument.active,
        "data_status": instrument.data_status,
        "notes": instrument.notes,
        "mappings": [mapping_payload(mapping) for mapping in instrument.mappings],
    }


@dataclass(frozen=True, slots=True)
class MasterProjection:
    """What one :func:`project_master` call did. Empty ``projected`` means the master was already there."""

    #: Instrument ids written, sorted.
    projected: tuple[str, ...]
    #: Instrument ids whose stored projection was already byte-identical, so nothing was appended.
    unchanged: tuple[str, ...]
    #: One audit record id per projected instrument — the chain entries the rows came from.
    audit_refs: tuple[str, ...]
    #: Mapping rows written. A re-projection replaces them; it never duplicates them.
    mappings: int

    @property
    def changed(self) -> bool:
        return bool(self.projected)


def project_master(
    registry: InstrumentRegistry,
    *,
    audit: Any,
    store: Any,
    actor: str = "INSTRUMENT-MASTER",
) -> MasterProjection:
    """Write every instrument in the master into the system of record, audit entry first (L-2).

    Safe at every boot. An instrument whose canonical payload is byte-identical to what is already
    stored appends nothing, so a second call is a no-op in the audit chain as well as in the tables;
    one whose rank climbed, whose notes changed or whose mappings moved is re-audited and re-projected,
    because that is a change worth having a record of.

    ``audit`` and ``store`` are typed loosely to match :func:`write_with_audit`, which takes the same
    seam.
    """
    stored: dict[str, Any] = {}
    for row in store.instruments():
        stored[str(row.get("instrument_id"))] = row.get("payload") or {}

    projected: list[str] = []
    unchanged: list[str] = []
    refs: list[str] = []
    mappings = 0

    for instrument in sorted(registry.all(), key=lambda item: item.instrument_id):
        payload = instrument_payload(instrument)
        if dumps_canonical(stored.get(instrument.instrument_id)) == dumps_canonical(payload):
            unchanged.append(instrument.instrument_id)
            continue
        entry = write_with_audit(
            audit=audit,
            store=store,
            event_type=EVENT_TYPE,
            payload=payload,
            actor=actor,
        )
        projected.append(instrument.instrument_id)
        refs.append(str(entry.record_id))
        mappings += len(instrument.mappings)

    return MasterProjection(
        projected=tuple(projected),
        unchanged=tuple(unchanged),
        audit_refs=tuple(refs),
        mappings=mappings,
    )
