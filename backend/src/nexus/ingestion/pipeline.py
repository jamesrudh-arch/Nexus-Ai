"""Ingestion pipeline: adapter → registry → validation → archive → event bus (Section 4).

This is the only place raw venue payloads become NEXUS data, so every guarantee about the
archive is enforced here rather than trusted to the caller.

Order of operations, and why it is this order:

1. **Resolve the symbol through the instrument registry first.** An unrecognised venue symbol
   is refused, never guessed and never archived under a made-up id. A wrong instrument id
   propagates into research, into sizing and eventually into an order — the most expensive
   bug in the system, and the cheapest to prevent.
2. **Validate.** Non-positive prices, naive timestamps, inconsistent OHLC, crossed books.
   Rejected records are *counted with reasons*, not dropped quietly: a feed that degrades
   from 0% to 40% rejections is an incident, and it must be visible.
3. **Attach provenance.** Every archived row keeps the venue symbol, the source label and the
   ingestion time, so any number can be traced back to the feed that produced it.
4. **Archive, then publish.** Writing before publishing means a consumer can never see a
   record the archive does not have. The reverse order would allow research to read data that
   vanishes on restart.

The pipeline never places an order, never touches credentials, and never enables an
instrument. It has no authority to do any of those things.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from nexus.archive.bars import bars_from_ticks, merge_bars
from nexus.archive.parquet_store import ParquetArchive, WriteResult
from nexus.core.errors import RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.domain.instrument import Venue, VenueStatus
from nexus.ingestion.base import (
    BarRecord,
    QuoteRecord,
    TickRecord,
    validate_bar,
    validate_quote,
    validate_tick,
)
from nexus.instruments.registry import InstrumentRegistry, certification_rank

#: Minimum venue status required before that venue's data is archived. ``DATA_AVAILABLE``
#: means the feed was actually observed working — accepting ``UNKNOWN`` would archive data
#: from a mapping nobody has verified.
MINIMUM_STATUS_FOR_ARCHIVE = VenueStatus.DATA_AVAILABLE


@dataclass(slots=True)
class PipelineReport:
    """One pass through the pipeline, with every refusal accounted for."""

    started_at: datetime
    finished_at: datetime | None = None
    symbols_requested: int = 0
    #: Distinct ``venue:symbol`` keys successfully mapped this pass. A *set*, not a counter:
    #: counting records made ``resolution_rate`` a ratio of records to symbols (620 records
    #: for one symbol reported 62,000%). Both sides of a rate must be the same unit.
    resolved_keys: set[str] = field(default_factory=set)
    unresolved_symbols: list[str] = field(default_factory=list)
    status_refusals: dict[str, int] = field(default_factory=dict)
    bars_fetched: int = 0
    bars_accepted: int = 0
    bars_rejected: int = 0
    ticks_fetched: int = 0
    ticks_accepted: int = 0
    ticks_rejected: int = 0
    quotes_fetched: int = 0
    quotes_accepted: int = 0
    quotes_rejected: int = 0
    bars_from_ticks_produced: int = 0
    #: Records that were structurally valid and archived, but excluded while building bars.
    #: Kept separate from ``total_rejected`` because these were *not* refused at the gate —
    #: they are a distinct fault, and hiding them inside either counter would make the
    #: accepted+rejected identity lie. They still count toward degradation.
    aggregation_rejected: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    archive_writes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1

    def finish(self, at: datetime | None = None) -> None:
        self.finished_at = at or utc_now()

    @property
    def resolved(self) -> int:
        """How many *distinct symbols* were mapped — the same unit as ``symbols_requested``."""
        return len(self.resolved_keys)

    @property
    def resolution_rate(self) -> float:
        """Distinct symbols mapped ÷ distinct symbols requested. Always in [0, 1].

        Deliberately *not* clamped: if a caller passes a ``symbols_requested`` smaller than
        the symbols actually seen, a rate above 1.0 is the honest signal that the two sides
        disagree, and clamping would hide it.
        """
        return (self.resolved / self.symbols_requested) if self.symbols_requested else 0.0

    @property
    def total_rejected(self) -> int:
        return self.bars_rejected + self.ticks_rejected + self.quotes_rejected

    @property
    def total_faults(self) -> int:
        """Everything that went wrong: refused at the gate, plus excluded during aggregation."""
        return self.total_rejected + self.aggregation_rejected

    @property
    def total_accepted(self) -> int:
        return self.bars_accepted + self.ticks_accepted + self.quotes_accepted

    @property
    def rejection_rate(self) -> float:
        """Share of records that did not make it into the bars, from any cause.

        Includes aggregation exclusions. A feed whose ticks are structurally fine but whose
        timestamps are all in the future would otherwise report a 0% rejection rate while
        producing almost no bars — degradation that looks like success.
        """
        total = self.total_accepted + self.total_faults
        return (self.total_faults / total) if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": iso_utc(self.started_at),
            "finished_at": iso_utc(self.finished_at) if self.finished_at else None,
            "symbols_requested": self.symbols_requested,
            "resolved": self.resolved,
            "resolution_rate": round(self.resolution_rate, 4),
            "unresolved_symbols": list(self.unresolved_symbols)[:50],
            "status_refusals": dict(self.status_refusals),
            "bars": {
                "fetched": self.bars_fetched,
                "accepted": self.bars_accepted,
                "rejected": self.bars_rejected,
            },
            "ticks": {
                "fetched": self.ticks_fetched,
                "accepted": self.ticks_accepted,
                "rejected": self.ticks_rejected,
            },
            "quotes": {
                "fetched": self.quotes_fetched,
                "accepted": self.quotes_accepted,
                "rejected": self.quotes_rejected,
            },
            "bars_from_ticks_produced": self.bars_from_ticks_produced,
            "aggregation_rejected": self.aggregation_rejected,
            "total_accepted": self.total_accepted,
            "total_rejected": self.total_rejected,
            "total_faults": self.total_faults,
            "rejection_rate": round(self.rejection_rate, 4),
            "rejection_reasons": dict(self.rejection_reasons),
            "archive_writes": list(self.archive_writes),
            "errors": list(self.errors)[:20],
        }

    def to_audit_payload(self) -> dict[str, Any]:
        """Bounded, secret-free form suitable for the audit chain."""
        payload = self.to_dict()
        payload.pop("errors", None)  # free text from a venue; kept in logs, not in audit
        return payload


PublishFn = Callable[[str, dict[str, Any]], Awaitable[None] | None]


class IngestionPipeline:
    """Binds a registry, an archive and (optionally) an event bus into one ingest path."""

    def __init__(
        self,
        *,
        registry: InstrumentRegistry,
        archive: ParquetArchive | None = None,
        publish: PublishFn | None = None,
        minimum_status: VenueStatus = MINIMUM_STATUS_FOR_ARCHIVE,
        now_fn: Callable[[], datetime] = utc_now,
        max_rejection_rate: float = 0.25,
    ) -> None:
        self._registry = registry
        self._archive = archive
        self._publish = publish
        self._minimum_status = minimum_status
        self._now_fn = now_fn
        # Above this rejection rate the pass is flagged DEGRADED rather than reported as a
        # clean ingest. A feed that is 40% garbage is an outage, not a normal day.
        self._max_rejection_rate = max_rejection_rate
        self._reports: list[PipelineReport] = []

    @property
    def reports(self) -> tuple[PipelineReport, ...]:
        return tuple(self._reports)

    @property
    def last_report(self) -> PipelineReport | None:
        return self._reports[-1] if self._reports else None

    # ------------------------------------------------------------------ resolution

    def resolve(
        self, venue: Venue | str, venue_symbol: str, *, report: PipelineReport
    ) -> tuple[str, VenueStatus] | None:
        """Map a venue symbol to a canonical instrument id, or explain why not.

        Returns ``None`` when the symbol is unknown or the mapping is not yet certified for
        data. Both cases are recorded on the report so the reason is never lost.
        """
        resolved = self._registry.resolve(venue, venue_symbol)
        if resolved is None:
            report.unresolved_symbols.append(f"{venue}:{venue_symbol}")
            report.reject(f"{RejectReason.INSTRUMENT_UNKNOWN.value}:{venue}:{venue_symbol}")
            return None
        instrument, mapping = resolved
        if certification_rank(mapping.status) < certification_rank(self._minimum_status):
            key = f"{mapping.venue.value}:{mapping.status.value}"
            report.status_refusals[key] = report.status_refusals.get(key, 0) + 1
            report.reject(
                f"{RejectReason.INSTRUMENT_NOT_CERTIFIED.value}:{key} below {self._minimum_status.value}",
            )
            return None
        # Keyed on the venue + symbol actually requested, so the same canonical instrument
        # reached through two venues counts twice (both mappings were proven this pass) and
        # one venue symbol seen in 600 records counts once.
        report.resolved_keys.add(f"{venue}:{venue_symbol}")
        return instrument.instrument_id, mapping.status

    # ------------------------------------------------------------------ ingest

    def ingest_bars(
        self,
        bars: Iterable[BarRecord],
        *,
        venue: Venue | str,
        report: PipelineReport,
    ) -> list[BarRecord]:
        """Validate, resolve and archive bars. Returns the rows actually accepted."""
        accepted: list[BarRecord] = []
        for raw in bars:
            report.bars_fetched += 1
            reason = validate_bar(raw)
            if reason is not None:
                report.bars_rejected += 1
                report.reject(reason)
                continue
            resolved = self.resolve(venue, raw.venue_symbol, report=report)
            if resolved is None:
                report.bars_rejected += 1
                continue
            instrument_id, _status = resolved
            accepted.append(
                BarRecord(
                    instrument_id=instrument_id,
                    venue=raw.venue,
                    venue_symbol=raw.venue_symbol,
                    interval=raw.interval,
                    open_time=raw.open_time,
                    close_time=raw.close_time,
                    open=raw.open,
                    high=raw.high,
                    low=raw.low,
                    close=raw.close,
                    volume=raw.volume,
                    quote_volume=raw.quote_volume,
                    trades=raw.trades,
                    confirmed=raw.confirmed,
                    source=raw.source,
                ),
            )
        report.bars_accepted += len(accepted)
        return accepted

    def ingest_ticks(
        self,
        ticks: Iterable[TickRecord],
        *,
        venue: Venue | str,
        report: PipelineReport,
        aggregate_to: str | None = "1m",
    ) -> tuple[list[TickRecord], list[BarRecord]]:
        """Validate and resolve ticks, optionally aggregating them into bars.

        Aggregation runs on *resolved* ticks only, and only the resolved instrument's own
        ticks are aggregated together — mixing venues into one bar would create a price
        series that never existed.
        """
        accepted: list[TickRecord] = []
        by_instrument: dict[str, list[TickRecord]] = {}
        for raw in ticks:
            report.ticks_fetched += 1
            reason = validate_tick(raw)
            if reason is not None:
                report.ticks_rejected += 1
                report.reject(reason)
                continue
            resolved = self.resolve(venue, raw.venue_symbol, report=report)
            if resolved is None:
                report.ticks_rejected += 1
                continue
            instrument_id, _status = resolved
            tick = TickRecord(
                instrument_id=instrument_id,
                venue=raw.venue,
                venue_symbol=raw.venue_symbol,
                price=raw.price,
                quantity=raw.quantity,
                observed_at=raw.observed_at,
                venue_timestamp=raw.venue_timestamp,
                side=raw.side,
                trade_id=raw.trade_id,
                source=raw.source,
            )
            accepted.append(tick)
            by_instrument.setdefault(instrument_id, []).append(tick)
        report.ticks_accepted += len(accepted)

        produced: list[BarRecord] = []
        if aggregate_to and by_instrument:
            for instrument_id, group in by_instrument.items():
                sample = group[0]
                built, agg_report = bars_from_ticks(
                    group,
                    interval=aggregate_to,
                    instrument_id=instrument_id,
                    venue=sample.venue,
                    venue_symbol=sample.venue_symbol,
                    source=f"AGGREGATED_FROM_TICKS_{aggregate_to}",
                    now=self._now_fn(),
                )
                produced.extend(built)
                # An aggregation exclusion is a real fault, not a footnote: these ticks passed
                # the gate and were archived, yet could not be turned into bars. Counting them
                # only in `rejection_reasons` left `rejection_rate` at 0% while the pass
                # silently produced almost nothing.
                report.aggregation_rejected += agg_report.records_rejected
                for reason_name, count in agg_report.rejection_reasons.items():
                    report.reject(f"AGGREGATION:{reason_name}×{count}")
            report.bars_from_ticks_produced += len(produced)
        return accepted, produced

    def ingest_quotes(
        self,
        quotes: Iterable[QuoteRecord],
        *,
        venue: Venue | str,
        report: PipelineReport,
    ) -> list[QuoteRecord]:
        accepted: list[QuoteRecord] = []
        for raw in quotes:
            report.quotes_fetched += 1
            reason = validate_quote(raw)
            if reason is not None:
                report.quotes_rejected += 1
                report.reject(reason)
                continue
            resolved = self.resolve(venue, raw.venue_symbol, report=report)
            if resolved is None:
                report.quotes_rejected += 1
                continue
            instrument_id, _status = resolved
            accepted.append(
                QuoteRecord(
                    instrument_id=instrument_id,
                    venue=raw.venue,
                    venue_symbol=raw.venue_symbol,
                    bid=raw.bid,
                    ask=raw.ask,
                    bid_size=raw.bid_size,
                    ask_size=raw.ask_size,
                    last=raw.last,
                    observed_at=raw.observed_at,
                    venue_timestamp=raw.venue_timestamp,
                    delayed=raw.delayed,
                    source=raw.source,
                ),
            )
        report.quotes_accepted += len(accepted)
        return accepted

    # ------------------------------------------------------------------ persistence

    async def persist(
        self,
        *,
        bars: Sequence[BarRecord] = (),
        ticks: Sequence[TickRecord] = (),
        quotes: Sequence[QuoteRecord] = (),
        report: PipelineReport,
        emit_events: bool = True,
    ) -> dict[str, WriteResult]:
        """Archive accepted records, then publish. Archive-first is deliberate."""
        results: dict[str, WriteResult] = {}
        if self._archive is None:
            if bars or ticks or quotes:
                report.errors.append("no archive configured; accepted records were not persisted")
            return results

        if bars:
            results["bars"] = self._archive.write_bars(list(bars))
        if ticks:
            results["ticks"] = self._archive.write_ticks(list(ticks))
        if quotes:
            results["quotes"] = self._archive.write_quotes(list(quotes))
        report.archive_writes = [r.to_dict() for r in results.values()]

        if emit_events and self._publish is not None:
            if bars:
                await _maybe_await(
                    self._publish(
                        "market.bars.archived",
                        {
                            "count": len(bars),
                            "intervals": sorted({b.interval for b in bars}),
                            "venues": sorted({b.venue for b in bars}),
                            "first": iso_utc(min(b.open_time for b in bars)),
                            "last": iso_utc(max(b.open_time for b in bars)),
                        },
                    ),
                )
            if ticks:
                await _maybe_await(
                    self._publish(
                        "market.ticks.archived",
                        {
                            "count": len(ticks),
                            "venues": sorted({t.venue for t in ticks}),
                            "first": iso_utc(min(t.observed_at for t in ticks)),
                            "last": iso_utc(max(t.observed_at for t in ticks)),
                        },
                    ),
                )
            if quotes:
                await _maybe_await(
                    self._publish(
                        "market.quotes.archived",
                        {"count": len(quotes), "venues": sorted({q.venue for q in quotes})},
                    ),
                )
        return results

    async def run(
        self,
        *,
        venue: Venue | str,
        bars: Iterable[BarRecord] = (),
        ticks: Iterable[TickRecord] = (),
        quotes: Iterable[QuoteRecord] = (),
        symbols_requested: int | None = None,
        aggregate_ticks_to: str | None = "1m",
        emit_events: bool = True,
    ) -> PipelineReport:
        """One full pass. Always returns a report, even when everything was refused."""
        report = PipelineReport(started_at=self._now_fn())
        # Materialise the inputs once. They may be generators, and the resolution rate has to
        # count the symbols that were *asked for*. Deriving it from accepted records only
        # would make the rate a constant 100% and hide every unresolved symbol — the exact
        # signal that tells us the registry is missing part of the universe.
        bar_input = list(bars)
        tick_input = list(ticks)
        quote_input = list(quotes)
        try:
            accepted_bars = self.ingest_bars(bar_input, venue=venue, report=report)
            accepted_ticks, aggregated = self.ingest_ticks(
                tick_input,
                venue=venue,
                report=report,
                aggregate_to=aggregate_ticks_to,
            )
            accepted_quotes = self.ingest_quotes(quote_input, venue=venue, report=report)
            # Aggregated bars go through the same validation as feed bars: a bar NEXUS built
            # is not more trustworthy than one a venue published.
            all_bars = merge_bars(accepted_bars, [b for b in aggregated if validate_bar(b) is None])
            requested: set[str] = set()
            requested.update(r.venue_symbol for r in bar_input)
            requested.update(r.venue_symbol for r in tick_input)
            requested.update(r.venue_symbol for r in quote_input)
            report.symbols_requested = symbols_requested or len(requested)
            await self.persist(
                bars=all_bars,
                ticks=accepted_ticks,
                quotes=accepted_quotes,
                report=report,
                emit_events=emit_events,
            )
        except Exception as exc:  # noqa: BLE001 - a pass must always produce a report
            report.errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            report.reject("PIPELINE_FAULT")
        finally:
            # Guarded on `total_faults`, not `total_rejected`: a pass where every record cleared
            # the gate but the aggregator discarded almost all of them has total_rejected == 0.
            # Requiring a gate rejection here meant the worst kind of degradation — data that
            # looks accepted but produces no usable bars — could never be flagged.
            if report.rejection_rate > self._max_rejection_rate and report.total_faults:
                report.errors.append(
                    f"DEGRADED:rejection rate {report.rejection_rate:.1%} exceeds "
                    f"{self._max_rejection_rate:.1%} — treat this feed as unreliable",
                )
            report.finish(self._now_fn())
            self._reports.append(report)
        return report


async def _maybe_await(value: Any) -> None:
    if hasattr(value, "__await__"):
        await value


def summarise_reports(reports: Sequence[PipelineReport]) -> dict[str, Any]:
    """Roll several passes into one honest picture for the Operations page."""
    if not reports:
        return {"passes": 0, "accepted": 0, "rejected": 0, "degraded": False}
    accepted = sum(r.total_accepted for r in reports)
    rejected = sum(r.total_rejected for r in reports)
    degraded = any("DEGRADED" in e for r in reports for e in r.errors)
    unresolved = sorted({s for r in reports for s in r.unresolved_symbols})
    return {
        "passes": len(reports),
        "accepted": accepted,
        "rejected": rejected,
        "rejection_rate": round(rejected / (accepted + rejected), 4) if (accepted + rejected) else 0.0,
        "degraded": degraded,
        "unresolved_symbols": unresolved[:50],
        "first_started": iso_utc(reports[0].started_at),
        "last_finished": iso_utc(reports[-1].finished_at) if reports[-1].finished_at else None,
        "timezone_note": "all timestamps UTC",
        "now_utc": iso_utc(datetime.now(tz=UTC)),
    }


__all__ = [
    "MINIMUM_STATUS_FOR_ARCHIVE",
    "IngestionPipeline",
    "PipelineReport",
    "PublishFn",
    "summarise_reports",
]
