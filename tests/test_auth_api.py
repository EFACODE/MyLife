"""Tests for the authentication endpoints (T2.2)."""

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


def _register(client: TestClient) -> None:
    response = client.post(
        "/users", json={"email": EMAIL, "display_name": "Ada", "password": PASSWORD}
    )
    assert response.status_code == 201


def _login(client: TestClient, password: str = PASSWORD) -> dict[str, object]:
    return client.post("/auth/login", data={"username": EMAIL, "password": password}).json()


def test_register_login_and_me(client: TestClient) -> None:
    _register(client)

    login = client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD})
    assert login.status_code == 200
    body = login.json()
    assert body["token_type"] == "bearer"
    token = body["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_wrong_password_is_401(client: TestClient) -> None:
    _register(client)
    login = client.post("/auth/login", data={"username": EMAIL, "password": "nope-wrong"})
    assert login.status_code == 401


def test_me_without_token_is_401(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_with_bad_token_is_401(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
