"""Tests for the audit log (T2.4)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus, LifeEventRecorded, LifeEventRecordedPayload
from mylife.db.base import Base
from mylife.identity.audit import AuditService, AuditSubscriber

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as db:
        yield db


def test_record_and_list_scoped(session: Session) -> None:
    user, other = uuid.uuid4(), uuid.uuid4()
    audit = AuditService(session)
    audit.record("auth.login", now=NOW, subject_user_id=user, actor_user_id=user)
    audit.record("timeline.query", now=NOW, subject_user_id=other)

    entries = audit.list_for_subject(user)
    assert [e.action for e in entries] == ["auth.login"]
    assert entries[0].actor_user_id == user


def test_append_only() -> None:
    assert not hasattr(AuditService, "update")
    assert not hasattr(AuditService, "delete")


def test_subscriber_records_per_event(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    AuditSubscriber(factory).register(bus)

    event = LifeEventRecorded(
        user_id=user,
        occurred_at=NOW,
        source="manual",
        correlation_id="cid",
        payload=LifeEventRecordedPayload(title="Run", category="health"),
    )
    bus.publish(event)

    with factory() as session:
        entries = AuditService(session).list_for_subject(user)
    assert len(entries) == 1
    assert entries[0].action == "timeline.life_event_recorded"
    assert entries[0].resource == str(event.event_id)
    assert entries[0].correlation_id == "cid"
