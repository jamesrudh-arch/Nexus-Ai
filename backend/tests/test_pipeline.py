"""Ingestion pipeline (Phase 3): registry → validation → archive → publish.

This is the only place raw venue payloads become NEXUS data, so every archive guarantee is
enforced here. The properties under test:

* an **unrecognised venue symbol is refused, never guessed** — a wrong instrument id would
  propagate into research, into sizing and eventually into an order;
* a mapping **below ``DATA_AVAILABLE`` cannot feed the archive** — an unverified feed is not
  evidence;
* the resolved ``instrument_id`` is stamped on every record;
* rejections are **counted with reasons**, and a high rejection rate marks the pass DEGRADED
  rather than reporting a clean ingest;
* the **archive is written before events are published**, so a consumer can never observe a
  record the archive does not hold;
* bars NEXUS built from ticks go through the **same validation** as venue-published bars.

No test here can place an order: the pipeline has no such capability, and one test asserts
that structurally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.archive.parquet_store import ParquetArchive
from nexus.data.records import BarRecord, QuoteRecord, TickRecord
from nexus.domain.instrument import AssetClass, Venue, VenueMapping, VenueStatus
from nexus.ingestion.pipeline import (
    MINIMUM_STATUS_FOR_ARCHIVE,
    IngestionPipeline,
    PipelineReport,
    summarise_reports,
)
from nexus.instruments.registry import InstrumentRegistry, build_instrument

D = Decimal
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
BTC_ID = "INS-BTC-USDT-USDT"


def make_registry(*, status: VenueStatus = VenueStatus.DATA_AVAILABLE) -> InstrumentRegistry:
    """A registry with one Bybit perp certified up to ``status``."""
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
                    tick_size=D("0.01"),
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
    for step in ladder[1 : ladder.index(status) + 1]:
        registry.certify(BTC_ID, Venue.BYBIT, step, evidence=f"proved {step.value}")
    return registry


def make_bar(
    at: datetime = NOW,
    *,
    symbol: str = "BTCUSDT",
    venue: str = "BYBIT",
    confirmed: bool = True,
    open_px: str = "99000.00",
) -> BarRecord:
    return BarRecord(
        instrument_id="",  # adapters leave this empty; the pipeline resolves it
        venue=venue,
        venue_symbol=symbol,
        interval="1m",
        open_time=at,
        close_time=at + timedelta(minutes=1),
        open=D(open_px),
        high=D("99100.00"),
        low=D("98900.00"),
        close=D("99050.00"),
        volume=D("10"),
        quote_volume=D("990000"),
        trades=5,
        confirmed=confirmed,
        source="BYBIT_V5_PUBLIC_REST",
    )


def make_tick(at: datetime = NOW, *, symbol: str = "BTCUSDT", price: str = "99000.00") -> TickRecord:
    return TickRecord(
        instrument_id="",
        venue="BYBIT",
        venue_symbol=symbol,
        price=D(price),
        quantity=D("0.01"),
        observed_at=at,
        venue_timestamp=at,
        side="BUY",
        trade_id=f"exec-{int(at.timestamp() * 1000)}",
        source="BYBIT_V5_PUBLIC_REST",
    )


def make_quote(at: datetime = NOW, *, symbol: str = "BTCUSDT") -> QuoteRecord:
    return QuoteRecord(
        instrument_id="",
        venue="BYBIT",
        venue_symbol=symbol,
        bid=D("98999.90"),
        ask=D("99000.10"),
        bid_size=D("0.5"),
        ask_size=D("0.75"),
        last=D("99000.00"),
        observed_at=at,
        venue_timestamp=at,
        delayed=False,
        source="BYBIT_V5_PUBLIC_REST",
    )


class RecordingPublisher:
    """Records published events, in order, so archive-before-publish can be asserted."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []
        self.calls_at_publish: list[int] = []
        self._archive: ParquetArchive | None = None

    def attach(self, archive: ParquetArchive) -> None:
        self._archive = archive

    async def __call__(self, topic: str, payload: dict[str, object]) -> None:
        self.events.append((topic, payload))
        # Snapshot how many files existed *at the moment of publication*. If archiving
        # happened first, this is non-zero; if publishing happened first, it is zero.
        if self._archive is not None:
            self.calls_at_publish.append(self._archive.count_files())


@pytest.fixture
def archive(tmp_path: Path) -> ParquetArchive:
    return ParquetArchive(tmp_path / "archive", now_fn=lambda: NOW)


pytest.importorskip("pyarrow", reason="archive extra not installed")


class TestStructuralSafety:
    def test_pipeline_has_no_order_capability(self) -> None:
        """Phase 3 ingestion must not be able to trade, by construction."""
        forbidden = ("place", "submit", "cancel", "withdraw", "transfer", "order", "trade", "execute")
        for name in dir(IngestionPipeline):
            if name.startswith("_"):
                continue
            lowered = name.lower()
            for verb in forbidden:
                assert verb not in lowered, f"IngestionPipeline.{name} looks like a trading capability"

    def test_pipeline_accepts_no_credentials(self) -> None:
        import inspect

        params = set(inspect.signature(IngestionPipeline.__init__).parameters)
        forbidden = {"api_key", "api_secret", "secret", "passphrase", "token", "password", "credentials"}
        assert not (params & forbidden)

    def test_minimum_archive_status_is_data_available(self) -> None:
        assert MINIMUM_STATUS_FOR_ARCHIVE is VenueStatus.DATA_AVAILABLE


class TestSymbolResolution:
    async def test_resolved_records_are_stamped_with_the_canonical_id(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.resolved == 1
        assert report.bars_accepted == 1
        rows = archive.read_bars()
        assert rows[0].instrument_id == BTC_ID

    async def test_unknown_symbol_is_refused_never_guessed(self, archive: ParquetArchive) -> None:
        """The most expensive bug in the system is a wrong instrument id. Refuse instead."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(symbol="ETHUSDT")])
        assert report.bars_accepted == 0
        assert report.bars_rejected == 1
        assert "BYBIT:ETHUSDT" in report.unresolved_symbols
        assert any("INSTRUMENT_UNKNOWN" in k for k in report.rejection_reasons)
        assert archive.read_bars() == []  # nothing was archived under a made-up id

    async def test_unknown_venue_is_refused(self, archive: ParquetArchive) -> None:
        """BTCUSDT at Bybit says nothing about BTCUSDT at OKX."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.OKX, bars=[make_bar(venue="OKX")])
        assert report.bars_accepted == 0
        assert "OKX:BTCUSDT" in report.unresolved_symbols

    async def test_uncertified_mapping_cannot_feed_the_archive(self, archive: ParquetArchive) -> None:
        """A feed nobody has verified working is not evidence."""
        pipeline = IngestionPipeline(
            registry=make_registry(status=VenueStatus.SUPPORTED),
            archive=archive,
            now_fn=lambda: NOW,
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.bars_accepted == 0
        assert report.status_refusals == {"BYBIT:SUPPORTED": 1}
        assert any("INSTRUMENT_NOT_CERTIFIED" in k for k in report.rejection_reasons)
        assert archive.read_bars() == []

    @pytest.mark.parametrize(
        "status",
        [VenueStatus.UNKNOWN, VenueStatus.SUPPORTED, VenueStatus.CONNECTED],
    )
    async def test_every_status_below_data_available_is_refused(
        self, archive: ParquetArchive, status: VenueStatus
    ) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(status=status), archive=archive, now_fn=lambda: NOW
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.bars_accepted == 0

    @pytest.mark.parametrize(
        "status",
        [VenueStatus.DATA_AVAILABLE, VenueStatus.TRADE_ENABLED, VenueStatus.LIVE_VERIFIED],
    )
    async def test_data_available_and_above_are_accepted(
        self, archive: ParquetArchive, status: VenueStatus
    ) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(status=status), archive=archive, now_fn=lambda: NOW
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.bars_accepted == 1

    async def test_a_stricter_minimum_status_can_be_configured(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(status=VenueStatus.DATA_AVAILABLE),
            archive=archive,
            minimum_status=VenueStatus.TRADE_ENABLED,
            now_fn=lambda: NOW,
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.bars_accepted == 0

    async def test_resolution_rate_is_reported(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar(), make_bar(symbol="ETHUSDT")],
        )
        assert report.resolution_rate == pytest.approx(0.5)


class TestValidation:
    async def test_inconsistent_ohlc_is_rejected(self, archive: ParquetArchive) -> None:
        bad = BarRecord(
            instrument_id="",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            interval="1m",
            open_time=NOW,
            close_time=None,
            open=D("100"),
            high=D("90"),  # below the open
            low=D("110"),
            close=D("100"),
            confirmed=True,
        )
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[bad])
        assert report.bars_accepted == 0
        assert any("OHLC_INCONSISTENT" in k for k in report.rejection_reasons)
        assert archive.read_bars() == []

    async def test_non_positive_tick_price_is_rejected(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            ticks=[make_tick(price="0"), make_tick(price="-1", at=NOW + timedelta(seconds=1))],
        )
        assert report.ticks_accepted == 0
        assert report.rejection_reasons.get("NON_POSITIVE_PRICE") == 2

    async def test_crossed_quote_is_rejected(self, archive: ParquetArchive) -> None:
        crossed = QuoteRecord(
            instrument_id="",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            bid=D("99000.10"),
            ask=D("98999.90"),  # below the bid
            observed_at=NOW,
        )
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, quotes=[crossed])
        assert report.quotes_accepted == 0
        assert any("CROSSED_OR_LOCKED" in k for k in report.rejection_reasons)

    async def test_valid_records_are_accepted(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()], quotes=[make_quote()])
        assert report.bars_accepted == 1
        assert report.quotes_accepted == 1
        assert report.total_rejected == 0
        assert report.rejection_rate == 0.0


class TestDegradation:
    async def test_high_rejection_rate_marks_the_pass_degraded(self, archive: ParquetArchive) -> None:
        """A feed that is 40% garbage is an outage, not a normal day."""
        bad = [make_bar(at=NOW + timedelta(minutes=m), symbol=f"NOPE{m}") for m in range(4)]
        good = [make_bar(at=NOW + timedelta(minutes=10))]
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[*good, *bad])
        assert report.rejection_rate > 0.25
        assert any("DEGRADED" in e for e in report.errors)

    async def test_clean_pass_is_not_marked_degraded(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert not any("DEGRADED" in e for e in report.errors)

    async def test_empty_pass_is_not_marked_degraded(self, archive: ParquetArchive) -> None:
        """Zero records is not a 0/0 rejection rate crisis."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[])
        assert report.rejection_rate == 0.0
        assert not any("DEGRADED" in e for e in report.errors)

    async def test_threshold_is_configurable(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            max_rejection_rate=0.0,
            now_fn=lambda: NOW,
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(), make_bar(symbol="NOPE")])
        assert any("DEGRADED" in e for e in report.errors)


class TestTickAggregation:
    async def test_ticks_are_aggregated_into_minute_bars(self, archive: ParquetArchive) -> None:
        ticks = [make_tick(at=NOW + timedelta(seconds=s), price=str(99000 + s)) for s in range(5)]
        pipeline = IngestionPipeline(
            registry=make_registry(), archive=archive, now_fn=lambda: NOW + timedelta(minutes=10)
        )
        report = await pipeline.run(venue=Venue.BYBIT, ticks=ticks)
        assert report.ticks_accepted == 5
        assert report.bars_from_ticks_produced == 1
        bars = archive.read_bars(confirmed_only=False)
        assert len(bars) == 1
        assert bars[0].interval == "1m"
        assert bars[0].instrument_id == BTC_ID
        assert bars[0].source.startswith("AGGREGATED_FROM_TICKS")

    async def test_aggregation_can_be_disabled(self, archive: ParquetArchive) -> None:
        ticks = [make_tick(at=NOW + timedelta(seconds=s)) for s in range(3)]
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, ticks=ticks, aggregate_ticks_to=None)
        assert report.ticks_accepted == 3
        assert report.bars_from_ticks_produced == 0
        assert archive.read_bars(confirmed_only=False) == []

    async def test_aggregated_bars_are_validated_too(self, archive: ParquetArchive) -> None:
        """A bar NEXUS built is not more trustworthy than one a venue published."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        # Only invalid ticks: nothing should reach the archive.
        report = await pipeline.run(venue=Venue.BYBIT, ticks=[make_tick(price="0")])
        assert report.bars_from_ticks_produced == 0
        assert archive.read_bars(confirmed_only=False) == []

    async def test_ticks_from_different_instruments_are_not_mixed_into_one_bar(
        self, archive: ParquetArchive
    ) -> None:
        """Mixing venues or instruments into one bar creates a price series that never existed."""
        registry = make_registry()
        registry.register(
            build_instrument(
                canonical_symbol="ETH/USDT:USDT",
                asset_class=AssetClass.CRYPTO_PERP,
                base_currency="ETH",
                quote_currency="USDT",
                mappings=[VenueMapping(venue=Venue.BYBIT, venue_symbol="ETHUSDT", contract_size=D("1"))],
            ),
        )
        registry.certify("INS-ETH-USDT-USDT", Venue.BYBIT, VenueStatus.SUPPORTED, evidence="adapter written")
        registry.certify(
            "INS-ETH-USDT-USDT", Venue.BYBIT, VenueStatus.CONNECTED, evidence="connectivity proved"
        )
        registry.certify(
            "INS-ETH-USDT-USDT", Venue.BYBIT, VenueStatus.DATA_AVAILABLE, evidence="feed observed"
        )

        pipeline = IngestionPipeline(
            registry=registry, archive=archive, now_fn=lambda: NOW + timedelta(minutes=10)
        )
        report = await pipeline.run(
            venue=Venue.BYBIT,
            ticks=[
                make_tick(price="99000"),
                make_tick(symbol="ETHUSDT", price="3000", at=NOW + timedelta(seconds=1)),
            ],
        )
        assert report.ticks_accepted == 2
        bars = archive.read_bars(confirmed_only=False)
        assert len(bars) == 2
        assert {b.instrument_id for b in bars} == {BTC_ID, "INS-ETH-USDT-USDT"}


class TestArchiveBeforePublish:
    async def test_the_archive_holds_the_data_before_any_event_is_published(
        self, archive: ParquetArchive
    ) -> None:
        """Otherwise a consumer could read data that vanishes on restart."""
        publisher = RecordingPublisher()
        publisher.attach(archive)
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=publisher,
            now_fn=lambda: NOW,
        )
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert publisher.events
        # At the moment of publication the file already existed.
        assert all(count >= 1 for count in publisher.calls_at_publish)

    async def test_event_topics_are_published(self, archive: ParquetArchive) -> None:
        publisher = RecordingPublisher()
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=publisher,
            now_fn=lambda: NOW,
        )
        await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar()],
            quotes=[make_quote()],
            aggregate_ticks_to=None,
        )
        topics = [topic for topic, _ in publisher.events]
        assert "market.bars.archived" in topics
        assert "market.quotes.archived" in topics

    async def test_event_payloads_carry_no_secret_material(self, archive: ParquetArchive) -> None:
        publisher = RecordingPublisher()
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=publisher,
            now_fn=lambda: NOW,
        )
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        for _topic, payload in publisher.events:
            text = str(payload).lower()
            for forbidden in ("api_key", "secret", "token", "password", "passphrase"):
                assert forbidden not in text

    async def test_events_can_be_suppressed(self, archive: ParquetArchive) -> None:
        publisher = RecordingPublisher()
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=publisher,
            now_fn=lambda: NOW,
        )
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()], emit_events=False)
        assert publisher.events == []
        assert archive.read_bars()  # still archived

    async def test_tick_events_are_published(self, archive: ParquetArchive) -> None:
        publisher = RecordingPublisher()
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=publisher,
            now_fn=lambda: NOW + timedelta(minutes=5),
        )
        await pipeline.run(venue=Venue.BYBIT, ticks=[make_tick()])
        topics = [topic for topic, _ in publisher.events]
        assert "market.ticks.archived" in topics


class TestReportIntegrity:
    async def test_a_fault_still_produces_a_report(self, archive: ParquetArchive) -> None:
        """A pass must always report something — a silent failure is the worst outcome."""

        def exploding_publish(topic: str, payload: dict[str, object]) -> None:
            raise RuntimeError("bus down")

        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            publish=exploding_publish,
            now_fn=lambda: NOW,
        )
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert isinstance(report, PipelineReport)
        assert report.errors
        assert any("bus down" in e for e in report.errors)
        assert report.finished_at is not None

    async def test_reports_are_retained_in_order(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(at=NOW + timedelta(minutes=1))])
        assert len(pipeline.reports) == 2
        assert pipeline.last_report is pipeline.reports[-1]

    async def test_report_is_always_finished(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.finished_at == NOW

    async def test_audit_payload_omits_free_text_errors(self, archive: ParquetArchive) -> None:
        """Venue error text is untrusted free text; it belongs in logs, not in the audit chain."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(symbol="NOPE")])
        assert report.errors or report.unresolved_symbols
        payload = report.to_audit_payload()
        assert "errors" not in payload
        assert payload["rejection_reasons"]

    async def test_error_list_is_bounded(self) -> None:
        report = PipelineReport(started_at=NOW)
        for index in range(500):
            report.errors.append(f"error {index}")
        assert len(report.to_dict()["errors"]) <= 20

    async def test_unresolved_symbol_list_is_bounded(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar(symbol=f"NOPE{i}") for i in range(200)],
        )
        assert len(report.unresolved_symbols) == 200  # internal state is complete
        assert len(report.to_dict()["unresolved_symbols"]) <= 50  # the payload is bounded

    async def test_report_counts_are_consistent(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar(), make_bar(symbol="NOPE")],
            quotes=[make_quote()],
        )
        assert report.total_accepted == report.bars_accepted + report.ticks_accepted + report.quotes_accepted
        assert report.total_rejected == report.bars_rejected + report.ticks_rejected + report.quotes_rejected
        assert report.total_accepted == 2
        assert report.total_rejected == 1

    async def test_no_archive_configured_is_reported_not_silent(self) -> None:
        """Accepting records that were never persisted must be visible."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=None, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        assert report.bars_accepted == 1
        assert any("no archive configured" in e for e in report.errors)

    async def test_report_payload_is_json_safe(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        payload = report.to_dict()
        assert payload["started_at"].endswith("Z")
        assert payload["bars"]["accepted"] == 1
        assert isinstance(payload["archive_writes"], list)


class TestSummarise:
    async def test_summary_across_passes(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(symbol="NOPE")])
        summary = summarise_reports(pipeline.reports)
        assert summary["passes"] == 2
        assert summary["accepted"] == 1
        assert summary["rejected"] == 1
        # The second pass rejected everything it was given (rate 1.0 > 0.25), so it is
        # correctly flagged DEGRADED even though the first pass was clean.
        assert summary["degraded"] is True
        assert summary["unresolved_symbols"] == ["BYBIT:NOPE"]

    async def test_summary_flags_degradation(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(),
            archive=archive,
            max_rejection_rate=0.0,
            now_fn=lambda: NOW,
        )
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar(symbol="NOPE")])
        assert summarise_reports(pipeline.reports)["degraded"] is True

    def test_summary_of_no_passes(self) -> None:
        summary = summarise_reports([])
        assert summary == {"passes": 0, "accepted": 0, "rejected": 0, "degraded": False}

    async def test_summary_timestamps_are_utc(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        summary = summarise_reports(pipeline.reports)
        assert summary["first_started"].endswith("Z")
        assert summary["last_finished"].endswith("Z")
        assert summary["timezone_note"] == "all timestamps UTC"


class TestEndToEndArchiveContent:
    async def test_bars_and_ticks_land_in_separate_datasets(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(
            registry=make_registry(), archive=archive, now_fn=lambda: NOW + timedelta(minutes=10)
        )
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()], ticks=[make_tick()])
        manifest = archive.manifest()
        datasets = {key.split("/")[0] for key in manifest["partitions"]}
        assert "dataset=bars" in datasets

    async def test_venue_and_source_provenance_is_preserved(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()])
        row = archive.read_bars()[0]
        assert row.venue == "BYBIT"
        assert row.venue_symbol == "BTCUSDT"
        assert row.source == "BYBIT_V5_PUBLIC_REST"

    async def test_prices_are_exact_after_the_whole_pipeline(self, archive: ParquetArchive) -> None:
        """A 10-decimal price must survive ingest, Parquet and read-back bit-for-bit."""
        exact = BarRecord(
            instrument_id="",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            interval="1m",
            open_time=NOW,
            close_time=NOW + timedelta(minutes=1),
            open=D("99123.45678901"),
            high=D("99200.00000000"),
            low=D("99000.00000000"),
            close=D("99123.45678902"),
            volume=D("0.00000001"),
            confirmed=True,
            source="TEST",
        )
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        await pipeline.run(venue=Venue.BYBIT, bars=[exact])
        row = archive.read_bars()[0]
        assert row.open == D("99123.45678901")
        assert row.close == D("99123.45678902")
        assert row.volume == D("0.00000001")


class TestResolutionRateUnits:
    """Regression: `resolved` counted *records* while `symbols_requested` counted *symbols*.

    620 records for one symbol reported a resolution rate of 62,000%. A rate whose two sides
    are different units is worse than no rate at all, because it looks like a measurement.
    """

    async def test_many_records_for_one_symbol_resolve_once(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        bars = [make_bar(at=NOW - timedelta(minutes=m)) for m in range(620)]
        report = await pipeline.run(venue=Venue.BYBIT, bars=bars)
        assert report.bars_accepted == 620
        assert report.symbols_requested == 1
        assert report.resolved == 1
        assert report.resolution_rate == 1.0  # not 620.0

    async def test_rate_stays_within_zero_and_one_for_a_mixed_pass(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar(), make_bar(at=NOW - timedelta(minutes=1)), make_bar(symbol="ETHUSDT")],
            ticks=[make_tick(), make_tick(at=NOW - timedelta(seconds=30))],
        )
        assert report.symbols_requested == 2  # BTCUSDT + ETHUSDT, counted once each
        assert report.resolved == 1
        assert report.resolution_rate == 0.5
        assert 0.0 <= report.resolution_rate <= 1.0

    async def test_ticks_and_bars_for_the_same_symbol_are_not_double_counted(
        self, archive: ParquetArchive
    ) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT, bars=[make_bar()], ticks=[make_tick()], quotes=[make_quote()]
        )
        assert report.symbols_requested == 1
        assert report.resolved == 1
        assert report.resolution_rate == 1.0

    async def test_explicit_symbols_requested_override_still_governs_the_rate(
        self, archive: ParquetArchive
    ) -> None:
        """A caller that knows it asked for more symbols than it delivered records for."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, bars=[make_bar()], symbols_requested=4)
        assert report.symbols_requested == 4
        assert report.resolved == 1
        assert report.resolution_rate == 0.25

    async def test_a_rate_above_one_is_left_visible_not_clamped(self, archive: ParquetArchive) -> None:
        """Clamping would hide the caller's own inconsistency; the number must stay honest.

        Two symbols genuinely resolve, but the caller claims it only asked for one — so the
        rate exceeds 1.0 and says so rather than being silently floored at 100%.
        """
        registry = make_registry()
        registry.register(
            build_instrument(
                canonical_symbol="ETH/USDT:USDT",
                asset_class=AssetClass.CRYPTO_PERP,
                base_currency="ETH",
                quote_currency="USDT",
                mappings=[
                    VenueMapping(
                        venue=Venue.BYBIT,
                        venue_symbol="ETHUSDT",
                        contract_size=D("1"),
                        tick_size=D("0.01"),
                        quote_currency="USDT",
                    ),
                ],
            ),
        )
        for step in (VenueStatus.SUPPORTED, VenueStatus.CONNECTED, VenueStatus.DATA_AVAILABLE):
            registry.certify("INS-ETH-USDT-USDT", Venue.BYBIT, step, evidence=f"proved {step.value}")

        pipeline = IngestionPipeline(registry=registry, archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(
            venue=Venue.BYBIT,
            bars=[make_bar(), make_bar(symbol="ETHUSDT", at=NOW - timedelta(minutes=1))],
            symbols_requested=1,
        )
        assert report.resolved == 2
        assert report.resolution_rate > 1.0
        assert report.to_dict()["resolution_rate"] > 1.0
        assert report.total_rejected == 0  # both symbols were known; nothing was refused


class TestAggregationFaultsAreVisible:
    """Regression: ticks excluded during bar building were invisible to the rejection rate.

    A feed with a broken clock sends future-dated ticks. They pass the gate and are archived
    as evidence, but `bars_from_ticks` refuses them. Before this fix the pass reported a 0%
    rejection rate and `degraded=False` while producing almost no bars — degradation that
    looked exactly like success.
    """

    async def test_future_ticks_are_archived_but_excluded_from_bars(self, archive: ParquetArchive) -> None:
        """The archive keeps what the feed said; the gates decide what may be used."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        future = [make_tick(at=NOW + timedelta(seconds=2 * i)) for i in range(500)]
        report = await pipeline.run(venue=Venue.BYBIT, ticks=future)

        assert report.ticks_accepted == 500  # structurally valid, kept as evidence
        assert report.bars_from_ticks_produced <= 1  # but almost nothing is usable
        assert report.aggregation_rejected >= 499
        assert any("AGGREGATION:FUTURE_TIMESTAMP" in k for k in report.rejection_reasons)

    async def test_aggregation_exclusions_drive_the_rejection_rate(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        future = [make_tick(at=NOW + timedelta(seconds=2 * i)) for i in range(500)]
        report = await pipeline.run(venue=Venue.BYBIT, ticks=future)
        assert report.rejection_rate > 0.25
        assert any("DEGRADED" in e for e in report.errors)

    async def test_accepted_plus_rejected_identity_is_preserved(self, archive: ParquetArchive) -> None:
        """Aggregation faults are a separate counter, so the gate identity must still hold."""
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        future = [make_tick(at=NOW + timedelta(seconds=2 * i)) for i in range(500)]
        report = await pipeline.run(venue=Venue.BYBIT, ticks=future)
        assert report.total_rejected == report.bars_rejected + report.ticks_rejected + report.quotes_rejected
        assert report.total_rejected == 0  # nothing was refused at the gate
        assert report.total_faults == report.total_rejected + report.aggregation_rejected
        assert report.total_faults > 0

    async def test_a_clean_pass_reports_no_aggregation_faults(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        past = [make_tick(at=NOW - timedelta(seconds=2 * i)) for i in range(500)]
        report = await pipeline.run(venue=Venue.BYBIT, ticks=past)
        assert report.aggregation_rejected == 0
        assert report.bars_from_ticks_produced > 1
        assert report.rejection_rate == 0.0
        assert not any("DEGRADED" in e for e in report.errors)

    async def test_new_counters_appear_in_the_report_payload(self, archive: ParquetArchive) -> None:
        pipeline = IngestionPipeline(registry=make_registry(), archive=archive, now_fn=lambda: NOW)
        report = await pipeline.run(venue=Venue.BYBIT, ticks=[make_tick(at=NOW + timedelta(hours=1))])
        payload = report.to_dict()
        assert payload["aggregation_rejected"] == report.aggregation_rejected
        assert payload["total_faults"] == report.total_faults
        assert payload["resolved"] == 1
        # The audit payload keeps the same shape minus untrusted free text.
        audit = report.to_audit_payload()
        assert "errors" not in audit
        assert audit["total_faults"] == report.total_faults
