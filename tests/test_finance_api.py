"""Tests for the finance endpoints (T4.1)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.db.base import Base, get_session
from mylife.main import create_app

EMAIL = "ada@example.com"
PASSWORD = "s3cretpw"


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


def _account(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post("/accounts", json={"name": "Checking", "currency": "BRL"}, headers=auth)
    assert response.status_code == 201
    return str(response.json()["account_id"])


def test_create_account_and_list(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    listed = client.get("/accounts", headers=auth)
    assert listed.status_code == 200
    assert [a["account_id"] for a in listed.json()] == [account_id]


def test_record_expense_returns_money_out(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    response = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 4599,
            "currency": "BRL",
            "description": "Lunch",
            "category": "food",
        },
        headers=auth,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["amount_minor"] == -4599
    assert body["kind"] == "expense"


def test_import_transaction_and_list(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    client.post(
        "/finance/transactions",
        json={
            "account_id": account_id,
            "amount_minor": -4599,
            "currency": "BRL",
            "description": "Card 1234",
            "external_id": "tx-1",
        },
        headers=auth,
    )
    txns = client.get("/finance/transactions", headers=auth)
    assert txns.status_code == 200
    assert [t["kind"] for t in txns.json()] == ["import"]


def test_expense_unknown_account_is_404(client: TestClient) -> None:
    auth = _auth(client)
    response = client.post(
        "/finance/expenses",
        json={
            "account_id": "00000000-0000-0000-0000-000000000000",
            "amount_minor": 100,
            "currency": "BRL",
            "description": "x",
        },
        headers=auth,
    )
    assert response.status_code == 404


def test_foreign_account_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    account_id = _account(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    response = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 100,
            "currency": "BRL",
            "description": "x",
        },
        headers=intruder_auth,
    )
    assert response.status_code == 404


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/accounts").status_code == 401
    assert client.get("/finance/transactions").status_code == 401
    assert client.post("/accounts", json={"name": "x", "currency": "BRL"}).status_code == 401
