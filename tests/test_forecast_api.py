"""Tests for the forecast endpoints (T8.1)."""

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


def _capture_event(client: TestClient, auth: dict[str, str]) -> str:
    """Create a real event owned by the user (a finance expense) and return its id."""
    account = client.post(
        "/accounts", json={"name": "Checking", "currency": "BRL"}, headers=auth
    ).json()
    response = client.post(
        "/finance/expenses",
        json={
            "account_id": account["account_id"],
            "amount_minor": 4599,
            "currency": "BRL",
            "description": "Lunch",
            "category": "food",
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["event_id"])


def _forecast_body(event_id: str) -> dict:
    return {
        "metric": "cash_flow",
        "unit": "BRL_minor",
        "horizon_days": 30,
        "points": [
            {
                "at": "2026-08-18T00:00:00+00:00",
                "value": -120000,
                "lower": -180000,
                "upper": -60000,
            }
        ],
        "assumptions": [
            {
                "name": "recurring_income",
                "value": "steady at last 90d average",
                "basis": "3 salary credits, low variance",
            }
        ],
        "evidence": [event_id],
        "confidence": 0.6,
        "limitations": "Assumes no one-off large expenses in the window",
    }


def test_create_and_get_forecast_with_evidence(client: TestClient) -> None:
    auth = _auth(client)
    event_id = _capture_event(client, auth)

    created = client.post("/forecasts", json=_forecast_body(event_id), headers=auth)
    assert created.status_code == 201, created.text
    forecast_id = created.json()["forecast_id"]

    detail = client.get(f"/forecasts/{forecast_id}", headers=auth)
    assert detail.status_code == 200
    body = detail.json()
    assert body["evidence"] == [event_id]
    assert body["assumptions"][0]["name"] == "recurring_income"
    assert body["points"][0]["upper"] == -60000
    assert [e["event_id"] for e in body["evidence_events"]] == [event_id]
    # The forecast shows up in the user's list.
    assert len(client.get("/forecasts", headers=auth).json()) == 1


def test_missing_assumptions_is_422(client: TestClient) -> None:
    auth = _auth(client)
    event_id = _capture_event(client, auth)
    body = _forecast_body(event_id)
    body["assumptions"] = []
    assert client.post("/forecasts", json=body, headers=auth).status_code == 422


def test_empty_evidence_is_422(client: TestClient) -> None:
    auth = _auth(client)
    body = _forecast_body("00000000-0000-0000-0000-000000000000")
    body["evidence"] = []
    assert client.post("/forecasts", json=body, headers=auth).status_code == 422


def test_foreign_evidence_is_422(client: TestClient) -> None:
    owner_auth = _auth(client, "owner@example.com")
    event_id = _capture_event(client, owner_auth)

    intruder_auth = _auth(client, "intruder@example.com")
    response = client.post("/forecasts", json=_forecast_body(event_id), headers=intruder_auth)
    assert response.status_code == 422


def test_malformed_interval_is_422(client: TestClient) -> None:
    auth = _auth(client)
    event_id = _capture_event(client, auth)
    body = _forecast_body(event_id)
    body["points"][0]["lower"] = 0  # now lower(0) > value(-120000)
    assert client.post("/forecasts", json=body, headers=auth).status_code == 422


def test_confidence_out_of_range_is_422(client: TestClient) -> None:
    auth = _auth(client)
    event_id = _capture_event(client, auth)
    body = _forecast_body(event_id)
    body["confidence"] = 1.5
    assert client.post("/forecasts", json=body, headers=auth).status_code == 422


def test_unknown_forecast_is_404(client: TestClient) -> None:
    auth = _auth(client)
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/forecasts/{missing}", headers=auth).status_code == 404


def test_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/forecasts").status_code == 401
    assert client.post("/forecasts", json=_forecast_body("x")).status_code == 401
