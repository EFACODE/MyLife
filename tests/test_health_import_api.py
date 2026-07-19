"""Tests for the health CSV import endpoint (T4.5)."""

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
    "kind,occurred_at,duration_minutes,quality,activity,distance_meters,energy_kcal,external_id\n"
    "sleep,2026-07-19T00:30:00+00:00,465,good,,,,s-1\n"
    "workout,2026-07-19T07:00:00+00:00,42,,run,8000,520,w-1\n"
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


def _auth(client: TestClient) -> dict[str, str]:
    client.post("/users", json={"email": EMAIL, "display_name": "Ada", "password": PASSWORD})
    token = client.post("/auth/login", data={"username": EMAIL, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _grant_health(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/consents", json={"scope": "health"}, headers=auth).status_code == 201


def test_import_requires_consent(client: TestClient) -> None:
    auth = _auth(client)
    response = client.post("/health/connectors/import", json={"csv": CSV}, headers=auth)
    assert response.status_code == 403
    assert client.get("/health/sleep", headers=auth).json() == []


def test_import_after_consent_creates_events(client: TestClient) -> None:
    auth = _auth(client)
    _grant_health(client, auth)

    response = client.post("/health/connectors/import", json={"csv": CSV}, headers=auth)
    assert response.status_code == 201
    body = response.json()
    assert body["raw_ingested"] == 2
    assert body["events_created"] == 2

    assert [s["duration_minutes"] for s in client.get("/health/sleep", headers=auth).json()] == [
        465
    ]
    assert [w["activity"] for w in client.get("/health/workouts", headers=auth).json()] == ["run"]


def test_import_is_idempotent(client: TestClient) -> None:
    auth = _auth(client)
    _grant_health(client, auth)

    client.post("/health/connectors/import", json={"csv": CSV}, headers=auth)
    second = client.post("/health/connectors/import", json={"csv": CSV}, headers=auth).json()
    assert (second["raw_ingested"], second["skipped_duplicates"]) == (0, 2)


def test_import_requires_auth(client: TestClient) -> None:
    assert client.post("/health/connectors/import", json={"csv": CSV}).status_code == 401
