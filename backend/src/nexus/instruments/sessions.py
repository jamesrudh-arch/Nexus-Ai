"""Trading sessions and market calendars (Section 4.3, Section 11.6).

Why this exists: a feed going quiet at Friday 22:00 UTC is **not** a data fault, and a
feed going quiet on a Tuesday is. Without a calendar the freshness gate cannot tell those
apart, so it would either cry wolf every weekend or miss a real outage. This module is the
authority on "is this market supposed to be trading right now?".

Honesty rules (Appendix C):

* **DST is handled by IANA zone data**, never by hard-coded UTC offsets. FX open/close is
  defined in ``America/New_York`` and converted, so the UTC instant moves with the season.
* **Holiday coverage is declared, not assumed.** If no holiday set is loaded for an
  exchange, the answer carries ``confidence=PARTIAL`` — the caller can see that the
  calendar knows the weekday rule but not the holiday list. It never silently claims to be
  authoritative.
* **Unknown asset class → CLOSED with ``confidence=UNKNOWN``.** An unrecognised instrument
  is treated as not trading, which blocks new risk rather than enabling it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from nexus.core.ids import iso_utc
from nexus.domain.instrument import AssetClass

_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")

#: FX spot runs Sunday 17:00 New York to Friday 17:00 New York. Expressed in local NY time
#: so daylight saving shifts the UTC instant automatically.
FX_WEEK_OPEN_DOW = 6  # Sunday
FX_WEEK_CLOSE_DOW = 4  # Friday
FX_SESSION_TIME = time(17, 0)


class SessionKind(StrEnum):
    CONTINUOUS_24_7 = "CONTINUOUS_24_7"
    FX_24X5 = "FX_24X5"
    EXCHANGE_REGULAR = "EXCHANGE_REGULAR"
    CLOSED = "CLOSED"


class CalendarConfidence(StrEnum):
    """How much the answer can be trusted. Surfaced in the UI next to every session."""

    FULL = "FULL"  # weekday rule + holiday set + verified hours
    PARTIAL = "PARTIAL"  # weekday rule only; holidays unknown
    UNKNOWN = "UNKNOWN"  # no rule for this asset class / exchange


@dataclass(frozen=True, slots=True)
class ExchangeHours:
    """Regular session for one exchange, in the exchange's own timezone."""

    exchange: str
    timezone: str
    open_time: time
    close_time: time
    trading_days: frozenset[int]  # ISO weekday numbers, Mon=1 .. Sun=7
    label: str = ""

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def contains(self, moment_local: datetime) -> bool:
        if moment_local.isoweekday() not in self.trading_days:
            return False
        return self.open_time <= moment_local.time() < self.close_time


#: Seed hours for exchanges in scope. These are the *regular* sessions only; holiday sets
#: are loaded separately and coverage is reported honestly until they are.
EXCHANGE_HOURS: dict[str, ExchangeHours] = {
    "NYSE": ExchangeHours(
        "NYSE", "America/New_York", time(9, 30), time(16, 0), frozenset({1, 2, 3, 4, 5}), "US equities"
    ),
    "NASDAQ": ExchangeHours(
        "NASDAQ", "America/New_York", time(9, 30), time(16, 0), frozenset({1, 2, 3, 4, 5}), "US equities"
    ),
    "LSE": ExchangeHours(
        "LSE", "Europe/London", time(8, 0), time(16, 30), frozenset({1, 2, 3, 4, 5}), "UK equities"
    ),
    "NGX": ExchangeHours(
        "NGX", "Africa/Lagos", time(9, 30), time(14, 30), frozenset({1, 2, 3, 4, 5}), "Nigerian equities"
    ),
    "CME": ExchangeHours(
        "CME", "America/Chicago", time(17, 0), time(16, 0), frozenset({1, 2, 3, 4, 5}), "CME futures"
    ),
}


@dataclass(frozen=True, slots=True)
class CalendarStatus:
    """Answer to "should this market be trading now?" plus the next transitions."""

    instrument_id: str
    is_open: bool
    kind: SessionKind
    confidence: CalendarConfidence
    reasons: tuple[str, ...] = ()
    next_open: datetime | None = None
    next_close: datetime | None = None
    checked_at: datetime | None = None

    @property
    def is_closed_by_calendar(self) -> bool:
        """True when silence is *expected* — so the freshness gate must not call it stale."""
        return not self.is_open and self.confidence != CalendarConfidence.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "is_open": self.is_open,
            "kind": self.kind.value,
            "confidence": self.confidence.value,
            "reasons": list(self.reasons),
            "next_open": iso_utc(self.next_open) if self.next_open else None,
            "next_close": iso_utc(self.next_close) if self.next_close else None,
            "checked_at": iso_utc(self.checked_at) if self.checked_at else None,
        }


class HolidaySet:
    """Exchange holidays. Free sources publish these; until loaded, coverage is PARTIAL."""

    def __init__(self, holidays: Iterable[tuple[str, date]] = ()) -> None:
        self._by_exchange: dict[str, set[date]] = {}
        for exchange, day in holidays:
            self._by_exchange.setdefault(exchange.upper(), set()).add(day)

    def add(self, exchange: str, days: Iterable[date]) -> None:
        bucket = self._by_exchange.setdefault(exchange.upper(), set())
        bucket.update(days)

    def is_holiday(self, exchange: str, day: date) -> bool:
        return day in self._by_exchange.get(exchange.upper(), set())

    def covers(self, exchange: str) -> bool:
        """True only when a (possibly empty) holiday list has been supplied for that exchange."""
        return exchange.upper() in self._by_exchange

    def exchanges(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_exchange))

    def count(self, exchange: str) -> int:
        return len(self._by_exchange.get(exchange.upper(), set()))

    @classmethod
    def from_mapping(cls, raw: dict[str, Iterable[str]]) -> HolidaySet:
        """Build from ``{"NYSE": ["2026-01-01", ...]}`` — the shape a free JSON feed gives."""
        out = cls()
        for exchange, days in raw.items():
            out.add(exchange, [date.fromisoformat(d) for d in days])
        return out


def _session_kind_for(asset_class: AssetClass) -> SessionKind:
    if asset_class in (
        AssetClass.CRYPTO_SPOT,
        AssetClass.CRYPTO_PERP,
        AssetClass.CRYPTO_FUTURES,
        AssetClass.CRYPTO_OPTIONS,
    ):
        return SessionKind.CONTINUOUS_24_7
    if asset_class in (AssetClass.FX_SPOT, AssetClass.FX_CFD, AssetClass.METALS):
        return SessionKind.FX_24X5
    if asset_class in (
        AssetClass.EQUITIES,
        AssetClass.ETF,
        AssetClass.INDICES,
        AssetClass.FUTURES,
        AssetClass.OPTIONS,
        AssetClass.COMMODITIES,
    ):
        return SessionKind.EXCHANGE_REGULAR
    return SessionKind.CLOSED


def fx_week_is_open(now: datetime) -> bool:
    """FX spot weekly window, evaluated in New York local time (DST-correct)."""
    local = now.astimezone(_NY)
    dow = local.weekday()  # Mon=0 .. Sun=6
    if dow == FX_WEEK_OPEN_DOW:  # Sunday: open from 17:00
        return local.time() >= FX_SESSION_TIME
    if dow == FX_WEEK_CLOSE_DOW:  # Friday: open until 17:00
        return local.time() < FX_SESSION_TIME
    return dow != 5  # Saturday closed; Mon-Thu continuous


def _fx_week_open_after(now: datetime) -> datetime:
    local = now.astimezone(_NY)
    candidate = local
    for _ in range(9):
        candidate = candidate + timedelta(days=1)
        candidate = candidate.replace(hour=FX_SESSION_TIME.hour, minute=0, second=0, microsecond=0)
        if candidate.weekday() == FX_WEEK_OPEN_DOW:
            return candidate.astimezone(_UTC)
    return local.astimezone(_UTC)


def _fx_week_close_after(now: datetime) -> datetime:
    local = now.astimezone(_NY)
    candidate = local.replace(hour=FX_SESSION_TIME.hour, minute=0, second=0, microsecond=0)
    for _ in range(9):
        if candidate.weekday() == FX_WEEK_CLOSE_DOW and candidate > local:
            return candidate.astimezone(_UTC)
        candidate = candidate + timedelta(days=1)
    return local.astimezone(_UTC)


class MarketCalendar:
    """Resolves session state for an instrument from its asset class and venue exchange."""

    def __init__(
        self,
        *,
        holidays: HolidaySet | None = None,
        exchange_hours: dict[str, ExchangeHours] | None = None,
    ) -> None:
        self._holidays = holidays or HolidaySet()
        self._hours = exchange_hours if exchange_hours is not None else dict(EXCHANGE_HOURS)

    @property
    def holiday_exchanges(self) -> tuple[str, ...]:
        return self._holidays.exchanges()

    def status(
        self,
        *,
        instrument_id: str,
        asset_class: AssetClass,
        exchange: str | None = None,
        now: datetime,
    ) -> CalendarStatus:
        """Evaluate whether the market should be open at ``now`` (aware UTC)."""
        kind = _session_kind_for(asset_class)

        if kind is SessionKind.CONTINUOUS_24_7:
            return CalendarStatus(
                instrument_id=instrument_id,
                is_open=True,
                kind=kind,
                confidence=CalendarConfidence.FULL,
                reasons=("crypto trades continuously; no exchange holiday applies",),
                next_close=None,
                checked_at=now,
            )

        if kind is SessionKind.FX_24X5:
            is_open = fx_week_is_open(now)
            window_note = (
                "inside FX weekly window (Sun 17:00 - Fri 17:00 America/New_York)"
                if is_open
                else "outside FX weekly window; broker feed silence is expected"
            )
            return CalendarStatus(
                instrument_id=instrument_id,
                is_open=is_open,
                kind=kind,
                confidence=CalendarConfidence.PARTIAL,  # bank holidays can still close FX
                reasons=(window_note, "holiday coverage: none (bank holidays not loaded)"),
                next_open=None if is_open else _fx_week_open_after(now),
                next_close=_fx_week_close_after(now) if is_open else None,
                checked_at=now,
            )

        if kind is SessionKind.EXCHANGE_REGULAR:
            if exchange is None:
                return CalendarStatus(
                    instrument_id=instrument_id,
                    is_open=False,
                    kind=SessionKind.CLOSED,
                    confidence=CalendarConfidence.UNKNOWN,
                    reasons=("no exchange recorded for this instrument; treated as closed",),
                    checked_at=now,
                )
            hours = self._hours.get(exchange.upper())
            if hours is None:
                return CalendarStatus(
                    instrument_id=instrument_id,
                    is_open=False,
                    kind=SessionKind.CLOSED,
                    confidence=CalendarConfidence.UNKNOWN,
                    reasons=(f"no session table for exchange {exchange}; treated as closed",),
                    checked_at=now,
                )
            local = now.astimezone(hours.tz)
            day = local.date()
            holiday_known = self._holidays.covers(exchange)
            if holiday_known and self._holidays.is_holiday(exchange, day):
                return CalendarStatus(
                    instrument_id=instrument_id,
                    is_open=False,
                    kind=SessionKind.EXCHANGE_REGULAR,
                    confidence=CalendarConfidence.FULL,
                    reasons=(f"{exchange} holiday on {day.isoformat()}",),
                    next_open=_next_exchange_open(hours, local, self._holidays),
                    checked_at=now,
                )
            is_open = hours.contains(local)
            confidence = CalendarConfidence.FULL if holiday_known else CalendarConfidence.PARTIAL
            session_text = f"{hours.open_time:%H:%M}-{hours.close_time:%H:%M} {hours.timezone}"
            reasons: tuple[str, ...] = (f"{exchange} regular session {session_text}",)
            if not holiday_known:
                reasons = (*reasons, f"holiday coverage: none for {exchange} — answer is PARTIAL")
            if is_open:
                close_local = local.replace(
                    hour=hours.close_time.hour,
                    minute=hours.close_time.minute,
                    second=0,
                    microsecond=0,
                )
                next_close = close_local.astimezone(_UTC) if close_local > local else None
            else:
                next_close = None
            return CalendarStatus(
                instrument_id=instrument_id,
                is_open=is_open,
                kind=SessionKind.EXCHANGE_REGULAR,
                confidence=confidence,
                reasons=reasons,
                next_open=None if is_open else _next_exchange_open(hours, local, self._holidays),
                next_close=next_close,
                checked_at=now,
            )

        return CalendarStatus(
            instrument_id=instrument_id,
            is_open=False,
            kind=SessionKind.CLOSED,
            confidence=CalendarConfidence.UNKNOWN,
            reasons=(f"unsupported asset class {asset_class.value}; treated as closed",),
            checked_at=now,
        )


def _next_exchange_open(hours: ExchangeHours, local_now: datetime, holidays: HolidaySet) -> datetime:
    """Next regular open after ``local_now``, skipping non-trading days and holidays."""
    candidate = local_now.replace(
        hour=hours.open_time.hour,
        minute=hours.open_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate = candidate + timedelta(days=1)
    for _ in range(400):  # bounded: ~14 months of skips is already absurd
        if candidate.isoweekday() in hours.trading_days and not (
            holidays.covers(hours.exchange) and holidays.is_holiday(hours.exchange, candidate.date())
        ):
            return candidate.astimezone(_UTC)
        candidate = candidate + timedelta(days=1)
    return candidate.astimezone(_UTC)


def asset_class_sessions(asset_class: AssetClass) -> SessionKind:
    """Public helper: what kind of session does this asset class have?"""
    return _session_kind_for(asset_class)


def describe_exchange(exchange: str) -> dict[str, Any]:
    """Human-readable session info for the Connections and Global Markets pages."""
    hours = EXCHANGE_HOURS.get(exchange.upper())
    if hours is None:
        return {"exchange": exchange, "known": False}
    return {
        "exchange": hours.exchange,
        "known": True,
        "timezone": hours.timezone,
        "open": f"{hours.open_time:%H:%M}",
        "close": f"{hours.close_time:%H:%M}",
        "trading_days": sorted(hours.trading_days),
        "label": hours.label,
    }


__all__ = [
    "EXCHANGE_HOURS",
    "CalendarConfidence",
    "CalendarStatus",
    "ExchangeHours",
    "HolidaySet",
    "MarketCalendar",
    "SessionKind",
    "asset_class_sessions",
    "describe_exchange",
    "fx_week_is_open",
]
