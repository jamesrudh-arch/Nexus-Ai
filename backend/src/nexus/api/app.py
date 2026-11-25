"""FastAPI application factory.

Endpoints (Phase 2):
  GET  /healthz          liveness
  GET  /readyz           readiness (audit store writable, config valid)
  GET  /v1/status        environment, halt, live authority, phase gate — the truth view
  GET  /v1/audit/verify  hash-chain verification result and head
  GET  /metrics          Prometheus exposition
  POST /v1/halt          engage emergency halt (owner-authenticated)
  POST /v1/halt/release  release halt (owner-authenticated, step-up)

Owner authentication in Phase 2 is a bearer token resolved through the secrets provider;
no secret is ever accepted as a query parameter or logged.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus import PHASE_GATE, __phase__, __version__
from nexus.audit.log import AuditLog
from nexus.core.config import Settings, get_settings
from nexus.core.environment import EnvironmentState
from nexus.core.ids import iso_utc, utc_now
from nexus.execution.halt import HaltManager, HaltScope
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
) -> FastAPI:
    """Build the API with explicit dependencies (testable, no global state required)."""
    cfg = settings or get_settings()
    audit_log = audit or AuditLog(store=_default_store(cfg))
    halt_manager = halt or HaltManager(audit=audit_log)

    app = FastAPI(
        title="NEXUS Core API",
        version=__version__,
        summary="Phase 2 core foundation. Live trading disabled; no venue adapters.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = cfg
    app.state.audit = audit_log
    app.state.halt = halt_manager

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
            "venue_adapters": [],
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
    """SQLite audit store under ./data by default; in-memory for tests via env override."""
    import os

    from nexus.audit.log import InMemoryAuditStore, SqliteAuditStore

    if os.environ.get("NEXUS_AUDIT_BACKEND", "sqlite").lower() == "memory":
        return InMemoryAuditStore()
    url = cfg.database_url
    if url.startswith("sqlite:///"):
        return SqliteAuditStore(url.removeprefix("sqlite:///"))
    return InMemoryAuditStore()
