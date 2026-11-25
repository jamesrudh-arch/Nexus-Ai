"""Audit log writer with pluggable storage.

Rules enforced here:
- Append-only: no update or delete API exists.
- Secret material is refused at the door (defence in depth behind redaction).
- Every write is chained, so a gap is detectable even if the store is swapped.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from nexus.audit.chain import (
    GENESIS_HASH,
    AuditRecord,
    HashChain,
    verify_chain,
)
from nexus.core.errors import NexusError, RejectReason

_FORBIDDEN_KEY = re.compile(
    r"(api[_-]?secret|api[_-]?key|access[_-]?key|secret[_-]?key|private[_-]?key|"
    r"password|passwd|passphrase|seed[_-]?phrase|mnemonic|token|authorization|bearer|"
    r"cookie|session[_-]?id|totp|otp[_-]?secret|passkey)",
    re.IGNORECASE,
)
_FORBIDDEN_VALUE = re.compile(
    r"(xox[baprs]-|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.IGNORECASE
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq         INTEGER PRIMARY KEY,
    record_id   TEXT    NOT NULL UNIQUE,
    event_type  TEXT    NOT NULL,
    actor       TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    prev_hash   TEXT    NOT NULL,
    record_hash TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS ix_audit_timestamp ON audit_log(timestamp);
"""


class SecretMaterialDetected(NexusError):
    """Raised when a payload appears to contain credentials. The write is refused."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            RejectReason.SECRET_UNAVAILABLE,
            f"refused to audit secret material: {detail}",
            retryable=False,
        )


def assert_no_secrets(payload: dict[str, Any], *, path: str = "") -> None:
    """Recursively reject payloads whose keys or values look like credentials."""
    for key, value in payload.items():
        key_path = f"{path}.{key}" if path else str(key)
        if _FORBIDDEN_KEY.search(str(key)):
            raise SecretMaterialDetected(f"forbidden key at {key_path}")
        if isinstance(value, str):
            if _FORBIDDEN_VALUE.search(value):
                raise SecretMaterialDetected(f"forbidden value pattern at {key_path}")
            # Long high-entropy hex/base64 blobs under a suspicious name are caught above;
            # here we only reject obvious long secrets paired with key-like names.
            if len(value) >= 32 and _FORBIDDEN_KEY.search(key_path):
                raise SecretMaterialDetected(f"long secret-like value at {key_path}")
        elif isinstance(value, dict):
            assert_no_secrets(value, path=key_path)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    assert_no_secrets(item, path=f"{key_path}[{index}]")


class AuditStore(Protocol):
    """Storage backend for audit records. Append and read only."""

    def append(self, record: AuditRecord) -> None: ...

    def read_all(self) -> list[AuditRecord]: ...

    def last(self) -> AuditRecord | None: ...


class InMemoryAuditStore:
    """Volatile store for tests and dry runs. Never used for live authority."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()

    def append(self, record: AuditRecord) -> None:
        with self._lock:
            self._records.append(record)

    def read_all(self) -> list[AuditRecord]:
        with self._lock:
            return list(self._records)

    def last(self) -> AuditRecord | None:
        with self._lock:
            return self._records[-1] if self._records else None


class SqliteAuditStore:
    """Durable store for single-host deployment (free-tier VM, 200 GB cap).

    SQLite in WAL mode is the right $0 choice for one owner, one host. The schema
    mirrors the PostgreSQL migration so promotion is a copy, not a rewrite.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def append(self, record: AuditRecord) -> None:
        row = record.to_row()
        with self._lock:
            self._conn.execute(
                """INSERT INTO audit_log
                   (seq, record_id, event_type, actor, payload, timestamp, prev_hash, record_hash)
                   VALUES (:seq, :record_id, :event_type, :actor, :payload, :timestamp,
                           :prev_hash, :record_hash)""",
                row,
            )
            self._conn.commit()

    def read_all(self) -> list[AuditRecord]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM audit_log ORDER BY seq ASC")
            return [AuditRecord.from_row(dict(row)) for row in cursor.fetchall()]

    def last(self) -> AuditRecord | None:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT 1")
            row = cursor.fetchone()
        return AuditRecord.from_row(dict(row)) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class AuditLog:
    """The single write path for auditable events."""

    def __init__(self, store: AuditStore, *, actor_default: str = "system") -> None:
        self._store = store
        self._actor_default = actor_default
        self._lock = threading.Lock()
        last = store.last()
        self._chain = HashChain(
            last_hash=last.record_hash if last else GENESIS_HASH,
            seq=last.seq if last else 0,
        )

    @property
    def chain_head(self) -> str:
        return self._chain.last_hash

    @property
    def length(self) -> int:
        return self._chain.seq

    def record(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
    ) -> AuditRecord:
        """Append one chained record. Raises if the payload contains secret material."""
        safe_payload = dict(payload or {})
        assert_no_secrets(safe_payload)
        with self._lock:
            entry = self._chain.next(
                event_type=event_type,
                actor=actor or self._actor_default,
                payload=safe_payload,
            )
            self._store.append(entry)
        return entry

    def verify(self) -> list[Any]:
        """Return chain breaks (empty == intact)."""
        return verify_chain(self._store.read_all())
