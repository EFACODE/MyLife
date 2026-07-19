"""Briefing endpoint.

``POST /briefing`` delivers a rule-based, evidence-linked briefing for a user and
records a ``BriefingDelivered`` event. See
``specs/domain/assistant/daily-briefing.md`` (T3.6).

``user_id`` is an explicit field until Identity/consent (T2) gate this endpoint.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.deps import get_event_bus
from mylife.assistant.briefing import Briefing, BriefingService
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session

router = APIRouter(tags=["assistant"])


class BriefingRequest(BaseModel):
    """Request to deliver a briefing."""

    user_id: uuid.UUID
    window_hours: int = Field(default=24, ge=1, le=720)


@router.post("/briefing", response_model=Briefing, status_code=201)
def deliver_briefing(
    request: BriefingRequest,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Briefing:
    """Deliver a briefing for the user over the requested window."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return BriefingService(session, bus).deliver(
        request.user_id,
        now=utcnow(),
        correlation_id=correlation_id,
        window_hours=request.window_hours,
    )
