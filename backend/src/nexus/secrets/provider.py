"""Secret providers — free/OSS backends only (D-019).

- ``env``: process environment, for local development and tests only.
- ``sops``: SOPS+age encrypted files (MPL/EUPL, $0).
- ``openbao``: OpenBao, the OSS fork of Vault (MPL-2.0, self-hosted, $0).

No cloud KMS, no paid secrets manager. Providers return values; they never log them.
"""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

from nexus.core.errors import NexusError, RejectReason


class SecretNotFoundError(NexusError):
    """A referenced secret is missing. The caller must fail closed."""

    def __init__(self, reference: str) -> None:
        # Deliberately does not echo any value; the reference name is not sensitive.
        super().__init__(
            RejectReason.SECRET_UNAVAILABLE,
            f"secret reference not resolvable: {reference}",
            retryable=False,
        )


class SecretProvider(ABC):
    """Resolve a secret by reference name. Implementations must not log values."""

    name: str = "abstract"

    @abstractmethod
    def get(self, reference: str) -> str:
        """Return the secret value, or raise :class:`SecretNotFoundError`."""

    def try_get(self, reference: str) -> str | None:
        """Return the value or ``None`` — never raises."""
        try:
            return self.get(reference)
        except SecretNotFoundError:
            return None

    @abstractmethod
    def available(self) -> bool:
        """Whether this backend is usable right now (fail closed if not)."""


class EnvSecretProvider(SecretProvider):
    """Read secrets from the process environment. Development and tests only.

    Reference ``alerts/telegram-bot-token`` maps to env var
    ``NEXUS_SECRET_ALERTS_TELEGRAM_BOT_TOKEN``.
    """

    name = "env"
    PREFIX = "NEXUS_SECRET_"

    def __init__(self, environ: os._Environ[str] | dict[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    @staticmethod
    def _var_name(reference: str) -> str:
        cleaned = reference.strip().upper().replace("/", "_").replace("-", "_").replace(".", "_")
        return f"{EnvSecretProvider.PREFIX}{cleaned}"

    def get(self, reference: str) -> str:
        value = self._environ.get(self._var_name(reference))
        if value is None or value == "":
            raise SecretNotFoundError(reference)
        return value

    def available(self) -> bool:
        return True


class SopsSecretProvider(SecretProvider):
    """Decrypt a SOPS+age file on demand via the ``sops`` CLI (free, OSS).

    The decrypted document is held in memory only, never written to disk or logged.
    """

    name = "sops"

    def __init__(self, encrypted_file: str | Path, *, sops_binary: str = "sops") -> None:
        self._file = Path(encrypted_file)
        self._binary = sops_binary
        self._cache: dict[str, str] | None = None

    def available(self) -> bool:
        return self._file.exists()

    def _decrypt(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self.available():
            raise SecretNotFoundError(str(self._file))
        try:
            completed = subprocess.run(  # noqa: S603 - fixed binary, no shell
                [self._binary, "decrypt", str(self._file)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            # Never include stderr: it can contain key material hints.
            raise SecretNotFoundError(f"sops decryption failed ({type(exc).__name__})") from None
        cache: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                cache[key.strip()] = value.strip().strip('"')
        self._cache = cache
        return cache

    def get(self, reference: str) -> str:
        data = self._decrypt()
        value = data.get(reference)
        if value is None or value == "":
            raise SecretNotFoundError(reference)
        return value


class NullSecretProvider(SecretProvider):
    """Provides nothing. Used when no backend is configured — forces fail-closed behaviour."""

    name = "null"

    def get(self, reference: str) -> str:
        raise SecretNotFoundError(reference)

    def available(self) -> bool:
        return False


@lru_cache(maxsize=1)
def get_secret_provider() -> SecretProvider:
    """Select the provider from ``NEXUS_SECRETS_BACKEND`` (default: env for dev)."""
    backend = os.environ.get("NEXUS_SECRETS_BACKEND", "env").strip().lower()
    if backend == "sops":
        path = os.environ.get("NEXUS_SECRETS_SOPS_FILE", "")
        return SopsSecretProvider(path) if path else NullSecretProvider()
    if backend == "openbao":
        # OpenBao integration lands in Phase 8 (execution/live hardening). Until then it
        # must fail closed rather than pretend to work.
        return NullSecretProvider()
    return EnvSecretProvider()


def reset_secret_provider_cache() -> None:
    get_secret_provider.cache_clear()
