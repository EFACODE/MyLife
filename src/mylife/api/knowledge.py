"""Knowledge endpoints.

Authenticated, user-scoped document upload, listing and download. Document bytes
live in the blob store; metadata in the ``documents`` registry. See
``specs/domain/knowledge/document-ingest.md`` (T6.1).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_blob_store, get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User
from mylife.knowledge import (
    BlobStore,
    Document,
    ExtractedText,
    ExtractionService,
    KnowledgeService,
    UnknownDocumentError,
    UnsupportedContentTypeError,
)

router = APIRouter(tags=["knowledge"])


class DocumentText(BaseModel):
    """A document's extracted text."""

    document_id: uuid.UUID
    text: str


_DEFAULT_CONTENT_TYPE = "application/octet-stream"


@router.post("/documents", response_model=Document, status_code=201)
async def upload_document(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
    file: Annotated[UploadFile, File()],
) -> Document:
    """Ingest an uploaded document for the authenticated user."""
    data = await file.read()
    correlation_id = get_correlation_id() or new_correlation_id()
    return KnowledgeService(session, bus, blob_store).ingest_document(
        current_user.user_id,
        file.filename or "document",
        file.content_type or _DEFAULT_CONTENT_TYPE,
        data,
        now=utcnow(),
        correlation_id=correlation_id,
    )


@router.get("/documents", response_model=list[Document])
def list_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> list[Document]:
    """List the authenticated user's documents."""
    return KnowledgeService(session, bus, blob_store).list_documents(current_user.user_id)


@router.get("/documents/{document_id}", response_model=Document)
def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> Document:
    """Return one of the authenticated user's documents' metadata."""
    document = KnowledgeService(session, bus, blob_store).get_document(
        current_user.user_id, document_id
    )
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@router.get("/documents/{document_id}/content")
def get_document_content(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> Response:
    """Stream a document's stored bytes with its original content type."""
    service = KnowledgeService(session, bus, blob_store)
    if service.get_document(current_user.user_id, document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    document, data = service.get_content(current_user.user_id, document_id)
    return Response(content=data, media_type=document.content_type)


@router.post("/documents/{document_id}/extract", response_model=ExtractedText)
def extract_document(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> ExtractedText:
    """Extract text from one of the authenticated user's documents."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return ExtractionService(session, bus, blob_store).extract_document(
            current_user.user_id, document_id, now=utcnow(), correlation_id=correlation_id
        )
    except UnknownDocumentError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except UnsupportedContentTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/documents/{document_id}/text", response_model=DocumentText)
def get_document_text(
    document_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> DocumentText:
    """Return a document's extracted text (404 if not extracted / not the caller's)."""
    text = ExtractionService(session, bus, blob_store).get_text(current_user.user_id, document_id)
    if text is None:
        raise HTTPException(status_code=404, detail="document text not found")
    return DocumentText(document_id=document_id, text=text)
