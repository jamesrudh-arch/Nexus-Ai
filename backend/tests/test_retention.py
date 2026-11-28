"""Tiered retention (D-024) and the disk-watermark fail-safe.

The two failures this prevents: filling the disk that also holds the audit chain, and
deleting evidence whose replacement tier was never written. A DELETE is only planned when the
coarser tier demonstrably reaches back far enough; otherwise the plan refuses and reports
``is_safe=False``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.archive.retention import (
    DEFAULT_DISK_FORCE_PCT,
    DEFAULT_DISK_WARN_PCT,
    CoverageWindow,
    DiskPressure,
    RetentionAction,
    RetentionPolicy,
    RetentionTier,
    build_inventory,
    default_tiers,
    disk_pressure,
    estimate_bytes_per_day,
)
from nexus.data.records import BarRecord

D = Decimal
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def window(
    instrument_id: str,
    interval: str,
    *,
    earliest: datetime | None,
    latest: datetime | None = NOW,
    count: int = 100,
) -> CoverageWindow:
    return CoverageWindow(
        instrument_id=instrument_id,
        interval=interval,
        earliest=earliest,
        latest=latest,
        record_count=count,
        resolution_note=f"{interval} data",
    )


def minute_bar(at: datetime, *, symbol: str = "BTCUSDT", confirmed: bool = True) -> BarRecord:
    return BarRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue="BYBIT",
        venue_symbol=symbol,
        interval="1m",
        open_time=at,
        close_time=at + timedelta(minutes=1),
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("10"),
        confirmed=confirmed,
        source="TEST",
    )


@pytest.fixture
def policy() -> RetentionPolicy:
    return RetentionPolicy(now_fn=lambda: NOW)


class TestDefaultTiers:
    def test_the_ladder_matches_d024(self) -> None:
        """D-024: ticks 30d -> 1m bars 12mo -> 5m/daily indefinitely."""
        tiers = {t.interval: t for t in default_tiers()}
        assert tiers["tick"].max_age_days == 30
        assert tiers["tick"].rollup_to == "1m"
        assert tiers["1m"].max_age_days == 365
        assert tiers["1m"].rollup_to == "5m"
        assert tiers["5m"].max_age_days is None
        assert tiers["1d"].max_age_days is None

    def test_terminal_tiers_keep_forever(self) -> None:
        tiers = {t.interval: t for t in default_tiers()}
        assert tiers["5m"].keeps_forever is True
        assert tiers["1d"].keeps_forever is True
        assert tiers["tick"].keeps_forever is False

    def test_ticks_are_not_kept_forever(self) -> None:
        """The whole point of the tiering: ticks cannot accumulate without limit on 200 GB."""
        tiers = {t.interval: t for t in default_tiers()}
        assert tiers["tick"].keeps_forever is False
        assert tiers["tick"].max_age_days is not None

    def test_every_rollup_target_is_itself_a_tier(self, policy: RetentionPolicy) -> None:
        intervals = {t.interval for t in policy.tiers}
        for tier in policy.tiers:
            if tier.rollup_to is not None:
                assert tier.rollup_to in intervals

    def test_broken_ladder_is_refused_at_construction(self) -> None:
        """A tier that rolls up to nothing is a data-loss machine."""
        with pytest.raises(ValueError, match="not itself a tier"):
            RetentionPolicy(tiers=[RetentionTier("tick", 30, "1m", "no 1m tier defined")])

    def test_cutoff_is_none_for_indefinite_tiers(self, policy: RetentionPolicy) -> None:
        assert policy.effective_cutoff("5m", now=NOW) is None
        assert policy.effective_cutoff("1d", now=NOW) is None

    def test_cutoff_for_ticks_is_thirty_days(self, policy: RetentionPolicy) -> None:
        cutoff = policy.effective_cutoff("tick", now=NOW)
        assert cutoff is not None
        # Under OK disk pressure the cutoff is exactly the configured age.
        assert cutoff <= NOW - timedelta(days=29)


class TestDiskPressure:
    def test_reads_real_filesystem_usage(self, tmp_path: object) -> None:
        pressure = disk_pressure(tmp_path)  # type: ignore[arg-type]
        assert isinstance(pressure, DiskPressure)
        assert pressure.total_bytes > 0
        assert pressure.used_bytes >= 0
        assert pressure.free_bytes >= 0
        assert 0.0 <= pressure.used_pct <= 100.0
        assert pressure.level in {"OK", "WARN", "FORCE"}

    def test_nonexistent_path_falls_back_to_cwd(self) -> None:
        """Must not crash when the archive root has not been created yet."""
        pressure = disk_pressure("/nonexistent/path/that/does/not/exist")
        assert pressure.total_bytes > 0

    def test_thresholds_are_ordered(self) -> None:
        assert DEFAULT_DISK_WARN_PCT < DEFAULT_DISK_FORCE_PCT

    def test_custom_thresholds_drive_the_level(self, tmp_path: object) -> None:
        """A threshold of 0 forces FORCE; 100 keeps it OK. Proves the level is computed."""
        forced = disk_pressure(tmp_path, warn_pct=0.0, force_pct=0.0)  # type: ignore[arg-type]
        assert forced.level == "FORCE"
        relaxed = disk_pressure(tmp_path, warn_pct=100.0, force_pct=100.0)  # type: ignore[arg-type]
        assert relaxed.level == "OK"

    def test_payload_is_json_safe(self, tmp_path: object) -> None:
        payload = disk_pressure(tmp_path).to_dict()  # type: ignore[arg-type]
        assert set(payload) == {"path", "total_gb", "used_gb", "free_gb", "used_pct", "level"}
        assert isinstance(payload["total_gb"], float)


class TestPlanSafety:
    def test_no_actions_when_nothing_has_expired(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(
            inventory=[window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=1))],
            now=NOW,
        )
        assert plan.actions == ()
        assert plan.is_safe is True

    def test_expired_ticks_without_a_1m_replacement_are_refused(self, policy: RetentionPolicy) -> None:
        """The core safety property: never delete evidence that has no replacement."""
        plan = policy.plan(
            inventory=[window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=400))],
            now=NOW,
        )
        assert len(plan.actions) == 1
        action = plan.actions[0]
        assert action.action == "REFUSE"
        assert action.interval == "tick"
        assert action.rollup_to == "1m"
        assert "no replacement" in action.reason
        assert plan.is_safe is False
        assert len(plan.deletes) == 0

    def test_expired_ticks_with_1m_coverage_are_deleted(self, policy: RetentionPolicy) -> None:
        # 40d expires the tick tier (>30d); 100d keeps the 1m tier inside its 365d allowance,
        # so the only planned action is the tick delete. A 1m window older than 365d would
        # itself expire and add a second action — that is correct, but a different test.
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=40)),
                window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=100)),
            ],
            now=NOW,
        )
        deletes = plan.deletes
        assert len(deletes) == 1
        assert deletes[0].action == "DELETE"
        assert deletes[0].interval == "tick"
        assert "superseded by 1m coverage" in deletes[0].reason
        assert plan.is_safe is True

    def test_replacement_that_does_not_reach_back_far_enough_is_refused(
        self, policy: RetentionPolicy
    ) -> None:
        """1m coverage starting *later* than the ticks would lose the older period."""
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=400)),
                window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=100)),
            ],
            now=NOW,
        )
        assert len(plan.refusals) == 1
        assert len(plan.deletes) == 0
        assert "does not reach back" in plan.refusals[0].reason

    def test_exact_boundary_coverage_is_accepted(self, policy: RetentionPolicy) -> None:
        tick_earliest = NOW - timedelta(days=40)
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=tick_earliest),
                window("INS-BTC-USDT-USDT", "1m", earliest=tick_earliest),
            ],
            now=NOW,
        )
        assert len(plan.deletes) == 1

    def test_a_tier_with_no_rollup_target_refuses_permanent_loss(self) -> None:
        """If a tier expires and has nowhere to roll up, deletion is permanent loss."""
        policy = RetentionPolicy(
            tiers=[RetentionTier("tick", 30, None, "terminal tier")],
            now_fn=lambda: NOW,
        )
        plan = policy.plan(
            inventory=[window("INS-X", "tick", earliest=NOW - timedelta(days=60))],
            now=NOW,
        )
        assert len(plan.refusals) == 1
        assert "permanent evidence loss" in plan.refusals[0].reason
        assert plan.is_safe is False

    def test_indefinite_tiers_never_produce_deletes(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "5m", earliest=NOW - timedelta(days=5000)),
                window("INS-BTC-USDT-USDT", "1d", earliest=NOW - timedelta(days=5000)),
            ],
            now=NOW,
        )
        assert plan.deletes == ()

    def test_window_without_an_earliest_time_is_not_planned(self, policy: RetentionPolicy) -> None:
        """Unknown coverage start must not trigger deletion."""
        plan = policy.plan(
            inventory=[window("INS-BTC-USDT-USDT", "tick", earliest=None)],
            now=NOW,
        )
        assert plan.actions == ()

    def test_plan_is_separate_from_execution(self, policy: RetentionPolicy) -> None:
        """Planning must not mutate anything — the owner sees consequences first."""
        inventory = [
            window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=400)),
            window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=500)),
        ]
        plan = policy.plan(inventory=inventory, now=NOW)
        assert all(a.executed is False for a in plan.actions)
        assert inventory[0].record_count == 100  # untouched

    def test_multiple_instruments_are_planned_independently(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=40)),
                window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=100)),
                window("INS-EUR-USD", "tick", earliest=NOW - timedelta(days=40)),
                # EURUSD has no 1m coverage -> must be refused, not deleted
            ],
            now=NOW,
        )
        assert len(plan.deletes) == 1
        assert len(plan.refusals) == 1
        assert plan.deletes[0].records_affected == 100
        assert "INS-EUR-USD" in plan.refusals[0].reason
        assert plan.is_safe is False

    def test_an_expired_middle_tier_without_its_own_replacement_is_also_refused(
        self, policy: RetentionPolicy
    ) -> None:
        """Each tier is judged on its own: 1m older than 365d needs 5m coverage too."""
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=40)),
                window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=500)),
            ],
            now=NOW,
        )
        assert len(plan.deletes) == 1  # tick -> 1m is covered (1m reaches back further)
        assert len(plan.refusals) == 1  # 1m -> 5m has no coverage at all
        assert plan.refusals[0].interval == "1m"
        assert plan.is_safe is False

    def test_coverage_after_describes_resolution_honestly(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(
            inventory=[
                window("INS-BTC-USDT-USDT", "tick", earliest=NOW - timedelta(days=10), count=5000),
                window("INS-BTC-USDT-USDT", "1m", earliest=NOW - timedelta(days=200), count=9000),
            ],
            now=NOW,
        )
        note = plan.coverage_after["INS-BTC-USDT-USDT"]
        assert "tick" in note
        assert "1m" in note
        assert "finest resolution" in note

    def test_empty_inventory_yields_an_empty_safe_plan(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(inventory=[], now=NOW)
        assert plan.actions == ()
        assert plan.is_safe is True
        assert plan.coverage_after == {}

    def test_plan_payload_is_json_safe(self, policy: RetentionPolicy) -> None:
        plan = policy.plan(
            inventory=[window("INS-X", "tick", earliest=NOW - timedelta(days=400))],
            now=NOW,
        )
        payload = plan.to_dict()
        assert payload["is_safe"] is False
        assert payload["generated_at"].endswith("Z")
        assert payload["tiers"][0]["interval"] == "tick"
        assert payload["actions"][0]["action"] == "REFUSE"


class TestRollupAction:
    def test_rollup_produces_coarser_bars(self, policy: RetentionPolicy) -> None:
        # 10:00..10:09 -> exactly two 5m buckets (10:00 and 10:05).
        anchor = NOW - timedelta(hours=2)
        source = [minute_bar(anchor + timedelta(minutes=m)) for m in range(10)]
        rolled, action = policy.rollup(
            source,
            target_interval="5m",
            instrument_id="INS-BTC-USDT-USDT",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            now=NOW,
        )
        assert len(rolled) == 2
        assert action.action == "ROLLUP"
        assert action.executed is True
        assert action.records_affected == 10
        assert action.records_produced == 2
        assert all(b.interval == "5m" for b in rolled)

    def test_illegal_rollup_is_refused(self, policy: RetentionPolicy) -> None:
        source = [minute_bar(NOW - timedelta(hours=2))]
        rolled, action = policy.rollup(
            source,
            target_interval="1s",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=NOW,
        )
        assert rolled == ()
        assert action.action == "REFUSE"
        assert action.executed is False
        assert "cannot be rolled up" in action.reason

    def test_empty_source_is_refused_not_silently_accepted(self, policy: RetentionPolicy) -> None:
        rolled, action = policy.rollup(
            [],
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=NOW,
        )
        assert rolled == ()
        assert action.action == "REFUSE"
        assert "no source bars" in action.reason

    def test_rollup_action_payload_is_audit_safe(self, policy: RetentionPolicy) -> None:
        anchor = NOW - timedelta(hours=2)
        source = [minute_bar(anchor + timedelta(minutes=m)) for m in range(10)]
        _, action = policy.rollup(
            source,
            target_interval="5m",
            instrument_id="I",
            venue="V",
            venue_symbol="S",
            now=NOW,
        )
        payload = action.to_audit_payload()
        assert payload["action"] == "ROLLUP"
        assert payload["executed"] is True
        assert payload["at"].endswith("Z")
        assert isinstance(payload["reason"], str)


class TestActionModel:
    def test_action_defaults_to_not_executed(self) -> None:
        action = RetentionAction(
            action="DELETE",
            interval="tick",
            rollup_to="1m",
            records_affected=1,
            records_produced=0,
            bytes_freed_estimate=0,
            reason="test",
        )
        assert action.executed is False
        assert action.at is None
        assert action.to_audit_payload()["executed"] is False


class TestInventoryBuilding:
    def test_rows_become_coverage_windows(self) -> None:
        rows = [
            {
                "instrument_id": "INS-BTC-USDT-USDT",
                "interval": "1m",
                "earliest": NOW - timedelta(days=10),
                "latest": NOW,
                "count": 1440,
            },
        ]
        inventory = build_inventory(rows)
        assert len(inventory) == 1
        assert inventory[0].instrument_id == "INS-BTC-USDT-USDT"
        assert inventory[0].record_count == 1440
        assert "1m bars" in inventory[0].resolution_note

    def test_ticks_are_labelled_as_full_resolution(self) -> None:
        inventory = build_inventory(
            [{"instrument_id": "I", "interval": "tick", "earliest": NOW, "latest": NOW, "count": 5}],
        )
        assert inventory[0].resolution_note == "full-resolution ticks"

    def test_non_standard_interval_is_labelled_honestly(self) -> None:
        inventory = build_inventory(
            [{"instrument_id": "I", "interval": "7m", "earliest": NOW, "latest": NOW, "count": 5}],
        )
        assert "non-standard interval" in inventory[0].resolution_note

    def test_missing_fields_do_not_fabricate_values(self) -> None:
        inventory = build_inventory([{"interval": "1m"}])
        assert inventory[0].instrument_id == "UNKNOWN"
        assert inventory[0].record_count == 0
        assert inventory[0].earliest is None
        assert inventory[0].span_days is None

    def test_span_days_is_computed(self) -> None:
        inventory = build_inventory(
            [
                {
                    "instrument_id": "I",
                    "interval": "1m",
                    "earliest": NOW - timedelta(days=3),
                    "latest": NOW,
                    "count": 1,
                },
            ],
        )
        assert inventory[0].span_days == pytest.approx(3.0)

    def test_payload_is_json_safe(self) -> None:
        inventory = build_inventory(
            [
                {
                    "instrument_id": "I",
                    "interval": "1m",
                    "earliest": NOW,
                    "latest": NOW,
                    "count": 1,
                },
            ],
        )
        payload = inventory[0].to_dict()
        assert payload["earliest"].endswith("Z")
        assert payload["record_count"] == 1


class TestSizingEstimate:
    def test_estimate_scales_with_record_count(self) -> None:
        small = estimate_bytes_per_day(1_000)
        large = estimate_bytes_per_day(1_000_000)
        assert large > small
        assert small == pytest.approx(24_000.0)

    def test_custom_record_size(self) -> None:
        assert estimate_bytes_per_day(10, bytes_per_record=100.0) == pytest.approx(1000.0)
