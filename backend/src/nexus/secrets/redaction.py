"""Redaction of secret material before anything is logged, audited or displayed.

Two layers:
1. :func:`redact` scrubs known key names and known secret *values* from arbitrary data.
2. :func:`nexus.audit.log.assert_no_secrets` refuses to audit anything still suspicious.

Redaction is destructive on purpose: the original value is never recoverable from logs.
"""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"

SENSITIVE_KEY = re.compile(
    r"(api[_-]?secret|api[_-]?key|apikey|access[_-]?key|app[_-]?key|secret|"
    r"private[_-]?key|password|passwd|passphrase|passkey|seed|mnemonic|"
    r"token|authorization|bearer|cookie|credential|signature|sign|totp|otp)",
    re.IGNORECASE,
)
CREDENTIAL_VALUE = re.compile(
    r"(xox[baprs]-[A-Za-z0-9-]+|"  # slack-style tokens
    r"AKIA[0-9A-Z]{16}|"  # AWS access key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,})",  # JWT
    re.IGNORECASE,
)
LONG_HEX_OR_B64 = re.compile(r"^[A-Za-z0-9+/_=-]{40,}$")


class Redactor:
    """Redacts values it has been told about, plus anything matching known patterns.

    Register the actual secret values you hold (in memory only) so they can be scrubbed
    from free-form text such as error messages and venue responses.
    """

    __slots__ = ("_known",)

    def __init__(self, known_values: list[str] | None = None) -> None:
        self._known: list[str] = sorted(
            {v for v in (known_values or []) if len(v) >= 6}, key=len, reverse=True
        )

    def register(self, value: str) -> None:
        """Remember a secret value so it can be scrubbed from arbitrary text."""
        if value and len(value) >= 6 and value not in self._known:
            self._known.append(value)
            self._known.sort(key=len, reverse=True)

    def scrub_text(self, text: str) -> str:
        """Remove known secret values and credential-shaped strings from text."""
        result = text
        for value in self._known:
            if value in result:
                result = result.replace(value, MASK)
        return CREDENTIAL_VALUE.sub(MASK, result)

    def scrub(self, data: Any) -> Any:  # noqa: PLR0911
        """Recursively redact a structure. Keys that look sensitive are masked entirely."""
        if isinstance(data, dict):
            return {
                key: MASK if SENSITIVE_KEY.search(str(key)) else self.scrub(value)
                for key, value in data.items()
            }
        if isinstance(data, (list, tuple)):
            return [self.scrub(item) for item in data]
        if isinstance(data, str):
            if CREDENTIAL_VALUE.search(data):
                return MASK
            if LONG_HEX_OR_B64.match(data):
                return MASK
            return self.scrub_text(data)
        return data


_default_redactor = Redactor()


def get_default_redactor() -> Redactor:
    return _default_redactor


def redact(data: Any, *, redactor: Redactor | None = None) -> Any:
    """Redact ``data`` using the given (or default) redactor."""
    return (redactor or _default_redactor).scrub(data)


def redact_mapping(mapping: dict[str, Any], *, redactor: Redactor | None = None) -> dict[str, Any]:
    """Convenience wrapper for dict payloads (audit, logs, API responses)."""
    result = redact(mapping, redactor=redactor)
    return result if isinstance(result, dict) else {"value": result}
