"""Tiered retention policy (D-024) with a disk-watermark fail-safe.

The owner decision: **full ticks 30 days → 1-minute bars 12 months → 5-minute/daily bars
indefinitely**, on a 200 GB free-tier volume.

Two failure modes this module exists to prevent:

1. **Filling the disk.** On a single free VM the disk is also where PostgreSQL, the audit
   chain and the logs live. A full disk corrupts the audit trail — the worst possible
   failure for a system whose whole claim to trust is its evidence. So retention is not just
   a scheduled tidy-up: the watermark check runs *before* a write, and it rolls up early
   rather than letting the volume fill.
2. **Silently deleting evidence.** Nothing here deletes without first confirming the coarser
   tier exists and covers the same range. Deleting ticks whose 1-minute bars were never
   written is data loss dressed as housekeeping, so the policy refuses and reports.

Coverage is always reported honestly. After a rollup, an instrument has *bars* for a period,
not ticks — and the UI must say so rather than implying full-resolution history.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nexus.archive.bars import ROLLUP_CHAIN, interval_duration, is_rollup_of, rollup_bars
from nexus.core.ids import iso_utc
from nexus.data.records import BarRecord

#: Default tiers, per D-024. Days of age at which each resolution stops being kept.
DEFAULT_TICK_RETENTION_DAYS = 30
DEFAULT_1M_RETENTION_DAYS = 365
DEFAULT_5M_RETENTION_DAYS = None  # None = keep indefinitely
DEFAULT_1D_RETENTION_DAYS = None

#: Disk watermark. Below `warn_pct` nothing happens; above it, rollup is forced early.
DEFAULT_DISK_WARN_PCT = 70.0
DEFAULT_DISK_FORCE_PCT = 85.0


@dataclass(frozen=True, slots=True)
class RetentionTier:
    """One resolution and how long it survives."""

    interval: str
    max_age_days: int | None  # None = indefinite
    rollup_to: str | None  # what replaces it once it expires
    label: str = ""

    @property
    def keeps_forever(self) -> bool:
        return self.max_age_days is None

    def expires_at(self, now: datetime) -> datetime | None:
        if self.max_age_days is None:
            return None
        return now - timedelta(days=self.max_age_days)


def default_tiers() -> tuple[RetentionTier, ...]:
    """The D-024 ladder, as data."""
    return (
        RetentionTier("tick", DEFAULT_TICK_RETENTION_DAYS, "1m", "full-resolution ticks"),
        RetentionTier("1m", DEFAULT_1M_RETENTION_DAYS, "5m", "one-minute bars"),
        RetentionTier("5m", DEFAULT_5M_RETENTION_DAYS, "1d", "five-minute bars"),
        RetentionTier("1d", DEFAULT_1D_RETENTION_DAYS, None, "daily bars"),
    )


@dataclass(frozen=True, slots=True)
class DiskPressure:
    """Where the volume stands right now."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_pct: float
    level: str  # OK | WARN | FORCE
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "total_gb": round(self.total_bytes / 1e9, 2),
            "used_gb": round(self.used_bytes / 1e9, 2),
            "free_gb": round(self.free_bytes / 1e9, 2),
            "used_pct": round(self.used_pct, 2),
            "level": self.level,
        }


def disk_pressure(
    path: Path | str,
    *,
    warn_pct: float = DEFAULT_DISK_WARN_PCT,
    force_pct: float = DEFAULT_DISK_FORCE_PCT,
) -> DiskPressure:
    """Read real filesystem usage. Never a guess, never a hard-coded 200 GB."""
    target = Path(path)
    probe = target if target.exists() else Path.cwd()
    usage = shutil.disk_usage(probe)
    used_pct = (usage.used / usage.total * 100.0) if usage.total else 100.0
    if used_pct >= force_pct:
        level = "FORCE"
    elif used_pct >= warn_pct:
        level = "WARN"
    else:
        level = "OK"
    return DiskPressure(
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        used_pct=used_pct,
        level=level,
        path=str(target),
    )


@dataclass(slots=True)
class RetentionAction:
    """One planned or executed retention step. Audit-safe."""

    action: str  # ROLLUP | DELETE | REFUSE
    interval: str
    rollup_to: str | None
    records_affected: int
    records_produced: int
    bytes_freed_estimate: int
    reason: str
    executed: bool = False
    at: datetime | None = None

    def to_audit_payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "interval": self.interval,
            "rollup_to": self.rollup_to,
            "records_affected": self.records_affected,
            "records_produced": self.records_produced,
            "bytes_freed_estimate": self.bytes_freed_estimate,
            "reason": self.reason,
            "executed": self.executed,
            "at": iso_utc(self.at) if self.at else None,
        }


@dataclass(slots=True)
class RetentionPlan:
    """What retention *would* do, computed without touching anything.

    Planning separately from executing is deliberate: the owner can see the consequences
    before any evidence is removed, which is what "no silent destruction" means in practice.
    """

    generated_at: datetime
    disk: DiskPressure | None
    tiers: tuple[RetentionTier, ...]
    actions: tuple[RetentionAction, ...]
    coverage_after: dict[str, str] = field(default_factory=dict)

    @property
    def deletes(self) -> tuple[RetentionAction, ...]:
        return tuple(a for a in self.actions if a.action == "DELETE")

    @property
    def refusals(self) -> tuple[RetentionAction, ...]:
        return tuple(a for a in self.actions if a.action == "REFUSE")

    @property
    def is_safe(self) -> bool:
        """True when nothing is refused — i.e. no delete lacks its replacement tier."""
        return not self.refusals

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": iso_utc(self.generated_at),
            "disk": self.disk.to_dict() if self.disk else None,
            "tiers": [
                {
                    "interval": t.interval,
                    "max_age_days": t.max_age_days,
                    "rollup_to": t.rollup_to,
                    "label": t.label,
                }
                for t in self.tiers
            ],
            "actions": [a.to_audit_payload() for a in self.actions],
            "coverage_after": dict(self.coverage_after),
            "is_safe": self.is_safe,
        }


@dataclass(frozen=True, slots=True)
class CoverageWindow:
    """Honest description of what resolution exists for which period."""

    instrument_id: str
    interval: str
    earliest: datetime | None
    latest: datetime | None
    record_count: int
    resolution_note: str

    @property
    def span_days(self) -> float | None:
        if self.earliest is None or self.latest is None:
            return None
        return (self.latest - self.earliest).total_seconds() / 86400.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "interval": self.interval,
            "earliest": iso_utc(self.earliest) if self.earliest else None,
            "latest": iso_utc(self.latest) if self.latest else None,
            "record_count": self.record_count,
            "span_days": round(self.span_days, 2) if self.span_days is not None else None,
            "resolution_note": self.resolution_note,
        }


class RetentionPolicy:
    """Computes and (optionally) applies the D-024 ladder."""

    def __init__(
        self,
        *,
        tiers: Sequence[RetentionTier] | None = None,
        warn_pct: float = DEFAULT_DISK_WARN_PCT,
        force_pct: float = DEFAULT_DISK_FORCE_PCT,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._tiers: tuple[RetentionTier, ...] = tuple(tiers) if tiers is not None else default_tiers()
        self._warn_pct = warn_pct
        self._force_pct = force_pct
        self._now_fn = now_fn or (lambda: datetime.now(tz=UTC))
        self._validate()

    def _validate(self) -> None:
        """A tier ladder that cannot roll up is a data-loss machine. Refuse to build it."""
        for tier in self._tiers:
            if tier.rollup_to is None:
                continue
            if not any(t.interval == tier.rollup_to for t in self._tiers):
                raise ValueError(
                    f"tier {tier.interval!r} rolls up to {tier.rollup_to!r}, which is not itself a tier",
                )

    @property
    def tiers(self) -> tuple[RetentionTier, ...]:
        return self._tiers

    def tier_for(self, interval: str) -> RetentionTier | None:
        for tier in self._tiers:
            if tier.interval == interval:
                return tier
        return None

    def effective_cutoff(self, interval: str, *, now: datetime | None = None) -> datetime | None:
        """The oldest timestamp that may still be kept at this resolution.

        Under FORCE disk pressure the cutoff moves *forward* (data expires sooner) so the
        volume cannot fill. Under WARN it moves forward by a quarter of the tier's age.
        """
        reference = (now or self._now_fn()).astimezone(UTC)
        tier = self.tier_for(interval)
        if tier is None or tier.max_age_days is None:
            return None
        age = timedelta(days=tier.max_age_days)
        pressure = disk_pressure(Path.cwd(), warn_pct=self._warn_pct, force_pct=self._force_pct)
        if pressure.level == "FORCE":
            age = age / 2
        elif pressure.level == "WARN":
            age = age * 3 / 4
        return reference - age

    def plan(
        self,
        *,
        inventory: Iterable[CoverageWindow],
        disk_path: Path | str | None = None,
        now: datetime | None = None,
    ) -> RetentionPlan:
        """Work out what to roll up and what to delete, without doing either.

        The safety rule: a DELETE is only planned when the coarser tier demonstrably covers
        the same period. Otherwise the action is a REFUSE with a reason, and the plan reports
        ``is_safe=False``.
        """
        reference = (now or self._now_fn()).astimezone(UTC)
        pressure = (
            disk_pressure(disk_path, warn_pct=self._warn_pct, force_pct=self._force_pct)
            if disk_path
            else None
        )
        windows = list(inventory)
        by_key: dict[tuple[str, str], CoverageWindow] = {(w.instrument_id, w.interval): w for w in windows}
        actions: list[RetentionAction] = []
        coverage_after: dict[str, str] = {}

        for tier in self._tiers:
            if tier.max_age_days is None:
                continue
            cutoff = self.effective_cutoff(tier.interval, now=reference)
            if cutoff is None:
                continue
            affected = [
                w
                for w in windows
                if w.interval == tier.interval and w.earliest is not None and w.earliest < cutoff
            ]
            if not affected:
                continue

            if tier.rollup_to is None:
                for window in affected:
                    actions.append(
                        RetentionAction(
                            action="REFUSE",
                            interval=tier.interval,
                            rollup_to=None,
                            records_affected=window.record_count,
                            records_produced=0,
                            bytes_freed_estimate=0,
                            reason=(
                                f"{tier.interval} data older than {iso_utc(cutoff)} has no coarser tier to "
                                f"roll into; deletion would be permanent evidence loss"
                            ),
                            at=reference,
                        ),
                    )
                continue

            for window in affected:
                window_earliest = window.earliest
                if window_earliest is None:
                    continue  # unreachable given the filter above, but mypy narrows only here
                replacement = by_key.get((window.instrument_id, tier.rollup_to))
                replacement_earliest = replacement.earliest if replacement is not None else None
                # A delete is only safe when the coarser tier demonstrably reaches back at
                # least as far as the data being removed.
                covered = replacement_earliest is not None and replacement_earliest <= window_earliest
                if covered:
                    actions.append(
                        RetentionAction(
                            action="DELETE",
                            interval=tier.interval,
                            rollup_to=tier.rollup_to,
                            records_affected=window.record_count,
                            records_produced=0,
                            bytes_freed_estimate=0,
                            reason=(
                                f"{tier.interval} data older than {iso_utc(cutoff)} is superseded by "
                                f"{tier.rollup_to} coverage from {iso_utc(replacement_earliest)}"
                            ),
                            at=reference,
                        ),
                    )
                else:
                    actions.append(
                        RetentionAction(
                            action="REFUSE",
                            interval=tier.interval,
                            rollup_to=tier.rollup_to,
                            records_affected=window.record_count,
                            records_produced=0,
                            bytes_freed_estimate=0,
                            reason=(
                                f"{tier.rollup_to} coverage for {window.instrument_id} does not "
                                f"reach back to {iso_utc(window.earliest)}; refusing to delete "
                                f"{tier.interval} records that have no replacement (roll up first)"
                            ),
                            at=reference,
                        ),
                    )

        for window in windows:
            coverage_after[window.instrument_id] = _describe_coverage(
                [w for w in windows if w.instrument_id == window.instrument_id],
            )

        return RetentionPlan(
            generated_at=reference,
            disk=pressure,
            tiers=self._tiers,
            actions=tuple(actions),
            coverage_after=coverage_after,
        )

    def rollup(
        self,
        bars: Iterable[BarRecord],
        *,
        target_interval: str,
        instrument_id: str,
        venue: str,
        venue_symbol: str,
        now: datetime | None = None,
    ) -> tuple[tuple[BarRecord, ...], RetentionAction]:
        """Produce the coarser tier from the finer one.

        This is the step that must succeed *before* any delete is allowed to run. Refusing an
        illegal rollup is better than writing a wrong bar.
        """
        source = list(bars)
        if not source:
            action = RetentionAction(
                action="REFUSE",
                interval=target_interval,
                rollup_to=None,
                records_affected=0,
                records_produced=0,
                bytes_freed_estimate=0,
                reason="no source bars to roll up",
                at=now or self._now_fn(),
            )
            return (), action

        source_interval = source[0].interval
        if not is_rollup_of(source_interval, target_interval):
            action = RetentionAction(
                action="REFUSE",
                interval=source_interval,
                rollup_to=target_interval,
                records_affected=len(source),
                records_produced=0,
                bytes_freed_estimate=0,
                reason=f"{source_interval} cannot be rolled up to {target_interval} (not an even multiple)",
                at=now or self._now_fn(),
            )
            return (), action

        rolled, report = rollup_bars(
            source,
            target_interval=target_interval,
            instrument_id=instrument_id,
            venue=venue,
            venue_symbol=venue_symbol,
            source=f"ROLLUP_FROM_{source_interval}",
            now=now,
        )
        action = RetentionAction(
            action="ROLLUP",
            interval=source_interval,
            rollup_to=target_interval,
            records_affected=len(source),
            records_produced=len(rolled),
            bytes_freed_estimate=0,
            reason=(
                f"rolled {len(source)} {source_interval} bars into {len(rolled)} {target_interval} bars "
                f"({report.bars_unconfirmed} unconfirmed, {report.records_rejected} rejected)"
            ),
            executed=True,
            at=now or self._now_fn(),
        )
        return rolled, action


def _describe_coverage(windows: Sequence[CoverageWindow]) -> str:
    """One honest sentence about what resolution exists for an instrument."""
    if not windows:
        return "no archived data"
    ordered = sorted(
        windows,
        key=lambda w: (
            interval_duration(w.interval)
            if w.interval in ROLLUP_CHAIN or w.interval != "tick"
            else timedelta(microseconds=1)
        ),
    )
    finest = ordered[0]
    parts = [f"{w.interval}×{w.record_count}" for w in ordered if w.record_count]
    span = finest.span_days
    span_text = f"{span:.0f}d" if span is not None else "unknown span"
    return f"{', '.join(parts)} over {span_text}; finest resolution {finest.interval}"


def build_inventory(
    rows: Iterable[dict[str, Any]],
) -> tuple[CoverageWindow, ...]:
    """Turn archive query rows into coverage windows.

    Expected row keys: ``instrument_id``, ``interval``, ``earliest``, ``latest``, ``count``.
    Anything missing yields an empty window rather than a fabricated one.
    """
    out: list[CoverageWindow] = []
    for row in rows:
        earliest = row.get("earliest")
        latest = row.get("latest")
        interval_name = str(row.get("interval") or "unknown")
        if interval_name == "tick":
            note = "full-resolution ticks"
        elif interval_name in ROLLUP_CHAIN:
            note = f"{interval_name} bars ({interval_duration(interval_name)})"
        else:
            note = f"{interval_name} bars (non-standard interval)"
        out.append(
            CoverageWindow(
                instrument_id=str(row.get("instrument_id") or "UNKNOWN"),
                interval=interval_name,
                earliest=earliest,
                latest=latest,
                record_count=int(row.get("count") or 0),
                resolution_note=note,
            ),
        )
    return tuple(out)


def estimate_bytes_per_day(records_per_day: int, *, bytes_per_record: float = 24.0) -> float:
    """Rough sizing helper for the storage-cap conversation (O-008/Q-08).

    Deliberately conservative and clearly labelled an estimate: it is used to decide whether
    the instrument universe fits, never to claim a measured figure.
    """
    return records_per_day * bytes_per_record


__all__ = [
    "DEFAULT_1D_RETENTION_DAYS",
    "DEFAULT_1M_RETENTION_DAYS",
    "DEFAULT_5M_RETENTION_DAYS",
    "DEFAULT_DISK_FORCE_PCT",
    "DEFAULT_DISK_WARN_PCT",
    "DEFAULT_TICK_RETENTION_DAYS",
    "CoverageWindow",
    "DiskPressure",
    "RetentionAction",
    "RetentionPlan",
    "RetentionPolicy",
    "RetentionTier",
    "build_inventory",
    "default_tiers",
    "disk_pressure",
    "estimate_bytes_per_day",
]
