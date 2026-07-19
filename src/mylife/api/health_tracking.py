"""Health tracking endpoints.

Authenticated, user-scoped access to sleep sessions and workouts. Distinct from
``api/health.py`` (the service health check). See
``specs/domain/health/workout-tracking.md`` (T4.4).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import ensure_utc
from mylife.db.base import get_session
from mylife.health import HealthService, SleepSession, Workout
from mylife.identity import User

router = APIRouter(tags=["health-tracking"])


class SleepRequest(BaseModel):
    """Request to record a sleep session."""

    occurred_at: datetime
    duration_minutes: int = Field(gt=0)
    quality: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class WorkoutRequest(BaseModel):
    """Request to record a completed workout."""

    occurred_at: datetime
    activity: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    distance_meters: int | None = Field(default=None, ge=0)
    energy_kcal: int | None = Field(default=None, ge=0)

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


@router.post("/health/sleep", response_model=SleepSession, status_code=201)
def record_sleep(
    request: SleepRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> SleepSession:
    """Record a sleep session for the authenticated user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return HealthService(session, bus).record_sleep(
        current_user.user_id,
        request.occurred_at,
        request.duration_minutes,
        quality=request.quality,
        correlation_id=correlation_id,
    )


@router.post("/health/workouts", response_model=Workout, status_code=201)
def record_workout(
    request: WorkoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Workout:
    """Record a completed workout for the authenticated user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return HealthService(session, bus).record_workout(
        current_user.user_id,
        request.occurred_at,
        request.activity,
        request.duration_minutes,
        distance_meters=request.distance_meters,
        energy_kcal=request.energy_kcal,
        correlation_id=correlation_id,
    )


@router.get("/health/sleep", response_model=list[SleepSession])
def list_sleep(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[SleepSession]:
    """List the authenticated user's sleep sessions, newest first."""
    return HealthService(session, bus).list_sleep(current_user.user_id)


@router.get("/health/workouts", response_model=list[Workout])
def list_workouts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Workout]:
    """List the authenticated user's workouts, newest first."""
    return HealthService(session, bus).list_workouts(current_user.user_id)
