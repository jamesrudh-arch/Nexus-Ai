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

from nexus.core.errors import RejectReason
from nexus.core.ids import iso_utc
from nexus.domain.instrument import (
    AssetClass,
    CanonicalInstrument,
    InstrumentDefinitionError,
    Venue,
    VenueMapping,
    VenueStatus,
)
from nexus.instruments.registry import (
    AUTH_DECLARATIONS,
    AUTH_NOT_APPLICABLE,
    AUTH_VERIFIED,
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


def _auth_for(status: VenueStatus) -> str | None:
    """The auth declaration a certification to ``status`` must carry (Stage 7.2, lever L-E).

    ``CONNECTED`` no longer means "auth verified", so certifying to it requires an explicit
    declaration; every other rung makes no claim about authentication and refuses one. Every venue
    in these tests is a credential-free public feed, so the honest declaration is
    ``AUTH_NOT_APPLICABLE``.
    """
    return AUTH_NOT_APPLICABLE if status is VenueStatus.CONNECTED else None


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
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                status,
                evidence=f"proved {status.value}",
                auth=_auth_for(status),
            )
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
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok", auth=_auth_for(status))
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
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok", auth=_auth_for(status))
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
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok", auth=_auth_for(status))
        with pytest.raises(CertificationRejected, match="cannot be activated for trading"):
            registry.activate("INS-BTC-USDT-USDT", for_trading=True, reason="owner wants to trade")

    def test_trading_activation_allowed_once_trade_enabled(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        for status in CERTIFICATION_ORDER[1:5]:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok", auth=_auth_for(status))
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
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, status, evidence="ok", auth=_auth_for(status))
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


class TestVenueVocabularyIsEnforced:
    """Finding F-4 / lever L-B: the declared vocabularies are now enforced at the boundary.

    Before Stage 7.2 a dataclass annotation was the only thing standing between a caller and a venue
    that does not exist, and annotations do nothing at runtime: ``VenueMapping(venue="DUKASCOPY")``
    constructed happily and then raised an unclassified ``AttributeError`` inside
    ``InstrumentRegistry.register`` at the first ``m.venue.value`` — through the API, a 500 where
    every comparable condition is a named refusal.
    """

    def test_dukascopy_is_a_venue(self) -> None:
        """The only free FX source is now representable, which is what made FX coverage unrecordable."""
        assert Venue("DUKASCOPY") is Venue.DUKASCOPY

    def test_the_fx_adapter_venue_string_resolves_to_a_member(self) -> None:
        from nexus.ingestion.dukascopy import VENUE as ADAPTER_VENUE

        assert Venue(ADAPTER_VENUE) is Venue.DUKASCOPY

    def test_a_venue_outside_the_enum_is_refused_at_construction(self) -> None:
        with pytest.raises(InstrumentDefinitionError) as exc:
            VenueMapping(venue="DUKASCOPYX", venue_symbol="EURUSD")  # type: ignore[arg-type]
        assert exc.value.reason is RejectReason.INSTRUMENT_DEFINITION_INVALID
        assert "Venue member" in exc.value.detail
        assert "DUKASCOPYX" in exc.value.detail  # names the offending value

    def test_a_bare_string_status_is_refused(self) -> None:
        """Same fail-open, same boundary: ``coverage_report`` reads ``mapping.status.value``."""
        with pytest.raises(InstrumentDefinitionError, match="VenueStatus member"):
            VenueMapping(venue=Venue.OKX, venue_symbol="BTC-USDT", status="DATA_AVAILABLE")  # type: ignore[arg-type]

    def test_a_bare_string_asset_class_is_refused(self) -> None:
        with pytest.raises(InstrumentDefinitionError, match="AssetClass member"):
            CanonicalInstrument(
                instrument_id="INS-EUR-USD",
                canonical_symbol="EUR/USD",
                asset_class="FX_SPOT",  # type: ignore[arg-type]
                base_currency="EUR",
                quote_currency="USD",
                settlement_currency="USD",
            )

    def test_a_mapping_that_is_not_a_mapping_is_refused(self) -> None:
        with pytest.raises(InstrumentDefinitionError, match="VenueMapping instances"):
            CanonicalInstrument(
                instrument_id="INS-EUR-USD",
                canonical_symbol="EUR/USD",
                asset_class=AssetClass.FX_SPOT,
                base_currency="EUR",
                quote_currency="USD",
                settlement_currency="USD",
                mappings=[Venue.DUKASCOPY],  # type: ignore[list-item]
            )

    def test_certify_refuses_a_venue_outside_the_enum(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(InstrumentDefinitionError, match="Venue member"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                "BYBIT",
                VenueStatus.SUPPORTED,
                evidence="x",  # type: ignore[arg-type]
            )

    def test_certify_refuses_a_status_outside_the_enum(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        with pytest.raises(InstrumentDefinitionError, match="VenueStatus member"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                "SUPPORTED",
                evidence="x",  # type: ignore[arg-type]
            )

    def test_fx_coverage_is_recordable_end_to_end(self, registry: InstrumentRegistry) -> None:
        """The closure of F-4, at every step that used to be impossible.

        Register an FX instrument on the venue that actually serves it, certify it to the rank its
        evidence supports, and read it back through the coverage report — with data still not
        implying permission.
        """
        fx = build_instrument(
            canonical_symbol="EUR/USD",
            asset_class=AssetClass.FX_SPOT,
            base_currency="EUR",
            quote_currency="USD",
            mappings=[VenueMapping(venue=Venue.DUKASCOPY, venue_symbol="EURUSD")],
            notes="Dukascopy bi5 tick history; layout verified 2026-11-26 (docs/14 F-1)",
        )
        registry.register(fx, source="LIVE_VERIFICATION")
        for status in CERTIFICATION_ORDER[1:4]:  # UNKNOWN -> SUPPORTED -> CONNECTED -> DATA_AVAILABLE
            registry.certify(
                "INS-EUR-USD",
                Venue.DUKASCOPY,
                status,
                evidence=f"run 45759709313: {status.value} on a real bi5 hour",
                auth=_auth_for(status),
            )

        report = coverage_report(registry)
        assert report.by_asset_class == {"FX_SPOT": 1}
        assert report.by_venue_status == {"DATA_AVAILABLE": 1}
        assert report.ready_for_research == ("INS-EUR-USD",)
        assert report.ready_for_paper == ()  # TRADE_ENABLED not reached: data is not permission
        assert report.ready_for_live == ()
        mapping = registry.require("INS-EUR-USD").mapping_for(Venue.DUKASCOPY)
        assert mapping is not None
        assert mapping.is_tradeable is False
        assert registry.require("INS-EUR-USD").active is False  # D-002: never active by default


class TestConnectedDeclaresItsAuthCase:
    """Finding F-7 / lever L-E: ``CONNECTED`` declares its authentication case instead of assuming it.

    The rung meant "auth verified". All four sources this system uses are credential-free public
    feeds, so none could occupy it honestly — and because the ladder never skips, ``DATA_AVAILABLE``
    was unreachable for every one of them, which is what made ``MINIMUM_STATUS_FOR_ARCHIVE``
    unsatisfiable (F-3). The rung now means "the venue answered and its responses normalised", and a
    certification to it must say which case applies.
    """

    def _to_supported(self, registry: InstrumentRegistry) -> None:
        registry.register(_btc_instrument())
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.SUPPORTED, evidence="adapter exists")

    def test_the_vocabulary_is_exactly_two_declarations(self) -> None:
        assert AUTH_DECLARATIONS == (AUTH_VERIFIED, AUTH_NOT_APPLICABLE)

    def test_connecting_without_a_declaration_is_refused(self, registry: InstrumentRegistry) -> None:
        self._to_supported(registry)
        with pytest.raises(CertificationRejected, match="requires an explicit auth declaration"):
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.CONNECTED, evidence="it answered")

    def test_the_refusal_names_both_options_and_why(self, registry: InstrumentRegistry) -> None:
        """A refusal that does not say how to comply just produces a retry with the same mistake."""
        self._to_supported(registry)
        with pytest.raises(CertificationRejected) as exc:
            registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.CONNECTED, evidence="it answered")
        detail = str(exc.value)
        assert AUTH_VERIFIED in detail
        assert AUTH_NOT_APPLICABLE in detail
        assert "no longer assumes auth was verified" in detail

    def test_an_unknown_declaration_is_refused(self, registry: InstrumentRegistry) -> None:
        self._to_supported(registry)
        with pytest.raises(CertificationRejected, match="must be one of"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                VenueStatus.CONNECTED,
                evidence="it answered",
                auth="PROBABLY_AUTHENTICATED",
            )

    def test_a_public_source_declares_not_applicable_and_it_is_recorded(
        self, registry: InstrumentRegistry
    ) -> None:
        self._to_supported(registry)
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="public unauthenticated endpoints answered; no credential exists or was used",
            auth=AUTH_NOT_APPLICABLE,
        )
        change = registry.changes[-1]
        assert change.kind == "CERTIFY"
        assert change.to_status == "CONNECTED"
        assert change.auth_state == AUTH_NOT_APPLICABLE
        # It must survive into the audit payload, not only the in-memory record.
        assert change.to_audit_payload()["auth_state"] == AUTH_NOT_APPLICABLE

    def test_a_credentialed_source_declares_verified(self, registry: InstrumentRegistry) -> None:
        self._to_supported(registry)
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="demo credential accepted by the venue",
            auth=AUTH_VERIFIED,
        )
        assert registry.changes[-1].auth_state == AUTH_VERIFIED
        assert registry.changes[-1].to_audit_payload()["auth_state"] == AUTH_VERIFIED

    def test_a_declaration_on_any_other_rung_is_refused(self, registry: InstrumentRegistry) -> None:
        """Cargo-culting the field would imply an authentication claim the rung does not make."""
        registry.register(_btc_instrument())
        with pytest.raises(CertificationRejected, match="belongs to the CONNECTED rung only"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                VenueStatus.SUPPORTED,
                evidence="adapter exists",
                auth=AUTH_NOT_APPLICABLE,
            )

    def test_demotion_to_connected_also_requires_the_declaration(self, registry: InstrumentRegistry) -> None:
        self._to_supported(registry)
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="public endpoints answered",
            auth=AUTH_NOT_APPLICABLE,
        )
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.DATA_AVAILABLE,
            evidence="feed observed",
        )
        with pytest.raises(CertificationRejected, match="requires an explicit auth declaration"):
            registry.certify(
                "INS-BTC-USDT-USDT",
                Venue.BYBIT,
                VenueStatus.CONNECTED,
                evidence="entitlement withdrawn",
            )
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="entitlement withdrawn; public data only",
            auth=AUTH_NOT_APPLICABLE,
        )
        assert registry.changes[-1].kind == "DE_CERTIFY"
        assert registry.changes[-1].auth_state == AUTH_NOT_APPLICABLE

    def test_restatement_needs_no_declaration_because_it_records_nothing(
        self, registry: InstrumentRegistry
    ) -> None:
        self._to_supported(registry)
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="public endpoints answered",
            auth=AUTH_NOT_APPLICABLE,
        )
        before = len(registry.changes)
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.CONNECTED, evidence="unchanged")
        assert len(registry.changes) == before  # a no-op makes no claim, so it needs no declaration

    def test_a_credential_free_source_can_now_reach_the_archive_gate(
        self, registry: InstrumentRegistry
    ) -> None:
        """The point of the ruling: F-3's gate becomes reachable without lying about authentication.

        ``MINIMUM_STATUS_FOR_ARCHIVE`` is ``DATA_AVAILABLE``, and nothing could reach it while the
        rung below it demanded an auth verification that public feeds cannot provide.
        """
        from nexus.ingestion.pipeline import MINIMUM_STATUS_FOR_ARCHIVE

        self._to_supported(registry)
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.CONNECTED,
            evidence="public unauthenticated endpoints answered and normalised; no credential exists",
            auth=AUTH_NOT_APPLICABLE,
        )
        registry.certify(
            "INS-BTC-USDT-USDT",
            Venue.BYBIT,
            VenueStatus.DATA_AVAILABLE,
            evidence="run 45759709313: instruments/quotes/trades/candles/book normalised",
        )
        mapping = registry.require("INS-BTC-USDT-USDT").mapping_for(Venue.BYBIT)
        assert mapping is not None
        assert certification_rank(mapping.status) >= certification_rank(MINIMUM_STATUS_FOR_ARCHIVE)
        report = coverage_report(registry)
        assert report.ready_for_research == ("INS-BTC-USDT-USDT",)
        assert report.ready_for_paper == ()  # still no trade authority
        assert mapping.is_tradeable is False

    def test_non_connected_changes_carry_no_auth_state(self, registry: InstrumentRegistry) -> None:
        """Absence must stay meaningful: a null here says the rung makes no auth claim."""
        registry.register(_btc_instrument())
        registry.certify("INS-BTC-USDT-USDT", Venue.BYBIT, VenueStatus.SUPPORTED, evidence="adapter exists")
        assert registry.changes[-1].auth_state is None
        assert registry.changes[-1].to_audit_payload()["auth_state"] is None
