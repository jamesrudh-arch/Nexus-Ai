"""First-party Parquet archive (Section 4.4 — "record from day one", Q-08/D-024).

Why a first-party archive instead of relying on venue history: free endpoints have no SLA
(Z-08), they trim their history without notice, and a backfill request during an outage
returns nothing. Whatever NEXUS observed is the only record that can be trusted to be
*complete*, because it is the one NEXUS wrote.

Format choices, all free/OSS:

* **Parquet + zstd.** Columnar so a research query reads only the columns it needs; zstd
  because on a 200 GB volume compression is the difference between a month of ticks and a
  week. Compression level is modest — CPU on a 2-OCPU free ARM VM is the scarcer resource.
* **Hive-style partitioning** ``dataset=.../venue=.../symbol=.../interval=.../year=.../month=...``
  so a query for one instrument never scans the whole archive.
* **DuckDB for reads** — it queries Parquet in place with no server process, which is what a
  single 12 GB VM can actually afford.
* **Decimal is stored as a string column.** Parquet has no exact decimal-with-unbounded-
  precision type that survives every reader; a string preserves the value exactly, and
  DuckDB/Arrow cast it back on read. Losing a cent of precision in a financial archive to
  save bytes is not a trade worth making.

Both pyarrow and duckdb are optional at import time and fail closed: if either is missing,
the store raises rather than silently writing CSV or losing data.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc
from nexus.data.records import BarRecord, QuoteRecord, TickRecord

COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3  # modest: CPU-bound on a 2 OCPU free ARM VM
FORMAT_VERSION = "nexus-archive-v1"


class ArchiveError(NexusError):
    """Raised when the archive cannot be written or read safely."""


class ArchiveUnavailable(ArchiveError):
    """pyarrow or duckdb is not installed. Fail closed — never degrade to CSV silently."""

    def __init__(self, detail: str) -> None:
        super().__init__(RejectReason.CONFIG_INVALID, detail, retryable=False)


def _require_pyarrow() -> Any:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ArchiveUnavailable(
            "pyarrow is not installed; the Parquet archive refuses to fall back to a lossy "
            "format. Install the 'archive' extra (free, Apache-2.0)."
        ) from exc
    return pa, pq


def _require_duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:
        raise ArchiveUnavailable(
            "duckdb is not installed; archive reads are unavailable. Install the 'archive' extra (free, MIT)."
        ) from exc
    return duckdb


#: Portable type kinds. The archive schema is declared in these terms rather than in pyarrow
#: alias strings, so (a) the module imports without pyarrow installed and (b) a reader
#: implementation can be swapped without rewriting every column definition.
TYPE_STRING = "string"
TYPE_INT64 = "int64"
TYPE_BOOL = "bool"
TYPE_TIMESTAMP_UTC_MS = "timestamp_utc_ms"

_TYPE_KINDS = frozenset({TYPE_STRING, TYPE_INT64, TYPE_BOOL, TYPE_TIMESTAMP_UTC_MS})


def _build_schema(pa: Any, columns: tuple[tuple[str, str], ...]) -> Any:
    """Materialise a pyarrow schema from the portable column declarations."""
    fields = []
    for name, kind in columns:
        if kind == TYPE_STRING:
            arrow_type = pa.string()
        elif kind == TYPE_INT64:
            arrow_type = pa.int64()
        elif kind == TYPE_BOOL:
            arrow_type = pa.bool_()
        elif kind == TYPE_TIMESTAMP_UTC_MS:
            arrow_type = pa.timestamp("ms", tz="UTC")
        else:  # pragma: no cover - guarded by _validate_columns
            raise ArchiveError(RejectReason.CONFIG_INVALID, f"unknown archive column type kind: {kind!r}")
        fields.append(pa.field(name, arrow_type))
    return pa.schema(fields)


def _validate_columns(columns: tuple[tuple[str, str], ...]) -> None:
    """Fail at import-construction time rather than mid-write on a typo'd column type."""
    for name, kind in columns:
        if kind not in _TYPE_KINDS:
            raise ValueError(f"archive column {name!r} has unknown type kind {kind!r}")


BAR_COLUMNS: tuple[tuple[str, str], ...] = (
    ("instrument_id", "string"),
    ("venue", "string"),
    ("venue_symbol", "string"),
    ("interval", "string"),
    ("open_time", TYPE_TIMESTAMP_UTC_MS),
    ("close_time", TYPE_TIMESTAMP_UTC_MS),
    ("open", "string"),  # Decimal preserved exactly as text
    ("high", "string"),
    ("low", "string"),
    ("close", "string"),
    ("volume", "string"),
    ("quote_volume", "string"),
    ("trades", "int64"),
    ("confirmed", "bool"),
    ("source", "string"),
    ("ingested_at", TYPE_TIMESTAMP_UTC_MS),
)

TICK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("instrument_id", "string"),
    ("venue", "string"),
    ("venue_symbol", "string"),
    ("observed_at", TYPE_TIMESTAMP_UTC_MS),
    ("venue_timestamp", TYPE_TIMESTAMP_UTC_MS),
    ("price", "string"),
    ("quantity", "string"),
    ("side", "string"),
    ("trade_id", "string"),
    ("source", "string"),
    ("ingested_at", TYPE_TIMESTAMP_UTC_MS),
)

QUOTE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("instrument_id", "string"),
    ("venue", "string"),
    ("venue_symbol", "string"),
    ("observed_at", TYPE_TIMESTAMP_UTC_MS),
    ("venue_timestamp", TYPE_TIMESTAMP_UTC_MS),
    ("bid", "string"),
    ("ask", "string"),
    ("bid_size", "string"),
    ("ask_size", "string"),
    ("last", "string"),
    ("delayed", "bool"),
    ("source", "string"),
    ("ingested_at", TYPE_TIMESTAMP_UTC_MS),
)


for _columns in (BAR_COLUMNS, TICK_COLUMNS, QUOTE_COLUMNS):
    _validate_columns(_columns)


def _dec(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _bar_rows(bars: Iterable[BarRecord], *, ingested_at: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        if bar.open_time.tzinfo is None:
            raise ArchiveError(
                RejectReason.CONFIG_INVALID,
                f"bar open_time for {bar.venue_symbol} is naive; the archive stores UTC only",
            )
        rows.append(
            {
                "instrument_id": bar.instrument_id,
                "venue": bar.venue,
                "venue_symbol": bar.venue_symbol,
                "interval": bar.interval,
                "open_time": bar.open_time.astimezone(UTC),
                "close_time": bar.close_time.astimezone(UTC) if bar.close_time else None,
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": _dec(bar.volume),
                "quote_volume": _dec(bar.quote_volume),
                "trades": bar.trades,
                "confirmed": bool(bar.confirmed),
                "source": bar.source,
                "ingested_at": ingested_at,
            },
        )
    return rows


def _tick_rows(ticks: Iterable[TickRecord], *, ingested_at: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tick in ticks:
        if tick.venue_timestamp is None or tick.venue_timestamp.tzinfo is None:
            # Names the field it actually checked. This message said `observed_at` while the check
            # read the venue's stamp, and a refusal that points at the wrong field sends whoever
            # reads it to fix a timestamp that was never the problem.
            raise ArchiveError(
                RejectReason.CONFIG_INVALID,
                f"tick venue_timestamp for {tick.venue_symbol} is missing or naive; "
                "the archive stores UTC only, and the venue's event time is the partition key",
            )
        rows.append(
            {
                "instrument_id": tick.instrument_id,
                "venue": tick.venue,
                "venue_symbol": tick.venue_symbol,
                # Our receipt time, and it may legitimately be absent: a tick parsed from bytes
                # on disk was never received. The column stays nullable rather than being filled
                # from the venue's stamp, because a copied value is the defect this batch removed.
                "observed_at": tick.observed_at.astimezone(UTC) if tick.observed_at else None,
                "venue_timestamp": tick.venue_timestamp.astimezone(UTC),
                "price": str(tick.price),
                "quantity": _dec(tick.quantity),
                "side": tick.side,
                "trade_id": tick.trade_id,
                "source": tick.source,
                "ingested_at": ingested_at,
            },
        )
    return rows


def _quote_rows(quotes: Iterable[QuoteRecord], *, ingested_at: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for quote in quotes:
        observed = quote.observed_at
        if observed is None or observed.tzinfo is None:
            raise ArchiveError(
                RejectReason.DATA_UNAVAILABLE,
                f"quote for {quote.venue_symbol} has no usable observation time; "
                f"refusing to archive an undatable row",
            )
        rows.append(
            {
                "instrument_id": quote.instrument_id,
                "venue": quote.venue,
                "venue_symbol": quote.venue_symbol,
                "observed_at": observed.astimezone(UTC),
                "venue_timestamp": quote.venue_timestamp.astimezone(UTC) if quote.venue_timestamp else None,
                "bid": _dec(quote.bid),
                "ask": _dec(quote.ask),
                "bid_size": _dec(quote.bid_size),
                "ask_size": _dec(quote.ask_size),
                "last": _dec(quote.last),
                "delayed": bool(quote.delayed),
                "source": quote.source,
                "ingested_at": ingested_at,
            },
        )
    return rows


@dataclass(slots=True)
class WriteResult:
    """Outcome of one write, including the path and whether anything was refused."""

    path: Path | None
    rows_written: int
    rows_refused: int
    reasons: dict[str, int] = field(default_factory=dict)
    bytes_written: int = 0
    wrote_at: datetime | None = None
    skipped_empty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path else None,
            "rows_written": self.rows_written,
            "rows_refused": self.rows_refused,
            "reasons": dict(self.reasons),
            "bytes_written": self.bytes_written,
            "wrote_at": iso_utc(self.wrote_at) if self.wrote_at else None,
            "skipped_empty": self.skipped_empty,
        }


class ParquetArchive:
    """Append-oriented Parquet writer with Hive-style partitioning.

    Each write produces one file under a partition directory. Files are never rewritten in
    place: rewriting history in a financial archive destroys the ability to prove what was
    known when. Compaction is an explicit, separately-audited operation.
    """

    def __init__(self, root: Path | str, *, now_fn: Any = None) -> None:
        self._root = Path(root)
        self._now_fn = now_fn or (lambda: datetime.now(tz=UTC))
        self._files_written = 0
        self._bytes_written = 0

    @property
    def root(self) -> Path:
        return self._root

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "root": str(self._root),
            "files_written": self._files_written,
            "bytes_written": self._bytes_written,
            "exists": self._root.exists(),
        }

    def partition_dir(self, dataset: str, venue: str, symbol: str, interval: str, when: datetime) -> Path:
        """Hive-style partition path. ``dataset`` is ``bars`` | ``ticks`` | ``quotes``."""
        utc = when.astimezone(UTC)
        safe_symbol = symbol.replace("/", "-").replace(":", "-").upper()
        return (
            self._root
            / f"dataset={dataset}"
            / f"venue={venue.upper()}"
            / f"symbol={safe_symbol}"
            / f"interval={interval}"
            / f"year={utc.year:04d}"
            / f"month={utc.month:02d}"
        )

    def write_bars(self, bars: Sequence[BarRecord], *, dataset: str = "bars") -> WriteResult:
        return self._write(bars, dataset=dataset, kind="bars")

    def write_ticks(self, ticks: Sequence[TickRecord], *, dataset: str = "ticks") -> WriteResult:
        return self._write(ticks, dataset=dataset, kind="ticks")

    def write_quotes(self, quotes: Sequence[QuoteRecord], *, dataset: str = "quotes") -> WriteResult:
        return self._write(quotes, dataset=dataset, kind="quotes")

    def _write(self, records: Sequence[Any], *, dataset: str, kind: str) -> WriteResult:
        if not records:
            return WriteResult(path=None, rows_written=0, rows_refused=0, skipped_empty=True)

        pa, pq = _require_pyarrow()
        ingested_at = self._now_fn().astimezone(UTC)

        # Partition by the record's own time, not by wall clock, so a historical backfill
        # lands in the partition it belongs to rather than in "today".
        groups: dict[Path, list[Any]] = {}
        for record in records:
            # Fail closed on an anonymous record. Partitioning is by venue and symbol, so a
            # record with either blank lands in a `venue=/symbol=` directory shared with every
            # other anonymous record: unfindable by any filter, and silently colliding across
            # instruments. Refusing the whole write is cheaper than an unattributable archive.
            if not record.venue or not record.venue_symbol:
                raise ArchiveError(
                    RejectReason.CONFIG_INVALID,
                    f"refusing to archive a {kind[:-1]} record with no venue or venue_symbol "
                    f"(venue={record.venue!r}, venue_symbol={record.venue_symbol!r}); "
                    "an anonymous record cannot be attributed to an instrument",
                    retryable=False,
                )
            when = self._time_of(record, kind)
            interval = getattr(record, "interval", "tick" if kind != "bars" else "raw")
            key = self.partition_dir(dataset, record.venue, record.venue_symbol, interval, when)
            groups.setdefault(key, []).append(record)

        total_written = 0
        total_bytes = 0
        last_path: Path | None = None
        for directory, group in groups.items():
            if kind == "bars":
                rows = _bar_rows(group, ingested_at=ingested_at)
                columns = BAR_COLUMNS
            elif kind == "ticks":
                rows = _tick_rows(group, ingested_at=ingested_at)
                columns = TICK_COLUMNS
            else:
                rows = _quote_rows(group, ingested_at=ingested_at)
                columns = QUOTE_COLUMNS
            schema = _build_schema(pa, columns)
            table = pa.Table.from_pylist(rows, schema=schema)
            directory.mkdir(parents=True, exist_ok=True)
            stamp = ingested_at.strftime("%Y%m%dT%H%M%SZ")
            path = directory / f"{dataset}-{stamp}-{len(rows):07d}.parquet"
            # A collision means two writes in the same second with the same row count.
            # Refusing to overwrite is the safe answer: overwriting would destroy data.
            if path.exists():
                suffix = 1
                while path.exists() and suffix < 1000:
                    path = directory / f"{dataset}-{stamp}-{len(rows):07d}-{suffix}.parquet"
                    suffix += 1
                if path.exists():
                    raise ArchiveError(
                        RejectReason.CONFIG_INVALID,
                        f"cannot allocate a unique archive filename under {directory}",
                    )
            pq.write_table(
                table,
                path,
                compression=COMPRESSION,
                compression_level=COMPRESSION_LEVEL,
                write_statistics=True,
                version="2.6",
            )
            written_bytes = path.stat().st_size
            total_written += len(rows)
            total_bytes += written_bytes
            last_path = path

        self._files_written += len(groups)
        self._bytes_written += total_bytes
        return WriteResult(
            path=last_path,
            rows_written=total_written,
            rows_refused=0,
            bytes_written=total_bytes,
            wrote_at=ingested_at,
        )

    @staticmethod
    def _time_of(record: Any, kind: str) -> datetime:
        """The record's **event** time — the partition key, so it is never our receipt time.

        Bars carry ``open_time``; ticks and quotes carry the venue's ``venue_timestamp``. Since
        F-14's fix ``observed_at`` is the instant this process received the response, which for a
        downloaded dump is one value shared by every row: partitioning on it would file a day of
        2020 trades under today's date and silently destroy the archive's time layout. A record
        with no event time is refused here, as it always was — the reason now names the field the
        archive actually needs.
        """
        if kind == "bars":
            raw_time: datetime | None = record.open_time
        else:
            raw_time = record.venue_timestamp
        when: datetime | None = raw_time
        if when is None:
            raise ArchiveError(
                RejectReason.DATA_UNAVAILABLE,
                f"{kind} record for {record.venue_symbol} has no venue event time "
                "(venue_timestamp); refusing to archive it, because a partition key invented from "
                "our receipt clock would file the row under the wrong date",
            )
        if when.tzinfo is None:
            raise ArchiveError(
                RejectReason.CONFIG_INVALID,
                f"{kind} record for {record.venue_symbol} has a naive timestamp",
            )
        return when.astimezone(UTC)

    # ------------------------------------------------------------------ reads

    def read_bars(
        self,
        *,
        venue: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        confirmed_only: bool = True,
        limit: int | None = None,
    ) -> list[BarRecord]:
        """Read bars back through DuckDB. Decimal columns are rehydrated exactly."""
        duckdb = _require_duckdb()
        glob = str(self._root / "dataset=bars" / "**" / "*.parquet")
        clauses: list[str] = []
        params: list[Any] = []
        if venue is not None:
            clauses.append("venue = ?")
            params.append(venue.upper())
        if symbol is not None:
            clauses.append("venue_symbol = ?")
            params.append(symbol.upper())
        if interval is not None:
            clauses.append("interval = ?")
            params.append(interval)
        if start is not None:
            clauses.append("open_time >= ?")
            params.append(start.astimezone(UTC))
        if end is not None:
            clauses.append("open_time < ?")
            params.append(end.astimezone(UTC))
        if confirmed_only:
            clauses.append("confirmed = TRUE")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
        # Every caller-supplied *value* is bound as a `?` parameter below. The only
        # interpolated text is the archive root path, which comes from configuration at
        # construction time — and is still rejected here if it contains a quote, so a
        # misconfigured path cannot become an injection vector.
        if "'" in glob:
            raise ArchiveError(
                RejectReason.CONFIG_INVALID,
                "archive root path must not contain a quote character",
            )
        query = (
            "SELECT instrument_id, venue, venue_symbol, interval, open_time, close_time, "  # noqa: S608
            "open, high, low, close, volume, quote_volume, trades, confirmed, source "
            f"FROM read_parquet('{glob}', hive_partitioning=false, union_by_name=true)"
            f"{where} ORDER BY open_time{limit_sql}"
        )
        try:
            rows = duckdb.sql(query, params=params).fetchall()
        except duckdb.Error as exc:  # noqa: PERF203 - single call site, not a loop
            message = str(exc)
            if "No files found" in message or "does not exist" in message:
                return []
            raise ArchiveError(
                RejectReason.DATA_UNAVAILABLE, f"archive read failed: {message[:300]}"
            ) from exc

        out: list[BarRecord] = []
        for row in rows:
            out.append(
                BarRecord(
                    instrument_id=str(row[0] or ""),
                    venue=str(row[1] or ""),
                    venue_symbol=str(row[2] or ""),
                    interval=str(row[3] or ""),
                    open_time=_as_utc(row[4]),
                    close_time=_as_utc(row[5]) if row[5] is not None else None,
                    open=Decimal(str(row[6])),
                    high=Decimal(str(row[7])),
                    low=Decimal(str(row[8])),
                    close=Decimal(str(row[9])),
                    volume=Decimal(str(row[10])) if row[10] is not None else None,
                    quote_volume=Decimal(str(row[11])) if row[11] is not None else None,
                    trades=int(row[12]) if row[12] is not None else None,
                    confirmed=bool(row[13]),
                    source=str(row[14] or "ARCHIVE"),
                ),
            )
        return out

    def count_files(self) -> int:
        if not self._root.exists():
            return 0
        return sum(1 for _ in self._root.rglob("*.parquet"))

    def total_bytes(self) -> int:
        if not self._root.exists():
            return 0
        return sum(p.stat().st_size for p in self._root.rglob("*.parquet"))

    def manifest(self) -> dict[str, Any]:
        """What the archive actually holds — the honest answer to 'do we have this data?'."""
        partitions: dict[str, dict[str, Any]] = {}
        if self._root.exists():
            for path in sorted(self._root.rglob("*.parquet")):
                relative = path.relative_to(self._root)
                parts = {seg.split("=", 1)[0]: seg.split("=", 1)[1] for seg in relative.parts if "=" in seg}
                key = "/".join(f"{k}={v}" for k, v in sorted(parts.items()))
                entry = partitions.setdefault(key, {"files": 0, "bytes": 0})
                entry["files"] += 1
                entry["bytes"] += path.stat().st_size
        return {
            "format_version": FORMAT_VERSION,
            "compression": COMPRESSION,
            "root": str(self._root),
            "files": self.count_files(),
            "bytes": self.total_bytes(),
            "partitions": partitions,
        }

    def write_manifest(self) -> Path:
        """Persist the manifest next to the data so coverage survives a restart."""
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / "manifest.json"
        path.write_text(json.dumps(self.manifest(), indent=2, sort_keys=True), encoding="utf-8")
        return path


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    raise ArchiveError(RejectReason.CONFIG_INVALID, f"archive timestamp is not a datetime: {value!r}")


__all__ = [
    "BAR_COLUMNS",
    "TYPE_BOOL",
    "TYPE_INT64",
    "TYPE_STRING",
    "TYPE_TIMESTAMP_UTC_MS",
    "COMPRESSION",
    "COMPRESSION_LEVEL",
    "FORMAT_VERSION",
    "QUOTE_COLUMNS",
    "TICK_COLUMNS",
    "ArchiveError",
    "ArchiveUnavailable",
    "ParquetArchive",
    "WriteResult",
]
