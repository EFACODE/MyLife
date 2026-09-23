"""Tests for the identity endpoints (T2.1)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.db.base import Base, get_session
from mylife.main import create_app


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


def _auth(client: TestClient, email: str = "ada@example.com") -> dict[str, str]:
    client.post("/users", json={"email": email, "display_name": "Ada", "password": "s3cretpw"})
    token = client.post("/auth/login", data={"username": email, "password": "s3cretpw"}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_update_current_user_display_name(client: TestClient) -> None:
    auth = _auth(client)

    response = client.patch("/users/me", json={"display_name": "Ada Lovelace"}, headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"  # unchanged, not accepted by the request


def test_update_current_user_requires_auth(client: TestClient) -> None:
    response = client.patch("/users/me", json={"display_name": "Ada Lovelace"})
    assert response.status_code == 401


def test_register_and_read_user(client: TestClient) -> None:
    created = client.post(
        "/users", json={"email": "ada@example.com", "display_name": "Ada", "password": "s3cretpw"}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "ada@example.com"
    assert body["status"] == "active"

    fetched = client.get(f"/users/{body['user_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["user_id"] == body["user_id"]


def test_duplicate_email_is_409(client: TestClient) -> None:
    client.post(
        "/users", json={"email": "dup@example.com", "display_name": "A", "password": "s3cretpw"}
    )
    again = client.post(
        "/users", json={"email": "dup@example.com", "display_name": "B", "password": "s3cretpw"}
    )
    assert again.status_code == 409


def test_invalid_email_is_422(client: TestClient) -> None:
    response = client.post(
        "/users", json={"email": "nope", "display_name": "A", "password": "s3cretpw"}
    )
    assert response.status_code == 422


def test_unknown_user_is_404(client: TestClient) -> None:
    assert client.get("/users/11111111-1111-1111-1111-111111111111").status_code == 404


def test_household_create_link_and_unknown(client: TestClient) -> None:
    household = client.post("/households", json={"name": "Home"})
    assert household.status_code == 201
    household_id = household.json()["household_id"]

    user = client.post(
        "/users",
        json={
            "email": "h@example.com",
            "display_name": "H",
            "password": "s3cretpw",
            "household_id": household_id,
        },
    )
    assert user.status_code == 201
    assert user.json()["household_id"] == household_id

    unknown = client.post(
        "/users",
        json={
            "email": "u@example.com",
            "display_name": "U",
            "password": "s3cretpw",
            "household_id": "22222222-2222-2222-2222-222222222222",
        },
    )
    assert unknown.status_code == 422
