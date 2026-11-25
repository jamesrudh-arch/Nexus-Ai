"""Prometheus metrics (self-hosted, $0).

Counters are intentionally narrow: decisions, refusals by reason, data staleness, halts,
audit chain length, and event publish failures. No metric may include a secret, an account
number, or a full instrument list as a label (cardinality + privacy).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest


@dataclass(frozen=True)
class _Metrics:
    """Container so tests can build an isolated registry."""

    registry: CollectorRegistry
    decisions: Counter
    refusals: Counter
    stale_quotes: Counter
    halt_active: Gauge
    environment_state: Gauge
    audit_records: Gauge
    audit_chain_broken: Gauge
    event_publish_failures: Counter
    api_requests: Counter
    live_orders_sent: Counter  # must stay 0 until Phase 8+live authority

    def render(self) -> bytes:
        return generate_latest(self.registry)


def build_metrics(namespace: str = "nexus") -> _Metrics:
    registry = CollectorRegistry()
    return _Metrics(
        registry=registry,
        decisions=Counter(
            f"{namespace}_decisions_total",
            "Decisions produced by the intelligence layer",
            ["state", "verb"],
            registry=registry,
        ),
        refusals=Counter(
            f"{namespace}_refusals_total",
            "Governance/risk refusals by reason code",
            ["reason", "stage"],
            registry=registry,
        ),
        stale_quotes=Counter(
            f"{namespace}_stale_quotes_total",
            "Market-data snapshots rejected as stale or faulty",
            ["venue", "status"],
            registry=registry,
        ),
        halt_active=Gauge(
            f"{namespace}_halt_active",
            "1 when an emergency halt or kill switch is engaged",
            ["scope"],
            registry=registry,
        ),
        environment_state=Gauge(
            f"{namespace}_environment_state",
            "Numeric rollout stage (0=DISABLED … 6=LIVE)",
            registry=registry,
        ),
        audit_records=Gauge(
            f"{namespace}_audit_records",
            "Number of chained audit records held",
            registry=registry,
        ),
        audit_chain_broken=Gauge(
            f"{namespace}_audit_chain_broken",
            "1 when audit chain verification detects a break",
            registry=registry,
        ),
        event_publish_failures=Counter(
            f"{namespace}_event_publish_failures_total",
            "Event bus publish failures (never silently dropped)",
            ["transport"],
            registry=registry,
        ),
        api_requests=Counter(
            f"{namespace}_api_requests_total",
            "API requests by path and status",
            ["path", "status"],
            registry=registry,
        ),
        live_orders_sent=Counter(
            f"{namespace}_live_orders_sent_total",
            "Real-money orders transmitted. Must remain zero before live authority.",
            ["venue"],
            registry=registry,
        ),
    )


METRICS: _Metrics = build_metrics()


def render_metrics() -> bytes:
    """Prometheus text exposition for /metrics."""
    return METRICS.render()


def observe_decision(state: str, verb: str) -> None:
    METRICS.decisions.labels(state=state, verb=verb).inc()


def observe_refusal(reason: str, *, stage: str = "gateway") -> None:
    METRICS.refusals.labels(reason=reason.split(":", 1)[0], stage=stage).inc()


def observe_stale_quote(venue: str, status: str) -> None:
    METRICS.stale_quotes.labels(venue=venue, status=status).inc()


def set_environment_state(value: int) -> None:
    METRICS.environment_state.set(value)


def set_halt_active(scope: str, active: bool) -> None:
    METRICS.halt_active.labels(scope=scope).set(1 if active else 0)


def set_audit_stats(records: int, broken: bool) -> None:
    METRICS.audit_records.set(records)
    METRICS.audit_chain_broken.set(1 if broken else 0)


def observe_api_request(path: str, status: int) -> None:
    METRICS.api_requests.labels(path=path, status=str(status)).inc()


def observe_event_failure(transport: str) -> None:
    METRICS.event_publish_failures.labels(transport=transport).inc()


def mark_live_order_sent(venue: str) -> Any:
    """Only callable from a certified live adapter (Phase 8+). Counted for audit parity."""
    METRICS.live_orders_sent.labels(venue=venue).inc()
    return METRICS.live_orders_sent
