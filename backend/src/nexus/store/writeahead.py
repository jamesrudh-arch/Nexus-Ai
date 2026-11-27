"""Audit-first writes and the projector registry (law L-2).

The ordering rule: **the audit entry commits first, the operational projection second.** A crash
between the two leaves a record in the chain with no row beside it — a hole that boot recovery can
see and fill, because :func:`reproject_missing` compares the chain against ``op_projection``. The
opposite order (row first, audit second) would leave state nobody can explain, which is the failure
mode this system is built never to have.

Anything written through :func:`write_with_audit` is therefore recoverable by construction, and any
event type with a projector here can be re-applied from the chain alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nexus.audit.chain import AuditRecord
from nexus.core.ids import iso_utc, utc_now
from nexus.execution.orders import OrderState
from nexus.store.operational import OperationalStore

__all__ = ["PROJECTABLE", "project", "reproject_missing", "write_with_audit"]

#: Event types that have an operational projection, and the entity table each one lands in.
PROJECTABLE: dict[str, str] = {
    "halt.engage": "halt_event",
    "halt.release": "halt_event",
    "execution.accepted": "execution_result",
    "execution.refused": "execution_result",
    "execution.idempotent_replay": "execution_result",
    "decision.recorded": "decision",
    "intent.created": "trade_intent",
    "approval.granted": "approval",
    "instrument.registered": "instrument",
    "evidence.recorded": "evidence_ref",
    "dossier.opened": "dossier",
    "memory.recorded": "memory_item",
    "fill.recorded": "fills",
    "order.state": "orders",
    "risk.limit_change": "risk_limit_change",
}


def write_with_audit(
    *,
    audit: Any,
    store: OperationalStore,
    event_type: str,
    payload: Mapping[str, Any],
    actor: str | None = None,
) -> AuditRecord:
    """Persist ``payload`` durably: audit entry first, projection second (L-2).

    The acknowledgement (the returned record) happens only after both writes are committed. If the
    projection fails, the exception propagates to the caller — the audit entry is already durable,
    so :func:`reproject_missing` finishes the job at the next boot instead of losing it.
    """
    entry: AuditRecord = audit.record(event_type, dict(payload), actor=actor)
    project(store, event_type, dict(payload), audit_ref=entry.record_id)
    return entry


def project(
    store: OperationalStore,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    audit_ref: str | None,
) -> bool:
    """Apply one audited event to the operational tables. True when it was projectable."""
    if event_type not in PROJECTABLE:
        return False
    if event_type in ("halt.engage", "halt.release"):
        _project_halt(store, event_type, payload, audit_ref=audit_ref)
    elif event_type.startswith("execution."):
        store.save_execution_result(payload, audit_ref=audit_ref)
    elif event_type == "decision.recorded":
        store.save_decision_payload(payload, audit_ref=audit_ref)
    elif event_type == "intent.created":
        store.save_intent_payload(payload, audit_ref=audit_ref)
    elif event_type == "approval.granted":
        store.save_approval_payload(payload, audit_ref=audit_ref)
    elif event_type == "instrument.registered":
        _project_instrument(store, payload, audit_ref=audit_ref)
    elif event_type == "evidence.recorded":
        store.save_evidence_ref(payload, audit_ref=audit_ref)
    elif event_type == "dossier.opened":
        store.save_dossier(payload, audit_ref=audit_ref)
    elif event_type == "memory.recorded":
        store.save_memory_item(payload, audit_ref=audit_ref)
    elif event_type == "fill.recorded":
        store.save_fill(payload, audit_ref=audit_ref)
    elif event_type == "risk.limit_change":
        store.save_limit_change(payload, audit_ref=audit_ref)
    elif event_type == "order.state":
        _project_order(store, payload, audit_ref=audit_ref)
    return True


def _project_instrument(
    store: OperationalStore, payload: Mapping[str, Any], *, audit_ref: str | None
) -> None:
    """One event, two tables: the instrument, and how it is traded on each of its venues.

    ``op_projection`` is keyed on ``audit_ref`` alone, so a projection that writes several rows must
    declare itself complete only after the last of them commits. Handing ``audit_ref`` to each save
    would mark the event done the moment the instrument row landed, and a crash before the mappings
    were written would leave a hole boot recovery believes is filled — the exact failure L-2 exists to
    prevent. The saves therefore run unmarked and one :meth:`mark_projected` follows them.
    """
    instrument_id = str(payload.get("instrument_id") or "")
    store.save_instrument(payload, audit_ref=None)
    for mapping in payload.get("mappings") or ():
        row = dict(mapping)
        row["instrument_id"] = instrument_id
        store.save_venue_mapping(row, audit_ref=None)
    if audit_ref:
        store.mark_projected(
            audit_ref,
            event_type="instrument.registered",
            entity_type="instrument",
            entity_id=instrument_id,
        )


def reproject_missing(*, audit: Any, store: OperationalStore) -> tuple[str, ...]:
    """Finish any audited write whose projection is missing. Returns the record ids re-applied."""
    done = store.projected_refs()
    reapplied: list[str] = []
    for record in audit.records():
        if record.record_id in done or record.event_type not in PROJECTABLE:
            continue
        if project(store, record.event_type, record.payload, audit_ref=record.record_id):
            reapplied.append(record.record_id)
    return tuple(reapplied)


# ---------------------------------------------------------------- projectors


def _project_halt(
    store: OperationalStore,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    audit_ref: str | None,
) -> None:
    action = "ENGAGE" if event_type == "halt.engage" else "RELEASE"
    stated = str(payload.get("action") or action)
    # A release carries an empty HaltState (scope NONE, no reason); the human reason is in the note.
    reason = str(payload.get("reason") or payload.get("note") or "")
    store.save_halt_event(
        action=stated if stated in ("ENGAGE", "RELEASE") else action,
        scope=str(payload.get("scope") or "NONE"),
        reason=reason,
        triggered_by=str(payload.get("triggered_by") or "SYSTEM"),
        at=str(payload.get("since") or payload.get("at") or iso_utc(utc_now())),
        incident_id=payload.get("incident_id"),
        affected_accounts=tuple(str(item) for item in payload.get("affected_accounts") or ()),
        affected_instruments=tuple(str(item) for item in payload.get("affected_instruments") or ()),
        cancel_working_orders=bool(payload.get("cancel_working_orders", True)),
        audit_ref=audit_ref,
    )


def _project_order(
    store: OperationalStore,
    payload: Mapping[str, Any],
    *,
    audit_ref: str | None,
) -> None:
    order_id = str(payload.get("order_id") or "")
    if not order_id:
        return
    state = str(payload.get("state") or payload.get("order_state") or OrderState.DRAFT.value)
    if store.get_order(order_id) is None:
        store.save_order(
            order_id=order_id,
            venue=str(payload.get("venue") or ""),
            account_id=str(payload.get("account_id") or ""),
            state=state,
            idempotency_key=str(payload.get("idempotency_key") or order_id),
            intent_id=payload.get("intent_id"),
            venue_order_id=payload.get("venue_order_id"),
            submitted_at=payload.get("submitted_at"),
            reject_reason=payload.get("reject_reason") or payload.get("reason"),
            audit_ref=audit_ref,
        )
        return
    store.update_order_state(
        order_id,
        state,
        reason=str(payload.get("reject_reason") or payload.get("reason") or ""),
        at=payload.get("at"),
        audit_ref=audit_ref,
    )
