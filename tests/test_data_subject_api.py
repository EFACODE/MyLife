"""Tests for the data-subject endpoints (T2.5)."""

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


def test_export_returns_bundle(client: TestClient) -> None:
    auth = _auth(client)
    response = client.get("/me/export", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == EMAIL
    assert "events" in body and "consents" in body and "audit" in body


def test_delete_account_then_token_is_401(client: TestClient) -> None:
    auth = _auth(client)

    deleted = client.delete("/me", headers=auth)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["users"] == 1

    # The user no longer exists, so the (still-valid) token resolves to 401.
    assert client.get("/auth/me", headers=auth).status_code == 401


def test_export_requires_auth(client: TestClient) -> None:
    assert client.get("/me/export").status_code == 401
