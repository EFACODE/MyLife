"""Knowledge service — document ingest and retrieval.

Ingesting a document stores its **bytes** in the blob store (raw source data),
writes a ``documents`` metadata row and emits ``DocumentIngested``
(commit-before-publish). Reads are user-scoped; the blob key is namespaced by
``user_id``. See ``specs/domain/knowledge/document-ingest.md`` (T6.1).
"""

import contextlib
import hashlib
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.core.events.store import _stored_utc
from mylife.knowledge.blob_store import BlobNotFoundError, BlobStore
from mylife.knowledge.models import (
    KNOWLEDGE_SOURCE,
    Document,
    DocumentIngested,
    DocumentIngestedPayload,
    DocumentRow,
)

logger = logging.getLogger(__name__)


class UnknownDocumentError(Exception):
    """Raised when a document is missing or not owned by the acting user."""

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(f"document {document_id} not found")
        self.document_id = document_id


def _to_document(row: DocumentRow) -> Document:
    return Document(
        document_id=row.document_id,
        filename=row.filename,
        content_type=row.content_type,
        byte_size=row.byte_size,
        checksum=row.checksum,
        created_at=_stored_utc(row.created_at),
    )


class KnowledgeService:
    """Ingests and reads a user's documents (metadata in DB, bytes in the store)."""

    def __init__(self, session: Session, bus: EventBus, blob_store: BlobStore) -> None:
        self._session = session
        self._bus = bus
        self._blobs = blob_store

    def ingest_document(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
        *,
        now: datetime,
        correlation_id: str,
    ) -> Document:
        """Store the bytes, register metadata and emit ``DocumentIngested``."""
        document_id = uuid.uuid4()
        storage_key = f"{user_id}/{document_id}"
        checksum = hashlib.sha256(data).hexdigest()

        self._blobs.put(storage_key, data)
        try:
            row = DocumentRow(
                document_id=document_id,
                user_id=user_id,
                filename=filename,
                content_type=content_type,
                byte_size=len(data),
                checksum=checksum,
                storage_key=storage_key,
                created_at=now,
            )
            self._session.add(row)
            event = DocumentIngested(
                user_id=user_id,
                occurred_at=now,
                source=KNOWLEDGE_SOURCE,
                correlation_id=correlation_id,
                payload=DocumentIngestedPayload(
                    document_id=document_id,
                    filename=filename,
                    content_type=content_type,
                    byte_size=len(data),
                    checksum=checksum,
                    storage_key=storage_key,
                ),
            )
            EventStore(self._session).append(event)
            self._session.commit()
        except Exception:
            # Best-effort cleanup so a failed ingest leaves no orphan blob.
            self._session.rollback()
            with contextlib.suppress(BlobNotFoundError):
                self._blobs.delete(storage_key)
            raise

        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return _to_document(row)

    def get_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        """Return the user's document metadata, or ``None`` if missing/not theirs."""
        row = self._require_document(user_id, document_id, raising=False)
        return _to_document(row) if row is not None else None

    def list_documents(self, user_id: uuid.UUID) -> list[Document]:
        """Return all of a user's documents, ordered by creation time."""
        rows = self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.user_id == user_id)
            .order_by(DocumentRow.created_at)
        )
        return [_to_document(row) for row in rows]

    def get_content(self, user_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Document, bytes]:
        """Return a document's metadata and its bytes from the store."""
        row = self._require_document(user_id, document_id)
        assert row is not None  # _require_document raises otherwise
        return _to_document(row), self._blobs.get(row.storage_key)

    def delete_user_documents(self, user_id: uuid.UUID) -> int:
        """Delete a user's document rows and blobs (for erasure, T2.5).

        Returns the number of documents removed.
        """
        rows = list(
            self._session.scalars(select(DocumentRow).where(DocumentRow.user_id == user_id))
        )
        for row in rows:
            with contextlib.suppress(BlobNotFoundError):
                self._blobs.delete(row.storage_key)
            self._session.delete(row)
        return len(rows)

    def _require_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID, *, raising: bool = True
    ) -> DocumentRow | None:
        row = self._session.scalars(
            select(DocumentRow).where(
                DocumentRow.document_id == document_id, DocumentRow.user_id == user_id
            )
        ).one_or_none()
        if row is None and raising:
            raise UnknownDocumentError(document_id)
        return row
