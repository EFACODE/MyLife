"""Read-only timeline queries.

Encapsulates filtering/paginating the ``events`` table into a typed page of
timeline events (with provenance). Read-only — no writes. See
``specs/domain/timeline/timeline-api.md`` (T3.1).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events.store import EventRow, StoredEvent, _to_stored


class TimelineQueryFilter(BaseModel):
    """Filters for a timeline query. Time bounds are inclusive UTC."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    event_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    limit: int = 50
    offset: int = 0


class TimelineEvent(BaseModel):
    """A timeline event as returned by the query API (provenance included)."""

    model_config = ConfigDict(frozen=True)

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


class TimelinePage(BaseModel):
    """A page of timeline events with offset/limit pagination metadata."""

    model_config = ConfigDict(frozen=True)

    items: list[TimelineEvent]
    limit: int
    offset: int
    has_more: bool


def _to_timeline_event(stored: StoredEvent) -> TimelineEvent:
    return TimelineEvent(
        event_id=stored.event_id,
        user_id=stored.user_id,
        event_type=stored.event_type,
        occurred_at=stored.occurred_at,
        recorded_at=stored.recorded_at,
        schema_version=stored.schema_version,
        source=stored.source,
        correlation_id=stored.correlation_id,
        raw_record_id=stored.raw_record_id,
        corrects_event_id=stored.corrects_event_id,
        payload=stored.payload,
    )


class TimelineQueryService:
    """Read-only queries over a user's timeline."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def query(self, query_filter: TimelineQueryFilter) -> TimelinePage:
        """Return a page of the user's events matching ``query_filter``."""
        stmt = select(EventRow).where(EventRow.user_id == query_filter.user_id)
        if query_filter.occurred_from is not None:
            stmt = stmt.where(EventRow.occurred_at >= query_filter.occurred_from)
        if query_filter.occurred_to is not None:
            stmt = stmt.where(EventRow.occurred_at <= query_filter.occurred_to)
        if query_filter.event_types:
            stmt = stmt.where(EventRow.event_type.in_(query_filter.event_types))
        if query_filter.sources:
            stmt = stmt.where(EventRow.source.in_(query_filter.sources))
        stmt = stmt.order_by(EventRow.occurred_at.desc(), EventRow.global_seq.desc())
        # Fetch one extra row to compute has_more without a count query.
        stmt = stmt.offset(query_filter.offset).limit(query_filter.limit + 1)

        rows = list(self._session.scalars(stmt))
        has_more = len(rows) > query_filter.limit
        items = [_to_timeline_event(_to_stored(row)) for row in rows[: query_filter.limit]]
        return TimelinePage(
            items=items,
            limit=query_filter.limit,
            offset=query_filter.offset,
            has_more=has_more,
        )
