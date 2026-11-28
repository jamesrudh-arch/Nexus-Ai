"""Migration runner: idempotent, forward-only, audited (Stage 6, law L-4).

The runner has three refusals and one honest skip. Each is asserted here, because a migration
system that repairs itself silently is a migration system nobody can reason about after the fact.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from nexus.audit.log import AuditLog, InMemoryAuditStore, SqliteAuditStore
from nexus.store.migrations import MigrationError, MigrationRunner
from nexus.store.operational import SqliteOperationalStore
from nexus.store.schema import MIGRATIONS, Migration


def _durable(tmp_path: Path) -> tuple[AuditLog, SqliteOperationalStore]:
    """Audit store first, then the operational store — the ordering migration 0003 requires."""
    path = tmp_path / "nexus.db"
    audit = AuditLog(SqliteAuditStore(path))
    return audit, SqliteOperationalStore(path, audit=audit)


class TestMigrationApplication:
    def test_applies_every_migration_in_order(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        report = store.migrations
        assert report is not None
        assert [item.version for item in report.applied] == [item.version for item in MIGRATIONS]
        assert report.changed is True
        assert report.skipped == ()

    def test_rerun_is_a_no_op(self, tmp_path: Path) -> None:
        """Idempotence: a restart during boot must not half-apply a schema."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        first = SqliteOperationalStore(path, audit=audit)
        assert first.migrations is not None and first.migrations.changed
        first.close()

        audit2 = AuditLog(SqliteAuditStore(path))
        second = SqliteOperationalStore(path, audit=audit2)
        report = second.migrations
        assert report is not None
        assert report.changed is False
        assert report.applied == ()
        assert sorted(report.already_applied) == sorted(item.version for item in MIGRATIONS)

    def test_each_application_is_audited_with_its_checksum(self, tmp_path: Path) -> None:
        """Law L-4: 'when did the schema change' is answerable from the chain."""
        audit, store = _durable(tmp_path)
        applied = [record for record in audit.records() if record.event_type == "migration.applied"]
        assert [record.payload["version"] for record in applied] == [item.version for item in MIGRATIONS]
        for record, migration in zip(applied, MIGRATIONS, strict=True):
            assert record.payload["checksum"] == migration.checksum
            assert record.payload["statements"] == migration.statements
        assert store.counts()["orders"] == 0  # tables exist and are queryable

    def test_append_only_triggers_are_enforced_inside_sqlite(self, tmp_path: Path) -> None:
        """Migration 0003 mirrors the PostgreSQL triggers: no UPDATE, no DELETE on the chain."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        SqliteOperationalStore(path, audit=audit)
        audit.record("test.event", {"a": 1})

        conn = sqlite3.connect(path)
        try:
            with pytest.raises(sqlite3.Error, match="append-only"):
                conn.execute("UPDATE audit_log SET actor = 'tampered'")
            with pytest.raises(sqlite3.Error, match="append-only"):
                conn.execute("DELETE FROM audit_log WHERE seq = 1")
        finally:
            conn.close()
        assert audit.verify() == []


class TestMigrationRefusals:
    def test_changed_checksum_is_refused(self, tmp_path: Path) -> None:
        """An applied migration is immutable; the fix is a new migration, not an edited one."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        SqliteOperationalStore(path, audit=audit).close()

        edited = Migration(
            version=MIGRATIONS[0].version,
            description=MIGRATIONS[0].description,
            sql=MIGRATIONS[0].sql + "\n-- edited after the fact\n",
        )
        conn = sqlite3.connect(path)
        try:
            with pytest.raises(MigrationError, match="changed after it was applied"):
                MigrationRunner(conn, migrations=(edited, *MIGRATIONS[1:])).run()
        finally:
            conn.close()

    def test_removed_migration_is_refused(self, tmp_path: Path) -> None:
        """A schema this build cannot account for is a refusal, not a shrug."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        SqliteOperationalStore(path, audit=audit).close()

        conn = sqlite3.connect(path)
        try:
            with pytest.raises(MigrationError, match="no longer exists in code"):
                MigrationRunner(conn, migrations=()).run()
        finally:
            conn.close()

    def test_gap_in_the_sequence_is_refused(self, tmp_path: Path) -> None:
        """Forward-only: a pending migration under an applied one means the sequence has a hole."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        first = SqliteOperationalStore(path, audit=audit, migrate=False)
        runner = MigrationRunner(first._conn, audit=audit, migrations=(MIGRATIONS[0], MIGRATIONS[2]))
        runner.run()  # applies 0001 and 0003, leaving 0002 out

        with pytest.raises(MigrationError, match="sequence has a hole"):
            MigrationRunner(first._conn, audit=audit, migrations=MIGRATIONS).run()

    def test_missing_audit_table_gives_an_explicit_refusal(self, tmp_path: Path) -> None:
        """Wrong ordering must say what to do, not leak a bare sqlite3 error.

        A migration that declares ``requires`` is skipped and reported instead; this is the case
        where someone wrote SQL against ``audit_log`` and forgot to declare the dependency.
        """
        undeclared = Migration(
            version="9999_needs_audit",
            description="probe: touches audit_log without declaring the requirement",
            sql="CREATE INDEX IF NOT EXISTS ix_probe ON audit_log (seq);",
        )
        conn = sqlite3.connect(tmp_path / "bare.db")
        try:
            with pytest.raises(MigrationError, match="audit store to exist first"):
                MigrationRunner(conn, migrations=(undeclared,)).run()
        finally:
            conn.close()

    def test_a_skipped_migration_is_not_treated_as_a_hole(self, tmp_path: Path) -> None:
        """Reopening a store with no audit_log present must not look like a broken sequence."""
        path = tmp_path / "nexus.db"
        first = SqliteOperationalStore(path)  # no audit store: 0003 has nothing to protect
        report = first.migrations
        assert report is not None
        assert [item.version for item in report.skipped] == ["0003_audit_append_only"]
        first.close()

        second = SqliteOperationalStore(path)
        report2 = second.migrations
        assert report2 is not None
        assert report2.applied == ()
        assert [item.version for item in report2.skipped] == ["0003_audit_append_only"]

    def test_a_memory_migration_defers_when_memory_item_is_absent(self, tmp_path: Path) -> None:
        """``requires="memory_item"`` is what makes 0006 a deferral rather than a fatal boot.

        The three memory migrations (0002's tables, 0005's beliefs, 0006's expiry) each declare
        ``requires="memory_item"``, and nothing in the normal path exercises it, because 0002 creates the
        table before any of them run. So the branch is built here: a database whose ``memory_item`` has
        been dropped, with 0006 still pending, must **skip and report** — F-20's rule that a deferral and
        a bypass look identical in ``schema_migrations`` unless the skip is remembered.

        Without ``requires`` this boot raises ``MigrationError`` instead: ``ALTER TABLE`` against a table
        that is not there. Both halves are asserted below, and the pair is what makes the declared
        dependency observable at all. A tamper run for Stage 8.7 found it was not: dropping ``requires``
        from 0006 left all 1,427 tests green, because no test put the runner on a database where the
        difference would show.
        """
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        first = SqliteOperationalStore(path, audit=audit)
        report = first.migrations
        assert report is not None
        assert [item.version for item in report.applied] == [m.version for m in MIGRATIONS]
        first.close()

        conn = sqlite3.connect(path, isolation_level=None)
        conn.execute("DROP TABLE memory_item")
        # Leave 0006 pending again, so this boot has to make a decision about it. 0001-0005 stay applied,
        # which also keeps the sequence free of a hole.
        conn.execute("DELETE FROM schema_migrations WHERE version = '0006_memory_expiry'")
        conn.close()

        reopened = SqliteOperationalStore(path, audit=audit)
        report2 = reopened.migrations
        assert report2 is not None
        assert [item.version for item in report2.applied] == []
        skipped = {item.version: item.reason for item in report2.skipped}
        assert "0006_memory_expiry" in skipped, skipped
        assert "memory_item" in skipped["0006_memory_expiry"], skipped
        reopened.close()

        # The mirror: the same ALTER with the dependency undeclared is fatal, not deferred.
        undeclared = Migration(
            version="9998_needs_memory",
            description="probe: alters memory_item without declaring the requirement",
            sql="ALTER TABLE memory_item ADD COLUMN probe TEXT;",
        )
        probe = sqlite3.connect(tmp_path / "bare.db")
        try:
            with pytest.raises(MigrationError, match="no such table"):
                MigrationRunner(probe, migrations=(undeclared,)).run()
        finally:
            probe.close()

    def test_a_skipped_migration_applies_once_its_table_exists(self, tmp_path: Path) -> None:
        """Skipping is deferral, not abandonment: the durable boot still gets its triggers."""
        path = tmp_path / "nexus.db"
        first = SqliteOperationalStore(path)
        first.close()

        audit = AuditLog(SqliteAuditStore(path))  # now audit_log exists in the same file
        second = SqliteOperationalStore(path, audit=audit)
        report = second.migrations
        assert report is not None
        assert [item.version for item in report.applied] == ["0003_audit_append_only"]
        assert report.skipped == ()


class TestMigrationSkip:
    def test_migration_requiring_an_absent_table_is_skipped_and_reported(self) -> None:
        """An ephemeral audit backend has no audit_log to protect.

        The skip is reported and — crucially — not recorded as applied, so a later boot against a
        durable store still applies it.
        """
        audit = AuditLog(InMemoryAuditStore())
        store = SqliteOperationalStore(":memory:", audit=audit)
        report = store.migrations
        assert report is not None
        # Derived, not written out: this assertion is about 0003 being deferred, and a hardcoded list
        # breaks every time a migration is added behind it.
        assert [item.version for item in report.applied] == [
            item.version for item in MIGRATIONS if item.version != "0003_audit_append_only"
        ]
        assert len(report.skipped) == 1
        assert report.skipped[0].version == "0003_audit_append_only"
        assert "audit_log" in report.skipped[0].reason

        again = MigrationRunner(store._conn, audit=audit, migrations=MIGRATIONS).run()
        assert again.applied == ()
        assert [item.version for item in again.skipped] == ["0003_audit_append_only"]

    def test_a_deferral_is_recorded_so_it_can_be_told_from_a_bypass(self) -> None:
        """A version absent from ``schema_migrations`` is either waiting for a table this database does
        not have, or was moved past by mistake. Only the second is fatal, and telling them apart needs
        the first to be written down — which is what ``schema_migration_skips`` is for."""
        audit = AuditLog(InMemoryAuditStore())
        store = SqliteOperationalStore(":memory:", audit=audit)
        rows = store._conn.execute("SELECT version, reason FROM schema_migration_skips").fetchall()
        assert [str(row[0]) for row in rows] == ["0003_audit_append_only"]
        assert "audit_log" in str(rows[0][1])
        assert "0003_audit_append_only" not in {item.version for item in store.migrations.applied}

        # and a second ephemeral boot re-records the same deferral rather than stacking it
        MigrationRunner(store._conn, audit=audit, migrations=MIGRATIONS).run()
        assert store._conn.execute("SELECT count(*) FROM schema_migration_skips").fetchone()[0] == 1
        store.close()

    def test_a_deferred_migration_behind_an_applied_one_is_not_a_hole(self, tmp_path: Path) -> None:
        """The scenario migration 0004 created: a migration now sits *behind* the one that can be
        skipped, so an ephemeral boot applies 0004 while 0003 waits. A later durable boot must then be
        able to apply 0003 rather than refuse to start — deferral, not abandonment."""
        path = tmp_path / "nexus.db"
        first = SqliteOperationalStore(path)
        assert [item.version for item in first.migrations.skipped] == ["0003_audit_append_only"]
        assert "0004_memory_fidelity" in [item.version for item in first.migrations.applied]
        first.close()

        audit = AuditLog(SqliteAuditStore(path))
        second = SqliteOperationalStore(path, audit=audit)
        report = second.migrations
        assert [item.version for item in report.applied] == ["0003_audit_append_only"]
        assert report.skipped == ()
        recorded = {item.version for item in MigrationRunner(second._conn, audit=audit).applied()}
        assert recorded == {item.version for item in MIGRATIONS}, "every migration eventually applies"
        assert second._conn.execute("SELECT count(*) FROM schema_migration_skips").fetchone()[0] == 0, (
            "applying a migration clears its deferral in the same transaction"
        )
        second.close()

    def test_a_genuine_hole_is_still_refused(self, tmp_path: Path) -> None:
        """The refinement above must not cost the guard its teeth: a version removed from the
        bookkeeping, with no deferral recorded against it, is a bypass and the boot fails closed."""
        path = tmp_path / "nexus.db"
        audit = AuditLog(SqliteAuditStore(path))
        store = SqliteOperationalStore(path, audit=audit)
        store._conn.execute("DELETE FROM schema_migrations WHERE version = '0002_memory'")
        store._conn.commit()
        store.close()
        with pytest.raises(MigrationError, match="the sequence has a hole"):
            MigrationRunner(sqlite3.connect(path), audit=audit, migrations=MIGRATIONS).run()

    def test_report_serialises_for_the_api(self, tmp_path: Path) -> None:
        audit, store = _durable(tmp_path)
        payload: dict[str, Any] = store.migrations.to_dict() if store.migrations else {}
        assert payload["changed"] is True
        assert payload["applied"][0]["version"] == "0001_operational"
        assert payload["skipped"] == []
