"""Tests for the assistant query endpoint (T7.2)."""

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


def _auth(client: TestClient) -> dict[str, str]:
    client.post("/users", json={"email": EMAIL, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _seed_food_expense(client: TestClient, auth: dict[str, str]) -> None:
    account = client.post(
        "/accounts", json={"name": "Checking", "currency": "BRL"}, headers=auth
    ).json()
    client.post(
        "/finance/expenses",
        json={
            "account_id": account["account_id"],
            "amount_minor": 4599,
            "currency": "BRL",
            "description": "Lunch",
            "category": "food",
        },
        headers=auth,
    )


def test_grounded_query(client: TestClient) -> None:
    auth = _auth(client)
    _seed_food_expense(client, auth)

    response = client.post("/assistant/query", json={"question": "how much on food?"}, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["insight"]["evidence"]
    # The grounded answer shows up in the user's insights.
    assert len(client.get("/insights", headers=auth).json()) == 1


def test_refusal_query(client: TestClient) -> None:
    auth = _auth(client)
    _seed_food_expense(client, auth)

    response = client.post(
        "/assistant/query", json={"question": "photosynthesis in ferns"}, headers=auth
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["insight"] is None
    assert client.get("/insights", headers=auth).json() == []


def test_query_requires_auth(client: TestClient) -> None:
    assert client.post("/assistant/query", json={"question": "x"}).status_code == 401
