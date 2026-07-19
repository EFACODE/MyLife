"""Tests for domain instrumentation + readiness probe (T9.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.api.health import readiness
from mylife.core.events import (
    EventStore,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.core.events.store import DuplicateEventError
from mylife.core.metrics import EVENTS_APPENDED
from mylife.db.base import Base

EVENT_TYPE = "timeline.life_event_recorded"
NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _event() -> LifeEventRecorded:
    return LifeEventRecorded(
        user_id=uuid.uuid4(),
        occurred_at=NOW,
        source="manual",
        correlation_id="c",
        payload=LifeEventRecordedPayload(title="Note", category="misc"),
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


def test_append_increments_events_counter(session: Session) -> None:
    before = EVENTS_APPENDED.value(EVENT_TYPE)
    EventStore(session).append(_event())
    session.commit()
    assert EVENTS_APPENDED.value(EVENT_TYPE) == before + 1


def test_duplicate_append_does_not_increment(session: Session) -> None:
    store = EventStore(session)
    event = _event()
    store.append(event)
    session.commit()
    before = EVENTS_APPENDED.value(EVENT_TYPE)
    with pytest.raises(DuplicateEventError):
        store.append(event)  # same event_id
    assert EVENTS_APPENDED.value(EVENT_TYPE) == before


def test_readiness_ok_when_db_answers(session: Session) -> None:
    assert readiness(session).status == "ready"


class _BrokenSession:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("db down")


def test_readiness_503_when_db_unavailable() -> None:
    with pytest.raises(HTTPException) as exc:
        readiness(_BrokenSession())  # type: ignore[arg-type]
    assert exc.value.status_code == 503
