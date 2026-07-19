"""Tests for the goals endpoints (T5.1)."""

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


def _goal(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post(
        "/goals",
        json={"title": "Fund", "metric": "net_worth", "target_value": 1000000, "unit": "BRL"},
        headers=auth,
    )
    assert response.status_code == 201
    return str(response.json()["goal_id"])


def test_create_and_list_goal(client: TestClient) -> None:
    auth = _auth(client)
    goal_id = _goal(client, auth)
    assert [g["goal_id"] for g in client.get("/goals", headers=auth).json()] == [goal_id]
    assert client.get(f"/goals/{goal_id}", headers=auth).status_code == 200


def test_record_and_list_milestones(client: TestClient) -> None:
    auth = _auth(client)
    goal_id = _goal(client, auth)

    posted = client.post(
        f"/goals/{goal_id}/milestones", json={"value": 250000, "note": "Q1"}, headers=auth
    )
    assert posted.status_code == 201
    assert posted.json()["value"] == 250000
    milestones = client.get(f"/goals/{goal_id}/milestones", headers=auth).json()
    assert [m["value"] for m in milestones] == [250000]


def test_foreign_goal_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    goal_id = _goal(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    assert client.get(f"/goals/{goal_id}", headers=intruder_auth).status_code == 404
    assert (
        client.post(
            f"/goals/{goal_id}/milestones", json={"value": 1}, headers=intruder_auth
        ).status_code
        == 404
    )


def test_progress_endpoints(client: TestClient) -> None:
    auth = _auth(client)
    goal_id = _goal(client, auth)  # net_worth goal, target 1,000,000, no data yet

    single = client.get(f"/goals/{goal_id}/progress", headers=auth)
    assert single.status_code == 200
    body = single.json()
    assert body["current_value"] == 0
    assert body["achieved"] is False

    listed = client.get("/goals/progress", headers=auth)
    assert listed.status_code == 200
    assert [p["goal_id"] for p in listed.json()] == [goal_id]


def test_progress_foreign_goal_is_404(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    goal_id = _goal(client, owner_auth)
    intruder_auth = _auth(client, "intruder@example.com")
    assert client.get(f"/goals/{goal_id}/progress", headers=intruder_auth).status_code == 404


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/goals").status_code == 401
    assert client.get("/goals/progress").status_code == 401
    assert (
        client.post(
            "/goals",
            json={"title": "x", "metric": "m", "target_value": 1, "unit": "u"},
        ).status_code
        == 401
    )
