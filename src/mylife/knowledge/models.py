"""Knowledge models and events.

A ``documents`` registry (metadata only) plus the ``DocumentIngested`` event.
Document **bytes** live in the blob store; the event and row reference the blob by
``storage_key`` + ``checksum`` — never the bytes. See
``specs/domain/knowledge/document-ingest.md`` (T6.1).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

DOCUMENT_INGESTED: Final = "knowledge.document_ingested"
KNOWLEDGE_SOURCE = "knowledge"


class DocumentRow(Base):
    """A user-scoped document's metadata (bytes live in the blob store)."""

    __tablename__ = "documents"

    document_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    byte_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String)
    storage_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Document(BaseModel):
    """A document's metadata as read back."""

    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int
    checksum: str
    created_at: datetime


class DocumentIngestedPayload(BaseModel):
    """The ingest fact — a reference to the stored blob, not the bytes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int
    checksum: str
    storage_key: str


class DocumentIngested(LifeEvent[DocumentIngestedPayload]):
    """Emitted when a document is ingested (Knowledge context)."""

    event_type: Literal["knowledge.document_ingested"] = DOCUMENT_INGESTED
    schema_version: Literal[1] = 1
