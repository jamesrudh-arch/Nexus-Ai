"""PostgreSQL driver adapter: one store implementation, two databases (F-31).

Why an adapter and not a second store
-------------------------------------
``store/operational.py`` is 1,373 lines carrying 37 protocol methods and 219 ``?`` placeholders.
A parallel ``PostgresOperationalStore`` written by hand would duplicate all of it, and the two
would drift — which is not a hypothetical: ``tests/test_schema_fidelity.py`` exists, at 856 lines,
precisely because the SQLite schema and ``migrations/*.sql`` drifted in both directions until
Stage 8.2 made the divergence fail a test. Duplicating the *store* would create a second, larger
surface with the same failure mode and no equivalent police.

So the seam is the driver, not the store. Everything above ``self._conn`` is unchanged: the same
SQL text, the same 37 methods, the same ``dict(row)`` deserialisers. This module makes a psycopg
connection answer to the ``sqlite3.Connection`` shape the store already uses.

What that requires, each item measured against a real PostgreSQL 16.2 rather than assumed
----------------------------------------------------------------------------------------
* **Placeholders.** SQLite binds ``?``; psycopg binds ``%s``. Rewritten by a tokenizer that skips
  string literals, quoted identifiers and ``--`` comments, so a ``?`` inside a literal is left
  alone. No statement in the store path contains a bare ``%``, so pyformat needs no escaping.
* **Upserts.** SQLite's ``INSERT OR REPLACE`` / ``INSERT OR IGNORE`` do not exist in PostgreSQL;
  ``ON CONFLICT`` appears nowhere in ``src/``. All 15 writer statements share one grammar —
  ``INSERT OR <kind> INTO <table> (<cols>) VALUES (<placeholders>)`` with a column count equal to
  the placeholder count in every case — so the translation is mechanical. Anything that mentions
  ``INSERT OR`` and does not match that grammar raises rather than being passed through, because a
  silently mistranslated upsert writes to the wrong rows.
* **Conflict targets.** ``INSERT OR REPLACE`` fires on *any* unique violation; ``ON CONFLICT DO
  UPDATE`` requires a named target. Resolved from the live catalog: the primary key when its
  columns are all in the insert list, otherwise the single unique constraint that is. Ambiguity
  raises. ``venue_instrument_mapping`` is the case that needs the fallback — its upsert omits
  ``mapping_id``, a ``GENERATED ALWAYS AS IDENTITY`` column, so the target is
  ``UNIQUE (instrument_id, venue, venue_symbol)``.
* **Types.** The mirror declares richer types than SQLite stores, and ``TYPE_TRANSLATIONS`` in the
  fidelity suite sanctions each one. But it maps *types*, never *values*, and the store's
  deserialisers expect SQLite's shapes: ``dict(row)["payload"]`` must be canonical JSON **text**,
  not a dict, because ``loads_json`` parses a string. So values are normalised in both directions
  against ``store/serialise.py``'s writers (``_text``, ``_num``, ``_json_list``) and
  ``core.ids.iso_utc``.
* **PRAGMA.** Only three execute in this path — ``journal_mode=WAL``, ``synchronous=FULL``,
  ``busy_timeout=5000``. The other 18 textual hits in ``src/`` are prose. PostgreSQL's WAL is
  always on and its locking does not need a busy timeout, so those two are no-ops; ``synchronous``
  maps to ``synchronous_commit``, the one setting that answers the same question.

Known divergence, recorded not hidden
-------------------------------------
A ``NUMERIC(p, s)`` column does not return the string that was written to it: PostgreSQL pads to
the declared scale, so ``'0.50'`` reads back ``Decimal('0.50000')``. ``NUMERIC(6, 5)`` also refuses
any magnitude at or above 10, which SQLite's TEXT column accepts. L-4 requires Decimals to travel
as their exact string form, and payloads are digest-referenced from the audit chain, so this is a
real gap in "promotion is a copy, not a rewrite". :func:`numeric_to_text` narrows it to the
shortest exact form, which round-trips every value that does not carry deliberate trailing zeros;
``tests/test_postgres_store.py`` pins both the cases that survive and the case that does not, so
the gap cannot widen unnoticed.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from nexus.core.ids import iso_utc
from nexus.store.serialise import dumps_canonical

try:  # the driver is an optional extra, so its absence must not break an import of this module
    import psycopg as _psycopg
    from psycopg.errors import Error as _DriverFault

    PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover - the default install has no Postgres driver
    _psycopg = None  # type: ignore[assignment]
    PSYCOPG_AVAILABLE = False

    class _DriverFault(Exception):  # type: ignore[no-redef]
        """Stand-in so the ``except`` clauses below stay valid without the driver installed."""


__all__ = [
    "PSYCOPG_AVAILABLE",
    "PostgresConnection",
    "PostgresCursor",
    "Row",
    "StoreDriverError",
    "numeric_to_text",
    "to_pyformat",
]


class StoreDriverError(Exception):
    """A database fault from a non-SQLite driver.

    ``store/operational.py`` catches ``sqlite3.Error`` around every read and write. Catching this
    alongside it keeps one error path for both drivers, so a Postgres fault is reported as the same
    ``PersistenceError`` with the same redaction as a SQLite one instead of escaping raw.
    """


class PostgresError(StoreDriverError):
    """A fault raised by PostgreSQL, or by this adapter refusing to guess."""


#: Statements the store issues as SQLite PRAGMAs, and what PostgreSQL does about each. A PRAGMA not
#: listed is refused rather than dropped, so a new one cannot be silently ignored.
_PRAGMA_MAP: dict[str, str | None] = {
    # PostgreSQL's write-ahead log is not a mode you select; it is how the server works.
    "journal_mode=wal": None,
    # The one PRAGMA with a genuine counterpart: full durability on commit.
    "synchronous=full": "SET synchronous_commit = on",
    # SQLite needs this because a single-file database serialises writers itself. PostgreSQL has
    # real row-level locking and blocks instead of returning SQLITE_BUSY.
    "busy_timeout=5000": None,
}

#: Columns the portable target declares for the driver's own use and that must never reach a caller.
#:
#: ``store/operational.py`` reads with ``SELECT *`` and deserialises with ``dict(row)``, so a column
#: added only to give PostgreSQL an insertion order would appear in every entity dict and from there
#: in every HTTP response — on PostgreSQL and not on SQLite. That is a difference in the API caused by
#: a difference in the driver, which is the one thing "nothing above the seam changes" forbids, so the
#: adapter projects it away on the way out. It is declared last in every table that has it, but the
#: projection is by name rather than by position so that cannot come to matter.
_DRIVER_INTERNAL_COLUMNS = frozenset({"row_order"})

_OR_INSERT = re.compile(
    r"INSERT\s+OR\s+(REPLACE|IGNORE)\s+INTO\s+(?P<table>\w+)\s*"
    r"\((?P<cols>[^)]*)\)\s*VALUES\s*\((?P<vals>[^)]*)\)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_MENTIONS_OR_INSERT = re.compile(r"INSERT\s+OR\s+", re.IGNORECASE)
_FROM_TABLE = re.compile(r"\bFROM\s+(?P<table>\w+)", re.IGNORECASE)
_INSERT_INTO = re.compile(r"\bINSERT\s+INTO\s+(?P<table>\w+)", re.IGNORECASE)
_INSERT_COLUMNS = re.compile(r"\(([^)]*)\)\s*VALUES", re.IGNORECASE | re.DOTALL)
_PRAGMA = re.compile(r"^\s*PRAGMA\s+(?P<body>[^;]*?)\s*;?\s*$", re.IGNORECASE)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _checked(identifiers: Sequence[str], what: str) -> list[str]:
    """Reject any identifier that is not a bare SQL name before it is interpolated into a statement.

    The table and column names a translation builds come out of the store's own SQL text, not out of
    a request, but "it came from our own code" is exactly the assumption that should not be trusted
    in a string that becomes SQL. Anything else raises here.
    """
    for name in identifiers:
        if not _IDENTIFIER.match(name):
            raise PostgresError(f"refusing to interpolate {what} {name!r} into a statement")
    return list(identifiers)


#: SQLite's ``:name`` parameter. ``::`` is consumed by the scanner first, as a cast.
_NAMED_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def to_pyformat(sql: str) -> str:
    """Rewrite SQLite's placeholders as psycopg's, leaving literals and casts alone.

    SQLite accepts two placeholder spellings and this repository uses both: ``?`` in the 219
    statements of ``store/operational.py``, and ``:name`` in ``audit/log.py``'s append, which binds a
    dict. psycopg wants ``%s`` for the first and ``%(name)s`` for the second, so a statement written
    for SQLite reaches the server with no placeholder at all unless both are translated — which is how
    a first cut failed boot recovery with "the query has 0 placeholders but 8 parameters were passed".

    A character scanner rather than a regex, because ``?`` and ``:`` are both legal inside a string
    literal and a regex that does not know about quotes would rewrite one. Single quotes are handled
    with SQLite's doubled-quote escape, ``"`` starts a quoted identifier, and ``--`` starts a comment
    that runs to the end of the line. ``::`` is a PostgreSQL cast and must survive: it begins with the
    same character as a named parameter.

    SQLite's other two spellings, ``@name`` and ``$name``, are deliberately not translated. Neither
    appears in this repository, and both collide with PostgreSQL syntax — ``$1`` is a server-side
    placeholder and ``$.field`` is a JSON path — so guessing would rewrite statements that were
    already correct.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        char = sql[i]
        if char == "'":
            out.append("'")
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(sql[i])
                i += 1
            continue
        if char == '"':
            close = sql.find('"', i + 1)
            stop = n if close < 0 else close + 1
            out.append(sql[i:stop])
            i = stop
            continue
        if char == "-" and sql.startswith("--", i):
            newline = sql.find("\n", i)
            stop = n if newline < 0 else newline
            out.append(sql[i:stop])
            i = stop
            continue
        if char == ":":
            if sql.startswith("::", i):  # a PostgreSQL cast, not a parameter
                out.append("::")
                i += 2
                continue
            named = _NAMED_PARAM.match(sql, i)
            if named:
                out.append(f"%({named.group(1)})s")
                i = named.end()
                continue
        if char == "?":
            out.append("%s")
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


#: Keys of psycopg's keyword connection form that carry a secret.
_CREDENTIAL_KEYS = frozenset({"password", "pwd", "passfile"})


def public_dsn(url: str) -> str:
    """A connection target with its credentials removed, safe to publish.

    ``/v1/status`` reports where the system of record lives, and that endpoint is unauthenticated
    (D-026), so the string it carries must never be able to hold a secret. A SQLite path cannot. A
    PostgreSQL URL can — ``postgresql://nexus:hunter2@db.internal:5432/nexus`` is the shape every
    managed platform hands out, and publishing it would put a live credential on an open endpoint.

    Scheme, host, port and database are kept, because an operator reading the status needs to know
    which server the system is talking to; only the userinfo goes. The keyword form psycopg also
    accepts is filtered key by key for the same reason.
    """
    if "://" in url:
        parts = urlsplit(url)
        # Everything after the last "@" in the authority. ``rpartition`` rather than ``hostname`` and
        # ``port``, which would lower-case the host, reject a malformed port, and — through
        # ``urlunsplit`` — drop the ``//`` from an empty authority, turning ``sqlite:///./data/x.db``
        # into ``sqlite:/./data/x.db``: a different URL that opens nothing. This way the result is the
        # input verbatim minus the userinfo, so scrubbing a clean URL is a no-op.
        authority = parts.netloc.rpartition("@")[2]
        tail = f"?{parts.query}" if parts.query else ""
        tail += f"#{parts.fragment}" if parts.fragment else ""
        return f"{parts.scheme}://{authority}{parts.path}{tail}"
    kept = [kv for kv in url.split() if kv.split("=", 1)[0].lower() not in _CREDENTIAL_KEYS]
    return " ".join(kept) or url


#: Statements that only read, so the transaction they open can be ended immediately.
_READ_ONLY_HEADS = frozenset({"SELECT", "SHOW", "EXPLAIN", "WITH", "VALUES"})

#: Anything that could change the database or the session. A match anywhere in the statement makes it
#: a write, which is the safe direction to be wrong in: calling a write a read would end a transaction
#: that a later statement in the same unit of work still needs, while calling a read a write only
#: leaves the transaction open the way it is today.
_WRITE_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|SET|CALL|COPY|VACUUM|ANALYZE)\b",
    re.IGNORECASE,
)


def reads_only(sql: str) -> bool:
    """Whether a statement only reads, decided on its first word and then on its whole text.

    The first word alone is not enough: ``WITH x AS (DELETE FROM t RETURNING *)`` starts with a read
    keyword and writes, so the body is scanned too. ``SET`` counts as a write deliberately — it is what
    the ``PRAGMA synchronous=FULL`` mapping produces, and rolling a ``SET`` back undoes it.
    """
    stripped = sql.lstrip()
    if not stripped:
        return False
    head = stripped.split(None, 1)[0].upper().rstrip(";(")
    return head in _READ_ONLY_HEADS and not _WRITE_WORDS.search(sql)


def numeric_to_text(value: Decimal) -> str:
    """The shortest exact decimal string, which is what SQLite's TEXT column would have held.

    PostgreSQL returns ``NUMERIC`` padded to the column's declared scale, so ``Decimal('0.50000')``
    comes back for a written ``'0.5'``. Stripping the padding recovers the original for every value
    that did not carry trailing zeros of its own. ``Decimal.normalize`` alone is not enough: it
    renders ``100`` as ``1E+2``, so the result is formatted as a fixed-point string.
    """
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


class Row:
    """A result row that behaves like ``sqlite3.Row``.

    ``dict(row)`` is how ``operational.py`` deserialises every entity — ``_decision_dict`` and five
    other call sites — and index access is used at twelve more. ``dict()`` needs ``keys()`` plus a
    ``__getitem__`` that answers to a name, so the row carries both.
    """

    __slots__ = ("_lookup", "_names", "_values")

    def __init__(self, values: Sequence[Any], names: Sequence[str]) -> None:
        self._values = tuple(values)
        self._names = tuple(names)
        self._lookup = {name: position for position, name in enumerate(self._names)}

    def keys(self) -> tuple[str, ...]:
        return self._names

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._values[key]
        try:
            return self._values[self._lookup[key]]
        except KeyError:
            raise IndexError(key) from None

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __contains__(self, key: object) -> bool:
        return key in self._lookup

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Row):
            return self._names == other._names and self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"<Row {dict(zip(self._names, self._values, strict=False))!r}>"


class PostgresCursor:
    """The ``sqlite3.Cursor`` surface the store and the migration runner actually use."""

    __slots__ = ("_adapter", "_cursor", "_keep", "_names", "_types")

    def __init__(
        self,
        adapter: PostgresConnection,
        cursor: Any,
        names: Sequence[str],
        types: Sequence[str | None],
        keep: Sequence[int] | None = None,
    ) -> None:
        self._adapter = adapter
        self._cursor = cursor
        self._names = tuple(names)
        self._types = tuple(types)
        self._keep = tuple(keep) if keep is not None else None

    @property
    def description(self) -> tuple[tuple[Any, None, None, None, None, None, None], ...] | None:
        """sqlite3-shaped description: seven slots per column, only the name carries anything."""
        if not self._names:
            return None
        return tuple((name, None, None, None, None, None, None) for name in self._names)

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def _adapt(self, raw: Sequence[Any]) -> Row:
        values = raw if self._keep is None else [raw[i] for i in self._keep]
        adapted = [
            self._adapter.value_from_postgres(value, kind)
            for value, kind in zip(values, self._types, strict=True)
        ]
        return Row(adapted, self._names)

    def fetchone(self) -> Row | None:
        raw = self._cursor.fetchone()
        return None if raw is None else self._adapt(raw)

    def fetchall(self) -> list[Row]:
        return [self._adapt(raw) for raw in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[Row]:
        for raw in self._cursor:
            yield self._adapt(raw)


class PostgresConnection:
    """A ``sqlite3.Connection``-shaped façade over one psycopg connection.

    Not a general-purpose DBAPI shim. It implements exactly the surface ``store/operational.py``,
    ``audit/log.py`` and ``store/migrations.py`` use — ``execute``, ``executescript``, ``commit``,
    ``rollback``, ``close`` — and refuses anything else, so a new SQLite-ism in the store fails here
    loudly instead of being quietly passed to a server that cannot parse it.
    """

    def __init__(self, dsn: str, *, autocommit: bool = False) -> None:
        if _psycopg is None:
            raise PostgresError(
                "the postgresql scheme needs the 'postgres' extra: pip install 'nexus-core[postgres]'. "
                "Refusing to start rather than falling back to SQLite, which would be a different "
                "system of record than the one the configuration named."
            )
        self._dsn = dsn
        try:
            self._conn = _psycopg.connect(dsn, autocommit=autocommit)
        except _DriverFault as exc:
            # An unreachable server is the one place a DSN is most likely to be echoed back, and
            # this message can reach a log line, an audit row and an HTTP response. test_api.py pins
            # that a refused URL leaks neither its password nor its hostname, and a Postgres
            # connection fault has to earn the same treatment rather than escaping raw.
            raise PostgresError(f"could not open the PostgreSQL connection: {_redact(str(exc))}") from exc
        self._types: dict[str, dict[str, str]] = {}
        self._primary: dict[str, list[str]] = {}
        self._unique: dict[str, list[list[str]]] = {}
        self._lock = threading.RLock()
        # Statements executed since the last commit or rollback that could have written. Zero means
        # the open transaction is read-only, and so means it can be ended without losing anything.
        self._writes = 0

    @property
    def dsn(self) -> str:
        """The connection string, as supplied. Never logged: it can carry a password."""
        return self._dsn

    # -- introspection ---------------------------------------------------

    def _load_catalog(self, *, force: bool = False) -> None:
        """Column types and unique constraints, read from the live catalog.

        Derived from the database rather than written down here, so the adapter cannot disagree with
        the schema the way ``migrations/*.sql`` disagreed with ``store/schema.py`` before Stage 8.2.

        Reloaded when a table is asked for that the cache does not hold. Caching once was wrong and
        the parity suite caught it: ``bootstrap_schema`` applies ``0001_core.sql`` and then records a
        bookkeeping row, and recording it reads the catalog — so a load-once cache froze the schema
        at "everything except the tables ``0002_memory.sql`` goes on to create", and ``memory_item``
        resolved to no columns at all.
        """
        if self._types and not force:
            return
        with self._lock:
            if self._types and not force:
                return
            columns: dict[str, dict[str, str]] = {}
            for table, column, udt in self._conn.execute(
                "SELECT table_name, column_name, udt_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            ).fetchall():
                columns.setdefault(table, {})[column] = udt

            attribute_names: dict[tuple[str, int], str] = {}
            for table, number, name in self._conn.execute(
                "SELECT attrelid::regclass::text, attnum, attname FROM pg_attribute "
                "WHERE attrelid::regclass::text IN "
                "(SELECT table_name FROM information_schema.tables WHERE table_schema = 'public')"
            ).fetchall():
                attribute_names[(table, number)] = name

            primary: dict[str, list[str]] = {}
            unique: dict[str, list[list[str]]] = {}
            for table, kind, keys in self._conn.execute(
                "SELECT conrelid::regclass::text, contype, conkey FROM pg_constraint "
                "WHERE contype IN ('p', 'u') AND connamespace = 'public'::regnamespace"
            ).fetchall():
                names = [attribute_names[(table, int(key))] for key in keys]
                if kind == "p":
                    primary[table] = names
                else:
                    unique.setdefault(table, []).append(names)

            self._primary, self._unique, self._types = primary, unique, columns

    def column_types(self, table: str) -> Mapping[str, str]:
        """The PostgreSQL type of every column in ``table``, as the catalog reports it."""
        self._load_catalog()
        if table not in self._types:
            # Either the cache predates the table's DDL or the table genuinely does not exist. Reload
            # once and let the caller see the truth either way.
            self._load_catalog(force=True)
        return self._types.get(table, {})

    def _conflict_target(self, table: str, columns: Sequence[str]) -> list[str]:
        """Which constraint ``ON CONFLICT`` should name, derived from the catalog.

        ``INSERT OR REPLACE`` replaces on any unique violation. ``ON CONFLICT DO UPDATE`` cannot: it
        needs one target. The primary key wins when the statement supplies it, because every upsert
        in the store is keyed by identity; otherwise the one unique constraint the statement fully
        supplies is used. Two candidates or none is a refusal, not a coin toss.
        """
        self._load_catalog()
        supplied = set(columns)
        primary = self._primary.get(table)
        if primary is not None and set(primary) <= supplied:
            return primary
        fitting = [c for c in self._unique.get(table, []) if set(c) <= supplied]
        if len(fitting) != 1:
            raise PostgresError(
                f"cannot choose an ON CONFLICT target for {table} from {sorted(supplied)}: "
                f"{len(fitting)} constraints fit ({fitting}). Refusing rather than guessing, because "
                "the wrong target upserts the wrong row."
            )
        return fitting[0]

    # -- value translation ------------------------------------------------

    def value_to_postgres(self, value: Any, udt: str | None) -> Any:
        """Adapt one bound parameter from the store's SQLite shape to PostgreSQL's.

        Only arrays need work on the way in. ``_json_list`` writes canonical JSON text, and
        PostgreSQL rejects ``'[]'`` as a malformed array literal — its own literal syntax is
        ``{}``. Everything else the store binds (strings for numerics, timestamps, canonical JSON)
        is accepted as-is, each case measured rather than assumed.
        """
        if udt is None or value is None:
            return value
        if udt == "bool":
            # _int_bool binds 1/0 for SQLite's INTEGER affinity, and PostgreSQL refuses an integer
            # for a boolean column ("expression is of type smallint"). This is the write-side half of
            # the bool handling in value_from_postgres; only the read half existed at first, and the
            # parity suite found the missing one by failing on halt_event.
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "t", "yes", "y", "on")
            return bool(value)
        if udt.startswith("_"):
            if isinstance(value, str):
                loaded = json.loads(value) if value else []
                if not isinstance(loaded, list):
                    raise PostgresError(f"a {udt[1:]}[] column was handed JSON that is not a list: {value!r}")
                return [str(item) for item in loaded]
            return [str(item) for item in value]
        return value

    def value_from_postgres(self, value: Any, udt: str | None) -> Any:
        """Adapt one result value back to exactly what the SQLite store would have returned.

        This is the half that keeps 1,373 lines of deserialisers working unchanged: they call
        ``loads_json`` on a string, build a ``Decimal`` from a string, and compare timestamps to the
        output of ``iso_utc``. Returning PostgreSQL's native types instead would not merely differ,
        it would raise ``TypeError`` deep inside a projection.
        """
        if value is None or udt is None:
            return value
        if udt == "jsonb":
            return dumps_canonical(value)
        if udt.startswith("_"):
            return dumps_canonical([str(item) for item in value])
        if udt == "numeric":
            return numeric_to_text(value) if isinstance(value, Decimal) else str(value)
        if udt in ("timestamptz", "timestamp"):
            if isinstance(value, datetime):
                moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
                return iso_utc(moment)
            return str(value)
        if udt == "date":
            return value.isoformat() if isinstance(value, date) else str(value)
        if udt == "bool":
            # SQLite's INTEGER affinity turns the "1"/"0" that _text writes into an int, and the
            # deserialisers compare against ints.
            return 1 if value else 0
        if udt in ("int8", "int4", "int2"):
            return int(value)
        return value if isinstance(value, str) else str(value)

    # -- statement rewriting ---------------------------------------------

    def _rewrite(self, sql: str) -> tuple[str, str | None, list[str]]:
        """Translate one statement, returning the SQL, its target table, and its column list.

        Refuses rather than approximates: a statement that mentions ``INSERT OR`` without matching
        the one grammar all fifteen writer statements share is an error here, not a best effort.
        """
        pragma = _PRAGMA.match(sql)
        if pragma:
            body = re.sub(r"\s+", "", pragma.group("body").lower())
            if body not in _PRAGMA_MAP:
                raise PostgresError(
                    f"PRAGMA {pragma.group('body')} has no PostgreSQL counterpart and this adapter "
                    "will not silently drop one it has never seen."
                )
            return _PRAGMA_MAP[body] or "", None, []

        if _MENTIONS_OR_INSERT.search(sql) and not _OR_INSERT.search(sql):
            raise PostgresError(
                f"an INSERT OR ... statement this adapter cannot translate: {' '.join(sql.split())[:120]}"
            )
        match = _OR_INSERT.search(sql)
        if match:
            kind = match.group(1).upper()
            table = match.group("table")
            columns = _checked(
                [c.strip().strip('"') for c in match.group("cols").split(",") if c.strip()], "column"
            )
            _checked([table], "table")
            values = [v.strip() for v in match.group("vals").split(",") if v.strip()]
            if len(columns) != len(values):
                raise PostgresError(
                    f"INSERT OR {kind} INTO {table} lists {len(columns)} columns and {len(values)} "
                    "placeholders; the translation depends on them matching."
                )
            placeholders = ", ".join(["%s"] * len(columns))
            quoted = ", ".join(columns)
            if kind == "IGNORE":
                # No target: PostgreSQL then ignores a violation of *any* constraint, which is
                # exactly what INSERT OR IGNORE does.
                return (
                    f"INSERT INTO {table} ({quoted}) VALUES ({placeholders}) "  # noqa: S608
                    f"ON CONFLICT DO NOTHING",
                    table,
                    columns,
                )
            target = self._conflict_target(table, columns)
            conflict = ", ".join(target)
            # The target columns are excluded from the SET list: PostgreSQL refuses to update a
            # column that is the conflict target, and re-setting it to the same value is noise.
            assignments = [c for c in columns if c not in target]
            if not assignments:
                return (
                    f"INSERT INTO {table} ({quoted}) VALUES ({placeholders}) "  # noqa: S608
                    f"ON CONFLICT ({conflict}) DO NOTHING",
                    table,
                    columns,
                )
            update = ", ".join(f"{c} = EXCLUDED.{c}" for c in assignments)
            return (
                f"INSERT INTO {table} ({quoted}) VALUES ({placeholders}) "  # noqa: S608
                f"ON CONFLICT ({conflict}) DO UPDATE SET {update}",
                table,
                columns,
            )

        text = to_pyformat(sql)
        insert = _INSERT_INTO.search(text)
        if insert:
            table = insert.group("table")
            paren = _INSERT_COLUMNS.search(text)
            columns = [c.strip().strip('"') for c in paren.group(1).split(",") if c.strip()] if paren else []
            return text, table, columns
        found = _FROM_TABLE.search(text)
        table = found.group("table") if found else None
        return self._order_surrogate(text, table), table, []

    def _order_surrogate(self, sql: str, table: str | None) -> str:
        """Rewrite SQLite's ``rowid`` to the surrogate column the portable target declares.

        Five queries in ``store/operational.py`` order by ``rowid``, and PostgreSQL has no such
        column: ``ctid`` is a physical address that moves under ``VACUUM``, and the primary keys
        here embed a random uuid4 (``core.ids.new_id``) so they are not monotonic and cannot stand
        in for insertion order. One of the five orders halt history, which boot recovery derives
        state from, so ``migrations/0001_core.sql`` gives those four tables a
        ``row_order BIGINT GENERATED ALWAYS AS IDENTITY`` and the rewrite is driven by the catalog
        rather than by a list kept here. A ``rowid`` the catalog cannot answer for is a refusal.
        """
        if not re.search(r"\browid\b", sql, re.IGNORECASE):
            return sql
        if table is None or "row_order" not in self.column_types(table):
            raise PostgresError(
                f"a query orders by SQLite's rowid but {table or 'its table'} declares no row_order "
                "surrogate. Refusing rather than dropping the ordering, because the five queries "
                "that use it include halt history."
            )
        return re.sub(r"\browid\b", "row_order", sql, flags=re.IGNORECASE)

    # -- the sqlite3 surface ------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> PostgresCursor:
        text, table, columns = self._rewrite(sql)
        if not text:
            return PostgresCursor(self, self._conn.cursor(), [], [])
        by_name = dict(self.column_types(table)) if table else {}
        bound: Sequence[Any] | Mapping[str, Any]
        if isinstance(params, Mapping):
            # A named parameter resolves its column type by its own name, which is the column name in
            # every statement in this repository that binds a dict. A positional parameter cannot do
            # that; it is matched to the INSERT's column list by index instead.
            bound = {key: self.value_to_postgres(value, by_name.get(key)) for key, value in params.items()}
        else:
            bound = [
                self.value_to_postgres(value, by_name.get(columns[i]) if i < len(columns) else None)
                for i, value in enumerate(params)
            ]
        try:
            # `None` rather than an empty sequence: psycopg only interprets `%` when parameters are
            # passed, so a statement with none is sent exactly as written.
            cursor = self._conn.execute(text, bound if bound else None)
        except _DriverFault as exc:
            raise PostgresError(_redact(str(exc))) from exc
        if reads_only(text):
            if self._writes == 0:
                # sqlite3 defers BEGIN until a write, so the store it was written against has never
                # had to end a read transaction: `in_transaction` is False after any number of
                # SELECTs. PostgreSQL opens one on the first statement and keeps it open until
                # commit, so without this an API process that has served one read and then gone quiet
                # sits `idle in transaction` indefinitely — holding a snapshot that stops dead tuples
                # being vacuumed, and waiting for the provider's idle_in_transaction_session_timeout
                # to terminate a connection this store never re-opens. The rows are already
                # client-side (libpq transfers the whole result on execute), so ending the transaction
                # here cannot lose any of them; measured element-for-element identical to the same
                # query left inside its transaction.
                self._conn.rollback()
        else:
            self._writes += 1
        described = [d.name for d in cursor.description] if cursor.description else []
        keep = [i for i, name in enumerate(described) if name not in _DRIVER_INTERNAL_COLUMNS]
        names = [described[i] for i in keep]
        # A result column is adapted only when this statement's table declares it; aggregates such
        # as count(*) have no entry and pass through untouched.
        kinds: list[str | None] = [by_name.get(name) for name in names]
        return PostgresCursor(self, cursor, names, kinds, keep if len(keep) != len(described) else None)

    def executescript(self, script: str) -> None:
        """Run a multi-statement DDL script, as ``sqlite3.Connection.executescript`` does.

        Dollar-quoted bodies (``$$ ... $$``) are why this cannot reuse :meth:`_rewrite`: a naive
        ``;`` split — which a first attempt used — cuts the append-only trigger function in half and
        reports two syntax errors that are artifacts of the splitter rather than of the SQL.
        """
        try:
            self._conn.execute(script)
            self._conn.commit()
            # DDL changes the catalog, so anything cached before it is now a statement about a schema
            # that no longer exists.
            self._types, self._primary, self._unique = {}, {}, {}
        except _DriverFault as exc:
            self._conn.rollback()
            raise PostgresError(_redact(str(exc))) from exc

    def commit(self) -> None:
        self._conn.commit()
        self._writes = 0

    def rollback(self) -> None:
        self._conn.rollback()
        self._writes = 0

    def close(self) -> None:
        self._conn.close()

    def cursor(self) -> Any:
        return self._conn.cursor()

    @property
    def row_factory(self) -> type[Row]:
        return Row

    @row_factory.setter
    def row_factory(self, value: Any) -> None:  # noqa: ARG002 - accepted for sqlite3 compatibility
        """Accept and ignore ``row_factory = sqlite3.Row``.

        The store sets that on every connection it opens. Rows here are always :class:`Row`, so the
        assignment is honoured in effect and discarded in fact, rather than raising on a line of
        code that is doing the right thing for the other driver.
        """

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


#: The shapes a PostgreSQL connection fault actually arrives in, each one observed against a real
#: server rather than guessed: ``failed to resolve host 'db-host'``, ``connection to server at
#: "127.0.0.1", port 5999 failed``, and the keyword form ``host=db-host password=...``. psycopg does
#: not echo a password in any of them, but it does name the host, and ``test_api.py`` has pinned
#: since before F-31 that a refused URL leaks neither.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(password|pwd)\s*=\s*[^\s&]+"), r"\1=<redacted>"),
    (re.compile(r"//[^\s/@]+@"), "//<redacted>@"),
    (re.compile(r"(?i)\bhost\s+'[^']*'"), "host '<redacted>'"),
    (re.compile(r"(?i)\bhost\s*=\s*\S+"), "host=<redacted>"),
    (re.compile(r'(?i)\bserver at "[^"]*"'), 'server at "<redacted>"'),
    (re.compile(r"(?i)\bserver\s+(?:at|on)\s+\S+"), "server at <redacted>"),
)


def _redact(message: str) -> str:
    """Strip credentials and hostnames from a driver error before it can travel.

    The refusal is persisted, surfaced in the UI and readable by anyone who can open the dossier, so
    it outlives the log line that produced it.
    """
    text = message
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text
