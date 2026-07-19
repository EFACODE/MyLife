"""Tests for the connector framework (T3.4)."""

import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.connectors import (
    ConnectorRegistry,
    ConnectorRunner,
    FetchContext,
    ProvenanceMismatchError,
    RawPayload,
    UnknownConnectorError,
)
from mylife.core.events import (
    EventStore,
    InProcessEventBus,
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    StoredRawRecord,
)
from mylife.db.base import Base
from mylife.timeline import TimelineQueryFilter, TimelineQueryService
from mylife.workers.tasks import celery_app

FETCHED_AT = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


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


class FakeConnector:
    """A connector that emits one LifeEventRecorded per payload."""

    source = "fake"

    def __init__(self, payloads: list[RawPayload]) -> None:
        self._payloads = payloads

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        return list(self._payloads)

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


class BadProvenanceConnector(FakeConnector):
    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        yield LifeEventRecorded(
            user_id=raw.user_id,
            occurred_at=raw.fetched_at,
            source=raw.source,
            correlation_id=raw.correlation_id,
            raw_record_id=None,  # wrong: not linked to the raw record
            payload=LifeEventRecordedPayload(title=content["title"], category=content["category"]),
        )


def _payload(title: str, category: str = "health") -> RawPayload:
    return RawPayload(content={"title": title, "category": category}, fetched_at=FETCHED_AT)


def _context(user: uuid.UUID) -> FetchContext:
    return FetchContext(user_id=user, correlation_id="corr-1")


def test_sync_ingests_normalizes_and_links_provenance(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    connector = FakeConnector([_payload("Run"), _payload("Swim")])
    bus = InProcessEventBus()
    published: list[LifeEvent[Any]] = []
    bus.subscribe(published.append)

    with factory() as session:
        result = ConnectorRunner(session, bus).sync(connector, _context(user))

    assert (result.raw_ingested, result.events_created, result.skipped_duplicates) == (2, 2, 0)
    assert len(published) == 2

    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
    assert len(events) == 2
    assert all(e.raw_record_id is not None for e in events)


def test_resync_is_idempotent(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    connector = FakeConnector([_payload("Run"), _payload("Swim")])
    bus = InProcessEventBus()

    with factory() as session:
        ConnectorRunner(session, bus).sync(connector, _context(user))
    with factory() as session:
        second = ConnectorRunner(session, bus).sync(connector, _context(user))

    assert (second.raw_ingested, second.events_created, second.skipped_duplicates) == (0, 0, 2)
    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
    assert len(events) == 2  # unchanged


def test_changed_payload_ingests_as_new(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()
    with factory() as session:
        ConnectorRunner(session, bus).sync(FakeConnector([_payload("Run")]), _context(user))
    with factory() as session:
        result = ConnectorRunner(session, bus).sync(
            FakeConnector([_payload("Run", category="fitness")]), _context(user)
        )

    assert (result.raw_ingested, result.events_created) == (1, 1)
    with factory() as session:
        events = TimelineQueryService(session).query(TimelineQueryFilter(user_id=user)).items
    assert len(events) == 2


def test_provenance_mismatch_is_rejected_and_rolls_back(factory: sessionmaker[Session]) -> None:
    user = uuid.uuid4()
    bus = InProcessEventBus()

    connector = BadProvenanceConnector([_payload("Run")])
    with factory() as session, pytest.raises(ProvenanceMismatchError):
        ConnectorRunner(session, bus).sync(connector, _context(user))

    # The whole batch rolled back: nothing persisted.
    with factory() as session:
        assert EventStore(session).read_all() == []


def test_registry_register_get_all() -> None:
    reg = ConnectorRegistry()
    connector = FakeConnector([])
    reg.register(connector)

    assert reg.get("fake") is connector
    assert reg.all() == [connector]
    with pytest.raises(UnknownConnectorError):
        reg.get("missing")


def test_sync_connector_task_is_registered() -> None:
    assert "mylife.sync_connector" in celery_app.tasks
