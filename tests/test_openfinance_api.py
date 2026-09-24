"""Tests for the Open Finance (Pierre Finance) connector endpoints (T4.9)."""

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.api.deps import get_pierre_client
from mylife.db.base import Base, get_session
from mylife.finance.openfinance import PierreFinanceClient
from mylife.main import create_app

EMAIL = "ada@example.com"
PASSWORD = "s3cretpw"

ACCOUNT = {
    "accountId": "acc-1",
    "accountName": "Conta Corrente",
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
    }
]


def _fake_client() -> PierreFinanceClient:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tools/api/get-accounts":
            return httpx.Response(200, json={"success": True, "data": [ACCOUNT]})
        if request.url.path == "/tools/api/get-transactions":
            return httpx.Response(200, json={"success": True, "data": TRANSACTIONS})
        return httpx.Response(404, json={"success": False, "error": "not found"})

    http_client = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://fake.test")
    return PierreFinanceClient(base_url="https://fake.test", http_client=http_client)


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()

    def override_session() -> Iterator[Session]:
        yield db

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_pierre_client] = _fake_client
    with TestClient(app) as test_client:
        yield test_client
    db.close()
    engine.dispose()


def _auth(client: TestClient, email: str = EMAIL) -> dict[str, str]:
    client.post("/users", json={"email": email, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _grant_openfinance(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/consents", json={"scope": "openfinance"}, headers=auth).status_code == 201


def test_sync_requires_auth(client: TestClient) -> None:
    response = client.post("/finance/connectors/openfinance/sync")
    assert response.status_code == 401


def test_sync_requires_consent(client: TestClient) -> None:
    auth = _auth(client)
    client.post(
        "/finance/connectors/openfinance/credentials", json={"api_key": "sk-test"}, headers=auth
    )

    response = client.post("/finance/connectors/openfinance/sync", headers=auth)

    assert response.status_code == 403
    assert client.get("/finance/transactions", headers=auth).json() == []


def test_sync_without_stored_key_is_409(client: TestClient) -> None:
    auth = _auth(client)
    _grant_openfinance(client, auth)

    response = client.post("/finance/connectors/openfinance/sync", headers=auth)

    assert response.status_code == 409


def test_sync_creates_transactions_after_credential_and_consent(client: TestClient) -> None:
    auth = _auth(client)
    _grant_openfinance(client, auth)
    client.post(
        "/finance/connectors/openfinance/credentials", json={"api_key": "sk-test"}, headers=auth
    )

    response = client.post("/finance/connectors/openfinance/sync", headers=auth)

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "openfinance"
    assert body["events_created"] == 2  # 1 balance + 1 transaction

    transactions = client.get("/finance/transactions", headers=auth).json()
    assert [t["description"] for t in transactions] == ["Coffee"]

    # The account's balance mark (Pierre's own current balance, R$1500.00)
    # supersedes the running transaction sum rather than adding to it — see
    # PierreFinanceConnector.fetch()'s ordering note.
    net_worth = client.get("/finance/net-worth", headers=auth).json()
    assert net_worth["currencies"] == [{"currency": "BRL", "total_minor": 150000}]


def test_delete_credentials_then_sync_is_409(client: TestClient) -> None:
    auth = _auth(client)
    _grant_openfinance(client, auth)
    client.post(
        "/finance/connectors/openfinance/credentials", json={"api_key": "sk-test"}, headers=auth
    )

    assert (
        client.delete("/finance/connectors/openfinance/credentials", headers=auth).status_code
        == 204
    )
    response = client.post("/finance/connectors/openfinance/sync", headers=auth)

    assert response.status_code == 409
