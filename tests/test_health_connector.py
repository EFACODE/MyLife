"""Tests for the health CSV connector (T4.5)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import ConnectorRunner, FetchContext
from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.health import HealthCsvConnector, HealthService
from mylife.timeline import TimelineQueryFilter, TimelineQueryService

FETCHED_AT = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)

CSV = (
    "kind,occurred_at,duration_minutes,quality,activity,distance_meters,energy_kcal,external_id\n"
    "sleep,2026-07-19T00:30:00+00:00,465,good,,,,s-1\n"
    "workout,2026-07-19T07:00:00+00:00,42,,run,8000,520,w-1\n"
)


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


def _context(user: uuid.UUID) -> FetchContext:
    return FetchContext(user_id=user, correlation_id="corr-1")


def test_import_creates_sleep_and_workout_with_provenance(
    factory: sessionmaker[Session],
) -> None:
    user = uuid.uuid4()
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(
            HealthCsvConnector(CSV, fetched_at=FETCHED_AT), _context(user)
        )

    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
        health = HealthService(session, InProcessEventBus())
        sleep = health.list_sleep(user)
        workouts = health.list_workouts(user)

    assert len(events) == 2
    assert all(e.source == "health" for e in events)
    assert all(e.raw_record_id is not None for e in events)
    assert [s.duration_minutes for s in sleep] == [465]
    assert sleep[0].quality == "good"
    assert workouts[0].activity == "run"
    assert workouts[0].distance_meters == 8000
    assert workouts[0].energy_kcal == 520


def test_reimport_is_idempotent(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(
            HealthCsvConnector(CSV, fetched_at=FETCHED_AT), _context(user)
        )
    with factory() as session:
        second = ConnectorRunner(session, InProcessEventBus()).sync(
            HealthCsvConnector(CSV, fetched_at=FETCHED_AT), _context(user)
        )

    assert (second.raw_ingested, second.events_created, second.skipped_duplicates) == (0, 0, 2)


def test_unknown_kind_rolls_back_the_batch(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bad_csv = (
        "kind,occurred_at,duration_minutes\n"
        "sleep,2026-07-19T00:30:00+00:00,465\n"
        "meditation,2026-07-19T06:00:00+00:00,20\n"
    )
    with factory() as session, pytest.raises(ValueError):
        ConnectorRunner(session, InProcessEventBus()).sync(
            HealthCsvConnector(bad_csv, fetched_at=FETCHED_AT), _context(user)
        )

    with factory() as session:
        assert EventStore(session).read_all() == []


def test_missing_field_rolls_back_the_batch(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bad_csv = (
        "kind,occurred_at,duration_minutes,activity\n"
        "sleep,2026-07-19T00:30:00+00:00,465,\n"
        "workout,2026-07-19T07:00:00+00:00,,\n"  # workout missing activity + duration
    )
    with factory() as session, pytest.raises(ValueError):
        ConnectorRunner(session, InProcessEventBus()).sync(
            HealthCsvConnector(bad_csv, fetched_at=FETCHED_AT), _context(user)
        )

    with factory() as session:
        assert EventStore(session).read_all() == []
