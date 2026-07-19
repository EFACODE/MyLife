"""Tests for the consent service and enforcement (T2.3)."""

import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import ConnectorRunner, ConsentRequiredError, FetchContext, RawPayload
from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    StoredRawRecord,
)
from mylife.db.base import Base
from mylife.identity.consent import ConsentService

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


def test_grant_revoke_and_state(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    published: list[LifeEvent[object]] = []
    bus.subscribe(published.append)
    service = ConsentService(session, bus)

    assert service.is_granted(user, "calendar") is False

    service.grant(user, "calendar", now=NOW, correlation_id="c")
    assert service.is_granted(user, "calendar") is True

    service.revoke(user, "calendar", now=NOW, correlation_id="c")
    assert service.is_granted(user, "calendar") is False

    service.grant(user, "calendar", now=NOW, correlation_id="c")  # re-grant
    assert service.is_granted(user, "calendar") is True

    assert [e.event_type for e in published] == [
        "identity.consent_granted",
        "identity.consent_revoked",
        "identity.consent_granted",
    ]


def test_list_consents_scoped(session: Session) -> None:
    user, other = uuid.uuid4(), uuid.uuid4()
    service = ConsentService(session, InProcessEventBus())
    service.grant(user, "calendar", now=NOW, correlation_id="c")
    service.grant(user, "bank", now=NOW, correlation_id="c")
    service.grant(other, "calendar", now=NOW, correlation_id="c")

    scopes = [(c.scope, c.granted) for c in service.list_consents(user)]
    assert scopes == [("bank", True), ("calendar", True)]  # ordered by scope


class _FakeConnector:
    source = "calendar"

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        return [RawPayload(content={"title": "T", "category": "work"}, fetched_at=NOW)]

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        yield LifeEventRecorded(
            user_id=raw.user_id,
            occurred_at=raw.fetched_at,
            source=raw.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=LifeEventRecordedPayload(title=content["title"], category=content["category"]),
        )


def test_runner_fails_closed_without_consent(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    consent = ConsentService(session, bus)
    runner = ConnectorRunner(session, bus)
    context = FetchContext(user_id=user, correlation_id="c")

    with pytest.raises(ConsentRequiredError):
        runner.sync(_FakeConnector(), context, consent=consent)
    assert EventStore(session).read_all() == []  # nothing ingested


def test_runner_ingests_with_consent(session: Session) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    consent = ConsentService(session, bus)
    consent.grant(user, "calendar", now=NOW, correlation_id="c")

    result = ConnectorRunner(session, bus).sync(
        _FakeConnector(), FetchContext(user_id=user, correlation_id="c"), consent=consent
    )
    assert (result.raw_ingested, result.events_created) == (1, 1)
