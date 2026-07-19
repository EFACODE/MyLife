"""Append-only audit log.

A security trail of who did what. Most actions are domain events, so the log is
built primarily as a bus subscriber (one entry per published event), plus an
explicit ``record`` for non-event actions (e.g. login). Stores only ids, action
and correlation — never payloads or secrets. See
``specs/domain/identity/audit-log.md`` (T2.4).
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from mylife.core.events import InProcessEventBus, LifeEvent
from mylife.core.events.envelope import utcnow
from mylife.core.events.store import _stored_utc
from mylife.db.base import Base


class AuditLogRow(Base):
    """One append-only audit entry."""

    __tablename__ = "audit_log"

    audit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    resource: Mapped[str | None] = mapped_column(String, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEntry(BaseModel):
    """An audit entry as read back."""

    model_config = ConfigDict(frozen=True)

    audit_id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    subject_user_id: uuid.UUID | None
    resource: str | None
    correlation_id: str | None
    occurred_at: datetime
    recorded_at: datetime


def _to_entry(row: AuditLogRow) -> AuditEntry:
    return AuditEntry(
        audit_id=row.audit_id,
        action=row.action,
        actor_user_id=row.actor_user_id,
        subject_user_id=row.subject_user_id,
        resource=row.resource,
        correlation_id=row.correlation_id,
        occurred_at=_stored_utc(row.occurred_at),
        recorded_at=_stored_utc(row.recorded_at),
    )


class AuditService:
    """Appends and reads audit entries (append-only — no update/delete)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        action: str,
        *,
        now: datetime,
        actor_user_id: uuid.UUID | None = None,
        subject_user_id: uuid.UUID | None = None,
        resource: str | None = None,
        correlation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> AuditEntry:
        """Append one audit entry."""
        row = AuditLogRow(
            audit_id=uuid.uuid4(),
            action=action,
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            resource=resource,
            correlation_id=correlation_id,
            occurred_at=occurred_at or now,
            recorded_at=now,
        )
        self._session.add(row)
        self._session.commit()
        return _to_entry(row)

    def list_for_subject(self, user_id: uuid.UUID, *, limit: int = 100) -> list[AuditEntry]:
        """Return a user's audit entries, newest first."""
        stmt = (
            select(AuditLogRow)
            .where(AuditLogRow.subject_user_id == user_id)
            .order_by(AuditLogRow.recorded_at.desc())
            .limit(limit)
        )
        return [_to_entry(row) for row in self._session.scalars(stmt)]


class AuditSubscriber:
    """Records an audit entry for every published event."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def register(self, bus: InProcessEventBus) -> None:
        """Subscribe the audit handler to ``bus``."""
        bus.subscribe(self._handle)

    def _handle(self, event: LifeEvent[Any]) -> None:
        with self._session_factory() as session:
            AuditService(session).record(
                event.event_type,
                now=utcnow(),
                subject_user_id=event.user_id,
                resource=str(event.event_id),
                correlation_id=event.correlation_id,
                occurred_at=event.occurred_at,
            )
