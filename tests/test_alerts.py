"""Tests for governed alerts & weekly insights (T7.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.alerts import (
    AlertsService,
    AtRiskGoalRule,
    OverspendRule,
    ShortSleepRule,
)
from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService
from mylife.goals import GoalsService
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


def test_overspend_rule_fires_with_evidence(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    finance = FinanceService(session, bus)
    account = finance.create_account(user, "Checking", "BRL", now=NOW)
    # Small prior week, big current week.
    finance.record_expense(
        user,
        account.account_id,
        1000,
        "BRL",
        "old",
        now=NOW - timedelta(days=10),
        correlation_id="c",
    )
    txn = finance.record_expense(
        user,
        account.account_id,
        500000,
        "BRL",
        "big",
        now=NOW - timedelta(days=1),
        correlation_id="c",
    )

    results = OverspendRule().evaluate(session, user, NOW)
    assert len(results) == 1
    assert txn.event_id in results[0].evidence


def test_overspend_rule_silent_when_stable(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    finance = FinanceService(session, bus)
    account = finance.create_account(user, "Checking", "BRL", now=NOW)
    finance.record_expense(
        user,
        account.account_id,
        10000,
        "BRL",
        "prior",
        now=NOW - timedelta(days=10),
        correlation_id="c",
    )
    finance.record_expense(
        user,
        account.account_id,
        10000,
        "BRL",
        "current",
        now=NOW - timedelta(days=1),
        correlation_id="c",
    )
    assert OverspendRule().evaluate(session, user, NOW) == []


def test_at_risk_goal_rule(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    GoalsService(session, bus).create_goal(
        user,
        "Marathon",
        "reading_pages",
        100,
        "pages",
        due_at=NOW - timedelta(days=1),
        now=NOW - timedelta(days=30),
        correlation_id="c",
    )
    results = AtRiskGoalRule().evaluate(session, user, NOW)
    assert len(results) == 1
    assert "Marathon" in results[0].claim
    # Evidence is the goal's creation event.
    from mylife.core.events import EventStore

    created = next(
        e for e in EventStore(session).read_stream(user) if e.event_type == "goals.goal_created"
    )
    assert results[0].evidence == [created.event_id]


def test_short_sleep_rule(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    health = HealthService(session, bus)
    health.record_sleep(user, NOW - timedelta(days=1), 300, correlation_id="c")
    health.record_sleep(user, NOW - timedelta(days=2), 320, correlation_id="c")
    health.record_sleep(user, NOW - timedelta(days=3), 480, correlation_id="c")  # not short

    results = ShortSleepRule().evaluate(session, user, NOW)
    assert len(results) == 1
    assert len(results[0].evidence) == 2  # only the two short nights


def test_run_records_insights_and_empty_when_quiet(session: Session) -> None:
    user = uuid.uuid4()
    quiet = uuid.uuid4()
    bus = InProcessEventBus()
    GoalsService(session, bus).create_goal(
        user,
        "Late",
        "reading_pages",
        100,
        "pages",
        due_at=NOW - timedelta(days=1),
        now=NOW - timedelta(days=30),
        correlation_id="c",
    )

    insights = AlertsService(session, bus).run(user, now=NOW, correlation_id="c")
    assert len(insights) == 1
    assert insights[0].generator == "alerts-v1"
    # A user with no data triggers nothing.
    assert AlertsService(session, bus).run(quiet, now=NOW, correlation_id="c") == []
