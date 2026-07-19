"""Tests for the manual capture service (T3.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus, LifeEvent
from mylife.db.base import Base
from mylife.timeline import (
    RecordLifeEventCommand,
    TimelineQueryFilter,
    TimelineQueryService,
    TimelineWriter,
)


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


def _command(user: uuid.UUID) -> RecordLifeEventCommand:
    return RecordLifeEventCommand(
        user_id=user,
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        title="Morning run",
        category="health",
    )


def test_record_appends_publishes_and_is_queryable(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    published: list[LifeEvent[object]] = []
    bus.subscribe(published.append)

    stored = TimelineWriter(session, bus).record(_command(user), correlation_id="cid-1")

    assert stored.source == "manual"
    assert stored.correlation_id == "cid-1"
    assert stored.raw_record_id is None
    # Published to the bus...
    assert [e.event_id for e in published] == [stored.event_id]
    # ...and durably queryable.
    page = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user))
    assert [i.event_id for i in page.items] == [stored.event_id]
    assert page.items[0].payload["title"] == "Morning run"


def test_subscriber_failure_does_not_undo_the_event(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()

    def boom(_: LifeEvent[object]) -> None:
        raise RuntimeError("projection failed")

    bus.subscribe(boom)

    # record() must not raise even though the subscriber does.
    stored = TimelineWriter(session, bus).record(_command(user), correlation_id="cid-2")

    page = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user))
    assert [i.event_id for i in page.items] == [stored.event_id]
