"""Tests for the briefing endpoint (T3.6)."""

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

    EventStore(db).append(
        LifeEventRecorded(
            user_id=USER,
            occurred_at=datetime.now(UTC),
            source="manual",
            correlation_id="c",
            payload=LifeEventRecordedPayload(title="Run", category="health"),
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


def test_post_briefing_returns_evidence_linked_lines(client: TestClient) -> None:
    response = client.post("/briefing", json={"user_id": str(USER), "window_hours": 24})

    assert response.status_code == 201
    body = response.json()
    assert body["event_count"] == 1
    total = next(line for line in body["lines"] if line["kind"] == "total")
    assert len(total["evidence"]) == 1


def test_post_briefing_missing_user_is_422(client: TestClient) -> None:
    assert client.post("/briefing", json={"window_hours": 24}).status_code == 422


def test_post_briefing_window_out_of_range_is_422(client: TestClient) -> None:
    response = client.post("/briefing", json={"user_id": str(USER), "window_hours": 0})
    assert response.status_code == 422
