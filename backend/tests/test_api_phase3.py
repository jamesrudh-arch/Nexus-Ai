"""Phase 3 API surface: instruments, coverage, sessions, archive.

The routes added in Phase 3 are read-only. These tests pin that, and pin the honesty rules:
an unknown instrument is a 404 rather than a guess, "no archive configured" is reported as
distinct from "archive is empty", and readiness follows certification rather than enthusiasm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus import DATA_SOURCES, PHASE_GATE
from nexus.api.app import create_app
from nexus.audit.log import AuditLog
from nexus.core.config import Settings
from nexus.domain.instrument import AssetClass, Venue, VenueMapping, VenueStatus
from nexus.execution.halt import HaltManager
from nexus.instruments.registry import AUTH_NOT_APPLICABLE, InstrumentRegistry, build_instrument
from nexus.instruments.sessions import HolidaySet, MarketCalendar

D = Decimal
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
BTC_ID = "INS-BTC-USDT-USDT"


def _auth_for(status: VenueStatus) -> str | None:
    """The auth declaration a certification to ``status`` must carry (Stage 7.2, lever L-E).

    ``CONNECTED`` no longer means "auth verified", so certifying to it requires an explicit
    declaration; every other rung makes no claim about authentication and refuses one. Every venue
    in these tests is a credential-free public feed, so the honest declaration is
    ``AUTH_NOT_APPLICABLE``.
    """
    return AUTH_NOT_APPLICABLE if status is VenueStatus.CONNECTED else None


def make_registry(*, certify_to: VenueStatus = VenueStatus.DATA_AVAILABLE) -> InstrumentRegistry:
    registry = InstrumentRegistry(now_fn=lambda: NOW)
    registry.register(
        build_instrument(
            canonical_symbol="BTC/USDT:USDT",
            asset_class=AssetClass.CRYPTO_PERP,
            base_currency="BTC",
            quote_currency="USDT",
            mappings=[
                VenueMapping(
                    venue=Venue.BYBIT,
                    venue_symbol="BTCUSDT",
                    contract_size=D("1"),
                    tick_size=D("0.10"),
                    quote_currency="USDT",
                ),
            ],
        ),
    )
    ladder = [
        VenueStatus.UNKNOWN,
        VenueStatus.SUPPORTED,
        VenueStatus.CONNECTED,
        VenueStatus.DATA_AVAILABLE,
        VenueStatus.TRADE_ENABLED,
        VenueStatus.LIVE_VERIFIED,
    ]
    for step in ladder[1 : ladder.index(certify_to) + 1]:
        registry.certify(BTC_ID, Venue.BYBIT, step, evidence=f"proved {step.value}", auth=_auth_for(step))
    return registry


@pytest.fixture
def registry() -> InstrumentRegistry:
    return make_registry()


@pytest.fixture
def client(
    settings: Settings,
    audit_log: AuditLog,
    halt_manager: HaltManager,
    registry: InstrumentRegistry,
) -> TestClient:
    app = create_app(
        settings=settings,
        audit=audit_log,
        halt=halt_manager,
        registry=registry,
        calendar=MarketCalendar(holidays=HolidaySet()),
    )
    return TestClient(app)


class TestPhaseGateStillClosed:
    """Phase 3 adds data reading. It must not have added any trading capability."""

    def test_phase_gate_reports_no_order_capability(self) -> None:
        assert PHASE_GATE["live_trading"] is False
        assert PHASE_GATE["venue_adapters"] is False
        assert PHASE_GATE["real_money_orders_possible"] is False
        assert PHASE_GATE["order_capability"] is False
        assert PHASE_GATE["market_data_sources"] is True

    def test_status_still_denies_live_authority(self, client: TestClient) -> None:
        body = client.get("/v1/status").json()
        assert body["live_authority"]["status"] == "DENIED"
        assert body["live_authority"]["granted"] is False
        assert body["phase_gate"]["real_money_orders_possible"] is False

    def test_market_data_sources_are_read_only_and_free(self, client: TestClient) -> None:
        sources = client.get("/v1/status").json()["market_data_sources"]
        assert sources["authenticated"] is False
        assert sources["read_only"] is True
        assert sources["order_capable"] is False
        assert sources["cost_usd"] == 0
        assert set(sources["sources"]) == set(DATA_SOURCES)

    def test_no_trading_venue_adapters_are_listed(self, client: TestClient) -> None:
        assert client.get("/v1/status").json()["venue_adapters"] == []

    def test_no_order_or_trade_endpoint_exists(self, client: TestClient) -> None:
        """The structural guarantee: there is nothing to call, so nothing can be called."""
        paths = set(client.get("/openapi.json").json()["paths"])
        forbidden = {"/v1/orders", "/v1/trades", "/v1/positions", "/v1/intents", "/v1/execute"}
        assert not (paths & forbidden)
        for path in paths:
            lowered = path.lower()
            assert "order" not in lowered
            assert "trade" not in lowered
            assert "execute" not in lowered

    def test_instrument_master_counts_are_reported(self, client: TestClient) -> None:
        body = client.get("/v1/status").json()["instrument_master"]
        # registered but never active by default; and never projected, because this client injects its
        # own registry — the app projects what it seeded, so a test fixture stays a test fixture (L-B).
        assert body == {"count": 1, "active": 0, "projected": 0}


class TestInstrumentsEndpoint:
    def test_lists_the_canonical_master(self, client: TestClient) -> None:
        body = client.get("/v1/instruments").json()
        assert body["count"] == 1
        assert body["active_count"] == 0
        instrument = body["instruments"][0]
        assert instrument["instrument_id"] == BTC_ID
        assert instrument["canonical_symbol"] == "BTC/USDT:USDT"
        assert instrument["asset_class"] == "CRYPTO_PERP"
        assert instrument["active"] is False

    def test_decimals_are_serialised_as_exact_strings(self, client: TestClient) -> None:
        """A JSON float here would lose precision on the way to the UI."""
        mapping = client.get("/v1/instruments").json()["instruments"][0]["mappings"][0]
        assert mapping["contract_size"] == "1"
        assert mapping["tick_size"] == "0.10"
        assert mapping["venue_symbol"] == "BTCUSDT"

    def test_certification_state_is_exposed(self, client: TestClient) -> None:
        mapping = client.get("/v1/instruments").json()["instruments"][0]["mappings"][0]
        assert mapping["status"] == "DATA_AVAILABLE"
        assert mapping["is_tradeable"] is False  # data is not permission

    def test_empty_registry_reports_zero_not_an_error(self) -> None:
        settings = Settings()
        app = create_app(settings=settings, registry=InstrumentRegistry())
        with TestClient(app) as empty_client:
            body = empty_client.get("/v1/instruments").json()
        assert body["count"] == 0
        assert body["instruments"] == []


class TestCoverageEndpoint:
    def test_readiness_follows_certification(self, client: TestClient) -> None:
        body = client.get("/v1/instruments/coverage").json()
        assert body["total"] == 1
        assert body["ready_for_research"] == [BTC_ID]
        assert body["ready_for_paper"] == []
        assert body["ready_for_live"] == []

    def test_coverage_states_live_trading_is_disabled(self, client: TestClient) -> None:
        """Readiness for live is about certification, not about authority to trade."""
        body = client.get("/v1/instruments/coverage").json()
        assert body["live_trading_enabled"] is False
        assert "DENIED" in body["note"]

    def test_live_verified_instrument_appears_in_all_tiers(self) -> None:
        settings = Settings()
        app = create_app(settings=settings, registry=make_registry(certify_to=VenueStatus.LIVE_VERIFIED))
        with TestClient(app) as certified_client:
            body = certified_client.get("/v1/instruments/coverage").json()
        assert body["ready_for_research"] == [BTC_ID]
        assert body["ready_for_paper"] == [BTC_ID]
        assert body["ready_for_live"] == [BTC_ID]
        # Even fully certified, the API still reports live trading as disabled.
        assert body["live_trading_enabled"] is False

    def test_missing_economics_are_reported_as_gaps(self) -> None:
        """No contract size means sizing cannot run; the report must say so."""
        registry = InstrumentRegistry()
        registry.register(
            build_instrument(
                canonical_symbol="EUR/USD",
                asset_class=AssetClass.FX_SPOT,
                base_currency="EUR",
                quote_currency="USD",
                mappings=[VenueMapping(venue=Venue.MT5, venue_symbol="EURUSD")],
            ),
        )
        app = create_app(settings=Settings(), registry=registry)
        with TestClient(app) as gap_client:
            body = gap_client.get("/v1/instruments/coverage").json()
        assert "INS-EUR-USD@MT5" in body["missing_contract_size"]
        assert "INS-EUR-USD@MT5" in body["missing_tick_size"]
        assert body["ready_for_research"] == []


class TestSessionEndpoint:
    def test_crypto_is_open(self, client: TestClient) -> None:
        body = client.get(f"/v1/instruments/{BTC_ID}/session").json()
        assert body["is_open"] is True
        assert body["kind"] == "CONTINUOUS_24_7"
        assert body["confidence"] == "FULL"

    def test_unknown_instrument_is_a_404_not_a_guess(self, client: TestClient) -> None:
        response = client.get("/v1/instruments/INS-NOPE/session")
        assert response.status_code == 404
        assert "unknown instrument" in response.json()["detail"]

    def test_fx_instrument_reports_partial_confidence(self) -> None:
        registry = InstrumentRegistry()
        registry.register(
            build_instrument(
                canonical_symbol="EUR/USD",
                asset_class=AssetClass.FX_SPOT,
                base_currency="EUR",
                quote_currency="USD",
                mappings=[VenueMapping(venue=Venue.MT5, venue_symbol="EURUSD")],
            ),
        )
        app = create_app(settings=Settings(), registry=registry)
        with TestClient(app) as fx_client:
            body = fx_client.get("/v1/instruments/INS-EUR-USD/session").json()
        assert body["kind"] == "FX_24X5"
        assert body["confidence"] == "PARTIAL"  # bank holidays are not loaded
        assert body["instrument_id"] == "INS-EUR-USD"

    def test_exchange_override_is_honoured(self) -> None:
        registry = InstrumentRegistry()
        registry.register(
            build_instrument(
                canonical_symbol="AAPL",
                asset_class=AssetClass.EQUITIES,
                base_currency="AAPL",
                quote_currency="USD",
                mappings=[VenueMapping(venue=Venue.ALPACA, venue_symbol="AAPL")],
            ),
        )
        app = create_app(settings=Settings(), registry=registry)
        with TestClient(app) as eq_client:
            body = eq_client.get("/v1/instruments/INS-AAPL/session?exchange=NYSE").json()
        assert body["kind"] == "EXCHANGE_REGULAR"
        assert any("NYSE" in r for r in body["reasons"])

    def test_instrument_without_mappings_reports_unknown_confidence(self) -> None:
        registry = InstrumentRegistry()
        registry.register(
            build_instrument(
                canonical_symbol="MYSTERY",
                asset_class=AssetClass.EQUITIES,
                base_currency="X",
                quote_currency="USD",
            ),
        )
        app = create_app(settings=Settings(), registry=registry)
        with TestClient(app) as mystery_client:
            body = mystery_client.get("/v1/instruments/INS-MYSTERY/session").json()
        assert body["is_open"] is False
        assert body["confidence"] == "UNKNOWN"


class TestDataCoverageEndpoint:
    def test_no_archive_is_reported_as_unconfigured(self, client: TestClient) -> None:
        """'No archive' and 'archive is empty' are different facts."""
        body = client.get("/v1/data/coverage").json()
        assert body["configured"] is False
        assert body["files"] == 0
        assert "nothing has been persisted" in body["note"]

    def test_configured_archive_reports_the_manifest(self, tmp_path: Any) -> None:
        pytest.importorskip("pyarrow", reason="archive extra not installed")
        from nexus.archive.parquet_store import ParquetArchive
        from nexus.data.records import BarRecord

        archive = ParquetArchive(tmp_path / "archive", now_fn=lambda: NOW)
        archive.write_bars(
            [
                BarRecord(
                    instrument_id=BTC_ID,
                    venue="BYBIT",
                    venue_symbol="BTCUSDT",
                    interval="1m",
                    open_time=NOW,
                    close_time=None,
                    open=D("99000"),
                    high=D("99100"),
                    low=D("98900"),
                    close=D("99050"),
                    volume=D("10"),
                    confirmed=True,
                    source="TEST",
                ),
            ],
        )
        app = create_app(settings=Settings(), registry=make_registry(), archive=archive)
        with TestClient(app) as archive_client:
            body = archive_client.get("/v1/data/coverage").json()
        assert body["configured"] is True
        assert body["files"] == 1
        assert body["bytes"] > 0
        assert body["format_version"] == "nexus-archive-v1"
        assert "D-024" in body["retention_policy"]
        assert len(body["partitions"]) == 1

    def test_empty_archive_is_configured_but_holds_nothing(self, tmp_path: Any) -> None:
        pytest.importorskip("pyarrow", reason="archive extra not installed")
        from nexus.archive.parquet_store import ParquetArchive

        archive = ParquetArchive(tmp_path / "archive")
        app = create_app(settings=Settings(), archive=archive)
        with TestClient(app) as empty_client:
            body = empty_client.get("/v1/data/coverage").json()
        assert body["configured"] is True
        assert body["files"] == 0
        assert body["partitions"] == {}


class TestReadOnlySurface:
    @pytest.mark.parametrize(
        "path",
        [
            "/v1/instruments",
            "/v1/instruments/coverage",
            f"/v1/instruments/{BTC_ID}/session",
            "/v1/data/coverage",
        ],
    )
    def test_phase3_routes_reject_post(self, client: TestClient, path: str) -> None:
        """No Phase 3 route may accept a write."""
        assert client.post(path).status_code == 405

    @pytest.mark.parametrize(
        "path",
        ["/v1/instruments", "/v1/instruments/coverage", "/v1/data/coverage"],
    )
    def test_phase3_routes_need_no_authentication_to_read(self, client: TestClient, path: str) -> None:
        """Read-only market data is not a control action, so it must not require the owner token."""
        assert client.get(path).status_code == 200
