"""Document text extraction (T6.2).

Turns a document's bytes into searchable **derived** text via a content-type
strategy registry. A ``PlainTextExtractor`` ships (dependency-free); OCR/PDF
adapters (optional engines) register into the same registry later. Extracted text
is stored in ``document_texts`` (derived, regenerable) with a
``DocumentTextExtracted`` event that keeps its evidence (the source document),
method and extractor version. See ``specs/domain/knowledge/text-extraction.md``.
"""

import logging
import uuid
from datetime import datetime
from typing import Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.db.base import Base
from mylife.knowledge.blob_store import BlobStore
from mylife.knowledge.models import KNOWLEDGE_SOURCE, DocumentRow
from mylife.knowledge.service import UnknownDocumentError

logger = logging.getLogger(__name__)

DOCUMENT_TEXT_EXTRACTED: Final = "knowledge.document_text_extracted"
EXTRACTOR_VERSION: Final = "1"


class UnsupportedContentTypeError(Exception):
    """Raised when no extractor matches a document's content type."""

    def __init__(self, content_type: str) -> None:
        super().__init__(f"no text extractor for content type {content_type!r}")
        self.content_type = content_type


@runtime_checkable
class TextExtractor(Protocol):
    """A content-type-specific text extraction strategy."""

    method: str

    def content_type_matches(self, content_type: str) -> bool:
        """Return whether this extractor handles ``content_type``."""
        ...

    def extract(self, data: bytes) -> str:
        """Extract text from ``data``."""
        ...


class PlainTextExtractor:
    """Extracts text from ``text/*`` documents by decoding UTF-8."""

    method = "plaintext-utf8"

    def content_type_matches(self, content_type: str) -> bool:
        return content_type.split(";", 1)[0].strip().startswith("text/")

    def extract(self, data: bytes) -> str:
        return data.decode("utf-8", errors="replace")


class ExtractorRegistry:
    """An ordered registry of text extractors, matched by content type."""

    def __init__(self, extractors: list[TextExtractor] | None = None) -> None:
        self._extractors: list[TextExtractor] = list(extractors or [])

    def register(self, extractor: TextExtractor) -> None:
        """Append ``extractor`` to the registry."""
        self._extractors.append(extractor)

    def for_content_type(self, content_type: str) -> TextExtractor:
        """Return the first extractor that handles ``content_type``."""
        for extractor in self._extractors:
            if extractor.content_type_matches(content_type):
                return extractor
        raise UnsupportedContentTypeError(content_type)


# Default registry — plain text ships; OCR/PDF adapters register here later.
registry = ExtractorRegistry([PlainTextExtractor()])


class DocumentTextRow(Base):
    """Derived extracted text for a document (regenerable — not append-only)."""

    __tablename__ = "document_texts"

    document_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    method: Mapped[str] = mapped_column(String)
    extractor_version: Mapped[str] = mapped_column(String)
    char_count: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractedText(BaseModel):
    """The outcome of an extraction (metadata; text fetched separately)."""

    model_config = ConfigDict(frozen=True)

    document_id: uuid.UUID
    method: str
    extractor_version: str
    char_count: int


class DocumentTextExtractedPayload(BaseModel):
    """The extraction fact — references the document, not the text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: uuid.UUID
    method: str
    extractor_version: str
    char_count: int


class DocumentTextExtracted(LifeEvent[DocumentTextExtractedPayload]):
    """Emitted when a document's text is extracted (Knowledge context)."""

    event_type: Literal["knowledge.document_text_extracted"] = DOCUMENT_TEXT_EXTRACTED
    schema_version: Literal[1] = 1


class ExtractionService:
    """Extracts and reads a document's derived text (user-scoped)."""

    def __init__(
        self,
        session: Session,
        bus: EventBus,
        blob_store: BlobStore,
        extractors: ExtractorRegistry | None = None,
    ) -> None:
        self._session = session
        self._bus = bus
        self._blobs = blob_store
        self._registry = extractors or registry

    def extract_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID, *, now: datetime, correlation_id: str
    ) -> ExtractedText:
        """Extract a document's text into the derived store and emit the event."""
        document = self._require_document(user_id, document_id)
        extractor = self._registry.for_content_type(document.content_type)
        text = extractor.extract(self._blobs.get(document.storage_key))
        char_count = len(text)

        row = self._session.get(DocumentTextRow, document_id)
        if row is None:
            self._session.add(
                DocumentTextRow(
                    document_id=document_id,
                    user_id=user_id,
                    method=extractor.method,
                    extractor_version=EXTRACTOR_VERSION,
                    char_count=char_count,
                    text=text,
                    extracted_at=now,
                )
            )
        else:
            row.method = extractor.method
            row.extractor_version = EXTRACTOR_VERSION
            row.char_count = char_count
            row.text = text
            row.extracted_at = now

        event = DocumentTextExtracted(
            user_id=user_id,
            occurred_at=now,
            source=KNOWLEDGE_SOURCE,
            correlation_id=correlation_id,
            raw_record_id=None,
            payload=DocumentTextExtractedPayload(
                document_id=document_id,
                method=extractor.method,
                extractor_version=EXTRACTOR_VERSION,
                char_count=char_count,
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return ExtractedText(
            document_id=document_id,
            method=extractor.method,
            extractor_version=EXTRACTOR_VERSION,
            char_count=char_count,
        )

    def get_text(self, user_id: uuid.UUID, document_id: uuid.UUID) -> str | None:
        """Return a document's extracted text, or ``None`` if absent/not theirs."""
        row = self._session.get(DocumentTextRow, document_id)
        if row is None or row.user_id != user_id:
            return None
        return row.text

    def _require_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> DocumentRow:
        row = self._session.get(DocumentRow, document_id)
        if row is None or row.user_id != user_id:
            raise UnknownDocumentError(document_id)
        return row
