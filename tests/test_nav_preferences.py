"""Tests for per-user sidebar menu preferences (T10.12)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.db.base import Base, get_session
from mylife.main import create_app

PASSWORD = "s3cretpw"
URL = "/users/me/nav-preferences"


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
    client.post("/users", json={"email": email, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_defaults_when_never_set(client: TestClient) -> None:
    response = client.get(URL, headers=_auth(client))
    assert response.status_code == 200
    assert response.json() == {"order": [], "hidden": [], "updated_at": None}


def test_round_trip_and_dedup(client: TestClient) -> None:
    auth = _auth(client)
    saved = client.put(
        URL,
        json={"order": ["/finance", "/", "/finance"], "hidden": ["/health", "/health"]},
        headers=auth,
    )
    assert saved.status_code == 200
    assert saved.json()["order"] == ["/finance", "/"]
    assert saved.json()["hidden"] == ["/health"]
    assert saved.json()["updated_at"] is not None

    replaced = client.put(URL, json={"order": ["/goals"], "hidden": []}, headers=auth)
    assert replaced.json()["order"] == ["/goals"]
    assert client.get(URL, headers=auth).json()["hidden"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"order": ["finance"], "hidden": []},
        {"order": [], "hidden": ["/" + "x" * 64]},
        {"order": ["/a"] * 51, "hidden": []},
        {"order": [], "hidden": [], "extra": 1},
    ],
)
def test_invalid_bodies_are_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.put(URL, json=body, headers=_auth(client)).status_code == 422


def test_requires_auth_and_is_per_user(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"order": [], "hidden": []}).status_code == 401

    ada = _auth(client)
    bob = _auth(client, "bob@example.com")
    client.put(URL, json={"order": ["/finance"], "hidden": ["/"]}, headers=ada)
    assert client.get(URL, headers=bob).json()["order"] == []


def test_export_and_erase_cover_the_preference(client: TestClient) -> None:
    auth = _auth(client)
    client.put(URL, json={"order": ["/finance"], "hidden": ["/health"]}, headers=auth)

    exported = client.get("/me/export", headers=auth)
    assert exported.status_code == 200
    assert exported.json()["nav_preference"]["hidden"] == ["/health"]

    erased = client.delete("/me", headers=auth)
    assert erased.status_code == 200
    assert erased.json()["deleted"]["nav_preferences"] == 1
