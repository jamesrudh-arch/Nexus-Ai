"""Stage 7.3, lever L-C: the seeded instrument master — and the ranks it may claim.

Finding F-3 said the master was empty at boot, so every coverage route reported ``total=0`` and the
archive gate was unsatisfiable in production however honest the adapters were. Lever L-E (Stage 7.2)
removed the *definition* blocker; this batch removes the missing seed.

These tests are shaped around one rule, because a seed is exactly the place where a project can lie
to itself at scale: **an instrument is seeded only where evidence exists, and only at the rank that
evidence supports.** So the interesting assertions are not "the master has three instruments" — they
are that bybit sits at ``SUPPORTED`` and no higher, that no mapping claims a rank needing a
credential, that economics nobody measured are reported missing rather than filled in, and that
seeding twice changes nothing and records nothing.

Everything here is offline. The seed writes down what previous CI runs already proved; it contacts
no venue, and a test that needed the network to pass would not be a test of the seed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from nexus.api.app import create_app
from nexus.archive.parquet_store import ParquetArchive
from nexus.core.config import Settings
from nexus.data.records import BarRecord
from nexus.domain.instrument import AssetClass, Venue, VenueStatus
from nexus.ingestion.pipeline import MINIMUM_STATUS_FOR_ARCHIVE, IngestionPipeline
from nexus.instruments.registry import (
    AUTH_NOT_APPLICABLE,
    AUTH_VERIFIED,
    InstrumentRegistry,
    certification_rank,
    coverage_report,
)
from nexus.instruments.seed import (
    EVIDENCE_MAX_CHARS,
    SEED_REQUESTER,
    SEED_SPECS,
    RungEvidence,
    SeedMapping,
    seed_master,
)

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

BTC_PERP = "INS-BTC-USDT-USDT"
BTC_SPOT = "INS-BTC-USDT"
EUR_USD = "INS-EUR-USD"


@pytest.fixture
def seeded() -> InstrumentRegistry:
    registry = InstrumentRegistry()
    seed_master(registry)
    return registry


def _status(registry: InstrumentRegistry, instrument_id: str, venue: Venue) -> VenueStatus:
    mapping = registry.require(instrument_id).mapping_for(venue)
    assert mapping is not None, f"{instrument_id} has no {venue.value} mapping"
    return mapping.status


def _bar(venue: str, symbol: str) -> BarRecord:
    return BarRecord(
        instrument_id="",  # adapters leave this empty; the pipeline resolves it
        venue=venue,
        venue_symbol=symbol,
        interval="1m",
        open_time=NOW,
        close_time=NOW + timedelta(minutes=1),
        open=Decimal("99000.00"),
        high=Decimal("99100.00"),
        low=Decimal("98900.00"),
        close=Decimal("99050.00"),
        volume=Decimal("10"),
        confirmed=True,
        source="TEST",
    )


class TestTheSeedClaimsOnlyWhatTheEvidenceSupports:
    def test_three_instruments_and_four_mappings(self, seeded: InstrumentRegistry) -> None:
        assert len(seeded) == 3
        assert {i.instrument_id for i in seeded.all()} == {BTC_PERP, BTC_SPOT, EUR_USD}
        # The perpetual carries two venues at two different ranks: that is the point of a
        # per-venue ladder, and it is what makes bybit's block visible without inflating it.
        assert len(seeded.require(BTC_PERP).mappings) == 2

    def test_each_mapping_sits_at_the_rank_its_evidence_supports(self, seeded: InstrumentRegistry) -> None:
        assert _status(seeded, BTC_PERP, Venue.OKX) is VenueStatus.DATA_AVAILABLE
        assert _status(seeded, BTC_SPOT, Venue.BINANCE) is VenueStatus.DATA_AVAILABLE
        assert _status(seeded, EUR_USD, Venue.DUKASCOPY) is VenueStatus.DATA_AVAILABLE
        assert _status(seeded, BTC_PERP, Venue.BYBIT) is VenueStatus.SUPPORTED

    def test_nothing_claims_a_rank_that_needs_a_credential(self, seeded: InstrumentRegistry) -> None:
        """``TRADE_ENABLED`` needs a sandbox order lifecycle; ``LIVE_VERIFIED`` a live pilot with
        reconciliation proven. No credential-free public data source can reach either, and
        ``DUKASCOPY`` is data rather than a broker, so it can never reach them at all."""
        forbidden = {VenueStatus.TRADE_ENABLED, VenueStatus.LIVE_VERIFIED}
        for instrument in seeded.all():
            for mapping in instrument.mappings:
                assert mapping.status not in forbidden, f"{instrument.instrument_id} overclaims"

    def test_bybit_is_present_at_its_honest_rank_with_the_block_recorded(
        self, seeded: InstrumentRegistry
    ) -> None:
        """The owner's ruling: bybit stays open and visible, not dropped from sight.

        ``SUPPORTED`` claims only that an adapter exists, which is true. Everything the geo-block
        means travels in the notes, so the record cannot be read as coverage.
        """
        mapping = seeded.require(BTC_PERP).mapping_for(Venue.BYBIT)
        assert mapping is not None
        assert mapping.status is VenueStatus.SUPPORTED
        assert "GEO-BLOCKED" in mapping.notes
        assert "F-2" in mapping.notes, "the finding that keeps it open must be named"
        assert "D-021" in mapping.notes, "and so must the machine that would close it"
        assert mapping.is_tradeable is False

    def test_economics_come_from_the_feed_and_not_from_assumption(self, seeded: InstrumentRegistry) -> None:
        """okx publishes ctVal/tickSz/minSz and they were read off the live instrument endpoint.
        The other three sources publish no lot economics in the data this project verified, so
        nothing is filled in for them."""
        okx = seeded.require(BTC_PERP).mapping_for(Venue.OKX)
        assert okx is not None
        assert okx.contract_size == Decimal("0.01")
        assert okx.tick_size == Decimal("0.1")
        assert okx.min_order_qty == Decimal("0.01")

        for instrument_id, venue in ((BTC_SPOT, Venue.BINANCE), (BTC_PERP, Venue.BYBIT)):
            mapping = seeded.require(instrument_id).mapping_for(venue)
            assert mapping is not None
            assert mapping.contract_size is None, f"{venue.value}: contract size was not measured"

    def test_dukascopys_tick_size_is_derived_from_the_verified_divisor(
        self, seeded: InstrumentRegistry
    ) -> None:
        """EURUSD's point divisor of 100000 is the one verified fact about scale, and the parsed
        prices carried five decimals. The notes must say it is derived, not published."""
        mapping = seeded.require(EUR_USD).mapping_for(Venue.DUKASCOPY)
        assert mapping is not None
        assert mapping.tick_size == Decimal("0.00001")
        assert "derived from the verified divisor" in mapping.notes
        assert mapping.contract_size is None, "a bi5 file carries ticks, not lot economics"
        assert "EURUSD ONLY" in mapping.notes

    def test_unmeasured_economics_are_reported_missing_not_invented(self, seeded: InstrumentRegistry) -> None:
        """``coverage_report`` has fields for exactly this. A seed that quietly supplied numbers
        would empty them and hide what is still unknown."""
        report = coverage_report(seeded)
        assert f"{BTC_PERP}@{Venue.BYBIT.value}" in report.missing_contract_size
        assert f"{BTC_SPOT}@{Venue.BINANCE.value}" in report.missing_contract_size
        assert f"{EUR_USD}@{Venue.DUKASCOPY.value}" in report.missing_contract_size
        assert f"{BTC_SPOT}@{Venue.BINANCE.value}" in report.missing_tick_size
        # okx is the one mapping with measured economics, so it must not appear in either list.
        assert f"{BTC_PERP}@{Venue.OKX.value}" not in report.missing_contract_size
        assert f"{BTC_PERP}@{Venue.OKX.value}" not in report.missing_tick_size

    def test_nothing_is_active_or_tradeable(self, seeded: InstrumentRegistry) -> None:
        """D-002: staged activation. Data is not permission."""
        assert seeded.active() == ()
        assert seeded.tradeable() == ()
        for instrument in seeded.all():
            assert instrument.active is False
            assert instrument.tradeable_venues() == ()
            for mapping in instrument.mappings:
                assert mapping.is_tradeable is False

    def test_coverage_is_non_zero_and_research_ready_is_the_only_readiness(
        self, seeded: InstrumentRegistry
    ) -> None:
        """F-3's observable: the routes used to report ``total=0 active=0`` at boot."""
        report = coverage_report(seeded)
        assert report.total == 3
        assert report.active == 0
        assert report.by_asset_class == {
            AssetClass.CRYPTO_PERP.value: 1,
            AssetClass.CRYPTO_SPOT.value: 1,
            AssetClass.FX_SPOT.value: 1,
        }
        assert report.by_venue_status == {
            VenueStatus.DATA_AVAILABLE.value: 3,
            VenueStatus.SUPPORTED.value: 1,
        }
        assert set(report.ready_for_research) == {BTC_PERP, BTC_SPOT, EUR_USD}
        # Paper and live need trade authority nobody has been given.
        assert report.ready_for_paper == ()
        assert report.ready_for_live == ()

    def test_all_three_asset_classes_stage_7_can_evidence_are_covered(
        self, seeded: InstrumentRegistry
    ) -> None:
        """F-6 counted 3 of 14 asset classes with a verified free source. The seed covers exactly
        those three and invents nothing for the other eleven."""
        report = coverage_report(seeded)
        assert set(report.by_asset_class) == {
            AssetClass.CRYPTO_PERP.value,
            AssetClass.CRYPTO_SPOT.value,
            AssetClass.FX_SPOT.value,
        }
        assert len(AssetClass) == 14, "if this grows, the seed's scope must be re-argued"


class TestTheSeedIsIdempotent:
    def test_a_second_call_registers_nothing_climbs_nothing_and_records_nothing(
        self, seeded: InstrumentRegistry
    ) -> None:
        before = len(seeded.changes)
        report = seed_master(seeded)
        assert report.registered == ()
        assert report.rungs_climbed == 0
        assert report.rungs_skipped == 10, "every rung was already held"
        assert tuple(report.already_present) == (BTC_PERP, BTC_SPOT, EUR_USD)
        assert len(seeded.changes) == before, "a boot must not rewrite history"

    def test_no_remap_and_no_de_certify_entries_appear(self, seeded: InstrumentRegistry) -> None:
        """The two ways a careless seed corrupts a master: ``register`` overwrites an existing
        record and logs ``REMAP`` (resetting certified mappings to ``UNKNOWN``), and ``certify``
        to a rung below the current one is recorded as ``DE_CERTIFY``. Neither may happen at boot.
        """
        seed_master(seeded)
        seed_master(seeded)
        kinds = {change.kind for change in seeded.changes}
        assert kinds == {"REGISTER", "CERTIFY"}, f"unexpected kinds: {kinds - {'REGISTER', 'CERTIFY'}}"

    def test_status_survives_repeated_boots(self, seeded: InstrumentRegistry) -> None:
        for _ in range(3):
            seed_master(seeded)
        assert _status(seeded, BTC_PERP, Venue.OKX) is VenueStatus.DATA_AVAILABLE
        assert _status(seeded, BTC_PERP, Venue.BYBIT) is VenueStatus.SUPPORTED

    def test_a_mapping_somebody_else_certified_higher_is_never_demoted(self) -> None:
        """If a future pipeline certifies a seeded mapping further, a later boot must leave it
        alone rather than restating the seed's own rank."""
        registry = InstrumentRegistry()
        seed_master(registry)
        registry.certify(
            BTC_PERP,
            Venue.OKX,
            VenueStatus.TRADE_ENABLED,
            evidence="sandbox order lifecycle verified in a test",
            requested_by="TEST",
        )
        before = len(registry.changes)
        report = seed_master(registry)
        assert _status(registry, BTC_PERP, Venue.OKX) is VenueStatus.TRADE_ENABLED
        assert len(registry.changes) == before, "the seed must not touch what it did not earn"
        assert report.rungs_climbed == 0


class TestTheChangeLogTellsTheTruth:
    def test_every_change_names_the_seed_as_its_actor(self, seeded: InstrumentRegistry) -> None:
        assert seeded.changes, "a seed that records nothing cannot be audited"
        assert {change.requested_by for change in seeded.changes} == {SEED_REQUESTER}

    def test_the_shape_of_the_log_is_three_registrations_and_ten_rungs(
        self, seeded: InstrumentRegistry
    ) -> None:
        kinds = [change.kind for change in seeded.changes]
        assert kinds.count("REGISTER") == 3
        assert kinds.count("CERTIFY") == 10  # okx 3 + bybit 1 + binance 3 + dukascopy 3

    def test_connected_rungs_declare_their_auth_case_and_no_others_do(
        self, seeded: InstrumentRegistry
    ) -> None:
        """Lever L-E: ``CONNECTED`` no longer assumes auth was verified, so which case applied is a
        recorded field. Every source seeded here is credential-free public data."""
        declared = {
            (change.venue, change.auth_state)
            for change in seeded.changes
            if change.to_status == VenueStatus.CONNECTED.value
        }
        assert declared == {
            (Venue.OKX.value, AUTH_NOT_APPLICABLE),
            (Venue.BINANCE.value, AUTH_NOT_APPLICABLE),
            (Venue.DUKASCOPY.value, AUTH_NOT_APPLICABLE),
        }
        for change in seeded.changes:
            if change.to_status != VenueStatus.CONNECTED.value:
                assert change.auth_state is None, f"{change.kind} must not carry a declaration"

    def test_bybit_claims_one_rung_and_declares_nothing(self, seeded: InstrumentRegistry) -> None:
        bybit = [c for c in seeded.changes if c.venue == Venue.BYBIT.value]
        assert [c.to_status for c in bybit] == [VenueStatus.SUPPORTED.value]
        assert all(c.auth_state is None for c in bybit)

    def test_every_evidence_label_fits_the_audit_payload(self, seeded: InstrumentRegistry) -> None:
        """``to_audit_payload`` truncates evidence at 200 characters. A label longer than that
        loses its tail silently in the audit view while looking complete in the change log — so the
        bound is a property of the seed, not a hope."""
        for change in seeded.changes:
            assert len(change.evidence) <= EVIDENCE_MAX_CHARS, change.evidence
            assert change.to_audit_payload()["evidence"] == change.evidence, "truncated"

    def test_every_label_says_what_was_measured_not_that_it_was_verified(
        self, seeded: InstrumentRegistry
    ) -> None:
        """The registry cannot judge a label, so the label has to carry the reason. A bare
        "verified" would be exactly the unjudgeable claim L-E was written to prevent."""
        for change in seeded.changes:
            if change.kind != "CERTIFY":
                continue
            assert change.evidence.strip(), "an empty label is refused by certify anyway"
            assert len(change.evidence) > 40, f"too thin to be evidence: {change.evidence!r}"
        certified = [c for c in seeded.changes if c.kind == "CERTIFY"]
        assert any("geo-blocked" in c.evidence for c in certified if c.venue == Venue.BYBIT.value)
        assert any("1440" in c.evidence for c in certified if c.venue == Venue.BINANCE.value)
        assert any("5,074" in c.evidence for c in certified if c.venue == Venue.DUKASCOPY.value)


class TestTheLadderGuardRefusesAnUnclimbableSeed:
    """A ladder that cannot be climbed must fail when the seed is declared, not halfway through a
    boot — ``certify`` advances exactly one rung at a time."""

    def test_a_ladder_that_skips_a_rung_is_refused(self) -> None:
        with pytest.raises(ValueError, match="one rung at a time"):
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                ladder=(
                    RungEvidence(VenueStatus.SUPPORTED, "adapter exists"),
                    RungEvidence(VenueStatus.DATA_AVAILABLE, "skipped CONNECTED"),
                ),
            )

    def test_a_ladder_that_does_not_start_at_supported_is_refused(self) -> None:
        with pytest.raises(ValueError, match="one rung at a time"):
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                ladder=(RungEvidence(VenueStatus.CONNECTED, "started too high", auth=AUTH_NOT_APPLICABLE),),
            )

    def test_an_empty_ladder_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one rung"):
            SeedMapping(venue=Venue.OKX, venue_symbol="BTC-USDT-SWAP", ladder=())

    def test_an_auth_declaration_off_the_connected_rung_is_refused(self) -> None:
        with pytest.raises(ValueError, match="auth declaration belongs to CONNECTED"):
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                ladder=(RungEvidence(VenueStatus.SUPPORTED, "adapter exists", auth=AUTH_VERIFIED),),
            )

    def test_a_connected_rung_without_a_declaration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="auth declaration belongs to CONNECTED"):
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                ladder=(
                    RungEvidence(VenueStatus.SUPPORTED, "adapter exists"),
                    RungEvidence(VenueStatus.CONNECTED, "it answered"),
                ),
            )

    def test_an_overlong_evidence_label_is_refused(self) -> None:
        with pytest.raises(ValueError, match="would be truncated"):
            SeedMapping(
                venue=Venue.OKX,
                venue_symbol="BTC-USDT-SWAP",
                ladder=(RungEvidence(VenueStatus.SUPPORTED, "x" * (EVIDENCE_MAX_CHARS + 1)),),
            )

    def test_the_declared_seed_satisfies_its_own_guard(self) -> None:
        """Constructing the specs is the check; this pins that they were constructed."""
        assert len(SEED_SPECS) == 3
        total = sum(len(m.ladder) for spec in SEED_SPECS for m in spec.mappings)
        assert total == 10
        for spec in SEED_SPECS:
            assert spec.mappings, f"{spec.canonical_symbol} seeds no venue at all"
            for mapping in spec.mappings:
                assert mapping.ladder[-1].status is not VenueStatus.LIVE_VERIFIED


class TestBootServesTheSeededMaster:
    def test_a_boot_with_no_registry_serves_the_seeded_master(self, settings: Settings) -> None:
        """F-3's observable, through the API rather than through the registry."""
        with TestClient(create_app(settings=settings)) as client:
            body = client.get("/v1/instruments/coverage").json()
            master = client.get("/v1/status").json()["instrument_master"]
        assert body["total"] == 3
        assert body["active"] == 0
        assert sorted(body["ready_for_research"]) == sorted([BTC_PERP, BTC_SPOT, EUR_USD])
        assert body["ready_for_paper"] == []
        assert body["ready_for_live"] == []
        assert master == {"count": 3, "active": 0, "projected": 3}

    def test_the_seeded_master_lists_bybit_as_supported_not_as_covered(self, settings: Settings) -> None:
        with TestClient(create_app(settings=settings)) as client:
            body = client.get("/v1/instruments").json()
        perp = next(i for i in body["instruments"] if i["instrument_id"] == BTC_PERP)
        by_v = {m["venue"]: m for m in perp["mappings"]}
        assert by_v["OKX"]["status"] == "DATA_AVAILABLE"
        assert by_v["BYBIT"]["status"] == "SUPPORTED"
        assert by_v["BYBIT"]["is_tradeable"] is False
        assert "GEO-BLOCKED" in by_v["BYBIT"]["notes"]

    def test_seed_false_boots_an_empty_master(self, settings: Settings) -> None:
        """The escape hatch, so an empty master is still reachable on purpose."""
        with TestClient(create_app(settings=settings, seed=False)) as client:
            body = client.get("/v1/instruments/coverage").json()
        assert body["total"] == 0
        assert body["ready_for_research"] == []

    def test_an_injected_registry_is_never_seeded(self, settings: Settings) -> None:
        """What a caller built is what the app serves: a test fixture stays a test fixture, and no
        composition root has its own registry silently rewritten underneath it."""
        with TestClient(create_app(settings=settings, registry=InstrumentRegistry())) as client:
            body = client.get("/v1/instruments").json()
        assert body["count"] == 0
        assert body["instruments"] == []

    def test_the_archive_route_still_reports_that_nothing_is_stored(self, settings: Settings) -> None:
        """Seeding the master must not imply data exists. "No archive" and "archive holds nothing"
        are different facts and the route keeps saying which one is true."""
        with TestClient(create_app(settings=settings)) as client:
            body = client.get("/v1/data/coverage").json()
        assert body["configured"] is False
        assert body["files"] == 0


class TestTheArchiveGateIsReachableInProduction:
    """F-3's other half. Stage 7.2 proved the gate was reachable *in principle* with a registry
    built inside a test; this proves it is reachable with the registry the app actually boots."""

    async def test_a_seeded_source_can_feed_the_archive(self, tmp_path: object) -> None:
        registry = InstrumentRegistry()
        seed_master(registry)
        archive = ParquetArchive(root=tmp_path)  # type: ignore[arg-type]
        pipeline = IngestionPipeline(registry=registry, archive=archive, now_fn=lambda: NOW)

        report = await pipeline.run(venue=Venue.BINANCE, bars=[_bar("BINANCE", "BTCUSDT")])
        assert report.bars_accepted == 1, report.rejection_reasons
        assert report.status_refusals == {}
        assert MINIMUM_STATUS_FOR_ARCHIVE is VenueStatus.DATA_AVAILABLE
        rows = archive.read_bars()
        assert rows[0].instrument_id == BTC_SPOT, "resolved from the master, not invented"

    async def test_a_seeded_fx_source_can_feed_the_archive(self, tmp_path: object) -> None:
        """What lever L-B made representable and this seed makes usable: FX at Dukascopy."""
        registry = InstrumentRegistry()
        seed_master(registry)
        archive = ParquetArchive(root=tmp_path)  # type: ignore[arg-type]
        pipeline = IngestionPipeline(registry=registry, archive=archive, now_fn=lambda: NOW)

        report = await pipeline.run(venue=Venue.DUKASCOPY, bars=[_bar("DUKASCOPY", "EURUSD")])
        assert report.bars_accepted == 1, report.rejection_reasons
        assert archive.read_bars()[0].instrument_id == EUR_USD

    async def test_bybit_still_cannot_feed_the_archive(self, tmp_path: object) -> None:
        """The gate is a gate. Seeding bybit at ``SUPPORTED`` must not let its data through."""
        registry = InstrumentRegistry()
        seed_master(registry)
        archive = ParquetArchive(root=tmp_path)  # type: ignore[arg-type]
        pipeline = IngestionPipeline(registry=registry, archive=archive, now_fn=lambda: NOW)

        report = await pipeline.run(venue=Venue.BYBIT, bars=[_bar("BYBIT", "BTCUSDT")])
        assert report.bars_accepted == 0
        assert report.status_refusals == {f"{Venue.BYBIT.value}:SUPPORTED": 1}
        assert archive.read_bars() == []

    def test_the_seeded_ranks_sit_where_the_gate_requires(self, seeded: InstrumentRegistry) -> None:
        for instrument in seeded.all():
            for mapping in instrument.mappings:
                reached = certification_rank(mapping.status) >= certification_rank(MINIMUM_STATUS_FOR_ARCHIVE)
                assert reached is (mapping.status is VenueStatus.DATA_AVAILABLE)
