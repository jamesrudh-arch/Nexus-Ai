"""PostgreSQL parity: the same store, the same values, against a real server (F-31).

Every test here runs against an actual PostgreSQL 16 started in-process by ``pgserver`` — not a
mock, not a dialect guess. That distinction is the whole point of the file. ``migrations/*.sql`` was
described for four stages as "the portable PostgreSQL target" and promotion as "a copy, not a
rewrite", and nothing in the repository had ever sent that file to a server: ``test_schema_fidelity.py``
parses it with a regex, so six missing commas in ``0001_core.sql`` — which left two of fourteen
tables standing and produced thirteen cascade errors behind the one real fault — survived until this
file existed. A parse cannot catch a statement that will not run.

The suite skips, loudly, when the driver or the server cannot be had. A skip is honest; a green run
that never contacted a database is the same failure as a tamper sweep reporting every site silent
because its harness suppressed the summary it parsed.

What is pinned, and what is pinned as a known divergence
--------------------------------------------------------
Parity is asserted on values, not on SQL text: the same call through ``PostgresOperationalStore``
and ``SqliteOperationalStore`` must read back equal. Where the two cannot be made equal, the
difference is asserted explicitly with its reason in ``TestKnownDivergences``, so it is a recorded
property of the system rather than something discovered in production.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

from nexus.store.pg import (
    PostgresConnection,
    PostgresError,
    Row,
    numeric_to_text,
    public_dsn,
    reads_only,
    to_pyformat,
)
from nexus.store.postgres import (
    PostgresAuditStore,
    PostgresOperationalStore,
    bootstrap_schema,
    migrations_dir,
    split_statements,
)
from nexus.store.serialise import dumps_canonical

SKIP_REASON = (
    "PostgreSQL parity needs the 'postgres' extra and pgserver, both in the dev extra: "
    "pip install -e '.[dev]'. Skipping rather than passing, because a test that never contacted a "
    "database proves nothing about one."
)

STORE_DIR = Path(__file__).resolve().parents[1] / "src/nexus/store"
OPERATIONAL = STORE_DIR / "operational.py"


def _upserts_in(path: Path) -> list[str]:
    """Every ``INSERT OR ...`` statement in a module, found by parsing it rather than by regex.

    Python joins implicitly concatenated literals into one constant, so the ``op_projection``
    statement — written across two quoted lines — arrives here whole, which a text search for
    triple-quoted SQL does not.
    """
    import ast

    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(r"INSERT OR (?:REPLACE|IGNORE) INTO", node.value, re.IGNORECASE)
        ):
            found.append(" ".join(node.value.split()))
    return found


def _minimal_row(
    conn: PostgresConnection, table: str, overrides: dict[str, Any]
) -> tuple[list[str], list[Any]]:
    """A valid row for ``table``, derived from the catalog rather than from an assumption.

    Only the columns the server says are NOT NULL and have no default are supplied, plus whatever the
    caller overrides. A first attempt guessed which columns were nullable, passed ``None`` for
    ``venue_instrument_mapping.fees``, and was refused — which is the catalog being right and the
    guess being wrong.
    """
    names: list[str] = []
    values: list[Any] = []
    rows = conn.execute(
        "SELECT column_name, udt_name, is_nullable, column_default, is_identity "
        "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ? "
        "ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    assert rows, f"no such table in the catalog: {table}"
    for name, udt, nullable, default, identity in rows:
        if identity == "YES":
            continue  # GENERATED ALWAYS: the writer cannot supply it and must not try
        if name in overrides:
            names.append(name)
            values.append(conn.value_to_postgres(overrides[name], udt))
            continue
        if nullable == "NO" and default is None:
            names.append(name)
            values.append(
                conn.value_to_postgres(
                    {
                        "bool": True,
                        "int8": 1,
                        "int4": 1,
                        "numeric": "0",
                        "jsonb": "{}",
                        "timestamptz": "2026-11-28T09:00:00.000Z",
                    }.get(udt, "[]" if udt.startswith("_") else f"{name}-value"),
                    udt,
                )
            )
    return names, values


def _insert_minimal(conn: PostgresConnection, table: str, overrides: dict[str, Any]) -> None:
    names, values = _minimal_row(conn, table, overrides)
    conn.execute(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(['?'] * len(names))})",  # noqa: S608
        values,
    )
    conn.commit()


@pytest.fixture(scope="session")
def pg_uri(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real PostgreSQL server, started once per session and torn down at the end."""
    pgserver = pytest.importorskip("pgserver", reason=SKIP_REASON)
    psycopg = pytest.importorskip("psycopg", reason=SKIP_REASON)
    root = Path(pgserver.__file__).parent
    if not any(root.glob("pginstall/bin/postgres")):
        pytest.skip(f"{SKIP_REASON} (pgserver shipped no server binary)")
    data = tmp_path_factory.mktemp("pgdata") / "cluster"
    try:
        server = pgserver.get_server(str(data), cleanup_mode=None)
    except Exception as exc:  # noqa: BLE001 - the reason is the point, whatever raised it
        # Skip rather than error, and carry the cause in the reason: on a runner that cannot provide
        # a server this is the only text that survives, and the CI step that reads it fails the build,
        # so a skip here is loud rather than silent.
        pytest.skip(f"{SKIP_REASON} (the server would not start: {type(exc).__name__}: {exc})")
    with psycopg.connect(server.get_uri()) as probe:
        version = int(probe.execute("SHOW server_version_num").fetchone()[0])
    assert version >= 160000, f"the portable target is written for PostgreSQL 16, found {version}"
    yield server.get_uri()
    server.cleanup()


@pytest.fixture
def admin(pg_uri: str) -> Iterator[Any]:
    """A maintenance connection, for creating and dropping the per-test database."""
    import psycopg

    with psycopg.connect(pg_uri, autocommit=True) as connection:
        yield connection


@pytest.fixture
def dsn(pg_uri: str, admin: Any) -> Iterator[str]:
    """One empty database per test, dropped afterwards, so nothing is inherited between them."""
    name = f"nexus_test_{uuid4().hex[:12]}"
    admin.execute(f'CREATE DATABASE "{name}"')  # noqa: S608 - a generated identifier, not input
    # A URL, not psycopg's keyword form: NEXUS_DATABASE_URL is documented as a URL and that is what a
    # managed platform hands out, so the tests should use the same shape. make_conninfo would return
    # `host=... dbname=...`, which _postgres_dsn rightly does not accept.
    parts = urlsplit(pg_uri)
    yield urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # noqa: S608


@pytest.fixture
def conn(dsn: str) -> Iterator[PostgresConnection]:
    """An adapter over a database whose schema is already up."""
    connection = PostgresConnection(dsn)
    bootstrap_schema(connection)
    yield connection
    connection.close()


def _decision_payload(decision_id: str = "DEC-PARITY-1") -> dict[str, Any]:
    """A decision exercising every awkward column type at once.

    Arrays for the three reference lists, a dict for the ``jsonb`` risk check, a Decimal-bearing
    string for the ``numeric`` confidence and ISO-8601 timestamps for the ``timestamptz`` columns, so
    one round trip tests the whole value-translation boundary rather than a single column of it.
    """
    return {
        "decision_id": decision_id,
        "created_at": "2026-11-28T09:00:00.000Z",
        "updated_at": "2026-11-28T09:00:01.500Z",
        "state": "PROPOSED",
        "verb": "ABSTAIN",
        "instrument_id": "INS-BTC-USDT",
        "venue": "BYBIT",
        "strategy_id": "STRAT-1",
        "model_id": "MODEL-1",
        "horizon": "1h",
        "confidence": "0.5",
        "rationale": "insufficient evidence to act",
        "reason_codes": ["INSUFFICIENT_EVIDENCE", "STALE_QUOTE"],
        "evidence_refs": ["EV-1", "EV-2"],
        "counter_evidence_refs": ["EV-9"],
        "intent_id": None,
        "risk_check": {"passed": False, "breaches": ["max_leverage"], "score": 0.25},
        "expires_at": "2026-11-28T10:00:00.000Z",
    }


class TestPortableTargetApplies:
    """The claim four stages of documents made, executed for the first time."""

    def test_every_migration_file_applies_to_a_real_server(self, dsn: str) -> None:
        """Regression test for the six missing commas.

        ``audit_ref TEXT`` followed by ``UNIQUE (...)`` with no comma between them is a syntax error
        in any dialect. It aborted ``0001_core.sql`` at line 98, and the thirteen errors reported
        behind it were only the aborted transaction refusing to continue — which is also why a first
        attempt at this audit counted fourteen faults where there was one.
        """
        connection = PostgresConnection(dsn)
        try:
            for path in sorted(migrations_dir().glob("*.sql")):
                connection.executescript(path.read_text(encoding="utf-8"))
        finally:
            connection.close()

    def test_the_schema_the_target_produces_is_complete(self, conn: PostgresConnection) -> None:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            ).fetchall()
        }
        assert len(tables) == 17, sorted(tables)
        # 0003_audit_append_only's protection is a trigger here, because a server binds a trigger to
        # its table; the mirror carries it in 0001 for that reason and that is not drift.
        functions = {
            row[0]
            for row in conn.execute(
                "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public'"
            ).fetchall()
        }
        assert "audit_log_is_append_only" in functions
        triggers = {
            row[0] for row in conn.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal").fetchall()
        }
        assert triggers == {"trg_audit_no_update", "trg_audit_no_delete"}

    def test_the_surrogate_sits_on_exactly_the_tables_that_order_by_rowid(
        self, conn: PostgresConnection
    ) -> None:
        # Searched inside string literals only. Scanning the module text found `from __future__
        # import annotations` and reported it as a table ordering by rowid.
        ordered: set[str] = set()
        for literal in re.findall(r'"""(.*?)"""', OPERATIONAL.read_text(), re.S):
            if re.search(r"\browid\b", literal, re.IGNORECASE):
                match = re.search(r"FROM\s+(\w+)", literal, re.IGNORECASE)
                assert match, f"a rowid ordering with no FROM: {literal[:80]}"
                ordered.add(match.group(1))
        assert "__future__" not in ordered
        declared = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'row_order'"
            ).fetchall()
        }
        assert ordered <= declared, (
            f"queries order by rowid on tables with no surrogate: {sorted(ordered - declared)}"
        )
        assert declared == {"decision", "execution_result", "halt_event", "orders"}
        for table in sorted(declared):
            identity = conn.execute(
                "SELECT is_identity FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = ? AND column_name = 'row_order'",
                (table,),
            ).fetchone()[0]
            assert identity == "YES", f"{table}.row_order must be an identity column to be monotonic"

    def test_reopening_finds_the_schema_already_current(self, dsn: str) -> None:
        """Idempotence is load-bearing: the audit store and the operational store both bootstrap.

        SQLite keeps them in two files, so only one applies DDL. PostgreSQL has one database, so
        whichever opens first brings the schema up and the other must find it already there.
        """
        first = PostgresConnection(dsn)
        report = bootstrap_schema(first)
        assert [row.version for row in report.applied] == ["0001_core", "0002_memory"]
        assert report.already_applied == ()
        assert all(row.statements > 0 for row in report.applied)
        first.close()

        second = PostgresConnection(dsn)
        again = bootstrap_schema(second)
        assert again.applied == (), "a second boot must not claim to have applied anything"
        assert again.already_applied == ("0001_core", "0002_memory")
        second.close()

    def test_both_open_orders_work(self, pg_uri: str, admin: Any) -> None:
        """Audit-first and operational-first, because the app does not guarantee an order."""
        from psycopg.conninfo import make_conninfo

        name = f"nexus_order_{uuid4().hex[:8]}"
        admin.execute(f'CREATE DATABASE "{name}"')  # noqa: S608
        other = make_conninfo(pg_uri, dbname=name)
        try:
            audit_first = PostgresAuditStore(other)
            operational_second = PostgresOperationalStore(other)
            assert operational_second.migrations is not None
            assert operational_second.migrations.applied == (), "the audit store already brought it up"
            operational_second.close()
            audit_first.close()
        finally:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # noqa: S608

        name = f"nexus_order_{uuid4().hex[:8]}"
        admin.execute(f'CREATE DATABASE "{name}"')  # noqa: S608
        other = make_conninfo(pg_uri, dbname=name)
        try:
            operational_first = PostgresOperationalStore(other)
            audit_second = PostgresAuditStore(other)
            assert operational_first.migrations is not None
            assert len(operational_first.migrations.applied) == 2
            audit_second.close()
            operational_first.close()
        finally:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # noqa: S608

    def test_a_missing_migrations_directory_is_a_refusal_not_an_empty_database(
        self, dsn: str, tmp_path: Path
    ) -> None:
        connection = PostgresConnection(dsn)
        try:
            with pytest.raises(FileNotFoundError, match="no portable DDL"):
                bootstrap_schema(connection, tmp_path / "nowhere")
        finally:
            connection.close()


class TestStatementTranslation:
    """Every SQLite-ism the store actually uses, translated and then planned by the server."""

    def test_every_upsert_in_the_store_plans_on_postgres(self, conn: PostgresConnection) -> None:
        """All fifteen writer statements, taken from the source rather than retyped here.

        ``EXPLAIN`` parses and plans without executing, so a statement that would fail against the
        real schema fails here — and NOT NULL constraints cannot interfere, because planning does
        not check them.
        """
        statements = _upserts_in(OPERATIONAL) + _upserts_in(STORE_DIR / "migrations.py")
        # A first attempt at this test used a regex for triple-quoted strings, extracted thirteen of
        # the fifteen and reported success. Two were invisible to it: op_projection's is a
        # concatenated literal and schema_migration_skips' lives in migrations.py. Parsing the module
        # instead means the quoting style cannot hide one, and the count is asserted so it cannot
        # silently drop again.
        assert len(statements) == 15, f"expected 15 upserts across the store, found {len(statements)}"
        assert any("op_projection" in s for s in statements), "the concatenated literal was missed"
        assert any("schema_migration_skips" in s for s in statements), "migrations.py was missed"

        for sql in statements:
            text, table, columns = conn._rewrite(sql)
            assert "INSERT OR" not in text, f"{table}: SQLite syntax survived the translation"
            assert "?" not in text, f"{table}: a placeholder survived the translation"
            assert text.count("%s") == len(columns), f"{table}: placeholder count disagrees with columns"
            conn._conn.execute("EXPLAIN " + text, [None] * len(columns))

    @pytest.mark.parametrize(
        ("table", "expected"),
        [
            ("decision", ["decision_id"]),
            ("memory_item", ["memory_id"]),
            ("orders", ["order_id"]),
            # The one table whose upsert omits its own primary key, because mapping_id is GENERATED
            # ALWAYS AS IDENTITY and the writer cannot supply it. The target has to fall back to the
            # unique triple; choosing the primary key would fail on every insert.
            ("venue_instrument_mapping", ["instrument_id", "venue", "venue_symbol"]),
        ],
    )
    def test_the_conflict_target_is_the_one_the_catalog_implies(
        self, conn: PostgresConnection, table: str, expected: list[str]
    ) -> None:
        columns = [c for c in conn.column_types(table) if c not in ("mapping_id", "row_order")]
        assert conn._conflict_target(table, columns) == expected

    def test_a_table_with_no_fitting_constraint_is_refused_not_guessed(
        self, conn: PostgresConnection
    ) -> None:
        with pytest.raises(PostgresError, match="cannot choose an ON CONFLICT target"):
            conn._conflict_target("decision", ["instrument_id", "venue"])

    @pytest.mark.parametrize(
        ("sql", "expected"),
        [
            ("SELECT * FROM t WHERE a = ?", "SELECT * FROM t WHERE a = %s"),
            ("SELECT * FROM t WHERE a = '?' AND b = ?", "SELECT * FROM t WHERE a = '?' AND b = %s"),
            (
                "SELECT * FROM t WHERE a = 'it''s ?' AND b = ?",
                "SELECT * FROM t WHERE a = 'it''s ?' AND b = %s",
            ),
            (
                "SELECT * FROM t WHERE a = ? -- why?\nAND b = ?",
                "SELECT * FROM t WHERE a = %s -- why?\nAND b = %s",
            ),
            ('SELECT * FROM t WHERE "odd?name" = ?', 'SELECT * FROM t WHERE "odd?name" = %s'),
        ],
    )
    def test_placeholder_rewrite_leaves_literals_alone(self, sql: str, expected: str) -> None:
        assert to_pyformat(sql) == expected

    @pytest.mark.parametrize(
        ("pragma", "expected"),
        [
            ("PRAGMA journal_mode=WAL", ""),
            ("PRAGMA synchronous=FULL", "SET synchronous_commit = on"),
            ("PRAGMA busy_timeout=5000", ""),
        ],
    )
    def test_the_three_pragmas_the_store_executes_are_mapped(
        self, conn: PostgresConnection, pragma: str, expected: str
    ) -> None:
        assert conn._rewrite(pragma)[0] == expected

    def test_named_parameters_are_translated_too(self) -> None:
        """SQLite has two placeholder spellings; psycopg wants two different ones.

        ``audit/log.py`` binds a dict with ``:name``. Translating only ``?`` left that statement with
        no placeholder at all, so boot recovery died on "the query has 0 placeholders but 8 parameters
        were passed" — after the schema had already been created, which is the worst place to fail.
        """
        assert to_pyformat("VALUES (:seq, :record_id)") == "VALUES (%(seq)s, %(record_id)s)"
        assert to_pyformat("WHERE a = ? AND b = :name") == "WHERE a = %s AND b = %(name)s"
        # The append-only trigger's own casts must survive the rewrite.
        assert to_pyformat("SELECT x::text, y::jsonb") == "SELECT x::text, y::jsonb"
        assert to_pyformat("SELECT '12:30:45'") == "SELECT '12:30:45'"
        assert to_pyformat("SELECT ':not_a_param'") == "SELECT ':not_a_param'"
        # Deliberately untranslated: both collide with PostgreSQL syntax and neither is used here.
        assert to_pyformat("SELECT $name, @name") == "SELECT $name, @name"

    def test_a_dict_can_be_bound_where_sqlite_bound_a_dict(self, conn: PostgresConnection) -> None:
        """The audit append, exercised exactly as the audit append writes it."""
        row = {
            "seq": 1,
            "record_id": "REC-NAMED-1",
            "event_type": "TEST",
            "actor": "test",
            "payload": dumps_canonical({"ok": True}),
            "timestamp": "2026-11-28T10:00:00.000Z",
            "prev_hash": "0" * 64,
            "record_hash": "a" * 64,
        }
        conn.execute(
            """INSERT INTO audit_log
               (seq, record_id, event_type, actor, payload, timestamp, prev_hash, record_hash)
               VALUES (:seq, :record_id, :event_type, :actor, :payload, :timestamp,
                       :prev_hash, :record_hash)""",
            row,
        )
        conn.commit()
        found = conn.execute("SELECT * FROM audit_log WHERE record_id = ?", ("REC-NAMED-1",)).fetchone()
        assert found is not None
        assert dict(found)["payload"] == dumps_canonical({"ok": True}), (
            "jsonb must come back byte-identical or loads_json fails on it"
        )

    def test_an_unknown_pragma_is_refused_rather_than_dropped(self, conn: PostgresConnection) -> None:
        """A new durability setting silently ignored is a durability setting silently lost."""
        with pytest.raises(PostgresError, match="no PostgreSQL counterpart"):
            conn._rewrite("PRAGMA foreign_keys=ON")

    def test_rowid_becomes_the_surrogate_the_catalog_declares(self, conn: PostgresConnection) -> None:
        text, table, _ = conn._rewrite("SELECT * FROM halt_event ORDER BY seq ASC, rowid ASC")
        assert table == "halt_event"
        assert "rowid" not in text
        assert "row_order" in text
        conn._conn.execute("EXPLAIN " + text)

    def test_rowid_on_a_table_with_no_surrogate_is_refused(self, conn: PostgresConnection) -> None:
        with pytest.raises(PostgresError, match="declares no row_order"):
            conn._rewrite("SELECT * FROM instrument ORDER BY rowid ASC")

    def test_an_untranslatable_upsert_is_refused(self, conn: PostgresConnection) -> None:
        with pytest.raises(PostgresError, match="cannot translate"):
            conn._rewrite("INSERT OR ROLLBACK INTO decision (decision_id) VALUES (?)")

    def test_an_identifier_that_is_not_a_bare_name_is_refused(self, conn: PostgresConnection) -> None:
        """The names come from the store's own SQL, which is not a reason to trust them in a string
        that becomes SQL."""
        with pytest.raises(PostgresError, match="refusing to interpolate"):
            conn._rewrite("INSERT OR REPLACE INTO decision (decision_id, x y) VALUES (?,?)")


class TestValueParity:
    """The half that keeps 1,373 lines of deserialisers working without knowing the driver changed."""

    def test_the_same_decision_reads_back_equal_from_both_drivers(self, dsn: str, tmp_path: Path) -> None:
        from nexus.store.operational import SqliteOperationalStore

        payload = _decision_payload()
        sqlite_store = SqliteOperationalStore(tmp_path / "parity.db")
        pg_store = PostgresOperationalStore(dsn)
        try:
            # PostgreSQL enforces decision_instrument_id_fkey, which SQLite declares and does not
            # enforce, so the parent has to exist on that side. Seeding only PostgreSQL keeps the
            # comparison honest: SQLite is not being given a row it did not need.
            with PostgresConnection(dsn) as seed:
                _insert_minimal(seed, "instrument", {"instrument_id": payload["instrument_id"]})
            sqlite_store.save_decision_payload(payload)
            pg_store.save_decision_payload(payload)
            from_sqlite = sqlite_store.get_decision(payload["decision_id"])
            from_postgres = pg_store.get_decision(payload["decision_id"])
            assert from_sqlite is not None and from_postgres is not None
            assert from_postgres == from_sqlite, (
                "a value that differs between drivers is a value one of the two got wrong:\n"
                + "\n".join(
                    f"   {k}: sqlite={from_sqlite.get(k)!r} postgres={from_postgres.get(k)!r}"
                    for k in sorted(set(from_sqlite) | set(from_postgres))
                    if from_sqlite.get(k) != from_postgres.get(k)
                )
            )
        finally:
            sqlite_store.close()
            pg_store.close()

    def test_the_same_halt_event_reads_back_equal_from_both_drivers(self, dsn: str, tmp_path: Path) -> None:
        """The array columns and the boolean, which are the two shapes SQLite cannot express natively."""
        from nexus.store.operational import SqliteOperationalStore

        kwargs: dict[str, Any] = {
            "action": "ENGAGE",
            "scope": "ALL_TRADING",
            "reason": "daily drawdown breached",
            "triggered_by": "SYSTEM",
            "at": "2026-11-28T09:00:00.000Z",
            "halt_id": "HLT-PARITY-1",
            "affected_accounts": ("ACC-1", "ACC-2"),
            "affected_instruments": (),
            "cancel_working_orders": True,
        }
        sqlite_store = SqliteOperationalStore(tmp_path / "halt.db")
        pg_store = PostgresOperationalStore(dsn)
        try:
            sqlite_store.save_halt_event(**kwargs)
            pg_store.save_halt_event(**kwargs)
            from_sqlite = sqlite_store.halt_events()
            from_postgres = pg_store.halt_events()
            assert len(from_sqlite) == len(from_postgres) == 1
            assert from_postgres[0] == from_sqlite[0], "\n".join(
                f"   {k}: sqlite={from_sqlite[0][k]!r} postgres={from_postgres[0][k]!r}"
                for k in sorted(from_sqlite[0])
                if from_sqlite[0].get(k) != from_postgres[0].get(k)
            )
        finally:
            sqlite_store.close()
            pg_store.close()

    def test_the_same_memory_item_reads_back_equal_from_both_drivers(self, dsn: str, tmp_path: Path) -> None:
        from nexus.store.operational import SqliteOperationalStore

        payload = {
            "memory_id": "MEM-PARITY-1",
            "kind": "BELIEF",
            "scope": "INSTRUMENT",
            "subject": "INS-BTC-USDT",
            "body": "funding has been positive for three sessions",
            "created_at": "2026-11-28T09:00:00.000Z",
            "cited_by": ["EV-1", "EV-2"],
            "confidence": "0.75",
            "payload": {"window": "3d", "samples": 9},
        }
        sqlite_store = SqliteOperationalStore(tmp_path / "memory.db")
        pg_store = PostgresOperationalStore(dsn)
        try:
            sqlite_store.save_memory_item(payload)
            pg_store.save_memory_item(payload)
            from_sqlite = sqlite_store.get_memory_item(payload["memory_id"])
            from_postgres = pg_store.get_memory_item(payload["memory_id"])
            assert from_sqlite is not None and from_postgres is not None
            assert from_postgres == from_sqlite, "\n".join(
                f"   {k}: sqlite={from_sqlite.get(k)!r} postgres={from_postgres.get(k)!r}"
                for k in sorted(set(from_sqlite) | set(from_postgres))
                if from_sqlite.get(k) != from_postgres.get(k)
            )
        finally:
            sqlite_store.close()
            pg_store.close()

    def test_jsonb_comes_back_as_canonical_text_not_a_dict(self, conn: PostgresConnection) -> None:
        """``loads_json`` parses a string; handing it a dict would raise deep inside a projection."""
        risk = {"passed": False, "breaches": ["max_leverage"], "score": 0.25}
        conn.execute(
            "INSERT OR REPLACE INTO decision (decision_id, created_at, updated_at, state, verb, "
            "rationale, reason_codes, evidence_refs, counter_evidence_refs, risk_check) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "DEC-J",
                "2026-11-28T09:00:00.000Z",
                "2026-11-28T09:00:00.000Z",
                "PROPOSED",
                "ABSTAIN",
                "",
                "[]",
                "[]",
                "[]",
                dumps_canonical(risk),
            ),
        )
        conn.commit()
        raw = conn._conn.execute("SELECT risk_check FROM decision WHERE decision_id = 'DEC-J'").fetchone()[0]
        assert isinstance(raw, dict), "the server really is storing jsonb, so the test is not vacuous"
        adapted = dict(
            conn.execute("SELECT risk_check FROM decision WHERE decision_id = ?", ("DEC-J",)).fetchone()
        )
        assert isinstance(adapted["risk_check"], str)
        assert json.loads(adapted["risk_check"]) == risk
        assert adapted["risk_check"] == dumps_canonical(risk), "byte-identical to what SQLite stores"

    def test_the_surrogate_never_reaches_a_caller(self, conn: PostgresConnection) -> None:
        """``SELECT *`` must not return a column SQLite does not have.

        The store deserialises with ``dict(row)`` and the API serves those dicts, so an extra column
        would appear in every HTTP response on PostgreSQL and in none from SQLite. The column exists
        to give the server an insertion order; it is not part of any entity.
        """
        _insert_minimal(conn, "instrument", {"instrument_id": "INS-PROJ"})
        conn.execute(
            "INSERT OR REPLACE INTO decision (decision_id, created_at, updated_at, state, verb, "
            "instrument_id, rationale, reason_codes, evidence_refs, counter_evidence_refs, "
            "risk_check) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "DEC-PROJ",
                "2026-11-28T09:00:00.000Z",
                "2026-11-28T09:00:00.000Z",
                "PROPOSED",
                "ABSTAIN",
                "INS-PROJ",
                "",
                "[]",
                "[]",
                "[]",
                "{}",
            ),
        )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM decision WHERE decision_id = ?", ("DEC-PROJ",)).fetchone())
        assert "row_order" not in row
        assert "decision_id" in row and "risk_check" in row
        # The column is really there and really monotonic; only the adapter hides it.
        raw = conn._conn.execute("SELECT row_order FROM decision WHERE decision_id = 'DEC-PROJ'")
        assert raw.fetchone()[0] >= 1

    def test_rows_support_dict_and_index_access_like_sqlite_row(self) -> None:
        row = Row((1, "two", None), ("a", "b", "c"))
        assert dict(row) == {"a": 1, "b": "two", "c": None}
        assert row[0] == 1
        assert row["b"] == "two"
        assert len(row) == 3
        assert list(row) == [1, "two", None]
        assert row == (1, "two", None)
        assert "b" in row
        assert "zzz" not in row
        with pytest.raises(IndexError):
            row["nope"]


class TestKnownDivergences:
    """Where the two drivers cannot be made equal, pinned so the gap cannot widen unnoticed."""

    def test_numeric_pads_to_its_declared_scale_so_trailing_zeros_are_lost(self) -> None:
        """L-4 says Decimals travel as their exact string form; ``NUMERIC`` cannot honour that.

        Measured rather than reasoned about: PostgreSQL returns ``numeric(6,5)`` padded to five
        places, so ``'0.5'`` survives the round trip and ``'0.50'`` does not. ``numeric_to_text``
        recovers the shortest exact form, which is every value not carrying zeros of its own.
        """
        assert numeric_to_text(Decimal("0.50000")) == "0.5"
        assert numeric_to_text(Decimal("-9.90000")) == "-9.9"
        assert numeric_to_text(Decimal("9.99999")) == "9.99999"
        assert numeric_to_text(Decimal("0.00001")) == "0.00001"
        assert numeric_to_text(Decimal("100")) == "100"
        assert numeric_to_text(Decimal("1.00000")) == "1"
        # The divergence, stated as a fact instead of left to be discovered later:
        assert numeric_to_text(Decimal("0.50000")) != "0.50"
        assert numeric_to_text(Decimal("1.00000")) != "1.0"

    def test_numeric_6_5_refuses_a_magnitude_sqlite_accepts(self, dsn: str, tmp_path: Path) -> None:
        """The ceiling that made F-24's band a two-column question, proven at the DDL level.

        ``decision.confidence`` is ``NUMERIC(6,5)`` in the target and unconstrained ``TEXT`` in
        SQLite, so a confidence of 10 stores in one and is refused by the other. A promoted database
        is stricter than the one it replaced. D-057 ruled the band as two endpoints rather than a
        width for exactly this reason: a width is a magnitude and inherits this ceiling.
        """
        from nexus.store.operational import SqliteOperationalStore

        payload = _decision_payload("DEC-BIG") | {"confidence": "10"}
        sqlite_store = SqliteOperationalStore(tmp_path / "big.db")
        pg_store = PostgresOperationalStore(dsn)
        try:
            with PostgresConnection(dsn) as seed:
                _insert_minimal(seed, "instrument", {"instrument_id": payload["instrument_id"]})
            sqlite_store.save_decision_payload(payload)
            assert sqlite_store.get_decision("DEC-BIG") is not None, "SQLite's TEXT column has no ceiling"
            with pytest.raises(Exception, match="numeric field overflow|operational write failed"):
                pg_store.save_decision_payload(payload)
        finally:
            sqlite_store.close()
            pg_store.close()

    def test_the_two_schemas_do_not_declare_the_same_checks(self, conn: PostgresConnection) -> None:
        """A promotion changes which writes are refused, in both directions.

        PostgreSQL declares ``quantity > 0`` on ``fills`` and ``trade_intent`` where SQLite declares
        neither, so a zero quantity is refused after promotion and accepted before it. SQLite declares
        a ``confidence`` CHECK on ``memory_item`` — the leaky one 0004 added, which admits
        ``'0.5abc'`` — and the target declares none, so that column is *less* constrained after
        promotion. Neither direction is visible from either DDL alone.
        """
        checks: dict[str, set[str]] = {}
        for table, definition in conn.execute(
            "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
        ).fetchall():
            checks.setdefault(table, set()).add(definition)
        assert any("quantity" in c for c in checks.get("fills", set()))
        assert any("quantity" in c for c in checks.get("trade_intent", set()))
        assert "memory_item" not in checks, (
            "the target grew a confidence CHECK, which is 8.8's decision to make and not this file's"
        )

    def test_an_upsert_preserves_the_surrogate_where_sqlite_churns_rowid(self, dsn: str) -> None:
        """``INSERT OR REPLACE`` deletes and re-inserts, so SQLite assigns a fresh rowid every save.

        ``ON CONFLICT DO UPDATE`` updates in place and ``row_order`` survives, so re-saving a decision
        moves it to the end of a rowid ordering on SQLite and leaves it where it was on PostgreSQL.
        Recorded rather than replicated: matching SQLite would mean reproducing an artifact of
        delete-plus-insert, which also resets every column the statement does not list and fires
        ``ON DELETE CASCADE``.
        """
        conn = PostgresConnection(dsn)
        bootstrap_schema(conn)
        try:
            sql = (
                "INSERT OR REPLACE INTO decision (decision_id, created_at, updated_at, state, verb, "
                "rationale, reason_codes, evidence_refs, counter_evidence_refs, risk_check) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)"
            )
            args = (
                "DEC-UP",
                "2026-11-28T09:00:00.000Z",
                "2026-11-28T09:00:00.000Z",
                "PROPOSED",
                "ABSTAIN",
                "",
                "[]",
                "[]",
                "[]",
                "{}",
            )
            conn.execute(sql, args)
            conn.commit()
            # Through the raw driver: the adapter projects row_order out of every result, which is
            # the point of the column and is asserted separately in TestValueParity.
            raw = "SELECT row_order FROM decision WHERE decision_id = 'DEC-UP'"
            first = conn._conn.execute(raw).fetchone()[0]
            conn.execute(sql, (*args[:4], "WAIT", *args[5:]))
            conn.commit()
            second = conn._conn.execute(raw).fetchone()[0]
            assert first == second, "row_order must survive an upsert"
            assert (
                conn.execute("SELECT verb FROM decision WHERE decision_id = ?", ("DEC-UP",)).fetchone()[0]
                == "WAIT"
            )
        finally:
            conn.close()

    def test_the_identity_key_is_kept_where_sqlite_would_reassign_it(self, conn: PostgresConnection) -> None:
        """The same artifact, on the one table with a ``GENERATED ALWAYS AS IDENTITY`` key.

        ``mapping_id`` is not in the upsert's column list, so SQLite's replace assigns a new one on
        every save while PostgreSQL's conflict-update keeps the original. A stable surrogate is the
        better behaviour, but it is a difference, and this pins which side does what.
        """
        _insert_minimal(conn, "instrument", {"instrument_id": "INS-BTC-USDT"})
        # Both writes go through INSERT OR REPLACE so both are translated to ON CONFLICT. A plain
        # INSERT the second time is refused by the unique triple and proves nothing about
        # conflict-update, which is what a first version of this test did.
        names, values = _minimal_row(
            conn,
            "venue_instrument_mapping",
            {"instrument_id": "INS-BTC-USDT", "venue": "BYBIT", "venue_symbol": "BTC/USDT"},
        )
        # Every identifier comes from the live catalog, not from input.
        upsert = (
            f"INSERT OR REPLACE INTO venue_instrument_mapping ({', '.join(names)}) "  # noqa: S608
            f"VALUES ({', '.join(['?'] * len(names))})"  # noqa: S608
        )
        lookup = "SELECT mapping_id FROM venue_instrument_mapping WHERE instrument_id = ?"
        conn.execute(upsert, values)
        conn.commit()
        first = conn.execute(lookup, ("INS-BTC-USDT",)).fetchone()[0]
        conn.execute(upsert, values)
        conn.commit()
        second = conn.execute(lookup, ("INS-BTC-USDT",)).fetchone()[0]
        assert first == second, "PostgreSQL keeps the identity; SQLite would have reassigned it"


class TestAppendOnlyIsEnforcedByTheServer:
    """0003's protection, which in PostgreSQL is a trigger rather than application discipline."""

    def _append(self, conn: PostgresConnection, seq: int) -> None:
        conn.execute(
            "INSERT INTO audit_log (seq, record_id, event_type, actor, payload, timestamp, prev_hash, "
            "record_hash) VALUES (?,?,?,?,?,?,?,?)",
            (
                seq,
                f"REC-{seq}",
                "decision.recorded",
                "system",
                "{}",
                "2026-11-28T09:00:00.000Z",
                f"hash{seq - 1}" if seq > 1 else "genesis",
                f"hash{seq}",
            ),
        )
        conn.commit()

    def test_an_update_to_the_chain_is_refused(self, conn: PostgresConnection) -> None:
        self._append(conn, 1)
        with pytest.raises(PostgresError):
            conn.execute("UPDATE audit_log SET event_type = 'tampered' WHERE seq = 1")

    def test_a_delete_from_the_chain_is_refused(self, conn: PostgresConnection) -> None:
        self._append(conn, 1)
        with pytest.raises(PostgresError):
            conn.execute("DELETE FROM audit_log WHERE seq = 1")

    def test_appending_still_works(self, conn: PostgresConnection) -> None:
        self._append(conn, 1)
        self._append(conn, 2)
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 2


class TestRefusalsAreSafeToSurface:
    """A database URL carries a password, and a refusal is persisted and shown in the UI."""

    def test_an_unreachable_server_leaks_neither_host_nor_password(self) -> None:
        with pytest.raises(PostgresError) as exc:
            PostgresConnection("postgresql://nexus:Sup3rSecretPassword@db-host.invalid:5432/nexus")
        message = str(exc.value)
        assert "Sup3rSecretPassword" not in message
        assert "db-host.invalid" not in message, (
            "psycopg names the host it failed to resolve, and test_api.py has pinned since before "
            "F-31 that a refused URL leaks neither the credential nor the hostname"
        )

    def test_a_keyword_form_url_does_not_put_its_password_in_the_refusal(self) -> None:
        """psycopg also accepts ``host=... password=...``, which has no colon to split on.

        ``url.split(":", 1)[0]`` returned the whole string for that shape, and the refusal it feeds is
        persisted and surfaced in the UI. A configuration mistake would have written a live credential
        into the audit chain.
        """
        from nexus.api.app import _scheme_of

        assert _scheme_of("postgresql://u:pw@h:5432/db") == "postgresql"
        assert _scheme_of("sqlite:///./data/nexus.db") == "sqlite"
        assert _scheme_of("host=h password=Sup3rSecret dbname=nexus") == "<not-a-url>"
        assert "Sup3rSecret" not in _scheme_of("host=h password=Sup3rSecret dbname=nexus")
        assert _scheme_of("") == "<not-a-url>"

    def test_the_missing_driver_is_a_refusal_not_a_silent_fallback(self, monkeypatch: Any) -> None:
        import nexus.store.pg as pg

        monkeypatch.setattr(pg, "_psycopg", None)
        with pytest.raises(PostgresError, match="postgres' extra"):
            pg.PostgresConnection("postgresql://nexus@localhost:5432/nexus")


class TestWhatTheStatusEndpointPublishes:
    """``/v1/status`` is unauthenticated (D-026), so nothing it reports may be a secret.

    Two defects appeared together when the second driver landed. ``persistence.engine`` was
    hard-coded to ``"sqlite"``, so a system running on PostgreSQL described itself as SQLite while
    the ``path`` beside it was a PostgreSQL DSN — an endpoint contradicting itself on the wire. And
    that ``path`` was the raw DSN, which on every managed platform carries the password.
    """

    def test_credentials_are_stripped_and_the_rest_is_kept_verbatim(self) -> None:
        assert public_dsn("postgresql://nexus:Sup3rSecret@db.internal:5432/nexus") == (
            "postgresql://db.internal:5432/nexus"
        )
        assert public_dsn("postgresql://u:pw@h:5432/db?sslmode=require") == (
            "postgresql://h:5432/db?sslmode=require"
        )
        # psycopg's keyword form, filtered key by key.
        assert public_dsn("host=db password=Sup3rSecret dbname=nexus user=nexus") == (
            "host=db dbname=nexus user=nexus"
        )
        # An empty authority keeps its `//`: urlunsplit would drop it and change the URL's meaning.
        assert public_dsn("sqlite:///./data/nexus.db") == "sqlite:///./data/nexus.db"
        assert public_dsn("sqlite:////abs/nexus.db") == "sqlite:////abs/nexus.db"
        assert public_dsn(":memory:") == ":memory:"

    def test_scrubbing_a_clean_target_changes_nothing(self) -> None:
        for url in (
            "postgresql://db.internal:5432/nexus",
            "sqlite:///./data/nexus.db",
            "./data/nexus.db",
            ":memory:",
        ):
            assert public_dsn(url) == url
            assert public_dsn(public_dsn(url)) == url, "the scrub must be idempotent"

    def test_the_postgres_store_reports_its_engine_and_a_publishable_path(self) -> None:
        from nexus.store.operational import SqliteOperationalStore
        from nexus.store.postgres import PostgresOperationalStore

        assert PostgresOperationalStore.engine == "postgresql"
        assert SqliteOperationalStore.engine == "sqlite"
        # Built without connecting: this pins what the store *reports*, not what it opens.
        store = object.__new__(PostgresOperationalStore)
        store._path = "postgresql://nexus:Sup3rSecret@db.internal:5432/nexus"
        assert store.path == "postgresql://db.internal:5432/nexus"
        assert "Sup3rSecret" not in store.path

    def test_an_ephemeral_audit_backend_overrides_the_database_url(self, dsn: str) -> None:
        """`NEXUS_AUDIT_BACKEND=memory` wins over `NEXUS_DATABASE_URL`, and says so on the wire.

        Documented behaviour rather than a defect: `_default_operational_store` refuses to put a
        durable operational state beside a volatile record of why it changed. It is pinned here because
        it is the reason the two tests above have to clear the variable — `ci.yml` sets it for the
        whole workflow, so an app-boot test that does not is a test of the in-memory store. The
        override is visible rather than silent: the endpoint reports `engine: sqlite` and
        `ephemeral: true`, and no PostgreSQL connection is attempted.
        """
        import os

        from fastapi.testclient import TestClient

        from nexus.api.app import create_app
        from nexus.core.config import Settings

        previous = os.environ.get("NEXUS_AUDIT_BACKEND")
        os.environ["NEXUS_AUDIT_BACKEND"] = "memory"
        try:
            app = create_app(settings=Settings(_env_file=None, database_url=dsn))
            with TestClient(app) as client:
                persistence = client.get("/v1/status").json()["persistence"]
        finally:
            if previous is None:
                os.environ.pop("NEXUS_AUDIT_BACKEND", None)
            else:
                os.environ["NEXUS_AUDIT_BACKEND"] = previous
        assert persistence["engine"] == "sqlite", persistence
        assert persistence["ephemeral"] is True, persistence
        assert persistence["path"] is None, "an ephemeral store has no location to publish"

    def test_the_live_status_endpoint_names_the_engine_and_leaks_nothing(
        self, dsn: str, monkeypatch: Any
    ) -> None:
        from fastapi.testclient import TestClient

        from nexus.api.app import create_app
        from nexus.core.config import Settings

        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        app = create_app(settings=Settings(_env_file=None, database_url=dsn))
        with TestClient(app) as client:
            persistence = client.get("/v1/status").json()["persistence"]
        assert persistence["engine"] == "postgresql", persistence["engine"]
        assert persistence["path"].startswith("postgresql://"), persistence["path"]
        # No userinfo, whatever the fixture's DSN happens to contain.
        authority = persistence["path"].split("://", 1)[1].split("/", 1)[0]
        assert "@" not in authority, persistence["path"]


class TestTheApiBootsOnPostgres:
    """The store is not the deliverable; a serving API is.

    ``create_app`` refuses to start without a durable audit trail, so this exercises the whole boot
    path — config, audit store, operational store, boot recovery, projections — against a server
    rather than asserting only that the driver works.
    """

    def test_the_app_serves_and_its_chain_verifies(self, dsn: str, monkeypatch: Any) -> None:
        from fastapi.testclient import TestClient

        from nexus.api.app import create_app
        from nexus.core.config import Settings

        # ci.yml sets NEXUS_AUDIT_BACKEND=memory for the whole workflow, and _default_operational_store
        # answers it by building an ephemeral SQLite store and ignoring database_url — deliberately, so
        # a durable operational state never sits beside a volatile record of why it changed. Without
        # this line the test passed on the runner while exercising no PostgreSQL at all.
        monkeypatch.delenv("NEXUS_AUDIT_BACKEND", raising=False)
        app = create_app(settings=Settings(_env_file=None, database_url=dsn))
        with TestClient(app) as client:
            persistence = client.get("/v1/status").json()["persistence"]
            assert persistence["engine"] == "postgresql", persistence
            assert persistence["ephemeral"] is False, persistence
            health = client.get("/healthz")
            assert health.status_code == 200, health.text
            assert health.json()["status"] == "ok"

            ready = client.get("/readyz").json()
            assert ready["ready"] is True, ready

            status = client.get("/v1/status").json()
            assert status["phase_gate"]["live_trading"] is False
            assert status["phase_gate"]["real_money_orders_possible"] is False

            verify = client.get("/v1/audit/verify").json()
            assert verify["intact"] is True, verify
            assert verify["breaks"] == []

    def test_boot_recovery_runs_against_a_reopened_server(self, dsn: str) -> None:
        """A restart is where a promoted database either survives or does not."""
        from nexus.store.postgres import PostgresOperationalStore

        first = PostgresOperationalStore(dsn)
        # PostgreSQL enforces decision_instrument_id_fkey; SQLite declares it and does not. Seeding
        # the parent is what makes this a test of restart rather than of the foreign key.
        with PostgresConnection(dsn) as seed:
            _insert_minimal(seed, "instrument", {"instrument_id": "INS-BTC-USDT"})
        first.save_decision_payload(_decision_payload("DEC-RESTART"))
        first.close()

        reopened = PostgresOperationalStore(dsn)
        try:
            assert reopened.migrations is not None
            assert reopened.migrations.applied == (), "a restart must not re-apply the schema"
            found = reopened.get_decision("DEC-RESTART")
            assert found is not None
            assert found["decision_id"] == "DEC-RESTART"
            assert found["verb"] == "ABSTAIN"
            assert reopened.counts()["decision"] >= 1
        finally:
            reopened.close()


class TestTransactionShape:
    """A read must not leave a transaction open, and a write must not have one ended under it.

    ``sqlite3`` defers ``BEGIN`` until a write, so ``in_transaction`` is False after any number of
    SELECTs and the store never had to end a read transaction. PostgreSQL opens one on the first
    statement and holds it until commit. Left alone, an API process that had served one read and then
    gone quiet sat ``idle in transaction`` — measured, before the fix, as 2 of the 3 client backends
    one live process held — which pins a snapshot so dead tuples cannot be vacuumed, and waits for
    the provider's ``idle_in_transaction_session_timeout`` to terminate a connection this store never
    re-opens.
    """

    def _status(self, conn: PostgresConnection) -> str:
        return conn._conn.info.transaction_status.name

    def test_reads_leave_nothing_open(self, conn: PostgresConnection) -> None:
        _insert_minimal(conn, "instrument", {"instrument_id": "INS-TXN"})
        assert self._status(conn) == "IDLE", "the insert helper commits, so this starts clean"
        conn.execute("SELECT count(*) FROM instrument").fetchone()
        conn.execute("SELECT * FROM instrument WHERE instrument_id = ?", ("INS-TXN",)).fetchall()
        assert self._status(conn) == "IDLE", "a read must end its own transaction"

    def test_a_write_holds_its_transaction_until_the_store_ends_it(self, conn: PostgresConnection) -> None:
        names, values = _minimal_row(conn, "instrument", {"instrument_id": "INS-W"})
        conn.execute(
            f"INSERT INTO instrument ({', '.join(names)}) VALUES ({', '.join(['?'] * len(names))})",  # noqa: S608
            values,
        )
        assert self._status(conn) == "INTRANS", "an uncommitted write must still be in a transaction"
        conn.rollback()
        assert self._status(conn) == "IDLE"
        assert conn.execute("SELECT count(*) FROM instrument").fetchone()[0] == 0, "and undone"

    def test_a_read_inside_a_write_unit_does_not_end_it(self, conn: PostgresConnection) -> None:
        """The property the whole fix rests on: atomicity of a multi-statement write.

        ``save_decision`` is four statements, not one. If a read between them ended the transaction,
        the write would be half-applied — the worst possible outcome and the reason ``reads_only``
        errs towards calling a statement a write.
        """
        names, values = _minimal_row(conn, "instrument", {"instrument_id": "INS-MID"})
        conn.execute(
            f"INSERT INTO instrument ({', '.join(names)}) VALUES ({', '.join(['?'] * len(names))})",  # noqa: S608
            values,
        )
        seen = conn.execute("SELECT count(*) FROM instrument").fetchone()[0]
        assert seen == 1, "the read must see the uncommitted write beside it"
        assert self._status(conn) == "INTRANS", "and must not have ended the transaction"
        conn.commit()

    def test_the_rows_survive_the_release(self, conn: PostgresConnection) -> None:
        """libpq transfers the whole result on execute, so ending the transaction cannot lose rows."""
        for i in range(5):
            _insert_minimal(conn, "instrument", {"instrument_id": f"INS-ROWS-{i}"})
        cursor = conn.execute("SELECT instrument_id FROM instrument ORDER BY instrument_id")
        assert self._status(conn) == "IDLE", "already released by the time the caller fetches"
        fetched = [row[0] for row in cursor.fetchall()]
        assert fetched == [f"INS-ROWS-{i}" for i in range(5)]
        # sqlite3's shape: a sequence of 7-item tuples, not psycopg's Column objects.
        assert [d[0] for d in cursor.description] == ["instrument_id"]

    def test_the_classifier_errs_towards_calling_a_statement_a_write(self) -> None:
        assert reads_only("SELECT * FROM decision")
        assert reads_only("  select 1")
        assert reads_only("SHOW server_version")
        assert reads_only("EXPLAIN SELECT 1")
        # A data-modifying CTE starts with a read keyword and writes.
        assert not reads_only("WITH gone AS (DELETE FROM decision RETURNING *) SELECT * FROM gone")
        # SET is what the PRAGMA synchronous=FULL mapping produces; rolling one back undoes it.
        assert not reads_only("SET synchronous_commit = on")
        assert not reads_only("INSERT OR REPLACE INTO decision (decision_id) VALUES (?)")
        assert not reads_only("UPDATE decision SET verb = ?")
        # Conservative by design: a literal that mentions a write keyword keeps the transaction open,
        # which costs nothing and cannot lose a write.
        assert not reads_only("SELECT * FROM decision WHERE rationale = 'delete everything'")
        assert not reads_only("")


class TestStatementCounting:
    """``split_statements`` exists because a naive ``;`` split produced two errors that were not there."""

    def test_a_dollar_quoted_body_is_one_statement(self) -> None:
        sql = (
            "CREATE FUNCTION f() RETURNS trigger AS $$\nBEGIN\n  RAISE EXCEPTION 'no';\nEND;\n"
            "$$ LANGUAGE plpgsql;"
        )
        assert len(split_statements(sql)) == 1

    def test_a_semicolon_inside_a_literal_does_not_split(self) -> None:
        sql = "INSERT INTO t (a) VALUES ('x;y'); INSERT INTO t (a) VALUES ('z');"
        assert len(split_statements(sql)) == 2

    def test_prose_is_not_a_statement(self) -> None:
        assert split_statements("-- just prose\n/* a block */\n-- more prose\n") == []

    def test_the_real_files_count_to_a_plausible_number(self) -> None:
        for path in sorted(migrations_dir().glob("*.sql")):
            statements = split_statements(path.read_text(encoding="utf-8"))
            assert statements, f"{path.name} counted as zero statements"
            assert not any(s.startswith("--") for s in statements), f"{path.name} counted a comment"
