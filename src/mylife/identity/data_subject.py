"""Data-subject rights — export and erasure (LGPD/GDPR).

Export gathers all of a user's data; erasure hard-deletes it across every store.
Erasure is the sanctioned path that overrides append-only immutability. See
``specs/domain/identity/data-subject-rights.md`` (T2.5).
"""

import uuid
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from mylife.core.events import EventStore, InProcessEventBus, StoredEvent, StoredRawRecord
from mylife.core.events.raw_store import RawRecordRow
from mylife.core.events.raw_store import _to_stored as _raw_to_stored
from mylife.core.events.store import EventRow
from mylife.identity.audit import AuditEntry, AuditLogRow, AuditService
from mylife.identity.consent import Consent, ConsentRow, ConsentService
from mylife.identity.models import CredentialRow, User, UserRow
from mylife.identity.service import _to_user
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


class ErasureResult(BaseModel):
    """Per-table counts of rows removed by erasure."""

    model_config = ConfigDict(frozen=True)

    deleted: dict[str, int]


class DataSubjectService:
    """Exports and erases a user's data across every store."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def export(self, user_id: uuid.UUID) -> ExportBundle:
        """Gather all of the user's data into an export bundle."""
        user_row = self._session.get(UserRow, user_id)
        raw_rows = self._session.scalars(
            select(RawRecordRow).where(RawRecordRow.user_id == user_id)
        )
        projection = EntityProjection(self._session)
        return ExportBundle(
            user=_to_user(user_row) if user_row is not None else None,
            consents=ConsentService(self._session, InProcessEventBus()).list_consents(user_id),
            audit=AuditService(self._session).list_for_subject(user_id, limit=_UNBOUNDED),
            events=EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED),
            raw_records=[_raw_to_stored(row) for row in raw_rows],
            entities=projection.list_entities(user_id),
            relationships=projection.list_relationships(user_id),
        )

    def erase(self, user_id: uuid.UUID) -> ErasureResult:
        """Hard-delete all of the user's rows across every table."""
        statements = [
            ("audit_log", delete(AuditLogRow).where(AuditLogRow.subject_user_id == user_id)),
            ("relationships", delete(RelationshipRow).where(RelationshipRow.user_id == user_id)),
            ("entities", delete(EntityRow).where(EntityRow.user_id == user_id)),
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
