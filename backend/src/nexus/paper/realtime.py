"""The real-time paper trading loop (Stage 11, D-059).

This is the machine running: quotes arrive, they are analysed, and when the analysis clears the
confidence band the resulting intent is executed in simulation. It is the rehearsal the owner asked
for — the same path a live trade would take, up to the point where a live trade would leave the
building.

The loop is driven rather than polling. ``on_quote`` is called by whatever already receives market
data, so the analysis happens on the observation and not on a timer that could be slower than the
market. A background worker is provided for running it against a live feed, but the synchronous path
is the real one and is what the tests exercise: a loop that only works when a thread is running
cannot be proven to work.

Two protections matter and are not decoration.

**Per-instrument throttling.** Analysing every tick of a fast feed produces hundreds of verdicts a
second for one instrument, most of them the same verdict. ``min_analysis_interval_seconds`` bounds
that, and the bounded recent-analysis log bounds memory. Without both, a real feed would exhaust the
process long before it taught anyone anything.

**Position and exposure limits.** The loop will not open a position it is not sized for, and will
not exceed ``max_open_positions``. A simulator with no limits produces a spectacular equity curve
that means nothing, because no real account could have held the positions that made it.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionVerb
from nexus.execution.intent import TradeIntent
from nexus.paper.analysis import AnalysisVerdict, Analyzer, QuoteFlowAnalyzer
from nexus.paper.engine import PaperEngineStatus, PaperTradingEngine

__all__ = [
    "EquityFractionSizer",
    "LoopStats",
    "PaperTradingLoop",
    "Sizer",
]


class Sizer(Protocol):
    """How large a position the loop is allowed to take."""

    def quantity(
        self, *, price: Decimal, engine: PaperTradingEngine, instrument_id: str, venue: str
    ) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class EquityFractionSizer:
    """Sizes a position as a fraction of current simulated equity, capped by notional.

    Real code with real arithmetic: the quantity is what the equity, the price and the cap actually
    allow, rounded down to the instrument's lot step. It never returns a quantity the account could
    not pay for, which is the one property a paper sizer must have if its P&L is to mean anything.
    """

    risk_fraction: Decimal = Decimal("0.02")
    max_position_notional: Decimal = Decimal("25000")
    lot_step: Decimal = Decimal("0.00000001")
    max_quantity: Decimal = Decimal("1000000")

    def quantity(
        self,
        *,
        price: Decimal,
        engine: PaperTradingEngine,
        # Unused here but part of the Sizer contract: a per-instrument limit is exactly what a
        # Strategy Laboratory sizer needs, and widening the protocol later would silently pass the
        # wrong arguments to every implementation written against it.
        instrument_id: str,  # noqa: ARG002
        venue: str,  # noqa: ARG002
    ) -> Decimal:
        if price <= 0:
            return Decimal("0")
        snapshot = engine.snapshot()
        budget = min(
            snapshot.equity * self.risk_fraction,
            self.max_position_notional,
        )
        if budget <= 0:
            return Decimal("0")
        raw = budget / price
        if self.lot_step > 0:
            raw = (raw / self.lot_step).to_integral_value(rounding="ROUND_DOWN") * self.lot_step
        return min(raw, self.max_quantity).quantize(self.lot_step or Decimal("0.00000001"))


@dataclass(frozen=True, slots=True)
class LoopStats:
    """What the loop has done. Every counter is a fact, published for the dashboard."""

    quotes_observed: int = 0
    analyses_run: int = 0
    analyses_throttled: int = 0
    actionable_verdicts: int = 0
    intents_created: int = 0
    trades_simulated: int = 0
    trades_refused: int = 0
    trades_unfilled: int = 0
    blocked_by_position_limit: int = 0
    blocked_by_cooldown: int = 0
    blocked_by_sizing: int = 0
    last_analysis_elapsed_ms: float = 0.0
    slowest_analysis_ms: float = 0.0
    started_at: str | None = None
    stopped_at: str | None = None
    running: bool = False
    instruments_tracked: int = 0
    queue_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "quotes_observed": self.quotes_observed,
            "analyses_run": self.analyses_run,
            "analyses_throttled": self.analyses_throttled,
            "actionable_verdicts": self.actionable_verdicts,
            "intents_created": self.intents_created,
            "trades_simulated": self.trades_simulated,
            "trades_refused": self.trades_refused,
            "trades_unfilled": self.trades_unfilled,
            "blocked_by_position_limit": self.blocked_by_position_limit,
            "blocked_by_cooldown": self.blocked_by_cooldown,
            "blocked_by_sizing": self.blocked_by_sizing,
            "last_analysis_elapsed_ms": self.last_analysis_elapsed_ms,
            "slowest_analysis_ms": self.slowest_analysis_ms,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "running": self.running,
            "instruments_tracked": self.instruments_tracked,
            "queue_depth": self.queue_depth,
            "simulated": True,
            "environment": "PAPER",
        }


class PaperTradingLoop:
    """Observe → analyse → (maybe) trade, in simulation, as fast as real data arrives."""

    def __init__(
        self,
        *,
        engine: PaperTradingEngine,
        analyzer: Analyzer | None = None,
        sizer: Sizer | None = None,
        events: Any | None = None,
        audit: Any | None = None,
        account_id: str = "PAPER-MAIN",
        min_analysis_interval_seconds: Decimal = Decimal("1"),
        post_trade_cooldown_seconds: Decimal = Decimal("60"),
        max_open_positions: int = 8,
        recent_limit: int = 200,
        max_queue: int = 10_000,
        watchlist: tuple[str, ...] = (),
    ) -> None:
        self._engine = engine
        self._analyzer: Analyzer = analyzer or QuoteFlowAnalyzer()
        self._sizer: Sizer = sizer or EquityFractionSizer()
        self._events = events
        self._audit = audit
        self._account_id = account_id
        self._min_interval = min_analysis_interval_seconds
        self._cooldown = post_trade_cooldown_seconds
        self._max_open_positions = max_open_positions
        self._last_trade: dict[tuple[str, str], datetime] = {}
        self._watchlist = tuple(watchlist)
        self._recent: list[dict[str, Any]] = []
        self._recent_limit = recent_limit
        self._lock = threading.RLock()
        self._last_analysis: dict[tuple[str, str], datetime] = {}
        # Counters live in plain dicts rather than as a `LoopStats` instance: the dataclass is the
        # published shape and deliberately has no `simulated`/`environment` fields to construct
        # from, so round-tripping it through `to_dict()` would raise on the very first quote.
        self._counts: dict[str, int] = dict.fromkeys(
            (
                "quotes_observed",
                "analyses_run",
                "analyses_throttled",
                "actionable_verdicts",
                "intents_created",
                "trades_simulated",
                "trades_refused",
                "trades_unfilled",
                "blocked_by_position_limit",
                "blocked_by_cooldown",
                "blocked_by_sizing",
            ),
            0,
        )
        self._timing = {"last_analysis_elapsed_ms": 0.0, "slowest_analysis_ms": 0.0}
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=max_queue)
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()

    # -- what it is --------------------------------------------------------

    simulated = True
    can_place_live_orders = False

    def describe(self) -> dict[str, Any]:
        analyzer_describe = (
            self._analyzer.describe() if hasattr(self._analyzer, "describe") else {"analyzer": "custom"}
        )
        return {
            "loop": "paper-realtime",
            "simulated": True,
            "environment": "PAPER",
            "can_place_live_orders": False,
            "account_id": self._account_id,
            "analyzer": analyzer_describe,
            "min_analysis_interval_seconds": str(self._min_interval),
            "post_trade_cooldown_seconds": str(self._cooldown),
            "max_open_positions": self._max_open_positions,
            "watchlist": list(self._watchlist),
            "engine": self._engine.describe(),
        }

    def stats(self) -> LoopStats:
        with self._lock:
            fields: dict[str, Any] = dict(self._counts)
            fields.update(self._timing)
            return LoopStats(
                **fields,
                started_at=self._started_at,
                stopped_at=self._stopped_at,
                running=self._worker is not None and self._worker.is_alive(),
                instruments_tracked=len(self._last_analysis),
                queue_depth=self._queue.qsize(),
            )

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent[-limit:])

    # -- the synchronous path (the real one) --------------------------------

    def on_quote(self, quote: Any, *, now: datetime | None = None) -> AnalysisVerdict | None:
        """Feed one real observation through the loop. Returns the verdict if one was produced.

        Returns ``None`` when the quote was dropped (not on the watchlist, unusable sides) or when
        analysis was throttled. The caller can always ask ``stats()`` for which happened.
        """
        moment = now or utc_now()
        instrument_id = str(getattr(quote, "instrument_id", ""))
        venue = str(getattr(quote, "venue", ""))
        if self._watchlist and instrument_id not in self._watchlist:
            return None

        self._analyzer.observe(quote, now=moment)
        self._bump("quotes_observed")

        key = (instrument_id, venue)
        with self._lock:
            previous = self._last_analysis.get(key)
        if previous is not None and self._min_interval > 0:
            elapsed = Decimal((moment - previous).total_seconds())
            if elapsed < self._min_interval:
                self._bump("analyses_throttled")
                return None

        with self._lock:
            self._last_analysis[key] = moment
        verdict = self._analyzer.verdict(instrument_id, venue, now=moment)
        self._remember(verdict)
        self._bump("analyses_run")
        with self._lock:
            self._timing["last_analysis_elapsed_ms"] = verdict.elapsed_ms
            self._timing["slowest_analysis_ms"] = max(self._timing["slowest_analysis_ms"], verdict.elapsed_ms)
        self._publish("nexus.paper.analysis", verdict.to_dict())

        if not verdict.actionable:
            return verdict
        self._bump("actionable_verdicts")
        key = (verdict.instrument_id, verdict.venue)
        with self._lock:
            last = self._last_trade.get(key)
        # Without a cooldown the loop adds to the same position on every tick that still shows
        # momentum, and a rising market produces a spectacular curve built out of one idea repeated
        # thirty times. The cooldown makes each trade a separate decision.
        since = Decimal("0") if last is None else Decimal((moment - last).total_seconds())
        if last is not None and self._cooldown > 0 and since < self._cooldown:
            self._bump("blocked_by_cooldown")
            self._remember_block(
                verdict,
                f"COOLDOWN:traded this instrument {since}s ago, inside the {self._cooldown}s cooldown",
            )
            return verdict
        self._trade(verdict, quote=quote, now=moment)
        return verdict

    def _trade(self, verdict: AnalysisVerdict, *, quote: Any, now: datetime) -> None:
        with self._lock:
            if len(self._engine.account.open_positions) >= self._max_open_positions:
                self._bump("blocked_by_position_limit")
                self._remember_block(
                    verdict,
                    f"POSITION_LIMIT:{self._max_open_positions} positions already open",
                )
                return

        price = self._reference_price(verdict, quote)
        if price is None or price <= 0:
            self._bump("blocked_by_sizing")
            self._remember_block(verdict, "NO_PRICE:nothing real to size against")
            return

        quantity = self._sizer.quantity(
            price=price,
            engine=self._engine,
            instrument_id=verdict.instrument_id,
            venue=verdict.venue,
        )
        if quantity <= 0:
            self._bump("blocked_by_sizing")
            self._remember_block(verdict, "SIZING_ZERO:the sizer returned no quantity for this price")
            return

        side = self._side_for(verdict)
        intent = TradeIntent(
            intent_id=new_id("PPI"),
            decision_id=verdict.analysis_id,
            instrument_id=verdict.instrument_id,
            venue=verdict.venue,
            account_id=self._account_id,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            quote_currency="USD",
            # The intent declares its own environment, so a paper intent can never be mistaken for a
            # live one downstream — not even by a reader looking at the ledger row alone.
            environment="PAPER",
            # `TradeIntent` has no `rationale` field; `evidence_summary` is the one that carries why
            # this intent exists, and it is what the approval UI is ruled to show (Section 24).
            evidence_summary=(
                f"paper loop acted on {verdict.verb.value} at confidence {verdict.confidence}: "
                + "; ".join(verdict.reasons)
            ),
        )
        self._bump("intents_created")
        with self._lock:
            self._last_trade[(verdict.instrument_id, verdict.venue)] = now
        result = self._engine.run(
            intent,
            quote=quote,
            mark=self._analyzer.mark(verdict.instrument_id, verdict.venue)
            if hasattr(self._analyzer, "mark")
            else None,
            now=now,
        )
        if result.refused:
            counter = "trades_refused"
        elif result.status is PaperEngineStatus.UNFILLED:
            counter = "trades_unfilled"
        else:
            counter = "trades_simulated"
        self._bump(counter)
        self._publish("nexus.paper.trade", result.to_audit_payload())

    # -- the background worker ---------------------------------------------

    def submit(self, quote: Any) -> bool:
        """Hand a quote to the background worker. ``False`` if the queue is full.

        A full queue is reported rather than blocked on: ingestion must never stall because the
        paper loop is behind, and dropping a quote is recoverable while stalling a feed is not.
        """
        try:
            self._queue.put_nowait(quote)
        except queue.Full:
            return False
        return True

    def start(self) -> None:
        """Start the background worker. Idempotent."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop.clear()
            self._worker = threading.Thread(target=self._run_worker, name="nexus-paper-loop", daemon=True)
            self._started_at = iso_utc(utc_now())
            self._worker.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the worker and drain nothing: queued quotes are dropped, and that is reported."""
        self._stop.set()
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)
        with self._lock:
            dropped = self._queue.qsize()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:  # pragma: no cover - race with the worker
                    break
            self._stopped_at = iso_utc(utc_now())
        if dropped:
            self._audit_record(
                "paper.loop.stopped_with_backlog",
                {"dropped_quotes": dropped, "simulated": True, "environment": "PAPER"},
            )

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                quote = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self.on_quote(quote)
            except Exception as exc:  # noqa: BLE001 - a loop must not die on one bad quote
                self._audit_record(
                    "paper.loop.error",
                    {
                        "error": str(exc),
                        "instrument_id": str(getattr(quote, "instrument_id", "")),
                        "simulated": True,
                        "environment": "PAPER",
                    },
                )

    # -- internals ---------------------------------------------------------

    def _side_for(self, verdict: AnalysisVerdict) -> str:
        """Map a verb to the position intent the engine expects."""
        if verdict.verb is DecisionVerb.EXIT:
            held = self._engine.account.position(verdict.instrument_id, verdict.venue)
            if held is not None and held.quantity < 0:
                return "BUY"  # closing a short
            if held is not None and held.quantity > 0:
                return "CLOSE"
            return "SHORT"
        if verdict.verb is DecisionVerb.REDUCE:
            return "CLOSE"
        return "LONG"

    def _reference_price(self, verdict: AnalysisVerdict, quote: Any) -> Decimal | None:
        mid = verdict.evidence.get("mid")
        if isinstance(mid, str):
            return Decimal(mid)
        for name in ("last", "ask", "bid"):
            value = getattr(quote, name, None)
            if isinstance(value, Decimal):
                return value
        return None

    def _remember(self, verdict: AnalysisVerdict) -> None:
        with self._lock:
            self._recent.append(verdict.to_dict())
            if len(self._recent) > self._recent_limit:
                del self._recent[: len(self._recent) - self._recent_limit]

    def _remember_block(self, verdict: AnalysisVerdict, reason: str) -> None:
        payload = verdict.to_dict()
        payload["blocked"] = reason
        with self._lock:
            self._recent.append(payload)
            if len(self._recent) > self._recent_limit:
                del self._recent[: len(self._recent) - self._recent_limit]
        self._audit_record("paper.loop.blocked", {"reason": reason, **payload})

    def _bump(self, name: str) -> None:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + 1

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._audit_record(topic.replace("nexus.", "").replace(".", "_"), payload)
        if self._events is None:
            return
        from nexus.events.bus import EventEnvelope

        self._events.publish(EventEnvelope(topic=topic, payload=payload))

    def _audit_record(self, kind: str, payload: dict[str, Any]) -> None:
        if self._audit is not None:
            self._audit.record(kind, payload)
