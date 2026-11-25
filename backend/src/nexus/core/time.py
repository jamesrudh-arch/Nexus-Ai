"""Time helpers. All NEXUS timestamps are timezone-aware UTC.

Venue-local time is a *display* concern (Section 17): storage, ordering and audit are UTC.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(UTC)


def iso_utc(moment: datetime | None = None) -> str:
    """ISO-8601 UTC string with 'Z' suffix at millisecond precision."""
    value = moment or utc_now()
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed; pass an aware UTC datetime")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string into an aware UTC datetime. Naive input is rejected."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"naive timestamp rejected: {value!r}")
    return parsed.astimezone(UTC)


def age_seconds(moment: datetime, *, now: datetime | None = None) -> float:
    """Seconds elapsed since ``moment``. Negative ages (future stamps) return 0.0 and
    are flagged separately by the data-quality gate as a clock/ingestion fault."""
    reference = now or utc_now()
    delta = (reference - moment).total_seconds()
    return max(0.0, delta)


def monotonic_ms() -> int:
    """Monotonic clock in milliseconds, for latency measurement (never for timestamps)."""
    return int(time.monotonic() * 1000)
