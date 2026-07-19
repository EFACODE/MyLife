"""Tests for what-if scenario simulation — ScenarioService (T8.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base
from mylife.forecast.contract import Assumption, Forecast, ForecastPoint, ForecastService
from mylife.forecast.scenario import EmptyScenarioError, ScenarioService, UnknownForecastError

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


def _base_forecast(session: Session, user: uuid.UUID) -> Forecast:
    stored = EventStore(session).append(
        LifeEventRecorded(
            user_id=user,
            occurred_at=NOW,
            source="manual",
            correlation_id="c",
            payload=LifeEventRecordedPayload(title="Salary", category="income"),
        )
    )
    session.commit()
    return ForecastService(session, InProcessEventBus()).generate(
        user,
        "cash_flow",
        "BRL_minor",
        30,
        [
            ForecastPoint(at=NOW + timedelta(days=30), value=-100000, lower=-150000, upper=-50000),
        ],
        [Assumption(name="net_flow_rate", value="steady", basis="last 90d")],
        [stored.event_id],
        0.6,
        "Rule-based; not advice.",
        method="test-v1",
        now=NOW,
        correlation_id="c",
    )


def _rel_band(point: ForecastPoint) -> float:
    return (point.upper - point.lower) / abs(point.value)


def test_simulate_scales_and_discounts_confidence(session: Session) -> None:
    user = uuid.uuid4()
    base = _base_forecast(session, user)
    service = ScenarioService(session, InProcessEventBus())

    scenario = service.simulate(user, base.forecast_id, scale=1.2, now=NOW, correlation_id="c")
    assert scenario.metric == base.metric
    assert scenario.evidence == base.evidence
    assert scenario.points[0].value == round(base.points[0].value * 1.2)
    assert scenario.confidence < base.confidence
    assert any(a.name == "scenario" for a in scenario.assumptions)


def test_simulate_widens_relative_uncertainty(session: Session) -> None:
    user = uuid.uuid4()
    base = _base_forecast(session, user)
    service = ScenarioService(session, InProcessEventBus())

    scenario = service.simulate(user, base.forecast_id, scale=1.2, now=NOW, correlation_id="c")
    assert _rel_band(scenario.points[0]) > _rel_band(base.points[0])


def test_override_replaces_assumption_by_name(session: Session) -> None:
    user = uuid.uuid4()
    base = _base_forecast(session, user)
    service = ScenarioService(session, InProcessEventBus())

    scenario = service.simulate(
        user,
        base.forecast_id,
        scale=1.0,
        overrides=[Assumption(name="net_flow_rate", value="20% higher", basis="assume a raise")],
        now=NOW,
        correlation_id="c",
    )
    rate = next(a for a in scenario.assumptions if a.name == "net_flow_rate")
    assert rate.value == "20% higher"
    # The base forecast is untouched; a new one is recorded.
    reloaded = ForecastService(session, InProcessEventBus()).get(user, base.forecast_id)
    assert reloaded is not None
    assert next(a for a in reloaded.assumptions if a.name == "net_flow_rate").value == "steady"


def test_no_op_scenario_rejected(session: Session) -> None:
    user = uuid.uuid4()
    base = _base_forecast(session, user)
    service = ScenarioService(session, InProcessEventBus())
    with pytest.raises(EmptyScenarioError):
        service.simulate(user, base.forecast_id, scale=1.0, now=NOW, correlation_id="c")


def test_unknown_base_forecast_raises(session: Session) -> None:
    service = ScenarioService(session, InProcessEventBus())
    with pytest.raises(UnknownForecastError):
        service.simulate(uuid.uuid4(), uuid.uuid4(), scale=1.5, now=NOW, correlation_id="c")
