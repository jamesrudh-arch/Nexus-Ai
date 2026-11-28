"""Canonical serialisation for persisted state (Stage 6, laws L-4 and L-5).

Three rules drive this module:

* **Decimal never becomes float.** Money and quantity are stored as their exact string form, the
  SQLite counterpart of the PostgreSQL ``NUMERIC`` columns in ``migrations/0001_core.sql``. A
  round-trip through ``float`` would silently change a quantity, and a changed quantity is a
  different order.
* **Canonical output.** Keys are sorted and separators are fixed, so the same logical payload
  always produces the same bytes. That matters because persisted payloads are referenced from the
  audit chain: a payload whose serialisation drifts cannot be compared after the fact.
* **Timestamps stay ISO-8601 UTC strings**, matching ``core.ids.iso_utc`` and the aware-UTC-only
  convention used everywhere else in the codebase.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from nexus.audit.chain import canonical_json

__all__ = [
    "dumps_canonical",
    "loads_json",
    "decimal_or_none",
    "to_jsonable",
]


def to_jsonable(value: Any) -> Any:
    """Convert domain values to JSON-safe primitives without losing precision."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        # Only calibrated confidence is a float by domain definition; it is never money.
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))
    return str(value)


def dumps_canonical(payload: Any) -> str:
    """Serialise to canonical JSON text.

    Delegates to :func:`nexus.audit.chain.canonical_json` — the same encoding every digest in the
    system uses — after converting domain values, so a stored payload and an audited payload of the
    same content are byte-identical.
    """
    return canonical_json(to_jsonable(payload))


def loads_json(text: str | None) -> Any:
    """Parse canonical JSON text. ``None`` and empty strings read back as ``None``."""
    if text is None or text == "":
        return None
    return json.loads(text)


def decimal_or_none(text: Any) -> Decimal | None:
    """Read a stored numeric column back as ``Decimal``.

    A value that cannot be read as a Decimal is a corruption, not a rounding opportunity: it is
    returned as ``None`` so callers fail closed instead of trading on a mangled quantity.
    """
    if text is None or text == "":
        return None
    if isinstance(text, Decimal):
        return text
    try:
        return Decimal(str(text))
    except InvalidOperation:
        return None
