"""Event bus implementations.

Production target is NATS JetStream (Apache-2, self-hosted, $0). Until it is deployed,
the in-memory bus is used. The NATS transport fails closed: if the client library or a
server URL is missing, publishing raises rather than silently dropping events — a dropped
event in a trading system is an incident, not a convenience.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
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


#: Both the connect and the publish cross from a synchronous call site into an owned event
#: loop, so each needs a bound. Without one a stalled socket would hang the calling thread,
#: and the callers are the audit and alert paths, which must fail closed rather than block.
_CONNECT_TIMEOUT_SECONDS = 10.0
_PUBLISH_TIMEOUT_SECONDS = 10.0


class NatsEventBus:
    """NATS JetStream transport (optional dependency ``nats-py``).

    ``nats.connect`` is a *coroutine function*, and so is ``jetstream.publish``. This class
    therefore owns a dedicated event loop on a daemon thread and drives both with
    ``run_coroutine_threadsafe``. Calling them synchronously does not fail in an obscure way: it
    returns a coroutine object that has no ``jetstream`` attribute, so every first publish raised
    ``EventPublishError`` and no event could ever have reached NATS (defect 37). It went unnoticed
    because nothing publishes in Phase 3 and the lines were marked ``pragma: no cover``, so no test
    ever executed them.

    Connection is established lazily on first publish. If the library or URL is absent, or the
    server cannot be reached, publishing raises :class:`EventPublishError` — events are never
    silently discarded.

    What is *not* verified: a real NATS server has still never been contacted. The loop bridging
    below is exercised by tests against an injected async client; end-to-end delivery is a VM
    bring-up item (docs/06 §3, B-5).
    """

    def __init__(self, url: str, *, stream: str = "NEXUS") -> None:
        self._url = url
        self._stream = stream
        self._nc: Any = None
        self._js: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._local = InMemoryEventBus()

    def _run(self, coroutine: Any, timeout: float) -> Any:
        """Await ``coroutine`` on the owned loop from this thread, with a bound.

        The bound is the point: the callers are the audit and alert paths, where a network stall
        must produce a refusal rather than a hung thread.
        """
        loop = self._loop
        if loop is None:
            raise EventPublishError("the NATS event loop is not running")
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=timeout)

    def _stop_loop(self) -> None:
        loop, thread = self._loop, self._thread
        self._loop = None
        self._thread = None
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=5)
        if loop is not None:
            with contextlib.suppress(Exception):
                loop.close()

    def _ensure_client(self) -> None:
        if self._js is not None:
            return
        with self._lock:
            if self._js is not None:
                return
            try:
                import nats
            except ImportError as exc:
                raise EventPublishError("nats-py not installed") from exc

            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, daemon=True, name="nexus-nats")
            thread.start()
            self._loop = loop
            self._thread = thread
            try:
                client = self._run(nats.connect(self._url), _CONNECT_TIMEOUT_SECONDS)
                self._nc = client
                self._js = client.jetstream()
            except Exception as exc:
                # The loop is stopped rather than left running: a failed connect must not leak a
                # thread per attempt, and the caller gets a refusal either way.
                self._stop_loop()
                raise EventPublishError(
                    f"cannot connect to NATS at {self._url}: {type(exc).__name__}"
                ) from None

    def publish(self, event: EventEnvelope) -> None:
        self._local.publish(event)  # local subscribers always see the event
        self._ensure_client()
        js = self._js
        if js is None:  # pragma: no cover - _ensure_client raises rather than leaving this None
            raise EventPublishError("the NATS JetStream context is unavailable")
        try:
            payload = json.dumps(event.to_dict()).encode("utf-8")
            self._run(js.publish(event.topic, payload), _PUBLISH_TIMEOUT_SECONDS)
        except EventPublishError:
            raise
        except Exception as exc:
            raise EventPublishError(type(exc).__name__) from None

    def subscribe(self, topic: str, handler: Subscriber) -> None:
        self._local.subscribe(topic, handler)

    def close(self) -> None:
        # Close is best-effort: a transport already down must not mask shutdown.
        self._local.close()
        client, self._nc, self._js = self._nc, None, None
        if client is not None:
            with contextlib.suppress(Exception):
                closing = client.close()
                if inspect.iscoroutine(closing):  # nats-py's close is a coroutine function
                    self._run(closing, _CONNECT_TIMEOUT_SECONDS)
        self._stop_loop()


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
