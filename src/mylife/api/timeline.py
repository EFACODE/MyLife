"""Timeline query endpoint.

``GET /timeline/events`` lists a user's Life Events filtered by time, type and
source, paginated, with provenance included. See
``specs/domain/timeline/timeline-api.md`` (T3.1).

``user_id`` is an explicit query parameter until Identity/consent (T2) gate this
endpoint; the query is always scoped to it, so it cannot leak across users.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.db.base import get_session
from mylife.timeline.capture import RecordLifeEventCommand, TimelineWriter
from mylife.timeline.query import (
    TimelineEvent,
    TimelinePage,
    TimelineQueryFilter,
    TimelineQueryService,
    _to_timeline_event,
)

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _require_utc(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail=f"{field} must be timezone-aware (UTC)")
    return value.astimezone(UTC)


@router.get("/events", response_model=TimelinePage)
def query_timeline(
    session: Annotated[Session, Depends(get_session)],
    user_id: Annotated[uuid.UUID, Query()],
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    event_type: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TimelinePage:
    """Return a page of the user's timeline events."""
    query_filter = TimelineQueryFilter(
        user_id=user_id,
        occurred_from=_require_utc(occurred_from, "occurred_from"),
        occurred_to=_require_utc(occurred_to, "occurred_to"),
        event_types=tuple(event_type or ()),
        sources=tuple(source or ()),
        limit=limit,
        offset=offset,
    )
    return TimelineQueryService(session).query(query_filter)


@router.post("/events", response_model=TimelineEvent, status_code=201)
def record_event(
    command: RecordLifeEventCommand,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> TimelineEvent:
    """Record a Life Event by hand; append it and publish it."""
    correlation_id = get_correlation_id() or new_correlation_id()
    stored = TimelineWriter(session, bus).record(command, correlation_id=correlation_id)
    return _to_timeline_event(stored)
