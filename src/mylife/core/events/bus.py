"""The event bus.

Two transports over the same :class:`EventBus` protocol:

* :class:`InProcessEventBus` — synchronous, same-process dispatch for
  projections that must update inside the request.
* :class:`RedisStreamPublisher` — appends events to a Redis stream so
  out-of-process consumers (Celery workers) can react asynchronously.

The bus only transports events; it neither persists them (that is the store,
T1.2) nor hooks into ``append`` (application services wire that in later tasks).
See ``specs/domain/timeline/event-bus.md`` (T1.3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from mylife.core.events.envelope import LifeEvent

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

DEFAULT_STREAM = "mylife:events"

Handler = Callable[[LifeEvent[Any]], None]


class EventDispatchError(Exception):
    """Raised after :meth:`InProcessEventBus.publish` when handlers failed.

    Every handler is still attempted; the failures are aggregated here so a
    broken subscriber neither blocks the others nor disappears silently.
    """

    def __init__(self, errors: list[Exception]) -> None:
        super().__init__(f"{len(errors)} event handler(s) failed during dispatch")
        self.errors = errors


@runtime_checkable
class EventBus(Protocol):
    """Anything that can publish a Life Event."""

    def publish(self, event: LifeEvent[Any]) -> None: ...


class InProcessEventBus:
    """Synchronous, in-memory dispatcher.

    Handlers are invoked in subscription order; a handler subscribed without an
    ``event_type`` receives every event.
    """

    def __init__(self) -> None:
        self._subscriptions: list[tuple[str | None, Handler]] = []

    def subscribe(self, handler: Handler, *, event_type: str | None = None) -> None:
        """Register ``handler``; ``event_type=None`` subscribes to all events."""
        self._subscriptions.append((event_type, handler))

    def publish(self, event: LifeEvent[Any]) -> None:
        """Invoke every matching handler; aggregate and raise any failures."""
        errors: list[Exception] = []
        for event_type, handler in self._subscriptions:
            if event_type is not None and event_type != event.event_type:
                continue
            try:
                handler(event)
            except Exception as exc:
                logger.exception(
                    "event handler failed for %s (%s)", event.event_type, event.event_id
                )
                errors.append(exc)
        if errors:
            raise EventDispatchError(errors)


class RedisStreamPublisher:
    """Publish events to a Redis stream for out-of-process consumers.

    Delivery is at-least-once; consumers must be idempotent (the unique
    ``event_id`` from T1.2 supports that).
    """

    def __init__(self, client: redis.Redis, *, stream: str = DEFAULT_STREAM) -> None:
        self._client = client
        self._stream = stream

    def publish(self, event: LifeEvent[Any]) -> None:
        """Append the event's envelope JSON as one entry on the stream."""
        self._client.xadd(self._stream, {"data": event.model_dump_json()})
