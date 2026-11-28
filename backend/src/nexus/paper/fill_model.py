"""Simulated execution against real market data (Stage 11, D-059).

The paper platform exists to answer one question before any real order is ever sent: *would this
decision have made money, and what would it actually have cost to do?* That question is only worth
answering if the execution is honest. Two rules follow, and they are the reason this module is not
twenty lines of ``price * quantity``.

**Rule 1 — never invent a price.** ``docs/03`` §3.5 carries the owner's law: real data only, no
fake balances, no invented P&L. A simulated *fill* is legitimate; a simulated *price* is not. So
every fill here is derived from a real :class:`~nexus.data.records.QuoteRecord` that the ingestion
pipeline actually observed. When there is no quote, or the quote is too old to trade against, this
model refuses to fill rather than guessing what the market might have been doing. An unfilled order
with a reason is a true statement about the simulation; a filled order at a made-up number is a lie
that would be believed, because it has a P&L attached to it.

**Rule 2 — pay for the trade.** A backtest that fills at the mid, instantly, for free, produces
returns that cannot survive contact with a real venue. The spread, adverse slippage, commission and
latency are all modelled, because together they are usually the difference between a strategy that
works and one that does not. Every one of them is applied *against* the order, never in its favour.

Latency deserves particular care. A real order reaches the venue some milliseconds after the
decision was made, and the price it meets is not the price that motivated it. This model therefore
stamps a fill with the quote it executed against and records the delay separately, so a later
analysis can distinguish "the idea was right" from "the idea was right and the execution was fast
enough to keep the edge".
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now

__all__ = [
    "FillModelConfig",
    "FillOutcome",
    "NoFillReason",
    "SimulatedFill",
    "SimulatedFillModel",
    "Side",
]

#: Basis points in one unit. Kept as a Decimal so no commission calculation ever touches a float.
_BPS = Decimal(10_000)


class Side(StrEnum):
    """The order side a fill is simulated for.

    ``TradeIntent.side`` is a *position* intent (LONG/SHORT); the order side depends on whether the
    position is being opened or closed. The paper engine resolves that before it gets here, so this
    model only ever sees the direction that actually crosses the spread.
    """

    BUY = "BUY"
    SELL = "SELL"


class NoFillReason(StrEnum):
    """Why an order did not fill. Each is a fact about the data, not a tuning parameter."""

    NO_QUOTE = "NO_QUOTE"
    NO_EXECUTABLE_SIDE = "NO_EXECUTABLE_SIDE"
    STALE_QUOTE = "STALE_QUOTE"
    CROSSED_OR_LOCKED = "CROSSED_OR_LOCKED"
    LIMIT_NOT_MARKETABLE = "LIMIT_NOT_MARKETABLE"
    NO_LIQUIDITY = "NO_LIQUIDITY"
    DELAYED_DATA_REFUSED = "DELAYED_DATA_REFUSED"


@dataclass(frozen=True, slots=True)
class FillModelConfig:
    """How pessimistic the simulation is.

    Every default is deliberately adverse. The point of paper trading is to find out whether an edge
    survives real costs, and a model that can be tuned optimistic will be, and will then report the
    strategy as profitable when the venue would not have agreed.
    """

    #: Adverse price movement applied on top of the executable price, in basis points.
    slippage_bps: Decimal = Decimal("2")
    #: Commission on notional, in basis points, with a per-fill floor.
    commission_bps: Decimal = Decimal("5")
    minimum_commission: Decimal = Decimal("0.10")
    #: Assumed round trip from decision to venue acknowledgement.
    latency_ms: int = 120
    #: A quote older than this cannot be traded against. Real-time analysis means acting on the
    #: market as it is, so a stale quote is a refusal rather than a fill at an old price.
    max_quote_age_seconds: Decimal = Decimal("30")
    #: When the order is larger than the displayed size, fill only what is there. Turning this off
    #: assumes infinite depth, which is the single most common way a simulation overstates itself.
    respect_displayed_size: bool = True
    #: Refuse to trade on a delayed feed. A delayed quote is real data, but it is not *current*
    #: data, and filling against it would attribute to the strategy an edge that belongs to whoever
    #: is not delayed.
    refuse_delayed_data: bool = True
    #: Seed for the slippage draw. Fixed so a run is reproducible: the same quotes and the same
    #: orders must produce the same fills, or a replay could not be compared with its original.
    seed: int = 20260101

    def validated(self) -> FillModelConfig:
        """Refuse a configuration that would flatter the simulation."""
        problems: list[str] = []
        if self.slippage_bps < 0:
            problems.append("slippage_bps cannot be negative (a favourable fill is not slippage)")
        if self.commission_bps < 0:
            problems.append("commission_bps cannot be negative")
        if self.minimum_commission < 0:
            problems.append("minimum_commission cannot be negative")
        if self.latency_ms < 0:
            problems.append("latency_ms cannot be negative")
        if self.max_quote_age_seconds <= 0:
            problems.append("max_quote_age_seconds must be positive")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@dataclass(frozen=True, slots=True)
class SimulatedFill:
    """One executed quantity at one price. An order can produce several of these."""

    fill_id: str
    order_id: str
    instrument_id: str
    venue: str
    side: Side
    quantity: Decimal
    #: The price actually paid: the executable side of the real quote, moved adversely by slippage.
    price: Decimal
    commission: Decimal
    currency: str
    #: The quote this fill executed against, so the fill can always be traced to real data.
    reference_price: Decimal
    bid_at_fill: Decimal | None
    ask_at_fill: Decimal | None
    quote_source: str
    quote_observed_at: str | None
    #: Cost modelled as paid between observing the quote and the venue acknowledging the order.
    latency_ms: int
    slippage_bps_applied: Decimal
    simulated: bool = True
    filled_at: str = field(default_factory=lambda: iso_utc(utc_now()))

    @property
    def notional(self) -> Decimal:
        return (self.quantity * self.price).quantize(Decimal("0.00000001"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "side": self.side.value,
            "quantity": str(self.quantity),
            "price": str(self.price),
            "commission": str(self.commission),
            "currency": self.currency,
            "reference_price": str(self.reference_price),
            "bid_at_fill": None if self.bid_at_fill is None else str(self.bid_at_fill),
            "ask_at_fill": None if self.ask_at_fill is None else str(self.ask_at_fill),
            "quote_source": self.quote_source,
            "quote_observed_at": self.quote_observed_at,
            "latency_ms": self.latency_ms,
            "slippage_bps_applied": str(self.slippage_bps_applied),
            "simulated": True,
            "filled_at": self.filled_at,
        }


@dataclass(frozen=True, slots=True)
class FillOutcome:
    """What the model did with an order, and why.

    ``fills`` may be empty — that is a normal, informative outcome, not an error. ``remaining`` is
    what was left unfilled, so a partially filled order can be reported honestly rather than being
    rounded up to a full fill.
    """

    order_id: str
    fills: tuple[SimulatedFill, ...]
    filled_quantity: Decimal
    remaining_quantity: Decimal
    no_fill_reason: NoFillReason | None = None
    detail: str = ""
    quote_age_seconds: Decimal | None = None
    simulated: bool = True

    @property
    def filled(self) -> bool:
        return bool(self.fills)

    @property
    def partially_filled(self) -> bool:
        return bool(self.fills) and self.remaining_quantity > 0

    @property
    def total_commission(self) -> Decimal:
        return sum((fill.commission for fill in self.fills), Decimal("0"))

    @property
    def average_price(self) -> Decimal | None:
        if self.filled_quantity <= 0:
            return None
        notional = sum((fill.quantity * fill.price for fill in self.fills), Decimal("0"))
        return (notional / self.filled_quantity).quantize(Decimal("0.00000001"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "filled": self.filled,
            "partially_filled": self.partially_filled,
            "filled_quantity": str(self.filled_quantity),
            "remaining_quantity": str(self.remaining_quantity),
            "average_price": None if self.average_price is None else str(self.average_price),
            "total_commission": str(self.total_commission),
            "no_fill_reason": None if self.no_fill_reason is None else self.no_fill_reason.value,
            "detail": self.detail,
            "quote_age_seconds": None if self.quote_age_seconds is None else str(self.quote_age_seconds),
            "fills": [fill.to_dict() for fill in self.fills],
            "simulated": True,
        }


class SimulatedFillModel:
    """Turns a real quote and an order into simulated executions.

    Stateless apart from its RNG, which is seeded so a replay is a replay. Thread-safe by the same
    discipline the rest of the codebase uses: the RNG is the only mutable thing, and it is guarded.
    """

    def __init__(self, config: FillModelConfig | None = None) -> None:
        self._config = (config or FillModelConfig()).validated()
        # S311 warns that `random` is not cryptographically secure. Nothing here needs it to be:
        # this draws the size of a simulated slippage, where the property that matters is
        # reproducibility, which a seeded Mersenne Twister has and a CSPRNG deliberately does not.
        self._rng = random.Random(self._config.seed)  # noqa: S311
        self._lock = threading.RLock()

    @property
    def config(self) -> FillModelConfig:
        return self._config

    def describe(self) -> dict[str, Any]:
        """The cost model, published so a result can never be read without its assumptions."""
        return {
            "slippage_bps": str(self._config.slippage_bps),
            "commission_bps": str(self._config.commission_bps),
            "minimum_commission": str(self._config.minimum_commission),
            "latency_ms": self._config.latency_ms,
            "max_quote_age_seconds": str(self._config.max_quote_age_seconds),
            "respect_displayed_size": self._config.respect_displayed_size,
            "refuse_delayed_data": self._config.refuse_delayed_data,
            "seed": self._config.seed,
            "simulated": True,
        }

    def simulate(
        self,
        *,
        order_id: str | None,
        instrument_id: str,
        venue: str,
        side: Side,
        quantity: Decimal,
        quote: Any,
        limit_price: Decimal | None = None,
        currency: str = "USD",
        now: datetime | None = None,
    ) -> FillOutcome:
        """Simulate one marketable order against ``quote``.

        ``quote`` is a :class:`~nexus.data.records.QuoteRecord` — deliberately untyped here so the
        model can also be driven by a replayed historical quote, which is what makes the same code
        usable for both real-time paper trading and a re-run over archived data.
        """
        oid = order_id or new_id("PPO")
        moment = now or utc_now()
        if quantity <= 0:
            return FillOutcome(
                order_id=oid,
                fills=(),
                filled_quantity=Decimal("0"),
                remaining_quantity=quantity,
                no_fill_reason=NoFillReason.NO_LIQUIDITY,
                detail=f"quantity must be positive, got {quantity}",
            )

        age = self._quote_age(quote, moment)
        refusal = self._refusal(quote, side, limit_price, age)
        if refusal is not None:
            reason, detail = refusal
            return FillOutcome(
                order_id=oid,
                fills=(),
                filled_quantity=Decimal("0"),
                remaining_quantity=quantity,
                no_fill_reason=reason,
                detail=detail,
                quote_age_seconds=age,
            )

        # A buy crosses to the ask, a sell to the bid. Filling at the mid would be a gift the venue
        # never gives, and would overstate every strategy that trades frequently.
        executable = quote.ask if side is Side.BUY else quote.bid
        assert executable is not None  # guaranteed by _refusal
        available = self._available_size(quote, side)
        filled_qty = quantity if available is None else min(quantity, available)
        if filled_qty <= 0:
            return FillOutcome(
                order_id=oid,
                fills=(),
                filled_quantity=Decimal("0"),
                remaining_quantity=quantity,
                no_fill_reason=NoFillReason.NO_LIQUIDITY,
                detail="the quote displayed no size on the executable side",
                quote_age_seconds=age,
            )

        slip_bps = self._draw_slippage()
        price = self._apply_slippage(executable, side, slip_bps)
        fill = SimulatedFill(
            fill_id=new_id("PFL"),
            order_id=oid,
            instrument_id=instrument_id,
            venue=venue,
            side=side,
            quantity=filled_qty,
            price=price,
            commission=self._commission(filled_qty, price),
            currency=currency,
            reference_price=executable,
            bid_at_fill=quote.bid,
            ask_at_fill=quote.ask,
            quote_source=getattr(quote, "source", "UNKNOWN"),
            quote_observed_at=self._stamp(quote),
            latency_ms=self._config.latency_ms,
            slippage_bps_applied=slip_bps,
            filled_at=iso_utc(moment + timedelta(milliseconds=self._config.latency_ms)),
        )
        return FillOutcome(
            order_id=oid,
            fills=(fill,),
            filled_quantity=filled_qty,
            remaining_quantity=quantity - filled_qty,
            quote_age_seconds=age,
        )

    # -- internals ---------------------------------------------------------

    def _refusal(
        self, quote: Any, side: Side, limit_price: Decimal | None, age: Decimal | None
    ) -> tuple[NoFillReason, str] | None:
        if quote is None:
            return NoFillReason.NO_QUOTE, "no quote has been observed for this instrument yet"
        if getattr(quote, "is_crossed_or_locked", False):
            # A crossed or locked book is not a price anyone can trade at; it is a data problem or
            # a market in the middle of an auction. Filling against it would be inventing a price.
            return (
                NoFillReason.CROSSED_OR_LOCKED,
                f"bid {quote.bid} is not below ask {quote.ask}; the book is crossed or locked",
            )
        if getattr(quote, "delayed", False) and self._config.refuse_delayed_data:
            return (
                NoFillReason.DELAYED_DATA_REFUSED,
                f"the quote from {getattr(quote, 'source', 'UNKNOWN')} is delayed; filling against "
                "it would credit the strategy with an edge that belongs to an undelayed participant",
            )
        executable = quote.ask if side is Side.BUY else quote.bid
        if executable is None:
            return (
                NoFillReason.NO_EXECUTABLE_SIDE,
                f"the quote carries no {'ask' if side is Side.BUY else 'bid'}, so there is nothing to cross",
            )
        if age is not None and age > self._config.max_quote_age_seconds:
            return (
                NoFillReason.STALE_QUOTE,
                f"the quote is {age}s old, older than the {self._config.max_quote_age_seconds}s this "
                "model will trade against",
            )
        if limit_price is not None:
            if side is Side.BUY and executable > limit_price:
                return (
                    NoFillReason.LIMIT_NOT_MARKETABLE,
                    f"ask {executable} is above the limit {limit_price}; a real venue would leave "
                    "this resting, not fill it",
                )
            if side is Side.SELL and executable < limit_price:
                return (
                    NoFillReason.LIMIT_NOT_MARKETABLE,
                    f"bid {executable} is below the limit {limit_price}; a real venue would leave "
                    "this resting, not fill it",
                )
        return None

    def _quote_age(self, quote: Any, now: datetime) -> Decimal | None:
        observed = getattr(quote, "observed_at", None)
        if not isinstance(observed, datetime):
            return None
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return Decimal((now - observed).total_seconds()).quantize(Decimal("0.001"))

    def _available_size(self, quote: Any, side: Side) -> Decimal | None:
        if not self._config.respect_displayed_size:
            return None
        size = quote.ask_size if side is Side.BUY else quote.bid_size
        return size if isinstance(size, Decimal) else None

    def _draw_slippage(self) -> Decimal:
        """Slippage drawn adverse to the order, mean ``slippage_bps``, never favourable.

        Uniform on [0, 2x] rather than normal: a normal draw would regularly produce a *negative*
        slippage, which is the order getting a better price than the book showed. That happens in
        real markets, but modelling it here would let a strategy look profitable because the
        simulator was generous to it.
        """
        with self._lock:
            factor = Decimal(str(self._rng.uniform(0.0, 2.0)))
        return (self._config.slippage_bps * factor).quantize(Decimal("0.0001"))

    def _apply_slippage(self, price: Decimal, side: Side, slip_bps: Decimal) -> Decimal:
        move = price * slip_bps / _BPS
        worse = price + move if side is Side.BUY else price - move
        if worse <= 0:
            # A slippage large enough to take a price through zero means the model has been given
            # absurd inputs. Clamping at zero would book a free position, so this refuses instead.
            raise ValueError(f"slippage of {slip_bps}bps drove {price} to {worse}; refusing to guess")
        return worse.quantize(Decimal("0.00000001"))

    def _commission(self, quantity: Decimal, price: Decimal) -> Decimal:
        notional = quantity * price
        computed = notional * self._config.commission_bps / _BPS
        return max(computed, self._config.minimum_commission).quantize(Decimal("0.00000001"))

    def _stamp(self, quote: Any) -> str | None:
        observed = getattr(quote, "observed_at", None)
        if isinstance(observed, datetime):
            return iso_utc(observed)
        venue_stamp = getattr(quote, "venue_timestamp", None)
        return iso_utc(venue_stamp) if isinstance(venue_stamp, datetime) else None
