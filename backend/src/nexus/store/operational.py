"""Durable operational state (Stage 6: findings F-2 and F-7, laws L-2, L-3, L-5).

Before Stage 6 the only SQL writer in the codebase was the audit log. Decisions, intents,
approvals, orders, fills, halt events, limit changes and the gateway's idempotency ledger existed
as in-memory objects, so a restart lost them: an active halt came back un-halted (F-3) and a
replayed intent could be processed twice because the ledger that refuses replays was gone (F-7).

This store closes that gap on the engine R-1 selected: SQLite, in the same file as the audit chain,
with ``WAL`` and ``synchronous=FULL``. Two laws shape the API:

* **L-2, durable before acknowledged** — every writer commits before it returns, and
  :func:`nexus.store.writeahead.write_with_audit` orders the audit entry *first*, so a crash between
  the two leaves a record that boot recovery re-projects rather than a silent hole.
* **L-5, secrets refused at the boundary** — payloads destined for a persisted column pass through
  the same :func:`nexus.audit.log.assert_no_secrets` gate the audit chain uses.

Money and quantity are stored as ``TEXT`` holding ``str(Decimal)`` and read back with
:func:`nexus.store.serialise.decimal_or_none`, which returns ``None`` rather than guessing when a
stored value cannot be parsed: a corrupted quantity must fail closed, not trade.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from nexus.audit.log import assert_no_secrets
from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionRecord
from nexus.execution.halt import HaltScope
from nexus.execution.intent import ApprovalRecord, TradeIntent
from nexus.execution.orders import OrderState, is_terminal
from nexus.store.migrations import MigrationReport, MigrationRunner
from nexus.store.serialise import decimal_or_none, dumps_canonical, loads_json

__all__ = [
    "ExecutionResultRow",
    "HaltEventRow",
    "OperationalStore",
    "OrderRow",
    "PersistenceError",
    "SqliteOperationalStore",
]


class PersistenceError(NexusError):
    """A durable read or write failed. Retryable — and never silently ignored."""

    def __init__(self, detail: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(
            RejectReason.PERSISTENCE_FAILED,
            detail,
            retryable=True,
            context=context,
        )


# ---------------------------------------------------------------- row types


@dataclass(frozen=True, slots=True)
class OrderRow:
    """One persisted order, as recovery reads it."""

    order_id: str
    venue: str
    account_id: str
    state: OrderState
    updated_at: str
    idempotency_key: str
    intent_id: str | None = None
    venue_order_id: str | None = None
    reject_reason: str | None = None
    filled_qty: Decimal | None = None
    average_price: Decimal | None = None

    @property
    def terminal(self) -> bool:
        return is_terminal(self.state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "intent_id": self.intent_id,
            "venue": self.venue,
            "account_id": self.account_id,
            "venue_order_id": self.venue_order_id,
            "state": self.state.value,
            "updated_at": self.updated_at,
            "reject_reason": self.reject_reason,
            "filled_qty": None if self.filled_qty is None else str(self.filled_qty),
            "average_price": None if self.average_price is None else str(self.average_price),
            "idempotency_key": self.idempotency_key,
            "terminal": self.terminal,
        }


@dataclass(frozen=True, slots=True)
class HaltEventRow:
    """One durable halt engagement or release."""

    halt_id: str
    seq: int
    action: str
    scope: HaltScope
    reason: str
    triggered_by: str
    at: str
    incident_id: str | None = None
    affected_accounts: tuple[str, ...] = ()
    affected_instruments: tuple[str, ...] = ()
    cancel_working_orders: bool = True
    audit_ref: str | None = None

    @property
    def engaged(self) -> bool:
        return self.action == "ENGAGE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "halt_id": self.halt_id,
            "seq": self.seq,
            "action": self.action,
            "scope": self.scope.value,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "incident_id": self.incident_id,
            "at": self.at,
            "affected_accounts": list(self.affected_accounts),
            "affected_instruments": list(self.affected_instruments),
            "cancel_working_orders": self.cancel_working_orders,
            "audit_ref": self.audit_ref,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResultRow:
    """A durable gateway result — the idempotency ledger that survives a restart (F-7)."""

    intent_id: str
    status: str
    order_state: str
    at: str
    order_id: str | None = None
    reasons: tuple[str, ...] = ()
    idempotent_replay: bool = False
    audit_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "status": self.status,
            "order_id": self.order_id,
            "order_state": self.order_state,
            "reasons": list(self.reasons),
            "idempotent_replay": self.idempotent_replay,
            "at": self.at,
            "audit_ref": self.audit_ref,
        }


# ---------------------------------------------------------------- protocol (the Postgres seam)


class OperationalStore(Protocol):
    """Storage backend for operational state.

    R-1 keeps this Protocol as the seam: a PostgreSQL implementation under trigger conditions
    T-1…T-4 satisfies the same surface, and nothing above this line changes.
    """

    migrations: MigrationReport | None

    def save_decision(self, record: DecisionRecord, *, audit_ref: str | None = None) -> None: ...

    def save_decision_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_intent(self, intent: TradeIntent, *, audit_ref: str | None = None) -> None: ...

    def save_intent_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_approval(self, approval: ApprovalRecord, *, audit_ref: str | None = None) -> None: ...

    def save_approval_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_instrument(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_venue_mapping(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_order(
        self,
        *,
        order_id: str,
        venue: str,
        account_id: str,
        state: OrderState | str,
        idempotency_key: str,
        intent_id: str | None = None,
        venue_order_id: str | None = None,
        submitted_at: str | None = None,
        updated_at: str | None = None,
        filled_qty: Decimal | str | None = None,
        average_price: Decimal | str | None = None,
        fees_quote: Decimal | str | None = None,
        funding_quote: Decimal | str | None = None,
        reject_reason: str | None = None,
        audit_ref: str | None = None,
    ) -> None: ...

    def update_order_state(
        self,
        order_id: str,
        state: OrderState | str,
        *,
        reason: str = "",
        at: str | None = None,
        audit_ref: str | None = None,
    ) -> bool: ...

    def save_fill(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_execution_result(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def save_halt_event(
        self,
        *,
        action: str,
        scope: HaltScope | str,
        reason: str,
        triggered_by: str,
        at: str,
        halt_id: str | None = None,
        incident_id: str | None = None,
        affected_accounts: Sequence[str] = (),
        affected_instruments: Sequence[str] = (),
        cancel_working_orders: bool = True,
        audit_ref: str | None = None,
    ) -> str: ...

    def save_limit_change(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def orders(self, *, states: Sequence[str] | None = None) -> tuple[OrderRow, ...]: ...

    def get_order(self, order_id: str) -> dict[str, Any] | None: ...

    def halt_events(self) -> tuple[HaltEventRow, ...]: ...

    def execution_results(self) -> tuple[ExecutionResultRow, ...]: ...

    def get_execution_result(self, intent_id: str) -> ExecutionResultRow | None: ...

    def get_intent(self, intent_id: str) -> dict[str, Any] | None: ...

    def decisions(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]: ...

    def save_dossier(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def dossiers(
        self, *, instrument_id: str | None = None, limit: int = 50
    ) -> tuple[dict[str, Any], ...]: ...

    def get_dossier(self, dossier_id: str) -> dict[str, Any] | None: ...

    def save_evidence_ref(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None: ...

    def evidence_refs(
        self, *, dossier_id: str | None = None, limit: int = 50
    ) -> tuple[dict[str, Any], ...]: ...

    def instruments(self) -> tuple[dict[str, Any], ...]: ...

    def venue_mappings(self, *, instrument_id: str | None = None) -> tuple[dict[str, Any], ...]: ...

    def mark_projected(
        self, audit_ref: str, *, event_type: str, entity_type: str, entity_id: str
    ) -> None: ...

    def projected_refs(self) -> frozenset[str]: ...

    def counts(self) -> dict[str, int]: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------- sqlite implementation


def _text(value: Any) -> str | None:
    """Bind value as TEXT, preserving Decimal exactly and unwrapping enums."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _int_bool(value: Any) -> int:
    return 1 if bool(value) else 0


def _num(value: Any) -> str | None:
    """Numeric column: Decimal or its exact string form, never a float rounding."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _json_list(value: Any) -> str:
    if value is None:
        return "[]"
    return dumps_canonical(list(value))


def _str_tuple(value: Any) -> tuple[str, ...]:
    loaded = loads_json(value if isinstance(value, str) else None)
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded)


class SqliteOperationalStore:
    """SQLite operational store: one writer, durable commits, migrations applied on open."""

    def __init__(
        self,
        path: str | Path,
        *,
        audit: Any = None,
        migrate: bool = True,
    ) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self.migrations: MigrationReport | None = (
            MigrationRunner(self._conn, audit=audit).run() if migrate else None
        )

    @property
    def path(self) -> str:
        return self._path

    # -- transaction plumbing -------------------------------------------

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise PersistenceError(f"operational write failed: {exc}") from exc

    def _query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return list(self._conn.execute(sql, tuple(params)).fetchall())
            except sqlite3.Error as exc:
                raise PersistenceError(f"operational read failed: {exc}") from exc

    # -- decisions -------------------------------------------------------

    def save_decision(self, record: DecisionRecord, *, audit_ref: str | None = None) -> None:
        payload = asdict(record)
        payload["state"] = record.state.value
        payload["verb"] = record.verb.value
        self.save_decision_payload(payload, audit_ref=audit_ref)

    def save_decision_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        decision_id = str(payload.get("decision_id") or "")
        if not decision_id:
            raise PersistenceError("a decision cannot be persisted without a decision_id")
        assert_no_secrets(dict(payload))
        now = iso_utc(utc_now())
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO decision
                   (decision_id, created_at, updated_at, state, verb, instrument_id, venue,
                    strategy_id, model_id, horizon, confidence, rationale, reason_codes,
                    evidence_refs, counter_evidence_refs, intent_id, risk_check, expires_at,
                    audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision_id,
                    _text(payload.get("created_at")) or now,
                    _text(payload.get("updated_at")) or now,
                    _text(payload.get("state")) or "PROPOSED",
                    _text(payload.get("verb")) or "ABSTAIN",
                    _text(payload.get("instrument_id")),
                    _text(payload.get("venue")),
                    _text(payload.get("strategy_id")),
                    _text(payload.get("model_id")),
                    _text(payload.get("horizon")),
                    _text(payload.get("confidence")),
                    str(payload.get("rationale") or ""),
                    _json_list(payload.get("reason_codes")),
                    _json_list(payload.get("evidence_refs")),
                    _json_list(payload.get("counter_evidence_refs")),
                    _text(payload.get("intent_id")),
                    dumps_canonical(payload.get("risk_check") or {}),
                    _text(payload.get("expires_at")),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "decision", decision_id)

    def decisions(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        rows = self._query(
            "SELECT * FROM decision ORDER BY created_at DESC, rowid DESC LIMIT ?", (int(limit),)
        )
        return tuple(self._decision_dict(row) for row in rows)

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM decision WHERE decision_id = ?", (decision_id,))
        return self._decision_dict(rows[0]) if rows else None

    @staticmethod
    def _decision_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("reason_codes", "evidence_refs", "counter_evidence_refs"):
            item[key] = _str_tuple(dumps_canonical(loads_json(item.get(key)) or []))
        item["risk_check"] = loads_json(item.get("risk_check")) or {}
        item["confidence"] = None if item.get("confidence") is None else float(item["confidence"])
        return item

    # -- intents & approvals ---------------------------------------------

    def save_intent(self, intent: TradeIntent, *, audit_ref: str | None = None) -> None:
        payload = asdict(intent)
        payload["digest"] = intent.digest()
        self.save_intent_payload(payload, audit_ref=audit_ref)

    def save_intent_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        intent_id = str(payload.get("intent_id") or "")
        if not intent_id:
            raise PersistenceError("an intent cannot be persisted without an intent_id")
        assert_no_secrets(dict(payload))
        digest = str(payload.get("digest") or "")
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO trade_intent
                   (intent_id, decision_id, created_at, expires_at, environment, instrument_id,
                    venue, account_id, side, order_type, quantity, limit_price, stop_price,
                    protective_stop, take_profit, time_in_force, reduce_only, post_only,
                    quote_currency, max_loss_usd, estimated_cost_usd, strategy_id, model_id,
                    evidence_summary, counter_case, exit_plan, idempotency_key, digest, payload,
                    audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    intent_id,
                    _text(payload.get("decision_id")),
                    _text(payload.get("created_at")) or iso_utc(utc_now()),
                    _text(payload.get("expires_at")),
                    _text(payload.get("environment")) or "DISABLED",
                    str(payload.get("instrument_id") or ""),
                    str(payload.get("venue") or ""),
                    str(payload.get("account_id") or ""),
                    str(payload.get("side") or "").upper(),
                    str(payload.get("order_type") or ""),
                    _num(payload.get("quantity")) or "0",
                    _num(payload.get("limit_price")),
                    _num(payload.get("stop_price")),
                    _num(payload.get("protective_stop")),
                    _num(payload.get("take_profit")),
                    _text(payload.get("time_in_force")) or "GTC",
                    _int_bool(payload.get("reduce_only")),
                    _int_bool(payload.get("post_only")),
                    _text(payload.get("quote_currency")) or "USD",
                    _num(payload.get("max_loss_usd")),
                    _num(payload.get("estimated_cost_usd")),
                    _text(payload.get("strategy_id")),
                    _text(payload.get("model_id")),
                    str(payload.get("evidence_summary") or ""),
                    str(payload.get("counter_case") or ""),
                    str(payload.get("exit_plan") or ""),
                    str(payload.get("idempotency_key") or intent_id),
                    digest,
                    dumps_canonical(payload),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "trade_intent", intent_id)

    def get_intent(self, intent_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM trade_intent WHERE intent_id = ?", (intent_id,))
        if not rows:
            return None
        item = dict(rows[0])
        for key in (
            "quantity",
            "limit_price",
            "stop_price",
            "protective_stop",
            "take_profit",
            "max_loss_usd",
            "estimated_cost_usd",
        ):
            item[key] = decimal_or_none(item.get(key))
        item["reduce_only"] = bool(item.get("reduce_only"))
        item["post_only"] = bool(item.get("post_only"))
        item["payload"] = loads_json(item.get("payload")) or {}
        return item

    def intents_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM trade_intent WHERE idempotency_key = ?", (idempotency_key,))
        return dict(rows[0]) if rows else None

    def save_approval(self, approval: ApprovalRecord, *, audit_ref: str | None = None) -> None:
        self.save_approval_payload(asdict(approval), audit_ref=audit_ref)

    def save_approval_payload(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        approval_id = str(payload.get("approval_id") or "")
        intent_id = str(payload.get("intent_id") or "")
        if not approval_id or not intent_id:
            raise PersistenceError("an approval needs both approval_id and intent_id")
        assert_no_secrets(dict(payload))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO approval
                   (approval_id, intent_id, intent_digest, approved_by, approved_at, expires_at,
                    scope, step_up_verified, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    approval_id,
                    intent_id,
                    str(payload.get("intent_digest") or ""),
                    str(payload.get("approved_by") or ""),
                    _text(payload.get("approved_at")) or iso_utc(utc_now()),
                    _text(payload.get("expires_at")),
                    dumps_canonical(payload.get("scope") or {}),
                    _int_bool(payload.get("step_up_verified")),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "approval", approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM approval WHERE approval_id = ?", (approval_id,))
        if not rows:
            return None
        item = dict(rows[0])
        item["scope"] = loads_json(item.get("scope")) or {}
        item["step_up_verified"] = bool(item.get("step_up_verified"))
        return item

    # -- instruments -----------------------------------------------------

    def save_instrument(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        instrument_id = str(payload.get("instrument_id") or "")
        if not instrument_id:
            raise PersistenceError("an instrument cannot be persisted without an instrument_id")
        assert_no_secrets(dict(payload))
        now = iso_utc(utc_now())
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO instrument
                   (instrument_id, canonical_symbol, asset_class, base_currency, quote_currency,
                    settlement_currency, underlying, expiry, strike, option_type, active,
                    data_status, notes, payload, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    instrument_id,
                    str(payload.get("canonical_symbol") or instrument_id),
                    str(payload.get("asset_class") or ""),
                    str(payload.get("base_currency") or ""),
                    str(payload.get("quote_currency") or ""),
                    str(payload.get("settlement_currency") or ""),
                    _text(payload.get("underlying")),
                    _text(payload.get("expiry")),
                    _num(payload.get("strike")),
                    _text(payload.get("option_type")),
                    _int_bool(payload.get("active")),
                    str(payload.get("data_status") or "UNAVAILABLE"),
                    str(payload.get("notes") or ""),
                    dumps_canonical(payload),
                    _text(payload.get("created_at")) or now,
                    now,
                ),
            )
            self._mark(conn, audit_ref, "instrument", instrument_id)

    def instruments(self) -> tuple[dict[str, Any], ...]:
        rows = self._query("SELECT * FROM instrument ORDER BY instrument_id ASC")
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["active"] = bool(item.get("active"))
            item["strike"] = decimal_or_none(item.get("strike"))
            item["payload"] = loads_json(item.get("payload")) or {}
            out.append(item)
        return tuple(out)

    def save_venue_mapping(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        """One (instrument, venue, venue_symbol) row: how the canonical instrument is traded somewhere.

        The identity triple is what makes this idempotent — re-projecting the same mapping replaces the
        row rather than adding a second one, which matters because the projection is re-runnable by
        design (L-2). ``certified_at`` is deliberately left NULL: the moment a mapping reached its
        present rank is recorded in the registry's change log, with the evidence and the requester
        beside it, and copying that timestamp here would create a second copy of a fact that can then
        disagree with the first.
        """
        instrument_id = str(payload.get("instrument_id") or "")
        venue = str(payload.get("venue") or "")
        venue_symbol = str(payload.get("venue_symbol") or "")
        if not instrument_id or not venue or not venue_symbol:
            raise PersistenceError(
                "a venue mapping needs instrument_id, venue and venue_symbol to be persisted"
            )
        assert_no_secrets(dict(payload))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO venue_instrument_mapping
                   (instrument_id, venue, venue_symbol, status, contract_size, tick_size, tick_value,
                    min_order_qty, max_order_qty, qty_step, quote_currency, settlement_currency,
                    trading_hours, margin_rate, fees, notes, certified_at, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    instrument_id,
                    venue,
                    venue_symbol,
                    str(payload.get("status") or "UNKNOWN"),
                    _num(payload.get("contract_size")),
                    _num(payload.get("tick_size")),
                    _num(payload.get("tick_value")),
                    _num(payload.get("min_order_qty")),
                    _num(payload.get("max_order_qty")),
                    _num(payload.get("qty_step")),
                    _text(payload.get("quote_currency")),
                    _text(payload.get("settlement_currency")),
                    _text(payload.get("trading_hours")),
                    _num(payload.get("margin_rate")),
                    dumps_canonical(payload.get("fees") or {}),
                    str(payload.get("notes") or ""),
                    _text(payload.get("certified_at")),
                    _text(audit_ref),
                ),
            )
            self._mark(conn, audit_ref, "venue_mapping", f"{instrument_id}:{venue}:{venue_symbol}")

    def venue_mappings(self, *, instrument_id: str | None = None) -> tuple[dict[str, Any], ...]:
        sql = "SELECT * FROM venue_instrument_mapping"
        args: tuple[Any, ...] = ()
        if instrument_id is not None:
            sql += " WHERE instrument_id = ?"
            args = (instrument_id,)
        sql += " ORDER BY instrument_id ASC, venue ASC, venue_symbol ASC"
        rows = self._query(sql, args)
        numeric = (
            "contract_size",
            "tick_size",
            "tick_value",
            "min_order_qty",
            "max_order_qty",
            "qty_step",
            "margin_rate",
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for column in numeric:
                item[column] = decimal_or_none(item.get(column))
            item["fees"] = loads_json(item.get("fees")) or {}
            out.append(item)
        return tuple(out)

    # -- orders & fills --------------------------------------------------

    def save_order(
        self,
        *,
        order_id: str,
        venue: str,
        account_id: str,
        state: OrderState | str,
        idempotency_key: str,
        intent_id: str | None = None,
        venue_order_id: str | None = None,
        submitted_at: str | None = None,
        updated_at: str | None = None,
        filled_qty: Decimal | str | None = None,
        average_price: Decimal | str | None = None,
        fees_quote: Decimal | str | None = None,
        funding_quote: Decimal | str | None = None,
        reject_reason: str | None = None,
        audit_ref: str | None = None,
    ) -> None:
        if not order_id:
            raise PersistenceError("an order cannot be persisted without an order_id")
        now = iso_utc(utc_now())
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO orders
                   (order_id, intent_id, venue, account_id, venue_order_id, state, submitted_at,
                    updated_at, filled_qty, average_price, fees_quote, funding_quote,
                    reject_reason, idempotency_key, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_id,
                    intent_id,
                    venue,
                    account_id,
                    venue_order_id,
                    state.value if isinstance(state, OrderState) else str(state),
                    submitted_at,
                    updated_at or now,
                    _num(filled_qty) or "0",
                    _num(average_price),
                    _num(fees_quote) or "0",
                    _num(funding_quote) or "0",
                    reject_reason,
                    idempotency_key,
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "orders", order_id)

    def update_order_state(
        self,
        order_id: str,
        state: OrderState | str,
        *,
        reason: str = "",
        at: str | None = None,
        audit_ref: str | None = None,
    ) -> bool:
        """Move a persisted order to ``state``. Returns False when the order is unknown."""
        target = state.value if isinstance(state, OrderState) else str(state)
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE orders SET state = ?, updated_at = ?, reject_reason = ?, audit_ref = ? "
                "WHERE order_id = ?",
                (target, at or iso_utc(utc_now()), reason or None, audit_ref, order_id),
            )
            changed = cursor.rowcount > 0
            if changed:
                self._mark(conn, audit_ref, "orders", order_id)
        return changed

    def orders(self, *, states: Sequence[str] | None = None) -> tuple[OrderRow, ...]:
        if states:
            marks = ",".join("?" for _ in states)
            rows = self._query(
                f"SELECT * FROM orders WHERE state IN ({marks}) ORDER BY rowid ASC",  # noqa: S608
                tuple(str(item) for item in states),
            )
        else:
            rows = self._query("SELECT * FROM orders ORDER BY rowid ASC")
        return tuple(self._order_row(row) for row in rows)

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        if not rows:
            return None
        item = dict(rows[0])
        for key in ("filled_qty", "average_price", "fees_quote", "funding_quote"):
            item[key] = decimal_or_none(item.get(key))
        return item

    @staticmethod
    def _order_row(row: sqlite3.Row) -> OrderRow:
        item = dict(row)
        return OrderRow(
            order_id=str(item["order_id"]),
            venue=str(item["venue"]),
            account_id=str(item["account_id"]),
            state=OrderState(str(item["state"])),
            updated_at=str(item["updated_at"]),
            idempotency_key=str(item["idempotency_key"]),
            intent_id=item.get("intent_id"),
            venue_order_id=item.get("venue_order_id"),
            reject_reason=item.get("reject_reason"),
            filled_qty=decimal_or_none(item.get("filled_qty")),
            average_price=decimal_or_none(item.get("average_price")),
        )

    def save_fill(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        order_id = str(payload.get("order_id") or "")
        if not order_id:
            raise PersistenceError("a fill cannot be persisted without an order_id")
        assert_no_secrets(dict(payload))
        fill_id = str(payload.get("fill_id") or new_id("FILL"))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO fills
                   (fill_id, order_id, venue, venue_trade_id, filled_at, quantity, price,
                    fee_quote, fee_currency, is_maker, side, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fill_id,
                    order_id,
                    str(payload.get("venue") or ""),
                    _text(payload.get("venue_trade_id")),
                    _text(payload.get("filled_at")) or iso_utc(utc_now()),
                    _num(payload.get("quantity")) or "0",
                    _num(payload.get("price")) or "0",
                    _num(payload.get("fee_quote")) or "0",
                    _text(payload.get("fee_currency")),
                    None if payload.get("is_maker") is None else _int_bool(payload.get("is_maker")),
                    str(payload.get("side") or ""),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "fills", fill_id)

    def fills(self, order_id: str) -> tuple[dict[str, Any], ...]:
        rows = self._query("SELECT * FROM fills WHERE order_id = ? ORDER BY filled_at ASC", (order_id,))
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("quantity", "price", "fee_quote"):
                item[key] = decimal_or_none(item.get(key))
            item["is_maker"] = None if item.get("is_maker") is None else bool(item["is_maker"])
            out.append(item)
        return tuple(out)

    # -- gateway results (durable idempotency) ---------------------------

    def save_execution_result(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        intent_id = str(payload.get("intent_id") or "")
        if not intent_id:
            raise PersistenceError("an execution result needs an intent_id")
        assert_no_secrets(dict(payload))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO execution_result
                   (intent_id, status, order_id, order_state, reasons, idempotent_replay, at,
                    audit_ref)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    intent_id,
                    str(payload.get("status") or ""),
                    _text(payload.get("order_id")),
                    str(payload.get("order_state") or OrderState.DRAFT.value),
                    _json_list(payload.get("reasons")),
                    _int_bool(payload.get("idempotent_replay")),
                    _text(payload.get("at")) or iso_utc(utc_now()),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "execution_result", intent_id)

    def execution_results(self) -> tuple[ExecutionResultRow, ...]:
        rows = self._query("SELECT * FROM execution_result ORDER BY at ASC, rowid ASC")
        return tuple(self._execution_row(row) for row in rows)

    def get_execution_result(self, intent_id: str) -> ExecutionResultRow | None:
        rows = self._query("SELECT * FROM execution_result WHERE intent_id = ?", (intent_id,))
        return self._execution_row(rows[0]) if rows else None

    @staticmethod
    def _execution_row(row: sqlite3.Row) -> ExecutionResultRow:
        item = dict(row)
        return ExecutionResultRow(
            intent_id=str(item["intent_id"]),
            status=str(item["status"]),
            order_state=str(item["order_state"]),
            at=str(item["at"]),
            order_id=item.get("order_id"),
            reasons=_str_tuple(item.get("reasons")),
            idempotent_replay=bool(item.get("idempotent_replay")),
            audit_ref=item.get("audit_ref"),
        )

    # -- halts -----------------------------------------------------------

    def save_halt_event(
        self,
        *,
        action: str,
        scope: HaltScope | str,
        reason: str,
        triggered_by: str,
        at: str,
        halt_id: str | None = None,
        incident_id: str | None = None,
        affected_accounts: Sequence[str] = (),
        affected_instruments: Sequence[str] = (),
        cancel_working_orders: bool = True,
        audit_ref: str | None = None,
    ) -> str:
        if action not in ("ENGAGE", "RELEASE"):
            raise PersistenceError(f"unknown halt action: {action}")
        identifier = halt_id or new_id("HLT")
        with self._transaction() as conn:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM halt_event").fetchone()
            seq = int(row[0]) if row else 1
            conn.execute(
                """INSERT OR REPLACE INTO halt_event
                   (halt_id, seq, action, scope, reason, triggered_by, incident_id, at,
                    affected_accounts, affected_instruments, cancel_working_orders, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    seq,
                    action,
                    scope.value if isinstance(scope, HaltScope) else str(scope),
                    reason,
                    triggered_by,
                    incident_id,
                    at,
                    _json_list(affected_accounts),
                    _json_list(affected_instruments),
                    _int_bool(cancel_working_orders),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "halt_event", identifier)
        return identifier

    def halt_events(self) -> tuple[HaltEventRow, ...]:
        rows = self._query("SELECT * FROM halt_event ORDER BY seq ASC, rowid ASC")
        out: list[HaltEventRow] = []
        for row in rows:
            item = dict(row)
            out.append(
                HaltEventRow(
                    halt_id=str(item["halt_id"]),
                    seq=int(item["seq"]),
                    action=str(item["action"]),
                    scope=HaltScope(str(item["scope"])),
                    reason=str(item["reason"]),
                    triggered_by=str(item["triggered_by"]),
                    at=str(item["at"]),
                    incident_id=item.get("incident_id"),
                    affected_accounts=_str_tuple(item.get("affected_accounts")),
                    affected_instruments=_str_tuple(item.get("affected_instruments")),
                    cancel_working_orders=bool(item.get("cancel_working_orders")),
                    audit_ref=item.get("audit_ref"),
                )
            )
        return tuple(out)

    # -- risk limit changes ----------------------------------------------

    def save_limit_change(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        change_id = str(payload.get("change_id") or new_id("RLC"))
        limit_name = str(payload.get("limit_name") or "")
        if not limit_name:
            raise PersistenceError("a limit change needs a limit_name")
        assert_no_secrets(dict(payload))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO risk_limit_change
                   (change_id, requested_by, approved_by, limit_name, old_value, new_value,
                    requested_at, effective_at, cooldown_seconds, status, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    change_id,
                    str(payload.get("requested_by") or ""),
                    _text(payload.get("approved_by")),
                    limit_name,
                    _num(payload.get("old_value")),
                    _num(payload.get("new_value")) or "0",
                    _text(payload.get("requested_at")) or iso_utc(utc_now()),
                    _text(payload.get("effective_at")),
                    int(payload.get("cooldown_seconds") or 3600),
                    str(payload.get("status") or "PENDING"),
                    audit_ref,
                ),
            )
            self._mark(conn, audit_ref, "risk_limit_change", change_id)

    def limit_changes(self) -> tuple[dict[str, Any], ...]:
        rows = self._query("SELECT * FROM risk_limit_change ORDER BY requested_at ASC")
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["old_value"] = decimal_or_none(item.get("old_value"))
            item["new_value"] = decimal_or_none(item.get("new_value"))
            out.append(item)
        return tuple(out)

    # -- intelligence memory (Stage 8) -----------------------------------
    #
    # Two of the three intelligence-memory tables now have a writer: `dossier` (Stage 8.3, audited as
    # `dossier.opened`) and `evidence_ref` (Stage 8.2, audited as `evidence.recorded`). `memory_item` is
    # still schema-only and arrives with stage 10, together with the three columns F-18 wants and D-051
    # deferred to that batch. The evidence writer is deliberately usable before a dossier exists —
    # `dossier_id` is nullable — and the dossier writer is deliberately usable before any evidence does.
    #
    # Both are projections, not records: `INSERT OR REPLACE` into a table the audit chain can rebuild,
    # which is why a replayed event must carry its own timestamps rather than inherit the replay's clock.

    def save_dossier(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        """Persist one research dossier.

        ``created_at`` and ``updated_at`` come from the payload when it carries them, for two reasons: the
        applied schema has no ``DEFAULT now()`` (one of the four lost defaults in ``docs/15`` §9.1), and a
        replayed ``dossier.opened`` must reproduce the row it first wrote instead of restamping it with
        the replay's clock — otherwise boot recovery would silently rewrite the chronology that
        ``docs/03`` J-04 asks the dossier view to show. The defaults below are the ABSTAIN-side values the
        schema itself declares: ``state='DRAFT'``, ``stance='ABSTAIN'``, ``sufficiency='INSUFFICIENT'``.

        Note what this method does *not* check. ``dossier.instrument_id`` carries a ``REFERENCES`` clause
        that migration ``0004_memory_fidelity`` restored, but ``PRAGMA foreign_keys`` is deliberately off
        (``schema.py``'s module docstring), so a dangling parent is accepted here. The refusal lives in
        ``intelligence.dossier.open_dossier``, which can see the store and name the missing instrument;
        putting it here instead would make boot recovery depend on a read and could fail a replay.
        """
        dossier_id = str(payload.get("dossier_id") or "")
        if not dossier_id:
            raise PersistenceError("a dossier cannot be persisted without a dossier_id")
        assert_no_secrets(dict(payload))
        now = iso_utc(utc_now())
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dossier
                   (dossier_id, instrument_id, venue, created_at, updated_at, state, summary,
                    stance, uncertainty, sufficiency, payload, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    _text(payload.get("instrument_id")),
                    _text(payload.get("venue")),
                    _text(payload.get("created_at")) or now,
                    _text(payload.get("updated_at")) or now,
                    str(payload.get("state") or "DRAFT"),
                    str(payload.get("summary") or ""),
                    str(payload.get("stance") or "ABSTAIN"),
                    str(payload.get("uncertainty") or ""),
                    str(payload.get("sufficiency") or "INSUFFICIENT"),
                    dumps_canonical(payload.get("payload") or {}),
                    _text(audit_ref),
                ),
            )
            self._mark(conn, audit_ref, "dossier", dossier_id)

    def dossiers(self, *, instrument_id: str | None = None, limit: int = 50) -> tuple[dict[str, Any], ...]:
        """Newest first, which is the order ``ix_dossier_created`` (``created_at DESC``) already keeps.

        Filtering by ``instrument_id`` scans: ``0002_memory`` indexes ``created_at`` only, and adding an
        index is a migration, not a query change. At the volumes Stage 8 writes that is invisible; it is
        recorded here rather than left to be discovered by whoever hits it at stage 10's.
        """
        sql = "SELECT * FROM dossier"
        args: list[Any] = []
        if instrument_id is not None:
            sql += " WHERE instrument_id = ?"
            args.append(instrument_id)
        sql += " ORDER BY created_at DESC, dossier_id ASC LIMIT ?"
        args.append(int(limit))
        rows = self._query(sql, tuple(args))
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = loads_json(item.get("payload")) or {}
            out.append(item)
        return tuple(out)

    def get_dossier(self, dossier_id: str) -> dict[str, Any] | None:
        """One dossier by id, or ``None``. The read a single-case view needs (``docs/03`` J-04 step 1)."""
        rows = self._query("SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,))
        if not rows:
            return None
        item = dict(rows[0])
        item["payload"] = loads_json(item.get("payload")) or {}
        return item

    def save_evidence_ref(self, payload: Mapping[str, Any], *, audit_ref: str | None = None) -> None:
        """Persist one piece of evidence and when it was seen.

        ``observed_at`` and ``retrieved_at`` are separate columns on purpose and both are required to be
        non-empty. ``observed_at`` is the venue's own timestamp for the observation; ``retrieved_at`` is
        the local clock at the moment this system received it. Collapsing the two is what makes latency
        unmeasurable (finding F-14, closed at the adapters by Stage 8.4 — the ingestion records now
        carry both clocks, while these two columns keep the meanings given here), and a NOT NULL column
        still accepts an empty string — so the refusal
        is here rather than left to the caller, because an evidence row that cannot say when it was
        observed cannot support a decision anyone can audit.
        """
        evidence_id = str(payload.get("evidence_id") or "")
        if not evidence_id:
            raise PersistenceError("evidence cannot be persisted without an evidence_id")
        source = str(payload.get("source") or "")
        if not source:
            raise PersistenceError("evidence cannot be persisted without a source")
        observed_at = str(payload.get("observed_at") or "")
        retrieved_at = str(payload.get("retrieved_at") or "")
        if not observed_at or not retrieved_at:
            raise PersistenceError(
                "evidence needs both observed_at (the venue's timestamp) and retrieved_at (the local "
                "clock at receipt); an evidence row with neither cannot support an auditable decision"
            )
        assert_no_secrets(dict(payload))
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO evidence_ref
                   (evidence_id, dossier_id, source, kind, observed_at, retrieved_at, data_status,
                    locator, checksum, payload, audit_ref)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidence_id,
                    _text(payload.get("dossier_id")),
                    source,
                    str(payload.get("kind") or "DATA"),
                    observed_at,
                    retrieved_at,
                    str(payload.get("data_status") or "UNAVAILABLE"),
                    str(payload.get("locator") or ""),
                    _text(payload.get("checksum")),
                    dumps_canonical(payload.get("payload") or {}),
                    _text(audit_ref),
                ),
            )
            self._mark(conn, audit_ref, "evidence_ref", evidence_id)

    def evidence_refs(self, *, dossier_id: str | None = None, limit: int = 50) -> tuple[dict[str, Any], ...]:
        """Most recent evidence first, so a reader sees what the system has lately relied on."""
        sql = "SELECT * FROM evidence_ref"
        args: list[Any] = []
        if dossier_id is not None:
            sql += " WHERE dossier_id = ?"
            args.append(dossier_id)
        sql += " ORDER BY retrieved_at DESC, evidence_id ASC LIMIT ?"
        args.append(int(limit))
        rows = self._query(sql, tuple(args))
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = loads_json(item.get("payload")) or {}
            out.append(item)
        return tuple(out)

    # -- projection bookkeeping (L-2) ------------------------------------

    def _mark(
        self,
        conn: sqlite3.Connection,
        audit_ref: str | None,
        entity_type: str,
        entity_id: str,
        event_type: str = "",
    ) -> None:
        if not audit_ref:
            return
        conn.execute(
            "INSERT OR IGNORE INTO op_projection (audit_ref, event_type, entity_type, entity_id, "
            "projected_at) VALUES (?,?,?,?,?)",
            (audit_ref, event_type, entity_type, entity_id, iso_utc(utc_now())),
        )

    def mark_projected(self, audit_ref: str, *, event_type: str, entity_type: str, entity_id: str) -> None:
        with self._transaction() as conn:
            self._mark(conn, audit_ref, entity_type, entity_id, event_type)

    def projected_refs(self) -> frozenset[str]:
        rows = self._query("SELECT audit_ref FROM op_projection")
        return frozenset(str(row[0]) for row in rows)

    # -- introspection ---------------------------------------------------

    def counts(self) -> dict[str, int]:
        tables = (
            "instrument",
            "venue_instrument_mapping",
            "decision",
            "trade_intent",
            "approval",
            "orders",
            "fills",
            "execution_result",
            "halt_event",
            "risk_limit_change",
            "op_projection",
            "dossier",
            "evidence_ref",
            "memory_item",
        )
        out: dict[str, int] = {}
        for table in tables:
            rows = self._query(f"SELECT count(*) FROM {table}")  # noqa: S608
            out[table] = int(rows[0][0]) if rows else 0
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
