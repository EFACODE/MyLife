"""Knowledge bounded context.

Personal documents ingested as searchable context: bytes in object storage, an
immutable ``DocumentIngested`` event and a ``documents`` registry referencing the
blob. OCR (T6.2), retrieval (T6.3) and knowledge-graph consolidation (T6.4) build
on this. See ``specs/domain/knowledge/document-ingest.md`` (T6.1).
"""

from mylife.knowledge.blob_store import (
    BlobNotFoundError,
    BlobStore,
    FilesystemBlobStore,
    InMemoryBlobStore,
)
from mylife.knowledge.models import (
    DOCUMENT_INGESTED,
    Document,
    DocumentIngested,
    DocumentRow,
)
from mylife.knowledge.service import KnowledgeService, UnknownDocumentError

__all__ = [
    "DOCUMENT_INGESTED",
    "BlobNotFoundError",
    "BlobStore",
    "Document",
    "DocumentIngested",
    "DocumentRow",
    "FilesystemBlobStore",
    "InMemoryBlobStore",
    "KnowledgeService",
    "UnknownDocumentError",
]
