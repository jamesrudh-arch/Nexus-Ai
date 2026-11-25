"""Portfolio and position snapshots used by the risk engine.

Snapshots come from the broker (execution truth) or from the paper simulator — never from
a model's imagination. Each snapshot carries its observation time so staleness can be
enforced by the data-quality gate before any risk decision is made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from nexus.core.ids import iso_utc, utc_now
from nexus.core.time import age_seconds, parse_iso


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """One open position as reported by the venue (or the paper ledger)."""

    instrument_id: str
    venue: str
    account_id: str
    side: str  # "LONG" | "SHORT"
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal | None = None
    contract_size: Decimal = Decimal("1")
    quote_currency: str = "USD"
    leverage: Decimal = Decimal("1")
    stop_price: Decimal | None = None
    protective_orders_confirmed: bool = False  # venue-reported, never assumed
    observed_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    source: str = "UNKNOWN"  # VENUE | PAPER | REPLAY

    @property
    def notional(self) -> Decimal:
        price = self.mark_price if self.mark_price is not None else self.entry_price
        return self.quantity * self.contract_size * price

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.mark_price is None:
            return Decimal("0")
        direction = Decimal("1") if self.side.upper() == "LONG" else Decimal("-1")
        return (self.mark_price - self.entry_price) * self.quantity * self.contract_size * direction

    def age_seconds(self, *, now: Any = None) -> float:
        return age_seconds(parse_iso(self.observed_at), now=now)


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Consolidated view across accounts, with the equity the limits are measured against."""

    equity_usd: Decimal
    cash_available_usd: Decimal
    realized_pnl_today_usd: Decimal = Decimal("0")
    starting_equity_today_usd: Decimal | None = None
    positions: tuple[PositionSnapshot, ...] = ()
    margin_used_usd: Decimal = Decimal("0")
    fx_rates: dict[str, Decimal] = field(default_factory=dict)  # quote ccy -> USD
    observed_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    source: str = "UNKNOWN"
    complete: bool = False  # False if any connected account failed to report

    @property
    def total_notional_usd(self) -> Decimal:
        total = Decimal("0")
        for position in self.positions:
            rate = self.fx_rates.get(position.quote_currency, Decimal("1"))
            total += position.notional * rate
        return total

    @property
    def daily_drawdown_pct(self) -> Decimal:
        """Drawdown from the day's starting equity, in percent. Never negative."""
        base = self.starting_equity_today_usd
        if base is None or base <= 0:
            return Decimal("0")
        drop = (base - self.equity_usd) / base * Decimal("100")
        return max(Decimal("0"), drop)

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    def exposure_pct_by_instrument(self) -> dict[str, Decimal]:
        """Notional share per instrument, as a percentage of equity."""
        shares: dict[str, Decimal] = {}
        if self.equity_usd <= 0:
            return shares
        for position in self.positions:
            rate = self.fx_rates.get(position.quote_currency, Decimal("1"))
            notional_usd = position.notional * rate
            shares[position.instrument_id] = shares.get(position.instrument_id, Decimal("0")) + (
                notional_usd / self.equity_usd * Decimal("100")
            )
        return shares

    def age_seconds(self, *, now: Any = None) -> float:
        return age_seconds(parse_iso(self.observed_at), now=now)
