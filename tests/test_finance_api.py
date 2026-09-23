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


def test_record_expense_with_expense_type(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    response = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 1200,
            "currency": "BRL",
            "description": "Netflix",
            "expense_type": "fixed",
        },
        headers=auth,
    )
    assert response.status_code == 201
    assert response.json()["expense_type"] == "fixed"


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


def test_update_transaction(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    created = client.post(
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
    event_id = created.json()["event_id"]

    response = client.patch(
        f"/finance/transactions/{event_id}",
        json={
            "amount_minor": -5000,
            "currency": "BRL",
            "description": "Lunch (corrected)",
            "category": "restaurante",
            "expense_type": "variable",
        },
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == event_id
    assert body["amount_minor"] == -5000
    assert body["description"] == "Lunch (corrected)"
    assert body["category"] == "restaurante"
    assert body["expense_type"] == "variable"

    listed = client.get("/finance/transactions", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["amount_minor"] == -5000


def test_update_unknown_transaction_is_404(client: TestClient) -> None:
    auth = _auth(client)
    response = client.patch(
        "/finance/transactions/00000000-0000-0000-0000-000000000000",
        json={"amount_minor": -100, "currency": "BRL", "description": "x"},
        headers=auth,
    )
    assert response.status_code == 404


def test_update_foreign_transaction_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    account_id = _account(client, owner_auth)
    created = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 1000,
            "currency": "BRL",
            "description": "x",
        },
        headers=owner_auth,
    )
    event_id = created.json()["event_id"]

    intruder_auth = _auth(client, "intruder@example.com")
    response = client.patch(
        f"/finance/transactions/{event_id}",
        json={"amount_minor": -100, "currency": "BRL", "description": "hijacked"},
        headers=intruder_auth,
    )
    assert response.status_code == 404


def test_delete_transaction(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    created = client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 1000,
            "currency": "BRL",
            "description": "gone soon",
        },
        headers=auth,
    )
    event_id = created.json()["event_id"]

    response = client.delete(f"/finance/transactions/{event_id}", headers=auth)
    assert response.status_code == 204
    assert client.get("/finance/transactions", headers=auth).json() == []


def test_delete_unknown_transaction_is_404(client: TestClient) -> None:
    auth = _auth(client)
    response = client.delete(
        "/finance/transactions/00000000-0000-0000-0000-000000000000", headers=auth
    )
    assert response.status_code == 404


def test_transaction_edit_endpoints_require_auth(client: TestClient) -> None:
    assert (
        client.patch(
            "/finance/transactions/00000000-0000-0000-0000-000000000000",
            json={"amount_minor": -100, "currency": "BRL", "description": "x"},
        ).status_code
        == 401
    )
    assert (
        client.delete("/finance/transactions/00000000-0000-0000-0000-000000000000").status_code
        == 401
    )


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


def test_create_category_list_and_delete(client: TestClient) -> None:
    auth = _auth(client)

    created = client.post("/finance/categories", json={"name": "Moradia"}, headers=auth)
    assert created.status_code == 201
    category_id = created.json()["category_id"]
    assert created.json()["name"] == "Moradia"

    listed = client.get("/finance/categories", headers=auth)
    assert listed.status_code == 200
    assert [c["name"] for c in listed.json()] == ["Moradia"]

    deleted = client.delete(f"/finance/categories/{category_id}", headers=auth)
    assert deleted.status_code == 204
    assert client.get("/finance/categories", headers=auth).json() == []


def test_create_category_duplicate_is_409(client: TestClient) -> None:
    auth = _auth(client)
    client.post("/finance/categories", json={"name": "Moradia"}, headers=auth)

    response = client.post("/finance/categories", json={"name": "moradia"}, headers=auth)
    assert response.status_code == 409


def test_categories_scoped_to_user(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    created = client.post("/finance/categories", json={"name": "Moradia"}, headers=owner_auth)
    category_id = created.json()["category_id"]

    intruder_auth = _auth(client, "intruder@example.com")
    assert client.get("/finance/categories", headers=intruder_auth).json() == []
    assert (
        client.delete(f"/finance/categories/{category_id}", headers=intruder_auth).status_code
        == 404
    )


def test_category_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/finance/categories").status_code == 401
    assert client.post("/finance/categories", json={"name": "x"}).status_code == 401
