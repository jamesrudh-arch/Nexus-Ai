"""Secrets handling (Section 13.3, D-019).

Nothing in this package ever prints, logs, audits or transmits a secret value.
Backends are free/OSS only: OpenBao (MPL-2.0), SOPS+age, or process env for dev.
"""

from nexus.secrets.provider import (
    EnvSecretProvider,
    SecretNotFoundError,
    SecretProvider,
    get_secret_provider,
)
from nexus.secrets.redaction import Redactor, redact, redact_mapping

__all__ = [
    "EnvSecretProvider",
    "Redactor",
    "SecretNotFoundError",
    "SecretProvider",
    "get_secret_provider",
    "redact",
    "redact_mapping",
]
