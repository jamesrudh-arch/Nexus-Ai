"""Parquet archive (Phase 3): exact Decimal round-trip, partitioning, honest manifests.

The archive is the system's memory, so the property that matters most is *exactness*: a price
written as ``Decimal("99123.40")`` must read back as exactly that, not as a float that has
drifted. Money is stored as text for precisely this reason.

Also pinned here: a naive timestamp is refused rather than assumed UTC, files are never
overwritten in place, and the manifest reports what actually exists instead of what was
requested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.archive.parquet_store import (
    BAR_COLUMNS,
    COMPRESSION,
    FORMAT_VERSION,
    ArchiveError,
    ArchiveUnavailable,
    ParquetArchive,
)
from nexus.data.records import BarRecord, QuoteRecord, TickRecord

D = Decimal
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def make_bar(
    at: datetime = NOW,
    *,
    interval: str = "1m",
    venue: str = "BYBIT",
    symbol: str = "BTCUSDT",
    open_px: str = "99123.40",
    volume: str | None = "10.5",
    confirmed: bool = True,
) -> BarRecord:
    return BarRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue=venue,
        venue_symbol=symbol,
        interval=interval,
        open_time=at,
        close_time=at + timedelta(minutes=1),
        open=D(open_px),
        high=D("99200.00"),
        low=D("99000.00"),
        close=D("99150.10"),
        volume=D(volume) if volume is not None else None,
        quote_volume=D("1040795.70") if volume is not None else None,
        trades=42,
        confirmed=confirmed,
        source="TEST",
    )


def make_tick(at: datetime = NOW, *, price: str = "99123.40", symbol: str = "BTCUSDT") -> TickRecord:
    return TickRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue="BYBIT",
        venue_symbol=symbol,
        price=D(price),
        quantity=D("0.001"),
        observed_at=at,
        venue_timestamp=at,
        side="BUY",
        trade_id=f"exec-{int(at.timestamp() * 1000)}",
        source="TEST",
    )


def make_quote(at: datetime = NOW, *, symbol: str = "BTCUSDT") -> QuoteRecord:
    return QuoteRecord(
        instrument_id="INS-BTC-USDT-USDT",
        venue="BYBIT",
        venue_symbol=symbol,
        bid=D("99123.30"),
        ask=D("99123.50"),
        bid_size=D("0.5"),
        ask_size=D("0.75"),
        last=D("99123.40"),
        observed_at=at,
        venue_timestamp=at,
        delayed=False,
        source="TEST",
    )


@pytest.fixture
def archive(tmp_path: Path) -> ParquetArchive:
    return ParquetArchive(tmp_path / "archive", now_fn=lambda: NOW)


pytest.importorskip("pyarrow", reason="archive extra not installed")


class TestDecimalExactness:
    def test_price_survives_a_round_trip_exactly(self, archive: ParquetArchive) -> None:
        """The whole reason prices are stored as text rather than as float64."""
        archive.write_bars([make_bar(open_px="99123.40")])
        rows = archive.read_bars()
        assert len(rows) == 1
        assert rows[0].open == D("99123.40")
        assert isinstance(rows[0].open, Decimal)

    def test_high_precision_value_is_not_truncated(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(open_px="0.000000012345678901")])
        rows = archive.read_bars()
        assert rows[0].open == D("0.000000012345678901")

    def test_large_value_is_not_scientific_notation_mangled(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(open_px="12345678901234567890.12345")])
        rows = archive.read_bars()
        assert rows[0].open == D("12345678901234567890.12345")

    def test_volume_round_trips(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(volume="10.5")])
        assert archive.read_bars()[0].volume == D("10.5")

    def test_null_volume_stays_null_not_zero(self, archive: ParquetArchive) -> None:
        """Zero volume is a claim; absence is not. A NULL must not become 0."""
        archive.write_bars([make_bar(volume=None)])
        rows = archive.read_bars()
        assert rows[0].volume is None
        assert rows[0].quote_volume is None

    def test_tick_price_round_trips(self, archive: ParquetArchive) -> None:
        archive.write_ticks([make_tick(price="1.08500")])
        files = list(archive.root.rglob("*.parquet"))
        assert len(files) == 1

    def test_quote_spread_round_trips(self, archive: ParquetArchive) -> None:
        archive.write_quotes([make_quote()])
        files = list(archive.root.rglob("*.parquet"))
        assert len(files) == 1


class TestNaiveTimestampRefusal:
    def test_naive_bar_open_time_is_refused(self, archive: ParquetArchive) -> None:
        """Assuming UTC for a naive timestamp is how archives get shifted by hours."""
        naive = BarRecord(
            instrument_id="I",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            interval="1m",
            open_time=datetime(2026, 11, 25, 12, 0),  # naive
            close_time=None,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
        )
        with pytest.raises(ArchiveError, match="naive"):
            archive.write_bars([naive])

    def test_naive_tick_time_is_refused(self, archive: ParquetArchive) -> None:
        naive = TickRecord(
            instrument_id="I",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            price=D("1"),
            quantity=D("1"),
            observed_at=datetime(2026, 11, 25, 12, 0),
        )
        with pytest.raises(ArchiveError, match="naive"):
            archive.write_ticks([naive])

    def test_quote_without_observation_time_is_refused(self, archive: ParquetArchive) -> None:
        """An undatable row cannot be partitioned, so it cannot be archived."""
        quote = QuoteRecord(
            instrument_id="I",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            bid=D("1"),
            ask=D("2"),
            observed_at=None,
        )
        with pytest.raises(ArchiveError, match="has no timestamp"):
            archive.write_quotes([quote])
        # Nothing was written: an undatable row must not leave a partial file behind.
        assert archive.count_files() == 0

    def test_non_utc_timezone_is_normalised_on_write(self, archive: ParquetArchive) -> None:
        from zoneinfo import ZoneInfo

        lagos = BarRecord(
            instrument_id="I",
            venue="BYBIT",
            venue_symbol="BTCUSDT",
            interval="1m",
            open_time=datetime(2026, 11, 25, 13, 0, tzinfo=ZoneInfo("Africa/Lagos")),  # 12:00 UTC
            close_time=None,
            open=D("1"),
            high=D("1"),
            low=D("1"),
            close=D("1"),
            confirmed=True,  # a read defaults to confirmed_only=True
        )
        result = archive.write_bars([lagos])
        assert result.rows_written == 1
        rows = archive.read_bars()
        assert rows[0].open_time == NOW
        assert rows[0].open_time.tzinfo is not None


class TestPartitioning:
    def test_partition_path_is_hive_style(self, archive: ParquetArchive) -> None:
        path = archive.partition_dir("bars", "BYBIT", "BTCUSDT", "1m", NOW)
        assert path.name == "month=11"
        assert "year=2026" in str(path)
        assert "interval=1m" in str(path)
        assert "symbol=BTCUSDT" in str(path)
        assert "venue=BYBIT" in str(path)
        assert "dataset=bars" in str(path)

    def test_partition_uses_record_time_not_wall_clock(self, archive: ParquetArchive) -> None:
        """A historical backfill must land in the partition it belongs to, not in 'today'."""
        old = NOW - timedelta(days=400)
        archive.write_bars([make_bar(at=old)])
        path = archive.partition_dir("bars", "BYBIT", "BTCUSDT", "1m", old)
        assert "year=2025" in str(path)
        assert path.exists()

    def test_symbols_with_slashes_are_made_path_safe(self, archive: ParquetArchive) -> None:
        """``BTC/USDT:USDT`` would otherwise create nested directories."""
        path = archive.partition_dir("bars", "BYBIT", "BTC/USDT:USDT", "1m", NOW)
        assert "symbol=BTC-USDT-USDT" in str(path)
        assert "/" not in path.name

    def test_separate_intervals_get_separate_partitions(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(interval="1m"), make_bar(interval="5m")])
        assert archive.count_files() == 2

    def test_separate_months_get_separate_partitions(self, archive: ParquetArchive) -> None:
        archive.write_bars(
            [
                make_bar(at=datetime(2026, 10, 15, 12, 0, tzinfo=UTC)),
                make_bar(at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC)),
            ],
        )
        assert archive.count_files() == 2

    def test_same_partition_batches_into_one_file(self, archive: ParquetArchive) -> None:
        bars = [make_bar(at=NOW + timedelta(minutes=m)) for m in range(10)]
        result = archive.write_bars(bars)
        assert result.rows_written == 10
        assert archive.count_files() == 1


class TestWriteBehaviour:
    def test_empty_write_creates_nothing(self, archive: ParquetArchive) -> None:
        result = archive.write_bars([])
        assert result.skipped_empty is True
        assert result.rows_written == 0
        assert archive.count_files() == 0
        assert not archive.root.exists()

    def test_files_are_never_overwritten(self, archive: ParquetArchive) -> None:
        """Rewriting history destroys the ability to prove what was known when."""
        archive.write_bars([make_bar(at=NOW)])
        archive.write_bars([make_bar(at=NOW + timedelta(minutes=1))])
        assert archive.count_files() == 2
        rows = archive.read_bars()
        assert len(rows) == 2

    def test_write_result_reports_bytes(self, archive: ParquetArchive) -> None:
        result = archive.write_bars([make_bar()])
        assert result.bytes_written > 0
        assert result.path is not None
        assert result.path.exists()
        assert result.wrote_at == NOW

    def test_stats_accumulate(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar()])
        archive.write_bars([make_bar(at=NOW + timedelta(minutes=1))])
        stats = archive.stats
        assert stats["files_written"] == 2
        assert stats["bytes_written"] > 0
        assert stats["exists"] is True

    def test_compression_is_zstd(self) -> None:
        assert COMPRESSION == "zstd"

    def test_format_version_is_declared(self) -> None:
        assert FORMAT_VERSION == "nexus-archive-v1"

    def test_schema_columns_include_provenance(self) -> None:
        names = [name for name, _ in BAR_COLUMNS]
        for required in ("instrument_id", "venue", "venue_symbol", "source", "ingested_at", "confirmed"):
            assert required in names

    def test_price_columns_are_strings(self) -> None:
        types = dict(BAR_COLUMNS)
        for column in ("open", "high", "low", "close", "volume", "quote_volume"):
            assert types[column] == "string"


class TestReads:
    def test_confirmed_only_is_the_default(self, archive: ParquetArchive) -> None:
        archive.write_bars(
            [make_bar(confirmed=True), make_bar(at=NOW + timedelta(minutes=1), confirmed=False)]
        )
        assert len(archive.read_bars()) == 1
        assert len(archive.read_bars(confirmed_only=False)) == 2

    def test_filter_by_interval(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(interval="1m"), make_bar(interval="5m")])
        assert len(archive.read_bars(interval="1m")) == 1
        assert len(archive.read_bars(interval="5m")) == 1

    def test_filter_by_venue_is_case_insensitive(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(venue="BYBIT")])
        assert len(archive.read_bars(venue="bybit")) == 1

    def test_filter_by_time_range(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(at=NOW + timedelta(minutes=m)) for m in range(10)])
        rows = archive.read_bars(start=NOW + timedelta(minutes=3), end=NOW + timedelta(minutes=6))
        assert len(rows) == 3
        assert rows[0].open_time == NOW + timedelta(minutes=3)

    def test_rows_are_returned_in_chronological_order(self, archive: ParquetArchive) -> None:
        bars = [make_bar(at=NOW + timedelta(minutes=m)) for m in range(5)]
        archive.write_bars(list(reversed(bars)))
        rows = archive.read_bars()
        assert [r.open_time for r in rows] == sorted(r.open_time for r in rows)

    def test_limit_is_applied(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(at=NOW + timedelta(minutes=m)) for m in range(10)])
        assert len(archive.read_bars(limit=3)) == 3

    def test_empty_archive_reads_as_empty_not_error(self, archive: ParquetArchive) -> None:
        assert archive.read_bars() == []
        assert archive.count_files() == 0
        assert archive.total_bytes() == 0

    def test_read_preserves_all_ohlc_fields(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar()])
        row = archive.read_bars()[0]
        assert row.high == D("99200.00")
        assert row.low == D("99000.00")
        assert row.close == D("99150.10")
        assert row.quote_volume == D("1040795.70")
        assert row.trades == 42
        assert row.confirmed is True
        assert row.interval == "1m"
        assert row.instrument_id == "INS-BTC-USDT-USDT"


class TestManifest:
    def test_manifest_reports_what_actually_exists(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar()])
        manifest = archive.manifest()
        assert manifest["format_version"] == FORMAT_VERSION
        assert manifest["files"] == 1
        assert manifest["bytes"] > 0
        assert len(manifest["partitions"]) == 1
        partition = next(iter(manifest["partitions"].values()))
        assert partition["files"] == 1
        assert partition["bytes"] > 0

    def test_manifest_of_an_empty_archive(self, archive: ParquetArchive) -> None:
        manifest = archive.manifest()
        assert manifest["files"] == 0
        assert manifest["partitions"] == {}

    def test_manifest_is_persisted_as_json(self, archive: ParquetArchive) -> None:
        import json

        archive.write_bars([make_bar()])
        path = archive.write_manifest()
        assert path.exists()
        payload = json.loads(path.read_text())
        assert payload["files"] == 1

    def test_manifest_partitions_are_keyed_by_hive_path(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(interval="1m"), make_bar(interval="5m")])
        manifest = archive.manifest()
        assert len(manifest["partitions"]) == 2
        assert any("interval=1m" in key for key in manifest["partitions"])


class TestFailClosedDependencies:
    def test_missing_pyarrow_raises_rather_than_degrading(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Falling back to CSV would silently lose Decimal exactness."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("pyarrow"):
                raise ImportError("simulated: pyarrow not installed")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        archive = ParquetArchive(tmp_path / "never-created")
        with pytest.raises(ArchiveUnavailable, match="refuses to fall back"):
            archive.write_bars([make_bar()])

    def test_missing_duckdb_raises_rather_than_degrading(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("duckdb"):
                raise ImportError("simulated: duckdb not installed")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        archive = ParquetArchive(tmp_path / "never-created")
        with pytest.raises(ArchiveUnavailable, match="archive reads are unavailable"):
            archive.read_bars()

    def test_unavailable_error_is_not_retryable(self) -> None:
        error = ArchiveUnavailable("x")
        assert error.retryable is False


class TestPathSafety:
    def test_a_quote_in_the_root_path_is_refused(self, tmp_path: Path) -> None:
        """The archive root is interpolated into a SQL literal; a quote must not become injection."""
        archive = ParquetArchive(tmp_path / "bad'name")
        archive.write_bars([make_bar()])
        with pytest.raises(ArchiveError, match="quote character"):
            archive.read_bars()


class TestAnonymousRecordsAreRefused:
    """Regression: a record with a blank venue/symbol partitioned into `venue=/symbol=`.

    Every anonymous record in the system would share that one directory — unfindable by any
    `read_bars(venue=...)` filter and silently colliding across instruments. Refusing the
    write is the only honest option: an unattributable archive is worse than no archive.
    """

    def test_a_bar_with_no_venue_is_refused(self, archive: ParquetArchive) -> None:
        with pytest.raises(ArchiveError, match="no venue or venue_symbol"):
            archive.write_bars([make_bar(venue="")])
        assert archive.count_files() == 0

    def test_a_bar_with_no_symbol_is_refused(self, archive: ParquetArchive) -> None:
        with pytest.raises(ArchiveError, match="no venue or venue_symbol"):
            archive.write_bars([make_bar(symbol="")])
        assert archive.count_files() == 0

    def test_a_tick_with_no_venue_is_refused(self, archive: ParquetArchive) -> None:
        import dataclasses

        with pytest.raises(ArchiveError, match="no venue or venue_symbol"):
            archive.write_ticks([dataclasses.replace(make_tick(), venue="")])
        assert archive.count_files() == 0

    def test_a_quote_with_no_symbol_is_refused(self, archive: ParquetArchive) -> None:
        with pytest.raises(ArchiveError, match="no venue or venue_symbol"):
            archive.write_quotes([make_quote(symbol="")])
        assert archive.count_files() == 0

    def test_one_anonymous_record_refuses_the_whole_write(self, archive: ParquetArchive) -> None:
        """Partial writes would leave the archive holding some of a batch nobody can attribute."""
        with pytest.raises(ArchiveError, match="no venue or venue_symbol"):
            archive.write_bars(
                [
                    make_bar(),
                    make_bar(at=NOW + timedelta(minutes=1)),
                    make_bar(at=NOW + timedelta(minutes=2), symbol=""),
                ],
            )
        assert archive.count_files() == 0
        assert archive.read_bars() == []

    def test_the_refusal_is_not_retryable(self, archive: ParquetArchive) -> None:
        """Retrying identical anonymous data can never succeed; it is a caller bug."""
        with pytest.raises(ArchiveError) as excinfo:
            archive.write_bars([make_bar(venue="")])
        assert excinfo.value.retryable is False

    def test_identified_records_still_write_normally(self, archive: ParquetArchive) -> None:
        archive.write_bars([make_bar(), make_bar(at=NOW + timedelta(minutes=1), symbol="ETHUSDT")])
        assert archive.count_files() == 2
        assert {b.venue_symbol for b in archive.read_bars()} == {"BTCUSDT", "ETHUSDT"}

    def test_no_empty_partition_directory_is_created(self, archive: ParquetArchive, tmp_path: Path) -> None:
        with pytest.raises(ArchiveError):
            archive.write_bars([make_bar(venue="", symbol="")])
        written = [p for p in tmp_path.rglob("*") if p.is_dir() and "venue=" in p.name]
        assert written == []
