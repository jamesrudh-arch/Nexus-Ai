"""Hash-chained audit records.

A record's digest covers its own content *and* the previous record's digest, so any
insertion, deletion or edit in the middle of the chain is detectable. This is a
tamper-*evidence* mechanism, not encryption: the payload is readable by design because
the owner must be able to audit it.

Canonical JSON (sorted keys, no insignificant whitespace, UTF-8) is hashed so that
semantically identical records always produce the same digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from nexus.core.ids import iso_utc, new_id, utc_now

GENESIS_HASH = "0" * 64


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON encoding used for every digest in the system."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One immutable audit entry.

    ``redacted_payload`` must already have secrets removed — see
    :func:`nexus.secrets.redaction.redact`. The audit log refuses payloads containing
    obvious secret material as a second line of defence.
    """

    seq: int
    event_type: str
    actor: str
    payload: dict[str, Any]
    timestamp: str
    record_id: str = field(default_factory=lambda: new_id("AUD"))
    prev_hash: str = GENESIS_HASH
    record_hash: str = ""

    def digest_input(self) -> str:
        return canonical_json(
            {
                "seq": self.seq,
                "record_id": self.record_id,
                "event_type": self.event_type,
                "actor": self.actor,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "prev_hash": self.prev_hash,
            }
        )

    def with_hash(self) -> AuditRecord:
        """Return a copy of this record with ``record_hash`` computed."""
        if self.record_hash:
            return self
        digest = sha256_hex(self.digest_input())
        return AuditRecord(
            seq=self.seq,
            event_type=self.event_type,
            actor=self.actor,
            payload=self.payload,
            timestamp=self.timestamp,
            record_id=self.record_id,
            prev_hash=self.prev_hash,
            record_hash=digest,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "record_id": self.record_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload": canonical_json(self.payload),
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AuditRecord:
        payload = row["payload"]
        return cls(
            seq=int(row["seq"]),
            event_type=str(row["event_type"]),
            actor=str(row["actor"]),
            payload=json.loads(payload) if isinstance(payload, str) else dict(payload),
            timestamp=str(row["timestamp"]),
            record_id=str(row["record_id"]),
            prev_hash=str(row["prev_hash"]),
            record_hash=str(row["record_hash"]),
        )


class HashChain:
    """Tracks the last digest so records can be appended in order."""

    __slots__ = ("_last_hash", "_seq")

    def __init__(self, last_hash: str = GENESIS_HASH, seq: int = 0) -> None:
        self._last_hash = last_hash
        self._seq = seq

    @property
    def last_hash(self) -> str:
        return self._last_hash

    @property
    def seq(self) -> int:
        return self._seq

    def next(self, event_type: str, actor: str, payload: dict[str, Any]) -> AuditRecord:
        """Build the next chained record (already hashed)."""
        self._seq += 1
        record = AuditRecord(
            seq=self._seq,
            event_type=event_type,
            actor=actor,
            payload=payload,
            timestamp=iso_utc(utc_now()),
            prev_hash=self._last_hash,
        ).with_hash()
        self._last_hash = record.record_hash
        return record

    def sync_to(self, seq: int, last_hash: str) -> None:
        """Adopt persisted chain state after a restart."""
        self._seq = max(self._seq, int(seq))
        self._last_hash = last_hash or GENESIS_HASH


@dataclass(frozen=True, slots=True)
class ChainBreak:
    seq: int
    record_id: str
    reason: str


def verify_chain(records: list[AuditRecord]) -> list[ChainBreak]:
    """Return every detected break. An empty list means the chain verifies.

    Checks: monotonic sequence from 1, prev_hash linkage, and recomputed record_hash.
    """
    breaks: list[ChainBreak] = []
    expected_prev = GENESIS_HASH
    expected_seq = 1
    for record in records:
        if record.seq != expected_seq:
            breaks.append(ChainBreak(record.seq, record.record_id, "sequence gap or reordering"))
        if record.prev_hash != expected_prev:
            breaks.append(
                ChainBreak(record.seq, record.record_id, "prev_hash mismatch (record altered or removed)")
            )
        recomputed = sha256_hex(record.digest_input())
        if recomputed != record.record_hash:
            breaks.append(ChainBreak(record.seq, record.record_id, "record_hash mismatch (content altered)"))
        expected_prev = record.record_hash
        expected_seq = record.seq + 1
    return breaks
