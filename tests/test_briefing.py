"""Tests for the daily briefing service (T3.6)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.briefing import BriefingService
from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def _append(
    store: EventStore, user: uuid.UUID, *, hours_ago: float, source: str, category: str
) -> uuid.UUID:
    event = LifeEventRecorded(
        user_id=user,
        occurred_at=NOW - timedelta(hours=hours_ago),
        source=source,
        correlation_id="c",
        payload=LifeEventRecordedPayload(title="t", category=category),
    )
    return store.append(event).event_id


def test_briefing_lines_are_evidence_linked(session: Session) -> None:
    user = uuid.uuid4()
    store = EventStore(session)
    e1 = _append(store, user, hours_ago=1, source="manual", category="health")
    e2 = _append(store, user, hours_ago=2, source="calendar", category="health")
    e3 = _append(store, user, hours_ago=3, source="calendar", category="work")
    session.commit()

    briefing = BriefingService(session, InProcessEventBus()).deliver(
        user, now=NOW, correlation_id="cid"
    )

    assert briefing.event_count == 3
    lines = {line.kind: line for line in briefing.lines}
    assert set(lines["total"].evidence) == {e1, e2, e3}

    category_lines = [line for line in briefing.lines if line.kind == "category"]
    health = next(line for line in category_lines if "health" in line.summary)
    assert set(health.evidence) == {e1, e2}
    assert health.summary == "2 health events"

    source_lines = [line for line in briefing.lines if line.kind == "source"]
    calendar = next(line for line in source_lines if "calendar" in line.summary)
    assert set(calendar.evidence) == {e2, e3}


def test_window_and_system_events_excluded(session: Session) -> None:
    user = uuid.uuid4()
    store = EventStore(session)
    inside = _append(store, user, hours_ago=1, source="manual", category="health")
    _append(store, user, hours_ago=48, source="manual", category="health")  # outside 24h
    session.commit()
    service = BriefingService(session, InProcessEventBus())

    first = service.deliver(user, now=NOW, correlation_id="cid", window_hours=24)
    assert first.event_count == 1
    assert set(first.lines[0].evidence) == {inside}

    # A BriefingDelivered was recorded; the next briefing must not count it.
    second = service.deliver(user, now=NOW, correlation_id="cid", window_hours=24)
    assert second.event_count == 1


def test_delivery_emits_and_publishes_briefing_event(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    published: list[LifeEvent[object]] = []
    bus.subscribe(published.append)

    BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")

    assert [e.event_type for e in published] == ["assistant.briefing_delivered"]
    stored = EventStore(session).read_stream(user)
    assert [e.event_type for e in stored] == ["assistant.briefing_delivered"]


def test_empty_window_has_single_total_line(session: Session) -> None:
    user = uuid.uuid4()

    briefing = BriefingService(session, InProcessEventBus()).deliver(
        user, now=NOW, correlation_id="cid"
    )

    assert briefing.event_count == 0
    assert len(briefing.lines) == 1
    assert briefing.lines[0].kind == "total"
    assert briefing.lines[0].evidence == []
