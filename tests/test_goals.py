"""Tests for the goals service (T5.1)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.goals import GOAL_CREATED, MILESTONE_REACHED, GoalsService, UnknownGoalError

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


@pytest.fixture
def goals(session: Session) -> GoalsService:
    return GoalsService(session, InProcessEventBus())


def test_create_goal_emits_event_and_is_listed(goals: GoalsService, session: Session) -> None:
    user = uuid.uuid4()
    goal = goals.create_goal(
        user,
        "Emergency fund",
        "net_worth",
        1000000,
        "BRL",
        currency="brl",
        now=NOW,
        correlation_id="c",
    )

    assert goal.target_value == 1000000
    assert goal.currency == "BRL"
    assert [g.goal_id for g in goals.list_goals(user)] == [goal.goal_id]
    assert [e.event_type for e in EventStore(session).read_stream(user)] == [GOAL_CREATED]


def test_goal_scoped_to_user(goals: GoalsService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    goal = goals.create_goal(other, "Theirs", "net_worth", 10, "BRL", now=NOW, correlation_id="c")
    assert goals.get_goal(user, goal.goal_id) is None
    assert goals.list_goals(user) == []


def test_record_milestone_and_list(goals: GoalsService, session: Session) -> None:
    user = uuid.uuid4()
    goal = goals.create_goal(
        user, "Run 500km", "distance", 500000, "m", now=NOW, correlation_id="c"
    )

    goals.record_milestone(user, goal.goal_id, 100000, note="month 1", now=NOW, correlation_id="c")
    goals.record_milestone(user, goal.goal_id, 250000, note="month 2", now=NOW, correlation_id="c")

    milestones = goals.list_milestones(user, goal.goal_id)
    assert [m.value for m in milestones] == [250000, 100000]  # newest first
    types = [e.event_type for e in EventStore(session).read_stream(user)]
    assert types == [GOAL_CREATED, MILESTONE_REACHED, MILESTONE_REACHED]


def test_record_milestone_unknown_goal_raises(goals: GoalsService) -> None:
    user = uuid.uuid4()
    with pytest.raises(UnknownGoalError):
        goals.record_milestone(user, uuid.uuid4(), 100, now=NOW, correlation_id="c")


def test_record_milestone_foreign_goal_raises(goals: GoalsService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    goal = goals.create_goal(other, "Theirs", "net_worth", 10, "BRL", now=NOW, correlation_id="c")
    with pytest.raises(UnknownGoalError):
        goals.record_milestone(user, goal.goal_id, 5, now=NOW, correlation_id="c")


def test_milestones_filtered_by_goal(goals: GoalsService) -> None:
    user = uuid.uuid4()
    a = goals.create_goal(user, "A", "net_worth", 10, "BRL", now=NOW, correlation_id="c")
    b = goals.create_goal(user, "B", "distance", 10, "m", now=NOW, correlation_id="c")
    goals.record_milestone(user, a.goal_id, 1, now=NOW, correlation_id="c")
    goals.record_milestone(user, b.goal_id, 2, now=NOW, correlation_id="c")

    assert [m.value for m in goals.list_milestones(user, a.goal_id)] == [1]
    assert [m.value for m in goals.list_milestones(user, b.goal_id)] == [2]
