"""Tests for the consent endpoints (T2.3)."""

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


def _auth_header(client: TestClient) -> dict[str, str]:
    client.post("/users", json={"email": EMAIL, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_grant_list_and_revoke(client: TestClient) -> None:
    auth = _auth_header(client)

    granted = client.post("/consents", json={"scope": "calendar"}, headers=auth)
    assert granted.status_code == 201
    assert granted.json() == {
        "scope": "calendar",
        "granted": True,
        "updated_at": granted.json()["updated_at"],
    }

    listed = client.get("/consents", headers=auth)
    assert listed.status_code == 200
    assert [c["scope"] for c in listed.json()] == ["calendar"]

    revoked = client.delete("/consents/calendar", headers=auth)
    assert revoked.status_code == 204

    after = client.get("/consents", headers=auth)
    assert after.json()[0]["granted"] is False


def test_consent_requires_authentication(client: TestClient) -> None:
    assert client.get("/consents").status_code == 401
    assert client.post("/consents", json={"scope": "calendar"}).status_code == 401
