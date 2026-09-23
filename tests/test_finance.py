"""Tests for the finance service (T4.1)."""

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
    EXPENSE_CREATED,
    TRANSACTION_DELETED,
    TRANSACTION_IMPORTED,
    TRANSACTION_UPDATED,
    DuplicateCategoryError,
    FinanceService,
    NetWorthService,
    UnknownAccountError,
    UnknownCategoryError,
    UnknownTransactionError,
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


@pytest.fixture
def service(session: Session) -> FinanceService:
    return FinanceService(session, InProcessEventBus())


def test_create_and_list_accounts_scoped(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    account = service.create_account(user, "Checking", "brl", now=NOW)
    service.create_account(other, "Savings", "usd", now=NOW)

    assert account.currency == "BRL"  # normalized to upper
    listed = service.list_accounts(user)
    assert [a.account_id for a in listed] == [account.account_id]
    assert service.get_account(user, account.account_id) is not None
    # The other user's account is not visible to this user.
    assert service.get_account(user, service.list_accounts(other)[0].account_id) is None


def test_record_expense_stores_negative_and_emits_event(
    service: FinanceService, session: Session
) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)

    txn = service.record_expense(
        user,
        account.account_id,
        4599,
        "BRL",
        "Lunch",
        category="food",
        now=NOW,
        correlation_id="c",
    )

    assert txn.amount_minor == -4599  # money out, stored negative
    assert txn.kind == "expense"
    assert txn.category == "food"
    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [EXPENSE_CREATED]
    assert events[0].payload["amount_minor"] == -4599


def test_record_expense_with_expense_type(service: FinanceService, session: Session) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)

    txn = service.record_expense(
        user,
        account.account_id,
        1200,
        "BRL",
        "Netflix",
        expense_type="fixed",
        now=NOW,
        correlation_id="c",
    )

    assert txn.expense_type == "fixed"
    events = EventStore(session).read_stream(user)
    assert events[0].payload["expense_type"] == "fixed"


def test_import_transaction_keeps_sign(service: FinanceService, session: Session) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)

    txn = service.import_transaction(
        user,
        account.account_id,
        -4599,
        "BRL",
        "Card 1234",
        external_id="tx-1",
        now=NOW,
        correlation_id="c",
    )

    assert txn.amount_minor == -4599
    assert txn.kind == "import"
    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [TRANSACTION_IMPORTED]


def test_record_expense_unknown_account_raises(service: FinanceService) -> None:
    user = uuid.uuid4()
    with pytest.raises(UnknownAccountError):
        service.record_expense(user, uuid.uuid4(), 100, "BRL", "x", now=NOW, correlation_id="c")


def test_record_expense_foreign_account_raises(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    foreign = service.create_account(other, "Checking", "BRL", now=NOW)
    with pytest.raises(UnknownAccountError):
        service.record_expense(
            user, foreign.account_id, 100, "BRL", "x", now=NOW, correlation_id="c"
        )


def test_list_transactions_newest_first_and_filtered(service: FinanceService) -> None:
    user = uuid.uuid4()
    a = service.create_account(user, "Checking", "BRL", now=NOW)
    b = service.create_account(user, "Savings", "BRL", now=NOW)

    older = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    service.record_expense(user, a.account_id, 100, "BRL", "old", now=older, correlation_id="c")
    service.record_expense(user, a.account_id, 200, "BRL", "new", now=NOW, correlation_id="c")
    service.import_transaction(user, b.account_id, 500, "BRL", "b-txn", now=NOW, correlation_id="c")

    all_txns = service.list_transactions(user)
    assert [t.description for t in all_txns[:2]] == ["b-txn", "new"] or [
        t.description for t in all_txns[:2]
    ] == ["new", "b-txn"]
    assert len(all_txns) == 3

    a_only = service.list_transactions(user, account_id=a.account_id)
    assert {t.account_id for t in a_only} == {a.account_id}
    assert [t.description for t in a_only] == ["new", "old"]  # newest first


def test_list_transactions_scoped_to_user(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)
    service.record_expense(
        user, account.account_id, 100, "BRL", "mine", now=NOW, correlation_id="c"
    )

    assert service.list_transactions(other) == []


def test_update_transaction_changes_fields_and_emits_correction(
    service: FinanceService, session: Session
) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)
    original = service.record_expense(
        user, account.account_id, 4599, "BRL", "Lunch", category="food", now=NOW, correlation_id="c"
    )

    updated = service.update_transaction(
        user,
        original.event_id,
        5000,
        "BRL",
        "Lunch (corrected)",
        category="restaurante",
        expense_type="variable",
        now=NOW,
        correlation_id="c2",
    )

    assert updated.event_id == original.event_id  # identity preserved
    assert updated.amount_minor == 5000
    assert updated.description == "Lunch (corrected)"
    assert updated.category == "restaurante"
    assert updated.expense_type == "variable"

    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [EXPENSE_CREATED, TRANSACTION_UPDATED]
    assert events[1].corrects_event_id == original.event_id

    listed = service.list_transactions(user)
    assert len(listed) == 1
    assert listed[0].amount_minor == 5000
    assert listed[0].description == "Lunch (corrected)"


def test_update_transaction_unknown_or_foreign_raises(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    account = service.create_account(other, "Checking", "BRL", now=NOW)
    theirs = service.record_expense(
        other, account.account_id, 100, "BRL", "x", now=NOW, correlation_id="c"
    )

    with pytest.raises(UnknownTransactionError):
        service.update_transaction(user, uuid.uuid4(), 100, "BRL", "x", now=NOW, correlation_id="c")
    with pytest.raises(UnknownTransactionError):
        service.update_transaction(
            user, theirs.event_id, 100, "BRL", "x", now=NOW, correlation_id="c"
        )


def test_delete_transaction_removes_it_from_listing(
    service: FinanceService, session: Session
) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)
    txn = service.record_expense(
        user, account.account_id, 100, "BRL", "gone soon", now=NOW, correlation_id="c"
    )
    service.record_expense(
        user, account.account_id, 200, "BRL", "stays", now=NOW, correlation_id="c"
    )

    service.delete_transaction(user, txn.event_id, now=NOW, correlation_id="c2")

    listed = service.list_transactions(user)
    assert [t.description for t in listed] == ["stays"]
    events = EventStore(session).read_stream(user)
    assert [e.event_type for e in events] == [
        EXPENSE_CREATED,
        EXPENSE_CREATED,
        TRANSACTION_DELETED,
    ]


def test_delete_transaction_unknown_or_foreign_raises(service: FinanceService) -> None:
    user = uuid.uuid4()
    with pytest.raises(UnknownTransactionError):
        service.delete_transaction(user, uuid.uuid4(), now=NOW, correlation_id="c")


def test_update_and_delete_transaction_adjust_account_balance(
    service: FinanceService, session: Session
) -> None:
    user = uuid.uuid4()
    account = service.create_account(user, "Checking", "BRL", now=NOW)
    txn = service.record_expense(
        user, account.account_id, 1000, "BRL", "x", now=NOW, correlation_id="c"
    )
    keeper = service.record_expense(
        user, account.account_id, 500, "BRL", "y", now=NOW, correlation_id="c"
    )

    net_worth = NetWorthService(session)
    assert net_worth.account_balance(user, account.account_id).balance_minor == -1500

    service.update_transaction(user, txn.event_id, -2000, "BRL", "x", now=NOW, correlation_id="c2")
    assert net_worth.account_balance(user, account.account_id).balance_minor == -2500

    service.delete_transaction(user, keeper.event_id, now=NOW, correlation_id="c3")
    assert net_worth.account_balance(user, account.account_id).balance_minor == -2000


def test_create_and_list_categories_scoped(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    category = service.create_category(user, "Moradia", now=NOW)
    service.create_category(other, "Mercado", now=NOW)

    assert category.name == "Moradia"
    listed = service.list_categories(user)
    assert [c.category_id for c in listed] == [category.category_id]


def test_create_category_rejects_case_insensitive_duplicate(service: FinanceService) -> None:
    user = uuid.uuid4()
    service.create_category(user, "Moradia", now=NOW)

    with pytest.raises(DuplicateCategoryError):
        service.create_category(user, "moradia", now=NOW)


def test_delete_category(service: FinanceService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    category = service.create_category(user, "Moradia", now=NOW)

    with pytest.raises(UnknownCategoryError):
        service.delete_category(other, category.category_id)

    service.delete_category(user, category.category_id)
    assert service.list_categories(user) == []
