"""Tests for the bill due-date alert scanner and service (T4.8)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import BillAlertScanner, BillAlertsService, BillsService, FinanceService
from mylife.identity import IdentityService
from mylife.notifications import NotificationPreferenceService

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


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
def bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
def user_id(session: Session, bus: InProcessEventBus) -> uuid.UUID:
    user = IdentityService(session, bus).register_user(
        "ada@example.com", "Ada", password="s3cretpw", now=NOW, correlation_id="c"
    )
    return user.user_id


@pytest.fixture
def account_id(session: Session, bus: InProcessEventBus, user_id: uuid.UUID) -> uuid.UUID:
    account = FinanceService(session, bus).create_account(user_id, "Checking", "BRL", now=NOW)
    return account.account_id


def _register_bill(
    session: Session,
    bus: InProcessEventBus,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    due_day: int,
    *,
    registered_at: datetime = NOW,
) -> uuid.UUID:
    bill = BillsService(session, bus).register_bill(
        user_id,
        account_id,
        "Aluguel",
        250000,
        "BRL",
        recurrence="monthly",
        due_day=due_day,
        now=registered_at,
        correlation_id="c",
    )
    return bill.bill_id


def test_scanner_flags_due_in_3_1_0_days(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    # NOW is 2026-09-21; due on the 24th (in 3 days) should be flagged due_soon.
    _register_bill(session, bus, user_id, account_id, due_day=24)

    alerts = BillAlertScanner(session).scan(user_id, now=NOW)

    assert len(alerts) == 1
    assert alerts[0].reason == "due_soon"
    assert alerts[0].due_at == datetime(2026, 9, 24, tzinfo=UTC)
    assert len(alerts[0].evidence) == 1


def test_scanner_ignores_bill_due_outside_window(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    # Due on the 30th — 9 days out, outside the 3/1/0-day due-soon window.
    _register_bill(session, bus, user_id, account_id, due_day=30)

    alerts = BillAlertScanner(session).scan(user_id, now=NOW)

    assert alerts == []


_REGISTERED_BEFORE_SEP = datetime(2026, 9, 1, tzinfo=UTC)


def test_scanner_flags_overdue_unpaid(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    # Registered before its due date (the 5th, 16 days before NOW) — unpaid.
    _register_bill(
        session, bus, user_id, account_id, due_day=5, registered_at=_REGISTERED_BEFORE_SEP
    )

    alerts = BillAlertScanner(session).scan(user_id, now=NOW)

    assert len(alerts) == 1
    assert alerts[0].reason == "overdue"


def test_scanner_excludes_paid_occurrence(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    bill_id = _register_bill(
        session, bus, user_id, account_id, due_day=5, registered_at=_REGISTERED_BEFORE_SEP
    )
    BillsService(session, bus).pay_bill(
        user_id, bill_id, datetime(2026, 9, 5, tzinfo=UTC), now=NOW, correlation_id="c"
    )

    alerts = BillAlertScanner(session).scan(user_id, now=NOW)

    assert alerts == []


class _RecordingChannel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> str | None:
        self.calls.append((recipient, subject, body))
        return "id"


def test_alerts_service_sends_email_by_default(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    _register_bill(
        session, bus, user_id, account_id, due_day=5, registered_at=_REGISTERED_BEFORE_SEP
    )
    email_channel = _RecordingChannel()

    outcomes = BillAlertsService(session, bus, {"email": email_channel}).run(
        user_id, now=NOW, correlation_id="c"
    )

    assert len(outcomes) == 1
    assert outcomes[0].channel == "email"
    assert outcomes[0].recipient == "ada@example.com"
    assert len(email_channel.calls) == 1


def test_alerts_service_sends_whatsapp_only_when_enabled_and_phone_set(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    _register_bill(
        session, bus, user_id, account_id, due_day=5, registered_at=_REGISTERED_BEFORE_SEP
    )
    NotificationPreferenceService(session).set(
        user_id,
        email_enabled=False,
        whatsapp_enabled=True,
        whatsapp_phone="+5511999999999",
        now=NOW,
    )
    whatsapp_channel = _RecordingChannel()

    outcomes = BillAlertsService(session, bus, {"whatsapp": whatsapp_channel}).run(
        user_id, now=NOW, correlation_id="c"
    )

    assert len(outcomes) == 1
    assert outcomes[0].channel == "whatsapp"
    assert outcomes[0].recipient == "+5511999999999"


def test_alerts_service_no_alerts_sends_nothing(
    session: Session, bus: InProcessEventBus, user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    _register_bill(session, bus, user_id, account_id, due_day=30)  # outside window

    outcomes = BillAlertsService(session, bus, {"email": _RecordingChannel()}).run(
        user_id, now=NOW, correlation_id="c"
    )

    assert outcomes == []


def test_alerts_service_unknown_user_returns_empty(
    session: Session, bus: InProcessEventBus
) -> None:
    outcomes = BillAlertsService(session, bus, {"email": _RecordingChannel()}).run(
        uuid.uuid4(), now=NOW, correlation_id="c"
    )

    assert outcomes == []
