"""Canonical instrument identity (Section 3.1, Section 11.6).

The same economic exposure can have different symbols, multipliers, hours, spreads,
swaps and margin rules per broker. NEXUS therefore keeps one canonical instrument record
and a separate per-venue mapping. ``BTCUSD`` at one broker is never assumed to equal
``BTCUSDT`` at an exchange.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from nexus.core.errors import NexusError, RejectReason

InstrumentId = str  # e.g. "INS-BTCUSDT-PERP-BYBIT"


class InstrumentDefinitionError(NexusError):
    """An instrument or venue mapping was built outside the declared vocabularies (D-007).

    Raised at construction, which is the boundary where a bad value enters. Before Stage 7.2 the
    annotations alone did the work, and they do nothing at runtime: a venue that was not a ``Venue``
    member was accepted silently and then raised an unclassified ``AttributeError`` deep inside
    ``InstrumentRegistry.register`` (finding F-4, ``registry.py:282``) — through the API that is a
    500 where every comparable condition is a named refusal. Not retryable: the value does not
    become valid by waiting.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(RejectReason.INSTRUMENT_DEFINITION_INVALID, detail, retryable=False)


class AssetClass(StrEnum):
    CRYPTO_SPOT = "CRYPTO_SPOT"
    CRYPTO_PERP = "CRYPTO_PERP"
    CRYPTO_FUTURES = "CRYPTO_FUTURES"
    CRYPTO_OPTIONS = "CRYPTO_OPTIONS"
    FX_SPOT = "FX_SPOT"
    FX_CFD = "FX_CFD"
    METALS = "METALS"
    EQUITIES = "EQUITIES"
    ETF = "ETF"
    INDICES = "INDICES"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    FIXED_INCOME = "FIXED_INCOME"
    COMMODITIES = "COMMODITIES"


class Venue(StrEnum):
    """Venues in scope (D-007). Eligibility per Nigeria is tracked separately.

    ``DUKASCOPY`` was added in Stage 7.2 (lever L-B, authorised by the owner as an extension of
    D-007's scope). It was the only source with a working adapter that could not be represented
    here, so FX coverage could be tested but never recorded — every FX test modelled EUR/USD at
    ``MT5``, which has no adapter and no free source at all (finding F-4).
    """

    BYBIT = "BYBIT"
    BINANCE = "BINANCE"
    OKX = "OKX"
    #: Free public FX (and metals) tick history over HTTP; no credential, no order capability.
    #: Data, not a broker: nothing here can ever reach TRADE_ENABLED through this venue.
    DUKASCOPY = "DUKASCOPY"
    MT4 = "MT4"
    MT5 = "MT5"
    CTRADER = "CTRADER"
    IBKR = "IBKR"
    OANDA = "OANDA"
    ALPACA = "ALPACA"


class VenueStatus(StrEnum):
    """Per-account capability states. Each is proven separately (Section 11).

    ``CONNECTED`` was redefined in Stage 7.2 (lever L-E, owner's ruling). It read "auth verified",
    which none of the four credential-free sources can honestly occupy: they are public HTTP feeds
    with no credential to verify, so a source could be data-verified without ever being able to
    claim this rung, and the one-step rule in ``InstrumentRegistry.certify`` forbids skipping it.
    The rung now means **the venue answered and its responses normalised**, and the certification
    that claims it must declare which of two cases it is in — ``AUTH_VERIFIED`` (a credential was
    presented and accepted) or ``AUTH_NOT_APPLICABLE`` (public, credential-free, with the evidence
    label stating why). The registry cannot judge an evidence label, so the declaration is a
    separate, recorded field rather than prose.
    """

    UNKNOWN = "UNKNOWN"
    SUPPORTED = "SUPPORTED"  # adapter exists
    CONNECTED = "CONNECTED"  # venue answered and normalised; auth declared, not assumed
    DATA_AVAILABLE = "DATA_AVAILABLE"  # market data verified
    TRADE_ENABLED = "TRADE_ENABLED"  # sandbox order lifecycle verified
    LIVE_VERIFIED = "LIVE_VERIFIED"  # live pilot verified + reconciliation proven


@dataclass(frozen=True, slots=True)
class VenueMapping:
    """How one venue refers to a canonical instrument, with its own economics."""

    venue: Venue
    venue_symbol: str
    status: VenueStatus = VenueStatus.UNKNOWN
    contract_size: Decimal | None = None  # units per contract (FX lots, 100oz gold, 1 BTC)
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    min_order_qty: Decimal | None = None
    max_order_qty: Decimal | None = None
    qty_step: Decimal | None = None
    quote_currency: str | None = None
    settlement_currency: str | None = None
    trading_hours: str | None = None  # e.g. "24/7", "FX 24x5", exchange session string
    margin_rate: Decimal | None = None
    fees: dict[str, Any] = field(default_factory=dict)  # maker/taker/funding as published
    notes: str = ""

    def __post_init__(self) -> None:
        """Refuse a venue or status that is not one of the declared enumerations.

        A frozen dataclass does not enforce its annotations, so ``venue: Venue`` was documentation
        only: ``VenueMapping(venue="DUKASCOPY", ...)`` used to construct happily and then raise an
        unclassified ``AttributeError`` inside ``InstrumentRegistry.register`` at the first
        ``m.venue.value`` (finding F-4). Failing here instead puts the refusal at the boundary where
        the bad value enters, with a reason code a caller can act on.
        """
        if not isinstance(self.venue, Venue):
            raise InstrumentDefinitionError(
                "a venue mapping's venue must be a Venue member (D-007 scope); got "
                f"{self.venue!r} of type {type(self.venue).__name__}",
            )
        if not isinstance(self.status, VenueStatus):
            raise InstrumentDefinitionError(
                "a venue mapping's status must be a VenueStatus member; got "
                f"{self.status!r} of type {type(self.status).__name__}",
            )

    @property
    def is_tradeable(self) -> bool:
        return self.status in (VenueStatus.TRADE_ENABLED, VenueStatus.LIVE_VERIFIED)


@dataclass(frozen=True, slots=True)
class CanonicalInstrument:
    """One economic instrument, independent of venue."""

    instrument_id: InstrumentId
    canonical_symbol: str  # e.g. "BTC/USDT:USDT"
    asset_class: AssetClass
    base_currency: str
    quote_currency: str
    settlement_currency: str
    underlying: str | None = None  # for derivatives
    expiry: str | None = None  # ISO date for futures/options
    strike: Decimal | None = None
    option_type: str | None = None  # "CALL" | "PUT"
    mappings: tuple[VenueMapping, ...] = ()
    active: bool = False  # staged activation (D-002): never active by default
    data_status: str = "UNAVAILABLE"  # LIVE | DELAYED | STALE | UNAVAILABLE
    notes: str = ""

    def __post_init__(self) -> None:
        """Refuse an asset class or mapping that is not one of the declared types.

        Same boundary rule as :class:`VenueMapping`: ``coverage_report`` reads
        ``instrument.asset_class.value`` and ``mapping.venue.value``, so a bare string anywhere in
        this record becomes an unclassified crash in the coverage path rather than a refusal.
        """
        if not isinstance(self.asset_class, AssetClass):
            raise InstrumentDefinitionError(
                "an instrument's asset_class must be an AssetClass member; got "
                f"{self.asset_class!r} of type {type(self.asset_class).__name__}",
            )
        for mapping in self.mappings:
            if not isinstance(mapping, VenueMapping):
                raise InstrumentDefinitionError(
                    f"{self.instrument_id}: mappings must be VenueMapping instances; got "
                    f"{mapping!r} of type {type(mapping).__name__}",
                )

    def mapping_for(self, venue: Venue) -> VenueMapping | None:
        for mapping in self.mappings:
            if mapping.venue == venue:
                return mapping
        return None

    def tradeable_venues(self) -> tuple[Venue, ...]:
        return tuple(m.venue for m in self.mappings if m.is_tradeable)
