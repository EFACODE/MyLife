"""Tests for the cross-domain briefing v2 (T4.6)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.assistant.briefing import BriefingLine, BriefingService
from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base
from mylife.finance import FinanceService
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


def _calendar_event(session: Session, user: uuid.UUID, *, hours_ago: float) -> uuid.UUID:
    event = LifeEventRecorded(
        user_id=user,
        occurred_at=NOW - timedelta(hours=hours_ago),
        source="calendar",
        correlation_id="c",
        payload=LifeEventRecordedPayload(title="Meeting", category="work"),
    )
    stored = EventStore(session).append(event)
    session.commit()
    return stored.event_id


def _lines_by_kind(lines: list[BriefingLine]) -> dict[str, list[BriefingLine]]:
    grouped: dict[str, list[BriefingLine]] = {}
    for line in lines:
        grouped.setdefault(line.kind, []).append(line)
    return grouped


def test_cross_domain_lines_and_combined_insight(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    sleep = HealthService(session, bus).record_sleep(
        user, NOW - timedelta(hours=8), 300, quality="poor", correlation_id="c"
    )
    cal = [_calendar_event(session, user, hours_ago=h) for h in (1, 2, 3)]
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    FinanceService(session, bus).record_expense(
        user,
        account.account_id,
        125000,
        "BRL",
        "Dinner",
        now=NOW - timedelta(hours=5),
        correlation_id="c",
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    by_kind = _lines_by_kind(briefing.lines)

    # Domain summaries.
    assert by_kind["sleep"][0].summary == "Slept 5h 0m last night"
    assert by_kind["sleep"][0].evidence == [sleep.event_id]
    assert "3 meetings" in by_kind["calendar"][0].summary
    assert set(by_kind["calendar"][0].evidence) == set(cal)
    assert by_kind["spend"][0].summary == "BRL 1,250.00 out in the last 24h"

    # Combined insight cites the sleep event and all calendar events.
    combined = next(line for line in by_kind["insight"] if "Short sleep" in line.summary)
    assert set(combined.evidence) == {sleep.event_id, *cal}


def test_no_workout_insight_only_on_active_day(session: Session) -> None:
    user = uuid.uuid4()
    _calendar_event(session, user, hours_ago=2)  # active day, no workout

    briefing = BriefingService(session, InProcessEventBus()).deliver(
        user, now=NOW, correlation_id="cid"
    )
    insights = [line for line in briefing.lines if line.kind == "insight"]
    assert any("No workout logged" in line.summary for line in insights)


def test_spend_baseline_below_average(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    # Bigger spend in the previous window (25–48h ago) than in the current one.
    FinanceService(session, bus).record_expense(
        user,
        account.account_id,
        500000,
        "BRL",
        "Old",
        now=NOW - timedelta(hours=30),
        correlation_id="c",
    )
    FinanceService(session, bus).record_expense(
        user,
        account.account_id,
        10000,
        "BRL",
        "New",
        now=NOW - timedelta(hours=2),
        correlation_id="c",
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    baseline = next(
        line for line in briefing.lines if line.kind == "insight" and "Spending" in line.summary
    )
    assert "below your recent average" in baseline.summary


def test_workout_line_present(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    HealthService(session, bus).record_workout(
        user, NOW - timedelta(hours=3), "run", 42, correlation_id="c"
    )

    briefing = BriefingService(session, bus).deliver(user, now=NOW, correlation_id="cid")
    training = [line for line in briefing.lines if line.kind == "training"]
    assert training and "1 workout" in training[0].summary
    assert "42 min" in training[0].summary
