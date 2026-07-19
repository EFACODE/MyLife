"""Tests for data-subject export and erasure (T2.5)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)
from mylife.db.base import Base
from mylife.identity import IdentityService
from mylife.identity.audit import AuditService
from mylife.identity.consent import ConsentService
from mylife.identity.data_subject import DataSubjectService

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def _seed(session: Session, email: str) -> uuid.UUID:
    bus = InProcessEventBus()
    user = IdentityService(session, bus).register_user(
        email, "Name", password="s3cretpw", now=NOW, correlation_id="c"
    )
    EventStore(session).append(
        LifeEventRecorded(
            user_id=user.user_id,
            occurred_at=NOW,
            source="manual",
            correlation_id="c",
            payload=LifeEventRecordedPayload(title="Run", category="health"),
        )
    )
    ConsentService(session, bus).grant(user.user_id, "calendar", now=NOW, correlation_id="c")
    AuditService(session).record("auth.login", now=NOW, subject_user_id=user.user_id)
    session.commit()
    return user.user_id


def test_export_gathers_user_data(session: Session) -> None:
    user_id = _seed(session, "ada@example.com")

    bundle = DataSubjectService(session).export(user_id)

    assert bundle.user is not None
    assert bundle.user.email == "ada@example.com"
    assert any(e.event_type == "timeline.life_event_recorded" for e in bundle.events)
    assert [c.scope for c in bundle.consents] == ["calendar"]
    assert any(a.action == "auth.login" for a in bundle.audit)


def test_erase_removes_user_and_leaves_others(session: Session) -> None:
    victim = _seed(session, "victim@example.com")
    bystander = _seed(session, "bystander@example.com")

    result = DataSubjectService(session).erase(victim)

    assert result.deleted["users"] == 1
    assert result.deleted["events"] >= 1
    # Victim is gone...
    empty = DataSubjectService(session).export(victim)
    assert empty.user is None
    assert empty.events == []
    # ...bystander is intact.
    assert DataSubjectService(session).export(bystander).user is not None
    assert len(EventStore(session).read_stream(bystander)) >= 1
