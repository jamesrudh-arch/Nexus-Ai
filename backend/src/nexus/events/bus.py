"""Event bus implementations.

Production target is NATS JetStream (Apache-2, self-hosted, $0). Until it is deployed,
the in-memory bus is used. The NATS transport fails closed: if the client library or a
server URL is missing, publishing raises rather than silently dropping events — a dropped
event in a trading system is an incident, not a convenience.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from nexus.core.errors import NexusError, RejectReason
from nexus.core.ids import iso_utc, new_id, utc_now

Subscriber = Callable[["EventEnvelope"], None]


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """An immutable internal event."""

    topic: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: new_id("EVT"))
    occurred_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    source: str = "nexus-core"
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
            "source": self.source,
            "version": self.version,
        }


class EventBus(Protocol):
    """Publish/subscribe contract."""

    def publish(self, event: EventEnvelope) -> None: ...

    def subscribe(self, topic: str, handler: Subscriber) -> None: ...

    def close(self) -> None: ...


class EventPublishError(NexusError):
    """Publishing failed. Callers must not treat this as success."""

    def __init__(self, detail: str) -> None:
        super().__init__(RejectReason.VENUE_DISCONNECTED, f"event publish failed: {detail}", retryable=True)


class InMemoryEventBus:
    """Synchronous, single-process bus. Keeps a bounded ring buffer for inspection/tests."""

    def __init__(self, *, history_limit: int = 1000) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._history: deque[EventEnvelope] = deque(maxlen=history_limit)
        self._lock = threading.RLock()
        self._closed = False

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            if self._closed:
                raise EventPublishError("bus is closed")
            self._history.append(event)
            handlers = list(self._subscribers.get(event.topic, []))
            handlers += list(self._subscribers.get("*", []))
        for handler in handlers:
            handler(event)

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        with self._lock:
            self._subscribers[topic].append(handler)

    def history(self, topic: str | None = None) -> list[EventEnvelope]:
        with self._lock:
            events = list(self._history)
        return [e for e in events if topic is None or e.topic == topic]

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._subscribers.clear()


class NatsEventBus:
    """NATS JetStream transport (optional dependency ``nats-py``).

    Connection is established lazily on first publish. If the library or URL is absent,
    publishing raises :class:`EventPublishError` — events are never silently discarded.
    """

    def __init__(self, url: str, *, stream: str = "NEXUS") -> None:
        self._url = url
        self._stream = stream
        self._nc: Any = None
        self._js: Any = None
        self._lock = threading.Lock()
        self._local = InMemoryEventBus()

    def _ensure_client(self) -> None:
        if self._js is not None:
            return
        with self._lock:
            if self._js is not None:
                return
            try:
                import nats
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise EventPublishError("nats-py not installed") from exc
            try:
                client = nats.connect(self._url)
                self._nc = client
                self._js = client.jetstream()
            except Exception as exc:  # pragma: no cover - network dependent
                raise EventPublishError(
                    f"cannot connect to NATS at {self._url}: {type(exc).__name__}"
                ) from None

    def publish(self, event: EventEnvelope) -> None:
        self._local.publish(event)  # local subscribers always see the event
        self._ensure_client()
        try:
            self._js.publish(event.topic, json.dumps(event.to_dict()).encode("utf-8"))  # pragma: no cover
        except Exception as exc:  # pragma: no cover - network dependent
            raise EventPublishError(type(exc).__name__) from None

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        self._local.subscribe(topic, handler)

    def close(self) -> None:
        self._local.close()
        if self._nc is not None:  # pragma: no cover - network dependent
            # Close is best-effort: a transport already down must not mask shutdown.
            with contextlib.suppress(Exception):
                self._nc.close()
            self._nc = None
            self._js = None


_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the process bus, creating it from ``NEXUS_NATS_URL`` if configured."""
    global _bus  # noqa: PLW0603 - module-level singleton by design
    if _bus is not None:
        return _bus
    with _bus_lock:
        if _bus is None:
            import os

            url = os.environ.get("NEXUS_NATS_URL", "").strip()
            _bus = NatsEventBus(url) if url else InMemoryEventBus()
    return _bus


def reset_event_bus() -> None:
    """Close and clear the singleton (tests)."""
    global _bus  # noqa: PLW0603
    with _bus_lock:
        if _bus is not None:
            _bus.close()
        _bus = None
