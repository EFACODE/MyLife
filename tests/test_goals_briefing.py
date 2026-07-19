"""Tests for goals in the cross-domain briefing (T5.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.briefing import BriefingService
from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService
from mylife.goals import GoalsService

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


def test_goal_progress_line_with_evidence(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    FinanceService(session, bus).record_valuation(
        user, account.account_id, 600000, "BRL", now=NOW, correlation_id="c"
    )
    GoalsService(session, bus).create_goal(
        user,
        "Emergency fund",
        "net_worth",
        1000000,
        "BRL",
        currency="BRL",
        now=NOW,
        correlation_id="c",
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    goal_lines = [line for line in briefing.lines if line.kind == "goal"]
    assert len(goal_lines) == 1
    assert "Emergency fund" in goal_lines[0].summary
    assert "60% toward BRL 10,000.00" in goal_lines[0].summary
    assert goal_lines[0].evidence  # progress evidence


def test_achieved_goal_marked_reached(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    GoalsService(session, bus).create_goal(
        user, "Read", "reading_pages", 100, "pages", now=NOW, correlation_id="c"
    )
    goal = GoalsService(session, bus).list_goals(user)[0]
    GoalsService(session, bus).record_milestone(
        user, goal.goal_id, 100, now=NOW, correlation_id="c"
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    goal_line = next(line for line in briefing.lines if line.kind == "goal")
    assert "reached" in goal_line.summary


def test_overdue_goal_flagged_at_risk(session: Session) -> None:
    bus = InProcessEventBus()
    user = uuid.uuid4()
    GoalsService(session, bus).create_goal(
        user,
        "Marathon",
        "reading_pages",
        100,
        "pages",
        due_at=NOW - timedelta(days=1),
        now=NOW,
        correlation_id="c",
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    insights = [line for line in briefing.lines if line.kind == "insight"]
    assert any("past its due date" in line.summary for line in insights)


def test_no_goals_leaves_briefing_unchanged(session: Session) -> None:
    briefing = BriefingService(session, InProcessEventBus()).deliver(
        uuid.uuid4(), now=NOW, correlation_id="cid"
    )
    assert [line.kind for line in briefing.lines] == ["total"]
    assert not any(line.kind == "goal" for line in briefing.lines)
