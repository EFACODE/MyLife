"""Semantic retrieval over document text (T6.3).

Indexes extracted text (T6.2) as vectors and answers similarity queries. Behind
ports: a dependency-free, deterministic ``HashingEmbedder`` ships; real embedding
models and a pgvector index are documented production adapters. Vectors are
stored as JSON and scored with in-Python cosine similarity (portable across
SQLite/Postgres). Indexing emits ``MemoryIndexed`` referencing the document. See
``specs/domain/knowledge/semantic-retrieval.md``.
"""

import hashlib
import logging
import math
import re
import uuid
from datetime import datetime
from typing import Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.db.base import Base
from mylife.knowledge.extraction import DocumentTextRow
from mylife.knowledge.models import KNOWLEDGE_SOURCE, DocumentRow
from mylife.knowledge.service import UnknownDocumentError

logger = logging.getLogger(__name__)

MEMORY_INDEXED: Final = "knowledge.memory_indexed"
_DEFAULT_DIMENSION: Final = 256
_PREVIEW_CHARS: Final = 200
_TOKEN = re.compile(r"[a-z0-9]+")


class DocumentNotExtractedError(Exception):
    """Raised when indexing a document that has no extracted text yet."""

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(f"document {document_id} has no extracted text")
        self.document_id = document_id


@runtime_checkable
class Embedder(Protocol):
    """Turns text into a fixed-dimension vector."""

    name: str
    dimension: int

    def embed(self, text: str) -> list[float]:
        """Return the embedding of ``text``."""
        ...


class HashingEmbedder:
    """A deterministic bag-of-words hashing embedder (stdlib only).

    Lexical, not truly semantic — enough to prove the pipeline; a real model
    adapter can replace it behind the :class:`Embedder` port.
    """

    def __init__(self, dimension: int = _DEFAULT_DIMENSION) -> None:
        self.name = "hashing-v1"
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            vector[int(digest, 16) % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for equal-length L2-normalized vectors (a dot product)."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


class MemoryRow(Base):
    """A document's indexed vector (one memory per document)."""

    __tablename__ = "memory_index"

    memory_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    embedder: Mapped[str] = mapped_column(String)
    dimension: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSON)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Memory(BaseModel):
    """A memory's metadata as read back."""

    model_config = ConfigDict(frozen=True)

    memory_id: uuid.UUID
    document_id: uuid.UUID
    embedder: str
    dimension: int
    indexed_at: datetime


class SearchHit(BaseModel):
    """A search result — a document and its similarity to the query."""

    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    score: float
    preview: str


class MemoryIndexedPayload(BaseModel):
    """The index fact — references the document, not the vector/text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: uuid.UUID
    document_id: uuid.UUID
    embedder: str
    dimension: int


class MemoryIndexed(LifeEvent[MemoryIndexedPayload]):
    """Emitted when a document's text is indexed for retrieval (Knowledge)."""

    event_type: Literal["knowledge.memory_indexed"] = MEMORY_INDEXED
    schema_version: Literal[1] = 1


class RetrievalService:
    """Indexes document text and answers similarity queries (user-scoped)."""

    def __init__(self, session: Session, bus: EventBus, embedder: Embedder | None = None) -> None:
        self._session = session
        self._bus = bus
        self._embedder = embedder or HashingEmbedder()

    def index_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID, *, now: datetime, correlation_id: str
    ) -> Memory:
        """Embed a document's extracted text into the memory index."""
        document = self._session.get(DocumentRow, document_id)
        if document is None or document.user_id != user_id:
            raise UnknownDocumentError(document_id)
        text_row = self._session.get(DocumentTextRow, document_id)
        if text_row is None:
            raise DocumentNotExtractedError(document_id)

        vector = self._embedder.embed(text_row.text)
        row = self._session.scalars(
            select(MemoryRow).where(MemoryRow.document_id == document_id)
        ).one_or_none()
        if row is None:
            memory_id = uuid.uuid4()
            self._session.add(
                MemoryRow(
                    memory_id=memory_id,
                    user_id=user_id,
                    document_id=document_id,
                    embedder=self._embedder.name,
                    dimension=self._embedder.dimension,
                    vector=vector,
                    indexed_at=now,
                )
            )
        else:
            memory_id = row.memory_id
            row.embedder = self._embedder.name
            row.dimension = self._embedder.dimension
            row.vector = vector
            row.indexed_at = now

        event = MemoryIndexed(
            user_id=user_id,
            occurred_at=now,
            source=KNOWLEDGE_SOURCE,
            correlation_id=correlation_id,
            payload=MemoryIndexedPayload(
                memory_id=memory_id,
                document_id=document_id,
                embedder=self._embedder.name,
                dimension=self._embedder.dimension,
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return Memory(
            memory_id=memory_id,
            document_id=document_id,
            embedder=self._embedder.name,
            dimension=self._embedder.dimension,
            indexed_at=now,
        )

    def search(self, user_id: uuid.UUID, query: str, *, limit: int = 5) -> list[SearchHit]:
        """Return the user's documents most similar to ``query``, best first."""
        query_vector = self._embedder.embed(query)
        rows = list(self._session.scalars(select(MemoryRow).where(MemoryRow.user_id == user_id)))
        scored = [(row.document_id, _cosine(query_vector, list(row.vector))) for row in rows]
        # Descending score; ties broken deterministically by document id.
        scored.sort(key=lambda item: (-item[1], str(item[0])))
        hits: list[SearchHit] = []
        for document_id, score in scored[:limit]:
            text_row = self._session.get(DocumentTextRow, document_id)
            preview = text_row.text[:_PREVIEW_CHARS] if text_row is not None else ""
            hits.append(SearchHit(document_id=document_id, score=score, preview=preview))
        return hits
