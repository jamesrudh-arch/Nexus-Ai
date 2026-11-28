"""Core guarantees: fail-closed configuration, environment state machine, events, domain types.

These tests pin the properties the specification calls non-negotiable:
- defaults are the restrictive ones;
- unknown state resolves to DISABLED;
- promotion is one stage at a time, de-escalation is always allowed;
- events are never silently dropped;
- canonical instrument identity is venue-independent.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import types
from decimal import Decimal

import pytest

from nexus.core.config import (
    AlertConfig,
    ModelConfig_,
    RiskLimits,
    Settings,
    get_settings,
    reset_settings_cache,
)
from nexus.core.environment import EnvironmentState, can_place_live_order, is_pre_live, promotion_is_valid
from nexus.core.errors import NexusError, Rejected, RejectReason
from nexus.core.ids import new_id, new_idempotency_key
from nexus.core.time import age_seconds, iso_utc, parse_iso, utc_now
from nexus.domain.decision import DecisionRecord, DecisionState, DecisionVerb
from nexus.domain.instrument import AssetClass, CanonicalInstrument, Venue, VenueMapping, VenueStatus
from nexus.events import bus as event_bus
from nexus.events.bus import EventEnvelope, EventPublishError, InMemoryEventBus, NatsEventBus


class TestFailClosedDefaults:
    def test_live_trading_disabled_by_default(self) -> None:
        assert Settings(_env_file=None).live_trading_enabled is False

    def test_environment_disabled_by_default(self) -> None:
        assert Settings(_env_file=None).environment is EnvironmentState.DISABLED

    def test_legal_review_not_assumed(self) -> None:
        assert Settings(_env_file=None).legal_review_complete is False

    def test_owner_authority_not_assumed(self) -> None:
        assert Settings(_env_file=None).owner_live_authority_granted is False

    def test_withdrawal_permission_forbidden(self) -> None:
        assert Settings(_env_file=None).withdrawal_permission_forbidden is True

    def test_paid_models_are_off(self) -> None:
        assert ModelConfig_().allow_paid_apis is False

    def test_models_abstain_when_unavailable(self) -> None:
        assert ModelConfig_().abstain_when_unavailable is True

    def test_sensitive_data_never_goes_to_hosted_models(self) -> None:
        assert ModelConfig_().forbid_sensitive_data_to_hosted_models is True

    def test_local_models_preferred(self) -> None:
        assert ModelConfig_().local_first is True

    def test_sms_and_whatsapp_are_not_configurable(self) -> None:
        # D-019/D-020: these channels do not exist at $0, so they are not settings at all.
        fields = set(AlertConfig.model_fields)
        assert "sms_enabled" not in fields
        assert "whatsapp_enabled" not in fields

    def test_free_alert_channels_enabled(self) -> None:
        alerts = AlertConfig()
        assert (
            alerts.telegram_enabled
            and alerts.webpush_enabled
            and alerts.email_enabled
            and alerts.in_app_enabled
        )

    def test_email_budget_respects_free_tier(self) -> None:
        assert AlertConfig().email_daily_budget <= 300  # Brevo free cap

    def test_conservative_risk_defaults(self) -> None:
        limits = RiskLimits()
        assert limits.max_risk_per_trade_pct == 1.0
        assert limits.max_leverage == 2.0
        assert limits.daily_drawdown_halt_pct == 2.0

    def test_settings_are_cached(self) -> None:
        reset_settings_cache()
        assert get_settings() is get_settings()
        reset_settings_cache()

    def test_hosted_request_budget_below_free_caps(self) -> None:
        assert ModelConfig_().max_daily_hosted_requests <= 1000  # Groq free: 1,000/day


class TestEnvironmentCoercion:
    @pytest.mark.parametrize("raw", ["LIVE", "live", " Live "])
    def test_name_is_accepted(self, raw: str) -> None:
        assert Settings(_env_file=None, environment=raw).environment is EnvironmentState.LIVE  # type: ignore[arg-type]

    @pytest.mark.parametrize("raw", ["NOT_A_STATE", "", "PROD", "TRADING"])
    def test_unknown_name_becomes_disabled(self, raw: str) -> None:
        assert Settings(_env_file=None, environment=raw).environment is EnvironmentState.DISABLED  # type: ignore[arg-type]

    @pytest.mark.parametrize("raw", [99, -1, 1000])
    def test_unknown_number_becomes_disabled(self, raw: int) -> None:
        assert Settings(_env_file=None, environment=raw).environment is EnvironmentState.DISABLED  # type: ignore[arg-type]

    def test_none_becomes_disabled(self) -> None:
        assert Settings(_env_file=None, environment=None).environment is EnvironmentState.DISABLED  # type: ignore[arg-type]

    def test_valid_number_is_accepted(self) -> None:
        assert Settings(_env_file=None, environment=4).environment is EnvironmentState.PAPER  # type: ignore[arg-type]


class TestEnvironmentOrdering:
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
    def test_pre_live_states(self, state: EnvironmentState) -> None:
        assert is_pre_live(state)
        assert not can_place_live_order(state)

    @pytest.mark.parametrize("state", [EnvironmentState.PILOT, EnvironmentState.LIVE])
    def test_live_capable_states(self, state: EnvironmentState) -> None:
        assert not is_pre_live(state)
        assert can_place_live_order(state)

    def test_unknown_state_is_pre_live(self) -> None:
        assert is_pre_live(None)
        assert is_pre_live(999)
        assert not can_place_live_order(None)
        assert not can_place_live_order(999)

    def test_promotion_one_stage_at_a_time(self) -> None:
        assert promotion_is_valid(EnvironmentState.OBSERVE, EnvironmentState.RESEARCH)
        assert not promotion_is_valid(EnvironmentState.OBSERVE, EnvironmentState.LIVE)
        assert not promotion_is_valid(EnvironmentState.PAPER, EnvironmentState.LIVE)

    def test_de_escalation_always_allowed(self) -> None:
        assert promotion_is_valid(EnvironmentState.LIVE, EnvironmentState.DISABLED)
        assert promotion_is_valid(EnvironmentState.PILOT, EnvironmentState.SHADOW)

    def test_same_state_is_not_a_promotion(self) -> None:
        assert promotion_is_valid(EnvironmentState.PAPER, EnvironmentState.PAPER)

    def test_authority_is_strictly_ordered(self) -> None:
        order = list(EnvironmentState)
        assert order == sorted(order, key=lambda s: s.value)
        assert EnvironmentState.DISABLED.value == 0
        assert EnvironmentState.LIVE.value == 6


class TestTimeAndIds:
    def test_iso_utc_has_z_suffix(self) -> None:
        assert iso_utc(utc_now()).endswith("Z")

    def test_parse_round_trip(self) -> None:
        moment = utc_now()
        assert abs((parse_iso(iso_utc(moment)) - moment).total_seconds()) < 0.001

    def test_naive_datetime_rejected_on_format(self) -> None:
        from datetime import datetime

        with pytest.raises(ValueError):
            iso_utc(datetime(2026, 11, 25, 12, 0, 0))

    def test_naive_datetime_rejected_on_parse(self) -> None:
        with pytest.raises(ValueError):
            parse_iso("2026-11-25T12:00:00")

    def test_future_age_is_zero(self) -> None:
        from datetime import timedelta

        assert age_seconds(utc_now() + timedelta(seconds=60)) == 0.0

    def test_ids_are_unique_and_prefixed(self) -> None:
        ids = {new_id("INT") for _ in range(500)}
        assert len(ids) == 500
        assert all(i.startswith("INT-") for i in ids)

    def test_id_prefix_is_validated(self) -> None:
        with pytest.raises(ValueError):
            new_id("")
        with pytest.raises(ValueError):
            new_id("BAD PREFIX!")

    def test_idempotency_keys_are_unique(self) -> None:
        assert len({new_idempotency_key() for _ in range(500)}) == 500


class TestErrors:
    def test_reason_code_is_in_message(self) -> None:
        assert "DATA_STALE" in str(Rejected(RejectReason.DATA_STALE, "quote too old"))

    def test_rejected_is_not_retryable(self) -> None:
        assert Rejected(RejectReason.HALT_ACTIVE).retryable is False

    def test_nexus_error_carries_context(self) -> None:
        error = NexusError(RejectReason.ABSTAIN, "model unavailable", context={"model": "local"})
        assert error.context["model"] == "local"

    def test_reason_codes_are_stable_strings(self) -> None:
        assert RejectReason.LIVE_TRADING_DISABLED.value == "LIVE_TRADING_DISABLED"


class TestEventBus:
    def test_publish_reaches_subscriber(self) -> None:
        bus = InMemoryEventBus()
        received: list[EventEnvelope] = []
        bus.subscribe("nexus.test", received.append)
        bus.publish(EventEnvelope(topic="nexus.test", payload={"a": 1}))
        assert len(received) == 1
        assert received[0].payload == {"a": 1}

    def test_wildcard_subscriber_sees_all(self) -> None:
        bus = InMemoryEventBus()
        seen: list[str] = []
        bus.subscribe("*", lambda e: seen.append(e.topic))
        bus.publish(EventEnvelope(topic="a", payload={}))
        bus.publish(EventEnvelope(topic="b", payload={}))
        assert seen == ["a", "b"]

    def test_unsubscribed_topic_does_not_fire(self) -> None:
        bus = InMemoryEventBus()
        received: list[EventEnvelope] = []
        bus.subscribe("other", received.append)
        bus.publish(EventEnvelope(topic="nexus.test", payload={}))
        assert received == []

    def test_history_is_bounded(self) -> None:
        bus = InMemoryEventBus(history_limit=3)
        for i in range(10):
            bus.publish(EventEnvelope(topic="t", payload={"i": i}))
        assert len(bus.history()) == 3

    def test_history_can_be_filtered(self) -> None:
        bus = InMemoryEventBus()
        bus.publish(EventEnvelope(topic="a", payload={}))
        bus.publish(EventEnvelope(topic="b", payload={}))
        assert len(bus.history("a")) == 1

    def test_publish_after_close_raises(self) -> None:
        bus = InMemoryEventBus()
        bus.close()
        with pytest.raises(EventPublishError):
            bus.publish(EventEnvelope(topic="t", payload={}))

    def test_envelope_is_immutable(self) -> None:
        event = EventEnvelope(topic="t", payload={})
        with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass
            event.topic = "other"  # type: ignore[misc]

    def test_envelope_serialises(self) -> None:
        payload = EventEnvelope(topic="t", payload={"a": 1}).to_dict()
        assert payload["topic"] == "t"
        assert payload["version"] == 1
        assert payload["event_id"].startswith("EVT-")

    def test_nats_without_library_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Holds the fail-closed rule independent of what happens to be installed.

        This used to rely on nats-py being absent from the interpreter, so it silently changed
        meaning the moment the library was installed -- and it then passed for a different reason
        in CI than locally. `None` in sys.modules makes `import nats` raise ImportError wherever
        this runs.
        """
        monkeypatch.setitem(sys.modules, "nats", None)
        bus = NatsEventBus("nats://localhost:4222")
        with pytest.raises(EventPublishError, match="not installed"):
            bus.publish(EventEnvelope(topic="t", payload={}))
        bus.close()


def _nats_loop_threads() -> list[threading.Thread]:
    """Live threads owned by a NatsEventBus bridge. Named, so a leak is attributable."""
    return [t for t in threading.enumerate() if t.name == "nexus-nats" and t.is_alive()]


class _FakeJetStream:
    """Stands in for nats-py's JetStream context. `publish` is a coroutine function, as in the real one."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, payload))


class _FakeClient:
    def __init__(self) -> None:
        self.js = _FakeJetStream()
        self.closed = False

    def jetstream(self) -> _FakeJetStream:  # synchronous in nats-py as well
        return self.js

    async def close(self) -> None:
        self.closed = True


def _install_fake_nats(monkeypatch: pytest.MonkeyPatch, connect=None):  # type: ignore[no-untyped-def]
    """Put a fake `nats` module where the lazy import inside `_ensure_client` will find it."""
    client = _FakeClient()
    urls: list[str] = []

    async def default_connect(url, **options):  # type: ignore[no-untyped-def]
        urls.append(url)
        return client

    module = types.ModuleType("nats")
    module.connect = connect if connect is not None else default_connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nats", module)
    return client, urls


class TestNatsEventBusBridgesTheAsyncTransport:
    """Defect 37: `nats.connect` is a coroutine function, and it was called synchronously.

    Calling it without awaiting returns a coroutine object, which has no `jetstream` attribute, so
    the very first publish raised `EventPublishError` and no event could ever have reached NATS. It
    survived because nothing publishes in Phase 3 and both lines carried `pragma: no cover`, so no
    test executed them: the transport was declared fail-closed and was in fact fail-always.

    These tests drive the bridge with an injected async client rather than a server. That covers
    the part that was wrong -- owning an event loop and awaiting coroutines across a thread
    boundary -- without needing a NATS process, which no test environment here has. Reaching a real
    server stays a VM bring-up item.
    """

    def test_publish_reaches_the_jetstream_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The regression test for defect 37: a synchronous call would fail right here."""
        client, urls = _install_fake_nats(monkeypatch)
        bus = NatsEventBus("nats://nats:4222")
        try:
            bus.publish(EventEnvelope(topic="nexus.test", payload={"a": 1}))

            assert urls == ["nats://nats:4222"], "the URL never reached the async connect"
            assert len(client.js.published) == 1, "the event never reached JetStream"
            topic, raw = client.js.published[0]
            assert topic == "nexus.test"
            envelope = json.loads(raw)
            assert envelope["payload"] == {"a": 1}
            assert envelope["event_id"].startswith("EVT-")
        finally:
            bus.close()

    def test_local_subscribers_still_see_the_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bridging to NATS must not cost the in-process subscribers their copy."""
        client, _ = _install_fake_nats(monkeypatch)
        seen: list[EventEnvelope] = []
        bus = NatsEventBus("nats://nats:4222")
        try:
            bus.subscribe("nexus.test", seen.append)
            bus.publish(EventEnvelope(topic="nexus.test", payload={}))
            assert len(seen) == 1
            assert len(client.js.published) == 1
        finally:
            bus.close()

    def test_a_failed_connect_leaks_no_thread(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def refusing(url, **options):  # type: ignore[no-untyped-def]
            raise OSError("connection refused")

        _install_fake_nats(monkeypatch, connect=refusing)
        bus = NatsEventBus("nats://nats:4222")
        with pytest.raises(EventPublishError, match="cannot connect to NATS"):
            bus.publish(EventEnvelope(topic="t", payload={}))
        bus.close()
        assert _nats_loop_threads() == [], "a failed connect leaked its event loop thread"

    def test_a_stalled_transport_times_out_rather_than_hanging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The bound is the point: the callers are the audit and alert paths."""

        async def stalling(url, **options):  # type: ignore[no-untyped-def]
            await asyncio.sleep(60)

        _install_fake_nats(monkeypatch, connect=stalling)
        monkeypatch.setattr(event_bus, "_CONNECT_TIMEOUT_SECONDS", 0.2)
        bus = NatsEventBus("nats://nats:4222")
        started = time.monotonic()
        try:
            with pytest.raises(EventPublishError):
                bus.publish(EventEnvelope(topic="t", payload={}))
            elapsed = time.monotonic() - started
            assert elapsed < 15, f"the connect was not bounded; it blocked for {elapsed:.1f}s"
        finally:
            bus.close()

    def test_close_stops_the_loop_and_closes_the_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, _ = _install_fake_nats(monkeypatch)
        bus = NatsEventBus("nats://nats:4222")
        bus.publish(EventEnvelope(topic="t", payload={}))
        assert _nats_loop_threads(), "a connected bus should own a running loop thread"

        bus.close()
        assert client.closed is True
        assert _nats_loop_threads() == [], "close left the event loop thread running"

    def test_the_real_connect_is_a_coroutine_function(self) -> None:
        """Pin the measurement the whole bridge rests on, against the real library."""
        nats = pytest.importorskip("nats", reason="nats-py is an optional extra")
        assert asyncio.iscoroutinefunction(nats.connect), (
            "nats.connect is no longer a coroutine function. The bridge in NatsEventBus exists "
            "only because it is one, so that class should be re-examined before trusting it."
        )


class TestInstrumentIdentity:
    def _instrument(self) -> CanonicalInstrument:
        return CanonicalInstrument(
            instrument_id="INS-BTCUSDT-PERP-BYBIT",
            canonical_symbol="BTC/USDT:USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USDT",
            settlement_currency="USDT",
            underlying="BTC/USDT",
            mappings=(
                VenueMapping(
                    venue=Venue.BYBIT,
                    venue_symbol="BTCUSDT",
                    status=VenueStatus.DATA_AVAILABLE,
                    contract_size=Decimal("1"),
                    quote_currency="USDT",
                ),
                VenueMapping(venue=Venue.BINANCE, venue_symbol="BTCUSDT", status=VenueStatus.SUPPORTED),
                VenueMapping(venue=Venue.OKX, venue_symbol="BTC-USDT-SWAP", status=VenueStatus.TRADE_ENABLED),
            ),
        )

    def test_instruments_are_inactive_by_default(self) -> None:
        instrument = CanonicalInstrument(
            instrument_id="INS-X",
            canonical_symbol="X/Y",
            asset_class=AssetClass.CRYPTO_SPOT,
            base_currency="X",
            quote_currency="Y",
            settlement_currency="Y",
        )
        assert instrument.active is False
        assert instrument.data_status == "UNAVAILABLE"

    def test_mapping_lookup_by_venue(self) -> None:
        mapping = self._instrument().mapping_for(Venue.OKX)
        assert mapping is not None
        assert mapping.venue_symbol == "BTC-USDT-SWAP"

    def test_missing_mapping_is_none(self) -> None:
        assert self._instrument().mapping_for(Venue.MT5) is None

    def test_only_verified_venues_are_tradeable(self) -> None:
        assert self._instrument().tradeable_venues() == (Venue.OKX,)

    def test_data_available_is_not_trade_enabled(self) -> None:
        assert not VenueMapping(
            venue=Venue.BYBIT, venue_symbol="BTCUSDT", status=VenueStatus.DATA_AVAILABLE
        ).is_tradeable

    def test_unknown_status_is_not_tradeable(self) -> None:
        assert not VenueMapping(venue=Venue.BYBIT, venue_symbol="BTCUSDT").is_tradeable


class TestDecisionRecord:
    def test_defaults_to_abstain(self) -> None:
        record = DecisionRecord()
        assert record.verb is DecisionVerb.ABSTAIN
        assert record.state is DecisionState.PROPOSED

    def test_transition_stamps_time_and_reason(self) -> None:
        record = DecisionRecord()
        record.transition(
            DecisionState.REJECTED, reason="evidence insufficient", codes=("EVIDENCE_INSUFFICIENT",)
        )
        assert record.state is DecisionState.REJECTED
        assert "EVIDENCE_INSUFFICIENT" in record.reason_codes
        assert "evidence insufficient" in record.rationale

    def test_reason_codes_accumulate(self) -> None:
        record = DecisionRecord()
        record.transition(DecisionState.WAITING_DATA, codes=("DATA_STALE",))
        record.transition(DecisionState.REJECTED, codes=("EVIDENCE_INSUFFICIENT",))
        assert record.reason_codes == ("DATA_STALE", "EVIDENCE_INSUFFICIENT")

    def test_audit_payload_has_no_free_text_model_output(self) -> None:
        record = DecisionRecord(rationale="long narrative from the model", confidence=0.42)
        payload = record.to_audit_payload()
        assert "rationale" not in payload
        assert payload["confidence"] == 0.42
        assert payload["decision_id"].startswith("DEC-")


class TestPhase3Settings:
    """Phase 3 configuration: currency policy (D-025), archive location, free data sources."""

    def test_base_currency_is_usd_for_all_risk_math(self) -> None:
        """D-025: every limit is evaluated in USD, never in a converted figure."""
        cfg = Settings()
        assert cfg.base_currency == "USD"

    def test_reporting_currency_is_ngn_and_is_separate_from_base(self) -> None:
        """D-025: NGN is display/reporting only. It must not be the sizing base."""
        cfg = Settings()
        assert cfg.reporting_currency == "NGN"
        assert cfg.reporting_currency != cfg.base_currency

    def test_currency_codes_are_upper_cased(self) -> None:
        cfg = Settings(base_currency="usd", reporting_currency="ngn", timezone_display="utc")
        assert cfg.base_currency == "USD"
        assert cfg.reporting_currency == "NGN"
        assert cfg.timezone_display == "UTC"

    def test_archive_root_defaults_under_data(self) -> None:
        assert Settings().archive_root == "./data/archive"

    def test_data_sources_default_to_the_free_public_set(self) -> None:
        """D-026: free public sources only — no authenticated or paid feed is configured."""
        assert Settings().enabled_data_sources == (
            "bybit-public",
            "okx-public",
            "binance-vision",
            "dukascopy",
        )

    def test_empty_data_sources_disables_ingestion(self) -> None:
        cfg = Settings(data_sources_enabled="")
        assert cfg.enabled_data_sources == ()
        assert cfg.is_data_source_enabled("bybit-public") is False

    def test_source_lookup_is_case_insensitive_and_strips_whitespace(self) -> None:
        cfg = Settings(data_sources_enabled=" Bybit-Public , okx-public ")
        assert cfg.enabled_data_sources == ("Bybit-Public", "okx-public")
        assert cfg.is_data_source_enabled("bybit-public") is True
        assert cfg.is_data_source_enabled("dukascopy") is False

    def test_no_paid_data_source_is_configurable(self) -> None:
        """D-019: a paid vendor must not appear as a default or a documented option."""
        paid_markers = ("bloomberg", "refinitiv", "polygon", "tiingo", "databento", "iqfeed", "lseg")
        defaults = " ".join(Settings().enabled_data_sources).lower()
        for marker in paid_markers:
            assert marker not in defaults

    def test_live_trading_remains_disabled_with_phase3_defaults(self) -> None:
        """Adding data ingestion must not have loosened any trading gate."""
        cfg = Settings()
        assert cfg.live_trading_enabled is False
        assert cfg.legal_review_complete is False
        assert cfg.owner_live_authority_granted is False
        assert cfg.environment is EnvironmentState.DISABLED
        assert cfg.withdrawal_permission_forbidden is True

    def test_retention_defaults_match_the_d024_ladder(self) -> None:
        """D-024: 1m bars kept 12 months; the ladder itself lives in nexus.archive.retention."""
        cfg = Settings()
        assert cfg.market_data_retention_days >= 365
        from nexus.archive.retention import default_tiers

        tiers = {t.interval: t for t in default_tiers()}
        assert tiers["tick"].max_age_days == 30
        assert tiers["1m"].max_age_days == 365
        assert tiers["5m"].keeps_forever is True
        assert tiers["1d"].keeps_forever is True

    def test_config_version_is_bound_to_the_package_version(self) -> None:
        """The API, the docs and the config must never disagree about the running build."""
        from nexus import __version__

        assert Settings().version == __version__
        assert __version__ == "0.2.0"

    def test_phase3_phase_gate_reports_market_data_but_no_orders(self) -> None:
        """Phase 3 added data reading. That must not read as trading capability."""
        from nexus import PHASE_GATE, __phase__

        assert __phase__ == "3-market-data"
        assert PHASE_GATE["phase"] == 3
        assert PHASE_GATE["market_data_sources"] is True
        assert PHASE_GATE["order_capability"] is False
        assert PHASE_GATE["venue_adapters"] is False
        assert PHASE_GATE["real_money_orders_possible"] is False
