"""Tests for the event bus (T1.3).

In-process dispatch is pure; the Redis publisher is exercised with fakeredis so
no broker is required.
"""

import uuid
from datetime import UTC, datetime

import fakeredis
import pytest
from pydantic import BaseModel

from mylife.core.events import (
    EventDispatchError,
    InProcessEventBus,
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    RedisStreamPublisher,
)


def _event(title: str = "Run") -> LifeEventRecorded:
    return LifeEventRecorded(
        user_id=uuid.uuid4(),
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source="manual",
        correlation_id="corr-1",
        payload=LifeEventRecordedPayload(title=title, category="health"),
    )


def test_typed_subscription_receives_only_matching_events() -> None:
    bus = InProcessEventBus()
    received: list[LifeEvent[BaseModel]] = []
    bus.subscribe(received.append, event_type="timeline.life_event_recorded")

    event = _event()
    bus.publish(event)

    assert received == [event]


def test_typed_subscription_ignores_other_types() -> None:
    bus = InProcessEventBus()
    received: list[LifeEvent[BaseModel]] = []
    bus.subscribe(received.append, event_type="finance.transaction_imported")

    bus.publish(_event())

    assert received == []


def test_all_subscription_receives_everything_in_order() -> None:
    bus = InProcessEventBus()
    order: list[str] = []
    bus.subscribe(lambda e: order.append("first"))
    bus.subscribe(lambda e: order.append("second"))

    bus.publish(_event())

    assert order == ["first", "second"]


def test_failing_handler_is_isolated_and_aggregated() -> None:
    bus = InProcessEventBus()
    survivors: list[str] = []

    def boom(_: LifeEvent[BaseModel]) -> None:
        raise RuntimeError("handler exploded")

    bus.subscribe(boom)
    bus.subscribe(lambda e: survivors.append("ran"))

    with pytest.raises(EventDispatchError) as excinfo:
        bus.publish(_event())

    assert survivors == ["ran"]  # other handler still ran
    assert len(excinfo.value.errors) == 1
    assert isinstance(excinfo.value.errors[0], RuntimeError)


def test_redis_publisher_appends_and_round_trips() -> None:
    client = fakeredis.FakeStrictRedis()
    publisher = RedisStreamPublisher(client, stream="test:events")
    event = _event(title="Yoga")

    publisher.publish(event)

    entries = client.xrange("test:events")
    assert len(entries) == 1
    _entry_id, fields = entries[0]
    restored = LifeEventRecorded.model_validate_json(fields[b"data"])
    assert restored == event


def test_redis_publisher_uses_configured_stream() -> None:
    client = fakeredis.FakeStrictRedis()
    RedisStreamPublisher(client, stream="custom:stream").publish(_event())

    assert client.xlen("custom:stream") == 1
    assert client.xlen("mylife:events") == 0
