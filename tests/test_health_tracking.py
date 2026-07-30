"""Tests for the health service — sleep & workouts (T4.4)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.health import SLEEP_RECORDED, WORKOUT_COMPLETED, HealthService

DAY1 = datetime(2026, 7, 18, 0, 30, tzinfo=UTC)
DAY2 = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)


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


@pytest.fixture
def health(session: Session) -> HealthService:
    return HealthService(session, InProcessEventBus())


def test_record_sleep_emits_event(health: HealthService, session: Session) -> None:
    user = uuid.uuid4()
    sleep = health.record_sleep(user, DAY1, 465, quality="good", correlation_id="c")

    assert sleep.duration_minutes == 465
    assert sleep.quality == "good"
    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [SLEEP_RECORDED]


def test_record_workout_with_optional_fields(health: HealthService, session: Session) -> None:
    user = uuid.uuid4()
    workout = health.record_workout(
        user, DAY2, "run", 42, distance_meters=8000, energy_kcal=520, correlation_id="c"
    )

    assert (workout.activity, workout.duration_minutes) == ("run", 42)
    assert workout.distance_meters == 8000
    assert workout.energy_kcal == 520
    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [WORKOUT_COMPLETED]


def test_record_workout_without_optional_fields(health: HealthService) -> None:
    user = uuid.uuid4()
    workout = health.record_workout(user, DAY2, "yoga", 30, correlation_id="c")
    assert workout.distance_meters is None
    assert workout.energy_kcal is None


def test_list_newest_first_and_scoped(health: HealthService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    health.record_sleep(user, DAY1, 400, correlation_id="c")
    health.record_sleep(user, DAY2, 465, correlation_id="c")
    health.record_workout(user, DAY2, "run", 42, correlation_id="c")
    health.record_sleep(other, DAY1, 300, correlation_id="c")

    sleep = health.list_sleep(user)
    assert [s.duration_minutes for s in sleep] == [465, 400]  # newest first
    workouts = health.list_workouts(user)
    assert [w.activity for w in workouts] == ["run"]
    # Scoped: the other user's sleep is not returned.
    assert len(health.list_sleep(other)) == 1
