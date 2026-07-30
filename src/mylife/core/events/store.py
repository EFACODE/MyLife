"""The append-only event store.

Persists Life Events and reads them back in stable order. The store has exactly
two capabilities — **append** and **read** — and no update or delete surface, so
history can only grow. See ``specs/domain/timeline/event-store.md`` (T1.2).
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events.envelope import LifeEvent
from mylife.core.metrics import EVENTS_APPENDED
from mylife.db.base import Base

ModelT = TypeVar("ModelT", bound=BaseModel)


class DuplicateEventError(Exception):
    """Raised when appending an event whose ``event_id`` already exists."""

    def __init__(self, event_id: uuid.UUID) -> None:
        super().__init__(f"event {event_id} already exists")
        self.event_id = event_id


def _stored_utc(value: datetime) -> datetime:
    """Coerce a datetime read from storage to timezone-aware UTC.

    Events are always stored as UTC; some backends (e.g. SQLite) drop the
    timezone, so a naive value read back is interpreted as UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class EventRow(Base):
    """One row per Life Event. Append-only — never updated or deleted."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_user_seq", "user_id", "global_seq"),
        Index("ix_events_corrects_event_id", "corrects_event_id"),
    )

    # Database-assigned monotonic order (INTEGER on SQLite so it autoincrements
    # as a rowid alias; BIGINT elsewhere).
    global_seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column()
    event_type: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[int] = mapped_column()
    source: Mapped[str] = mapped_column(String)
    correlation_id: Mapped[str] = mapped_column(String)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    corrects_event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class StoredEvent(BaseModel):
    """An event as read back from the store (envelope + assigned order)."""

    model_config = ConfigDict(frozen=True)

    global_seq: int
    event_id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    schema_version: int
    source: str
    correlation_id: str
    raw_record_id: uuid.UUID | None
    corrects_event_id: uuid.UUID | None
    payload: Mapping[str, object]

    def rehydrate(self, model_type: type[ModelT]) -> ModelT:
        """Reconstruct a typed event model from this stored event."""
        return model_type.model_validate(
            {
                "event_id": self.event_id,
                "user_id": self.user_id,
                "event_type": self.event_type,
                "occurred_at": self.occurred_at,
                "recorded_at": self.recorded_at,
                "schema_version": self.schema_version,
                "source": self.source,
                "correlation_id": self.correlation_id,
                "raw_record_id": self.raw_record_id,
                "corrects_event_id": self.corrects_event_id,
                "payload": self.payload,
            }
        )


def _to_stored(row: EventRow) -> StoredEvent:
    return StoredEvent(
        global_seq=row.global_seq,
        event_id=row.event_id,
        user_id=row.user_id,
        event_type=row.event_type,
        occurred_at=_stored_utc(row.occurred_at),
        recorded_at=_stored_utc(row.recorded_at),
        schema_version=row.schema_version,
        source=row.source,
        correlation_id=row.correlation_id,
        raw_record_id=row.raw_record_id,
        corrects_event_id=row.corrects_event_id,
        payload=row.payload,
    )


class EventStore:
    """Append-only repository over the ``events`` table.

    Exposes only ``append`` and read operations — there is deliberately no
    update or delete. Transaction control is left to the caller.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: LifeEvent[Any]) -> StoredEvent:
        """Persist ``event`` and return it with its assigned ``global_seq``.

        Raises :class:`DuplicateEventError` if the ``event_id`` already exists;
        the store is left unchanged in that case.
        """
        row = EventRow(
            event_id=event.event_id,
            user_id=event.user_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            recorded_at=event.recorded_at,
            schema_version=event.schema_version,
            source=event.source,
            correlation_id=event.correlation_id,
            raw_record_id=event.raw_record_id,
            corrects_event_id=event.corrects_event_id,
            payload=event.payload.model_dump(mode="json"),
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateEventError(event.event_id) from exc
        EVENTS_APPENDED.labels(event_type=event.event_type).inc()
        return _to_stored(row)

    def read_stream(
        self, user_id: uuid.UUID, *, limit: int = 100, after_seq: int | None = None
    ) -> list[StoredEvent]:
        """Return one user's events in ascending ``global_seq`` order."""
        stmt = select(EventRow).where(EventRow.user_id == user_id)
        if after_seq is not None:
            stmt = stmt.where(EventRow.global_seq > after_seq)
        stmt = stmt.order_by(EventRow.global_seq).limit(limit)
        return [_to_stored(row) for row in self._session.scalars(stmt)]

    def read_all(self, *, limit: int = 100, after_seq: int | None = None) -> list[StoredEvent]:
        """Return events across all users in ascending ``global_seq`` order."""
        stmt = select(EventRow)
        if after_seq is not None:
            stmt = stmt.where(EventRow.global_seq > after_seq)
        stmt = stmt.order_by(EventRow.global_seq).limit(limit)
        return [_to_stored(row) for row in self._session.scalars(stmt)]

    def read_corrections(
        self, event_id: uuid.UUID, *, limit: int = 100, after_seq: int | None = None
    ) -> list[StoredEvent]:
        """Return the events that correct ``event_id``, in ``global_seq`` order."""
        stmt = select(EventRow).where(EventRow.corrects_event_id == event_id)
        if after_seq is not None:
            stmt = stmt.where(EventRow.global_seq > after_seq)
        stmt = stmt.order_by(EventRow.global_seq).limit(limit)
        return [_to_stored(row) for row in self._session.scalars(stmt)]
