"""Tests for the timeline query endpoint (T3.1)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, LifeEventRecorded, LifeEventRecordedPayload
from mylife.db.base import Base, get_session
from mylife.main import create_app

USER = uuid.uuid4()


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

    store = EventStore(db)
    store.append(
        LifeEventRecorded(
            user_id=USER,
            occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
            source="manual",
            correlation_id="c",
            payload=LifeEventRecordedPayload(title="Morning run", category="health"),
        )
    )
    db.commit()

    def override_session() -> Iterator[Session]:
        yield db

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    db.close()
    engine.dispose()


def test_returns_events_for_user(client: TestClient) -> None:
    response = client.get("/timeline/events", params={"user_id": str(USER)})

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["has_more"] is False
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["source"] == "manual"
    assert item["raw_record_id"] is None
    assert item["corrects_event_id"] is None
    assert item["payload"]["title"] == "Morning run"


def test_filters_out_other_users(client: TestClient) -> None:
    response = client.get("/timeline/events", params={"user_id": str(uuid.uuid4())})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_missing_user_id_is_422(client: TestClient) -> None:
    assert client.get("/timeline/events").status_code == 422


def test_limit_out_of_range_is_422(client: TestClient) -> None:
    response = client.get("/timeline/events", params={"user_id": str(USER), "limit": 0})
    assert response.status_code == 422


def test_naive_datetime_is_422(client: TestClient) -> None:
    response = client.get(
        "/timeline/events",
        params={"user_id": str(USER), "occurred_from": "2026-07-18T12:00:00"},
    )
    assert response.status_code == 422


def test_post_records_event_and_is_readable(client: TestClient) -> None:
    new_user = str(uuid.uuid4())
    payload = {
        "user_id": new_user,
        "occurred_at": "2026-07-18T09:30:00+00:00",
        "title": "Yoga",
        "category": "health",
    }

    created = client.post("/timeline/events", json=payload)

    assert created.status_code == 201
    body = created.json()
    assert body["event_id"]
    assert body["source"] == "manual"
    assert body["payload"] == {"title": "Yoga", "category": "health", "note": None}

    listed = client.get("/timeline/events", params={"user_id": new_user})
    assert [i["event_id"] for i in listed.json()["items"]] == [body["event_id"]]


def test_post_naive_datetime_is_422(client: TestClient) -> None:
    response = client.post(
        "/timeline/events",
        json={
            "user_id": str(uuid.uuid4()),
            "occurred_at": "2026-07-18T09:30:00",
            "title": "Yoga",
            "category": "health",
        },
    )
    assert response.status_code == 422


def test_post_missing_field_is_422(client: TestClient) -> None:
    response = client.post(
        "/timeline/events",
        json={"user_id": str(uuid.uuid4()), "occurred_at": "2026-07-18T09:30:00+00:00"},
    )
    assert response.status_code == 422
