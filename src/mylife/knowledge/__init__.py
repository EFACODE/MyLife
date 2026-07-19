"""Knowledge bounded context.

Personal documents ingested as searchable context: bytes in object storage, an
immutable ``DocumentIngested`` event and a ``documents`` registry referencing the
blob; extracted text as derived data (T6.2). Retrieval (T6.3) and knowledge-graph
consolidation (T6.4) build on this. See ``specs/domain/knowledge/`` (T6).
"""

from mylife.knowledge.blob_store import (
    BlobNotFoundError,
    BlobStore,
    FilesystemBlobStore,
    InMemoryBlobStore,
)
from mylife.knowledge.extraction import (
    DOCUMENT_TEXT_EXTRACTED,
    DocumentTextExtracted,
    DocumentTextRow,
    ExtractedText,
    ExtractionService,
    ExtractorRegistry,
    PlainTextExtractor,
    TextExtractor,
    UnsupportedContentTypeError,
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
    "DOCUMENT_TEXT_EXTRACTED",
    "BlobNotFoundError",
    "BlobStore",
    "Document",
    "DocumentIngested",
    "DocumentRow",
    "DocumentTextExtracted",
    "DocumentTextRow",
    "ExtractedText",
    "ExtractionService",
    "ExtractorRegistry",
    "FilesystemBlobStore",
    "InMemoryBlobStore",
    "KnowledgeService",
    "PlainTextExtractor",
    "TextExtractor",
    "UnknownDocumentError",
    "UnsupportedContentTypeError",
]
