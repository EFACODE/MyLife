"""Tests for balances, net worth and cash flow (T4.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService, NetWorthService, UnknownAccountError

DAY1 = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
DAY2 = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
DAY3 = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


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
def finance(session: Session) -> FinanceService:
    return FinanceService(session, InProcessEventBus())


@pytest.fixture
def net_worth(session: Session) -> NetWorthService:
    return NetWorthService(session)


def test_balance_is_sum_without_anchor(finance: FinanceService, net_worth: NetWorthService) -> None:
    user = uuid.uuid4()
    account = finance.create_account(user, "Checking", "BRL", now=DAY1)
    finance.import_transaction(
        user, account.account_id, 250000, "BRL", "Salary", now=DAY1, correlation_id="c"
    )
    finance.record_expense(
        user, account.account_id, 4599, "BRL", "Coffee", now=DAY2, correlation_id="c"
    )

    balance = net_worth.account_balance(user, account.account_id)
    assert balance is not None
    assert balance.balance_minor == 250000 - 4599
    assert balance.currency == "BRL"
    assert balance.as_of == DAY2


def test_valuation_anchors_and_later_transactions_accumulate(finance: FinanceService) -> None:
    user = uuid.uuid4()
    account = finance.create_account(user, "Checking", "BRL", now=DAY1)
    # A pre-anchor transaction is superseded by the valuation.
    finance.import_transaction(
        user, account.account_id, 999999, "BRL", "old", now=DAY1, correlation_id="c"
    )
    balance = finance.record_valuation(
        user, account.account_id, 1000000, "BRL", now=DAY2, correlation_id="c"
    )
    assert balance.balance_minor == 1000000  # anchor wins over prior history

    # A post-anchor transaction accumulates on top.
    finance.record_expense(
        user, account.account_id, 5000, "BRL", "Lunch", now=DAY3, correlation_id="c"
    )
    later = NetWorthService(finance._session).account_balance(user, account.account_id)  # noqa: SLF001
    assert later is not None
    assert later.balance_minor == 1000000 - 5000


def test_record_valuation_unknown_account_raises(finance: FinanceService) -> None:
    user = uuid.uuid4()
    with pytest.raises(UnknownAccountError):
        finance.record_valuation(user, uuid.uuid4(), 100, "BRL", now=DAY1, correlation_id="c")


def test_net_worth_groups_per_currency(finance: FinanceService, net_worth: NetWorthService) -> None:
    user = uuid.uuid4()
    brl = finance.create_account(user, "Checking", "BRL", now=DAY1)
    usd = finance.create_account(user, "Savings", "USD", now=DAY1)
    finance.record_valuation(user, brl.account_id, 1000000, "BRL", now=DAY1, correlation_id="c")
    finance.record_valuation(user, usd.account_id, 200000, "USD", now=DAY1, correlation_id="c")

    result = net_worth.net_worth(user)
    totals = {c.currency: c.total_minor for c in result.currencies}
    assert totals == {"BRL": 1000000, "USD": 200000}  # never summed across currencies
    assert {b.account_id for b in result.accounts} == {brl.account_id, usd.account_id}


def test_net_worth_scoped_to_user(finance: FinanceService, net_worth: NetWorthService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    account = finance.create_account(other, "Checking", "BRL", now=DAY1)
    finance.record_valuation(other, account.account_id, 500, "BRL", now=DAY1, correlation_id="c")

    result = net_worth.net_worth(user)
    assert result.currencies == []
    assert result.accounts == []


def test_cash_flow_window_and_signs(finance: FinanceService, net_worth: NetWorthService) -> None:
    user = uuid.uuid4()
    account = finance.create_account(user, "Checking", "BRL", now=DAY1)
    # Anchor should be ignored by cash flow.
    finance.record_valuation(user, account.account_id, 1000000, "BRL", now=DAY1, correlation_id="c")
    finance.import_transaction(
        user, account.account_id, 250000, "BRL", "Salary", now=DAY2, correlation_id="c"
    )
    finance.record_expense(
        user, account.account_id, 4599, "BRL", "Coffee", now=DAY2, correlation_id="c"
    )
    # Outside the window (DAY3) — excluded.
    finance.record_expense(
        user, account.account_id, 100, "BRL", "late", now=DAY3, correlation_id="c"
    )

    flow = net_worth.cash_flow(user, occurred_from=DAY2, occurred_to=DAY2)
    assert len(flow.flows) == 1
    brl = flow.flows[0]
    assert brl.currency == "BRL"
    assert brl.inflow_minor == 250000
    assert brl.outflow_minor == -4599
    assert brl.net_minor == 250000 - 4599
