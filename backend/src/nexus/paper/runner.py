"""The paper trading runner — the machine's composition root (Stage 11, D-059).

Run it and it trades: free public quotes are fetched, validated, archived, analysed, and the
resulting intents are executed in simulation. This module exists because without it the loop is only
ever driven by a test, and a component nothing calls is scaffolding however well tested it is.

It is a **separate process from the API**, and that is a deliberate shape rather than an omission:

* The API is a request/response service. A real-time loop that must keep polling a venue while the
  API restarts, redeploys or scales would either stop the loop or stop the API.
* The loop holds no request-scoped state and needs no inbound port, so it can run where an outbound
  connection is allowed and nothing else.
* A crash in the loop must not take the audit-serving API down with it, and the reverse.

Both processes read the same settings and write the same store, so the dashboard served by the API
shows what this runner is doing.

**What it refuses to do.** It checks the phase gate and the live-trading flag at startup and exits if
either would permit a real order, because a process that has been given venue symbols and an outbound
connection is exactly the process that must not be able to reach the trading path. The check is
redundant today — the paper package has no send path — and redundancy is the point: this is the one
place where being wrong twice is better than being wrong once.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nexus import PHASE_GATE
from nexus.archive import ParquetArchive
from nexus.core.config import Settings
from nexus.core.ids import iso_utc, utc_now
from nexus.ingestion import IngestionPipeline, QuoteRecord
from nexus.instruments.registry import InstrumentRegistry
from nexus.instruments.seed import seed_master
from nexus.paper.account import PaperAccount
from nexus.paper.analysis import AnalysisConfig, QuoteFlowAnalyzer
from nexus.paper.engine import PaperTradingEngine
from nexus.paper.fill_model import FillModelConfig, SimulatedFillModel
from nexus.paper.realtime import EquityFractionSizer, PaperTradingLoop

__all__ = ["FeedSpec", "PaperRunner", "main", "parse_feed", "run"]

#: Sources that can serve a *live* quote. binance-vision and dukascopy are historical archives: they
#: publish yesterday's data, and feeding that to a real-time loop would produce analysis of a market
#: that has already moved. They are excluded by name rather than by omission so the exclusion is a
#: decision on the record.
REALTIME_SOURCES = ("bybit-public", "okx-public")

#: The default feed is OKX rather than Bybit, and the reason is measured rather than preferred:
#: the seeded Bybit mapping for BTCUSDT sits at `VenueStatus.SUPPORTED`, below the pipeline's
#: `MINIMUM_STATUS_FOR_ARCHIVE` (DATA_AVAILABLE), so every quote from it is rejected before the loop
#: ever sees one — and F-2 records that bybit v5 answers 403 from hosted runners in any case. OKX's
#: BTC-USDT-SWAP mapping is DATA_AVAILABLE, so it is the free real-time source this build can
#: actually analyse. Changing this default silently would produce a runner that reports a healthy,
#: flat curve while accepting nothing.
_DEFAULT_FEED = "okx-public:BTC-USDT-SWAP"
HISTORICAL_SOURCES = ("binance-vision", "dukascopy")


#: A data *source* label and a *venue* name are different things, and the difference is not
#: cosmetic. `data_sources_enabled` lists sources ("okx-public"); the instrument registry maps
#: symbols to venues ("OKX"). Passing a source label where the pipeline expects a venue makes every
#: record resolve to INSTRUMENT_UNKNOWN, so the runner would poll a live feed, receive real quotes,
#: and accept none of them — reporting a healthy, flat curve the whole time. The mapping is written
#: down here rather than inferred, so a new source has to be added deliberately.
SOURCE_VENUE: dict[str, str] = {
    "bybit-public": "BYBIT",
    "okx-public": "OKX",
}


@dataclass(frozen=True, slots=True)
class FeedSpec:
    """One feed: the source to fetch from, the venue its symbols resolve against, and those symbols."""

    source: str
    venue: str
    symbols: tuple[str, ...]


def parse_feed(spec: str) -> tuple[FeedSpec, ...]:
    """Parse ``"bybit-public:BTCUSDT,ETHUSDT;okx-public:BTC-USDT"``.

    An empty or unparsable spec is an error rather than a silent no-feed run: a loop that polls
    nothing reports a healthy, flat equity curve, and a flat curve is indistinguishable from a
    strategy that made no mistakes.
    """
    if not spec or not spec.strip():
        raise ValueError("a feed spec is required: 'source:SYMBOL,SYMBOL;source:SYMBOL'")
    feeds: list[FeedSpec] = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        source, separator, symbols = chunk.partition(":")
        if not separator or not symbols.strip():
            raise ValueError(f"'{chunk}' is not 'source:SYMBOL,SYMBOL'")
        source = source.strip().lower()
        if source in HISTORICAL_SOURCES:
            raise ValueError(
                f"'{source}' is a historical archive and cannot serve a live quote; a real-time loop "
                f"fed from it would analyse a market that has already moved. Use one of "
                f"{', '.join(REALTIME_SOURCES)}."
            )
        if source not in REALTIME_SOURCES:
            raise ValueError(
                f"'{source}' is not a real-time source this runner implements; "
                f"the free real-time sources are {', '.join(REALTIME_SOURCES)}"
            )
        parsed = tuple(symbol.strip() for symbol in symbols.split(",") if symbol.strip())
        if not parsed:
            raise ValueError(f"'{chunk}' names no symbols")
        feeds.append(FeedSpec(source=source, venue=SOURCE_VENUE[source], symbols=parsed))
    if not feeds:
        raise ValueError(f"'{spec}' names no feeds")
    return tuple(feeds)


class PaperRunner:
    """Fetch → validate → archive → analyse → simulate, on a cycle, until stopped."""

    def __init__(
        self,
        *,
        settings: Settings,
        feeds: tuple[FeedSpec, ...],
        poll_seconds: float = 5.0,
        registry: InstrumentRegistry | None = None,
        verbose: bool = True,
        feed_spec: str = "",
    ) -> None:
        self._settings = settings
        self._feeds = feeds
        self._poll = poll_seconds
        self._feed_spec = feed_spec
        self._verbose = verbose
        self._stop = asyncio.Event()
        self._adapters: dict[str, Any] = {}
        self._cycles = 0
        self._quotes_seen = 0
        self._faults: list[str] = []

        self._registry = registry or InstrumentRegistry()
        if registry is None:
            # Seeded rather than empty, and nothing seeded becomes active (D-002): the runner needs
            # the master to resolve a venue symbol to an instrument id, exactly as ingestion does.
            seed_master(self._registry)

        starting = Decimal(str(settings.paper_starting_cash))
        self._engine = PaperTradingEngine(
            account=PaperAccount(
                account_id=settings.paper_account_id,
                currency=settings.paper_currency,
                simulated_cash=starting,
                starting_cash=starting,
            ),
            fill_model=SimulatedFillModel(
                FillModelConfig(
                    slippage_bps=Decimal(str(settings.paper_slippage_bps)),
                    commission_bps=Decimal(str(settings.paper_commission_bps)),
                    minimum_commission=Decimal(str(settings.paper_minimum_commission)),
                    latency_ms=int(settings.paper_latency_ms),
                    max_quote_age_seconds=Decimal(str(settings.paper_max_quote_age_seconds)),
                    respect_displayed_size=bool(settings.paper_respect_displayed_size),
                    refuse_delayed_data=bool(settings.paper_refuse_delayed_data),
                )
            ),
        )
        self._analyzer = QuoteFlowAnalyzer(
            AnalysisConfig(
                minimum_history=int(settings.paper_minimum_history),
                window=int(settings.paper_analysis_window),
                momentum_threshold_bps=Decimal(str(settings.paper_momentum_threshold_bps)),
                max_quote_age_seconds=Decimal(str(settings.paper_max_quote_age_seconds)),
                confidence_low=Decimal(str(settings.paper_confidence_low)),
                confidence_high=Decimal(str(settings.paper_confidence_high)),
            )
        )
        watchlist = tuple(
            part.strip() for part in str(settings.paper_watchlist or "").split(",") if part.strip()
        )
        self._loop = PaperTradingLoop(
            engine=self._engine,
            analyzer=self._analyzer,
            sizer=EquityFractionSizer(
                risk_fraction=Decimal(str(settings.paper_risk_fraction)),
                max_position_notional=Decimal(str(settings.paper_max_position_notional)),
            ),
            account_id=settings.paper_account_id,
            min_analysis_interval_seconds=Decimal(str(settings.paper_min_analysis_interval_seconds)),
            post_trade_cooldown_seconds=Decimal(str(settings.paper_post_trade_cooldown_seconds)),
            max_open_positions=int(settings.paper_max_open_positions),
            watchlist=watchlist,
        )
        # The archive is not optional here, and the reason is a rule rather than a preference.
        # `IngestionPipeline.persist` returns early when no archive is configured, because rule 4
        # says a consumer must never see a record the archive does not hold — so an observer wired to
        # an archive-less pipeline is never called at all. Configuring the archive is what makes the
        # loop receive quotes, and it also means every price a simulated fill executed against is on
        # disk and can be re-read: a paper result whose inputs were never kept cannot be audited,
        # which is the one thing a rehearsal is for.
        self._archive = ParquetArchive(settings.archive_root)
        self._pipeline = IngestionPipeline(
            registry=self._registry, archive=self._archive, on_records=self._observe
        )

    # -- safety --------------------------------------------------------------

    def assert_cannot_trade_live(self) -> None:
        """Refuse to start if this build could place a real order.

        Redundant with the paper package having no send path, and kept anyway: this is the process
        that holds venue symbols and an outbound connection.
        """
        problems: list[str] = []
        if PHASE_GATE["live_trading"]:
            problems.append("PHASE_GATE.live_trading is true")
        if PHASE_GATE["order_capability"]:
            problems.append("PHASE_GATE.order_capability is true")
        if PHASE_GATE["venue_adapters"]:
            problems.append("PHASE_GATE.venue_adapters is true")
        if self._settings.live_trading_enabled:
            problems.append("NEXUS_LIVE_TRADING_ENABLED is true")
        if self._engine.can_place_live_orders:
            problems.append("the paper engine claims live order capability")
        if problems:
            raise SystemExit(
                "refusing to start the paper runner: " + "; ".join(problems) + ". "
                "This process fetches live venue data and must never be the one that can trade it."
            )

    # -- the cycle -----------------------------------------------------------

    def _observe(self, kind: str, records: Any) -> None:
        """The pipeline's record observer: accepted quotes go to the loop.

        Called by the pipeline *after* the archive write, so the loop never analyses a record the
        archive does not hold — ingestion rule 4, preserved rather than routed around.
        """
        if kind != "quotes":
            return
        for record in records:
            if not isinstance(record, QuoteRecord):
                continue
            self._quotes_seen += 1
            self._loop.on_quote(record)

    async def _adapter_for(self, source: str) -> Any | None:
        if source in self._adapters:
            return self._adapters[source]
        adapter: Any | None = None
        if source == "bybit-public":
            from nexus.ingestion.bybit import BybitPublicAdapter

            adapter = BybitPublicAdapter()
        elif source == "okx-public":
            from nexus.ingestion.okx import OkxPublicAdapter

            adapter = OkxPublicAdapter()
        if adapter is not None:
            self._adapters[source] = adapter
        return adapter

    async def poll_once(self) -> dict[str, Any]:
        """One pass over every feed. Always returns a summary, even when every source failed."""
        self._cycles += 1
        summary: dict[str, Any] = {"cycle": self._cycles, "at": iso_utc(utc_now()), "feeds": []}
        for feed in self._feeds:
            entry: dict[str, Any] = {
                "source": feed.source,
                "venue": feed.venue,
                "symbols": list(feed.symbols),
            }
            adapter = await self._adapter_for(feed.source)
            if adapter is None:
                entry["error"] = "NO_ADAPTER"
                summary["feeds"].append(entry)
                continue
            try:
                quotes = await adapter.quotes(list(feed.symbols))
            except Exception as exc:  # noqa: BLE001 - one venue failing must not stop the others
                detail = f"{type(exc).__name__}: {str(exc)[:200]}"
                entry["error"] = detail
                self._faults.append(f"{feed.source}: {detail}")
                summary["feeds"].append(entry)
                continue
            # Through the pipeline rather than straight to the loop: validation, provenance and the
            # archive write all happen, so a quote the loop trades on is a quote the archive holds.
            # `feed.venue`, not `feed.source`: the registry resolves symbols against a venue name.
            report = await self._pipeline.run(venue=feed.venue, quotes=quotes, emit_events=False)
            entry["fetched"] = len(quotes)
            entry["accepted"] = report.quotes_accepted
            entry["rejected"] = len(report.rejections) if hasattr(report, "rejections") else 0
            summary["feeds"].append(entry)
        return summary

    async def run(self, *, max_cycles: int | None = None) -> None:
        """Poll until stopped, or for ``max_cycles`` passes when a bounded run was asked for."""
        self.assert_cannot_trade_live()
        self._log(
            f"paper runner starting: {len(self._feeds)} feed(s), poll every {self._poll}s, "
            f"account {self._settings.paper_account_id}, "
            f"capital {self._settings.paper_starting_cash} {self._settings.paper_currency} (simulated)"
        )
        while not self._stop.is_set():
            summary = await self.poll_once()
            if self._verbose:
                self._log(self._format(summary))
            if max_cycles is not None and self._cycles >= max_cycles:
                break
            # A timeout here is the normal path: it means nobody asked to stop, so the cycle
            # continues. `suppress` says that more clearly than an empty except block does.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
        await self.aclose()

    def stop(self) -> None:
        self._stop.set()

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            close = getattr(adapter, "aclose", None)
            if close is None:
                continue
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - shutdown must complete
                self._log(f"closing an adapter raised {type(exc).__name__}: {exc}")
        snapshot = self._engine.snapshot()
        self._log(
            f"stopped after {self._cycles} cycle(s), {self._quotes_seen} quote(s) observed. "
            f"Simulated equity {snapshot.equity} {snapshot.currency}, "
            f"net P&L {snapshot.net_pnl}, {snapshot.fills_applied} fills, "
            f"{snapshot.open_position_count} open position(s)."
        )
        if self._faults:
            self._log(f"{len(self._faults)} feed fault(s); the last: {self._faults[-1]}")

    @property
    def archive_root(self) -> str:
        """Where the quotes behind every simulated fill are written."""
        return str(self._settings.archive_root)

    @property
    def cycles(self) -> int:
        return self._cycles

    @property
    def quotes_seen(self) -> int:
        return self._quotes_seen

    def report(self) -> dict[str, Any]:
        snapshot = self._engine.snapshot()
        return {
            "feed": self._feed_spec,
            "archive_root": self.archive_root,
            "cycles": self._cycles,
            "quotes_seen": self._quotes_seen,
            "faults": list(self._faults[-20:]),
            "stats": self._loop.stats().to_dict(),
            "account": snapshot.to_dict(),
            "simulated": True,
            "environment": "PAPER",
        }

    def _format(self, summary: dict[str, Any]) -> str:
        parts = [f"cycle {summary['cycle']}"]
        for feed in summary["feeds"]:
            if "error" in feed:
                parts.append(f"{feed['source']}: ⚠ {feed['error']}")
            else:
                parts.append(f"{feed['source']}: {feed['accepted']}/{feed['fetched']} accepted")
        stats = self._loop.stats()
        parts.append(
            f"analyses {stats.analyses_run} · actionable {stats.actionable_verdicts} · "
            f"simulated {stats.trades_simulated} · unfilled {stats.trades_unfilled}"
        )
        return " | ".join(parts)

    def _log(self, message: str) -> None:
        print(f"[{iso_utc(utc_now())}] {message}", flush=True)


async def run(spec: str, *, cycles: int | None, poll: float, bounded: bool = False) -> int:
    settings = Settings()
    runner = PaperRunner(
        settings=settings,
        feeds=parse_feed(spec),
        poll_seconds=poll,
        feed_spec=spec,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except NotImplementedError:  # pragma: no cover - Windows has no signal handlers
            signal.signal(sig, lambda *_: runner.stop())
    await runner.run(max_cycles=cycles)
    if bounded and runner.quotes_seen == 0:
        # A bounded run that observed nothing is a failed run, whatever the reason: it is the shape
        # a compose healthcheck, a CI job or a cron entry sees, and exit 0 would report success for a
        # pass in which no venue answered. An unbounded run keeps polling instead, which is correct —
        # a feed that is down at 03:00 is not a reason to stop trying at 03:05.
        return 4
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nexus.paper.runner",
        description=(
            "Run the NEXUS paper trading machine: fetch free public quotes, archive them, analyse "
            "them in real time and simulate the trades. No venue connection, no credential, and no "
            "real order is possible."
        ),
    )
    parser.add_argument(
        "--feed",
        default=_DEFAULT_FEED,
        help=(
            "'source:SYMBOL,SYMBOL;source:SYMBOL' — real-time sources only. "
            "The default is the one free source whose seeded mapping is at DATA_AVAILABLE."
        ),
    )
    parser.add_argument(
        "--cycles", type=int, default=None, help="stop after N passes (default: run until stopped)"
    )
    parser.add_argument(
        "--poll", type=float, default=5.0, help="seconds between passes (default: %(default)s)"
    )
    args = parser.parse_args(argv)
    try:
        # Validated here so a bad spec is refused before an event loop is created, with the reason on
        # stderr and a distinct exit code. The result is discarded: `run` parses it again, and keeping
        # two parsed copies would be two chances to disagree.
        parse_feed(args.feed)
    except ValueError as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2
    try:
        return asyncio.run(
            run(args.feed, cycles=args.cycles, poll=args.poll, bounded=args.cycles is not None)
        )
    except SystemExit as exc:  # the safety refusal above
        print(str(exc), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
