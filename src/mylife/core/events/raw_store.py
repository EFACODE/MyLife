"""The raw ingestion store.

Stores verbatim source payloads separately from normalized events, so the
external system stays authoritative and every inference is auditable back to its
source. Append-only and content-addressed for idempotency. See
``specs/domain/timeline/raw-store.md`` (T1.4).
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy import DateTime, Index, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events.envelope import ensure_utc, utcnow
from mylife.core.events.store import _stored_utc
from mylife.db.base import Base


class DuplicateRawRecordError(Exception):
    """Raised when storing a payload already present for a source."""

    def __init__(self, source: str, checksum: str) -> None:
        super().__init__(f"raw record for source {source!r} (checksum {checksum}) already exists")
        self.source = source
        self.checksum = checksum


def checksum_of(content: JsonValue) -> str:
    """Return the SHA-256 hex of the canonical JSON serialization of ``content``."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RawRecordRow(Base):
    """One row per raw source payload. Append-only — never updated or deleted."""

    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("source", "checksum", name="uq_raw_records_source_checksum"),
        Index("ix_raw_records_source_external", "source", "external_id"),
    )

    raw_record_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str] = mapped_column(String)
    content: Mapped[Any] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String)


class RawRecord(BaseModel):
    """Caller-supplied raw payload to store. The store assigns id/checksum/time."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    source: str = Field(min_length=1)
    external_id: str | None = None
    content_type: str = "application/json"
    content: JsonValue
    fetched_at: datetime
    correlation_id: str = Field(min_length=1)

    @field_validator("fetched_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class StoredRawRecord(BaseModel):
    """A raw record as read back from the store."""

    model_config = ConfigDict(frozen=True)

    raw_record_id: uuid.UUID
    user_id: uuid.UUID
    source: str
    external_id: str | None
    content_type: str
    content: JsonValue
    checksum: str
    fetched_at: datetime
    recorded_at: datetime
    correlation_id: str


def _to_stored(row: RawRecordRow) -> StoredRawRecord:
    return StoredRawRecord(
        raw_record_id=row.raw_record_id,
        user_id=row.user_id,
        source=row.source,
        external_id=row.external_id,
        content_type=row.content_type,
        content=row.content,
        checksum=row.checksum,
        fetched_at=_stored_utc(row.fetched_at),
        recorded_at=_stored_utc(row.recorded_at),
        correlation_id=row.correlation_id,
    )


class RawRecordStore:
    """Append-only repository over the ``raw_records`` table.

    Exposes only ``store`` and reads — no update or delete. Transaction control
    is left to the caller.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def store(self, raw: RawRecord) -> StoredRawRecord:
        """Persist ``raw`` and return it with its assigned id, checksum and time.

        Raises :class:`DuplicateRawRecordError` if the same ``(source, checksum)``
        already exists; the store is left unchanged in that case.
        """
        checksum = checksum_of(raw.content)
        row = RawRecordRow(
            raw_record_id=uuid.uuid4(),
            user_id=raw.user_id,
            source=raw.source,
            external_id=raw.external_id,
            content_type=raw.content_type,
            content=raw.content,
            checksum=checksum,
            fetched_at=raw.fetched_at,
            recorded_at=utcnow(),
            correlation_id=raw.correlation_id,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRawRecordError(raw.source, checksum) from exc
        return _to_stored(row)

    def get(self, raw_record_id: uuid.UUID) -> StoredRawRecord | None:
        """Return the raw record with ``raw_record_id``, or ``None``."""
        row = self._session.get(RawRecordRow, raw_record_id)
        return _to_stored(row) if row is not None else None

    def get_by_checksum(self, source: str, checksum: str) -> StoredRawRecord | None:
        """Return the raw record matching ``(source, checksum)``, or ``None``."""
        stmt = select(RawRecordRow).where(
            RawRecordRow.source == source, RawRecordRow.checksum == checksum
        )
        row = self._session.scalars(stmt).one_or_none()
        return _to_stored(row) if row is not None else None
