"""Schema fidelity: the applied SQLite schema against the portable PostgreSQL target (F-15, L-A).

`migrations/*.sql` is the PostgreSQL promotion target and `store/schema.py` is what actually runs. The
target's own header calls the second a "mirror" of the first, and before Stage 8.1 nothing checked that
claim: no test read the `.sql` files, and the runner applies `schema.MIGRATIONS`, so the target is
executed by neither the app nor the suite. It had drifted in both directions — an entire table
(`venue_instrument_mapping`) existed only in the target, and columns the app really writes
(`halt_event.cancel_working_orders`, `audit_ref` on six tables) existed only in the applied schema.

This module compares the two and fails on divergence. Three things about it are deliberate:

**The comparison is against the live post-migration schema, not the SQL text.** Parsing `schema.py`
statically also picks up migration 0004's staging tables (`dossier_0004`) and the superseded
pre-rebuild `dossier` definition, reporting divergences that do not exist once the migrations run.

**Legitimate translations are an explicit map, not a shrug.** SQLite has no `TIMESTAMPTZ`, `JSONB`,
`BOOLEAN` or `TEXT[]`, and this schema stores every numeric as `TEXT` so `Decimal` values survive
without becoming floats. Those are conventions with reasons, so they are written down where a reader
can argue with them — which is what makes the remaining differences readable as defects.

**Table-level constraints are matched as grammar, not as prefixes.** A first version of this diff
excluded lines starting with `"CHECK"` and so silently dropped the column named `checksum`, reporting a
divergence that did not exist. An audit that produces false positives gets its findings acted on, which
is worse than no audit; the keyword must be followed by a space or a paren, as SQL requires.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, SqliteAuditStore
from nexus.store.migrations import MigrationRunner
from nexus.store.operational import SqliteOperationalStore
from nexus.store.schema import MIGRATIONS, SCHEMA_MIGRATIONS_DDL

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

#: SQLite type affinity has no equivalent for several PostgreSQL types, and this schema makes two
#: further choices of its own. Each entry is a translation the two schemas are allowed to disagree
#: about; anything not listed here is a divergence and fails.
TYPE_TRANSLATIONS: dict[str, str] = {
    "TIMESTAMPTZ": "TEXT",  # SQLite has no timezone-aware type; the app writes ISO-8601 UTC strings
    "DATE": "TEXT",
    "JSONB": "TEXT",  # canonical JSON text; `dumps_canonical` is the writer
    "BOOLEAN": "INTEGER",  # SQLite stores booleans as 0/1
    "TEXT[]": "TEXT",  # arrays become JSON text; `_json_list` is the writer
    "BIGINT": "INTEGER",
    # Every numeric column in this schema is TEXT, not an oversight: SQLite's NUMERIC affinity stores a
    # REAL — a float — and the house rule is that Decimals travel as strings so no precision is lost.
    # 26 columns across 8 tables do this today, and 19 across 7 did before migration 0004 added
    # `venue_instrument_mapping`'s seven; the count is re-derived from both DDLs by the comparison in
    # this module rather than trusted from this comment, because three copies of "19 across 8" went
    # stale in exactly that way. `memory_item.confidence` is one of them and stays one.
    "NUMERIC": "TEXT",
}

#: Tables one side has and the other legitimately does not, each with the reason.
EXEMPT_TABLES: dict[str, str] = {
    # Created by `SqliteAuditStore` from `audit/log.py`, not by a migration, because the audit store is
    # constructed before migrations run — migration 0003's `requires="audit_log"` depends on that order.
    # It is compared separately in `test_audit_log_agrees_with_its_own_mirror_claim`.
    "audit_log": "created by audit/log.py, not by a migration",
}

_CONSTRAINT_PREFIXES = (
    "CONSTRAINT ",
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE (",
    "UNIQUE(",
    "CHECK (",
    "CHECK(",
)


def _postgres_ddl() -> str:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, f"no .sql files under {MIGRATIONS_DIR}"
    return "\n".join(path.read_text() for path in files)


def _column_lines(body: str) -> list[str]:
    """Column definitions only. Table-level constraints are matched as grammar, not as prefixes."""
    out = []
    for raw in body.splitlines():
        line = raw.split("--")[0].strip().rstrip(",")
        if not line:
            continue
        if any(line.upper().startswith(prefix) for prefix in _CONSTRAINT_PREFIXES):
            continue
        out.append(line)
    return out


def _declared_type(line: str) -> str:
    """The column's declared type, normalised: precision dropped, `GENERATED … IDENTITY` seen as BIGINT."""
    if "IDENTITY" in line.upper():
        return "BIGINT"
    parts = line.split()
    return parts[1].split("(")[0].upper() if len(parts) > 1 else ""


def _parse_columns(body: str) -> dict[str, dict[str, Any]]:
    cols: dict[str, dict[str, Any]] = {}
    for line in _column_lines(body):
        name = line.split()[0]
        fk = re.search(r"REFERENCES\s+(\w+)\s*\((\w+)\)", line, re.IGNORECASE)
        cols[name] = {
            "type": _declared_type(line),
            "notnull": "NOT NULL" in line.upper(),
            "fk": fk.group(1) if fk else None,
        }
    return cols


def parse_postgres(text: str) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", text, re.S):
        out[match.group(1)] = _parse_columns(match.group(2))
    return out


def live_sqlite(tmp_path: Path) -> sqlite3.Connection:
    """Build the database the way the app does: audit store first, then bookkeeping, then migrations."""
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    store = SqliteOperationalStore(path, audit=audit)
    assert store.migrations is not None
    assert store.migrations.skipped == (), [s.reason for s in store.migrations.skipped]
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_MIGRATIONS_DDL)
    MigrationRunner(conn, audit=audit).run()
    return conn


def read_sqlite(conn: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for name in names:
        cols: dict[str, dict[str, Any]] = {}
        for row in conn.execute(f"PRAGMA table_info({name})"):  # noqa: S608
            cols[str(row[1])] = {"type": str(row[2]).upper(), "notnull": bool(row[3]), "fk": None}
        for row in conn.execute(f"PRAGMA foreign_key_list({name})"):  # noqa: S608
            cols[str(row[3])]["fk"] = str(row[2])
        out[name] = cols
    return out


def _translated(pg_type: str) -> str:
    return TYPE_TRANSLATIONS.get(pg_type, pg_type)


class TestSchemaFidelity:
    """The two schemas must declare the same tables, columns, nullability and foreign keys."""

    def test_the_same_tables_are_declared(self, tmp_path: Path) -> None:
        pg = parse_postgres(_postgres_ddl())
        lt = read_sqlite(live_sqlite(tmp_path))
        for name in EXEMPT_TABLES:
            pg.pop(name, None)
            lt.pop(name, None)
        assert set(pg) - set(lt) == set(), (
            "tables declared in the PostgreSQL target but absent from the applied SQLite schema; "
            "`venue_instrument_mapping` was exactly this before migration 0004, which left the four "
            "venue mappings Stage 7.3 seeded nowhere to be projected"
        )
        assert set(lt) - set(pg) == set(), (
            "tables in the applied SQLite schema with no PostgreSQL counterpart, so a promotion would "
            "silently lose them; `halt_event.cancel_working_orders` and `audit_ref` on six tables were "
            "exactly this before the target was corrected"
        )

    def test_every_table_declares_the_same_columns(self, tmp_path: Path) -> None:
        pg = parse_postgres(_postgres_ddl())
        lt = read_sqlite(live_sqlite(tmp_path))
        problems: list[str] = []
        for name in sorted(set(pg) & set(lt) - set(EXEMPT_TABLES)):
            missing = sorted(set(pg[name]) - set(lt[name]))
            extra = sorted(set(lt[name]) - set(pg[name]))
            if missing:
                problems.append(f"{name}: only in the target -> {missing}")
            if extra:
                problems.append(f"{name}: only in SQLite -> {extra}")
        assert problems == [], "\n".join(problems)

    def test_foreign_keys_agree(self, tmp_path: Path) -> None:
        """`dossier.instrument_id` was declared in the target and absent from SQLite, so the one link a
        dossier has to the instrument it is about could not be enforced even in principle."""
        pg = parse_postgres(_postgres_ddl())
        lt = read_sqlite(live_sqlite(tmp_path))
        problems: list[str] = []
        for name in sorted(set(pg) & set(lt) - set(EXEMPT_TABLES)):
            for col in sorted(set(pg[name]) & set(lt[name])):
                if pg[name][col]["fk"] != lt[name][col]["fk"]:
                    problems.append(
                        f"{name}.{col}: target references {pg[name][col]['fk']!r}, "
                        f"SQLite references {lt[name][col]['fk']!r}"
                    )
        assert problems == [], "\n".join(problems)

    def test_nullability_agrees(self, tmp_path: Path) -> None:
        pg = parse_postgres(_postgres_ddl())
        lt = read_sqlite(live_sqlite(tmp_path))
        problems: list[str] = []
        for name in sorted(set(pg) & set(lt) - set(EXEMPT_TABLES)):
            for col in sorted(set(pg[name]) & set(lt[name])):
                if pg[name][col]["notnull"] != lt[name][col]["notnull"]:
                    problems.append(
                        f"{name}.{col}: target NOT NULL={pg[name][col]['notnull']}, "
                        f"SQLite NOT NULL={lt[name][col]['notnull']}"
                    )
        assert problems == [], "\n".join(problems)

    def test_types_agree_once_the_declared_translations_are_applied(self, tmp_path: Path) -> None:
        pg = parse_postgres(_postgres_ddl())
        lt = read_sqlite(live_sqlite(tmp_path))
        problems: list[str] = []
        for name in sorted(set(pg) & set(lt) - set(EXEMPT_TABLES)):
            for col in sorted(set(pg[name]) & set(lt[name])):
                want = _translated(pg[name][col]["type"])
                got = lt[name][col]["type"]
                if want != got:
                    problems.append(
                        f"{name}.{col}: target {pg[name][col]['type']} -> expected {want}, SQLite has {got}"
                    )
        assert problems == [], (
            "a type disagreement that is not one of the documented translations:\n" + "\n".join(problems)
        )

    def test_the_translation_map_covers_every_type_the_target_declares(self) -> None:
        """A type the target starts using must be added to the map on purpose, not absorbed silently."""
        pg = parse_postgres(_postgres_ddl())
        declared = {c["type"] for table in pg.values() for c in table.values()}
        known = set(TYPE_TRANSLATIONS) | {"TEXT", "INTEGER"}
        assert declared - known == set(), (
            f"the PostgreSQL target declares types this test has no rule for: {sorted(declared - known)}"
        )

    def test_audit_log_agrees_with_its_own_mirror_claim(self, tmp_path: Path) -> None:
        """`SqliteAuditStore` says its schema "mirrors the PostgreSQL migration so promotion is a copy,
        not a rewrite". That claim is checkable, so it is checked."""
        pg = parse_postgres(_postgres_ddl())["audit_log"]
        lt = read_sqlite(live_sqlite(tmp_path))["audit_log"]
        assert set(pg) == set(lt), (
            f"audit_log columns differ: target only {sorted(set(pg) - set(lt))}, "
            f"SQLite only {sorted(set(lt) - set(pg))}"
        )


class TestMigration0004:
    """What the rebuild actually does, including to rows that already exist."""

    def test_it_applies_after_0002_and_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        store = SqliteOperationalStore(path, audit=audit)
        report = store.migrations
        assert report is not None
        assert [item.version for item in report.applied] == [m.version for m in MIGRATIONS]
        assert "0004_memory_fidelity" in [item.version for item in report.applied]

    #: Every applied checksum, pinned. `MigrationRunner` refuses a migration whose checksum has moved,
    #: but only for a database that already applied it — a fresh checkout, a CI runner and a new host
    #: apply whatever the file says. This list is what makes "forward-only" checkable offline: adding to
    #: it is normal, changing a line already in it means history was edited.
    CHECKSUMS = {
        "0001_operational": "fcfd79161c830f40a94f474c8b67569bcdbf285eaa478f69ff9d9778a9cba528",
        "0002_memory": "5e7fafd0673e0a60711bc3c9429a7c9c9bfb2884dba48a645c56cc8957840d12",
        "0003_audit_append_only": "1e9ec5a5d9154d0af95f229aa05d4677045892eda2a39b890de2d929d40ee26b",
        "0004_memory_fidelity": "4c7368d407bb1f180a79bcce3044d8a6f97e9eb7b677cc40c35932a66ca22bb6",
        "0005_memory_beliefs": "4520e5b5e259eb4c868b70d1bfdc5ebdbac58f32d7083ea00cc4e980ac789c28",
    }

    def test_no_applied_migration_was_edited(self) -> None:
        by_version = {m.version: m.checksum for m in MIGRATIONS}
        assert by_version == self.CHECKSUMS, (
            "the set of migrations or one of their checksums changed; the runner refuses a moved "
            "checksum for any database that already applied it, so this is either an edit to history "
            "or a new migration this list has not been told about"
        )

    def test_the_runner_records_what_it_applied(self, tmp_path: Path) -> None:
        """The bookkeeping row is what makes a refusal possible at all, and the target never declared
        the table, so a PostgreSQL deploy following the `.sql` files could not have recorded anything."""
        conn = live_sqlite(tmp_path)
        rows = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
        assert rows == {m.version: m.checksum for m in MIGRATIONS}
        counts = dict(conn.execute("SELECT version, statements FROM schema_migrations").fetchall())
        assert counts["0004_memory_fidelity"] == 15, "0004 rebuilds two tables and creates one"
        assert counts["0005_memory_beliefs"] == 4, "0005 is four ADD COLUMNs and nothing else"

    def test_the_rebuild_preserves_existing_rows(self, tmp_path: Path) -> None:
        """Both tables are empty today, but a migration that is only safe on an empty table will be run
        against a non-empty one someday. Build the pre-0004 schema, write rows, then rebuild."""
        conn = sqlite3.connect(tmp_path / "rebuild.db")
        conn.executescript("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY);")
        for migration in MIGRATIONS:
            if migration.version == "0004_memory_fidelity":
                break
            conn.executescript(migration.sql)
        stamp = "2026-11-26T15:00:00+00:00"
        conn.execute(
            "INSERT INTO dossier (dossier_id, instrument_id, venue, created_at, updated_at, stance, "
            "sufficiency, summary) VALUES (?,?,?,?,?,?,?,?)",
            ("DOS-1", "INS-1", "OKX", stamp, stamp, "ABSTAIN", "INSUFFICIENT", "kept"),
        )
        conn.execute(
            "INSERT INTO memory_item (memory_id, kind, scope, subject, body, created_at, confidence) "
            "VALUES (?,?,?,?,?,?,?)",
            ("MEM-1", "OBSERVATION", "GLOBAL", "BTC", "kept", stamp, "0.25"),
        )
        conn.commit()

        before = conn.execute("SELECT count(*) FROM dossier").fetchone()[0]
        assert before == 1, "the pre-0004 schema should hold the row this test just wrote"

        sql = next(m.sql for m in MIGRATIONS if m.version == "0004_memory_fidelity")
        conn.executescript(sql)

        row = conn.execute(
            "SELECT dossier_id, instrument_id, venue, stance, sufficiency, summary FROM dossier"
        ).fetchone()
        assert row == ("DOS-1", "INS-1", "OKX", "ABSTAIN", "INSUFFICIENT", "kept")
        mem = conn.execute("SELECT memory_id, kind, body, confidence FROM memory_item").fetchone()
        assert mem == ("MEM-1", "OBSERVATION", "kept", "0.25")
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(dossier)")}
        assert "ix_dossier_created" in indexes, "the rebuild must recreate the index it dropped"


class TestMigration0005:
    """F-18's three columns and `evidence_ref.contradicts`, added without rebuilding anything.

    0004 needed a create-copy-drop-rename because SQLite refuses `ALTER COLUMN ... TYPE` and
    `ADD CONSTRAINT`; 0005 needs neither, because all four of its changes are `ADD COLUMN`, which
    `docs/15` §5.3 executed rather than assumed. What is asserted here is therefore not only that the
    columns arrive but that they arrive *additively* — an existing row keeps every value it had — and
    that the columns which were **not** ruled into this batch are genuinely absent.
    """

    def test_it_applies_after_0004_and_is_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        store = SqliteOperationalStore(path, audit=audit)
        report = store.migrations
        assert report is not None
        assert [item.version for item in report.applied] == [m.version for m in MIGRATIONS]
        assert "0005_memory_beliefs" in [item.version for item in report.applied]
        assert store.migrations.skipped == (), [s.reason for s in store.migrations.skipped]
        store.close()

    def test_it_adds_exactly_the_columns_the_ruling_named(self, tmp_path: Path) -> None:
        """Three on `memory_item`, one on `evidence_ref`, and nothing else.

        D-051's ruling 2 named the cheap half as three `ADD COLUMN`s on `memory_item` (`valid_from`,
        `valid_until`, `change_conditions`) plus `contradicts` on `evidence_ref`, and D-053's ruling 4
        repeated it verbatim. `docs/15` §5.3 also lists `expires_at` as cheap and F-18's second gap asks
        for one, but it is not one of the three, so it is not here — and this assertion is what makes its
        absence a decision somebody can argue with rather than an oversight nobody noticed.
        """
        conn = live_sqlite(tmp_path)
        memory = {row[1] for row in conn.execute("PRAGMA table_info(memory_item)")}
        evidence = {row[1] for row in conn.execute("PRAGMA table_info(evidence_ref)")}
        assert {"valid_from", "valid_until", "change_conditions"} <= memory
        assert "contradicts" in evidence

        # F-18's second gap stays open: no expiry column, and `valid_until` is not one. It says until when
        # a claim holds in the world; an expiry says when this system should stop serving the row, which is
        # what `docs/10` §3.1's "expiring TTLs" asks for.
        assert not {"expires_at", "expires_on", "ttl", "ttl_seconds", "valid_for_seconds"} & memory
        # F-24: a band is an interval on the confidence axis, so it is two columns, and neither was ruled
        # into this batch. Pinning the absence is what stops a later reader inferring that the three new
        # columns delivered "confidence as a band" — they are on the time axis.
        assert (
            not {
                "confidence_low",
                "confidence_high",
                "confidence_min",
                "confidence_max",
                "confidence_band",
            }
            & memory
        )

    def test_it_is_additive_and_an_existing_row_keeps_every_value(self, tmp_path: Path) -> None:
        """Build the pre-0005 schema, write a row, then apply 0005 on top of it.

        There are no such rows today — nothing had ever written to this table — but 0004's rebuild test
        makes the same argument and it holds here too: a migration that is only safe on an empty table is
        a migration that will be run against a non-empty one someday.
        """
        conn = sqlite3.connect(tmp_path / "additive.db")
        conn.executescript("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY);")
        for migration in MIGRATIONS:
            if migration.version == "0005_memory_beliefs":
                break
            conn.executescript(migration.sql)
        stamp = "2026-11-27T15:00:00+00:00"
        conn.execute(
            "INSERT INTO memory_item (memory_id, kind, scope, subject, body, created_at, confidence, "
            "cited_by) VALUES (?,?,?,?,?,?,?,?)",
            ("MEM-1", "BELIEF", "GLOBAL", "BTC", "kept", stamp, "0.25", '["DEC-1"]'),
        )
        conn.execute(
            "INSERT INTO evidence_ref (evidence_id, source, kind, observed_at, retrieved_at) "
            "VALUES (?,?,?,?,?)",
            ("EV-1", "okx", "DATA", stamp, stamp),
        )
        conn.commit()

        sql = next(m.sql for m in MIGRATIONS if m.version == "0005_memory_beliefs")
        conn.executescript(sql)

        row = conn.execute(
            "SELECT memory_id, kind, scope, subject, body, created_at, confidence, cited_by, valid_from, "
            "valid_until, change_conditions FROM memory_item"
        ).fetchone()
        assert row == ("MEM-1", "BELIEF", "GLOBAL", "BTC", "kept", stamp, "0.25", '["DEC-1"]', None, None, "")
        ev = conn.execute("SELECT evidence_id, source, contradicts FROM evidence_ref").fetchone()
        assert ev == ("EV-1", "okx", None)
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(memory_item)")}
        assert {"ix_memory_kind", "ix_memory_created"} <= indexes, "ADD COLUMN must not drop an index"

    def test_the_new_foreign_key_is_declared(self, tmp_path: Path) -> None:
        """Declared, and still not enforced — `PRAGMA foreign_keys` is off, and the writer refuses instead.

        A self-referencing foreign key added by `ADD COLUMN` is the shape `docs/15` §5.3 executed, and
        `PRAGMA foreign_key_list` is the only thing that reports it, so this is where the claim is checked
        rather than in prose.
        """
        conn = live_sqlite(tmp_path)
        links = {row[3]: (row[2], row[4]) for row in conn.execute("PRAGMA foreign_key_list(evidence_ref)")}
        # Both of this table's foreign keys, and the reason the second is asserted beside the first: they
        # are declared identically and treated differently. A dangling `contradicts` is refused by
        # `record_evidence`; a dangling `dossier_id` is refused by nothing, which is F-25 (`docs/15` §12) —
        # an asymmetry this batch records rather than fixes, because changing an approved writer's contract
        # is not what D-053's ruling 4 authorised.
        assert links == {
            "contradicts": ("evidence_ref", "evidence_id"),
            "dossier_id": ("dossier", "dossier_id"),
        }, links
        conn.execute(
            "INSERT INTO evidence_ref (evidence_id, source, kind, observed_at, retrieved_at, contradicts) "
            "VALUES ('EV-1','okx','DATA','2026-11-27T15:00:00+00:00','2026-11-27T15:00:00+00:00','EV-NOPE')"
        )
        conn.commit()
        assert conn.execute("SELECT contradicts FROM evidence_ref").fetchone()[0] == "EV-NOPE", (
            "SQLite accepted a dangling parent, which is why the refusal lives in record_evidence and not "
            "here: a foreign key that is declared and not enforced protects nobody on its own"
        )

    def test_0004s_check_on_confidence_survives_it(self, tmp_path: Path) -> None:
        """`ADD COLUMN` does not rebuild, so an earlier migration's constraint is still there afterwards.

        Worth pinning because the alternative would have been a rebuild, and a rebuild that forgot to
        re-declare the CHECK would have removed the only thing making `confidence` numeric — silently, and
        in the migration whose stated purpose was to add columns.
        """
        conn = live_sqlite(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO memory_item (memory_id, body, created_at, confidence) "
                "VALUES ('MEM-JUNK','b','2026-11-27T15:00:00+00:00','not-a-number')"
            )
        conn.execute(
            "INSERT INTO memory_item (memory_id, body, created_at, confidence, valid_from, "
            "change_conditions) VALUES ('MEM-OK','b','2026-11-27T15:00:00+00:00','0.25',"
            "'2026-11-27T15:00:00+00:00','a funding flip')"
        )
        conn.commit()

    def test_the_target_declares_the_same_four_and_not_as_alterations(self) -> None:
        """The PostgreSQL target states the end state and SQLite walks to it (R-1: a promotion is a copy).

        That is why the four columns are inside `0002_memory.sql`'s `CREATE TABLE`s and there is no
        `0005_*.sql` full of `ALTER`s: `parse_postgres` reads table declarations, and a promotion follows
        the files, so the target has to describe the schema a fresh Postgres should end up with. 0004 set
        the precedent — its shape is declared in the target too, and only SQLite needed the rebuild.
        """
        pg = parse_postgres(_postgres_ddl())
        assert {"valid_from", "valid_until", "change_conditions"} <= set(pg["memory_item"])
        assert "contradicts" in pg["evidence_ref"]
        assert pg["memory_item"]["valid_from"]["type"] == "TIMESTAMPTZ"
        assert pg["memory_item"]["valid_until"]["type"] == "TIMESTAMPTZ"
        assert pg["memory_item"]["change_conditions"]["notnull"] is True
        assert pg["evidence_ref"]["contradicts"]["fk"] == "evidence_ref"
        assert pg["evidence_ref"]["contradicts"]["notnull"] is False
        altering = [
            path.name
            for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
            if "ALTER TABLE memory_item" in path.read_text()
        ]
        assert altering == [], altering


class TestConfidenceConstraint:
    """`memory_item.confidence` stays TEXT and gains a CHECK. Both halves are deliberate."""

    @staticmethod
    def _conn(tmp_path: Path) -> sqlite3.Connection:
        return live_sqlite(tmp_path)

    @pytest.mark.parametrize("value", ["0.5", "0.12345", "1", "0", "0.00000", "1e-9", "0.00001"])
    def test_a_numeric_confidence_is_accepted(self, tmp_path: Path, value: str) -> None:
        conn = self._conn(tmp_path)
        conn.execute(
            "INSERT INTO memory_item (memory_id, body, created_at, confidence) VALUES (?,?,?,?)",
            (f"M-{value}", "b", "2026-11-26T15:00:00+00:00", value),
        )

    @pytest.mark.parametrize("value", ["not-a-number", "", "abc123", "high"])
    def test_junk_is_rejected(self, tmp_path: Path, value: str) -> None:
        """Before 0004 all four were accepted, and `ORDER BY confidence` then put `'99999999'` above
        `'0.5'` because the column sorted lexicographically."""
        conn = self._conn(tmp_path)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            conn.execute(
                "INSERT INTO memory_item (memory_id, body, created_at, confidence) VALUES (?,?,?,?)",
                (f"M-{value or 'empty'}", "b", "2026-11-26T15:00:00+00:00", value),
            )

    def test_null_is_allowed(self, tmp_path: Path) -> None:
        """An unquantified belief is honest; a fabricated number is not. NULL is the record of the first."""
        conn = self._conn(tmp_path)
        conn.execute(
            "INSERT INTO memory_item (memory_id, body, created_at, confidence) VALUES (?,?,?,NULL)",
            ("M-unknown", "b", "2026-11-26T15:00:00+00:00"),
        )

    @staticmethod
    def _orderings(conn: sqlite3.Connection, values: tuple[str, ...]) -> tuple[list[str], list[str]]:
        stamp = "2026-11-26T15:00:00+00:00"
        conn.execute("DELETE FROM memory_item")
        for value in values:
            conn.execute(
                "INSERT INTO memory_item (memory_id, body, created_at, confidence) VALUES (?,?,?,?)",
                (f"M-{value}", "b", stamp, value),
            )
        plain = [r[0] for r in conn.execute("SELECT confidence FROM memory_item ORDER BY confidence")]
        cast = [
            r[0] for r in conn.execute("SELECT confidence FROM memory_item ORDER BY CAST(confidence AS REAL)")
        ]
        return plain, cast

    def test_ordering_by_cast_is_numeric(self, tmp_path: Path) -> None:
        conn = self._conn(tmp_path)
        plain, cast = self._orderings(conn, ("0.5", "0.05", "0.9", "0.12345"))
        assert cast == ["0.05", "0.12345", "0.5", "0.9"]
        assert plain == cast

    def test_the_two_orderings_agree_inside_the_range_a_probability_can_occupy(self, tmp_path: Path) -> None:
        """Measured, not assumed — and it corrects a claim this batch first wrote down. For values in
        [0,1), TEXT ordering and ``CAST`` ordering **coincide**, including the prefix tie ``"0.5"``
        against ``"0.50"``. An earlier draft of this batch asserted that a bare ``ORDER BY confidence``
        is lexicographic and therefore wrong; the probe says that is false for the only range a
        confidence value may legitimately occupy. The two diverge at ten and above — which the CHECK
        permits, and which is what the next test records."""
        conn = self._conn(tmp_path)
        assert self._orderings(conn, ("0.5", "0.50", "0.45")) == (
            ["0.45", "0.5", "0.50"],
            ["0.45", "0.5", "0.50"],
        )
        plain, cast = self._orderings(conn, ("9", "12", "1"))
        assert plain == ["1", "12", "9"], "TEXT ordering, which is not numeric"
        assert cast == ["1", "9", "12"], "and the ordering a reader of confidence actually wants"

    @pytest.mark.parametrize("value", ["12", "-0.5", "99999999", "1.0", "0.5abc", "1e-9"])
    def test_the_check_does_not_bound_the_range_and_that_is_recorded(
        self, tmp_path: Path, value: str
    ) -> None:
        """The CHECK asks whether the value casts to a nonzero number, not whether it is a probability.
        So ``confidence = '99999999'`` and ``'-0.5'`` are accepted by the database, and ``'0.5abc'``
        casts to 0.5. Pinned as a limitation rather than quietly fixed: bounding the range is the
        stage-10 writer's job, and a constraint that pretended to bound it would be worse than one that
        says it does not."""
        conn = self._conn(tmp_path)
        conn.execute(
            "INSERT INTO memory_item (memory_id, body, created_at, confidence) VALUES (?,?,?,?)",
            (f"M-{value}", "b", "2026-11-26T15:00:00+00:00", value),
        )
        assert conn.execute("SELECT count(*) FROM memory_item").fetchone()[0] == 1

    def test_the_column_stays_text_on_purpose(self, tmp_path: Path) -> None:
        """Pinned so the choice is argued rather than discovered. The PostgreSQL target says
        NUMERIC(6,5); SQLite's NUMERIC affinity would store a REAL, i.e. a float, and all 26 numeric
        columns across 8 tables in this schema are TEXT precisely so Decimals survive as strings (19
        across 7 before 0004 added `venue_instrument_mapping`). Changing this one column would make it
        the only float-backed numeric column in the applied schema.
        """
        conn = self._conn(tmp_path)
        kinds = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(memory_item)")}
        assert kinds["confidence"] == "TEXT"
        # and the same convention holds for the numeric columns the operational tables carry
        orders = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(orders)")}
        assert orders["average_price"] == "TEXT"


class TestDossierForeignKey:
    """Restored by 0004. Declared is not the same as enforced, and both halves are asserted."""

    def test_it_is_declared(self, tmp_path: Path) -> None:
        conn = live_sqlite(tmp_path)
        fks = list(conn.execute("PRAGMA foreign_key_list(dossier)"))
        assert [(r[2], r[3], r[4]) for r in fks] == [("instrument", "instrument_id", "instrument_id")]

    def test_it_is_enforced_when_the_pragma_is_on(self, tmp_path: Path) -> None:
        """The point of declaring it: the constraint becomes enforceable the moment the pragma is set,
        which it was not before 0004 when the column carried no REFERENCES at all."""
        conn = sqlite3.connect(tmp_path / "pragma.db", isolation_level=None)
        conn.executescript("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY);")
        for migration in MIGRATIONS:
            conn.executescript(migration.sql)
        conn.execute("PRAGMA foreign_keys = ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        stamp = "2026-11-26T15:00:00+00:00"
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            conn.execute(
                "INSERT INTO dossier (dossier_id, instrument_id, created_at, updated_at) "
                "VALUES ('DOS-GHOST', 'INS-NEVER-EXISTED', ?, ?)",
                (stamp, stamp),
            )
        conn.execute(
            "INSERT INTO instrument (instrument_id, canonical_symbol, created_at, updated_at) "
            "VALUES ('INS-1', 'BTC/USDT', ?, ?)",
            (stamp, stamp),
        )
        conn.execute(
            "INSERT INTO dossier (dossier_id, instrument_id, created_at, updated_at) "
            "VALUES ('DOS-1', 'INS-1', ?, ?)",
            (stamp, stamp),
        )

    def test_it_is_not_enforced_by_default_and_that_is_recorded(self, tmp_path: Path) -> None:
        """`docs/13` §2.5: the pragma is off because boot recovery re-projects in chain order, which is
        not always parent-first, and a hard FK failure mid-recovery would be worse than the
        inconsistency it prevents. This test pins that the limitation is real rather than assumed —
        and that 0004 moved `dossier.instrument_id` inside it instead of leaving it outside."""
        conn = live_sqlite(tmp_path)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        conn.execute(
            "INSERT INTO dossier (dossier_id, instrument_id, created_at, updated_at) "
            "VALUES ('DOS-GHOST', 'INS-NEVER-EXISTED', ?, ?)",
            ("2026-11-26T15:00:00+00:00", "2026-11-26T15:00:00+00:00"),
        )
