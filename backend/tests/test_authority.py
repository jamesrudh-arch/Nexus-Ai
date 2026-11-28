"""Live-authority gate tests (Section 2, Section 34, D-004, D-013).

The central safety property: with default configuration, live authority is DENIED, and it
stays denied unless *every* independent gate is satisfied simultaneously.
"""

from __future__ import annotations

import pytest

from nexus.core.config import Settings
from nexus.core.environment import EnvironmentState
from nexus.risk.authority import LiveAuthority, LiveAuthorityStatus, evaluate_authority

ALL_RUNTIME_GATES = {
    "phase_gate_complete": True,
    "venue_live_verified": True,
    "mandate_active": True,
    "data_quality_ok": True,
    "reconciliation_ok": True,
}


class TestDefaultDenial:
    def test_default_settings_deny(self, settings: Settings) -> None:
        authority = evaluate_authority(settings)
        assert authority.status is LiveAuthorityStatus.DENIED
        assert not authority.granted

    def test_default_reasons_name_every_missing_gate(self, settings: Settings) -> None:
        reasons = evaluate_authority(settings).blocking_reasons
        assert "LIVE_TRADING_DISABLED" in reasons
        assert "LEGAL_REVIEW_NOT_COMPLETE" in reasons
        assert "OWNER_LIVE_AUTHORITY_NOT_GRANTED" in reasons
        assert "PHASE_GATE_INCOMPLETE" in reasons
        assert "VENUE_NOT_LIVE_VERIFIED" in reasons
        assert "MANDATE_NOT_FOUND" in reasons
        assert any(r.startswith("ENVIRONMENT_NOT_AUTHORIZED") for r in reasons)

    def test_halt_blocks_even_when_all_static_gates_pass(self, live_capable_settings: Settings) -> None:
        authority = evaluate_authority(live_capable_settings, halt_active=True, **ALL_RUNTIME_GATES)
        assert not authority.granted
        assert "HALT_ACTIVE" in authority.blocking_reasons

    def test_kill_switch_blocks_everything(self, live_capable_settings: Settings) -> None:
        authority = evaluate_authority(live_capable_settings, kill_switch_active=True, **ALL_RUNTIME_GATES)
        assert not authority.granted
        assert "KILL_SWITCH_ACTIVE" in authority.blocking_reasons

    def test_stale_data_blocks(self, live_capable_settings: Settings) -> None:
        gates = {**ALL_RUNTIME_GATES, "data_quality_ok": False}
        authority = evaluate_authority(live_capable_settings, **gates)
        assert not authority.granted
        assert "DATA_STALE" in authority.blocking_reasons

    def test_reconciliation_mismatch_blocks(self, live_capable_settings: Settings) -> None:
        gates = {**ALL_RUNTIME_GATES, "reconciliation_ok": False}
        authority = evaluate_authority(live_capable_settings, **gates)
        assert not authority.granted
        assert "RECONCILIATION_MISMATCH" in authority.blocking_reasons

    def test_legal_review_alone_is_not_enough(self) -> None:
        cfg = Settings(_env_file=None, legal_review_complete=True)
        authority = evaluate_authority(cfg, **ALL_RUNTIME_GATES)
        assert not authority.granted
        assert "LEGAL_REVIEW_NOT_COMPLETE" not in authority.blocking_reasons
        assert "LIVE_TRADING_DISABLED" in authority.blocking_reasons


class TestGranting:
    def test_all_gates_satisfied_at_live_grants(self, live_capable_settings: Settings) -> None:
        authority = evaluate_authority(live_capable_settings, **ALL_RUNTIME_GATES)
        assert authority.granted
        assert authority.status is LiveAuthorityStatus.GRANTED
        assert authority.blocking_reasons == ()

    def test_pilot_environment_also_grants(self) -> None:
        cfg = Settings(
            _env_file=None,
            environment=EnvironmentState.PILOT,
            live_trading_enabled=True,
            legal_review_complete=True,
            owner_live_authority_granted=True,
        )
        assert evaluate_authority(cfg, **ALL_RUNTIME_GATES).granted

    @pytest.mark.parametrize(
        "state",
        [
            EnvironmentState.DISABLED,
            EnvironmentState.OBSERVE,
            EnvironmentState.RESEARCH,
            EnvironmentState.SHADOW,
            EnvironmentState.PAPER,
        ],
    )
    def test_pre_live_environments_never_grant(self, state: EnvironmentState) -> None:
        cfg = Settings(
            _env_file=None,
            environment=state,
            live_trading_enabled=True,
            legal_review_complete=True,
            owner_live_authority_granted=True,
        )
        authority = evaluate_authority(cfg, **ALL_RUNTIME_GATES)
        assert not authority.granted
        assert any(r.startswith("ENVIRONMENT_NOT_AUTHORIZED") for r in authority.blocking_reasons)


class TestUnknownStateFailsClosed:
    def test_unknown_environment_becomes_disabled(self) -> None:
        cfg = Settings(
            _env_file=None,
            live_trading_enabled=True,
            legal_review_complete=True,
            owner_live_authority_granted=True,
        )
        authority = evaluate_authority(cfg, environment=None, **ALL_RUNTIME_GATES)
        # environment=None means "use settings", which defaults to DISABLED
        assert authority.environment is EnvironmentState.DISABLED
        assert not authority.granted

    def test_garbage_environment_value_is_disabled(self) -> None:
        cfg = Settings(_env_file=None)
        authority = evaluate_authority(cfg, environment="NOT_A_STATE", **ALL_RUNTIME_GATES)  # type: ignore[arg-type]
        assert authority.environment is EnvironmentState.DISABLED
        assert not authority.granted

    def test_to_dict_exposes_every_gate(self, live_capable_settings: Settings) -> None:
        payload = evaluate_authority(live_capable_settings, **ALL_RUNTIME_GATES).to_dict()
        assert payload["status"] == "GRANTED"
        assert set(payload["gates"]) >= {
            "live_trading_enabled",
            "legal_review_complete",
            "owner_live_authority_granted",
            "phase_gate_complete",
            "venue_live_verified",
            "mandate_active",
            "halt_active",
            "kill_switch_active",
            "data_quality_ok",
            "reconciliation_ok",
        }


class TestAuthorityObject:
    def test_frozen_dataclass_is_immutable(self) -> None:
        authority = LiveAuthority(
            environment=EnvironmentState.PAPER,
            live_trading_enabled=False,
            legal_review_complete=False,
            owner_live_authority_granted=False,
            phase_gate_complete=False,
            venue_live_verified=False,
            mandate_active=False,
        )
        with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass raises
            authority.live_trading_enabled = True  # type: ignore[misc]
        assert not authority.granted
