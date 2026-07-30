"""Tests for the calendar CSV connector (T3.5)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import CalendarCsvConnector, ConnectorRunner, FetchContext
from mylife.core.events import EventStore, InProcessEventBus
from mylife.core.events.raw_store import RawRecordStore
from mylife.db.base import Base
from mylife.timeline import TimelineQueryFilter, TimelineQueryService

FETCHED_AT = datetime(2026, 7, 18, 20, 0, tzinfo=UTC)

CSV = (
    "external_id,title,category,occurred_at,description\n"
    "evt-1,Standup,work,2026-07-18T09:00:00+00:00,Daily sync\n"
    "evt-2,Gym,health,2026-07-18T18:00:00+00:00,\n"
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


def _sync(factory: sessionmaker[Session], user: uuid.UUID, csv_text: str) -> None:
    connector = CalendarCsvConnector(csv_text, fetched_at=FETCHED_AT)
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))


def test_import_creates_events_with_provenance(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    _sync(factory, user, CSV)

    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items

    assert len(events) == 2
    assert all(e.source == "calendar" for e in events)
    assert all(e.raw_record_id is not None for e in events)
    by_title = {e.payload["title"]: e for e in events}
    assert by_title["Standup"].payload["category"] == "work"
    assert by_title["Standup"].payload["note"] == "Daily sync"
    assert by_title["Gym"].payload["note"] is None
    assert by_title["Standup"].occurred_at == datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def test_reimport_is_idempotent(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    connector = CalendarCsvConnector(CSV, fetched_at=FETCHED_AT)
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))
    with factory() as session:
        second = ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))

    assert (second.raw_ingested, second.events_created, second.skipped_duplicates) == (0, 0, 2)


def test_external_id_preserved_on_raw_record(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    _sync(factory, user, CSV)

    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
        raw_store = RawRecordStore(session)
        external_ids = set()
        for event in events:
            assert event.raw_record_id is not None
            raw = raw_store.get(event.raw_record_id)
            assert raw is not None
            external_ids.add(raw.external_id)

    assert external_ids == {"evt-1", "evt-2"}


def test_bad_row_rolls_back_the_batch(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bad_csv = (
        "title,category,occurred_at\n"
        "Good,work,2026-07-18T09:00:00+00:00\n"
        "Bad,work,2026-07-18T10:00:00\n"  # naive datetime
    )
    connector = CalendarCsvConnector(bad_csv, fetched_at=FETCHED_AT)

    with factory() as session, pytest.raises(ValueError):
        ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))

    with factory() as session:
        assert EventStore(session).read_all() == []
