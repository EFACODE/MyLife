"""Tests for the raw ingestion store (T1.4).

Runs against a shared in-memory SQLite database.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import (
    DuplicateRawRecordError,
    RawRecord,
    RawRecordStore,
    checksum_of,
)
from mylife.db.base import Base


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


def _raw(source: str = "calendar", content: dict[str, object] | None = None) -> RawRecord:
    return RawRecord(
        user_id=uuid.uuid4(),
        source=source,
        external_id="evt-1",
        content=content if content is not None else {"title": "Meeting", "when": "2026-07-18"},
        fetched_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
        correlation_id="corr-1",
    )


def test_store_and_get_round_trip(session: Session) -> None:
    store = RawRecordStore(session)
    raw = _raw()

    stored = store.store(raw)
    fetched = store.get(stored.raw_record_id)

    assert fetched is not None
    assert fetched == stored
    assert fetched.content == raw.content
    assert fetched.fetched_at == raw.fetched_at
    assert fetched.checksum == checksum_of(raw.content)


def test_checksum_is_deterministic_and_content_sensitive() -> None:
    assert checksum_of({"a": 1, "b": 2}) == checksum_of({"b": 2, "a": 1})
    assert checksum_of({"a": 1}) != checksum_of({"a": 2})


def test_duplicate_source_checksum_rejected(session: Session) -> None:
    store = RawRecordStore(session)
    raw = _raw()
    first = store.store(raw)

    # Same content from the same source -> same checksum -> duplicate.
    with pytest.raises(DuplicateRawRecordError):
        store.store(_raw(content=dict(raw.content)))  # type: ignore[arg-type]

    by_checksum = store.get_by_checksum(raw.source, first.checksum)
    assert by_checksum is not None
    assert by_checksum.raw_record_id == first.raw_record_id


def test_same_content_different_source_is_allowed(session: Session) -> None:
    store = RawRecordStore(session)
    content = {"title": "same"}
    a = store.store(_raw(source="calendar", content=content))
    b = store.store(_raw(source="bank", content=content))

    assert a.checksum == b.checksum
    assert a.raw_record_id != b.raw_record_id


def test_store_is_append_only() -> None:
    assert not hasattr(RawRecordStore, "update")
    assert not hasattr(RawRecordStore, "delete")


def test_get_missing_returns_none(session: Session) -> None:
    store = RawRecordStore(session)
    assert store.get(uuid.uuid4()) is None
    assert store.get_by_checksum("calendar", "deadbeef") is None
