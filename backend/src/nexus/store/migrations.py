"""Forward-only migration runner (Stage 6, law L-4).

Three properties, each of which is a refusal rather than a repair:

* **Idempotent.** Applying the same version twice is a no-op, so a restart during boot never
  half-applies a schema.
* **Forward-only.** A version whose checksum changed after it was applied is refused, and so is a
  version that is no longer present in code. A schema that drifts from the code that writes it is
  worse than a schema that fails to start.
* **Audited.** Each application is itself an audit event (``migration.applied``) carrying the
  version, its checksum and its statement count, so "when did the schema change" is answerable from
  the chain rather than from memory.

The runner needs ``audit_log`` to exist for migration ``0003_audit_append_only``; the audit store is
therefore constructed before migrations run. When that ordering is violated the failure is explicit
(:class:`MigrationError`) instead of a bare ``sqlite3.OperationalError``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, utc_now
from nexus.store.schema import MIGRATIONS, SCHEMA_MIGRATIONS_DDL, Migration

__all__ = [
    "AppliedMigration",
    "MigrationError",
    "MigrationReport",
    "MigrationRunner",
    "SkippedMigration",
]


class MigrationError(NexusError):
    """A migration cannot be applied safely. Refuse to start rather than run on a wrong schema."""

    def __init__(self, detail: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(
            RejectReason.MIGRATION_INVALID,
            detail,
            retryable=False,
            context=context,
        )


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One row of ``schema_migrations``."""

    version: str
    checksum: str
    description: str
    statements: int
    applied_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "checksum": self.checksum,
            "description": self.description,
            "statements": self.statements,
            "applied_at": self.applied_at,
        }


@dataclass(frozen=True, slots=True)
class SkippedMigration:
    """A migration that could not apply here, and why. Skipping is reported, never silent."""

    version: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """What a run did. Empty ``applied`` means the schema was already current."""

    applied: tuple[AppliedMigration, ...] = ()
    already_applied: tuple[str, ...] = ()
    skipped: tuple[SkippedMigration, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.applied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": [item.to_dict() for item in self.applied],
            "already_applied": list(self.already_applied),
            "skipped": [item.to_dict() for item in self.skipped],
            "changed": self.changed,
        }


class MigrationRunner:
    """Applies :data:`nexus.store.schema.MIGRATIONS` in order, once each."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        audit: Any = None,
        migrations: Sequence[Migration] = MIGRATIONS,
    ) -> None:
        self._conn = conn
        self._audit = audit
        self._migrations = tuple(migrations)
        self._ensure_bookkeeping()

    # -- reads -----------------------------------------------------------

    def applied(self) -> tuple[AppliedMigration, ...]:
        cursor = self._conn.execute(
            "SELECT version, checksum, description, statements, applied_at "
            "FROM schema_migrations ORDER BY version ASC"
        )
        return tuple(
            AppliedMigration(
                version=str(row[0]),
                checksum=str(row[1]),
                description=str(row[2]),
                statements=int(row[3]),
                applied_at=str(row[4]),
            )
            for row in cursor.fetchall()
        )

    def pending(self) -> tuple[Migration, ...]:
        done = {item.version for item in self.applied()}
        return tuple(item for item in self._migrations if item.version not in done)

    # -- write -----------------------------------------------------------

    def run(self) -> MigrationReport:
        """Validate, then apply every pending migration in declared order."""
        recorded = {item.version: item for item in self.applied()}
        self._validate(recorded)

        applied: list[AppliedMigration] = []
        skipped: list[SkippedMigration] = []
        for migration in self._migrations:
            if migration.version in recorded:
                continue
            if not self._applicable(migration):
                # Not applied and not recorded: a durable audit store on a later boot still needs it.
                skipped.append(
                    SkippedMigration(
                        version=migration.version,
                        reason=(
                            f"requires table {migration.requires}, which is absent from this "
                            "database (an ephemeral audit backend has no audit_log to protect)"
                        ),
                    )
                )
                continue
            applied.append(self._apply(migration))
        return MigrationReport(
            applied=tuple(applied),
            already_applied=tuple(sorted(recorded)),
            skipped=tuple(skipped),
        )

    # -- internals -------------------------------------------------------

    def _ensure_bookkeeping(self) -> None:
        self._conn.executescript(SCHEMA_MIGRATIONS_DDL)
        self._conn.commit()

    def _table_exists(self, table: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        return row is not None

    def _validate(self, recorded: dict[str, AppliedMigration]) -> None:
        declared = {item.version: item for item in self._migrations}

        for version, row in recorded.items():
            migration = declared.get(version)
            if migration is None:
                raise MigrationError(
                    f"migration {version} is recorded as applied but no longer exists in code; "
                    "refusing to start on a schema this build cannot account for",
                    context={"version": version},
                )
            if migration.checksum != row.checksum:
                raise MigrationError(
                    f"migration {version} changed after it was applied "
                    f"(recorded {row.checksum[:12]}, now {migration.checksum[:12]}); "
                    "applied migrations are immutable — add a new migration instead",
                    context={"version": version, "recorded": row.checksum[:12]},
                )

        # Forward-only: no holes. A hole is an applicable migration that is still pending *below*
        # one that has already been applied — the sequence moved past it. A migration that cannot
        # apply in this database (its required table is absent) is not a hole: it is a reported
        # skip, and it stays pending for a boot that can apply it.
        positions = list(self._migrations)
        last_applied = max(
            (index for index, item in enumerate(positions) if item.version in recorded),
            default=-1,
        )
        for index, migration in enumerate(positions):
            if migration.version in recorded or index > last_applied:
                continue
            if not self._applicable(migration):
                continue
            raise MigrationError(
                f"migration {migration.version} is pending while later migrations are already "
                "applied; the sequence has a hole and this runner only moves forward",
                context={"version": migration.version},
            )

    def _applicable(self, migration: Migration) -> bool:
        # True when this migration can apply here: no requirement, or the requirement is present.
        return migration.requires is None or self._table_exists(migration.requires)

    def _apply(self, migration: Migration) -> AppliedMigration:
        applied_at = iso_utc(utc_now())
        try:
            self._conn.executescript(migration.sql)
            self._conn.execute(
                "INSERT INTO schema_migrations (version, checksum, description, statements, applied_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    migration.version,
                    migration.checksum,
                    migration.description,
                    migration.statements,
                    applied_at,
                ),
            )
            self._conn.commit()
        except sqlite3.OperationalError as exc:
            self._conn.rollback()
            detail = str(exc)
            if "no such table" in detail and "audit_log" in detail:
                raise MigrationError(
                    f"migration {migration.version} needs the audit store to exist first "
                    "(construct SqliteAuditStore before running migrations)",
                    context={"version": migration.version},
                ) from exc
            raise MigrationError(
                f"migration {migration.version} failed: {detail}",
                context={"version": migration.version},
            ) from exc

        record = AppliedMigration(
            version=migration.version,
            checksum=migration.checksum,
            description=migration.description,
            statements=migration.statements,
            applied_at=applied_at,
        )
        if self._audit is not None:
            # The schema change is committed before this entry is written. If the audit write fails
            # the exception propagates and the run is reported as failed; re-running is idempotent
            # because the version is now recorded.
            self._audit.record("migration.applied", record.to_dict())
        return record
