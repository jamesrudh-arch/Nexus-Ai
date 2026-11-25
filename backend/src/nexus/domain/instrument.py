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

InstrumentId = str  # e.g. "INS-BTCUSDT-PERP-BYBIT"


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
    """Venues in scope (D-007). Eligibility per Nigeria is tracked separately."""

    BYBIT = "BYBIT"
    BINANCE = "BINANCE"
    OKX = "OKX"
    MT4 = "MT4"
    MT5 = "MT5"
    CTRADER = "CTRADER"
    IBKR = "IBKR"
    OANDA = "OANDA"
    ALPACA = "ALPACA"


class VenueStatus(StrEnum):
    """Per-account capability states. Each is proven separately (Section 11)."""

    UNKNOWN = "UNKNOWN"
    SUPPORTED = "SUPPORTED"  # adapter exists
    CONNECTED = "CONNECTED"  # auth verified
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

    def mapping_for(self, venue: Venue) -> VenueMapping | None:
        for mapping in self.mappings:
            if mapping.venue == venue:
                return mapping
        return None

    def tradeable_venues(self) -> tuple[Venue, ...]:
        return tuple(m.venue for m in self.mappings if m.is_tradeable)
