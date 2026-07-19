"""Tests for the knowledge-graph endpoints (T6.4)."""

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


def test_consolidate_and_explore(client: TestClient) -> None:
    auth = _auth(client)
    account = client.post(
        "/accounts", json={"name": "Checking", "currency": "BRL"}, headers=auth
    ).json()
    client.post(
        "/finance/expenses",
        json={
            "account_id": account["account_id"],
            "amount_minor": 4599,
            "currency": "BRL",
            "description": "Coffee",
            "category": "food",
        },
        headers=auth,
    )

    consolidated = client.post("/knowledge-graph/consolidate", headers=auth)
    assert consolidated.status_code == 200
    assert consolidated.json()["entities"] > 0

    entities = client.get("/knowledge-graph/entities", headers=auth).json()
    food = next(e for e in entities if e["entity_type"] == "category" and e["entity_key"] == "food")

    neighbors = client.get(f"/knowledge-graph/entities/{food['entity_id']}/neighbors", headers=auth)
    assert neighbors.status_code == 200
    assert any(edge["rel_type"] == "spent_on" for edge in neighbors.json()["edges"])


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/knowledge-graph/entities").status_code == 401
    assert client.post("/knowledge-graph/consolidate").status_code == 401
