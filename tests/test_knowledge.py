"""Tests for the knowledge service — document ingest (T6.1)."""

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.identity.data_subject import DataSubjectService
from mylife.knowledge import (
    DOCUMENT_INGESTED,
    InMemoryBlobStore,
    KnowledgeService,
    UnknownDocumentError,
)

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
DATA = b"%PDF-1.7 fake statement bytes"


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


@pytest.fixture
def knowledge(session: Session, blobs: InMemoryBlobStore) -> KnowledgeService:
    return KnowledgeService(session, InProcessEventBus(), blobs)


def test_ingest_stores_blob_and_emits_event(
    knowledge: KnowledgeService, session: Session, blobs: InMemoryBlobStore
) -> None:
    user = uuid.uuid4()
    doc = knowledge.ingest_document(
        user, "statement.pdf", "application/pdf", DATA, now=NOW, correlation_id="c"
    )

    assert doc.byte_size == len(DATA)
    assert doc.checksum == hashlib.sha256(DATA).hexdigest()
    assert blobs.get(f"{user}/{doc.document_id}") == DATA
    assert [e.event_type for e in EventStore(session).read_stream(user)] == [DOCUMENT_INGESTED]
    # The event references the blob, never the bytes.
    payload = EventStore(session).read_stream(user)[0].payload
    assert payload["storage_key"] == f"{user}/{doc.document_id}"
    assert "data" not in payload


def test_content_round_trips_identical_bytes(knowledge: KnowledgeService) -> None:
    user = uuid.uuid4()
    doc = knowledge.ingest_document(user, "a.txt", "text/plain", DATA, now=NOW, correlation_id="c")
    got_doc, got_bytes = knowledge.get_content(user, doc.document_id)
    assert got_doc.document_id == doc.document_id
    assert got_bytes == DATA


def test_list_and_get_scoped(knowledge: KnowledgeService) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    doc = knowledge.ingest_document(user, "a.txt", "text/plain", DATA, now=NOW, correlation_id="c")
    knowledge.ingest_document(other, "b.txt", "text/plain", DATA, now=NOW, correlation_id="c")

    assert [d.document_id for d in knowledge.list_documents(user)] == [doc.document_id]
    assert knowledge.get_document(other, doc.document_id) is None


def test_get_content_unknown_raises(knowledge: KnowledgeService) -> None:
    with pytest.raises(UnknownDocumentError):
        knowledge.get_content(uuid.uuid4(), uuid.uuid4())


def test_erasure_deletes_documents_and_blobs(session: Session, blobs: InMemoryBlobStore) -> None:
    from mylife.identity import IdentityService

    user = IdentityService(session, InProcessEventBus()).register_user(
        "ada@example.com", "Ada", password="s3cretpw", now=NOW, correlation_id="c"
    )
    session.commit()
    doc = KnowledgeService(session, InProcessEventBus(), blobs).ingest_document(
        user.user_id, "a.txt", "text/plain", DATA, now=NOW, correlation_id="c"
    )
    key = f"{user.user_id}/{doc.document_id}"
    assert blobs.exists(key)

    result = DataSubjectService(session, blobs).erase(user.user_id)
    assert result.deleted["documents"] == 1
    assert not blobs.exists(key)  # blob gone too
