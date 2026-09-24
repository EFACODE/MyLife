"""Tests for the Pierre Finance (Open Finance) connector (T4.9)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import ConnectorRunner, FetchContext
from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance.net_worth import NetWorthService
from mylife.finance.openfinance import (
    PIERRE_PROVIDER,
    MissingCredentialError,
    PierreApiError,
    PierreFinanceClient,
    PierreFinanceConnector,
)
from mylife.finance.service import FinanceService
from mylife.identity.credential_vault import CredentialVault

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
KEY = Fernet.generate_key().decode()

ACCOUNT = {
    "accountId": "acc-1",
    "providerCode": "NUBANK",
    "accountName": "Conta Corrente",
    "accountType": "BANK",
    "accountSubtype": "CHECKING_ACCOUNT",
    "accountBalance": 1500.00,
    "accountCurrencyCode": "BRL",
    "accountMarketingName": "Nubank Conta",
}
TRANSACTIONS = [
    {
        "id": "tx-1",
        "accountId": "acc-1",
        "amount": -45.99,
        "description": "Coffee",
        "category": "food",
        "date": "2026-07-18",
    },
    {
        "id": "tx-2",
        "accountId": "acc-1",
        "amount": 2500.00,
        "description": "Salary",
        "category": "income",
        "date": "2026-07-19",
    },
]


def _handler(
    accounts: list[dict[str, object]], transactions: list[dict[str, object]]
) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tools/api/get-accounts":
            return httpx.Response(
                200, json={"success": True, "data": accounts, "count": len(accounts)}
            )
        if request.url.path == "/tools/api/get-transactions":
            return httpx.Response(
                200, json={"success": True, "data": transactions, "count": len(transactions)}
            )
        return httpx.Response(404, json={"success": False, "error": "not found"})

    return httpx.MockTransport(handle)


def _client(
    accounts: list[dict[str, object]], transactions: list[dict[str, object]]
) -> PierreFinanceClient:
    http_client = httpx.Client(
        transport=_handler(accounts, transactions), base_url="https://fake.pierre.test"
    )
    return PierreFinanceClient(base_url="https://fake.pierre.test", http_client=http_client)


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


def _context(user: uuid.UUID) -> FetchContext:
    return FetchContext(user_id=user, correlation_id="corr-1")


def test_sync_creates_account_transactions_and_balance(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    with factory() as session:
        CredentialVault(session, KEY).store(user, PIERRE_PROVIDER, "sk-test", now=NOW)
        connector = PierreFinanceConnector(
            FinanceService(session, InProcessEventBus()),
            CredentialVault(session, KEY),
            _client([ACCOUNT], TRANSACTIONS),
            now=NOW,
        )
        result = ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))

        assert result.raw_ingested == 3  # 1 balance + 2 transactions
        assert result.events_created == 3

        finance = FinanceService(session, InProcessEventBus())
        accounts = finance.list_accounts(user)
        assert len(accounts) == 1
        assert accounts[0].currency == "BRL"

        transactions = finance.list_transactions(user)
        assert {t.description for t in transactions} == {"Coffee", "Salary"}
        assert all(t.kind == "openfinance_import" for t in transactions)
        coffee = next(t for t in transactions if t.description == "Coffee")
        assert coffee.amount_minor == -4599
        assert coffee.category == "food"

        balance = NetWorthService(session).account_balance(user, accounts[0].account_id)
        assert balance is not None
        assert balance.balance_minor == 150000


def test_sync_is_idempotent(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    with factory() as session:
        CredentialVault(session, KEY).store(user, PIERRE_PROVIDER, "sk-test", now=NOW)
        finance = FinanceService(session, InProcessEventBus())

        def _connector() -> PierreFinanceConnector:
            return PierreFinanceConnector(
                finance, CredentialVault(session, KEY), _client([ACCOUNT], TRANSACTIONS), now=NOW
            )

        runner = ConnectorRunner(session, InProcessEventBus())
        first = runner.sync(_connector(), _context(user))
        second = runner.sync(_connector(), _context(user))

        assert first.raw_ingested == 3
        assert second.raw_ingested == 0
        assert second.skipped_duplicates == 3
        assert len(finance.list_accounts(user)) == 1


def test_sync_records_fresh_balance_on_change(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    with factory() as session:
        CredentialVault(session, KEY).store(user, PIERRE_PROVIDER, "sk-test", now=NOW)
        finance = FinanceService(session, InProcessEventBus())
        runner = ConnectorRunner(session, InProcessEventBus())

        runner.sync(
            PierreFinanceConnector(
                finance, CredentialVault(session, KEY), _client([ACCOUNT], []), now=NOW
            ),
            _context(user),
        )
        updated_account = {**ACCOUNT, "accountBalance": 1600.00}
        result = runner.sync(
            PierreFinanceConnector(
                finance, CredentialVault(session, KEY), _client([updated_account], []), now=NOW
            ),
            _context(user),
        )

        assert result.raw_ingested == 1
        account_id = finance.list_accounts(user)[0].account_id
        balance = NetWorthService(session).account_balance(user, account_id)
        assert balance is not None
        assert balance.balance_minor == 160000


def test_sync_without_credential_raises(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    with factory() as session:
        connector = PierreFinanceConnector(
            FinanceService(session, InProcessEventBus()),
            CredentialVault(session, KEY),
            _client([ACCOUNT], TRANSACTIONS),
            now=NOW,
        )
        with pytest.raises(MissingCredentialError):
            ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))


def test_transaction_missing_recognized_fields_fails_the_batch(
    factory: sessionmaker[Session],
) -> None:
    user = uuid.uuid4()
    bad_transaction = {"accountId": "acc-1", "foo": "bar"}
    with factory() as session:
        CredentialVault(session, KEY).store(user, PIERRE_PROVIDER, "sk-test", now=NOW)
        connector = PierreFinanceConnector(
            FinanceService(session, InProcessEventBus()),
            CredentialVault(session, KEY),
            _client([ACCOUNT], [bad_transaction]),
            now=NOW,
        )
        with pytest.raises(ValueError, match="amount"):
            ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))

        # Nothing left half-ingested (the balance raw record rolled back too).
        finance = FinanceService(session, InProcessEventBus())
        assert finance.list_transactions(user) == []


def test_upstream_error_raises_pierre_api_error(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_api_key"})

    with factory() as session:
        CredentialVault(session, KEY).store(user, PIERRE_PROVIDER, "sk-bad", now=NOW)
        http_client = httpx.Client(
            transport=httpx.MockTransport(handle), base_url="https://fake.test"
        )
        client = PierreFinanceClient(base_url="https://fake.test", http_client=http_client)
        connector = PierreFinanceConnector(
            FinanceService(session, InProcessEventBus()),
            CredentialVault(session, KEY),
            client,
            now=NOW,
        )
        with pytest.raises(PierreApiError):
            ConnectorRunner(session, InProcessEventBus()).sync(connector, _context(user))
