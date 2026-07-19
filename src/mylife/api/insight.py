"""Insight endpoints — the AI evidence contract (T7.1).

Authenticated, user-scoped recording and reading of insights. Every insight must
cite non-empty, user-owned evidence (enforced by ``InsightService``). See
``specs/domain/assistant/insight-contract.md``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.assistant.insight import (
    EmptyEvidenceError,
    Insight,
    InsightDetail,
    InsightService,
    UnknownEvidenceError,
)
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User

router = APIRouter(tags=["insight"])

_GENERATOR = "manual-v1"


class InsightRequest(BaseModel):
    """Request to record an insight (must cite evidence and state its limits)."""

    claim: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[uuid.UUID] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: str = Field(min_length=1)
    next_safe_action: str | None = None


@router.post("/insights", response_model=Insight, status_code=201)
def create_insight(
    request: InsightRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Insight:
    """Record an insight for the authenticated user (evidence enforced)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return InsightService(session, bus).generate(
            current_user.user_id,
            request.claim,
            request.rationale,
            request.evidence,
            request.confidence,
            request.limitations,
            next_safe_action=request.next_safe_action,
            generator=_GENERATOR,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except EmptyEvidenceError as exc:
        raise HTTPException(status_code=422, detail="an insight must cite evidence") from exc
    except UnknownEvidenceError as exc:
        raise HTTPException(
            status_code=422, detail="evidence must be one of your own events"
        ) from exc


@router.get("/insights", response_model=list[Insight])
def list_insights(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Insight]:
    """List the authenticated user's insights, newest first."""
    return InsightService(session, bus).list_insights(current_user.user_id)


@router.get("/insights/{insight_id}", response_model=InsightDetail)
def get_insight(
    insight_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> InsightDetail:
    """Return an insight with its resolved evidence events."""
    service = InsightService(session, bus)
    insight = service.get(current_user.user_id, insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="insight not found")
    evidence_events = service.resolve_evidence(current_user.user_id, insight_id)
    return InsightDetail(**insight.model_dump(), evidence_events=evidence_events)
