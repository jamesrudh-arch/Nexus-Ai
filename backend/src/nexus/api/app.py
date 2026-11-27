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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus import DATA_SOURCES, PHASE_GATE, __phase__, __version__
from nexus.audit.log import AuditLog
from nexus.core.config import Settings, get_settings
from nexus.core.environment import EnvironmentState
from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.domain.decision import DecisionVerb
from nexus.execution.halt import HaltManager, HaltScope
from nexus.instruments.projection import MasterProjection, project_master
from nexus.instruments.registry import InstrumentRegistry, UnknownInstrument, coverage_report
from nexus.instruments.seed import seed_master
from nexus.instruments.sessions import MarketCalendar
from nexus.intelligence.dossier import (
    DOSSIER_EVENT_TYPE,
    VENUE_MAPS_INSTRUMENT_KEY,
    sufficiency_of,
)
from nexus.intelligence.evidence import verify_evidence_checksum
from nexus.observability.metrics import (
    observe_api_request,
    render_metrics,
    set_environment_state,
    set_halt_active,
)
from nexus.risk.authority import evaluate_authority
from nexus.secrets.provider import SecretNotFoundError, get_secret_provider
from nexus.store.operational import SqliteOperationalStore
from nexus.store.recovery import (
    BootRecoveryReport,
    indeterminate_halt_state,
    recover,
)

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
    store: Any = None,
    seed: bool = True,
) -> FastAPI:
    """Build the API with explicit dependencies (testable, no global state required).

    ``archive`` is optional: with no archive the Phase 3 routes report that nothing has been
    stored yet rather than an empty dataset, because "no archive" and "archive holds nothing"
    are different facts. That answer is honest; it invents nothing.

    ``registry`` is optional too, and since Stage 7.3 (lever L-C) an absent registry is **seeded**
    rather than left empty: :func:`nexus.instruments.seed.seed_master` writes down the instruments
    whose live evidence exists, each at the rank that evidence supports and no higher, so the
    coverage routes report what has actually been proven instead of ``total=0`` (finding F-3).
    Pass ``seed=False`` to boot an empty master. An **injected** registry is never seeded — what a
    caller built is what the app serves, so a test fixture stays a test fixture.

    Since Stage 8.2 (lever L-B) a seeded master is also **projected** into the system of record, and for
    the same reason it is the only thing that gets projected: the app owns what it seeded. Before this,
    the three seeded instruments existed only in the registry — ``/v1/status`` reported
    ``instrument_master.count = 3`` beside ``persistence.counts.instrument = 0``, because the projector
    for ``instrument.registered`` existed and nothing emitted the event (finding F-16). The projection is
    idempotent at every boot and appends to the audit chain only for an instrument that actually
    changed, so a restart does not grow the chain by three records. An injected registry is not
    projected, exactly as it is not seeded — a test fixture stays a test fixture.
    """
    cfg = settings or get_settings()
    audit_log = audit or AuditLog(store=_default_store(cfg))
    op_store = store if store is not None else _default_operational_store(cfg, audit_log)

    # Stage 6 boot sequence (laws L-1, L-2, L-6): verify the chain, finish audited writes whose
    # projection never landed, re-derive the halt, resolve orders left non-terminal.
    recovery, boot_error = _boot_recovery(audit_log, op_store)
    restored = recovery.halt_state if recovery is not None else None
    if boot_error is not None:
        # Nothing derived from an untrusted chain can be believed — including the absence of a
        # halt. Fail closed into the kill switch instead of serving (L-6).
        restored = indeterminate_halt_state(
            f"boot recovery could not complete ({boot_error.reason.value}): failing closed"
        )
    halt_manager = halt or HaltManager(audit=audit_log, store=op_store, restored_state=restored)
    if halt is not None and restored is not None and restored.active and not halt_manager.active:
        # An injected manager must still honour a durable halt: re-engage at the recovered scope.
        halt_manager.engage(
            scope=restored.scope,
            reason=restored.reason or "boot recovery: durable halt re-applied",
            triggered_by=restored.triggered_by,
            affected_accounts=restored.affected_accounts,
            affected_instruments=restored.affected_instruments,
        )
    master_projection: MasterProjection | None = None
    if registry is None:
        instrument_registry = InstrumentRegistry()
        if seed:
            # Idempotent, offline and recorded: every rung it claims carries the evidence label
            # naming the runs that proved it, and nothing seeded here becomes active (D-002).
            seed_master(instrument_registry)
            # A boot that cannot write the master into the system of record does not serve: the
            # intelligence memory references instruments by id, and a row pointing at an instrument the
            # store has never held is the failure migration 0004's foreign key exists to refuse.
            master_projection = project_master(instrument_registry, audit=audit_log, store=op_store)
    else:
        instrument_registry = registry
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
    app.state.store = op_store
    app.state.master_projection = master_projection
    app.state.recovery = recovery
    app.state.boot_error = boot_error

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
        if boot_error is not None:
            problems.append(f"boot recovery refused: {boot_error.reason.value}")
        if recovery is not None:
            if recovery.halt_indeterminate:
                problems.append("halt state indeterminate at boot: failing closed")
            if recovery.orders_marked_unknown:
                problems.append(
                    f"{len(recovery.orders_marked_unknown)} order(s) UNKNOWN pending reconciliation"
                )
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
                # How many of them the system of record actually holds. This pair is the observable
                # F-16 was found by (3 beside 0); reporting only the registry side would have left the
                # fix invisible in the one place the defect was visible.
                "projected": _projected_instruments(op_store),
            },
            "archive": {"configured": archive is not None},
            "persistence": _persistence_status(op_store, recovery, boot_error),
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

    @app.get("/v1/intelligence/dossiers", tags=["intelligence"])
    def list_dossiers(
        instrument_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        evidence: bool = True,
    ) -> dict[str, Any]:
        """The research dossiers, newest first — and what the approved view asks for that cannot be served.

        Read-only by construction: there is no write verb in this module. A dossier is opened by
        :func:`nexus.intelligence.open_dossier`, audited as ``dossier.opened``; the audit chain is the
        record and this serves its projection, so ``served_from`` says so rather than letting a reader
        assume the row is the original.

        ``view_gaps`` is part of the response, not a comment in the source. ``docs/03`` J-04 and
        ``docs/10`` §3.1 fix what the Intelligence Centre's dossier view must show, and several of those
        elements have no column to come from. A route that served what it can and stayed silent about the
        rest would render as complete, which is the failure ``/v1/data/coverage`` was written to avoid
        when it distinguished "no archive" from "archive holds nothing". The same distinction is kept
        here: ``empty`` is not ``None`` when there are no dossiers, and it says why.
        """
        rows = op_store.dossiers(instrument_id=instrument_id, limit=limit)
        dossiers = [_dossier_view(op_store, row, with_evidence=evidence) for row in rows]
        return {
            "count": len(dossiers),
            "dossiers": dossiers,
            "served_from": "operational projection of the audit chain (R-1); the chain is the record",
            "vocabularies": DOSSIER_VOCABULARIES,
            "empty": None if dossiers else _no_dossiers_yet(instrument_id),
            "view_gaps": DOSSIER_VIEW_GAPS,
            "note": (
                "a stance is a research disposition and never a trade signal — docs/03 J-04's exit "
                "condition is 'Research completion ≠ trade signal', and live authority is DENIED"
            ),
        }

    @app.get("/v1/intelligence/dossiers/{dossier_id}", tags=["intelligence"])
    def dossier_detail(dossier_id: str) -> dict[str, Any]:
        """One case, which is what ``docs/03`` J-04 step 1 selects. 404 when the id is unknown.

        A 404 and not an empty 200: an unknown id is a caller error, and answering it with a successful
        empty body would make a typo indistinguishable from a case that was opened and holds nothing.
        """
        row = op_store.get_dossier(dossier_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown dossier: {dossier_id}",
            )
        return {
            "dossier": _dossier_view(op_store, row, with_evidence=True),
            "served_from": "operational projection of the audit chain (R-1); the chain is the record",
            "vocabularies": DOSSIER_VOCABULARIES,
            "view_gaps": DOSSIER_VIEW_GAPS,
        }

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


#: What the approved dossier view asks for that this route cannot serve, and why. Each element names the
#: document that asks for it, so the gap is a recorded fact rather than an absence nobody mentioned.
DOSSIER_VIEW_GAPS: tuple[dict[str, Any], ...] = (
    {
        "element": "contradictions highlighted and linked",
        "asked_by": "docs/10 §3.1 (dossier view); docs/03 J-04 step 4",
        "why_not_servable": (
            "needs evidence_ref.contradicts, and no such column exists. Nothing can be highlighted "
            "because nothing records that two sources disagree"
        ),
        "deferred_by": "D-051 — F-18's cheap half deferred to the stage-10 memory_item writer",
    },
    {
        "element": "counter-thesis",
        "asked_by": "docs/03 J-04 step 1; docs/10 §3.1",
        "why_not_servable": (
            "no column. dossier.uncertainty is served and is the nearest thing, but 'what is unresolved' "
            "is not 'the case against', and this route does not present one as the other"
        ),
        "deferred_by": None,
    },
    {
        "element": "publication time in the evidence table",
        "asked_by": "docs/03 J-04 step 2 ('source, publication time, observation time')",
        "why_not_servable": (
            "evidence_ref holds observed_at (the venue's stamp) and retrieved_at (our clock at receipt). "
            "A source's own publication moment has no column, so the first of J-04's three times is not "
            "recordable. Stage 8.4 closed F-14 by giving all four adapters a real receipt time, and that "
            "does not reach this gap: a receipt time says when we got it, not when the source published "
            "it, so J-04's first time is exactly as unrecordable as it was"
        ),
        "deferred_by": "D-051 scheduled this gap's batch as Stage 8.4, and 8.4 has now landed without "
        "filling it — its ruling scoped it to F-14's expensive half alone, with no new tables, no new "
        "columns and no writer wiring, so no third timestamp arrived with it. Nothing is scheduled for "
        "this gap now",
    },
    {
        "element": "research depth Tier 0–4",
        "asked_by": "docs/03 §7; docs/10 §3.1 (attention priorities)",
        "why_not_servable": "no column, and no tier is defined anywhere in the repository",
        "deferred_by": None,
    },
    {
        "element": "freshness",
        "asked_by": "docs/03 J-04 step 4; docs/10 §3.1",
        "why_not_servable": (
            "partly served, and the part that is not matters: each evidence row's data_status is what its "
            "writer was told when the row was recorded, and nothing re-evaluates it against the current "
            "clock. A row recorded LIVE stays LIVE in the projection forever, so serving that column as "
            "'freshness' without this qualification would be misleading"
        ),
        "deferred_by": None,
    },
    {
        "element": "quant result with run id",
        "asked_by": "docs/10 §3.1",
        "why_not_servable": (
            "the run id is served — every dossier and every evidence row carries audit_ref, which is the "
            "link into the audit chain. No quantitative result is computed anywhere in src/, so there is "
            "nothing to attach it to"
        ),
        "deferred_by": None,
    },
    {
        "element": "knowledge-sufficiency meter",
        "asked_by": "docs/10 §3.1 (context rail: 'meter with stated basis and what it is sufficient for')",
        "why_not_servable": (
            "the basis and the target are served as strings; the meter is not. docs/15 §6's L-E is "
            "explicit that sufficiency stays a string until stage 10 defines the meter, and inventing a "
            "scale here would put a number in front of a judgement this system cannot yet make"
        ),
        "deferred_by": "stage 10",
    },
    {
        "element": "beliefs with confidence band, validity interval and change conditions",
        "asked_by": "docs/03 §7; docs/10 §3.1",
        "why_not_servable": (
            "that is memory_item, which is schema-only: it has no writer, and F-18's valid_from, "
            "valid_until and change_conditions columns do not exist yet"
        ),
        "deferred_by": "D-051 — deferred to the stage-10 memory_item writer",
    },
    {
        "element": "disposition with reason code",
        "asked_by": "docs/10 §3.1",
        "why_not_servable": (
            "the disposition is served as stance, but dossier has no reason-code column. Reason codes "
            "live on DecisionRecord, and a dossier is not a decision"
        ),
        "deferred_by": None,
    },
)

#: Which words a dossier's fields are allowed to hold, and where each vocabulary comes from. ``None``
#: means nothing in the repository declares one, which is itself the answer a reader needs.
DOSSIER_VOCABULARIES: dict[str, dict[str, Any]] = {
    "stance": {
        "values": [member.value for member in DecisionVerb],
        "source": "domain/decision.py DecisionVerb — the schema default 'ABSTAIN' is a member, and "
        "docs/03 §7 with docs/10 §3.1 name this vocabulary for the intelligence layer's disposition",
        "enforced_by": "the writer (intelligence/dossier.py); the column is TEXT and the schema does not",
    },
    "sufficiency": {
        "values": None,
        "source": "none declared anywhere. The schema says only DEFAULT 'INSUFFICIENT', and docs/15 §6's "
        "L-E keeps it a string until stage 10 defines the meter. A numeric value is refused by the "
        "writer, because docs/12 §1.3's law is that no gate can be satisfied by a confidence value",
        "enforced_by": "the writer refuses a number and refuses a claim above INSUFFICIENT with no basis "
        "or no target",
    },
    "state": {
        "values": None,
        "source": "the schema default 'DRAFT' is the only value declared anywhere",
        "enforced_by": "nothing — free text, passed through",
    },
}


def _no_dossiers_yet(instrument_id: str | None) -> dict[str, Any]:
    """What an empty dossier list means, which is not the same as the list being empty."""
    scope = "for this instrument" if instrument_id else "at all"
    return {
        "meaning": f"no dossier has been opened {scope}",
        "writer": f"nexus.intelligence.open_dossier exists since Stage 8.3 and is audited as "
        f"{DOSSIER_EVENT_TYPE}",
        "callers": "none yet — nothing in src/ opens a dossier, which is the same limitation Stage 8.2 "
        "recorded for record_evidence. The writer is built and unwired on purpose: wiring it means "
        "deciding what the system should research, and that is not this batch's ruling",
        "not_a_fault": "the route works and the table exists; an empty list here is an honest empty, the "
        "distinction /v1/data/coverage draws between 'no archive' and 'archive holds nothing'",
    }


def _verified(evidence: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """Each evidence row with its checksum recomputed. ``None`` in a stored checksum verifies False."""
    return [{"checksum_ok": verify_evidence_checksum(item)} for item in evidence]


def _dossier_view(store: Any, row: dict[str, Any], *, with_evidence: bool) -> dict[str, Any]:
    """One dossier as the view serves it: the columns, the pinned payload keys lifted out, the chronology.

    Evidence is ordered oldest first here even though ``store.evidence_refs`` returns newest first,
    because ``docs/10`` §3.1 asks the dossier view for a *chronology* and a chronology runs forwards.
    """
    payload = row.get("payload")
    body: dict[str, Any] = payload if isinstance(payload, dict) else {}
    sufficiency = sufficiency_of(row)
    evidence = store.evidence_refs(dossier_id=str(row.get("dossier_id")))
    chronology = [
        {
            "evidence_id": item.get("evidence_id"),
            "source": item.get("source"),
            "kind": item.get("kind"),
            "observed_at": item.get("observed_at"),
            "retrieved_at": item.get("retrieved_at"),
            "observed_at_source": (item.get("payload") or {}).get("observed_at_source"),
            "apparent_latency_seconds": (item.get("payload") or {}).get("apparent_latency_seconds"),
            "data_status": item.get("data_status"),
            "locator": item.get("locator"),
            "checksum": item.get("checksum"),
            # Recomputed here from the row rather than trusted: the checksum covers nine stored fields
            # (F-21), so this is the first place in the system where an evidence row's integrity is
            # actually checked instead of merely recorded.
            "checksum_ok": verify_evidence_checksum(item),
            "audit_ref": item.get("audit_ref"),
        }
        for item in sorted(
            evidence, key=lambda item: (str(item.get("retrieved_at")), str(item.get("evidence_id")))
        )
    ]
    return {
        "dossier_id": row.get("dossier_id"),
        "instrument_id": row.get("instrument_id"),
        "venue": row.get("venue"),
        VENUE_MAPS_INSTRUMENT_KEY: body.get(VENUE_MAPS_INSTRUMENT_KEY),
        "state": row.get("state"),
        "stance": row.get("stance"),
        "summary": row.get("summary"),
        "uncertainty": row.get("uncertainty"),
        **sufficiency,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "audit_ref": row.get("audit_ref"),
        "evidence_count": len(evidence),
        "evidence_checksums_verify": (
            None if not evidence else all(entry["checksum_ok"] for entry in _verified(evidence))
        ),
        "chronology": chronology if with_evidence else None,
        "payload": body,
    }


def _default_operational_store(cfg: Settings, audit_log: AuditLog) -> Any:
    """Operational state, on the same footing as the audit chain (R-1 / D-042).

    R-1 makes SQLite the single-node system of record for governance *and* operational state, with
    market time series in the Parquet archive — so by default this is the same file the audit chain
    lives in. When the caller explicitly chose an ephemeral audit log (``NEXUS_AUDIT_BACKEND=memory``
    or an injected in-memory store) the operational store is ephemeral too: a durable operational
    state next to a volatile record of why it changed would be worse than either choice alone.
    """
    import os

    from nexus.audit.log import InMemoryAuditStore

    ephemeral = os.environ.get("NEXUS_AUDIT_BACKEND", "sqlite").lower() == "memory" or isinstance(
        audit_log.store, InMemoryAuditStore
    )
    if ephemeral:
        return SqliteOperationalStore(":memory:", audit=audit_log)
    url = cfg.database_url
    if url.startswith("sqlite:///"):
        return SqliteOperationalStore(url.removeprefix("sqlite:///"), audit=audit_log)
    # _default_store() already refuses a non-sqlite scheme; this branch is only reachable when an
    # audit store was injected for a backend this build does not implement. Stay ephemeral rather
    # than invent a file location for it.
    return SqliteOperationalStore(":memory:", audit=audit_log)


def _boot_recovery(audit_log: AuditLog, op_store: Any) -> tuple[BootRecoveryReport | None, NexusError | None]:
    """Run boot recovery, converting a refusal into state the endpoints can report honestly."""
    try:
        return recover(audit=audit_log, store=op_store), None
    except NexusError as exc:
        return None, exc


def _projected_instruments(op_store: Any) -> int | str:
    """Instrument rows in the system of record, or the reason there are none to count."""
    try:
        return int(op_store.counts().get("instrument", 0))
    except NexusError as exc:
        return exc.reason.value


def _persistence_status(
    op_store: Any,
    recovery: BootRecoveryReport | None,
    boot_error: NexusError | None,
) -> dict[str, Any]:
    """What the system of record is, and what boot recovery found (A-06: status on the wire)."""
    migrations = getattr(op_store, "migrations", None)
    try:
        counts: dict[str, Any] = op_store.counts()
    except NexusError as exc:
        counts = {"error": exc.reason.value}
    path = getattr(op_store, "path", None)
    return {
        "engine": "sqlite",
        "role": "system of record for governance + operational state (R-1 / D-042)",
        "time_series": "parquet+zstd archive under the D-024 retention ladder",
        "path": None if path in (None, ":memory:") else str(path),
        "ephemeral": path == ":memory:",
        "migrations": migrations.to_dict() if migrations is not None else None,
        "counts": counts,
        "boot_recovery": recovery.to_dict() if recovery is not None else None,
        "boot_error": None
        if boot_error is None
        else {"reason": boot_error.reason.value, "detail": boot_error.detail},
    }


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
