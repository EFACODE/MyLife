"""Tests for the AI evidence contract — InsightService (T7.1)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.insight import (
    INSIGHT_GENERATED,
    EmptyEvidenceError,
    InsightService,
    UnknownEvidenceError,
    UnknownInsightError,
)
from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


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


def _event(session: Session, user: uuid.UUID) -> uuid.UUID:
    stored = EventStore(session).append(
        LifeEventRecorded(
            user_id=user,
            occurred_at=NOW,
            source="manual",
            correlation_id="c",
            payload=LifeEventRecordedPayload(title="Lunch", category="food"),
        )
    )
    session.commit()
    return stored.event_id


def _generate(service: InsightService, user: uuid.UUID, evidence: list[uuid.UUID]):
    return service.generate(
        user,
        "You spent on food",
        "A food transaction was recorded",
        evidence,
        0.8,
        "Based only on the cited event",
        next_safe_action="Review it",
        generator="test-v1",
        now=NOW,
        correlation_id="c",
    )


def test_generate_records_insight_and_event(session: Session) -> None:
    user = uuid.uuid4()
    evidence = [_event(session, user)]
    service = InsightService(session, InProcessEventBus())

    insight = _generate(service, user, evidence)
    assert insight.evidence == evidence
    assert insight.confidence == 0.8
    assert insight.limitations
    assert INSIGHT_GENERATED in [e.event_type for e in EventStore(session).read_stream(user)]

    resolved = service.resolve_evidence(user, insight.insight_id)
    assert [e.event_id for e in resolved] == evidence


def test_empty_evidence_rejected(session: Session) -> None:
    service = InsightService(session, InProcessEventBus())
    with pytest.raises(EmptyEvidenceError):
        _generate(service, uuid.uuid4(), [])


def test_foreign_evidence_rejected(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    foreign_event = _event(session, other)
    service = InsightService(session, InProcessEventBus())
    with pytest.raises(UnknownEvidenceError):
        _generate(service, user, [foreign_event])
    # Nothing was recorded for the user.
    assert service.list_insights(user) == []


def test_list_and_get_scoped(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    evidence = [_event(session, user)]
    service = InsightService(session, InProcessEventBus())
    insight = _generate(service, user, evidence)

    assert [i.insight_id for i in service.list_insights(user)] == [insight.insight_id]
    assert service.get(other, insight.insight_id) is None


def test_resolve_evidence_unknown_insight_raises(session: Session) -> None:
    service = InsightService(session, InProcessEventBus())
    with pytest.raises(UnknownInsightError):
        service.resolve_evidence(uuid.uuid4(), uuid.uuid4())
