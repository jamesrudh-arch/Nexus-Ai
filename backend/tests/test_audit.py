"""Audit log tests: chaining, tamper evidence, append-only behaviour, secret refusal."""

from __future__ import annotations

import pytest

from nexus.audit.chain import GENESIS_HASH, AuditRecord, HashChain, canonical_json, sha256_hex, verify_chain
from nexus.audit.log import (
    AuditLog,
    InMemoryAuditStore,
    SecretMaterialDetected,
    SqliteAuditStore,
    assert_no_secrets,
)


class TestCanonicalJson:
    def test_key_order_does_not_change_digest(self) -> None:
        assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})

    def test_whitespace_does_not_change_digest(self) -> None:
        assert sha256_hex(canonical_json({"a": 1})) == sha256_hex(canonical_json({"a": 1}))

    def test_different_values_change_digest(self) -> None:
        assert sha256_hex(canonical_json({"a": 1})) != sha256_hex(canonical_json({"a": 2}))


class TestHashChain:
    def test_first_record_links_to_genesis(self) -> None:
        record = HashChain().next("test.event", "system", {"k": "v"})
        assert record.prev_hash == GENESIS_HASH
        assert record.seq == 1
        assert record.record_hash

    def test_records_link_sequentially(self) -> None:
        chain = HashChain()
        first = chain.next("a", "system", {})
        second = chain.next("b", "system", {})
        assert second.prev_hash == first.record_hash
        assert second.seq == 2

    def test_digest_is_deterministic(self) -> None:
        record = AuditRecord(
            seq=1, event_type="x", actor="system", payload={"a": 1}, timestamp="2026-11-25T00:00:00.000Z"
        )
        assert record.with_hash().record_hash == record.with_hash().record_hash

    def test_verify_intact_chain(self) -> None:
        chain = HashChain()
        records = [chain.next(f"e{i}", "system", {"i": i}) for i in range(5)]
        assert verify_chain(records) == []

    def test_verify_detects_content_tampering(self) -> None:
        chain = HashChain()
        records = [chain.next(f"e{i}", "system", {"i": i}) for i in range(3)]
        tampered = AuditRecord(
            seq=records[1].seq,
            event_type=records[1].event_type,
            actor=records[1].actor,
            payload={"i": 999},  # altered
            timestamp=records[1].timestamp,
            record_id=records[1].record_id,
            prev_hash=records[1].prev_hash,
            record_hash=records[1].record_hash,
        )
        records[1] = tampered
        breaks = verify_chain(records)
        assert breaks
        assert any("record_hash mismatch" in b.reason for b in breaks)

    def test_verify_detects_removed_record(self) -> None:
        chain = HashChain()
        records = [chain.next(f"e{i}", "system", {"i": i}) for i in range(4)]
        del records[1]
        breaks = verify_chain(records)
        assert breaks
        assert any("sequence gap" in b.reason or "prev_hash mismatch" in b.reason for b in breaks)

    def test_verify_detects_reordered_records(self) -> None:
        chain = HashChain()
        records = [chain.next(f"e{i}", "system", {"i": i}) for i in range(3)]
        records.reverse()
        assert verify_chain(records)

    def test_sync_to_restores_chain_after_restart(self) -> None:
        chain = HashChain()
        last = chain.next("e1", "system", {})
        restored = HashChain()
        restored.sync_to(last.seq, last.record_hash)
        nxt = restored.next("e2", "system", {})
        assert nxt.seq == 2
        assert nxt.prev_hash == last.record_hash


class TestAuditLog:
    def test_append_and_length(self, audit_log: AuditLog) -> None:
        audit_log.record("test.one", {"a": 1})
        audit_log.record("test.two", {"b": 2})
        assert audit_log.length == 2
        assert audit_log.verify() == []

    def test_actor_defaults_to_system(self, audit_log: AuditLog) -> None:
        record = audit_log.record("test.actor")
        assert record.actor == "system"

    def test_explicit_actor_recorded(self, audit_log: AuditLog) -> None:
        assert audit_log.record("test.actor", actor="OWNER").actor == "OWNER"

    def test_chain_head_advances(self, audit_log: AuditLog) -> None:
        first = audit_log.record("a").record_hash
        audit_log.record("b")
        assert audit_log.chain_head != first

    @pytest.mark.parametrize(
        "payload",
        [
            {"api_secret": "abc123"},
            {"password": "hunter2"},
            {"nested": {"private_key": "x" * 40}},
            {"seed_phrase": "one two three"},
            {"authorization": "Bearer xyz"},
            {"totp": "123456"},
        ],
    )
    def test_secret_keys_are_refused(self, audit_log: AuditLog, payload: dict[str, object]) -> None:
        with pytest.raises(SecretMaterialDetected):
            audit_log.record("test.secret", payload)

    def test_credential_shaped_values_are_refused(self, audit_log: AuditLog) -> None:
        with pytest.raises(SecretMaterialDetected):
            audit_log.record("test.secret", {"blob": "AKIA" + "A" * 16})

    def test_refused_write_does_not_extend_chain(self, audit_log: AuditLog) -> None:
        before = audit_log.length
        with pytest.raises(SecretMaterialDetected):
            audit_log.record("test.secret", {"api_secret": "x"})
        assert audit_log.length == before

    def test_assert_no_secrets_allows_normal_payload(self) -> None:
        assert_no_secrets(
            {"instrument_id": "INS-BTCUSDT-PERP-BYBIT", "quantity": "1.0", "reason": "DATA_STALE"}
        )


class TestSqliteStore:
    def test_persistence_and_reload(self, tmp_path: object) -> None:
        import pathlib

        path = pathlib.Path(str(tmp_path)) / "audit.sqlite3"
        store = SqliteAuditStore(path)
        log = AuditLog(store)
        log.record("boot", {"phase": 2})
        log.record("decision", {"state": "ABSTAINED"})
        head = log.chain_head
        store.close()

        reopened = AuditLog(SqliteAuditStore(path))
        assert reopened.length == 2
        assert reopened.chain_head == head
        assert reopened.verify() == []

    def test_chain_continues_after_restart(self, tmp_path: object) -> None:
        import pathlib

        path = pathlib.Path(str(tmp_path)) / "audit2.sqlite3"
        first = AuditLog(SqliteAuditStore(path))
        first.record("a")
        first.record("b")
        head = first.chain_head

        second = AuditLog(SqliteAuditStore(path))
        record = second.record("c")
        assert record.seq == 3
        assert record.prev_hash == head
        assert second.verify() == []

    def test_append_only_api_has_no_update_or_delete(self) -> None:
        store = InMemoryAuditStore()
        assert not hasattr(store, "update")
        assert not hasattr(store, "delete")
        assert not hasattr(AuditLog, "delete")
        assert not hasattr(AuditLog, "update")
