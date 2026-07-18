"""Tests for the append-only event store (T1.2).

Runs against a shared in-memory SQLite database — no network, no Postgres.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    DuplicateEventError,
    EventStore,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base


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


def _event(user_id: uuid.UUID, title: str = "Run") -> LifeEventRecorded:
    return LifeEventRecorded(
        user_id=user_id,
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source="manual",
        correlation_id="corr-1",
        payload=LifeEventRecordedPayload(title=title, category="health"),
    )


def test_append_and_read_round_trip(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    event = _event(user, title="Morning run")

    stored = store.append(event)
    (read_back,) = store.read_stream(user)

    assert stored.global_seq >= 1
    assert read_back.event_id == event.event_id
    assert read_back.occurred_at == event.occurred_at
    assert read_back.occurred_at.utcoffset() is not None
    assert read_back.payload == {"title": "Morning run", "category": "health", "note": None}


def test_ordering_and_read_all(session: Session) -> None:
    store = EventStore(session)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    first = store.append(_event(user_a, title="a1"))
    second = store.append(_event(user_b, title="b1"))
    third = store.append(_event(user_a, title="a2"))

    seqs = [e.global_seq for e in store.read_all()]
    assert seqs == sorted(seqs)
    assert seqs == [first.global_seq, second.global_seq, third.global_seq]


def test_user_isolation(session: Session) -> None:
    store = EventStore(session)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    store.append(_event(user_a))
    store.append(_event(user_b))

    stream_a = store.read_stream(user_a)

    assert len(stream_a) == 1
    assert stream_a[0].user_id == user_a


def test_duplicate_event_rejected(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    event = _event(user)
    store.append(event)

    with pytest.raises(DuplicateEventError):
        store.append(event)

    assert len(store.read_all()) == 1


def test_pagination(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    stored = [store.append(_event(user, title=f"e{i}")) for i in range(5)]

    page = store.read_stream(user, limit=2, after_seq=stored[1].global_seq)

    assert [e.global_seq for e in page] == [stored[2].global_seq, stored[3].global_seq]


def test_store_is_append_only() -> None:
    assert not hasattr(EventStore, "update")
    assert not hasattr(EventStore, "delete")


def test_provenance_raw_record_id_round_trips(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    raw_id = uuid.uuid4()
    event = LifeEventRecorded(
        user_id=user,
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source="calendar",
        correlation_id="corr-1",
        raw_record_id=raw_id,
        payload=LifeEventRecordedPayload(title="Imported", category="calendar"),
    )
    store.append(event)

    (stored,) = store.read_stream(user)
    assert stored.raw_record_id == raw_id
    assert stored.rehydrate(LifeEventRecorded).raw_record_id == raw_id


def test_manual_event_has_no_provenance(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    store.append(_event(user))

    (stored,) = store.read_stream(user)
    assert stored.raw_record_id is None


def test_rehydrate_to_typed_event(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    event = _event(user, title="Yoga")
    store.append(event)

    (stored,) = store.read_stream(user)
    rebuilt = stored.rehydrate(LifeEventRecorded)

    assert rebuilt == event
    assert rebuilt.payload.title == "Yoga"
