"""Freshness and integrity checks for market data.

Fail-closed rules:
- A missing observation time is treated as stale, not as "now".
- A future observation time is a clock/ingestion fault, not fresh data.
- A crossed or locked book (bid >= ask) blocks new risk.
- Unknown venue state blocks new risk.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from nexus.core.errors import RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.core.time import age_seconds


class DataStatus(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    FAULT = "FAULT"  # e.g. future timestamp, crossed book, clock skew


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Best bid/ask/last for one instrument at one venue."""

    instrument_id: str
    venue: str
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    observed_at: datetime | None = None
    venue_timestamp: datetime | None = None
    delayed: bool = False
    delay_seconds: float = 0.0
    source: str = "UNKNOWN"

    @property
    def mid(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def is_crossed_or_locked(self) -> bool:
        if self.bid is None or self.ask is None:
            return False
        return self.bid >= self.ask


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Top-of-book plus depth levels, where the venue entitles us to depth."""

    instrument_id: str
    venue: str
    bids: tuple[tuple[Decimal, Decimal], ...] = ()
    asks: tuple[tuple[Decimal, Decimal], ...] = ()
    observed_at: datetime | None = None
    entitlement: str = "NONE"  # NONE | DELAYED | LIVE
    source: str = "UNKNOWN"

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0][0] if self.asks else None


@dataclass(slots=True)
class GateResult:
    """Outcome of a data-quality gate. ``new_risk_allowed`` is the binding flag."""

    ok: bool
    status: DataStatus
    new_risk_allowed: bool
    reasons: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status.value,
            "new_risk_allowed": self.new_risk_allowed,
            "reasons": list(self.reasons),
            "details": {k: str(v) for k, v in self.details.items()},
        }


class DataQualityGate:
    """Applies freshness thresholds from :class:`nexus.core.config.DataQualityLimits`."""

    def __init__(self, limits: Any, *, now_fn: Callable[[], datetime] = utc_now) -> None:
        self._limits = limits
        self._now_fn = now_fn

    def _now(self) -> datetime:
        return self._now_fn()

    def check_quote(self, snapshot: MarketSnapshot | None) -> GateResult:
        """Check a top-of-book snapshot. ``None`` is UNAVAILABLE, not fresh."""
        now = self._now()
        if snapshot is None:
            return GateResult(
                ok=False,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_UNAVAILABLE.value}:no snapshot",),
            )
        if snapshot.observed_at is None:
            return GateResult(
                ok=False,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_UNAVAILABLE.value}:missing observation time",),
                details={"instrument_id": snapshot.instrument_id, "venue": snapshot.venue},
            )
        if snapshot.observed_at > now:
            return GateResult(
                ok=False,
                status=DataStatus.FAULT,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_STALE.value}:observation time is in the future (clock fault)",),
                details={
                    "observed_at": iso_utc(snapshot.observed_at),
                    "now": iso_utc(now),
                },
            )
        if snapshot.is_crossed_or_locked:
            return GateResult(
                ok=False,
                status=DataStatus.FAULT,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_CROSSED_MARKET.value}:bid >= ask",),
                details={"bid": str(snapshot.bid), "ask": str(snapshot.ask)},
            )

        age = age_seconds(snapshot.observed_at, now=now)
        max_age = float(self._limits.max_quote_age_seconds)
        details = {
            "age_seconds": round(age, 3),
            "max_age_seconds": max_age,
            "delayed": snapshot.delayed,
        }
        if age > max_age:
            return GateResult(
                ok=False,
                status=DataStatus.STALE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_STALE.value}:age {age:.1f}s > {max_age:.1f}s",),
                details=details,
            )
        if snapshot.delayed:
            return GateResult(
                ok=True,
                status=DataStatus.DELAYED,
                new_risk_allowed=False,  # delayed data may be read, never used for new live risk
                reasons=(f"{RejectReason.DATA_STALE.value}:feed is delayed {snapshot.delay_seconds:.0f}s",),
                details=details,
            )
        return GateResult(ok=True, status=DataStatus.LIVE, new_risk_allowed=True, details=details)

    def check_book(self, book: OrderBookSnapshot | None) -> GateResult:
        """Check order-book depth. Missing entitlement is reported honestly, never faked."""
        now = self._now()
        if book is None:
            return GateResult(
                ok=False,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_UNAVAILABLE.value}:no order book",),
            )
        if book.entitlement == "NONE":
            return GateResult(
                ok=True,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=("DEPTH_UNENTITLED:venue does not provide depth for this account",),
                details={"venue": book.venue},
            )
        if book.observed_at is None:
            return GateResult(
                ok=False,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_UNAVAILABLE.value}:missing book observation time",),
            )
        age = age_seconds(book.observed_at, now=now)
        max_age = float(self._limits.max_book_age_seconds)
        details = {
            "age_seconds": round(age, 3),
            "max_age_seconds": max_age,
            "levels": len(book.bids) + len(book.asks),
        }
        if age > max_age:
            return GateResult(
                ok=False,
                status=DataStatus.STALE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_STALE.value}:book age {age:.1f}s > {max_age:.1f}s",),
                details=details,
            )
        if book.best_bid is not None and book.best_ask is not None and book.best_bid >= book.best_ask:
            return GateResult(
                ok=False,
                status=DataStatus.FAULT,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_CROSSED_MARKET.value}:book crossed or locked",),
                details=details,
            )
        return GateResult(ok=True, status=DataStatus.LIVE, new_risk_allowed=True, details=details)

    def check_account_snapshot_age(self, observed_at: datetime | None) -> GateResult:
        """Account/portfolio snapshots must be recent before sizing against them."""
        now = self._now()
        if observed_at is None:
            return GateResult(
                ok=False,
                status=DataStatus.UNAVAILABLE,
                new_risk_allowed=False,
                reasons=(f"{RejectReason.DATA_UNAVAILABLE.value}:no account snapshot time",),
            )
        age = age_seconds(observed_at, now=now)
        max_age = float(self._limits.max_account_snapshot_age_seconds)
        details = {"age_seconds": round(age, 3), "max_age_seconds": max_age}
        if age > max_age:
            return GateResult(
                ok=False,
                status=DataStatus.STALE,
                new_risk_allowed=False,
                reasons=(
                    f"{RejectReason.DATA_STALE.value}:account snapshot {age:.0f}s old > {max_age:.0f}s",
                ),
                details=details,
            )
        return GateResult(ok=True, status=DataStatus.LIVE, new_risk_allowed=True, details=details)
