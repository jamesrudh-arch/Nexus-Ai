"""Canonical instrument master (Section 3.1, Section 11.6) — Phase 3.

One economic instrument, many venue representations. ``BTCUSD`` on a CFD broker is never
assumed equal to ``BTCUSDT`` on a perp exchange: different contract size, different tick
size, different funding, different hours, different margin. The registry is therefore the
single source of truth that ingestion, risk and execution all resolve through.

Governance properties enforced here (and pinned by tests):

* **Nothing is active by default** (D-002). An instrument registered with ``active=True``
  is stored as inactive; activation is an explicit, separately audited act.
* **Capability states never skip.** ``UNKNOWN -> SUPPORTED -> CONNECTED -> DATA_AVAILABLE
  -> TRADE_ENABLED -> LIVE_VERIFIED`` advances exactly one step at a time, each step
  requiring evidence. De-escalation is always allowed and always recorded.
* **Data is not permission.** ``DATA_AVAILABLE`` never implies ``TRADE_ENABLED``.
* **Reverse lookups are unique.** A ``(venue, venue_symbol)`` pair resolves to exactly one
  canonical instrument; a collision is refused rather than silently overwritten.
* **The change log is append-only.** Every mutation produces a record safe to audit: no
  free text from untrusted sources, no secret material.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.instrument import (
    AssetClass,
    CanonicalInstrument,
    InstrumentId,
    Venue,
    VenueMapping,
    VenueStatus,
)

# The certification ladder. Index == rank; a promotion must land exactly one rank higher.
CERTIFICATION_ORDER: tuple[VenueStatus, ...] = (
    VenueStatus.UNKNOWN,
    VenueStatus.SUPPORTED,
    VenueStatus.CONNECTED,
    VenueStatus.DATA_AVAILABLE,
    VenueStatus.TRADE_ENABLED,
    VenueStatus.LIVE_VERIFIED,
)


def certification_rank(status: VenueStatus) -> int:
    """Position of ``status`` on the ladder. Unknown values rank lowest (fail closed)."""
    try:
        return CERTIFICATION_ORDER.index(status)
    except ValueError:
        return -1


def is_certification_advance(current: VenueStatus, target: VenueStatus) -> bool:
    """True only when ``target`` is exactly one rung above ``current``."""
    return certification_rank(target) == certification_rank(current) + 1


class InstrumentError(NexusError):
    """Raised for any registry refusal."""


class UnknownInstrument(InstrumentError):
    """The requested instrument is not in the master registry."""

    def __init__(self, instrument_id: str) -> None:
        super().__init__(RejectReason.INSTRUMENT_UNKNOWN, f"unknown instrument: {instrument_id}")


class CertificationRejected(InstrumentError):
    """A capability state change was refused."""

    def __init__(self, detail: str) -> None:
        super().__init__(RejectReason.INSTRUMENT_NOT_CERTIFIED, detail)


@dataclass(frozen=True, slots=True)
class RegistryChange:
    """Append-only record of one registry mutation. Audit-safe: evidence is a short
    label, never a credential, a balance or a position."""

    change_id: str
    kind: str  # REGISTER | ACTIVATE | DEACTIVATE | CERTIFY | DE_CERTIFY | REMAP
    instrument_id: InstrumentId
    venue: str | None
    venue_symbol: str | None
    from_status: str | None
    to_status: str | None
    evidence: str
    changed_at: datetime
    requested_by: str = "SYSTEM"

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "kind": self.kind,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "venue_symbol": self.venue_symbol,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "evidence": self.evidence[:200],  # bounded: evidence is a label, not a payload
            "changed_at": iso_utc(self.changed_at),
            "requested_by": self.requested_by,
        }


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """Read-only view of the master, for the API and for reports."""

    instruments: tuple[CanonicalInstrument, ...]
    changes: tuple[RegistryChange, ...]
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.instruments),
            "active_count": sum(1 for i in self.instruments if i.active),
            "instruments": [_instrument_to_dict(i) for i in self.instruments],
            "generated_at": iso_utc(self.generated_at),
        }


def _mapping_to_dict(mapping: VenueMapping) -> dict[str, Any]:
    """Serialise a venue mapping. Decimal fields become strings so no precision is lost."""
    return {
        "venue": mapping.venue.value,
        "venue_symbol": mapping.venue_symbol,
        "status": mapping.status.value,
        "contract_size": str(mapping.contract_size) if mapping.contract_size is not None else None,
        "tick_size": str(mapping.tick_size) if mapping.tick_size is not None else None,
        "tick_value": str(mapping.tick_value) if mapping.tick_value is not None else None,
        "min_order_qty": str(mapping.min_order_qty) if mapping.min_order_qty is not None else None,
        "max_order_qty": str(mapping.max_order_qty) if mapping.max_order_qty is not None else None,
        "qty_step": str(mapping.qty_step) if mapping.qty_step is not None else None,
        "quote_currency": mapping.quote_currency,
        "settlement_currency": mapping.settlement_currency,
        "trading_hours": mapping.trading_hours,
        "is_tradeable": mapping.is_tradeable,
    }


def _instrument_to_dict(instrument: CanonicalInstrument) -> dict[str, Any]:
    return {
        "instrument_id": instrument.instrument_id,
        "canonical_symbol": instrument.canonical_symbol,
        "asset_class": instrument.asset_class.value,
        "base_currency": instrument.base_currency,
        "quote_currency": instrument.quote_currency,
        "settlement_currency": instrument.settlement_currency,
        "underlying": instrument.underlying,
        "expiry": instrument.expiry,
        "strike": str(instrument.strike) if instrument.strike is not None else None,
        "option_type": instrument.option_type,
        "active": instrument.active,
        "data_status": instrument.data_status,
        "mappings": [_mapping_to_dict(m) for m in instrument.mappings],
        "tradeable_venues": [v.value for v in instrument.tradeable_venues()],
        "highest_status": max(
            (m.status for m in instrument.mappings),
            key=certification_rank,
            default=VenueStatus.UNKNOWN,
        ).value,
    }


class InstrumentRegistry:
    """The canonical instrument master.

    Thread-safety: single-process, single-writer by design. Ingestion, research and the
    API read through :meth:`resolve` / :meth:`get`, which never mutate.
    """

    def __init__(self, *, now_fn: Any = utc_now) -> None:
        self._instruments: dict[InstrumentId, CanonicalInstrument] = {}
        self._by_symbol: dict[str, InstrumentId] = {}
        self._by_venue_symbol: dict[tuple[str, str], InstrumentId] = {}
        self._changes: list[RegistryChange] = []
        self._now_fn = now_fn

    # ------------------------------------------------------------------ read API

    def __len__(self) -> int:
        return len(self._instruments)

    def __contains__(self, instrument_id: object) -> bool:
        return isinstance(instrument_id, str) and instrument_id in self._instruments

    @property
    def changes(self) -> tuple[RegistryChange, ...]:
        return tuple(self._changes)

    def get(self, instrument_id: InstrumentId) -> CanonicalInstrument | None:
        return self._instruments.get(instrument_id)

    def require(self, instrument_id: InstrumentId) -> CanonicalInstrument:
        instrument = self._instruments.get(instrument_id)
        if instrument is None:
            raise UnknownInstrument(instrument_id)
        return instrument

    def by_symbol(self, canonical_symbol: str) -> CanonicalInstrument | None:
        instrument_id = self._by_symbol.get(canonical_symbol.strip().upper())
        return self._instruments.get(instrument_id) if instrument_id else None

    def resolve(
        self, venue: Venue | str, venue_symbol: str
    ) -> tuple[CanonicalInstrument, VenueMapping] | None:
        """Resolve a venue's own symbol to the canonical instrument and its mapping.

        This is the entry point every adapter uses. Returning ``None`` means *unknown*,
        which downstream treats as ``INSTRUMENT_UNKNOWN`` — never as a guess.
        """
        key = (str(venue), venue_symbol.strip())
        instrument_id = self._by_venue_symbol.get(key)
        if instrument_id is None:
            return None
        instrument = self._instruments.get(instrument_id)
        if instrument is None:
            return None
        mapping = (
            instrument.mapping_for(Venue(key[0])) if isinstance(venue, str) else instrument.mapping_for(venue)
        )
        if mapping is None:
            return None
        return instrument, mapping

    def all(self) -> tuple[CanonicalInstrument, ...]:
        return tuple(self._instruments.values())

    def active(self) -> tuple[CanonicalInstrument, ...]:
        return tuple(i for i in self._instruments.values() if i.active)

    def by_asset_class(self, asset_class: AssetClass) -> tuple[CanonicalInstrument, ...]:
        return tuple(i for i in self._instruments.values() if i.asset_class == asset_class)

    def tradeable(self) -> tuple[CanonicalInstrument, ...]:
        """Instruments with at least one venue mapping certified for trading."""
        return tuple(i for i in self._instruments.values() if i.tradeable_venues())

    def snapshot(self) -> RegistrySnapshot:
        return RegistrySnapshot(
            instruments=self.all(),
            changes=self.changes,
            generated_at=self._now_fn(),
        )

    # ------------------------------------------------------------------ write API

    def register(
        self,
        instrument: CanonicalInstrument,
        *,
        source: str = "MANUAL",
        requested_by: str = "SYSTEM",
    ) -> CanonicalInstrument:
        """Add a canonical instrument. Idempotent for an identical re-registration.

        Refuses: duplicate canonical symbol under a different id, or a ``(venue, symbol)``
        pair already bound to another instrument. ``active`` is forced to ``False`` —
        activation is a separate, explicit decision (D-002).
        """
        symbol = instrument.canonical_symbol.strip().upper()
        stored = replace(instrument, canonical_symbol=symbol, active=False)

        existing_id = self._by_symbol.get(symbol)
        if existing_id is not None and existing_id != stored.instrument_id:
            raise CertificationRejected(
                f"canonical symbol {symbol} already registered as {existing_id}",
            )

        collisions = [
            (m.venue.value, m.venue_symbol)
            for m in stored.mappings
            if self._by_venue_symbol.get((m.venue.value, m.venue_symbol)) not in (None, stored.instrument_id)
        ]
        if collisions:
            raise CertificationRejected(
                f"venue symbol(s) already bound to another instrument: {collisions}",
            )

        if stored.instrument_id in self._instruments:
            current = self._instruments[stored.instrument_id]
            if current == stored:
                return stored  # idempotent: nothing to record
            self._index(stored)
            self._record(
                kind="REMAP",
                instrument_id=stored.instrument_id,
                venue=None,
                venue_symbol=symbol,
                from_status=None,
                to_status=None,
                evidence=f"re-registered from {source}",
                requested_by=requested_by,
            )
            return stored

        self._index(stored)
        self._record(
            kind="REGISTER",
            instrument_id=stored.instrument_id,
            venue=None,
            venue_symbol=symbol,
            from_status=None,
            to_status=VenueStatus.UNKNOWN.value if not stored.mappings else None,
            evidence=f"source={source} mappings={len(stored.mappings)} active=False",
            requested_by=requested_by,
        )
        return stored

    def add_mapping(
        self,
        instrument_id: InstrumentId,
        mapping: VenueMapping,
        *,
        source: str = "MANUAL",
        requested_by: str = "SYSTEM",
    ) -> CanonicalInstrument:
        """Attach a venue representation. Status always starts at ``UNKNOWN``."""
        instrument = self.require(instrument_id)
        safe_mapping = replace(mapping, status=VenueStatus.UNKNOWN)
        if instrument.mapping_for(safe_mapping.venue) is not None:
            raise CertificationRejected(
                f"{safe_mapping.venue.value} already mapped for {instrument_id}; "
                f"use certify() to change state",
            )
        bound = self._by_venue_symbol.get((safe_mapping.venue.value, safe_mapping.venue_symbol))
        if bound is not None and bound != instrument_id:
            raise CertificationRejected(
                f"{safe_mapping.venue.value}:{safe_mapping.venue_symbol} is bound to {bound}",
            )
        updated = replace(instrument, mappings=(*instrument.mappings, safe_mapping))
        self._index(updated)
        self._record(
            kind="REMAP",
            instrument_id=instrument_id,
            venue=safe_mapping.venue.value,
            venue_symbol=safe_mapping.venue_symbol,
            from_status=None,
            to_status=VenueStatus.UNKNOWN.value,
            evidence=f"mapping added from {source}",
            requested_by=requested_by,
        )
        return updated

    def certify(
        self,
        instrument_id: InstrumentId,
        venue: Venue,
        to_status: VenueStatus,
        *,
        evidence: str,
        requested_by: str = "SYSTEM",
        now: datetime | None = None,
    ) -> CanonicalInstrument:
        """Move one venue mapping along the certification ladder.

        A promotion must advance exactly one rung and must carry evidence. A demotion
        (or restatement of the same status) is always permitted and is recorded as
        ``DE_CERTIFY`` — losing access is never an error to hide.
        """
        if not evidence.strip():
            raise CertificationRejected("certification requires evidence; an empty label is not proof")

        instrument = self.require(instrument_id)
        mapping = instrument.mapping_for(venue)
        if mapping is None:
            raise CertificationRejected(f"{venue.value} has no mapping on {instrument_id}")

        current = mapping.status
        if to_status == current:
            return instrument  # no-op, nothing to audit
        if certification_rank(to_status) < certification_rank(current):
            return self._set_status(
                instrument,
                mapping,
                to_status,
                kind="DE_CERTIFY",
                evidence=evidence,
                requested_by=requested_by,
                now=now,
            )
        if not is_certification_advance(current, to_status):
            raise CertificationRejected(
                f"{venue.value} on {instrument_id}: cannot move {current.value} -> {to_status.value}; "
                f"the ladder advances one step at a time ({[s.value for s in CERTIFICATION_ORDER]})",
            )
        return self._set_status(
            instrument,
            mapping,
            to_status,
            kind="CERTIFY",
            evidence=evidence,
            requested_by=requested_by,
            now=now,
        )

    def _set_status(
        self,
        instrument: CanonicalInstrument,
        mapping: VenueMapping,
        to_status: VenueStatus,
        *,
        kind: str,
        evidence: str,
        requested_by: str,
        now: datetime | None,
    ) -> CanonicalInstrument:
        updated_mapping = replace(mapping, status=to_status)
        updated = replace(
            instrument,
            mappings=tuple(updated_mapping if m.venue == mapping.venue else m for m in instrument.mappings),
        )
        self._index(updated)
        self._record(
            kind=kind,
            instrument_id=instrument.instrument_id,
            venue=mapping.venue.value,
            venue_symbol=mapping.venue_symbol,
            from_status=mapping.status.value,
            to_status=to_status.value,
            evidence=evidence,
            requested_by=requested_by,
            now=now,
        )
        return updated

    def set_data_status(
        self,
        instrument_id: InstrumentId,
        data_status: str,
        *,
        source: str = "INGESTION",
    ) -> CanonicalInstrument:
        """Record the honest data state: LIVE | DELAYED | STALE | UNAVAILABLE | FAULT."""
        instrument = self.require(instrument_id)
        if instrument.data_status == data_status:
            return instrument
        updated = replace(instrument, data_status=data_status)
        self._instruments[instrument_id] = updated
        self._record(
            kind="CERTIFY",
            instrument_id=instrument_id,
            venue=None,
            venue_symbol=instrument.canonical_symbol,
            from_status=instrument.data_status,
            to_status=data_status,
            evidence=f"data status from {source}",
        )
        return updated

    def activate(
        self,
        instrument_id: InstrumentId,
        *,
        for_trading: bool = False,
        reason: str,
        requested_by: str = "OWNER",
    ) -> CanonicalInstrument:
        """Staged activation (D-002).

        ``for_trading=True`` additionally requires a venue mapping already certified to
        ``TRADE_ENABLED`` or ``LIVE_VERIFIED``. Data availability is never sufficient:
        being able to *see* a price is not permission to *trade* it.
        """
        if not reason.strip():
            raise CertificationRejected("activation requires a reason")
        instrument = self.require(instrument_id)
        if instrument.active:
            return instrument
        if for_trading and not instrument.tradeable_venues():
            highest = max(
                (m.status for m in instrument.mappings),
                key=certification_rank,
                default=VenueStatus.UNKNOWN,
            )
            raise CertificationRejected(
                f"{instrument_id} cannot be activated for trading: no venue mapping is "
                f"TRADE_ENABLED or LIVE_VERIFIED (highest = {highest.value})",
            )
        updated = replace(instrument, active=True)
        self._instruments[instrument_id] = updated
        self._record(
            kind="ACTIVATE",
            instrument_id=instrument_id,
            venue=None,
            venue_symbol=instrument.canonical_symbol,
            from_status="INACTIVE",
            to_status="ACTIVE_FOR_TRADING" if for_trading else "ACTIVE_FOR_RESEARCH",
            evidence=reason,
            requested_by=requested_by,
        )
        return updated

    def deactivate(
        self,
        instrument_id: InstrumentId,
        *,
        reason: str,
        requested_by: str = "SYSTEM",
    ) -> CanonicalInstrument:
        """Deactivation is always allowed and never conditional — stopping is safe."""
        if not reason.strip():
            raise CertificationRejected("deactivation requires a reason")
        instrument = self.require(instrument_id)
        if not instrument.active:
            return instrument
        updated = replace(instrument, active=False)
        self._instruments[instrument_id] = updated
        self._record(
            kind="DEACTIVATE",
            instrument_id=instrument_id,
            venue=None,
            venue_symbol=instrument.canonical_symbol,
            from_status="ACTIVE",
            to_status="INACTIVE",
            evidence=reason,
            requested_by=requested_by,
        )
        return updated

    # ------------------------------------------------------------------ internals

    def _index(self, instrument: CanonicalInstrument) -> None:
        self._instruments[instrument.instrument_id] = instrument
        self._by_symbol[instrument.canonical_symbol] = instrument.instrument_id
        for mapping in instrument.mappings:
            self._by_venue_symbol[(mapping.venue.value, mapping.venue_symbol)] = instrument.instrument_id

    def _record(
        self,
        *,
        kind: str,
        instrument_id: InstrumentId,
        venue: str | None,
        venue_symbol: str | None,
        from_status: str | None,
        to_status: str | None,
        evidence: str,
        requested_by: str = "SYSTEM",
        now: datetime | None = None,
    ) -> None:
        self._changes.append(
            RegistryChange(
                change_id=new_id("IRG"),
                kind=kind,
                instrument_id=instrument_id,
                venue=venue,
                venue_symbol=venue_symbol,
                from_status=from_status,
                to_status=to_status,
                evidence=evidence,
                changed_at=now or self._now_fn(),
                requested_by=requested_by,
            ),
        )


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Honest description of what the master knows — used by the UI and by reports.

    Coverage is never implied. If a mapping has no contract size, the report says so,
    because sizing math cannot run without it.
    """

    total: int
    active: int
    by_asset_class: dict[str, int]
    by_venue_status: dict[str, int]
    missing_contract_size: tuple[str, ...]
    missing_tick_size: tuple[str, ...]
    ready_for_research: tuple[str, ...]
    ready_for_paper: tuple[str, ...]
    ready_for_live: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "active": self.active,
            "by_asset_class": dict(self.by_asset_class),
            "by_venue_status": dict(self.by_venue_status),
            "missing_contract_size": list(self.missing_contract_size),
            "missing_tick_size": list(self.missing_tick_size),
            "ready_for_research": list(self.ready_for_research),
            "ready_for_paper": list(self.ready_for_paper),
            "ready_for_live": list(self.ready_for_live),
        }


def coverage_report(registry: InstrumentRegistry) -> CoverageReport:
    """Summarise certification coverage across the master."""
    instruments = registry.all()
    by_class: dict[str, int] = {}
    by_status: dict[str, int] = {}
    missing_cs: list[str] = []
    missing_ts: list[str] = []
    research: list[str] = []
    paper: list[str] = []
    live: list[str] = []

    for instrument in instruments:
        by_class[instrument.asset_class.value] = by_class.get(instrument.asset_class.value, 0) + 1
        ranks = [certification_rank(m.status) for m in instrument.mappings] or [-1]
        for mapping in instrument.mappings:
            by_status[mapping.status.value] = by_status.get(mapping.status.value, 0) + 1
            if mapping.contract_size is None:
                missing_cs.append(f"{instrument.instrument_id}@{mapping.venue.value}")
            if mapping.tick_size is None:
                missing_ts.append(f"{instrument.instrument_id}@{mapping.venue.value}")
        highest = max(ranks)
        if highest >= certification_rank(VenueStatus.DATA_AVAILABLE):
            research.append(instrument.instrument_id)
        if highest >= certification_rank(VenueStatus.TRADE_ENABLED):
            paper.append(instrument.instrument_id)
        if highest >= certification_rank(VenueStatus.LIVE_VERIFIED):
            live.append(instrument.instrument_id)

    return CoverageReport(
        total=len(instruments),
        active=sum(1 for i in instruments if i.active),
        by_asset_class=by_class,
        by_venue_status=by_status,
        missing_contract_size=tuple(missing_cs),
        missing_tick_size=tuple(missing_ts),
        ready_for_research=tuple(research),
        ready_for_paper=tuple(paper),
        ready_for_live=tuple(live),
    )


def build_instrument(
    *,
    canonical_symbol: str,
    asset_class: AssetClass,
    base_currency: str,
    quote_currency: str,
    settlement_currency: str | None = None,
    underlying: str | None = None,
    expiry: str | None = None,
    strike: Decimal | None = None,
    option_type: str | None = None,
    mappings: Iterable[VenueMapping] = (),
    notes: str = "",
) -> CanonicalInstrument:
    """Convenience constructor producing a stable id and inactive-by-default record."""
    slug = canonical_symbol.replace("/", "-").replace(":", "-").upper()
    instrument_id = f"INS-{slug}"
    return CanonicalInstrument(
        instrument_id=instrument_id,
        canonical_symbol=canonical_symbol,
        asset_class=asset_class,
        base_currency=base_currency,
        quote_currency=quote_currency,
        settlement_currency=settlement_currency or quote_currency,
        underlying=underlying,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        mappings=tuple(mappings),
        active=False,
        notes=notes,
    )


__all__ = [
    "CERTIFICATION_ORDER",
    "CertificationRejected",
    "CoverageReport",
    "InstrumentError",
    "InstrumentRegistry",
    "RegistryChange",
    "RegistrySnapshot",
    "UnknownInstrument",
    "build_instrument",
    "certification_rank",
    "coverage_report",
    "is_certification_advance",
]
