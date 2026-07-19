"""Tests for document text extraction (T6.2)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.knowledge import (
    DOCUMENT_TEXT_EXTRACTED,
    ExtractionService,
    InMemoryBlobStore,
    KnowledgeService,
    UnknownDocumentError,
    UnsupportedContentTypeError,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


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


@pytest.fixture
def blobs() -> InMemoryBlobStore:
    return InMemoryBlobStore()


def _ingest(session: Session, blobs: InMemoryBlobStore, content_type: str, data: bytes) -> tuple:
    user = uuid.uuid4()
    doc = KnowledgeService(session, InProcessEventBus(), blobs).ingest_document(
        user, "doc", content_type, data, now=NOW, correlation_id="c"
    )
    return user, doc


def test_extract_plain_text(session: Session, blobs: InMemoryBlobStore) -> None:
    user, doc = _ingest(session, blobs, "text/plain", b"Hello, world!")
    service = ExtractionService(session, InProcessEventBus(), blobs)

    result = service.extract_document(user, doc.document_id, now=NOW, correlation_id="c")
    assert result.method == "plaintext-utf8"
    assert result.char_count == len("Hello, world!")
    assert service.get_text(user, doc.document_id) == "Hello, world!"

    types = [e.event_type for e in EventStore(session).read_stream(user)]
    assert DOCUMENT_TEXT_EXTRACTED in types


def test_reextract_updates_single_row(session: Session, blobs: InMemoryBlobStore) -> None:
    user, doc = _ingest(session, blobs, "text/plain", b"first")
    service = ExtractionService(session, InProcessEventBus(), blobs)
    service.extract_document(user, doc.document_id, now=NOW, correlation_id="c")

    # Overwrite the blob and re-extract.
    blobs.put(f"{user}/{doc.document_id}", b"second version")
    service.extract_document(user, doc.document_id, now=NOW, correlation_id="c")

    assert service.get_text(user, doc.document_id) == "second version"
    extracted = [
        e for e in EventStore(session).read_stream(user) if e.event_type == DOCUMENT_TEXT_EXTRACTED
    ]
    assert len(extracted) == 2  # a new event each run (derived row is upserted)


def test_unsupported_content_type_raises(session: Session, blobs: InMemoryBlobStore) -> None:
    user, doc = _ingest(session, blobs, "application/pdf", b"%PDF-1.7")
    service = ExtractionService(session, InProcessEventBus(), blobs)
    with pytest.raises(UnsupportedContentTypeError):
        service.extract_document(user, doc.document_id, now=NOW, correlation_id="c")
    assert service.get_text(user, doc.document_id) is None


def test_extract_unknown_document_raises(session: Session, blobs: InMemoryBlobStore) -> None:
    service = ExtractionService(session, InProcessEventBus(), blobs)
    with pytest.raises(UnknownDocumentError):
        service.extract_document(uuid.uuid4(), uuid.uuid4(), now=NOW, correlation_id="c")


def test_get_text_scoped(session: Session, blobs: InMemoryBlobStore) -> None:
    user, doc = _ingest(session, blobs, "text/plain", b"secret")
    ExtractionService(session, InProcessEventBus(), blobs).extract_document(
        user, doc.document_id, now=NOW, correlation_id="c"
    )
    assert (
        ExtractionService(session, InProcessEventBus(), blobs).get_text(
            uuid.uuid4(), doc.document_id
        )
        is None
    )
