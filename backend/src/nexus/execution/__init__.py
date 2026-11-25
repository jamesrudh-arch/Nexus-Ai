"""Execution governance (Section 12, Section 13).

Phase 2 contains **no venue adapters**. This package defines the immutable trade intent,
the approval binding, the order state machine, idempotency, halt/kill-switch state and the
gateway that refuses to send anything while live authority is denied.
"""

from nexus.execution.gateway import ExecutionGateway, GatewayStatus, SubmitResult
from nexus.execution.halt import HaltManager, HaltScope, HaltState
from nexus.execution.intent import ApprovalRecord, TradeIntent, build_intent_digest
from nexus.execution.orders import OrderState, allowed_transitions

__all__ = [
    "ApprovalRecord",
    "ExecutionGateway",
    "GatewayStatus",
    "HaltManager",
    "HaltScope",
    "HaltState",
    "OrderState",
    "SubmitResult",
    "TradeIntent",
    "allowed_transitions",
    "build_intent_digest",
]
