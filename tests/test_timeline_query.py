"""Tests for the timeline query service (T3.1)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, LifeEventRecorded, LifeEventRecordedPayload
from mylife.db.base import Base
from mylife.timeline import TimelineQueryFilter, TimelineQueryService

BASE_TIME = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


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
    store: EventStore,
    user: uuid.UUID,
    *,
    minutes: int,
    source: str = "manual",
    category: str = "health",
) -> None:
    store.append(
        LifeEventRecorded(
            user_id=user,
            occurred_at=BASE_TIME + timedelta(minutes=minutes),
            source=source,
            correlation_id="c",
            payload=LifeEventRecordedPayload(title=f"e{minutes}", category=category),
        )
    )


def test_scopes_to_user_and_orders_newest_first(session: Session) -> None:
    store = EventStore(session)
    user, other = uuid.uuid4(), uuid.uuid4()
    _append(store, user, minutes=0)
    _append(store, user, minutes=10)
    _append(store, other, minutes=5)

    page = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user))

    assert all(item.user_id == user for item in page.items)
    assert [item.occurred_at for item in page.items] == [
        BASE_TIME + timedelta(minutes=10),
        BASE_TIME,
    ]
    assert page.has_more is False


def test_filters_by_time_window_type_and_source(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    _append(store, user, minutes=0, source="manual")
    _append(store, user, minutes=30, source="calendar")
    _append(store, user, minutes=60, source="manual")

    service = TimelineQueryService(session)

    windowed = service.query(
        TimelineQueryFilter(
            user_id=user,
            occurred_from=BASE_TIME + timedelta(minutes=15),
            occurred_to=BASE_TIME + timedelta(minutes=45),
        )
    )
    assert [i.occurred_at for i in windowed.items] == [BASE_TIME + timedelta(minutes=30)]

    by_source = service.query(TimelineQueryFilter(user_id=user, sources=("manual",)))
    assert {i.source for i in by_source.items} == {"manual"}
    assert len(by_source.items) == 2

    by_type = service.query(
        TimelineQueryFilter(user_id=user, event_types=("timeline.life_event_recorded",))
    )
    assert len(by_type.items) == 3


def test_pagination_and_has_more(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    for minute in range(5):
        _append(store, user, minutes=minute)
    service = TimelineQueryService(session)

    first = service.query(TimelineQueryFilter(user_id=user, limit=2, offset=0))
    assert len(first.items) == 2
    assert first.has_more is True

    last = service.query(TimelineQueryFilter(user_id=user, limit=2, offset=4))
    assert len(last.items) == 1
    assert last.has_more is False


def test_provenance_fields_present(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    _append(store, user, minutes=0)

    (item,) = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
    assert item.raw_record_id is None
    assert item.corrects_event_id is None
    assert item.payload["title"] == "e0"
