"""Typed errors and rejection reasons.

Every refusal to act carries a machine-readable reason code so the audit trail, the UI
and the alerts can state *why* — never a bare "rejected".
"""

from __future__ import annotations

from enum import StrEnum


class RejectReason(StrEnum):
    """Stable reason codes. Persisted in audit records and surfaced in the UI."""

    # Authority / governance
    LIVE_TRADING_DISABLED = "LIVE_TRADING_DISABLED"
    ENVIRONMENT_NOT_AUTHORIZED = "ENVIRONMENT_NOT_AUTHORIZED"
    LEGAL_REVIEW_NOT_COMPLETE = "LEGAL_REVIEW_NOT_COMPLETE"
    MANDATE_NOT_FOUND = "MANDATE_NOT_FOUND"
    MANDATE_SCOPE_EXCEEDED = "MANDATE_SCOPE_EXCEEDED"
    APPROVAL_MISSING = "APPROVAL_MISSING"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_INTENT_MISMATCH = "APPROVAL_INTENT_MISMATCH"
    HALT_ACTIVE = "HALT_ACTIVE"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"

    # Data quality
    DATA_STALE = "DATA_STALE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_CROSSED_MARKET = "DATA_CROSSED_MARKET"
    VENUE_DISCONNECTED = "VENUE_DISCONNECTED"
    INSTRUMENT_NOT_CERTIFIED = "INSTRUMENT_NOT_CERTIFIED"
    INSTRUMENT_UNKNOWN = "INSTRUMENT_UNKNOWN"

    # Risk limits (Section 10.1 hard limits)
    RISK_PER_TRADE_EXCEEDED = "RISK_PER_TRADE_EXCEEDED"
    LEVERAGE_EXCEEDED = "LEVERAGE_EXCEEDED"
    DAILY_DRAWDOWN_HALT = "DAILY_DRAWDOWN_HALT"
    MAX_OPEN_POSITIONS_EXCEEDED = "MAX_OPEN_POSITIONS_EXCEEDED"
    CONCENTRATION_EXCEEDED = "CONCENTRATION_EXCEEDED"
    NOTIONAL_LIMIT_EXCEEDED = "NOTIONAL_LIMIT_EXCEEDED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"
    SIZING_UNDETERMINED = "SIZING_UNDETERMINED"

    # Execution
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    ORDER_STATE_UNKNOWN = "ORDER_STATE_UNKNOWN"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    VENUE_NOT_SUPPORTED = "VENUE_NOT_SUPPORTED"

    # Models / intelligence
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    ABSTAIN = "ABSTAIN"

    # Configuration
    CONFIG_INVALID = "CONFIG_INVALID"
    SECRET_UNAVAILABLE = "SECRET_UNAVAILABLE"  # noqa: S105 - reason code, not a credential

    # Persistence (Stage 6: D-042, laws L-1…L-6)
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    AUDIT_CHAIN_INVALID = "AUDIT_CHAIN_INVALID"
    BOOT_RECOVERY_INCOMPLETE = "BOOT_RECOVERY_INCOMPLETE"
    MIGRATION_INVALID = "MIGRATION_INVALID"


class NexusError(Exception):
    """Base error carrying a stable reason code and safe detail.

    ``detail`` must never contain credentials, full account numbers, or position sizes
    of other accounts. Use ``safe_detail`` discipline: describe the condition, not the secret.
    """

    def __init__(
        self,
        reason: RejectReason,
        detail: str = "",
        *,
        retryable: bool = False,
        context: dict[str, object] | None = None,
    ) -> None:
        self.reason = reason
        self.detail = detail
        self.retryable = retryable
        self.context = context or {}
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)


class Rejected(NexusError):
    """A governance/risk refusal. Expected, non-exceptional in operation, always audited."""

    def __init__(
        self,
        reason: RejectReason,
        detail: str = "",
        *,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(reason, detail, retryable=False, context=context)


class DataUnavailable(NexusError):
    """Required data is missing or stale. Callers must fail closed."""

    def __init__(self, reason: RejectReason, detail: str = "", *, retryable: bool = True) -> None:
        super().__init__(reason, detail, retryable=retryable)


class ConfigurationError(NexusError):
    """Invalid or missing configuration. Refuse to start rather than run unsafely."""

    def __init__(self, detail: str = "", *, context: dict[str, object] | None = None) -> None:
        super().__init__(RejectReason.CONFIG_INVALID, detail, retryable=False, context=context)
