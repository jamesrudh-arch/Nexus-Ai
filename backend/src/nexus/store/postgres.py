"""PostgreSQL driver bindings for the operational and audit stores (F-31).

What this module is, and what it is not
---------------------------------------
It is the driver half of a promotion that ``store/__init__.py`` has described since Stage 6 — "the
``OperationalStore`` Protocol is the seam R-1 kept: a PostgreSQL implementation under trigger
conditions T-1…T-4 satisfies the same surface and nothing above it changes" — and it is what makes
that sentence true rather than aspirational. It contains no SQL of its own beyond the bookkeeping
rows: every statement is the one ``SqlOperationalStore`` already writes, translated at the driver
boundary by :mod:`nexus.store.pg`.

It is **not** a second system of record. L-3 forbids two of those for one data class, so a process
runs exactly one driver, chosen by ``NEXUS_DATABASE_URL``, and R-1's declaration that SQLite is the
single-node system of record is unchanged for every deployment that keeps the default. What this
adds is the ability to point the same store at a server when a trigger fires — T-4, leaving the
single VM, being the one a managed host satisfies.

One structural difference, stated because it is real
----------------------------------------------------
SQLite keeps the audit chain and the operational state in **two files**, and the audit store is
constructed before migrations run because ``0003_audit_append_only`` requires ``audit_log`` to
exist. PostgreSQL has one database, so both stores open the same schema and the ordering
constraint dissolves: whichever store opens first applies ``migrations/*.sql``, and the other finds
it already there. :func:`bootstrap_schema` is idempotent for exactly that reason, and
``test_postgres_store.py`` opens the two stores in both orders to prove it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from nexus.audit.log import SqliteAuditStore
from nexus.core.ids import iso_utc, utc_now
from nexus.store.migrations import AppliedMigration, MigrationReport
from nexus.store.operational import SqlOperationalStore
from nexus.store.pg import PostgresConnection, public_dsn

__all__ = [
    "PostgresAuditStore",
    "PostgresOperationalStore",
    "bootstrap_schema",
    "migrations_dir",
    "split_statements",
]


def migrations_dir(explicit: str | Path | None = None) -> Path:
    """Where the portable DDL lives.

    Resolved from this file's own position rather than the working directory, because the two
    deployments that matter put it in different places relative to ``cwd``: ``backend/migrations``
    in a checkout, and ``/app/migrations`` in the image, where ``Dockerfile:104`` copies it. A
    relative path would make the schema reachable from one and not the other.
    """
    if explicit is not None:
        return Path(explicit)
    return Path(__file__).resolve().parents[3] / "migrations"


def split_statements(sql: str) -> list[str]:
    """The top-level statements in a script, for counting them honestly.

    A ``sql.split(";")`` is wrong here and was wrong when it was first tried: ``0001_core.sql``
    carries a dollar-quoted trigger body, ``$$ ... $$``, whose own semicolons cut the function in
    half and produced two syntax errors that were artifacts of the split rather than of the SQL.
    This tracks single-quoted literals, dollar-quote tags, ``--`` line comments and ``/* */`` block
    comments, so a ``;`` only ends a statement where it actually does.
    """
    statements: list[str] = []
    current: list[str] = []
    i, n = 0, len(sql)
    dollar: str | None = None
    while i < n:
        char = sql[i]
        if dollar is not None:
            current.append(char)
            if sql.startswith(dollar, i):
                current.append(sql[i + 1 : i + len(dollar)])
                i += len(dollar)
                dollar = None
            else:
                i += 1
            continue
        if char == "'":
            current.append(char)
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        current.append("''")
                        i += 2
                        continue
                    current.append("'")
                    i += 1
                    break
                current.append(sql[i])
                i += 1
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z_]*\$", sql[i:])
            if match:
                dollar = match.group(0)
                current.append(dollar)
                i += len(dollar)
                continue
        if char == "-" and sql.startswith("--", i):
            newline = sql.find("\n", i)
            i = n if newline < 0 else newline
            continue
        if char == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if char == ";":
            body = "".join(current).strip()
            if body:
                statements.append(body)
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _describe(sql: str, fallback: str) -> str:
    """The first prose line of a migration file, which is what its own header calls itself."""
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            text = stripped.lstrip("-").strip()
            if text:
                return text[:120]
    return fallback


def bootstrap_schema(
    conn: PostgresConnection,
    directory: str | Path | None = None,
    *,
    audit: Any = None,
) -> MigrationReport:
    """Apply ``migrations/*.sql`` and record what that took, idempotently.

    The files are the portable target R-1 kept and ``Dockerfile:104`` ships, so this is the path
    that finally executes them — which is why six missing commas in ``0001_core.sql`` survived to
    F-31: nothing in the repository had ever sent that file to a PostgreSQL server, and
    ``test_schema_fidelity.py`` parses it with a regex instead.

    Versions are the file stems and checksums are of the file bytes. They are deliberately *not*
    the six versions ``store/schema.py`` declares: those checksum SQLite DDL, and recording them
    here would claim a PostgreSQL server had applied SQL it was never sent.
    """
    root = migrations_dir(directory)
    files = sorted(root.glob("*.sql"))
    if not files:
        raise FileNotFoundError(
            f"no portable DDL under {root}; the image is built without migrations/ or the checkout "
            "is incomplete. Refusing to open a store with no schema rather than creating an empty "
            "database that reports healthy."
        )

    recorded = _recorded_versions(conn)
    pending = [f for f in files if f.stem not in recorded]
    applied: list[AppliedMigration] = []
    for path in pending:
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        row = AppliedMigration(
            version=path.stem,
            checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            description=_describe(sql, path.stem),
            statements=len(split_statements(sql)),
            applied_at=iso_utc(utc_now()),
        )
        conn.execute(
            "INSERT INTO schema_migrations (version, checksum, description, statements, applied_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (row.version, row.checksum, row.description, row.statements, row.applied_at),
        )
        conn.commit()
        applied.append(row)
        if audit is not None:
            # Committed before the event is written, the same order MigrationRunner uses: a schema
            # that exists but is unrecorded is recoverable, an event claiming one that does not is
            # not.
            audit.record("migration.applied", row.to_dict())
    return MigrationReport(applied=tuple(applied), already_applied=tuple(sorted(recorded)))


def _recorded_versions(conn: PostgresConnection) -> frozenset[str]:
    """Versions already in ``schema_migrations``, or nothing if the table is not there yet.

    Asked through ``information_schema`` rather than by catching a failed query, because on a
    non-autocommit connection a failed statement aborts the transaction and every statement after
    it fails until a rollback — the cascade that made a first attempt at this audit report fourteen
    errors where there was one.
    """
    exists = conn.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'schema_migrations'"
    ).fetchone()
    if not exists or not int(exists[0]):
        return frozenset()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return frozenset(str(row[0]) for row in rows)


class PostgresOperationalStore(SqlOperationalStore):
    """The operational store against a PostgreSQL server.

    Three overrides, and only three: nothing here re-states a query, a deserialiser or a refusal.
    """

    def __init__(
        self,
        dsn: str,
        *,
        audit: Any = None,
        migrate: bool = True,
        migrations_directory: str | Path | None = None,
    ) -> None:
        self._migrations_directory = migrations_directory
        self._audit_for_migrations = audit
        super().__init__(dsn, audit=audit, migrate=migrate)

    engine = "postgresql"

    @property
    def path(self) -> str:
        """The server this store talks to, without the credentials in its DSN.

        The base returns ``self._path`` unchanged, which is right for a filesystem path and wrong for
        a DSN: ``/v1/status`` publishes this value on an unauthenticated endpoint, and every managed
        PostgreSQL hands out a URL with the password in it.
        """
        return public_dsn(str(self._path))

    def _prepare_storage(self) -> None:
        """Nothing to create: the server owns its own data directory."""

    def _open_connection(self) -> Any:
        return PostgresConnection(self._path)

    def _apply_migrations(self, audit: Any) -> MigrationReport:
        return bootstrap_schema(
            self._conn, self._migrations_directory, audit=audit or self._audit_for_migrations
        )


class PostgresAuditStore(SqliteAuditStore):
    """The audit chain against the same PostgreSQL server the operational store uses.

    ``audit_log``, its ``audit_log_is_append_only`` function and both triggers are declared in
    ``migrations/0001_core.sql``, not here, because PostgreSQL binds a trigger to its table and
    that file is the portable target. So the SQLite ``_SCHEMA`` this class inherits is deliberately
    not applied: it is SQLite DDL, and sending it to a server would fail on the first statement.
    """

    def __init__(self, dsn: str, *, migrations_directory: str | Path | None = None) -> None:
        self._migrations_directory = migrations_directory
        super().__init__(dsn)

    def _normalise_path(self, value: str | Path) -> Any:
        """Keep the DSN a string.

        ``Path("postgresql://host/db")`` collapses the double slash and hands back
        ``postgresql:/host/db``, which is not a connection string anyone can use.
        """
        return str(value)

    def _prepare_storage(self) -> None:
        """Nothing to create: the server owns its own data directory."""

    def _open_connection(self) -> Any:
        conn = PostgresConnection(str(self._path))
        # Whichever store opens first brings the schema up; the other finds it already there.
        bootstrap_schema(conn, self._migrations_directory)
        return conn

    def _apply_schema(self) -> None:
        """Already applied by :meth:`_open_connection`, from the portable target."""
