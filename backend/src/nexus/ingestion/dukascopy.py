"""Dukascopy public historical FX feed (Section 4.4; free, no key, no SLA).

This is the free route to deep FX tick history, which is what makes the EURUSD/GOLD legs of
the research plan possible at $0. It is a **bulk historical** source, not a real-time one.

⚠️ **Layout verification status: VERIFIED for EURUSD, 2026-11-26.** The bi5 binary layout below —
LZMA-compressed, 20 bytes per tick, big-endian — was implemented from documentation and stayed
UNVERIFIED through Phases 3 and 4 because this sandbox has no egress to ``datafeed.dukascopy.com``.
It has now been checked against a real download. :func:`verify_layout` passed on a genuine
bi5 hour in **eight consecutive CI runs on 2026-11-26**: four before the flip
(``45754638978``, ``45756716181``, ``45758610197``, ``45759709313``) and four after it
(``45782533635``, ``45782540670``, ``45784665370``, ``45784657260``), the last four being the
flag's falsifiability test — it stayed green with the flag on. All eight fetched the same hour,
``2026-11-24T12:00Z``, whose path is ``EURUSD/2026/10/24/12h_ticks.bi5`` — the ``10`` is November, because the
month segment is 0-indexed, exactly the trap documented below. All eight returned 25,761
compressed bytes, 101,480 decompressed = **5,074 ticks × 20 exactly**, no failed check, and
parsed prices of 1.09502–1.0964 inside EURUSD's real band — the assertion that exists to
catch a wrong point divisor, the silent 100x error warned about below. ``LAYOUT_VERIFIED`` is
therefore ``True`` and every record carries ``source="DUKASCOPY_BI5"``. Evidence: ``docs/14``
§1.4 F-1 and §2.1, and ``docs/00`` O-010.

What is still **NOT** verified, and must not be inferred from the above: only EURUSD has been
checked, so **12 of the 13 divisors** in ``POINT_DIVISORS`` have never met a real file. The feed
is also intermittent, and the eight runs above did not agree about why: the production
User-Agent worked outright in four; in the other four the single-attempt probes faulted while
the patient fetch inside the same run still succeeded, and the probes contradicted each other
(a browser User-Agent answered in three of them, a different hour in two). No single variable
explains it and no cause is established (``docs/14`` F-5), so a failed hour says nothing about
the layout. Layout verification is not price verification either: nothing here reconciles
Dukascopy against a second source (``docs/14`` F-8). FX tick history for any pair other than
EURUSD remains PROVISIONAL and must never be used to size a live position.

URL shape (note the **0-indexed month**, a classic off-by-one trap):
``/datafeed/{PAIR}/{YYYY}/{MM-1:02d}/{DD}/{HH}h_ticks.bi5`` — one file per instrument-hour holds
**both** sides. Defect 39 removed an invented ``{BID|ASK}`` segment from this path, which is why no FX
tick could be downloaded at all before Phase 4; ``side`` is a parse-time choice, never a URL dimension.

Point divisors: prices are stored as integer points. EURUSD uses 100000 (5-digit quoting),
JPY pairs use 1000 (3-digit). Getting this wrong scales prices by 100x, so the divisor is
explicit per pair and the parser refuses an unknown pair rather than guessing.
"""

from __future__ import annotations

import inspect
import lzma
import struct
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from nexus.core.ids import iso_utc
from nexus.ingestion.base import IngestFault, IngestReport, TickRecord, Transport

DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
VENUE = "DUKASCOPY"
SOURCE_UNVERIFIED = "DUKASCOPY_BI5_UNVERIFIED"
SOURCE_VERIFIED = "DUKASCOPY_BI5"

#: Set only after :func:`verify_layout` passes against a real download. It passed eight times in
#: a row on 2026-11-26 — ``45754638978``, ``45756716181``, ``45758610197``, ``45759709313``
#: before the flip, ``45782533635``, ``45782540670``, ``45784665370``, ``45784657260`` after it — against hour
#: ``2026-11-24T12:00Z`` (``EURUSD/2026/10/24/12h_ticks.bi5``): 25,761 bytes → 101,480 = 5,074 × 20 exactly,
#: no failed check, prices 1.09502–1.0964. Recorded in ``docs/14`` §1.4 F-1 and §2.1,
#: and ``docs/00`` O-010.
#: Flip this back to ``False`` if a real download ever fails the check again — the honest state is
#: worth more than the convenient one, and ``SOURCE_UNVERIFIED`` exists for exactly that.
LAYOUT_VERIFIED = True

#: Which pairs have had their **point divisor** confirmed against real prices. The record layout is
#: the same for every pair, so ``LAYOUT_VERIFIED`` legitimately generalises; the divisor is not — a
#: wrong one is a silent 100x error, and only EURUSD has met a real file (parsed prices
#: 1.09502–1.0964, inside the band the live module asserts). The other twelve pairs in
#: ``POINT_DIVISORS`` are transcribed from documentation and remain PROVISIONAL. Kept as data rather
#: than prose so a coverage summary can show it instead of implying every pair is verified.
LAYOUT_VERIFIED_PAIRS: tuple[str, ...] = ("EURUSD",)

#: Bytes per tick: uint32 offset-ms, uint32 ask points, uint32 bid points, float32 ask vol,
#: float32 bid vol.
TICK_STRUCT = struct.Struct(">IIIf f".replace(" ", ""))
TICK_SIZE = 20

#: Integer point divisors per pair. A pair absent from this table is refused, not guessed:
#: a 100x price error would be catastrophic and silent.
POINT_DIVISORS: dict[str, int] = {
    "EURUSD": 100_000,
    "GBPUSD": 100_000,
    "AUDUSD": 100_000,
    "NZDUSD": 100_000,
    "USDCAD": 100_000,
    "USDCHF": 100_000,
    "EURGBP": 100_000,
    "EURJPY": 1_000,
    "USDJPY": 1_000,
    "GBPJPY": 1_000,
    "AUDJPY": 1_000,
    "XAUUSD": 100,
    "XAGUSD": 1_000,
}

#: One bi5 file holds **both** sides: every 20-byte record carries ask points and bid points
#: (and a volume for each). There is no BID/ASK dimension in the URL — the path is
#: ``{PAIR}/{YYYY}/{MM-1:02d}/{DD}/{HH}h_ticks.bi5`` and nothing else. `side` selects which of the
#: two columns a caller treats as "the" price, at parse time only.
SIDES = ("BID", "ASK")


def point_divisor(pair: str) -> int:
    """Integer divisor for a pair's price points. Unknown pair → refuse."""
    key = pair.strip().upper()
    divisor = POINT_DIVISORS.get(key)
    if divisor is None:
        raise IngestFault(
            f"DUKASCOPY: no point divisor recorded for {key!r}; refusing to guess "
            f"(a wrong divisor scales prices by orders of magnitude)",
            retryable=False,
        )
    return divisor


def hour_url(pair: str, hour: datetime, *, base_url: str = DUKASCOPY_BASE) -> str:
    """Build the bi5 URL for one hour of ticks.

    The month segment is **0-indexed** (January = ``00``). This is intentional and is the
    single most common bug when integrating this feed.

    There is deliberately no `side` parameter. An earlier version put ``BID``/``ASK`` in the path,
    which 404s: the feed serves one file per instrument-hour containing both sides, so a side
    segment addresses nothing (defect 39, found by live verification). Which side a caller wants is
    a question for :func:`parse_bi5`, not for the URL.
    """
    if hour.tzinfo is None:
        raise IngestFault("DUKASCOPY: hour must be timezone-aware (feed times are UTC)", retryable=False)
    local = hour.astimezone(UTC)
    pair_key = pair.strip().upper()
    return (
        f"{base_url}/{pair_key}/{local.year}/{local.month - 1:02d}/{local.day:02d}/"
        f"{local.hour:02d}h_ticks.bi5"
    )


def source_label() -> str:
    """Honest provenance string, so downstream can see whether the layout has been verified."""
    return SOURCE_VERIFIED if LAYOUT_VERIFIED else SOURCE_UNVERIFIED


@dataclass(frozen=True, slots=True)
class DukascopyHour:
    """One parsed hour of ticks plus the parse diagnostics."""

    pair: str
    side: str
    hour_start: datetime
    ticks: tuple[TickRecord, ...]
    url: str
    raw_bytes: int
    decompressed_bytes: int
    layout_verified: bool
    empty: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "side": self.side,
            "hour_start": iso_utc(self.hour_start),
            "tick_count": len(self.ticks),
            "url": self.url,
            "raw_bytes": self.raw_bytes,
            "decompressed_bytes": self.decompressed_bytes,
            "layout_verified": self.layout_verified,
            "empty": self.empty,
        }


def parse_bi5(
    payload: bytes,
    *,
    pair: str,
    hour_start: datetime,
    side: str = "BID",
    venue_symbol: str | None = None,
) -> tuple[TickRecord, ...]:
    """Decompress and parse a bi5 hour file into canonical ticks.

    An empty body is a **closed market**, not an error — FX does not trade on weekends, and
    Dukascopy serves a zero-length file for those hours. Returning ``()`` with ``empty=True``
    at the caller keeps that distinction visible.
    """
    if hour_start.tzinfo is None:
        raise IngestFault("DUKASCOPY: hour_start must be timezone-aware", retryable=False)
    side_key = side.strip().upper()
    if side_key not in SIDES:
        # Refused rather than defaulted: the choice below is a two-way branch, so an unrecognised
        # side would silently be read as ASK and every price would come from the wrong column.
        raise IngestFault(f"DUKASCOPY: side must be one of {SIDES}, got {side!r}", retryable=False)
    base = hour_start.astimezone(UTC)
    if not payload:
        return ()

    try:
        raw = lzma.decompress(payload)
    except lzma.LZMAError as exc:
        raise IngestFault(f"DUKASCOPY: bi5 payload is not valid LZMA ({exc})", retryable=False) from exc

    if len(raw) % TICK_SIZE != 0:
        raise IngestFault(
            f"DUKASCOPY: decompressed size {len(raw)} is not a multiple of {TICK_SIZE} bytes; "
            f"the bi5 layout assumption is wrong — refusing to parse rather than emit garbage",
            retryable=False,
        )

    divisor = Decimal(point_divisor(pair))
    symbol = venue_symbol or pair.strip().upper()
    source = source_label()
    ticks: list[TickRecord] = []
    for offset in range(0, len(raw), TICK_SIZE):
        chunk = raw[offset : offset + TICK_SIZE]
        offset_ms, ask_points, bid_points, ask_volume, bid_volume = TICK_STRUCT.unpack(chunk)

        # A tick offset beyond the hour means the layout assumption is wrong. Refusing here
        # is the difference between a bad hour and a silently corrupted archive.
        if offset_ms >= 3_600_000:
            raise IngestFault(
                f"DUKASCOPY: tick offset {offset_ms}ms exceeds one hour; layout mismatch",
                retryable=False,
            )
        observed = base + timedelta(milliseconds=offset_ms)
        price_points = bid_points if side_key == "BID" else ask_points
        price = Decimal(int(price_points)) / divisor
        if price <= 0:
            continue  # Dukascopy pads with zero-price records; they carry no information
        volume = Decimal(str(ask_volume if side_key == "ASK" else bid_volume))
        ticks.append(
            TickRecord(
                instrument_id="",  # resolved by the caller through the registry
                venue=VENUE,
                venue_symbol=symbol,
                price=price,
                quantity=volume if volume > 0 else None,
                observed_at=observed,
                venue_timestamp=observed,
                side=None,  # a bid/ask print is not a buyer- or seller-initiated trade
                trade_id=None,
                source=source,
            ),
        )
    return tuple(ticks)


def verify_layout(payload: bytes) -> dict[str, Any]:
    """Structural checks to run against the FIRST real download.

    Passing these is the evidence required to flip ``LAYOUT_VERIFIED`` to ``True``. They are
    deliberately mechanical: size divisibility, offset monotonicity, sane price range.

    It passed on 2026-11-26, four runs in a row, which is what ``LAYOUT_VERIFIED = True`` cites. The
    function stays for two reasons: the weekly live run keeps calling it, so an upstream change to the
    bi5 record layout is caught by the next real download instead of being assumed away; and the flag
    is a claim about the world rather than about this file, so it must be falsifiable by re-running
    this. A failure here means the flag goes back to ``False``, not that the check gets relaxed.
    """
    result: dict[str, Any] = {"payload_bytes": len(payload), "passed": False, "reasons": []}
    reasons: list[str] = []
    if not payload:
        reasons.append("EMPTY_PAYLOAD:cannot verify a layout from zero bytes")
        result["reasons"] = reasons
        return result
    try:
        raw = lzma.decompress(payload)
    except lzma.LZMAError as exc:
        reasons.append(f"NOT_LZMA:{exc}")
        result["reasons"] = reasons
        return result
    result["decompressed_bytes"] = len(raw)
    if len(raw) == 0:
        reasons.append("DECOMPRESSED_EMPTY:valid LZMA but no ticks (possible closed hour)")
    elif len(raw) % TICK_SIZE != 0:
        reasons.append(f"SIZE_NOT_MULTIPLE_OF_{TICK_SIZE}:{len(raw)}")
    else:
        count = len(raw) // TICK_SIZE
        result["tick_count"] = count
        offsets = []
        for offset in range(0, len(raw), TICK_SIZE):
            offset_ms = TICK_STRUCT.unpack(raw[offset : offset + TICK_SIZE])[0]
            offsets.append(offset_ms)
        if any(o >= 3_600_000 for o in offsets):
            reasons.append("OFFSET_EXCEEDS_HOUR:layout assumption is wrong")
        if offsets != sorted(offsets):
            reasons.append("OFFSETS_NOT_MONOTONIC:unexpected ordering (not fatal, but note it)")
    result["reasons"] = reasons
    result["passed"] = not reasons
    return result


class DukascopyHistorical:
    """Bulk historical FX tick downloader over any injected :class:`Transport`."""

    name = "dukascopy-public"
    venue = VENUE
    requires_credentials = False

    def __init__(self, *, transport: Transport, base_url: str = DUKASCOPY_BASE) -> None:
        self._transport = transport
        self._base = base_url.rstrip("/")

    async def fetch_hour(
        self,
        pair: str,
        hour: datetime,
        *,
        side: str = "BID",
        report: IngestReport | None = None,
    ) -> DukascopyHour:
        """Download and parse one hour. A 404 is recorded as a gap, never as zero ticks."""
        url = hour_url(pair, hour, base_url=self._base)
        payload = await self._transport.get_bytes(url)
        try:
            ticks = parse_bi5(payload, pair=pair, hour_start=hour, side=side)
        except IngestFault as exc:
            if report is not None:
                report.reject(f"PARSE_FAULT:{exc.reason.value}")
                report.errors.append(str(exc.detail)[:200])
            raise
        if report is not None:
            report.fetched += 1
            report.accepted += len(ticks)
        decompressed = len(payload)
        try:
            decompressed = len(lzma.decompress(payload)) if payload else 0
        except lzma.LZMAError:
            decompressed = -1  # signals "could not decompress"; the parse above already raised
        return DukascopyHour(
            pair=pair.strip().upper(),
            side=side.strip().upper(),
            hour_start=hour.astimezone(UTC),
            ticks=ticks,
            url=url,
            raw_bytes=len(payload),
            decompressed_bytes=decompressed,
            layout_verified=LAYOUT_VERIFIED,
            empty=len(ticks) == 0,
        )

    async def fetch_range(
        self,
        pair: str,
        *,
        start: datetime,
        end: datetime,
        side: str = "BID",
        on_hour: Callable[[DukascopyHour], Any] | None = None,
        report: IngestReport | None = None,
        skip_closed: bool = True,
    ) -> tuple[DukascopyHour, ...]:
        """Walk an hour range. Bounded by the range itself and a hard hour cap.

        ``skip_closed`` avoids downloading weekend hours at all: FX is closed, the file is
        empty, and fetching it wastes free-tier bandwidth for zero information.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise IngestFault("DUKASCOPY: start/end must be timezone-aware", retryable=False)
        if end < start:
            raise IngestFault("DUKASCOPY: end is before start", retryable=False)

        cursor = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        last = end.astimezone(UTC)
        max_hours = 24 * 400  # bounded: ~16 days per call; larger backfills paginate
        hours: list[DukascopyHour] = []
        for _ in range(max_hours):
            if cursor > last:
                break
            if skip_closed and _fx_closed(cursor):
                cursor += timedelta(hours=1)
                continue
            hour = await self.fetch_hour(pair, cursor, side=side, report=report)
            hours.append(hour)
            if on_hour is not None:
                result = on_hour(hour)
                if inspect.isawaitable(result):
                    await result
            cursor += timedelta(hours=1)
        return tuple(hours)


def _fx_closed(moment: datetime) -> bool:
    """True when FX is certainly closed: Saturday, or Sunday before 22:00 UTC.

    Conservative on purpose — Friday after 21:00 UTC and Sunday after 22:00 UTC are
    *fetched*, because the exact close depends on the season. Missing an hour of data is a
    worse error than downloading one empty file.
    """
    local = moment.astimezone(UTC)
    weekday = local.weekday()  # Mon=0 .. Sun=6
    # Saturday is always closed; Sunday is closed until 22:00 UTC (the Sydney open).
    return weekday == 5 or (weekday == 6 and local.hour < 22)


def pair_supported(pair: str) -> bool:
    """Whether a point divisor is known for this pair."""
    return pair.strip().upper() in POINT_DIVISORS


def supported_pairs() -> tuple[str, ...]:
    return tuple(sorted(POINT_DIVISORS))


def iter_hours(start: datetime, end: datetime) -> Iterable[datetime]:
    """Hour boundaries between ``start`` and ``end`` inclusive."""
    cursor = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    last = end.astimezone(UTC)
    while cursor <= last:
        yield cursor
        cursor += timedelta(hours=1)


def summarise(hours: Sequence[DukascopyHour]) -> dict[str, Any]:
    """Coverage summary — what the UI shows instead of implying completeness."""
    total_ticks = sum(len(h.ticks) for h in hours)
    empty = [h for h in hours if h.empty]
    return {
        "hours_requested": len(hours),
        "hours_with_data": len(hours) - len(empty),
        "hours_empty": len(empty),
        "total_ticks": total_ticks,
        "layout_verified": LAYOUT_VERIFIED,
        "layout_verified_pairs": list(LAYOUT_VERIFIED_PAIRS),
        "divisor_unverified_pairs": [p for p in POINT_DIVISORS if p not in LAYOUT_VERIFIED_PAIRS],
        "source": source_label(),
        "first": iso_utc(hours[0].hour_start) if hours else None,
        "last": iso_utc(hours[-1].hour_start) if hours else None,
        "coverage_note": (
            "Empty hours are expected on weekends and bank holidays; they are not missing data."
            if empty
            else "No empty hours in this range."
        ),
    }


__all__ = [
    "DUKASCOPY_BASE",
    "LAYOUT_VERIFIED",
    "LAYOUT_VERIFIED_PAIRS",
    "POINT_DIVISORS",
    "SIDES",
    "SOURCE_UNVERIFIED",
    "SOURCE_VERIFIED",
    "TICK_SIZE",
    "VENUE",
    "DukascopyHistorical",
    "DukascopyHour",
    "hour_url",
    "iter_hours",
    "pair_supported",
    "parse_bi5",
    "point_divisor",
    "source_label",
    "summarise",
    "supported_pairs",
    "verify_layout",
]
