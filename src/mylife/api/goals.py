"""Goals endpoints.

Authenticated, user-scoped access to goals and their milestones. See
``specs/domain/goals/goal-tracking.md`` (T5.1).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.goals import Goal, GoalsService, Milestone, UnknownGoalError
from mylife.identity import User

router = APIRouter(tags=["goals"])


class CreateGoalRequest(BaseModel):
    """Request to create a goal."""

    title: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    target_value: int
    unit: str = Field(min_length=1)
    currency: str | None = None
    due_at: datetime | None = None


class MilestoneRequest(BaseModel):
    """Request to record a milestone toward a goal."""

    value: int
    note: str | None = None


@router.post("/goals", response_model=Goal, status_code=201)
def create_goal(
    request: CreateGoalRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Goal:
    """Create a goal for the authenticated user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return GoalsService(session, bus).create_goal(
        current_user.user_id,
        request.title,
        request.metric,
        request.target_value,
        request.unit,
        currency=request.currency,
        due_at=request.due_at,
        now=utcnow(),
        correlation_id=correlation_id,
    )


@router.get("/goals", response_model=list[Goal])
def list_goals(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Goal]:
    """List the authenticated user's goals."""
    return GoalsService(session, bus).list_goals(current_user.user_id)


@router.get("/goals/{goal_id}", response_model=Goal)
def get_goal(
    goal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Goal:
    """Return one of the authenticated user's goals."""
    goal = GoalsService(session, bus).get_goal(current_user.user_id, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return goal


@router.post("/goals/{goal_id}/milestones", response_model=Milestone, status_code=201)
def record_milestone(
    goal_id: uuid.UUID,
    request: MilestoneRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Milestone:
    """Record a milestone toward one of the authenticated user's goals."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return GoalsService(session, bus).record_milestone(
            current_user.user_id,
            goal_id,
            request.value,
            note=request.note,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownGoalError as exc:
        raise HTTPException(status_code=404, detail="goal not found") from exc


@router.get("/goals/{goal_id}/milestones", response_model=list[Milestone])
def list_milestones(
    goal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Milestone]:
    """List a goal's milestones, newest first."""
    return GoalsService(session, bus).list_milestones(current_user.user_id, goal_id)
