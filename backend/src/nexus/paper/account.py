"""The paper account: simulated capital, positions and P&L (Stage 11, D-059).

Every number in here is money that does not exist, and the module is written so that fact cannot be
forgotten downstream. Three consequences shape the design:

**It is labelled, not hidden.** Every snapshot carries ``simulated: True`` and ``environment:
"PAPER"``, and the balance is named ``simulated_cash`` rather than ``cash``. ``docs/03`` §3.5
forbids a screen that shows a fake balance without saying so; the cheapest way to guarantee that is
to make the honest name the only name available.

**It is Decimal, end to end.** Money never touches a float in this codebase and paper money is not
an exception — a simulated account that drifts a cent per fill teaches nothing about whether a
strategy is profitable, because the drift and the edge are the same order of magnitude.

**It is append-only in effect.** A position is recomputed from its fills rather than mutated in
place, so a corrupted account can be rebuilt from the fill ledger and, more importantly, so the
ledger stays the thing that is true. ``rebuild_from_fills`` is the proof: if it can reproduce the
account, the account was never the source of record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from nexus.core.ids import iso_utc, utc_now

__all__ = [
    "PaperAccount",
    "PaperPosition",
    "PaperSnapshot",
    "rebuild_from_fills",
]

_CENT = Decimal("0.01")
_QTY = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class PaperPosition:
    """One instrument on one venue, held in the paper account.

    ``quantity`` is signed: positive is long, negative is short. ``average_entry`` is the
    volume-weighted cost of the quantity still open, which is what makes unrealised P&L meaningful
    after a partial close.
    """

    instrument_id: str
    venue: str
    quantity: Decimal
    average_entry: Decimal
    realized_pnl: Decimal = Decimal("0")
    commission_paid: Decimal = Decimal("0")
    fills: int = 0
    opened_at: str | None = None
    updated_at: str | None = None

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return "LONG"
        return "SHORT" if self.quantity < 0 else "FLAT"

    def unrealized_pnl(self, mark: Decimal | None) -> Decimal:
        """P&L of the open quantity against a *real* last price.

        Returns zero when there is no mark. A position with no current price has no honest
        unrealised P&L, and inventing one from the entry price would show a flat line where the
        truth is "unknown".
        """
        if mark is None or self.is_flat:
            return Decimal("0")
        return ((mark - self.average_entry) * self.quantity).quantize(_CENT)

    def notional(self, mark: Decimal | None) -> Decimal:
        price = mark if mark is not None else self.average_entry
        return (self.quantity * price).quantize(_CENT)

    def to_dict(self, *, mark: Decimal | None = None) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "quantity": str(self.quantity),
            "side": self.side,
            "average_entry": str(self.average_entry),
            "mark": None if mark is None else str(mark),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl(mark)),
            "commission_paid": str(self.commission_paid),
            "notional": str(self.notional(mark)),
            "fills": self.fills,
            "opened_at": self.opened_at,
            "updated_at": self.updated_at,
            "marked_with_real_data": mark is not None,
            "simulated": True,
        }


@dataclass(frozen=True, slots=True)
class PaperAccount:
    """The account itself. Immutable: applying a fill returns a new one."""

    account_id: str
    currency: str = "USD"
    simulated_cash: Decimal = Decimal("100000")
    starting_cash: Decimal = Decimal("100000")
    positions: tuple[PaperPosition, ...] = ()
    realized_pnl: Decimal = Decimal("0")
    commission_paid: Decimal = Decimal("0")
    fills_applied: int = 0
    created_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    updated_at: str = field(default_factory=lambda: iso_utc(utc_now()))

    def position(self, instrument_id: str, venue: str) -> PaperPosition | None:
        for held in self.positions:
            if held.instrument_id == instrument_id and held.venue == venue:
                return held
        return None

    @property
    def open_positions(self) -> tuple[PaperPosition, ...]:
        return tuple(held for held in self.positions if not held.is_flat)

    def equity(self, marks: dict[tuple[str, str], Decimal] | None = None) -> Decimal:
        """Cash plus the marked value of every open position.

        ``marks`` maps ``(instrument_id, venue)`` to a real last price. Positions with no mark are
        carried at their average entry, and the snapshot says so — carrying at entry is an
        assumption, and an assumption in an equity number has to be visible.
        """
        value = self.simulated_cash
        for held in self.positions:
            mark = None if marks is None else marks.get((held.instrument_id, held.venue))
            value += held.notional(mark)
        return value.quantize(_CENT)

    def apply_fill(
        self,
        *,
        instrument_id: str,
        venue: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        at: str | None = None,
    ) -> PaperAccount:
        """Return the account as it is after this fill. The receiver is unchanged."""
        if quantity <= 0:
            raise ValueError(f"a fill must carry a positive quantity, got {quantity}")
        if price <= 0:
            raise ValueError(f"a fill must carry a positive price, got {price}")
        signed = quantity if side == "BUY" else -quantity
        held = self.position(instrument_id, venue)
        previous = held.quantity if held is not None else Decimal("0")
        entry = held.average_entry if held is not None else Decimal("0")
        after = previous + signed
        realized = Decimal("0")

        # Whether this fill trades *against* the position already held. That one fact decides both
        # the realised P&L and what the entry of whatever remains should be.
        opposing = previous != 0 and (previous > 0) != (signed > 0)
        closed_quantity = min(abs(previous), abs(signed)) if opposing else Decimal("0")
        if closed_quantity > 0:
            # Realised P&L is booked on the quantity actually closed, entry to exit, and booked here
            # rather than at mark time so it depends only on fills — the one thing the ledger
            # records. A *partial* close realises too: selling 4 of 10 units at a profit has made
            # that profit whether or not the position is now flat, and reporting zero until the last
            # unit goes would understate every strategy that scales out of a position.
            direction = Decimal("1") if previous > 0 else Decimal("-1")
            realized = ((price - entry) * closed_quantity * direction).quantize(_CENT)

        if not opposing:
            # Opening from flat, or adding in the same direction: the entry becomes the
            # volume-weighted average of everything now held.
            total = abs(previous) + abs(signed)
            new_entry = ((abs(previous) * entry + abs(signed) * price) / total if total else price).quantize(
                Decimal("0.00000001")
            )
        else:
            # Reducing, closing or flipping. If the fill was larger than the position it flipped
            # through flat, so what remains was opened by this fill rather than by the old one.
            new_entry = price if abs(signed) > abs(previous) else entry

        stamp = at or iso_utc(utc_now())
        updated = PaperPosition(
            instrument_id=instrument_id,
            venue=venue,
            quantity=after.quantize(_QTY),
            average_entry=new_entry.quantize(Decimal("0.00000001")),
            realized_pnl=(held.realized_pnl if held is not None else Decimal("0")) + realized,
            commission_paid=(held.commission_paid if held is not None else Decimal("0")) + commission,
            fills=(held.fills if held is not None else 0) + 1,
            opened_at=held.opened_at if held is not None and held.opened_at else stamp,
            updated_at=stamp,
        )
        others = tuple(
            existing
            for existing in self.positions
            if not (existing.instrument_id == instrument_id and existing.venue == venue)
        )
        return PaperAccount(
            account_id=self.account_id,
            currency=self.currency,
            # Buying spends cash, selling returns it; commission is always spent.
            simulated_cash=(self.simulated_cash - signed * price - commission).quantize(_CENT),
            starting_cash=self.starting_cash,
            positions=(*others, updated),
            realized_pnl=(self.realized_pnl + realized).quantize(_CENT),
            commission_paid=(self.commission_paid + commission).quantize(_CENT),
            fills_applied=self.fills_applied + 1,
            created_at=self.created_at,
            updated_at=stamp,
        )

    def snapshot(self, marks: dict[tuple[str, str], Decimal] | None = None) -> PaperSnapshot:
        equity = self.equity(marks)
        unrealized = sum(
            (
                held.unrealized_pnl(None if marks is None else marks.get((held.instrument_id, held.venue)))
                for held in self.positions
            ),
            Decimal("0"),
        ).quantize(_CENT)
        unmarked = tuple(
            held
            for held in self.open_positions
            if marks is None or (held.instrument_id, held.venue) not in marks
        )
        return PaperSnapshot(
            account_id=self.account_id,
            currency=self.currency,
            simulated_cash=self.simulated_cash,
            starting_cash=self.starting_cash,
            equity=equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            commission_paid=self.commission_paid,
            net_pnl=(self.realized_pnl + unrealized - self.commission_paid).quantize(_CENT),
            return_pct=(
                ((equity - self.starting_cash) / self.starting_cash * Decimal(100)).quantize(
                    Decimal("0.0001")
                )
                if self.starting_cash
                else Decimal("0")
            ),
            positions=tuple(
                held.to_dict(mark=None if marks is None else marks.get((held.instrument_id, held.venue)))
                for held in self.positions
            ),
            open_position_count=len(self.open_positions),
            fills_applied=self.fills_applied,
            positions_marked_with_real_data=len(self.open_positions) - len(unmarked),
            positions_carried_at_entry=tuple(f"{held.instrument_id}@{held.venue}" for held in unmarked),
            updated_at=self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class PaperSnapshot:
    """The account as a screen can show it — with its assumptions named."""

    account_id: str
    currency: str
    simulated_cash: Decimal
    starting_cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    commission_paid: Decimal
    net_pnl: Decimal
    return_pct: Decimal
    positions: tuple[dict[str, Any], ...]
    open_position_count: int
    fills_applied: int
    positions_marked_with_real_data: int
    positions_carried_at_entry: tuple[str, ...]
    updated_at: str
    simulated: bool = True
    environment: str = "PAPER"

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "currency": self.currency,
            "simulated_cash": str(self.simulated_cash),
            "starting_cash": str(self.starting_cash),
            "equity": str(self.equity),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "commission_paid": str(self.commission_paid),
            "net_pnl": str(self.net_pnl),
            "return_pct": str(self.return_pct),
            "positions": list(self.positions),
            "open_position_count": self.open_position_count,
            "fills_applied": self.fills_applied,
            "positions_marked_with_real_data": self.positions_marked_with_real_data,
            "positions_carried_at_entry": list(self.positions_carried_at_entry),
            "updated_at": self.updated_at,
            "simulated": True,
            "environment": "PAPER",
        }


def rebuild_from_fills(
    *,
    account_id: str,
    fills: Any,
    currency: str = "USD",
    starting_cash: Decimal = Decimal("100000"),
) -> PaperAccount:
    """Recompute an account from its fill ledger.

    This exists because the ledger is the system of record and the account is a projection of it. If
    the two ever disagree, this is how the truth is restored — and the fact that it *can* restore
    the truth is what makes the projection safe to keep in a database at all.
    """
    account = PaperAccount(
        account_id=account_id,
        currency=currency,
        simulated_cash=starting_cash,
        starting_cash=starting_cash,
    )
    for fill in fills:
        account = account.apply_fill(
            instrument_id=fill["instrument_id"],
            venue=fill["venue"],
            side=fill["side"],
            quantity=Decimal(str(fill["quantity"])),
            price=Decimal(str(fill["price"])),
            commission=Decimal(str(fill.get("commission", "0"))),
            at=fill.get("filled_at"),
        )
    return account
