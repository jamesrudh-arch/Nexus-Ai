"""Append-only, hash-chained audit log (Section 15.4, Section 23).

Every security-relevant action, decision, approval, order event, limit change, halt and
incident is recorded here. Records are chained by SHA-256 so that deletion or alteration
of any record breaks verification of the whole chain.
"""

from nexus.audit.chain import AuditRecord, HashChain, verify_chain
from nexus.audit.log import AuditLog, AuditStore, InMemoryAuditStore, SqliteAuditStore

__all__ = [
    "AuditLog",
    "AuditRecord",
    "AuditStore",
    "HashChain",
    "InMemoryAuditStore",
    "SqliteAuditStore",
    "verify_chain",
]
