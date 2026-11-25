"""Halt / kill-switch and order state-machine tests (Section 12.3, 12.5, 34)."""

from __future__ import annotations

import pytest

from nexus.audit.log import AuditLog
from nexus.execution.halt import HaltManager, HaltScope, widest_scope
from nexus.execution.orders import (
    OrderState,
    allowed_transitions,
    blocks_new_risk,
    can_transition,
    is_terminal,
)


class TestHaltManager:
    def test_starts_inactive(self, halt_manager: HaltManager) -> None:
        assert not halt_manager.active
        assert halt_manager.state.scope is HaltScope.NONE
        assert not halt_manager.state.blocks_new_entries()

    def test_engage_blocks_new_entries(self, halt_manager: HaltManager) -> None:
        state = halt_manager.engage(reason="limit breach detected")
        assert state.active
        assert state.blocks_new_entries()
        assert not state.blocks_all_trading()
        assert state.incident_id

    def test_kill_switch_blocks_all_trading(self, halt_manager: HaltManager) -> None:
        state = halt_manager.engage(scope=HaltScope.ALL_TRADING, reason="broker compromise suspected")
        assert state.blocks_all_trading()
        assert state.blocks_new_entries()

    def test_risk_reducing_actions_always_allowed(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(scope=HaltScope.ALL_TRADING, reason="incident")
        assert halt_manager.state.allows_risk_reducing()

    def test_scope_widens_never_narrows(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(scope=HaltScope.ALL_TRADING, reason="kill switch")
        state = halt_manager.engage(scope=HaltScope.NEW_ENTRIES, reason="lesser request")
        assert state.scope is HaltScope.ALL_TRADING

    def test_incident_id_is_stable_across_re_engage(self, halt_manager: HaltManager) -> None:
        first = halt_manager.engage(reason="one").incident_id
        second = halt_manager.engage(reason="two").incident_id
        assert first == second

    def test_release_clears_state(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(reason="incident")
        state = halt_manager.release(reason="resolved and reconciled")
        assert not state.active
        assert state.scope is HaltScope.NONE
        assert not halt_manager.state.blocks_new_entries()

    def test_release_when_inactive_is_safe(self, halt_manager: HaltManager) -> None:
        assert not halt_manager.release(reason="no-op").active

    def test_history_records_engage_and_release(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(reason="incident")
        halt_manager.release(reason="resolved")
        actions = [entry["action"] for entry in halt_manager.history()]
        assert actions == ["ENGAGE", "RELEASE"]

    def test_engage_is_audited(self, halt_manager: HaltManager, audit_log: AuditLog) -> None:
        halt_manager.engage(reason="daily drawdown halt")
        assert audit_log.length == 1
        assert audit_log.verify() == []

    def test_affected_scope_is_recorded(self, halt_manager: HaltManager) -> None:
        state = halt_manager.engage(
            reason="venue outage",
            affected_accounts=("BYBIT-UNI-001",),
            affected_instruments=("INS-BTCUSDT-PERP-BYBIT",),
        )
        assert state.affected_accounts == ("BYBIT-UNI-001",)
        assert state.affected_instruments == ("INS-BTCUSDT-PERP-BYBIT",)

    def test_affected_scope_accumulates(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(reason="one", affected_accounts=("A1",))
        state = halt_manager.engage(reason="two", affected_accounts=("A2",))
        assert set(state.affected_accounts) == {"A1", "A2"}

    def test_state_to_dict_is_json_safe(self, halt_manager: HaltManager) -> None:
        halt_manager.engage(reason="incident")
        payload = halt_manager.state.to_dict()
        assert payload["active"] is True
        assert payload["scope"] == "NEW_ENTRIES"

    @pytest.mark.parametrize(
        ("current", "requested", "expected"),
        [
            (HaltScope.NONE, HaltScope.NEW_ENTRIES, HaltScope.NEW_ENTRIES),
            (HaltScope.NEW_ENTRIES, HaltScope.ALL_TRADING, HaltScope.ALL_TRADING),
            (HaltScope.ALL_TRADING, HaltScope.NEW_ENTRIES, HaltScope.ALL_TRADING),
            (HaltScope.ALL_TRADING, HaltScope.NONE, HaltScope.ALL_TRADING),
        ],
    )
    def test_widest_scope(self, current: HaltScope, requested: HaltScope, expected: HaltScope) -> None:
        assert widest_scope(current, requested) is expected


class TestOrderStateMachine:
    def test_draft_to_approval_is_legal(self) -> None:
        assert can_transition(OrderState.DRAFT, OrderState.PENDING_APPROVAL)

    def test_cannot_skip_approval_to_submitted(self) -> None:
        assert not can_transition(OrderState.DRAFT, OrderState.SUBMITTING)

    def test_submitting_may_end_unknown(self) -> None:
        assert can_transition(OrderState.SUBMITTING, OrderState.UNKNOWN)

    def test_unknown_is_only_resolved_by_reconciliation(self) -> None:
        allowed = allowed_transitions(OrderState.UNKNOWN)
        assert OrderState.RECONCILED in allowed
        # A guess of FILLED is allowed only as a reconciliation outcome, never as an
        # automatic recovery: there is no path back to SUBMITTING (resubmission).
        assert OrderState.SUBMITTING not in allowed

    def test_unknown_never_returns_to_submitting(self) -> None:
        assert not can_transition(OrderState.UNKNOWN, OrderState.SUBMITTING)

    def test_terminal_states_have_no_successors(self) -> None:
        for state in (OrderState.REJECTED_BY_GOVERNANCE, OrderState.RECONCILED):
            assert allowed_transitions(state) == frozenset()

    def test_filled_is_terminal(self) -> None:
        assert is_terminal(OrderState.FILLED)
        assert not is_terminal(OrderState.WORKING)

    def test_filled_may_only_be_reconciled(self) -> None:
        assert allowed_transitions(OrderState.FILLED) == frozenset({OrderState.RECONCILED})

    @pytest.mark.parametrize(
        "state",
        [OrderState.UNKNOWN, OrderState.SUBMITTING, OrderState.CANCEL_REQUESTED],
    )
    def test_states_that_block_new_risk(self, state: OrderState) -> None:
        assert blocks_new_risk(state)

    def test_normal_states_do_not_block_new_risk(self) -> None:
        assert not blocks_new_risk(OrderState.FILLED)
        assert not blocks_new_risk(OrderState.RECONCILED)

    def test_every_state_has_a_transition_entry(self) -> None:
        for state in OrderState:
            assert isinstance(allowed_transitions(state), frozenset)

    def test_cancel_path_is_legal(self) -> None:
        assert can_transition(OrderState.WORKING, OrderState.CANCEL_REQUESTED)
        assert can_transition(OrderState.CANCEL_REQUESTED, OrderState.CANCELLED)

    def test_partial_fill_path_is_legal(self) -> None:
        assert can_transition(OrderState.WORKING, OrderState.PARTIALLY_FILLED)
        assert can_transition(OrderState.PARTIALLY_FILLED, OrderState.FILLED)
