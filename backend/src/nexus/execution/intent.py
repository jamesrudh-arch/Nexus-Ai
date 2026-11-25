"""Immutable trade intent and approval binding (Section 24).

An intent is the exact thing the owner (or an approved mandate) authorises. Approval binds
to the intent's digest: any material change produces a different digest and therefore
invalidates the approval. Nothing may mutate an intent in place.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from nexus.audit.chain import canonical_json
from nexus.core.ids import iso_utc, new_id, utc_now


def _dec(value: Decimal | float | int | str) -> Decimal:
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    if not dec.is_finite():
        raise ValueError(f"non-finite decimal rejected: {value!r}")
    return dec


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """One proposed order, fully specified, immutable.

    Fields mirror what the approval UI must show (Section 24): instrument, venue, account,
    side, size, order type, estimated cost, worst-case loss, impact, evidence summary,
    counter-case, stop/exit plan, expiry.
    """

    intent_id: str
    decision_id: str
    instrument_id: str
    venue: str
    account_id: str
    side: str  # LONG | SHORT (position intent) — orders derive BUY/SELL from context
    order_type: str  # MARKET | LIMIT | STOP | STOP_LIMIT | TAKE_PROFIT
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    post_only: bool = False
    entry_price: Decimal | None = None
    protective_stop: Decimal | None = None
    take_profit: Decimal | None = None
    max_loss_usd: Decimal | None = None
    estimated_cost_usd: Decimal | None = None
    quote_currency: str = "USD"
    strategy_id: str | None = None
    model_id: str | None = None
    evidence_summary: str = ""
    counter_case: str = ""
    exit_plan: str = ""
    idempotency_key: str = ""
    expires_at: str | None = None
    created_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    environment: str = "DISABLED"

    def digest(self) -> str:
        """SHA-256 over the canonical, material fields of this intent."""
        return build_intent_digest(self.to_material_dict())

    def to_material_dict(self) -> dict[str, Any]:
        """Only the fields that materially define the order. Used for the approval digest."""
        return {
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "account_id": self.account_id,
            "side": self.side.upper(),
            "order_type": self.order_type.upper(),
            "quantity": str(self.quantity),
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "stop_price": str(self.stop_price) if self.stop_price is not None else None,
            "time_in_force": self.time_in_force.upper(),
            "reduce_only": self.reduce_only,
            "post_only": self.post_only,
            "protective_stop": str(self.protective_stop) if self.protective_stop is not None else None,
            "take_profit": str(self.take_profit) if self.take_profit is not None else None,
            "quote_currency": self.quote_currency.upper(),
            "strategy_id": self.strategy_id,
        }

    def to_dict(self) -> dict[str, Any]:
        """Full serialisation for audit/API (still secret-free)."""
        data: dict[str, Any] = {
            "intent_id": self.intent_id,
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "environment": self.environment,
            "idempotency_key_present": bool(self.idempotency_key),
            "evidence_summary": self.evidence_summary,
            "counter_case": self.counter_case,
            "exit_plan": self.exit_plan,
            "estimated_cost_usd": str(self.estimated_cost_usd)
            if self.estimated_cost_usd is not None
            else None,
            "max_loss_usd": str(self.max_loss_usd) if self.max_loss_usd is not None else None,
            "digest": self.digest(),
        }
        data.update(self.to_material_dict())
        return data

    def is_expired(self, *, now: Any = None) -> bool:
        if not self.expires_at:
            return False
        reference = now or utc_now()
        from nexus.core.time import parse_iso  # local import avoids a cycle at module load

        return parse_iso(self.expires_at) <= reference


def build_intent_digest(material: dict[str, Any]) -> str:
    """Deterministic digest of an intent's material fields."""
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """An owner or mandate approval bound to one exact intent digest."""

    approval_id: str
    intent_id: str
    intent_digest: str
    approved_by: str  # "OWNER" | "MANDATE:<id>"
    approved_at: str
    expires_at: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)  # accounts, instruments, notional, schedule
    step_up_verified: bool = False  # MFA/biometric confirmed for live actions

    def binds(self, intent: TradeIntent) -> bool:
        """True only if the digest matches exactly."""
        return self.intent_digest == intent.digest() and self.intent_id == intent.intent_id

    def is_expired(self, *, now: Any = None) -> bool:
        if not self.expires_at:
            return False
        from nexus.core.time import parse_iso

        reference = now or utc_now()
        return parse_iso(self.expires_at) <= reference


def new_intent(**kwargs: Any) -> TradeIntent:
    """Construct an intent with a generated ID, validating numeric fields."""
    kwargs.setdefault("intent_id", new_id("INT"))
    kwargs["quantity"] = _dec(kwargs["quantity"])
    for key in (
        "limit_price",
        "stop_price",
        "entry_price",
        "protective_stop",
        "take_profit",
        "max_loss_usd",
        "estimated_cost_usd",
    ):
        if kwargs.get(key) is not None:
            kwargs[key] = _dec(kwargs[key])
    if kwargs["side"].upper() not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    if kwargs["quantity"] <= 0:
        raise ValueError("quantity must be positive")
    return TradeIntent(**kwargs)
