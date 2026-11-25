"""Structured logging with mandatory redaction.

Every log line passes through :func:`nexus.secrets.redaction.redact`, so a credential can
never reach stdout, a file, or a log shipper even if a caller is careless.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from nexus.secrets.redaction import redact

_CONFIGURED = False


def _redact_processor(_logger: Any, _name: str, event_dict: MutableMapping[str, Any]) -> Mapping[str, Any]:
    """structlog processor: redact the whole event before rendering.

    Redacting the dict (not each value separately) is what makes *key-name* based
    masking work: ``{"api_secret": "abc"}`` is masked because of the key, and a JWT in a
    free-text message is masked because of its shape.
    """
    result = redact(event_dict)
    return result if isinstance(result, dict) else {"event": result}


def configure_logging(*, level: int = logging.INFO, json_output: bool = True) -> None:
    """Idempotent logging setup. JSON in production, console in development."""
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )
    # Silence noisy third-party loggers without hiding our own warnings.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            _redact_processor,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    """Return a configured structlog logger (configures on first use)."""
    configure_logging()
    return structlog.get_logger(name or "nexus")
