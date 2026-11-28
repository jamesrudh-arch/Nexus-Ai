"""Deterministic risk engine (Section 10).

Pure functions, decimal arithmetic, no I/O, no model calls. Inputs that are missing or
contradictory produce a refusal — never a guess. Sizing follows the specification:

    position_size = max_loss / stop_distance_per_unit

then is reduced (never increased) by leverage, notional, liquidity, concentration and
venue-quantity constraints. The engine may REDUCE a proposed size to fit limits; it may
never enlarge one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from typing import Any

from nexus.core.errors import RejectReason
from nexus.risk.portfolio import PortfolioSnapshot

ZERO = Decimal("0")


def _q(value: float | int | str | Decimal) -> Decimal:
    """Coerce to Decimal without float noise. Rejects NaN/inf and negatives-as-sizes."""
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    if not dec.is_finite():
        raise ValueError(f"non-finite quantity rejected: {value!r}")
    return dec


@dataclass(frozen=True, slots=True)
class PositionSizeRequest:
    """Everything needed to size one candidate trade."""

    instrument_id: str
    venue: str
    side: str  # LONG | SHORT
    entry_price: Decimal | float | str
    stop_price: Decimal | float | str
    contract_size: Decimal | float | str = Decimal("1")
    quote_currency: str = "USD"
    tick_value: Decimal | float | str | None = None  # USD value of one tick per contract
    proposed_quantity: Decimal | float | str | None = None  # optional cap from strategy
    min_quantity: Decimal | float | str | None = None
    max_quantity: Decimal | float | str | None = None
    quantity_step: Decimal | float | str | None = None
    margin_rate: Decimal | float | str | None = None  # e.g. 0.5 for 2x leverage
    average_daily_volume_quote: Decimal | float | str | None = None
    fx_to_usd: Decimal | float | str = Decimal("1")


@dataclass(slots=True)
class PositionSizeResult:
    """Sizing outcome. ``approved`` False means do not trade; reasons say why."""

    approved: bool
    quantity: Decimal = ZERO
    notional_quote: Decimal = ZERO
    notional_usd: Decimal = ZERO
    risk_amount_usd: Decimal = ZERO
    stop_distance_per_unit: Decimal = ZERO
    effective_leverage: Decimal = Decimal("1")
    margin_required_usd: Decimal = ZERO
    reasons: tuple[str, ...] = ()
    reductions: list[dict[str, Any]] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "quantity": str(self.quantity),
            "notional_usd": str(self.notional_usd),
            "risk_amount_usd": str(self.risk_amount_usd),
            "stop_distance_per_unit": str(self.stop_distance_per_unit),
            "effective_leverage": str(self.effective_leverage),
            "margin_required_usd": str(self.margin_required_usd),
            "reasons": list(self.reasons),
            "reductions": self.reductions,
        }


def size_from_risk(
    max_loss: Decimal,
    stop_distance_per_unit: Decimal,
    contract_size: Decimal = Decimal("1"),
) -> Decimal:
    """Core formula: how many units risk exactly ``max_loss`` given the stop distance.

    ``stop_distance_per_unit`` is price distance per whole unit of the base asset.
    Returns 0 when the stop distance is zero or negative — an undefined stop is a refusal,
    never an infinite position.
    """
    if max_loss <= ZERO or stop_distance_per_unit <= ZERO or contract_size <= ZERO:
        return ZERO
    return max_loss / (stop_distance_per_unit * contract_size)


class RiskEngine:
    """Applies hard limits (Section 10.1) to a sizing request against a portfolio snapshot."""

    def __init__(self, limits: Any) -> None:  # RiskLimits from settings; typed loosely to avoid cycles
        self._limits = limits

    @property
    def limits(self) -> Any:
        return self._limits

    def evaluate(
        self,
        request: PositionSizeRequest,
        portfolio: PortfolioSnapshot,
    ) -> PositionSizeResult:
        """Run every limit. Any failure returns ``approved=False`` with reason codes."""
        limits = self._limits
        reasons: list[str] = []
        reductions: list[dict[str, Any]] = []

        # --- 0. Snapshot integrity (fail closed) -------------------------------
        if not portfolio.complete:
            reasons.append(RejectReason.DATA_UNAVAILABLE.value + ":portfolio snapshot incomplete")
        if portfolio.equity_usd <= ZERO:
            reasons.append(RejectReason.SIZING_UNDETERMINED.value + ":equity must be positive")
        if reasons:
            return PositionSizeResult(approved=False, reasons=tuple(reasons))

        # --- 1. Daily drawdown halt -------------------------------------------
        drawdown_pct = portfolio.daily_drawdown_pct
        halt_threshold = _q(limits.daily_drawdown_halt_pct)
        if drawdown_pct >= halt_threshold:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.DAILY_DRAWDOWN_HALT.value}:"
                    f"drawdown {drawdown_pct:.4f}% >= {halt_threshold:.4f}%",
                ),
                checks={"daily_drawdown_pct": str(drawdown_pct), "threshold_pct": str(halt_threshold)},
            )

        # --- 2. Open position count -------------------------------------------
        max_open = int(limits.max_open_positions)
        if portfolio.open_position_count >= max_open:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.MAX_OPEN_POSITIONS_EXCEEDED.value}:"
                    f"{portfolio.open_position_count} >= {max_open}",
                ),
            )

        # --- 3. Inputs ---------------------------------------------------------
        try:
            entry = _q(request.entry_price)
            stop = _q(request.stop_price)
            contract_size = _q(request.contract_size)
            fx = _q(request.fx_to_usd)
        except ValueError as exc:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.CONFIG_INVALID.value}:{exc}",),
            )
        if entry <= ZERO or contract_size <= ZERO or fx <= ZERO:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.SIZING_UNDETERMINED.value}:non-positive price/contract/fx",),
            )

        side = request.side.upper()
        if side not in ("LONG", "SHORT"):
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.CONFIG_INVALID.value}:side must be LONG or SHORT",),
            )

        stop_distance = (entry - stop) if side == "LONG" else (stop - entry)
        if stop_distance <= ZERO:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.SIZING_UNDETERMINED.value}:"
                    "stop must be on the loss side of entry (zero/negative distance refused)",
                ),
            )

        min_stop_distance = entry * _q(limits.min_stop_distance_pct) / Decimal("100")
        if stop_distance < min_stop_distance:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.SIZING_UNDETERMINED.value}:"
                    f"stop distance {stop_distance} below minimum {min_stop_distance} "
                    f"({limits.min_stop_distance_pct}% of entry)",
                ),
            )

        # --- 4. Risk-based size ------------------------------------------------
        # Specification formula: quantity = max_loss / (stop_distance_per_unit * contract_size)
        # with stop distance converted to USD, so the result is a number of contracts.
        max_risk_usd = portfolio.equity_usd * _q(limits.max_risk_per_trade_pct) / Decimal("100")
        stop_distance_usd_per_unit = stop_distance * fx  # USD at risk per whole base unit
        stop_distance_usd_per_contract = stop_distance_usd_per_unit * contract_size
        quantity = size_from_risk(max_risk_usd, stop_distance_usd_per_unit, contract_size)

        if quantity <= ZERO:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.SIZING_UNDETERMINED.value}:computed quantity is zero",),
            )

        # --- 5. Strategy-proposed cap (reduction only) -------------------------
        if request.proposed_quantity is not None:
            proposed = _q(request.proposed_quantity)
            if proposed < quantity:
                reductions.append({"reason": "strategy_cap", "from": str(quantity), "to": str(proposed)})
                quantity = proposed

        # --- 6. Notional per position -----------------------------------------
        notional_usd = quantity * contract_size * entry * fx
        max_notional = _q(limits.max_notional_per_position_usd)
        if notional_usd > max_notional and entry > ZERO:
            reduced = max_notional / (contract_size * entry * fx)
            reductions.append(
                {"reason": "max_notional_per_position", "from": str(quantity), "to": str(reduced)}
            )
            quantity = reduced
            notional_usd = quantity * contract_size * entry * fx

        # --- 7. Portfolio notional cap ----------------------------------------
        max_portfolio_notional = _q(limits.max_portfolio_notional_usd)
        projected = portfolio.total_notional_usd + notional_usd
        if projected > max_portfolio_notional:
            headroom = max_portfolio_notional - portfolio.total_notional_usd
            if headroom <= ZERO:
                return PositionSizeResult(
                    approved=False,
                    reasons=(
                        f"{RejectReason.NOTIONAL_LIMIT_EXCEEDED.value}:"
                        f"portfolio notional {portfolio.total_notional_usd} already at cap",
                    ),
                    risk_amount_usd=max_risk_usd,
                )
            reduced = headroom / (contract_size * entry * fx)
            reductions.append({"reason": "portfolio_notional_cap", "from": str(quantity), "to": str(reduced)})
            quantity = reduced
            notional_usd = quantity * contract_size * entry * fx

        # --- 8. Single-instrument concentration -------------------------------
        max_single_pct = _q(limits.max_single_instrument_exposure_pct)
        current_pct = portfolio.exposure_pct_by_instrument().get(request.instrument_id, ZERO)
        added_pct = (
            (notional_usd / portfolio.equity_usd * Decimal("100")) if portfolio.equity_usd > ZERO else ZERO
        )
        if current_pct + added_pct > max_single_pct:
            allowed_notional = max(
                ZERO, (max_single_pct - current_pct) / Decimal("100") * portfolio.equity_usd
            )
            if allowed_notional <= ZERO:
                return PositionSizeResult(
                    approved=False,
                    reasons=(
                        f"{RejectReason.CONCENTRATION_EXCEEDED.value}:"
                        f"{request.instrument_id} already at {current_pct:.4f}% of equity",
                    ),
                )
            reduced = allowed_notional / (contract_size * entry * fx)
            reductions.append(
                {"reason": "instrument_concentration", "from": str(quantity), "to": str(reduced)}
            )
            quantity = reduced
            notional_usd = quantity * contract_size * entry * fx

        # --- 9. Leverage ------------------------------------------------------
        margin_rate = _q(request.margin_rate) if request.margin_rate is not None else Decimal("1")
        if margin_rate <= ZERO:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.CONFIG_INVALID.value}:margin_rate must be positive",),
            )
        effective_leverage = Decimal("1") / margin_rate
        max_leverage = _q(limits.max_leverage)
        if effective_leverage > max_leverage:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.LEVERAGE_EXCEEDED.value}:{effective_leverage}x > {max_leverage}x",),
            )
        margin_required_usd = notional_usd * margin_rate
        if margin_required_usd > portfolio.cash_available_usd:
            reduced_qty = (
                portfolio.cash_available_usd / (contract_size * entry * fx * margin_rate)
                if contract_size * entry * fx * margin_rate > ZERO
                else ZERO
            )
            if reduced_qty <= ZERO:
                return PositionSizeResult(
                    approved=False,
                    reasons=(
                        f"{RejectReason.INSUFFICIENT_MARGIN.value}:"
                        f"required {margin_required_usd} > available {portfolio.cash_available_usd}",
                    ),
                )
            reductions.append({"reason": "available_margin", "from": str(quantity), "to": str(reduced_qty)})
            quantity = reduced_qty
            notional_usd = quantity * contract_size * entry * fx
            margin_required_usd = notional_usd * margin_rate

        # --- 10. Liquidity participation -------------------------------------
        if request.average_daily_volume_quote is not None:
            adv_usd = _q(request.average_daily_volume_quote) * fx
            max_participation = _q(limits.max_participation_of_adv_pct)
            if adv_usd > ZERO:
                cap_notional = adv_usd * max_participation / Decimal("100")
                if notional_usd > cap_notional:
                    reduced = cap_notional / (contract_size * entry * fx)
                    reductions.append(
                        {"reason": "liquidity_participation", "from": str(quantity), "to": str(reduced)}
                    )
                    quantity = reduced
                    notional_usd = quantity * contract_size * entry * fx
            else:
                return PositionSizeResult(
                    approved=False,
                    reasons=(f"{RejectReason.LIQUIDITY_INSUFFICIENT.value}:ADV is zero or unknown",),
                )

        # --- 11. Venue quantity constraints ----------------------------------
        step = _q(request.quantity_step) if request.quantity_step is not None else None
        if step is not None and step > ZERO:
            quantity = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
        max_qty = _q(request.max_quantity) if request.max_quantity is not None else None
        if max_qty is not None and quantity > max_qty:
            reductions.append({"reason": "venue_max_quantity", "from": str(quantity), "to": str(max_qty)})
            quantity = max_qty
        min_qty = _q(request.min_quantity) if request.min_quantity is not None else None
        if min_qty is not None and quantity < min_qty:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.SIZING_UNDETERMINED.value}:"
                    f"quantity {quantity} below venue minimum {min_qty} after risk reductions",
                ),
                reductions=reductions,
            )

        # --- 12. Final recomputation -----------------------------------------
        if quantity <= ZERO:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.SIZING_UNDETERMINED.value}:quantity rounded to zero",),
                reductions=reductions,
            )
        notional_quote = quantity * contract_size * entry
        notional_usd = notional_quote * fx
        risk_amount_usd = quantity * stop_distance_usd_per_contract
        margin_required_usd = notional_usd * margin_rate

        # Risk must never exceed the hard per-trade limit after reductions.
        if risk_amount_usd > max_risk_usd:
            return PositionSizeResult(
                approved=False,
                reasons=(f"{RejectReason.RISK_PER_TRADE_EXCEEDED.value}:{risk_amount_usd} > {max_risk_usd}",),
                reductions=reductions,
            )
        if margin_required_usd > portfolio.cash_available_usd:
            return PositionSizeResult(
                approved=False,
                reasons=(
                    f"{RejectReason.INSUFFICIENT_MARGIN.value}:"
                    f"{margin_required_usd} > {portfolio.cash_available_usd}",
                ),
                reductions=reductions,
            )

        return PositionSizeResult(
            approved=True,
            quantity=quantity,
            notional_quote=notional_quote,
            notional_usd=notional_usd,
            risk_amount_usd=risk_amount_usd,
            stop_distance_per_unit=stop_distance,
            effective_leverage=effective_leverage,
            margin_required_usd=margin_required_usd,
            reductions=reductions,
            checks={
                "max_risk_usd": str(max_risk_usd),
                "daily_drawdown_pct": str(drawdown_pct),
                "open_positions": portfolio.open_position_count,
                "portfolio_notional_after": str(portfolio.total_notional_usd + notional_usd),
            },
        )


@dataclass(slots=True)
class RiskCheckResult:
    """Outcome of a pre-trade governance check (limits + data + authority)."""

    allowed: bool
    reasons: tuple[str, ...] = ()
    sizing: PositionSizeResult | None = None
    checks: dict[str, Any] = field(default_factory=dict)

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "sizing": self.sizing.to_audit_payload() if self.sizing else None,
            "checks": self.checks,
        }
