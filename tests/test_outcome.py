"""Tests for feedback / outcome loops — OutcomeService (T8.4)."""

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
from mylife.forecast.outcome import OUTCOME_RECORDED, OutcomeService, UnknownForecastError

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
TARGET = NOW + timedelta(days=30)


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


def _forecast(session: Session, user: uuid.UUID) -> Forecast:
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
        [ForecastPoint(at=TARGET, value=-100000, lower=-150000, upper=-50000)],
        [Assumption(name="net_flow_rate", value="steady", basis="last 90d")],
        [stored.event_id],
        0.6,
        "Rule-based; not advice.",
        method="test-v1",
        now=NOW,
        correlation_id="c",
    )


def test_record_outcome_and_event(session: Session) -> None:
    user = uuid.uuid4()
    forecast = _forecast(session, user)
    service = OutcomeService(session, InProcessEventBus())

    outcome = service.record(
        user, forecast.forecast_id, -95000, TARGET, now=NOW, correlation_id="c"
    )
    assert outcome.forecast_id == forecast.forecast_id
    assert outcome.observed_value == -95000
    assert OUTCOME_RECORDED in [e.event_type for e in EventStore(session).read_stream(user)]
    assert [o.outcome_id for o in service.list_outcomes(user)] == [outcome.outcome_id]


def test_unknown_forecast_rejected(session: Session) -> None:
    service = OutcomeService(session, InProcessEventBus())
    with pytest.raises(UnknownForecastError):
        service.record(uuid.uuid4(), uuid.uuid4(), 100, TARGET, now=NOW, correlation_id="c")


def test_calibration_counts_a_hit_inside_the_interval(session: Session) -> None:
    user = uuid.uuid4()
    forecast = _forecast(session, user)
    service = OutcomeService(session, InProcessEventBus())
    # -95000 is inside [-150000, -50000] -> a hit; error = observed - predicted.
    service.record(user, forecast.forecast_id, -95000, TARGET, now=NOW, correlation_id="c")

    calibration = service.calibrate(user)
    assert calibration.total == 1
    assert calibration.within_interval == 1
    assert calibration.hit_rate == 1.0
    assert calibration.mean_abs_error == 5000  # |-95000 - (-100000)|
    assert calibration.records[0].predicted_value == -100000
    assert calibration.records[0].within_interval is True


def test_calibration_counts_a_miss_outside_the_interval(session: Session) -> None:
    user = uuid.uuid4()
    forecast = _forecast(session, user)
    service = OutcomeService(session, InProcessEventBus())
    # 0 is outside [-150000, -50000] -> a miss.
    service.record(user, forecast.forecast_id, 0, TARGET, now=NOW, correlation_id="c")

    calibration = service.calibrate(user)
    assert calibration.total == 1
    assert calibration.within_interval == 0
    assert calibration.hit_rate == 0.0
    assert calibration.records[0].within_interval is False


def test_calibration_empty_report(session: Session) -> None:
    service = OutcomeService(session, InProcessEventBus())
    calibration = service.calibrate(uuid.uuid4())
    assert calibration.total == 0
    assert calibration.hit_rate == 0.0
    assert calibration.mean_abs_error == 0
    assert calibration.records == []


def test_outcomes_are_user_scoped(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    forecast = _forecast(session, user)
    service = OutcomeService(session, InProcessEventBus())
    service.record(user, forecast.forecast_id, -95000, TARGET, now=NOW, correlation_id="c")

    assert service.list_outcomes(other) == []
    assert service.calibrate(other).total == 0
