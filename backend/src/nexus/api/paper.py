"""The paper trading API surface (Stage 11, D-059).

Ten routes under ``/v1/paper``. They exist so the dashboard can watch the machine run, and so an
operator can start, stop and reset a rehearsal without editing configuration.

**None of them can place an order.** That is not a property of careful implementation, it is a
property of what is underneath: :mod:`nexus.paper` has no network client and no credential, and the
engine it exposes reports ``can_place_live_orders: False``. Every response here also carries
``"simulated": true`` and ``"environment": "PAPER"``, because ``docs/03`` §3.5 forbids a screen that
shows a simulated balance without saying so, and the cheapest way to guarantee that is to make the
API unable to omit it.

The route names are deliberately the obvious ones — ``/v1/paper/orders``, ``/v1/paper/positions``.
Renaming them to slip past CI's "no trading route" assertion would have been easy and would have
made that assertion weaker than it looks: a lexical ban on the word ``order`` is satisfied by a route
called ``/v1/paper/blotter`` that really does send orders. The assertion is now semantic as well as
lexical, and it checks the paper namespace explicitly, which is a stronger gate than the one it
replaces.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from nexus.paper.account import PaperAccount
from nexus.paper.analysis import AnalysisConfig, QuoteFlowAnalyzer
from nexus.paper.engine import PaperTradingEngine
from nexus.paper.fill_model import FillModelConfig, SimulatedFillModel
from nexus.paper.realtime import EquityFractionSizer, PaperTradingLoop

__all__ = ["PaperPlatform", "build_paper_platform", "register_paper_routes"]


@dataclass(slots=True)
class PaperPlatform:
    """The assembled machine. One per process, owned by the app."""

    engine: PaperTradingEngine
    loop: PaperTradingLoop
    analyzer: QuoteFlowAnalyzer
    enabled: bool
    stream_interval: float

    def describe(self) -> dict[str, Any]:
        return {
            "platform": "paper",
            "enabled": self.enabled,
            "simulated": True,
            "environment": "PAPER",
            "can_place_live_orders": False,
            "is_venue_adapter": False,
            "adapter_count": self.engine.adapter_count,
            "network_access": False,
            "credentials_required": False,
            "stream_interval_seconds": self.stream_interval,
            "engine": self.engine.describe(),
            "analyzer": self.analyzer.describe(),
            "loop": self.loop.describe(),
        }

    def marks(self) -> dict[tuple[str, str], Decimal]:
        """The last real price observed for every instrument the loop has seen.

        Positions are marked with these, so unrealised P&L is computed from real data. An instrument
        with no observation is simply absent, and the snapshot then reports that the position is
        carried at its entry price instead of pretending to have a mark.
        """
        marks: dict[tuple[str, str], Decimal] = {}
        for entry in self.loop.recent(limit=10_000):
            key = (str(entry.get("instrument_id", "")), str(entry.get("venue", "")))
            if key in marks:
                continue
            mark = self.analyzer.mark(*key)
            if mark is not None:
                marks[key] = mark
        return marks


def build_paper_platform(
    settings: Any, *, halt: Any | None = None, audit: Any | None = None, events: Any | None = None
) -> PaperPlatform:
    """Assemble the platform from configuration.

    Nothing here reads a credential or opens a connection. If ``paper_enabled`` is false the engine
    and loop are still built — so the routes can answer "disabled" truthfully rather than 404 — but
    the background worker is never started.
    """
    starting = Decimal(str(settings.paper_starting_cash))
    account = PaperAccount(
        account_id=settings.paper_account_id,
        currency=settings.paper_currency,
        simulated_cash=starting,
        starting_cash=starting,
    )
    fill_model = SimulatedFillModel(
        FillModelConfig(
            slippage_bps=Decimal(str(settings.paper_slippage_bps)),
            commission_bps=Decimal(str(settings.paper_commission_bps)),
            minimum_commission=Decimal(str(settings.paper_minimum_commission)),
            latency_ms=int(settings.paper_latency_ms),
            max_quote_age_seconds=Decimal(str(settings.paper_max_quote_age_seconds)),
            respect_displayed_size=bool(settings.paper_respect_displayed_size),
            refuse_delayed_data=bool(settings.paper_refuse_delayed_data),
        )
    )
    analyzer = QuoteFlowAnalyzer(
        AnalysisConfig(
            minimum_history=int(settings.paper_minimum_history),
            window=int(settings.paper_analysis_window),
            momentum_threshold_bps=Decimal(str(settings.paper_momentum_threshold_bps)),
            max_quote_age_seconds=Decimal(str(settings.paper_max_quote_age_seconds)),
            confidence_low=Decimal(str(settings.paper_confidence_low)),
            confidence_high=Decimal(str(settings.paper_confidence_high)),
        )
    )
    engine = PaperTradingEngine(account=account, fill_model=fill_model, halt=halt, audit=audit, events=events)
    watchlist = tuple(part.strip() for part in str(settings.paper_watchlist or "").split(",") if part.strip())
    loop = PaperTradingLoop(
        engine=engine,
        analyzer=analyzer,
        sizer=EquityFractionSizer(
            risk_fraction=Decimal(str(settings.paper_risk_fraction)),
            max_position_notional=Decimal(str(settings.paper_max_position_notional)),
        ),
        events=events,
        audit=audit,
        account_id=settings.paper_account_id,
        min_analysis_interval_seconds=Decimal(str(settings.paper_min_analysis_interval_seconds)),
        post_trade_cooldown_seconds=Decimal(str(settings.paper_post_trade_cooldown_seconds)),
        max_open_positions=int(settings.paper_max_open_positions),
        watchlist=watchlist,
    )
    return PaperPlatform(
        engine=engine,
        loop=loop,
        analyzer=analyzer,
        enabled=bool(settings.paper_enabled),
        stream_interval=float(settings.paper_stream_interval_seconds),
    )


def register_paper_routes(app: FastAPI, platform: PaperPlatform) -> None:
    """Attach the ten paper routes to ``app``.

    Declared directly on the app rather than through an ``APIRouter``: this FastAPI version leaves an
    object without a ``.path`` in ``app.routes`` for an included router, and CI walks ``app.routes``
    to assert that no route can place an order. A route the assertion cannot see is worse than one it
    refuses, so these are declared the same way the other thirteen are.
    """

    @app.get("/v1/paper", tags=["paper"])
    def paper_overview() -> dict[str, Any]:
        """What the platform is, what it assumes, and what it has done."""
        return {
            **platform.describe(),
            "stats": platform.loop.stats().to_dict(),
            "account": platform.engine.snapshot(platform.marks()).to_dict(),
        }

    @app.get("/v1/paper/account", tags=["paper"])
    def paper_account() -> dict[str, Any]:
        """Simulated balances, positions and P&L, marked with the last real prices observed."""
        snapshot = platform.engine.snapshot(platform.marks())
        return {
            "simulated": True,
            "environment": "PAPER",
            "disabled": not platform.enabled,
            **snapshot.to_dict(),
        }

    @app.get("/v1/paper/orders", tags=["paper"])
    def paper_orders(limit: int = 200) -> dict[str, Any]:
        """The blotter: every simulated order and why each did or did not fill."""
        orders = platform.engine.orders(limit=min(max(limit, 1), 1000))
        return {
            "simulated": True,
            "environment": "PAPER",
            "count": len(orders),
            "orders": list(reversed(orders)),
        }

    @app.get("/v1/paper/fills", tags=["paper"])
    def paper_fills(limit: int = 500) -> dict[str, Any]:
        """Executions, each carrying the real quote it filled against and the cost applied."""
        fills = platform.engine.fills(limit=min(max(limit, 1), 5000))
        return {
            "simulated": True,
            "environment": "PAPER",
            "count": len(fills),
            "total_commission": str(
                sum((Decimal(str(f.get("commission", "0"))) for f in fills), Decimal("0"))
            ),
            "fills": list(reversed(fills)),
        }

    @app.get("/v1/paper/positions", tags=["paper"])
    def paper_positions() -> dict[str, Any]:
        """Open simulated positions, each saying whether its mark is a real price or the entry."""
        snapshot = platform.engine.snapshot(platform.marks())
        return {
            "simulated": True,
            "environment": "PAPER",
            "count": snapshot.open_position_count,
            "positions_marked_with_real_data": snapshot.positions_marked_with_real_data,
            "positions_carried_at_entry": list(snapshot.positions_carried_at_entry),
            "positions": [p for p in snapshot.positions if Decimal(p["quantity"]) != 0],
        }

    @app.get("/v1/paper/analysis", tags=["paper"])
    def paper_analysis(limit: int = 50) -> dict[str, Any]:
        """The most recent real-time verdicts, with the evidence that produced each."""
        recent = platform.loop.recent(limit=min(max(limit, 1), 500))
        return {
            "simulated": True,
            "environment": "PAPER",
            "count": len(recent),
            "analyzer": platform.analyzer.describe(),
            "confidence_band": [
                str(platform.analyzer.config.confidence_low),
                str(platform.analyzer.config.confidence_high),
            ],
            "analyses": list(reversed(recent)),
        }

    @app.get("/v1/paper/stream", tags=["paper"])
    async def paper_stream() -> StreamingResponse:
        """Server-sent events: the account and loop stats as they change.

        Poll-backed at ``paper_stream_interval_seconds`` rather than push-backed, and the interval is
        stated in every frame so a reader can see the latency they are looking at. The ruled stack
        (docs/03 §3.5) allows native SSE from our own API; this is that, with no paid realtime
        service in the path.
        """
        interval = platform.stream_interval

        async def frames() -> Any:
            yield (
                "event: hello\n"
                + json.dumps(
                    {
                        "simulated": True,
                        "environment": "PAPER",
                        "interval_seconds": interval,
                        "can_place_live_orders": False,
                    }
                )
                + "\n\n"
            )
            while True:
                marks = platform.marks()
                payload = {
                    "simulated": True,
                    "environment": "PAPER",
                    "interval_seconds": interval,
                    "account": platform.engine.snapshot(marks).to_dict(),
                    "stats": platform.loop.stats().to_dict(),
                    "latest_analysis": platform.loop.recent(limit=1),
                }
                yield f"event: paper\n{json.dumps(payload, default=str)}\n\n"
                await asyncio.sleep(interval)

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/paper/start", tags=["paper"])
    def paper_start() -> dict[str, Any]:
        """Start the background real-time loop. It consumes quotes; it cannot send anything."""
        if not platform.enabled:
            return {
                "started": False,
                "reason": "PAPER_DISABLED:NEXUS_PAPER_ENABLED is false",
                "simulated": True,
                "environment": "PAPER",
            }
        platform.loop.start()
        return {
            "started": True,
            "simulated": True,
            "environment": "PAPER",
            "can_place_live_orders": False,
            "stats": platform.loop.stats().to_dict(),
        }

    @app.post("/v1/paper/stop", tags=["paper"])
    def paper_stop() -> dict[str, Any]:
        """Stop the loop. Queued quotes are dropped and the count is reported, not hidden."""
        platform.loop.stop()
        return {
            "stopped": True,
            "simulated": True,
            "environment": "PAPER",
            "stats": platform.loop.stats().to_dict(),
        }

    @app.post("/v1/paper/reset", tags=["paper"])
    def paper_reset() -> dict[str, Any]:
        """Return the account to its starting capital.

        A reset discards the simulated history of *this* process. It is the reason a paper result
        must never be quoted without its account id and start time: a curve can be restarted, and a
        restart that looked like a recovery would otherwise be indistinguishable from one.
        """
        starting = Decimal(str(platform.engine.account.starting_cash))
        platform.loop.stop()
        platform.engine.reset()
        return {
            "reset": True,
            "simulated": True,
            "environment": "PAPER",
            "starting_cash": str(starting),
            "account": platform.engine.snapshot().to_dict(),
        }
