"""Tests for event corrections (T1.5).

Runs against a shared in-memory SQLite database.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    EventCorrected,
    EventStore,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    correct_event,
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


def _original(user: uuid.UUID) -> LifeEventRecorded:
    return LifeEventRecorded(
        user_id=user,
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source="manual",
        correlation_id="corr-1",
        payload=LifeEventRecordedPayload(title="Wrong title", category="health"),
    )


def test_correction_references_original_and_preserves_it(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    original = store.append(_original(user))

    correction = correct_event(
        original.event_id,
        user_id=user,
        reason="typo in title",
        source="manual",
        correlation_id="corr-2",
        occurred_at=datetime(2026, 7, 18, 13, 0, tzinfo=UTC),
    )
    stored_correction = store.append(correction)

    stream = store.read_stream(user)
    # Original still present and unchanged; correction is a separate row.
    assert [e.event_id for e in stream] == [original.event_id, stored_correction.event_id]
    assert stream[0].payload == {"title": "Wrong title", "category": "health", "note": None}
    assert stream[0].corrects_event_id is None
    assert stream[1].corrects_event_id == original.event_id
    assert stream[1].event_type == "timeline.event_corrected"


def test_read_corrections_returns_only_matching(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    original = store.append(_original(user))
    store.append(_original(user))  # unrelated event

    store.append(
        correct_event(
            original.event_id,
            user_id=user,
            reason="bad data",
            source="manual",
            correlation_id="c",
            occurred_at=datetime(2026, 7, 18, 14, 0, tzinfo=UTC),
        )
    )

    corrections = store.read_corrections(original.event_id)
    assert len(corrections) == 1
    assert corrections[0].corrects_event_id == original.event_id


def test_domain_event_can_supersede_and_round_trips(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    original = store.append(_original(user))

    replacement = LifeEventRecorded(
        user_id=user,
        occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        source="manual",
        correlation_id="corr-3",
        corrects_event_id=original.event_id,
        payload=LifeEventRecordedPayload(title="Right title", category="health"),
    )
    store.append(replacement)

    (correction,) = store.read_corrections(original.event_id)
    rebuilt = correction.rehydrate(LifeEventRecorded)
    assert rebuilt.corrects_event_id == original.event_id
    assert rebuilt.payload.title == "Right title"


def test_correction_round_trips_as_typed_event(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    original = store.append(_original(user))
    correction = correct_event(
        original.event_id,
        user_id=user,
        reason="retracted",
        note="entered by mistake",
        source="manual",
        correlation_id="c",
        occurred_at=datetime(2026, 7, 18, 15, 0, tzinfo=UTC),
    )
    store.append(correction)

    (stored,) = store.read_corrections(original.event_id)
    rebuilt = stored.rehydrate(EventCorrected)
    assert rebuilt == correction
    assert rebuilt.payload.reason == "retracted"


def test_ordinary_event_has_no_correction_link(session: Session) -> None:
    store = EventStore(session)
    user = uuid.uuid4()
    store.append(_original(user))

    (stored,) = store.read_stream(user)
    assert stored.corrects_event_id is None
