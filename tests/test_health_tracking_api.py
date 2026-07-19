"""Tests for the health tracking endpoints (T4.4)."""

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


def _auth(client: TestClient, email: str = EMAIL) -> dict[str, str]:
    client.post("/users", json={"email": email, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_record_and_list_sleep(client: TestClient) -> None:
    auth = _auth(client)
    posted = client.post(
        "/health/sleep",
        json={
            "occurred_at": "2026-07-19T00:30:00+00:00",
            "duration_minutes": 465,
            "quality": "good",
        },
        headers=auth,
    )
    assert posted.status_code == 201
    assert posted.json()["duration_minutes"] == 465

    listed = client.get("/health/sleep", headers=auth)
    assert listed.status_code == 200
    assert [s["quality"] for s in listed.json()] == ["good"]


def test_record_and_list_workouts(client: TestClient) -> None:
    auth = _auth(client)
    client.post(
        "/health/workouts",
        json={
            "occurred_at": "2026-07-19T07:00:00+00:00",
            "activity": "run",
            "duration_minutes": 42,
            "distance_meters": 8000,
            "energy_kcal": 520,
        },
        headers=auth,
    )
    workouts = client.get("/health/workouts", headers=auth).json()
    assert [w["activity"] for w in workouts] == ["run"]
    assert workouts[0]["distance_meters"] == 8000


def test_invalid_duration_is_422(client: TestClient) -> None:
    auth = _auth(client)
    response = client.post(
        "/health/sleep",
        json={"occurred_at": "2026-07-19T00:30:00+00:00", "duration_minutes": 0},
        headers=auth,
    )
    assert response.status_code == 422


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/health/sleep").status_code == 401
    assert client.get("/health/workouts").status_code == 401
    assert (
        client.post(
            "/health/workouts",
            json={
                "occurred_at": "2026-07-19T07:00:00+00:00",
                "activity": "run",
                "duration_minutes": 42,
            },
        ).status_code
        == 401
    )
