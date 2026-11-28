"""Observability: structured logs and Prometheus metrics (Section 15.3, Section 21).

All components are self-hosted OSS ($0, D-019). Logs are JSON, redacted, and never
contain secret values. Metrics are exposed for Prometheus scraping by the API.
"""

from nexus.observability.logging import configure_logging, get_logger
from nexus.observability.metrics import (
    METRICS,
    observe_decision,
    observe_refusal,
    render_metrics,
)

__all__ = [
    "METRICS",
    "configure_logging",
    "get_logger",
    "observe_decision",
    "observe_refusal",
    "render_metrics",
]
