"""Tests for the bank CSV connector (T4.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import ConnectorRunner, FetchContext
from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.finance import BankCsvConnector, FinanceService
from mylife.timeline import TimelineQueryFilter, TimelineQueryService

FETCHED_AT = datetime(2026, 7, 19, 20, 0, tzinfo=UTC)

CSV = (
    "amount_minor,occurred_at,description,currency,category,external_id\n"
    "-4599,2026-07-18T12:00:00+00:00,Coffee,BRL,food,tx-1\n"
    "250000,2026-07-19T08:00:00+00:00,Salary,,income,tx-2\n"
)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _account(factory: sessionmaker[Session], user: uuid.UUID) -> uuid.UUID:
    with factory() as session:
        account = FinanceService(session, InProcessEventBus()).create_account(
            user, "Checking", "BRL", now=FETCHED_AT
        )
    return account.account_id


def _connector(account_id: uuid.UUID, csv_text: str = CSV) -> BankCsvConnector:
    return BankCsvConnector(
        csv_text, account_id=account_id, account_currency="BRL", fetched_at=FETCHED_AT
    )


def _context(user: uuid.UUID) -> FetchContext:
    return FetchContext(user_id=user, correlation_id="corr-1")


def test_import_creates_transactions_with_provenance(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    account_id = _account(factory, user)
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(_connector(account_id), _context(user))

    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
        txns = FinanceService(session, InProcessEventBus()).list_transactions(user)

    assert len(events) == 2
    assert all(e.source == "bank" for e in events)
    assert all(e.raw_record_id is not None for e in events)
    by_desc = {t.description: t for t in txns}
    assert by_desc["Coffee"].amount_minor == -4599
    assert by_desc["Coffee"].currency == "BRL"  # defaulted from the account for Salary too
    assert by_desc["Salary"].amount_minor == 250000
    assert by_desc["Salary"].account_id == account_id


def test_reimport_is_idempotent(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    account_id = _account(factory, user)
    with factory() as session:
        ConnectorRunner(session, InProcessEventBus()).sync(_connector(account_id), _context(user))
    with factory() as session:
        second = ConnectorRunner(session, InProcessEventBus()).sync(
            _connector(account_id), _context(user)
        )

    assert (second.raw_ingested, second.events_created, second.skipped_duplicates) == (0, 0, 2)


def test_bad_amount_rolls_back_the_batch(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    account_id = _account(factory, user)
    bad_csv = (
        "amount_minor,occurred_at,description\n"
        "100,2026-07-18T09:00:00+00:00,Good\n"
        "notanumber,2026-07-18T10:00:00+00:00,Bad\n"
    )
    with factory() as session, pytest.raises(ValueError):
        ConnectorRunner(session, InProcessEventBus()).sync(
            _connector(account_id, bad_csv), _context(user)
        )

    with factory() as session:
        assert EventStore(session).read_all() == []


def test_currency_mismatch_rolls_back_the_batch(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    account_id = _account(factory, user)
    mismatch_csv = (
        "amount_minor,occurred_at,description,currency\n100,2026-07-18T09:00:00+00:00,Foreign,USD\n"
    )
    with factory() as session, pytest.raises(ValueError):
        ConnectorRunner(session, InProcessEventBus()).sync(
            _connector(account_id, mismatch_csv), _context(user)
        )

    with factory() as session:
        assert EventStore(session).read_all() == []
