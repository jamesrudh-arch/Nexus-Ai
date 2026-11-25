"""FastAPI application factory.

Endpoints (Phase 2):
  GET  /healthz          liveness
  GET  /readyz           readiness (audit store writable, config valid)
  GET  /v1/status        environment, halt, live authority, phase gate — the truth view
  GET  /v1/audit/verify  hash-chain verification result and head
  GET  /metrics          Prometheus exposition
  POST /v1/halt          engage emergency halt (owner-authenticated)
  POST /v1/halt/release  release halt (owner-authenticated, step-up)

Endpoints added in Phase 3 (market data + instrument master):
  GET  /v1/instruments              the canonical master with per-venue certification states
  GET  /v1/instruments/coverage     what is proven ready, and what is missing
  GET  /v1/instruments/{id}/session whether that instrument should be trading right now
  GET  /v1/data/coverage            what the archive actually holds, per resolution tier

The Phase 3 routes are **read-only**. There is still no endpoint that can place, amend or
cancel an order, and none that accepts a venue credential.

Owner authentication is a bearer token resolved through the secrets provider; no secret is
ever accepted as a query parameter or logged.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus import DATA_SOURCES, PHASE_GATE, __phase__, __version__
from nexus.audit.log import AuditLog
from nexus.core.config import Settings, get_settings
from nexus.core.environment import EnvironmentState
from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.execution.halt import HaltManager, HaltScope
from nexus.instruments.registry import InstrumentRegistry, UnknownInstrument, coverage_report
from nexus.instruments.sessions import MarketCalendar
from nexus.observability.metrics import (
    observe_api_request,
    render_metrics,
    set_environment_state,
    set_halt_active,
)
from nexus.risk.authority import evaluate_authority
from nexus.secrets.provider import SecretNotFoundError, get_secret_provider

# Starlette removed the public ``RequestResponseEndpoint`` alias, so the middleware
# callable is typed locally. Keeping it explicit preserves strict-mypy coverage of the
# request-counting middleware without depending on a private symbol.
RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class HaltRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200)
    scope: HaltScope = HaltScope.NEW_ENTRIES
    affected_accounts: tuple[str, ...] = ()
    affected_instruments: tuple[str, ...] = ()


class HaltReleaseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


def _require_owner(authorization: str | None = Header(default=None)) -> str:
    """Validate the owner bearer token in constant time. 401 on any mismatch."""
    provider = get_secret_provider()
    try:
        expected = provider.get("owner/api-token")
    except SecretNotFoundError:
        # No token configured: refuse rather than allow unauthenticated control actions.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="owner authentication is not configured; control endpoints are disabled",
        ) from None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    supplied = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return "OWNER"


def create_app(
    *,
    settings: Settings | None = None,
    audit: AuditLog | None = None,
    halt: HaltManager | None = None,
    registry: InstrumentRegistry | None = None,
    calendar: MarketCalendar | None = None,
    archive: Any = None,
) -> FastAPI:
    """Build the API with explicit dependencies (testable, no global state required).

    ``registry`` and ``archive`` are optional: with no registry the Phase 3 routes report an
    empty master rather than failing, and with no archive they report that nothing has been
    stored yet. Both answers are honest; neither invents data.
    """
    cfg = settings or get_settings()
    audit_log = audit or AuditLog(store=_default_store(cfg))
    halt_manager = halt or HaltManager(audit=audit_log)
    instrument_registry = registry or InstrumentRegistry()
    market_calendar = calendar or MarketCalendar()

    app = FastAPI(
        title="NEXUS Core API",
        version=__version__,
        summary="Phase 3 core + market data. Live trading disabled; no venue adapters.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = cfg
    app.state.audit = audit_log
    app.state.halt = halt_manager
    app.state.registry = instrument_registry
    app.state.calendar = market_calendar
    app.state.archive = archive

    @app.middleware("http")
    async def _count_requests(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)
        observe_api_request(request.url.path, response.status_code)
        return response

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "phase": __phase__, "time": iso_utc(utc_now())}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> JSONResponse:
        problems: list[str] = []
        try:
            audit_log.record("health.readiness_probe", {"at": iso_utc(utc_now())})
        except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
            problems.append(f"audit store unwritable: {type(exc).__name__}")
        if cfg.environment not in set(EnvironmentState):
            problems.append("environment state invalid")
        ready = not problems
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"ready": ready, "problems": problems, "environment": cfg.environment.name},
        )

    @app.get("/v1/status", tags=["status"])
    def get_status() -> dict[str, Any]:
        authority = evaluate_authority(
            cfg,
            halt_active=halt_manager.state.blocks_new_entries(),
            kill_switch_active=halt_manager.state.blocks_all_trading(),
            phase_gate_complete=False,  # Phase 2: Phases 0-9 are not complete
            venue_live_verified=False,
            mandate_active=False,
        )
        set_environment_state(int(cfg.environment))
        set_halt_active(halt_manager.state.scope.value, halt_manager.state.active)
        return {
            "app": {"name": cfg.app_name, "version": __version__, "phase": __phase__},
            "phase_gate": PHASE_GATE,
            "environment": cfg.environment.name,
            "time_utc": iso_utc(utc_now()),
            "halt": halt_manager.state.to_dict(),
            "live_authority": authority.to_dict(),
            "risk_limits_provisional": True,  # O-002: exact numbers pending Risk Policy
            "cost_constraint": "D-019 zero-cost: free tools/APIs/data only",
            "alert_channels": {
                "in_app": cfg.alerts.in_app_enabled,
                "telegram": cfg.alerts.telegram_enabled,
                "web_push": cfg.alerts.webpush_enabled,
                "email": cfg.alerts.email_enabled,
                "sms": False,  # BLOCKED by D-019 (O-006)
                "whatsapp": False,  # BLOCKED by D-019 (O-006)
            },
            "venue_adapters": [],  # trading adapters: none exist in Phase 3
            "market_data_sources": {
                "enabled": bool(DATA_SOURCES),
                "sources": list(DATA_SOURCES),
                "authenticated": False,
                "read_only": True,
                "order_capable": False,
                "cost_usd": 0,
            },
            "instrument_master": {
                "count": len(instrument_registry),
                "active": len(instrument_registry.active()),
            },
            "archive": {"configured": archive is not None},
        }

    @app.get("/v1/audit/verify", tags=["audit"])
    def verify_audit() -> dict[str, Any]:
        breaks = audit_log.verify()
        return {
            "records": audit_log.length,
            "chain_head": audit_log.chain_head,
            "intact": not breaks,
            "breaks": [{"seq": b.seq, "record_id": b.record_id, "reason": b.reason} for b in breaks],
        }

    @app.post("/v1/halt", tags=["control"], status_code=status.HTTP_200_OK)
    def engage_halt(
        payload: HaltRequest,
        owner: str = Depends(_require_owner),
    ) -> dict[str, Any]:
        state = halt_manager.engage(
            scope=payload.scope,
            reason=payload.reason,
            triggered_by=owner,
            affected_accounts=payload.affected_accounts,
            affected_instruments=payload.affected_instruments,
        )
        return {"engaged": True, "halt": state.to_dict()}

    @app.post("/v1/halt/release", tags=["control"])
    def release_halt(
        payload: HaltReleaseRequest,
        owner: str = Depends(_require_owner),
    ) -> dict[str, Any]:
        state = halt_manager.release(reason=payload.reason, released_by=owner)
        return {"released": True, "halt": state.to_dict()}

    @app.get("/v1/instruments", tags=["instruments"])
    def list_instruments() -> dict[str, Any]:
        """The canonical master: one economic instrument, many venue representations."""
        return instrument_registry.snapshot().to_dict()

    @app.get("/v1/instruments/coverage", tags=["instruments"])
    def instrument_coverage() -> dict[str, Any]:
        """What is proven ready for research / paper / live, and what is still missing.

        Readiness follows certification, never enthusiasm: an instrument appears under
        ``ready_for_live`` only when a venue mapping has reached LIVE_VERIFIED.
        """
        report = coverage_report(instrument_registry)
        return {
            **report.to_dict(),
            "live_trading_enabled": False,  # Phase 3: structurally impossible
            "note": "readiness_for_live describes certification only; live authority is DENIED",
        }

    @app.get("/v1/instruments/{instrument_id}/session", tags=["instruments"])
    def instrument_session(instrument_id: str, exchange: str | None = None) -> dict[str, Any]:
        """Whether this instrument should be trading right now, and how sure we are.

        ``confidence`` matters as much as ``is_open``: a PARTIAL answer means the weekday rule
        is known but the holiday list is not, so weekend/holiday silence is expected while a
        midweek gap is not.
        """
        try:
            instrument = instrument_registry.require(instrument_id)
        except UnknownInstrument:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown instrument: {instrument_id}",
            ) from None
        resolved_exchange = exchange or (instrument.mappings[0].venue.value if instrument.mappings else None)
        session = market_calendar.status(
            instrument_id=instrument.instrument_id,
            asset_class=instrument.asset_class,
            exchange=resolved_exchange,
            now=utc_now(),
        )
        return session.to_dict()

    @app.get("/v1/data/coverage", tags=["data"])
    def data_coverage() -> dict[str, Any]:
        """What the first-party archive actually holds — never what was requested.

        Without an archive configured this reports ``configured: false`` rather than an empty
        dataset, because "no archive" and "archive holds nothing" are different facts.
        """
        if archive is None:
            return {
                "configured": False,
                "files": 0,
                "bytes": 0,
                "partitions": {},
                "note": "no archive configured; nothing has been persisted",
            }
        manifest = archive.manifest()
        return {
            "configured": True,
            **manifest,
            "retention_policy": "D-024 tiered: ticks 30d, 1m bars 12mo, 5m/daily indefinite",
            "coverage_is_honest": "partitions list what exists; absence means no data, not a query failure",
        }

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> Response:
        return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")

    @app.exception_handler(HTTPException)
    async def _http_exc(_request: Request, exc: HTTPException) -> JSONResponse:
        # Never echo credentials back; details are already written to be safe.
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    audit_log.record(
        "api.app_created",
        {"version": __version__, "phase": __phase__, "environment": cfg.environment.name},
    )
    return app


def _default_store(cfg: Settings) -> Any:
    """SQLite audit store under ./data by default; in-memory only when explicitly asked for.

    An unrecognised ``database_url`` scheme is **refused**, not downgraded. The audit log is the
    system's evidence trail: silently substituting an in-memory store discards it on every restart
    while liveness, readiness and every health check keep reporting success. ``NatsEventBus``
    states the house rule for exactly this situation — "events are never silently discarded" — and
    the audit store is held to the same standard.

    This was reachable by following the documented configuration. `.env.example` showed
    ``postgresql+psycopg://...`` as the compose variant while no Postgres store existed, so an
    operator bringing up the stack alongside TimescaleDB got an ephemeral audit log and no error —
    the worst possible outcome for a system whose decisions must be auditable after the fact.
    Choosing memory is what ``NEXUS_AUDIT_BACKEND=memory`` is for, and it is explicit.
    """
    import os

    from nexus.audit.log import InMemoryAuditStore, SqliteAuditStore

    if os.environ.get("NEXUS_AUDIT_BACKEND", "sqlite").lower() == "memory":
        return InMemoryAuditStore()
    url = cfg.database_url
    if url.startswith("sqlite:///"):
        return SqliteAuditStore(url.removeprefix("sqlite:///"))
    # Only the scheme goes into the context. A database URL can carry a password, and the refusal
    # is persisted and surfaced in the UI, so nothing past the first colon is safe to keep.
    raise NexusError(
        RejectReason.CONFIG_INVALID,
        "NEXUS_DATABASE_URL names a scheme this build does not implement; only sqlite:/// is "
        "supported. Refusing to start rather than keeping the audit log in memory, where it would "
        "be lost on every restart while still reporting healthy. Set NEXUS_AUDIT_BACKEND=memory "
        "to choose an ephemeral audit log explicitly.",
        retryable=False,
        context={"scheme": url.split(":", 1)[0]},
    )
