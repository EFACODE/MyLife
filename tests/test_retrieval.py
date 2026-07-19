"""Tests for semantic retrieval (T6.3)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.knowledge import (
    MEMORY_INDEXED,
    DocumentNotExtractedError,
    ExtractionService,
    HashingEmbedder,
    InMemoryBlobStore,
    KnowledgeService,
    MemoryRow,
    RetrievalService,
    UnknownDocumentError,
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


def _ingest_and_extract(
    session: Session, blobs: InMemoryBlobStore, user: uuid.UUID, text: str
) -> uuid.UUID:
    bus = InProcessEventBus()
    doc = KnowledgeService(session, bus, blobs).ingest_document(
        user, "doc", "text/plain", text.encode(), now=NOW, correlation_id="c"
    )
    ExtractionService(session, bus, blobs).extract_document(
        user, doc.document_id, now=NOW, correlation_id="c"
    )
    return doc.document_id


def test_hashing_embedder_is_unit_and_deterministic() -> None:
    emb = HashingEmbedder(dimension=64)
    v1 = emb.embed("the quick brown fox")
    v2 = emb.embed("the quick brown fox")
    assert v1 == v2
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-9  # L2-normalized
    assert emb.embed("") == [0.0] * 64  # empty -> zero vector


def test_index_creates_memory_and_event(session: Session, blobs: InMemoryBlobStore) -> None:
    user = uuid.uuid4()
    doc_id = _ingest_and_extract(session, blobs, user, "budget report about finances")

    memory = RetrievalService(session, InProcessEventBus()).index_document(
        user, doc_id, now=NOW, correlation_id="c"
    )
    assert memory.document_id == doc_id
    assert memory.embedder == "hashing-v1"
    assert MEMORY_INDEXED in [e.event_type for e in EventStore(session).read_stream(user)]


def test_search_ranks_relevant_document_first(session: Session, blobs: InMemoryBlobStore) -> None:
    user = uuid.uuid4()
    finance_doc = _ingest_and_extract(session, blobs, user, "annual budget and spending report")
    health_doc = _ingest_and_extract(session, blobs, user, "sleep and workout training log")
    service = RetrievalService(session, InProcessEventBus())
    service.index_document(user, finance_doc, now=NOW, correlation_id="c")
    service.index_document(user, health_doc, now=NOW, correlation_id="c")

    hits = service.search(user, "budget spending")
    assert hits[0].document_id == finance_doc
    assert hits[0].score > 0
    assert hits[0].preview.startswith("annual budget")


def test_reindex_updates_single_memory(session: Session, blobs: InMemoryBlobStore) -> None:
    user = uuid.uuid4()
    doc_id = _ingest_and_extract(session, blobs, user, "first")
    service = RetrievalService(session, InProcessEventBus())
    service.index_document(user, doc_id, now=NOW, correlation_id="c")
    service.index_document(user, doc_id, now=NOW, correlation_id="c")

    memories = list(session.scalars(select(MemoryRow)))
    assert len([m for m in memories if m.document_id == doc_id]) == 1


def test_index_without_text_raises(session: Session, blobs: InMemoryBlobStore) -> None:
    user = uuid.uuid4()
    doc = KnowledgeService(session, InProcessEventBus(), blobs).ingest_document(
        user, "doc", "text/plain", b"hi", now=NOW, correlation_id="c"
    )
    with pytest.raises(DocumentNotExtractedError):
        RetrievalService(session, InProcessEventBus()).index_document(
            user, doc.document_id, now=NOW, correlation_id="c"
        )


def test_index_foreign_document_raises(session: Session, blobs: InMemoryBlobStore) -> None:
    with pytest.raises(UnknownDocumentError):
        RetrievalService(session, InProcessEventBus()).index_document(
            uuid.uuid4(), uuid.uuid4(), now=NOW, correlation_id="c"
        )


def test_search_scoped_to_user(session: Session, blobs: InMemoryBlobStore) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    doc_id = _ingest_and_extract(session, blobs, other, "private notes")
    RetrievalService(session, InProcessEventBus()).index_document(
        other, doc_id, now=NOW, correlation_id="c"
    )
    assert RetrievalService(session, InProcessEventBus()).search(user, "notes") == []
