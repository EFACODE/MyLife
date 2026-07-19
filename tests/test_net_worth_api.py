"""Tests for the net-worth / balance / cash-flow endpoints (T4.3)."""

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


def _account(client: TestClient, auth: dict[str, str], currency: str = "BRL") -> str:
    response = client.post(
        "/accounts", json={"name": "Checking", "currency": currency}, headers=auth
    )
    return str(response.json()["account_id"])


def test_position_then_balance(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    posted = client.post(
        "/finance/positions",
        json={"account_id": account_id, "value_minor": 1000000, "currency": "BRL"},
        headers=auth,
    )
    assert posted.status_code == 201
    assert posted.json()["balance_minor"] == 1000000

    balance = client.get(f"/finance/accounts/{account_id}/balance", headers=auth)
    assert balance.status_code == 200
    assert balance.json()["balance_minor"] == 1000000


def test_net_worth_grouped_per_currency(client: TestClient) -> None:
    auth = _auth(client)
    brl = _account(client, auth, "BRL")
    usd = _account(client, auth, "USD")
    client.post(
        "/finance/positions",
        json={"account_id": brl, "value_minor": 1000000, "currency": "BRL"},
        headers=auth,
    )
    client.post(
        "/finance/positions",
        json={"account_id": usd, "value_minor": 200000, "currency": "USD"},
        headers=auth,
    )

    body = client.get("/finance/net-worth", headers=auth).json()
    totals = {c["currency"]: c["total_minor"] for c in body["currencies"]}
    assert totals == {"BRL": 1000000, "USD": 200000}
    assert len(body["accounts"]) == 2


def test_cash_flow_window(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    client.post(
        "/finance/transactions",
        json={
            "account_id": account_id,
            "amount_minor": 250000,
            "currency": "BRL",
            "description": "Salary",
        },
        headers=auth,
    )
    client.post(
        "/finance/expenses",
        json={
            "account_id": account_id,
            "amount_minor": 4599,
            "currency": "BRL",
            "description": "Coffee",
        },
        headers=auth,
    )

    body = client.get(
        "/finance/cash-flow",
        params={
            "occurred_from": "2000-01-01T00:00:00+00:00",
            "occurred_to": "2100-01-01T00:00:00+00:00",
        },
        headers=auth,
    ).json()
    assert len(body["flows"]) == 1
    brl = body["flows"][0]
    assert brl["inflow_minor"] == 250000
    assert brl["outflow_minor"] == -4599
    assert brl["net_minor"] == 250000 - 4599


def test_balance_foreign_account_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    account_id = _account(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    response = client.get(f"/finance/accounts/{account_id}/balance", headers=intruder_auth)
    assert response.status_code == 404


def test_finance_analytics_require_auth(client: TestClient) -> None:
    assert client.get("/finance/net-worth").status_code == 401
    assert (
        client.post(
            "/finance/positions",
            json={
                "account_id": "00000000-0000-0000-0000-000000000000",
                "value_minor": 1,
                "currency": "BRL",
            },
        ).status_code
        == 401
    )
