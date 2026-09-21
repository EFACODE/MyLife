"""Tests for the notification preference endpoints (T4.8)."""

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


def test_get_preferences_defaults(client: TestClient) -> None:
    auth = _auth(client)

    response = client.get("/notifications/preferences", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["email_enabled"] is True
    assert body["whatsapp_enabled"] is False


def test_set_and_get_preferences(client: TestClient) -> None:
    auth = _auth(client)

    response = client.put(
        "/notifications/preferences",
        json={
            "email_enabled": False,
            "whatsapp_enabled": True,
            "whatsapp_phone": "+5511999999999",
        },
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["whatsapp_phone"] == "+5511999999999"

    fetched = client.get("/notifications/preferences", headers=auth)
    assert fetched.json()["email_enabled"] is False


def test_preferences_require_auth(client: TestClient) -> None:
    assert client.get("/notifications/preferences").status_code == 401
    assert client.put("/notifications/preferences", json={}).status_code == 401
