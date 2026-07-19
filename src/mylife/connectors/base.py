"""Connector framework — the reusable ingestion spine.

A connector pulls payloads from an external source; the :class:`ConnectorRunner`
stores them as raw records (T1.4), normalizes new ones into Life Events (T1.2)
linked back to their raw record (provenance), and publishes them (T1.3).
Ingestion is idempotent via the raw store's content addressing. See
``specs/domain/timeline/connector-framework.md`` (T3.4).
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.core.events.envelope import ensure_utc
from mylife.core.events.raw_store import (
    DuplicateRawRecordError,
    RawRecord,
    RawRecordStore,
    StoredRawRecord,
)

logger = logging.getLogger(__name__)


class FetchContext(BaseModel):
    """The context a sync runs in."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    correlation_id: str = Field(min_length=1)


class RawPayload(BaseModel):
    """A single payload fetched from a source, before it is stored."""

    model_config = ConfigDict(frozen=True)

    content: JsonValue
    fetched_at: datetime
    external_id: str | None = None
    content_type: str = "application/json"

    @field_validator("fetched_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class Connector(Protocol):
    """The contract every connector implements."""

    source: str

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        """Pull payloads from the external source."""
        ...

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        """Map a stored raw record to Life Events (each carrying its provenance)."""
        ...


class ProvenanceMismatchError(Exception):
    """A normalized event does not reference the raw record it came from."""

    def __init__(self, expected: uuid.UUID, actual: uuid.UUID | None) -> None:
        super().__init__(
            f"normalized event provenance {actual} does not match raw record {expected}"
        )
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class SyncResult:
    """The outcome of a connector sync."""

    source: str
    raw_ingested: int
    events_created: int
    skipped_duplicates: int


class ConnectorRunner:
    """Runs a connector: pull → raw store → normalize → append → publish."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def sync(self, connector: Connector, context: FetchContext) -> SyncResult:
        """Ingest from ``connector`` idempotently and return the counts."""
        raw_store = RawRecordStore(self._session)
        event_store = EventStore(self._session)
        raw_ingested = 0
        events_created = 0
        skipped = 0
        to_publish: list[LifeEvent[Any]] = []

        try:
            for payload in connector.fetch(context):
                raw = RawRecord(
                    user_id=context.user_id,
                    source=connector.source,
                    external_id=payload.external_id,
                    content_type=payload.content_type,
                    content=payload.content,
                    fetched_at=payload.fetched_at,
                    correlation_id=context.correlation_id,
                )
                try:
                    stored_raw = raw_store.store(raw)
                except DuplicateRawRecordError:
                    skipped += 1
                    continue
                raw_ingested += 1
                for event in connector.normalize(stored_raw):
                    if event.raw_record_id != stored_raw.raw_record_id:
                        raise ProvenanceMismatchError(stored_raw.raw_record_id, event.raw_record_id)
                    event_store.append(event)
                    events_created += 1
                    to_publish.append(event)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        for event in to_publish:
            try:
                self._bus.publish(event)
            except EventDispatchError:
                logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return SyncResult(
            source=connector.source,
            raw_ingested=raw_ingested,
            events_created=events_created,
            skipped_duplicates=skipped,
        )
