"""Identifier helpers.

IDs are collision-resistant without a database round-trip, so an intent can be
identified before it is persisted. Time helpers live in :mod:`nexus.core.time`.
"""

from __future__ import annotations

import secrets
from uuid import uuid4

from nexus.core.time import iso_utc, utc_now

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford-ish: no I, L, O, U

__all__ = ["iso_utc", "new_id", "new_idempotency_key", "utc_now"]


def new_id(prefix: str) -> str:
    """Create an ID like ``INT-3F2A9C1B4D5E6F70-K3F9XYZA``.

    Prefix conventions:
      AUD audit record    INT trade intent    ORD order       EXE execution event
      DEC decision        CASE research case  STR strategy    INC incident
      ALR alert           CNX connection      MND mandate     HLT halt event
    """
    if not prefix or not prefix.isalnum():
        raise ValueError("prefix must be alphanumeric")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{prefix.upper()}-{uuid4().hex[:16].upper()}-{suffix}"


def new_idempotency_key() -> str:
    """128 bits of entropy, URL-safe. Callers may also supply their own."""
    return secrets.token_urlsafe(16)
