"""Tests for the bills service and report (T4.7)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.finance import (
    BILL_CANCELLED,
    BILL_PAID,
    BILL_REGISTERED,
    BILL_UPDATED,
    BillsReportService,
    BillsService,
    FinanceService,
    InvalidBillRecurrenceError,
    UnknownAccountError,
    UnknownBillError,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
USER = uuid.uuid4()


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
def bills(session: Session, bus: InProcessEventBus) -> BillsService:
    return BillsService(session, bus)


@pytest.fixture
def account_id(session: Session, bus: InProcessEventBus) -> uuid.UUID:
    account = FinanceService(session, bus).create_account(USER, "Checking", "BRL", now=NOW)
    return account.account_id


def test_register_monthly_bill_and_get(bills: BillsService, account_id: uuid.UUID) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        250000,
        "brl",
        recurrence="monthly",
        category="moradia",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )

    assert bill.currency == "BRL"
    assert bill.amount_minor == 250000
    assert bill.active is True
    assert bills.get_bill(USER, bill.bill_id) == bill


def test_register_requires_consistent_recurrence(
    bills: BillsService, account_id: uuid.UUID
) -> None:
    with pytest.raises(InvalidBillRecurrenceError):
        bills.register_bill(
            USER,
            account_id,
            "Aluguel",
            1000,
            "BRL",
            recurrence="monthly",
            now=NOW,
            correlation_id="c",
        )
    with pytest.raises(InvalidBillRecurrenceError):
        bills.register_bill(
            USER, account_id, "IPTU", 1000, "BRL", recurrence="once", now=NOW, correlation_id="c"
        )


def test_register_unknown_account_raises(bills: BillsService) -> None:
    with pytest.raises(UnknownAccountError):
        bills.register_bill(
            USER,
            uuid.uuid4(),
            "Aluguel",
            1000,
            "BRL",
            recurrence="monthly",
            due_day=5,
            now=NOW,
            correlation_id="c",
        )


def test_update_bill_emits_event_and_changes_fields(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Netflix",
        4990,
        "BRL",
        recurrence="monthly",
        due_day=10,
        now=NOW,
        correlation_id="c",
    )

    updated = bills.update_bill(
        USER,
        bill.bill_id,
        "Netflix Premium",
        5990,
        "BRL",
        recurrence="monthly",
        due_day=15,
        max_occurrences=6,
        now=NOW,
        correlation_id="c",
    )

    assert updated.payee == "Netflix Premium"
    assert updated.amount_minor == 5990
    assert updated.due_day == 15
    assert updated.max_occurrences == 6
    assert bills.get_bill(USER, bill.bill_id) == updated
    events = [e.event_type for e in EventStore(session).read_stream(USER)]
    assert events == [BILL_REGISTERED, BILL_UPDATED]


def test_update_requires_consistent_recurrence(bills: BillsService, account_id: uuid.UUID) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    with pytest.raises(InvalidBillRecurrenceError):
        bills.update_bill(
            USER,
            bill.bill_id,
            "Aluguel",
            1000,
            "BRL",
            recurrence="monthly",
            now=NOW,
            correlation_id="c",
        )


def test_update_foreign_bill_raises(bills: BillsService, account_id: uuid.UUID) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    other = uuid.uuid4()
    with pytest.raises(UnknownBillError):
        bills.update_bill(
            other,
            bill.bill_id,
            "Aluguel",
            1000,
            "BRL",
            recurrence="monthly",
            due_day=5,
            now=NOW,
            correlation_id="c",
        )


def test_cancel_bill_emits_event_and_flips_active(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Netflix",
        4990,
        "BRL",
        recurrence="monthly",
        due_day=10,
        now=NOW,
        correlation_id="c",
    )

    cancelled = bills.cancel_bill(USER, bill.bill_id, now=NOW, correlation_id="c")

    assert cancelled.active is False
    events = [e.event_type for e in EventStore(session).read_stream(USER)]
    assert events == [BILL_REGISTERED, BILL_CANCELLED]


def test_cancel_foreign_bill_raises(bills: BillsService, account_id: uuid.UUID) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Netflix",
        4990,
        "BRL",
        recurrence="monthly",
        due_day=10,
        now=NOW,
        correlation_id="c",
    )
    other = uuid.uuid4()
    with pytest.raises(UnknownBillError):
        bills.cancel_bill(other, bill.bill_id, now=NOW, correlation_id="c")


def test_pay_bill_defaults_amount_and_paid_at(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        250000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    due_at = datetime(2026, 9, 5, tzinfo=UTC)

    payment = bills.pay_bill(USER, bill.bill_id, due_at, now=NOW, correlation_id="c")

    assert payment.amount_minor == 250000
    assert payment.paid_at == NOW
    assert payment.period == "2026-09-05"
    events = [e.event_type for e in EventStore(session).read_stream(USER)]
    assert events == [BILL_REGISTERED, BILL_PAID]


def test_pay_unknown_bill_raises(bills: BillsService) -> None:
    with pytest.raises(UnknownBillError):
        bills.pay_bill(USER, uuid.uuid4(), NOW, now=NOW, correlation_id="c")


def test_report_flags_paid_unpaid_and_overdue(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    monthly = bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        250000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    once = bills.register_bill(
        USER,
        account_id,
        "IPTU",
        50000,
        "BRL",
        recurrence="once",
        due_at=datetime(2026, 9, 20, tzinfo=UTC),
        now=NOW,
        correlation_id="c",
    )
    bills.pay_bill(
        USER, monthly.bill_id, datetime(2026, 8, 5, tzinfo=UTC), now=NOW, correlation_id="c"
    )

    report = BillsReportService(session).list_occurrences(
        USER,
        due_from=datetime(2026, 8, 1, tzinfo=UTC),
        due_to=datetime(2026, 9, 30, tzinfo=UTC),
        as_of=NOW,
    )

    by_period = {(o.bill_id, o.period): o for o in report}
    august = by_period[(monthly.bill_id, "2026-08-05")]
    september = by_period[(monthly.bill_id, "2026-09-05")]
    iptu = by_period[(once.bill_id, "2026-09-20")]

    assert august.paid is True
    assert august.overdue is False
    assert september.paid is False
    assert september.overdue is True  # 2026-09-05 < NOW (2026-09-21)
    assert iptu.paid is False
    assert iptu.overdue is True


def test_report_clamps_monthly_due_day_to_month_length(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Assinatura",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=31,
        now=NOW,
        correlation_id="c",
    )

    report = BillsReportService(session).list_occurrences(
        USER,
        due_from=datetime(2026, 2, 1, tzinfo=UTC),
        due_to=datetime(2026, 2, 28, tzinfo=UTC),
        as_of=NOW,
    )

    assert len(report) == 1
    assert report[0].bill_id == bill.bill_id
    assert report[0].due_at == datetime(2026, 2, 28, tzinfo=UTC)


def test_report_filters_by_account_paid_and_overdue(
    bills: BillsService, session: Session, bus: InProcessEventBus
) -> None:
    a = FinanceService(session, bus).create_account(USER, "Checking", "BRL", now=NOW)
    b = FinanceService(session, bus).create_account(USER, "Card", "BRL", now=NOW)
    bills.register_bill(
        USER,
        a.account_id,
        "Aluguel",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    bills.register_bill(
        USER,
        b.account_id,
        "Fatura",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=15,
        now=NOW,
        correlation_id="c",
    )
    window = {
        "due_from": datetime(2026, 9, 1, tzinfo=UTC),
        "due_to": datetime(2026, 9, 30, tzinfo=UTC),
        "as_of": NOW,
    }

    only_a = BillsReportService(session).list_occurrences(USER, account_id=a.account_id, **window)
    assert {o.account_id for o in only_a} == {a.account_id}

    unpaid = BillsReportService(session).list_occurrences(USER, paid=False, **window)
    assert len(unpaid) == 2

    overdue = BillsReportService(session).list_occurrences(USER, overdue=True, **window)
    assert len(overdue) == 2


def test_report_caps_occurrences_at_max_occurrences(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bill = bills.register_bill(
        USER,
        account_id,
        "Parcela",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        max_occurrences=2,
        now=NOW,  # September 2026 is the genesis month.
        correlation_id="c",
    )

    report = BillsReportService(session).list_occurrences(
        USER,
        due_from=datetime(2026, 9, 1, tzinfo=UTC),
        due_to=datetime(2026, 12, 31, tzinfo=UTC),
        as_of=NOW,
    )

    assert [o.due_at for o in report] == [
        datetime(2026, 9, 5, tzinfo=UTC),
        datetime(2026, 10, 5, tzinfo=UTC),
    ]
    assert all(o.bill_id == bill.bill_id for o in report)


def test_report_scoped_to_user(
    bills: BillsService, session: Session, account_id: uuid.UUID
) -> None:
    bills.register_bill(
        USER,
        account_id,
        "Aluguel",
        1000,
        "BRL",
        recurrence="monthly",
        due_day=5,
        now=NOW,
        correlation_id="c",
    )
    other = uuid.uuid4()

    report = BillsReportService(session).list_occurrences(
        other,
        due_from=datetime(2026, 9, 1, tzinfo=UTC),
        due_to=datetime(2026, 9, 30, tzinfo=UTC),
        as_of=NOW,
    )

    assert report == []
