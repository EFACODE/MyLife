"""Tests for the forecasting models — cash-flow & goal-completion (T8.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService
from mylife.forecast.contract import ForecastService
from mylife.forecast.models import (
    CashFlowForecaster,
    ForecastingService,
    GoalCompletionForecaster,
    _horizon_offsets,
)
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


def _seed_transactions(session: Session, user: uuid.UUID) -> None:
    bus = InProcessEventBus()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    for day in (2, 9, 16):
        FinanceService(session, bus).record_expense(
            user,
            account.account_id,
            50000,
            "BRL",
            "groceries",
            category="food",
            now=NOW - timedelta(days=day),
            correlation_id="c",
        )


def _seed_goal(session: Session, user: uuid.UUID) -> None:
    bus = InProcessEventBus()
    GoalsService(session, bus).create_goal(
        user,
        "Run 1000 minutes",
        "workout_minutes",
        1000,
        "minutes",
        now=NOW - timedelta(days=20),
        correlation_id="c",
    )
    HealthService(session, bus).record_workout(
        user, NOW - timedelta(days=1), "run", 200, correlation_id="c"
    )


def test_horizon_offsets_weekly_and_final() -> None:
    assert _horizon_offsets(30) == [7, 14, 21, 28, 30]
    assert _horizon_offsets(7) == [7]
    assert _horizon_offsets(5) == [5]


def test_cash_flow_forecaster_projects_with_widening_interval(session: Session) -> None:
    user = uuid.uuid4()
    _seed_transactions(session, user)

    drafts = CashFlowForecaster().draft(session, user, now=NOW, horizon_days=30)
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.metric == "cash_flow"
    assert draft.unit == "BRL_minor"
    assert draft.evidence  # cites the transactions it used
    assert {a.name for a in draft.assumptions} == {"net_flow_rate", "no_structural_change"}
    # Net flow is outflow-only here, so values are negative and the band widens.
    assert draft.points[-1].value < draft.points[0].value <= 0
    for point in draft.points:
        assert point.lower <= point.value <= point.upper
    first_band = draft.points[0].upper - draft.points[0].lower
    last_band = draft.points[-1].upper - draft.points[-1].lower
    assert last_band > first_band


def test_goal_completion_forecaster_projects_metric_value(session: Session) -> None:
    user = uuid.uuid4()
    _seed_goal(session, user)

    drafts = GoalCompletionForecaster().draft(session, user, now=NOW, horizon_days=30)
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.metric == "goal_progress"
    assert draft.unit == "minutes"
    assert draft.evidence
    assert {a.name for a in draft.assumptions} == {"accumulation_rate", "linear_extrapolation"}
    # 200 minutes over 20 days -> ~10/day; projected value grows above the current 200.
    assert draft.points[0].value > 200
    assert draft.points[-1].value > draft.points[0].value


def test_run_records_forecasts_through_the_contract(session: Session) -> None:
    user = uuid.uuid4()
    _seed_transactions(session, user)
    _seed_goal(session, user)
    bus = InProcessEventBus()

    forecasts = ForecastingService(session, bus).run(user, now=NOW, correlation_id="c")
    metrics = sorted(f.metric for f in forecasts)
    assert metrics == ["cash_flow", "goal_progress"]
    # Recorded via the contract, so they are all readable back and evidence-cited.
    stored = ForecastService(session, bus).list_forecasts(user)
    assert len(stored) == 2
    assert all(f.assumptions and f.evidence for f in stored)


def test_run_with_no_data_records_nothing(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    assert ForecastingService(session, bus).run(user, now=NOW, correlation_id="c") == []
    assert ForecastService(session, bus).list_forecasts(user) == []


def test_achieved_goal_is_not_forecast(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    GoalsService(session, bus).create_goal(
        user,
        "Tiny goal",
        "workout_minutes",
        10,
        "minutes",
        now=NOW - timedelta(days=20),
        correlation_id="c",
    )
    HealthService(session, bus).record_workout(
        user, NOW - timedelta(days=1), "run", 200, correlation_id="c"
    )
    # Current value (200) already exceeds the target (10) -> achieved -> no forecast.
    assert GoalCompletionForecaster().draft(session, user, now=NOW, horizon_days=30) == []
