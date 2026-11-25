"""Instrument master (Phase 3): certification ladder, collisions, staged activation.

These tests pin the governance properties that keep a wrong symbol from becoming a wrong
trade: nothing active by default, capability states never skip, data is not permission, and
reverse lookups are unique.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nexus.core.ids import iso_utc
from nexus.domain.instrument import AssetClass, Venue, VenueMapping, VenueStatus
from nexus.instruments.registry import (
    CERTIFICATION_ORDER,
    CertificationRejected,
    InstrumentRegistry,
    UnknownInstrument,
    build_instrument,
    certification_rank,
    coverage_report,
    is_certification_advance,
)

D = Decimal
FIXED_NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def _mapping(
    venue: Venue = Venue.BYBIT,
    symbol: str = "BTCUSDT",
    *,
    contract_size: Decimal | None = D("1"),
    tick_size: Decimal | None = D("0.01"),
) -> VenueMapping:
    return VenueMapping(
        venue=venue,
        venue_symbol=symbol,
        contract_size=contract_size,
        tick_size=tick_size,
        quote_currency="USDT",
    )


def _btc_instrument() -> object:
    return build_instrument(
        canonical_symbol="BTC/USDT:USDT",
        asset_class=AssetClass.CRYPTO_PERP,
        base_currency="BTC",
        quote_currency="USDT",
        mappings=[_mapping()],
        notes="Bybit USDT-margined perpetual",
    )


@pytest.fixture
def registry() -> InstrumentRegistry:
    return InstrumentRegistry(now_fn=lambda: FIXED_NOW)


class TestCertificationLadder:
    def test_order_is_the_documented_ladder(self) -> None:
        assert [s.value for s in CERTIFICATION_ORDER] == [
            "UNKNOWN",
            "SUPPORTED",
            "CONNECTED",
            "DATA_AVAILABLE",
            "TRADE_ENABLED",
            "LIVE_VERIFIED",
        ]

    def test_ranks_are_strictly_increasing(self) -> None:
        ranks = [certification_rank(s) for s in CERTIFICATION_ORDER]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)

    @pytest.mark.parametrize(
        ("current", "target", "expected"),
        [
            (VenueStatus.UNKNOWN, VenueStatus.SUPPORTED, True),
            (VenueStatus.SUPPORTED, VenueStatus.CONNECTED, True),
            (VenueStatus.CONNECTED, VenueStatus.DATA_AVAILABLE, True),
            (VenueStatus.DATA_AVAILABLE, VenueStatus.TRADE_ENABLED, True),
            (VenueStatus.TRADE_ENABLED, VenueStatus.LIVE_VERIFIED, True),
            (VenueStatus.UNKNOWN, VenueStatus.CONNECTED, False),  # skip
            (VenueStatus.UNKNOWN, VenueStatus.LIVE_VERIFIED, False),  # big skip
            (VenueStatus.DATA_AVAILABLE, VenueStatus.TRADE_ENABLED, True),
            (VenueStatus.TRADE_ENABLED, VenueStatus.DATA_AVAILABLE, False),  # demotion
            (VenueStatus.LIVE_VERIFIED, VenueStatus.LIVE_VERIFIED, False),  # same
        ],
    )
    def test_advance_detection(self, current: VenueStatus, target: VenueStatus, expected: bool) -> None:
        assert is_certification_advance(current, target) is expected


class TestRegistration:
    def test_registered_instrument_is_never_active(self, registry: InstrumentRegistry) -> None:
        """D-002: staged activation. A caller cannot sneak an active instrument in."""
        forced_active = replace(_btc_instrument(), active=True)
        stored = registry.register(forced_active)
        assert stored.active is False
        assert registry.active() == ()

    def test_register_is_idempotent(self, registry: InstrumentRegistry) -> None:
        instrument = _btc_instrument()
        registry.register(instrument)
        registry.register(instrument)
        assert len(registry) == 1
        assert len(registry.changes) == 1  # a no-op must not manufacture an audit record

    def test_duplicate_canonical_symbol_under_different_id_is_refused(
        self, registry: InstrumentRegistry
    ) -> None:
        registry.register(_btc_instrument())
        impostor = build_instrument(
            canonical_symbol="BTC/USDT:USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USDT",
            mappings=[_mapping(venue=Venue.OKX, symbol="BTC-USDT-SWAP")],
        )
        impostor = replace(impostor, instrument_id="INS-SOMETHING-ELSE")
        with pytest.raises(CertificationRejected, match="already registered"):
            registry.register(impostor)

    def test_venue_symbol_collision_is_refused(self, registry: InstrumentRegistry) -> None:
        """Two canonical instruments claiming the same (venue, symbol) is a data bug."""
        registry.register(_btc_instrument())
        rival = build_instrument(
            canonical_symbol="BTC/USD:BTC",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USD",
            mappings=[_mapping(venue=Venue.BYBIT, symbol="BTCUSDT")],
        )
        with pytest.raises(CertificationRejected, match="already bound"):
            registry.register(rival)

    def test_symbol_is_normalised_to_upper(self, registry: InstrumentRegistry) -> None:
        instrument = build_instrument(
            canonical_symbol="btc/usdt:usdt",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USDT",
        )
        stored = registry.register(instrument)
        assert stored.canonical_symbol == "BTC/USDT:USDT"
        assert registry.by_symbol("BTC/USDT:USDT") is not None

    def test_unknown_instrument_raises_typed_error(self, registry: InstrumentRegistry) -> None:
        with pytest.raises(UnknownInstrument):
            registry.require("INS-NOPE")
        assert registry.get("INS-NOPE") is None


class TestResolution:
    def test_resolve_maps_venue_symbol_to_canonical(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        resolved = registry.resolve(Venue.BYBIT, "BTCUSDT")
        assert resolved is not None
        instrument, mapping = resolved
        assert instrument.canonical_symbol == "BTC/USDT:USDT"
        assert mapping.venue is Venue.BYBIT

    def test_venue_symbol_is_matched_exactly_not_case_folded(self, registry: InstrumentRegistry) -> None:
        """Venue symbols are case-significant identifiers, not free text.

        Folding case would let a feed's ``btcusdt`` silently resolve to a mapping registered
        as ``BTCUSDT``, and an unmapped casing would look like a hit. An exact miss is
        reported as unknown, which downstream treats as INSTRUMENT_UNKNOWN.
        """
        registry.register(_btc_instrument())
        assert registry.resolve(Venue.BYBIT, "BTCUSDT") is not None
        assert registry.resolve(Venue.BYBIT, "btcusdt") is None

    def test_unknown_venue_symbol_returns_none_not_a_guess(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        assert registry.resolve(Venue.BYBIT, "ETHUSDT") is None
        assert registry.resolve(Venue.OKX, "BTCUSDT") is None

    def test_same_symbol_at_different_venues_maps_to_different_instruments(
        self, registry: InstrumentRegistry
    ) -> None:
        """BTCUSD on a CFD broker is not BTCUSDT on an exchange — the whole point."""
        registry.register(_btc_instrument())
        cfd = build_instrument(
            canonical_symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USD",
            mappings=[_mapping(venue=Venue.MT5, symbol="BTCUSD", contract_size=D("1"))],
        )
        registry.register(cfd)
        perp = registry.resolve(Venue.BYBIT, "BTCUSDT")
        broker = registry.resolve(Venue.MT5, "BTCUSD")
        assert perp is not None and broker is not None
        assert perp[0].instrument_id != broker[0].instrument_id


class TestCertification:
    def test_cannot_skip_rungs(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(CertificationRejected, match="one step at a time"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                VenueStatus.TRADE_ENABLED,
                evidence="would be nice",
            )

    def test_full_ladder_walk(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence=f"proved {status.value}")
        instrument = registry.require("INS-BTC-USDT-USDT")
        mapping = instrument.mapping_for(Venue.BYBIT)
        assert mapping is not None
        assert mapping.status is VenueStatus.LIVE_VERIFIED
        assert mapping.is_tradeable is True

    def test_empty_evidence_is_refused(self, registry: InstrumentRegistry) -> None:
        """Certification without proof is just a claim."""
        registry.register(_btc_instrument())
        for evidence in ("", "   ", "\n"):
            with pytest.raises(CertificationRejected, match="requires evidence"):
                registry.certify(
                    "INS-BTC-USDT-USDT",
                    Venue.BYBIT,
                    VenueStatus.SUPPORTED,
                    evidence=evidence,
                )

    def test_demotion_is_allowed_and_recorded(self, registry: InstrumentRegistry) -> None:
        """Losing access is not an error to hide — it must be recorded."""
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:4]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok")
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.SUPPORTED,
            evidence="venue withdrew data entitlement",
        )
        instrument = registry.require("INS-BTC-USDT-USDT")
        mapping = instrument.mapping_for(Venue.BYBIT)
        assert mapping is not None
        assert mapping.status is VenueStatus.SUPPORTED
        de_certifications = [c for c in registry.changes if c.kind == "DE_CERTIFY"]
        assert len(de_certifications) == 1
        assert de_certifications[0].from_status == "DATA_AVAILABLE"

    def test_same_status_is_a_no_op(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        before = len(registry.changes)
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.UNKNOWN, evidence="unchanged")
        assert len(registry.changes) == before

    def test_certify_unknown_venue_mapping_is_refused(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(CertificationRejected, match="no mapping"):
            registry.certify("INS-BTC-USDT-USDT", Venue.OKX, VenueStatus.SUPPORTED, evidence="x")

    def test_data_available_does_not_imply_tradeable(self, registry: InstrumentRegistry) -> None:
        """Seeing a price is not permission to trade on it."""
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:4]:  # up to DATA_AVAILABLE
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok")
        instrument = registry.require("INS-BTC-USDT-USDT")
        mapping = instrument.mapping_for(Venue.BYBIT)
        assert mapping is not None
        assert mapping.status is VenueStatus.DATA_AVAILABLE
        assert mapping.is_tradeable is False
        assert instrument.tradeable_venues() == ()
        assert registry.tradeable() == ()


class TestAddMapping:
    def test_new_mapping_always_starts_unknown(self, registry: InstrumentRegistry) -> None:
        """A mapping cannot be born certified."""
        registry.register(_btc_instrument())
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.SUPPORTED, evidence="adapter written")
        pre_certified = VenueMapping(
            venue=Venue.OKX,
            venue_symbol="BTC-USDT-SWAP",
            status=VenueStatus.LIVE_VERIFIED,  # a lie
            contract_size=D("0.01"),
        )
        updated = registry.add_mapping("INS-BTC-USDT-USDT", pre_certified, source="okx instruments-info")
        mapping = updated.mapping_for(Venue.OKX)
        assert mapping is not None
        assert mapping.status is VenueStatus.UNKNOWN

    def test_duplicate_venue_mapping_refused(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(CertificationRejected, match="already mapped"):
            registry.add_mapping("INS-BTC-USDT-USDT", _mapping())

    def test_mapping_bound_to_other_instrument_refused(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        other = build_instrument(
            canonical_symbol="ETH/USDT:USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="ETH",
            quote_currency="USDT",
        )
        registry.register(other)
        with pytest.raises(CertificationRejected, match="is bound to"):
            registry.add_mapping("INS-ETH-USDT-USDT", _mapping(venue=Venue.BYBIT, symbol="BTCUSDT"))


class TestStagedActivation:
    def test_activation_requires_a_reason(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(CertificationRejected, match="requires a reason"):
            registry.activate("INS-BTC-USDT-USDT", reason="  ")

    def test_research_activation_needs_no_certification(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        updated = registry.activate("INS-BTC-USDT-USDT", reason="observe-only research")
        assert updated.active is True
        assert registry.active() == (updated,)

    def test_trading_activation_refused_without_trade_enabled(self, registry: InstrumentRegistry) -> None:
        """The key property: data availability never buys trading activation."""
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:4]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok")
        with pytest.raises(CertificationRejected, match="cannot be activated for trading"):
            registry.activate("INS-BTC-USDT-USDT", for_trading=True, reason="owner wants to trade")

    def test_trading_activation_allowed_once_trade_enabled(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:5]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok")
        updated = registry.activate("INS-BTC-USDT-USDT", for_trading=True, reason="sandbox lifecycle proved")
        assert updated.active is True
        assert registry.tradeable() == (updated,)

    def test_activation_is_idempotent(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.activate("INS-BTC-USDT-USDT", reason="once")
        before = len(registry.changes)
        registry.activate("INS-BTC-USDT-USDT", reason="twice")
        assert len(registry.changes) == before

    def test_deactivation_is_unconditional(self, registry: InstrumentRegistry) -> None:
        """Stopping is always safe — no gate may block a deactivation."""
        registry.register(_btc_instrument())
        registry.activate("INS-BTC-USDT-USDT", reason="research")
        updated = registry.deactivate("INS-BTC-USDT-USDT", reason="incident INC-1")
        assert updated.active is False
        with pytest.raises(CertificationRejected, match="requires a reason"):
            registry.deactivate("INS-BTC-USDT-USDT", reason="")

    def test_activation_change_log_is_append_only_and_ordered(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.activate("INS-BTC-USDT-USDT", reason="research")
        registry.deactivate("INS-BTC-USDT-USDT", reason="halt")
        kinds = [c.kind for c in registry.changes]
        assert kinds == ["REGISTER", "ACTIVATE", "DEACTIVATE"]
        stamps = [c.changed_at for c in registry.changes]
        assert stamps == sorted(stamps)
        assert all(c.change_id.startswith("IRG-") for c in registry.changes)

    def test_change_payloads_are_bounded_and_audit_safe(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.activate("INS-BTC-USDT-USDT", reason="x" * 5000)
        payload = registry.changes[-1].to_audit_payload()
        assert len(payload["evidence"]) <= 200
        assert payload["changed_at"] == iso_utc(FIXED_NOW)


class TestDataStatus:
    def test_set_data_status_records_transition(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.set_data_status("INS-BTC-USDT-USDT", "LIVE")
        assert registry.require("INS-BTC-USDT-USDT").data_status == "LIVE"
        registry.set_data_status("INS-BTC-USDT-USDT", "STALE")
        assert registry.require("INS-BTC-USDT-USDT").data_status == "STALE"
        transitions = [c for c in registry.changes if c.from_status in {"UNAVAILABLE", "LIVE"}]
        assert len(transitions) == 2

    def test_unchanged_status_is_a_no_op(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        before = len(registry.changes)
        registry.set_data_status("INS-BTC-USDT-USDT", "UNAVAILABLE")
        assert len(registry.changes) == before


class TestCoverageReport:
    def test_report_counts_and_honest_gaps(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.register(
            build_instrument(
                canonical_symbol="EUR/USD",
                asset_class=AssetClass.FX_SPOT,
                base_currency="EUR",
                quote_currency="USD",
                mappings=[_mapping(venue=Venue.MT5, symbol="EURUSD", contract_size=None, tick_size=None)],
            ),
        )
        report = coverage_report(registry)
        assert report.total == 2
        assert report.active == 0
        assert report.by_asset_class == {"CRYPTO_PERP": 1, "FX_SPOT": 1}
        # The FX mapping has no contract size or tick size: sizing cannot run, and the
        # report must say so rather than implying readiness.
        assert "INS-EUR-USD@MT5" in report.missing_contract_size
        assert "INS-EUR-USD@MT5" in report.missing_tick_size
        assert report.ready_for_research == ()
        assert report.ready_for_paper == ()
        assert report.ready_for_live == ()

    def test_readiness_follows_certification(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:5]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok")
        report = coverage_report(registry)
        assert report.ready_for_research == ("INS-BTC-USDT-USDT",)
        assert report.ready_for_paper == ("INS-BTC-USDT-USDT",)
        assert report.ready_for_live == ()  # LIVE_VERIFIED not yet reached

    def test_empty_registry_reports_zeroes(self, registry: InstrumentRegistry) -> None:
        report = coverage_report(registry)
        assert report.total == 0
        assert report.by_venue_status == {}
        assert report.to_dict()["ready_for_live"] == []


class TestSnapshot:
    def test_snapshot_serialises_decimals_as_strings(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        payload = registry.snapshot().to_dict()
        assert payload["count"] == 1
        mapping = payload["instruments"][0]["mappings"][0]
        assert mapping["contract_size"] == "1"
        assert mapping["tick_size"] == "0.01"
        assert mapping["is_tradeable"] is False
        assert payload["generated_at"] == iso_utc(FIXED_NOW)

    def test_snapshot_highest_status_is_reported(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.add_mapping(
            "INS-BTC-USDT-USDT",
            VenueMapping(venue=Venue.OKX, venue_symbol="BTC-USDT-SWAP", contract_size=D("0.01")),
        )
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.SUPPORTED, evidence="ok")
        payload = registry.snapshot().to_dict()
        assert payload["instruments"][0]["highest_status"] == "SUPPORTED"

    def test_build_instrument_defaults_are_safe(self) -> None:
        instrument = build_instrument(
            canonical_symbol="XAU/USD",
            asset_class=AssetClass.METALS,
            base_currency="XAU",
            quote_currency="USD",
        )
        assert instrument.active is False
        assert instrument.data_status == "UNAVAILABLE"
        assert instrument.settlement_currency == "USD"  # defaults to quote currency
        assert instrument.instrument_id == "INS-XAU-USD"

    def test_contains_and_len(self, registry: InstrumentRegistry) -> None:
        assert len(registry) == 0
        assert "INS-BTC-USDT-USDT" not in registry
        registry.register(_btc_instrument())
        assert len(registry) == 1
        assert "INS-BTC-USDT-USDT" in registry
        assert 12345 not in registry  # a non-string is simply not present
