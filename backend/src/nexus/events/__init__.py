"""Internal event bus (Section 22: NATS JetStream in production).

The in-memory bus is the default for dev/tests; the NATS transport is optional and only
activated when ``nats-py`` is installed and a URL is configured. No paid messaging service.
"""

from nexus.events.bus import (
    EventBus,
    EventEnvelope,
    InMemoryEventBus,
    NatsEventBus,
    get_event_bus,
    reset_event_bus,
)

__all__ = [
    "EventBus",
    "EventEnvelope",
    "InMemoryEventBus",
    "NatsEventBus",
    "get_event_bus",
    "reset_event_bus",
]
