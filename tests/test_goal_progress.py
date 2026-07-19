"""Tests for goal progress from domain events (T5.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService
from mylife.goals import GoalProgressService, GoalsService
from mylife.health import HealthService

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


def test_net_worth_progress(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    FinanceService(session, bus).record_valuation(
        user, account.account_id, 600000, "BRL", now=NOW, correlation_id="c"
    )
    goal = GoalsService(session, bus).create_goal(
        user, "Fund", "net_worth", 1000000, "BRL", currency="BRL", now=NOW, correlation_id="c"
    )

    progress = GoalProgressService(session).progress(user, goal)
    assert progress.current_value == 600000
    assert progress.progress_ratio == 0.6
    assert progress.achieved is False
    assert progress.source == "metric"
    assert progress.evidence  # the finance events


def test_workout_minutes_progress_achieved(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    HealthService(session, bus).record_workout(user, NOW, "run", 40, correlation_id="c")
    HealthService(session, bus).record_workout(user, NOW, "bike", 80, correlation_id="c")
    goal = GoalsService(session, bus).create_goal(
        user, "Move", "workout_minutes", 100, "min", now=NOW, correlation_id="c"
    )

    progress = GoalProgressService(session).progress(user, goal)
    assert progress.current_value == 120
    assert progress.achieved is True
    assert progress.progress_ratio == 1.2


def test_workout_distance_progress(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    HealthService(session, bus).record_workout(
        user, NOW, "run", 42, distance_meters=8000, correlation_id="c"
    )
    goal = GoalsService(session, bus).create_goal(
        user, "Distance", "workout_distance", 100000, "m", now=NOW, correlation_id="c"
    )

    progress = GoalProgressService(session).progress(user, goal)
    assert progress.current_value == 8000


def test_spend_progress(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    FinanceService(session, bus).record_expense(
        user, account.account_id, 4599, "BRL", "Coffee", now=NOW, correlation_id="c"
    )
    goal = GoalsService(session, bus).create_goal(
        user, "Budget", "spend", 10000, "BRL", currency="BRL", now=NOW, correlation_id="c"
    )

    progress = GoalProgressService(session).progress(user, goal)
    assert progress.current_value == 4599


def test_unknown_metric_falls_back_to_milestone(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    goal = GoalsService(session, bus).create_goal(
        user, "Custom", "reading_pages", 1000, "pages", now=NOW, correlation_id="c"
    )
    milestone = GoalsService(session, bus).record_milestone(
        user, goal.goal_id, 250, now=NOW, correlation_id="c"
    )

    progress = GoalProgressService(session).progress(user, goal)
    assert progress.current_value == 250
    assert progress.source == "milestone"
    assert progress.evidence == [milestone.event_id]


def test_progress_all_and_scoping(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    other = uuid.uuid4()
    GoalsService(session, bus).create_goal(
        user, "A", "reading_pages", 100, "pages", now=NOW, correlation_id="c"
    )
    GoalsService(session, bus).create_goal(
        other, "B", "reading_pages", 100, "pages", now=NOW, correlation_id="c"
    )

    all_progress = GoalProgressService(session).progress_all(user)
    assert len(all_progress) == 1
