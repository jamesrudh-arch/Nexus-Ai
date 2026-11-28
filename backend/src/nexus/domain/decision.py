"""Decision records (Section 5.5, Section 8).

A decision is not an order. Research completion never implies a trade. Every decision
carries its state, reason codes, evidence references and — when it proposes risk — an
immutable intent that governance may accept, reduce or refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now


class DecisionState(StrEnum):
    """Machine states a decision can occupy."""

    PROPOSED = "PROPOSED"
    WAITING_DATA = "WAITING_DATA"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"  # risk engine cut size to fit limits
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    CANCELLED = "CANCELLED"
    ABSTAINED = "ABSTAINED"  # no view / evidence insufficient / model unavailable
    FAILED = "FAILED"


class DecisionVerb(StrEnum):
    """What the intelligence layer proposes (Section 8)."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    WAIT = "WAIT"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    ESCALATE = "ESCALATE"
    ABSTAIN = "ABSTAIN"


@dataclass(slots=True)
class DecisionRecord:
    """One auditable decision with its rationale and evidence pointers."""

    decision_id: str = field(default_factory=lambda: new_id("DEC"))
    created_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    state: DecisionState = DecisionState.PROPOSED
    verb: DecisionVerb = DecisionVerb.ABSTAIN
    instrument_id: str | None = None
    venue: str | None = None
    strategy_id: str | None = None
    model_id: str | None = None
    horizon: str | None = None  # e.g. "INTRADAY", "DAY"
    confidence: float | None = None  # 0..1, calibrated — never a marketing number
    rationale: str = ""
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()  # source ids from the evidence graph
    counter_evidence_refs: tuple[str, ...] = ()
    intent_id: str | None = None  # links to the immutable TradeIntent, if any
    risk_check: dict[str, Any] = field(default_factory=dict)
    expires_at: str | None = None
    updated_at: str = field(default_factory=lambda: iso_utc(utc_now()))

    def transition(self, new_state: DecisionState, *, reason: str = "", codes: tuple[str, ...] = ()) -> None:
        """Move to a new state, stamping the time and appending reason codes."""
        self.state = new_state
        self.updated_at = iso_utc(utc_now())
        if reason:
            self.rationale = f"{self.rationale} | {reason}".strip(" |")
        if codes:
            self.reason_codes = (*self.reason_codes, *codes)

    def to_audit_payload(self) -> dict[str, Any]:
        """Payload safe for the audit log (no secrets, no free-form model output)."""
        return {
            "decision_id": self.decision_id,
            "state": self.state.value,
            "verb": self.verb.value,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "strategy_id": self.strategy_id,
            "model_id": self.model_id,
            "horizon": self.horizon,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
            "evidence_refs": list(self.evidence_refs),
            "counter_evidence_refs": list(self.counter_evidence_refs),
            "intent_id": self.intent_id,
            "expires_at": self.expires_at,
        }
