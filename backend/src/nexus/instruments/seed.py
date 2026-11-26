"""The seeded instrument master — lever L-C, Stage 7.3 (authorised by the owner as D-045's follow-on).

Until this module existed the master was empty at boot, so every coverage screen reported
``total=0 active=0`` and the archive gate (``MINIMUM_STATUS_FOR_ARCHIVE = DATA_AVAILABLE``) was
unsatisfiable in production however honest the adapters were: finding **F-3**. Stage 7.2 removed the
*definition* blocker (lever L-E made ``CONNECTED`` occupiable by a credential-free source); this
removes the missing seed.

The rule this module is built to obey
-------------------------------------
**Seed only instruments whose evidence exists, each at the rank its evidence supports and no
higher.** Nothing here is aspirational. Every rung carries an evidence label naming what was
actually measured and in which runs, because ``certify`` cannot judge a label — it only checks that
one is present — so the honesty of the ladder rests entirely on whoever writes it (finding F-7).

Three canonical instruments, four venue mappings:

``BTC/USDT:USDT`` (CRYPTO_PERP)
    ``OKX`` at ``DATA_AVAILABLE`` — five public endpoints verified against live responses in every
    venue run read for Stage 7.3, with the economics below taken from the instrument endpoint
    rather than assumed. ``BYBIT`` at ``SUPPORTED`` and **no higher**: its adapter exists, which is
    all ``SUPPORTED`` claims, and it has never answered from a hosted runner (finding F-2). Seeding
    it at a rank it has not earned would be exactly the overclaim Stage 7 exists to remove; leaving
    it out entirely would hide an open finding. So it is present, at its honest rank, with the
    geo-block in its notes.

``BTC/USDT`` (CRYPTO_SPOT)
    ``BINANCE`` at ``DATA_AVAILABLE`` — a real daily dump downloaded and parsed end to end:
    1,440 of 1,440 one-minute bars accepted, 0 rejected.

``EUR/USD`` (FX_SPOT)
    ``DUKASCOPY`` at ``DATA_AVAILABLE`` — the rung the pipeline itself defines as *"the feed was
    actually observed working"* (``ingestion/pipeline.py:47-49``), which every venue run since
    2026-11-25 satisfies against a real bi5 hour. The scope is carried in the label and the notes
    rather than being withheld from the rank: EURUSD only, one hour, 12 of 13 point divisors still
    unverified, and no reconciliation against a second source (findings F-5, F-8).

No mapping is seeded at ``TRADE_ENABLED`` or ``LIVE_VERIFIED``. Those need a sandbox order
lifecycle and a live pilot with reconciliation proven; no credential-free public data source can
reach them, and ``DUKASCOPY`` can never reach them at all — it is data, not a broker.

Two properties this module must keep
------------------------------------
* **Idempotent, and safe to call at every boot.** ``register`` overwrites an existing record and
  logs ``REMAP``, which would silently reset certified mappings to ``UNKNOWN``; and ``certify`` to a
  rung *below* the current one is recorded as ``DE_CERTIFY``. So an existing instrument is never
  re-registered and a rung is never re-claimed: both are skipped. Calling this twice changes nothing
  and records nothing.
* **Nothing becomes active or tradeable.** ``register`` forces ``active=False`` (D-002) and
  ``DATA_AVAILABLE`` is not permission: ``is_tradeable`` stays False for every mapping seeded here.

Run:  ``seed_master(InstrumentRegistry())`` — no network, no credentials, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nexus.domain.instrument import AssetClass, Venue, VenueMapping, VenueStatus
from nexus.instruments.registry import (
    AUTH_NOT_APPLICABLE,
    InstrumentRegistry,
    build_instrument,
    certification_rank,
)

#: Recorded as the actor on every change this module makes, so the change log can distinguish a
#: seeded rung from one a human or a pipeline claimed.
SEED_REQUESTER = "STAGE-7.3-SEED"

#: ``register``'s ``source`` label, which lands in the ``REGISTER`` evidence line.
SEED_SOURCE = "SEED-STAGE-7.3-L-C"

#: ``RegistryChange.to_audit_payload`` truncates evidence at 200 characters. A label longer than
#: that would lose its tail silently in the audit view while looking complete in the change log, so
#: every label here is written to fit and a test pins the bound.
EVIDENCE_MAX_CHARS = 200

#: The venue runs read for this batch, cited in the labels below. Bounded on purpose: the workflow
#: re-runs on every push that touches ``ingestion/**``, so an open-ended count would go stale.
RUNS_READ = "45754638978..45801459867"


@dataclass(frozen=True, slots=True)
class RungEvidence:
    """One rung of the ladder, with the label that justifies claiming it."""

    status: VenueStatus
    evidence: str
    #: Required by ``certify`` at ``CONNECTED`` and refused everywhere else (lever L-E).
    auth: str | None = None


@dataclass(frozen=True, slots=True)
class SeedMapping:
    """One venue's view of a canonical instrument, and how far its evidence reaches."""

    venue: Venue
    venue_symbol: str
    ladder: tuple[RungEvidence, ...]
    contract_size: Decimal | None = None
    tick_size: Decimal | None = None
    min_order_qty: Decimal | None = None
    qty_step: Decimal | None = None
    trading_hours: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        """Refuse a ladder that could not be climbed, rather than failing halfway through a boot.

        ``certify`` advances exactly one rung at a time, so a ladder that starts above ``SUPPORTED``
        or skips a rung is not a seed, it is a guaranteed ``CertificationRejected``.
        """
        if not self.ladder:
            raise ValueError(f"{self.venue.value}: a seed mapping must claim at least one rung")
        expected = certification_rank(VenueStatus.UNKNOWN) + 1
        for rung in self.ladder:
            if certification_rank(rung.status) != expected:
                raise ValueError(
                    f"{self.venue.value}: ladder must climb one rung at a time from UNKNOWN; "
                    f"got {rung.status.value} where rank {expected} was required",
                )
            if (rung.status is VenueStatus.CONNECTED) != (rung.auth is not None):
                raise ValueError(
                    f"{self.venue.value}: an auth declaration belongs to CONNECTED only "
                    f"(got auth={rung.auth!r} at {rung.status.value})",
                )
            if len(rung.evidence) > EVIDENCE_MAX_CHARS:
                raise ValueError(
                    f"{self.venue.value}/{rung.status.value}: evidence label is "
                    f"{len(rung.evidence)} chars and would be truncated to "
                    f"{EVIDENCE_MAX_CHARS} in the audit payload",
                )
            expected += 1


@dataclass(frozen=True, slots=True)
class SeedSpec:
    """One canonical instrument and every venue mapping seeded for it."""

    canonical_symbol: str
    asset_class: AssetClass
    base_currency: str
    quote_currency: str
    mappings: tuple[SeedMapping, ...]
    underlying: str | None = None
    settlement_currency: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class SeedReport:
    """What one ``seed_master`` call did — including what it deliberately did not do."""

    registered: tuple[str, ...]
    already_present: tuple[str, ...]
    rungs_climbed: int
    rungs_skipped: int
    #: instrument_id -> venue -> status, as the registry holds it after the call.
    final_status: dict[str, dict[str, str]]

    @property
    def instruments(self) -> int:
        return len(self.final_status)

    def to_dict(self) -> dict[str, object]:
        return {
            "registered": list(self.registered),
            "already_present": list(self.already_present),
            "instruments": self.instruments,
            "rungs_climbed": self.rungs_climbed,
            "rungs_skipped": self.rungs_skipped,
            "final_status": {k: dict(v) for k, v in sorted(self.final_status.items())},
            "requested_by": SEED_REQUESTER,
        }


SEED_SPECS: tuple[SeedSpec, ...] = (
    SeedSpec(
        canonical_symbol="BTC/USDT:USDT",
        asset_class=AssetClass.CRYPTO_PERP,
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        notes=(
            "Seeded at Stage 7.3 (lever L-C) from evidence only. Two venues, two different ranks: "
            "OKX answered and was verified; BYBIT has never answered from a hosted runner and stays "
            "at SUPPORTED with its geo-block recorded (F-2), visible rather than dropped."
        ),
        mappings=(
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                # Measured from the live instrument endpoint, not assumed: ctVal/tickSz/minSz/lotSz.
                contract_size=Decimal("0.01"),
                tick_size=Decimal("0.1"),
                min_order_qty=Decimal("0.01"),
                qty_step=Decimal("0.01"),
                trading_hours="24/7",
                notes="Perpetual swap. Economics read from okx's public instrument endpoint.",
                ladder=(
                    RungEvidence(
                        VenueStatus.SUPPORTED,
                        "adapter nexus.ingestion.okx implements five public endpoints; no credential",
                    ),
                    RungEvidence(
                        VenueStatus.CONNECTED,
                        "public credential-free endpoints: okx answered and normalised in every "
                        f"venue run read at Stage 7.3 ({RUNS_READ}), 5 of 5 checks",
                        auth=AUTH_NOT_APPLICABLE,
                    ),
                    RungEvidence(
                        VenueStatus.DATA_AVAILABLE,
                        "market data verified live: ctVal=0.01 tickSz=0.1 minSz=0.01, book uncrossed "
                        "entitlement=LIVE, candles ordered, trades normalised in every run read",
                    ),
                ),
            ),
            SeedMapping(
                venue=Venue.BYBIT,
                venue_symbol="BTCUSDT",
                trading_hours="24/7",
                notes=(
                    "GEO-BLOCKED and unverified: bybit v5 answers 403 from GitHub-hosted runners on "
                    "public unauthenticated endpoints (run 45724918466; F-2), and reports "
                    "`5 geo-blocked` in every venue run since. The adapter is exercised against "
                    "public documentation only. Climbing this mapping needs the D-021 deployment VM "
                    "as a self-hosted runner (lever L-D) — no code change and no money, but nothing "
                    "that can be done from a hosted runner."
                ),
                ladder=(
                    RungEvidence(
                        VenueStatus.SUPPORTED,
                        "adapter exists but is UNVERIFIED: 403 geo-blocked from hosted runners in "
                        "every run (F-2); exercised against public docs only; needs the D-021 VM",
                    ),
                ),
            ),
        ),
    ),
    SeedSpec(
        canonical_symbol="BTC/USDT",
        asset_class=AssetClass.CRYPTO_SPOT,
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        notes=(
            "Seeded at Stage 7.3 (lever L-C). Binance Vision publishes free daily dumps; this is an "
            "archive source, not a live feed, and no tick size or contract size is claimed because "
            "the dumps do not publish one — coverage_report lists it as missing rather than guessing."
        ),
        mappings=(
            SeedMapping(
                venue=Venue.BINANCE,
                venue_symbol="BTCUSDT",
                trading_hours="24/7",
                notes="Daily 1m kline dumps. Historical archive; nothing here streams.",
                ladder=(
                    RungEvidence(
                        VenueStatus.SUPPORTED,
                        "adapter nexus.ingestion.binance_vision reads the public daily dumps; no credential",
                    ),
                    RungEvidence(
                        VenueStatus.CONNECTED,
                        "public credential-free archive: URL shape verified and a real 71,720-byte "
                        "daily ZIP downloaded and parsed in every run read at Stage 7.3",
                        auth=AUTH_NOT_APPLICABLE,
                    ),
                    RungEvidence(
                        VenueStatus.DATA_AVAILABLE,
                        "market data verified: 1440 of 1440 1m bars accepted, 0 rejected, spanning "
                        "23.98h, timestamp_units=us (defect 40's fix observed on real data)",
                    ),
                ),
            ),
        ),
    ),
    SeedSpec(
        canonical_symbol="EUR/USD",
        asset_class=AssetClass.FX_SPOT,
        base_currency="EUR",
        quote_currency="USD",
        settlement_currency="USD",
        notes=(
            "Seeded at Stage 7.3 (lever L-C), and the first FX instrument this system has been able "
            "to record at all: before lever L-B added Venue.DUKASCOPY, every FX test modelled EUR/USD "
            "at MT5, which has no adapter and no free source (F-4). Data, not a broker: this mapping "
            "can never reach TRADE_ENABLED."
        ),
        mappings=(
            SeedMapping(
                venue=Venue.DUKASCOPY,
                venue_symbol="EURUSD",
                # Derived from the one verified fact about scale: EURUSD's point divisor is 100000,
                # confirmed against a real file, and the parsed prices carried five decimals.
                tick_size=Decimal("0.00001"),
                trading_hours="FX 24x5",
                notes=(
                    "EURUSD ONLY. 12 of the 13 point divisors in POINT_DIVISORS have never met a real "
                    "file, so any other pair stays provisional and must never size a position; "
                    "summarise() names them. tick_size is derived from the verified divisor 100000, "
                    "not published by the feed. No contract_size is claimed: a bi5 file carries "
                    "ticks, not lot economics. Feed intermittent (F-5); prices not reconciled "
                    "against a second source (F-8)."
                ),
                ladder=(
                    RungEvidence(
                        VenueStatus.SUPPORTED,
                        "adapter nexus.ingestion.dukascopy reads the free public bi5 tick history; "
                        "no credential",
                    ),
                    RungEvidence(
                        VenueStatus.CONNECTED,
                        "public credential-free feed: real bi5 hour 2026-11-24T12:00Z fetched and "
                        "normalised in every venue run since 2026-11-25; layout verified for EURUSD",
                        auth=AUTH_NOT_APPLICABLE,
                    ),
                    RungEvidence(
                        VenueStatus.DATA_AVAILABLE,
                        "feed observed working: 25,761 -> 101,480 bytes = 5,074 ticks x 20 exactly, "
                        "prices 1.09502-1.0964 in band; EURUSD only, one hour, unreconciled (F-8)",
                    ),
                ),
            ),
        ),
    ),
)


def seed_master(
    registry: InstrumentRegistry,
    *,
    requested_by: str = SEED_REQUESTER,
) -> SeedReport:
    """Register the instruments whose evidence exists, each at the rank that evidence supports.

    Safe to call repeatedly and at every boot: an instrument already in the master is left alone
    (re-registering it would overwrite certified mappings and log ``REMAP``) and a rung already
    reached is never re-claimed (re-claiming a lower rung is recorded as ``DE_CERTIFY``). A second
    call therefore registers nothing, climbs nothing and records nothing.

    No network, no credentials, no I/O: this writes down what previous runs already proved.
    """
    registered: list[str] = []
    already_present: list[str] = []
    seeded_ids: list[str] = []
    climbed = 0
    skipped = 0

    for spec in SEED_SPECS:
        instrument = build_instrument(
            canonical_symbol=spec.canonical_symbol,
            asset_class=spec.asset_class,
            base_currency=spec.base_currency,
            quote_currency=spec.quote_currency,
            settlement_currency=spec.settlement_currency,
            underlying=spec.underlying,
            notes=spec.notes,
            mappings=tuple(
                VenueMapping(
                    venue=mapping.venue,
                    venue_symbol=mapping.venue_symbol,
                    status=VenueStatus.UNKNOWN,
                    contract_size=mapping.contract_size,
                    tick_size=mapping.tick_size,
                    min_order_qty=mapping.min_order_qty,
                    qty_step=mapping.qty_step,
                    trading_hours=mapping.trading_hours,
                    notes=mapping.notes,
                )
                for mapping in spec.mappings
            ),
        )
        seeded_ids.append(instrument.instrument_id)
        if instrument.instrument_id in registry:
            already_present.append(instrument.instrument_id)
        else:
            registry.register(instrument, source=SEED_SOURCE, requested_by=requested_by)
            registered.append(instrument.instrument_id)

        for mapping in spec.mappings:
            for rung in mapping.ladder:
                held = registry.require(instrument.instrument_id).mapping_for(mapping.venue)
                current = held.status if held is not None else VenueStatus.UNKNOWN
                if certification_rank(current) >= certification_rank(rung.status):
                    skipped += 1
                    continue
                registry.certify(
                    instrument.instrument_id,
                    mapping.venue,
                    rung.status,
                    evidence=rung.evidence,
                    auth=rung.auth,
                    requested_by=requested_by,
                )
                climbed += 1

    # Read back from the ids ``build_instrument`` actually produced rather than recomputing its
    # slug rule here, so the two cannot drift apart.
    final: dict[str, dict[str, str]] = {}
    for instrument_id in seeded_ids:
        seeded = registry.require(instrument_id)
        final[instrument_id] = {m.venue.value: m.status.value for m in seeded.mappings}

    return SeedReport(
        registered=tuple(registered),
        already_present=tuple(already_present),
        rungs_climbed=climbed,
        rungs_skipped=skipped,
        final_status=final,
    )


__all__ = [
    "EVIDENCE_MAX_CHARS",
    "RUNS_READ",
    "SEED_REQUESTER",
    "SEED_SOURCE",
    "SEED_SPECS",
    "RungEvidence",
    "SeedMapping",
    "SeedReport",
    "SeedSpec",
    "seed_master",
]
