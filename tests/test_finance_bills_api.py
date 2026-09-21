"""Tests for the bills endpoints (T4.7)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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


def _bill(client: TestClient, auth: dict[str, str], account_id: str) -> dict[str, object]:
    response = client.post(
        "/finance/bills",
        json={
            "account_id": account_id,
            "payee": "Aluguel",
            "amount_minor": 250000,
            "currency": "BRL",
            "category": "moradia",
            "recurrence": "monthly",
            "due_day": 5,
        },
        headers=auth,
    )
    assert response.status_code == 201
    return dict(response.json())


def test_register_and_list_bill(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    bill = _bill(client, auth, account_id)
    assert bill["amount_minor"] == 250000
    assert bill["active"] is True

    listed = client.get("/finance/bills", headers=auth)
    assert listed.status_code == 200
    assert [b["bill_id"] for b in listed.json()] == [bill["bill_id"]]


def test_register_bill_invalid_recurrence_is_422(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    response = client.post(
        "/finance/bills",
        json={
            "account_id": account_id,
            "payee": "Aluguel",
            "amount_minor": 1000,
            "currency": "BRL",
            "recurrence": "monthly",
        },
        headers=auth,
    )
    assert response.status_code == 422


def test_register_bill_unknown_account_is_404(client: TestClient) -> None:
    auth = _auth(client)
    response = client.post(
        "/finance/bills",
        json={
            "account_id": "00000000-0000-0000-0000-000000000000",
            "payee": "Aluguel",
            "amount_minor": 1000,
            "currency": "BRL",
            "recurrence": "monthly",
            "due_day": 5,
        },
        headers=auth,
    )
    assert response.status_code == 404


def test_cancel_bill(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    bill = _bill(client, auth, account_id)

    response = client.delete(f"/finance/bills/{bill['bill_id']}", headers=auth)
    assert response.status_code == 204

    listed = client.get("/finance/bills", headers=auth).json()
    assert listed[0]["active"] is False


def test_pay_bill_and_report(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    bill = _bill(client, auth, account_id)

    pay = client.post(
        f"/finance/bills/{bill['bill_id']}/pay",
        json={"due_at": "2026-09-05T00:00:00Z"},
        headers=auth,
    )
    assert pay.status_code == 201
    assert pay.json()["amount_minor"] == 250000

    report = client.get(
        "/finance/bills/report",
        params={"due_from": "2026-09-01T00:00:00Z", "due_to": "2026-09-30T00:00:00Z"},
        headers=auth,
    )
    assert report.status_code == 200
    occurrences = report.json()
    assert len(occurrences) == 1
    assert occurrences[0]["paid"] is True


def test_bills_scoped_to_user(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    account_id = _account(client, owner_auth)
    bill = _bill(client, owner_auth, account_id)

    intruder_auth = _auth(client, "intruder@example.com")
    assert client.get("/finance/bills", headers=intruder_auth).json() == []
    assert (
        client.delete(f"/finance/bills/{bill['bill_id']}", headers=intruder_auth).status_code == 404
    )


def test_bill_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/finance/bills").status_code == 401
    assert (
        client.post(
            "/finance/bills",
            json={
                "account_id": "00000000-0000-0000-0000-000000000000",
                "payee": "x",
                "amount_minor": 100,
                "currency": "BRL",
                "recurrence": "monthly",
                "due_day": 5,
            },
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/finance/bills/report",
            params={"due_from": "2026-09-01T00:00:00Z", "due_to": "2026-09-30T00:00:00Z"},
        ).status_code
        == 401
    )
    assert client.post("/finance/bills/alerts/run").status_code == 401


def test_run_bill_alerts_without_configured_channels_records_failure(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    due_soon = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    client.post(
        "/finance/bills",
        json={
            "account_id": account_id,
            "payee": "Aluguel",
            "amount_minor": 250000,
            "currency": "BRL",
            "recurrence": "once",
            "due_at": due_soon,  # 3 days out -> due_soon -> alert fires
        },
        headers=auth,
    )

    response = client.post("/finance/bills/alerts/run", headers=auth)

    assert response.status_code == 200
    outcomes = response.json()
    assert len(outcomes) == 1
    assert outcomes[0]["delivered"] is False
    assert "no email channel configured" in outcomes[0]["reason"]
