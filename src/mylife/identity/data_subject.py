"""Data-subject rights — export and erasure (LGPD/GDPR).

Export gathers all of a user's data; erasure hard-deletes it across every store.
Erasure is the sanctioned path that overrides append-only immutability. See
``specs/domain/identity/data-subject-rights.md`` (T2.5).
"""

import contextlib
import uuid
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from mylife.assistant.insight import InsightRow
from mylife.core.config import get_settings
from mylife.core.events import EventStore, InProcessEventBus, StoredEvent, StoredRawRecord
from mylife.core.events.raw_store import RawRecordRow
from mylife.core.events.raw_store import _to_stored as _raw_to_stored
from mylife.core.events.store import EventRow
from mylife.finance.models import Account, AccountRow
from mylife.goals.models import Goal, GoalRow
from mylife.goals.service import _to_goal
from mylife.identity.audit import AuditEntry, AuditLogRow, AuditService
from mylife.identity.consent import Consent, ConsentRow, ConsentService
from mylife.identity.models import CredentialRow, User, UserRow
from mylife.identity.service import _to_user
from mylife.knowledge.blob_store import BlobNotFoundError, BlobStore, FilesystemBlobStore
from mylife.knowledge.extraction import DocumentTextRow
from mylife.knowledge.models import Document, DocumentRow
from mylife.knowledge.retrieval import MemoryRow
from mylife.knowledge.service import _to_document
from mylife.timeline import EntityProjection
from mylife.timeline.entities import EntityRecord, EntityRow, RelationshipRecord, RelationshipRow

_UNBOUNDED = 1_000_000


class ExportBundle(BaseModel):
    """A complete export of a user's data."""

    model_config = ConfigDict(frozen=True)

    user: User | None
    consents: list[Consent]
    audit: list[AuditEntry]
    events: list[StoredEvent]
    raw_records: list[StoredRawRecord]
    entities: list[EntityRecord]
    relationships: list[RelationshipRecord]
    accounts: list[Account]
    goals: list[Goal]
    documents: list[Document]


class ErasureResult(BaseModel):
    """Per-table counts of rows removed by erasure."""

    model_config = ConfigDict(frozen=True)

    deleted: dict[str, int]


class DataSubjectService:
    """Exports and erases a user's data across every store."""

    def __init__(self, session: Session, blob_store: BlobStore | None = None) -> None:
        self._session = session
        self._blobs = blob_store or FilesystemBlobStore(get_settings().blob_store_path)

    def export(self, user_id: uuid.UUID) -> ExportBundle:
        """Gather all of the user's data into an export bundle."""
        user_row = self._session.get(UserRow, user_id)
        raw_rows = self._session.scalars(
            select(RawRecordRow).where(RawRecordRow.user_id == user_id)
        )
        projection = EntityProjection(self._session)
        account_rows = self._session.scalars(
            select(AccountRow).where(AccountRow.user_id == user_id).order_by(AccountRow.created_at)
        )
        goal_rows = self._session.scalars(
            select(GoalRow).where(GoalRow.user_id == user_id).order_by(GoalRow.created_at)
        )
        document_rows = self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.user_id == user_id)
            .order_by(DocumentRow.created_at)
        )
        return ExportBundle(
            user=_to_user(user_row) if user_row is not None else None,
            consents=ConsentService(self._session, InProcessEventBus()).list_consents(user_id),
            audit=AuditService(self._session).list_for_subject(user_id, limit=_UNBOUNDED),
            events=EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED),
            raw_records=[_raw_to_stored(row) for row in raw_rows],
            entities=projection.list_entities(user_id),
            relationships=projection.list_relationships(user_id),
            accounts=[
                Account(
                    account_id=row.account_id,
                    name=row.name,
                    currency=row.currency,
                    created_at=row.created_at,
                )
                for row in account_rows
            ],
            goals=[_to_goal(row) for row in goal_rows],
            documents=[_to_document(row) for row in document_rows],
        )

    def erase(self, user_id: uuid.UUID) -> ErasureResult:
        """Hard-delete all of the user's rows across every table."""
        # Documents keep their bytes in the blob store — delete those first, then
        # let the bulk row-delete below remove the metadata (and count it).
        for row in self._session.scalars(select(DocumentRow).where(DocumentRow.user_id == user_id)):
            with contextlib.suppress(BlobNotFoundError):
                self._blobs.delete(row.storage_key)
        statements = [
            ("audit_log", delete(AuditLogRow).where(AuditLogRow.subject_user_id == user_id)),
            ("insights", delete(InsightRow).where(InsightRow.user_id == user_id)),
            ("relationships", delete(RelationshipRow).where(RelationshipRow.user_id == user_id)),
            ("entities", delete(EntityRow).where(EntityRow.user_id == user_id)),
            ("memory_index", delete(MemoryRow).where(MemoryRow.user_id == user_id)),
            ("document_texts", delete(DocumentTextRow).where(DocumentTextRow.user_id == user_id)),
            ("documents", delete(DocumentRow).where(DocumentRow.user_id == user_id)),
            ("goals", delete(GoalRow).where(GoalRow.user_id == user_id)),
            ("accounts", delete(AccountRow).where(AccountRow.user_id == user_id)),
            ("consents", delete(ConsentRow).where(ConsentRow.user_id == user_id)),
            ("raw_records", delete(RawRecordRow).where(RawRecordRow.user_id == user_id)),
            ("events", delete(EventRow).where(EventRow.user_id == user_id)),
            ("credentials", delete(CredentialRow).where(CredentialRow.user_id == user_id)),
            ("users", delete(UserRow).where(UserRow.user_id == user_id)),
        ]
        deleted = {
            name: cast("CursorResult[Any]", self._session.execute(stmt)).rowcount
            for name, stmt in statements
        }
        self._session.commit()
        return ErasureResult(deleted=deleted)
