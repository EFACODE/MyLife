"""Tests for the bank CSV import endpoint (T4.2)."""

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

CSV = (
    "amount_minor,occurred_at,description,category,external_id\n"
    "-4599,2026-07-18T12:00:00+00:00,Coffee,food,tx-1\n"
    "250000,2026-07-19T08:00:00+00:00,Salary,income,tx-2\n"
)


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
    return str(response.json()["account_id"])


def _grant_bank(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/consents", json={"scope": "bank"}, headers=auth).status_code == 201


def test_import_requires_consent(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)

    response = client.post(
        "/finance/connectors/bank/import",
        json={"account_id": account_id, "csv": CSV},
        headers=auth,
    )
    assert response.status_code == 403
    # Nothing ingested without consent.
    assert client.get("/finance/transactions", headers=auth).json() == []


def test_import_after_consent_creates_transactions(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    _grant_bank(client, auth)

    response = client.post(
        "/finance/connectors/bank/import",
        json={"account_id": account_id, "csv": CSV},
        headers=auth,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["raw_ingested"] == 2
    assert body["events_created"] == 2

    txns = client.get("/finance/transactions", headers=auth).json()
    assert {t["description"] for t in txns} == {"Coffee", "Salary"}
    assert all(t["kind"] == "import" for t in txns)


def test_import_is_idempotent(client: TestClient) -> None:
    auth = _auth(client)
    account_id = _account(client, auth)
    _grant_bank(client, auth)
    payload = {"account_id": account_id, "csv": CSV}

    client.post("/finance/connectors/bank/import", json=payload, headers=auth)
    second = client.post("/finance/connectors/bank/import", json=payload, headers=auth).json()
    assert (second["raw_ingested"], second["skipped_duplicates"]) == (0, 2)


def test_import_foreign_account_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    account_id = _account(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    _grant_bank(client, intruder_auth)
    response = client.post(
        "/finance/connectors/bank/import",
        json={"account_id": account_id, "csv": CSV},
        headers=intruder_auth,
    )
    assert response.status_code == 404


def test_import_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/finance/connectors/bank/import",
        json={"account_id": "00000000-0000-0000-0000-000000000000", "csv": CSV},
    )
    assert response.status_code == 401
