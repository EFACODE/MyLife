"""Tests for the retrieval-grounded query service (T7.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.insight import INSIGHT_GENERATED
from mylife.assistant.query import AssistantQueryService
from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService

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


def _seed_food_expense(session: Session, user: uuid.UUID) -> uuid.UUID:
    bus = InProcessEventBus()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    txn = FinanceService(session, bus).record_expense(
        user,
        account.account_id,
        4599,
        "BRL",
        "Lunch",
        category="food",
        now=NOW,
        correlation_id="c",
    )
    return txn.event_id


def test_grounded_answer_records_insight(session: Session) -> None:
    user = uuid.uuid4()
    event_id = _seed_food_expense(session, user)
    service = AssistantQueryService(session, InProcessEventBus())

    answer = service.answer(user, "how much on food?", now=NOW, correlation_id="c")
    assert answer.grounded is True
    assert answer.insight is not None
    assert event_id in answer.insight.evidence
    assert answer.evidence_count >= 1
    assert "timeline-keyword" in answer.tools_used
    # A grounded answer is persisted as an insight event.
    assert INSIGHT_GENERATED in [e.event_type for e in EventStore(session).read_stream(user)]


def test_refuses_without_evidence(session: Session) -> None:
    user = uuid.uuid4()
    _seed_food_expense(session, user)
    service = AssistantQueryService(session, InProcessEventBus())

    answer = service.answer(user, "quantum chromodynamics lecture", now=NOW, correlation_id="c")
    assert answer.grounded is False
    assert answer.insight is None
    assert answer.evidence_count == 0
    # Refusal records no insight.
    assert INSIGHT_GENERATED not in [e.event_type for e in EventStore(session).read_stream(user)]


def test_grounding_is_user_scoped(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    _seed_food_expense(session, other)  # only the other user has food data
    service = AssistantQueryService(session, InProcessEventBus())

    answer = service.answer(user, "how much on food?", now=NOW, correlation_id="c")
    assert answer.grounded is False


def test_confidence_calibrated_and_bounded(session: Session) -> None:
    user = uuid.uuid4()
    _seed_food_expense(session, user)
    service = AssistantQueryService(session, InProcessEventBus())

    answer = service.answer(user, "food", now=NOW, correlation_id="c")
    assert answer.insight is not None
    assert 0.0 < answer.insight.confidence <= 1.0
