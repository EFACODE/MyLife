"""Tests for the entities & relationships projection (T3.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.core.events.store import EventRow
from mylife.db.base import Base
from mylife.timeline import EntityProjection, EntityProjectionSubscriber

BASE_TIME = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as db:
        yield db


def _event(
    user: uuid.UUID, *, minutes: int = 0, source: str = "manual", category: str = "health"
) -> LifeEventRecorded:
    return LifeEventRecorded(
        user_id=user,
        occurred_at=BASE_TIME + timedelta(minutes=minutes),
        source=source,
        correlation_id="c",
        payload=LifeEventRecordedPayload(title=f"e{minutes}", category=category),
    )


def test_apply_creates_entities_and_relationship(session: Session) -> None:
    user = uuid.uuid4()
    projection = EntityProjection(session)

    projection.apply(_event(user, source="manual", category="health"))

    entities = projection.list_entities(user)
    keys = {(e.entity_type, e.entity_key) for e in entities}
    assert keys == {("source", "manual"), ("category", "health")}
    assert all(e.occurrences == 1 for e in entities)

    (relationship,) = projection.list_relationships(user)
    assert relationship.rel_type == "records"
    source = next(e for e in entities if e.entity_type == "source")
    category = next(e for e in entities if e.entity_type == "category")
    assert relationship.source_entity_id == source.entity_id
    assert relationship.target_entity_id == category.entity_id


def test_repeat_increments_and_advances_last_seen(session: Session) -> None:
    user = uuid.uuid4()
    projection = EntityProjection(session)
    projection.apply(_event(user, minutes=0, category="health"))
    projection.apply(_event(user, minutes=30, category="health"))

    category = next(e for e in projection.list_entities(user) if e.entity_type == "category")
    assert category.occurrences == 2
    assert category.first_seen_at == BASE_TIME
    assert category.last_seen_at == BASE_TIME + timedelta(minutes=30)

    (relationship,) = projection.list_relationships(user)
    assert relationship.occurrences == 2


def test_user_scoped(session: Session) -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    projection = EntityProjection(session)
    projection.apply(_event(user_a, category="health"))
    projection.apply(_event(user_b, category="finance"))

    assert {
        e.entity_key for e in projection.list_entities(user_a) if e.entity_type == "category"
    } == {"health"}
    assert {
        e.entity_key for e in projection.list_entities(user_b) if e.entity_type == "category"
    } == {"finance"}


def test_subscriber_updates_projection_on_publish(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    EntityProjectionSubscriber(factory).register(bus)

    bus.publish(_event(user, category="sleep"))

    with factory() as session:
        entities = EntityProjection(session).list_entities(user)
    assert ("category", "sleep") in {(e.entity_type, e.entity_key) for e in entities}


def test_rebuild_matches_live_apply_and_leaves_events_untouched(session: Session) -> None:
    user = uuid.uuid4()
    store = EventStore(session)
    events = [_event(user, minutes=0, category="health"), _event(user, minutes=10, category="work")]
    for event in events:
        store.append(event)
    session.commit()

    projection = EntityProjection(session)
    projection.rebuild(events)

    categories = {
        e.entity_key for e in projection.list_entities(user) if e.entity_type == "category"
    }
    assert categories == {"health", "work"}
    # Rebuild must not touch the append-only events.
    assert session.scalar(select(EventRow.user_id).limit(1)) == user
    assert len(store.read_stream(user)) == 2
