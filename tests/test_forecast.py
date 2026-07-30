"""Tests for the forecast contract — ForecastService (T8.1)."""

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
from mylife.forecast.contract import (
    FORECAST_GENERATED,
    Assumption,
    EmptyEvidenceError,
    EmptyForecastError,
    ForecastPoint,
    ForecastService,
    InvalidIntervalError,
    MissingAssumptionsError,
    UnknownEvidenceError,
    UnknownForecastError,
)

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
            payload=LifeEventRecordedPayload(title="Salary", category="income"),
        )
    )
    session.commit()
    return stored.event_id


def _point(**overrides: object) -> ForecastPoint:
    base: dict[str, object] = {
        "at": NOW + timedelta(days=30),
        "value": -120000,
        "lower": -180000,
        "upper": -60000,
    }
    base.update(overrides)
    return ForecastPoint(**base)  # type: ignore[arg-type]


def _assumption() -> Assumption:
    return Assumption(
        name="recurring_income",
        value="steady at last 90d average",
        basis="3 salary credits, low variance",
    )


def _generate(
    service: ForecastService,
    user: uuid.UUID,
    evidence: list[uuid.UUID],
    *,
    points: list[ForecastPoint] | None = None,
    assumptions: list[Assumption] | None = None,
):
    return service.generate(
        user,
        "cash_flow",
        "BRL_minor",
        30,
        points if points is not None else [_point()],
        assumptions if assumptions is not None else [_assumption()],
        evidence,
        0.6,
        "Assumes no one-off large expenses in the window",
        method="test-v1",
        now=NOW,
        correlation_id="c",
    )


def test_generate_records_forecast_and_event(session: Session) -> None:
    user = uuid.uuid4()
    evidence = [_event(session, user)]
    service = ForecastService(session, InProcessEventBus())

    forecast = _generate(service, user, evidence)
    assert forecast.evidence == evidence
    assert forecast.confidence == 0.6
    assert forecast.limitations
    assert [a.name for a in forecast.assumptions] == ["recurring_income"]
    assert forecast.points[0].value == -120000
    assert FORECAST_GENERATED in [e.event_type for e in EventStore(session).read_stream(user)]

    resolved = service.resolve_evidence(user, forecast.forecast_id)
    assert [e.event_id for e in resolved] == evidence


def test_missing_assumptions_rejected(session: Session) -> None:
    user = uuid.uuid4()
    evidence = [_event(session, user)]
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(MissingAssumptionsError):
        _generate(service, user, evidence, assumptions=[])
    assert service.list_forecasts(user) == []


def test_empty_points_rejected(session: Session) -> None:
    user = uuid.uuid4()
    evidence = [_event(session, user)]
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(EmptyForecastError):
        _generate(service, user, evidence, points=[])


def test_malformed_interval_rejected(session: Session) -> None:
    user = uuid.uuid4()
    evidence = [_event(session, user)]
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(InvalidIntervalError):
        _generate(service, user, evidence, points=[_point(value=0, lower=10, upper=20)])
    assert service.list_forecasts(user) == []


def test_empty_evidence_rejected(session: Session) -> None:
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(EmptyEvidenceError):
        _generate(service, uuid.uuid4(), [])


def test_foreign_evidence_rejected(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    foreign_event = _event(session, other)
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(UnknownEvidenceError):
        _generate(service, user, [foreign_event])
    assert service.list_forecasts(user) == []


def test_list_and_get_scoped(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    evidence = [_event(session, user)]
    service = ForecastService(session, InProcessEventBus())
    forecast = _generate(service, user, evidence)

    assert [f.forecast_id for f in service.list_forecasts(user)] == [forecast.forecast_id]
    assert service.get(other, forecast.forecast_id) is None


def test_resolve_evidence_unknown_forecast_raises(session: Session) -> None:
    service = ForecastService(session, InProcessEventBus())
    with pytest.raises(UnknownForecastError):
        service.resolve_evidence(uuid.uuid4(), uuid.uuid4())
