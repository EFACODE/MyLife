"""Health models and events.

The first two health facts — ``SleepRecorded`` (a sleep session) and
``WorkoutCompleted`` (a workout) — plus the views they are read back as. Both are
immutable Life Events; sessions/workouts are read from the event store, not a
dedicated table. Measures are integers in fixed units (minutes/meters/kcal) —
never floats. See ``specs/domain/health/workout-tracking.md`` (T4.4).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from mylife.core.events import LifeEvent

SLEEP_RECORDED: Final = "health.sleep_recorded"
WORKOUT_COMPLETED: Final = "health.workout_completed"
HEALTH_SOURCE = "health"


class SleepPayload(BaseModel):
    """A recorded sleep session (duration in whole minutes)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    duration_minutes: int = Field(gt=0)
    quality: str | None = None


class WorkoutPayload(BaseModel):
    """A completed workout (duration/distance/energy in fixed integer units)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    activity: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    distance_meters: int | None = Field(default=None, ge=0)
    energy_kcal: int | None = Field(default=None, ge=0)


class SleepRecorded(LifeEvent[SleepPayload]):
    """Emitted when a user records a sleep session (Health context)."""

    event_type: Literal["health.sleep_recorded"] = SLEEP_RECORDED
    schema_version: Literal[1] = 1


class WorkoutCompleted(LifeEvent[WorkoutPayload]):
    """Emitted when a user records a completed workout (Health context)."""

    event_type: Literal["health.workout_completed"] = WORKOUT_COMPLETED
    schema_version: Literal[1] = 1


class SleepSession(BaseModel):
    """A sleep session as read back from the event store."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    occurred_at: datetime
    duration_minutes: int
    quality: str | None


class Workout(BaseModel):
    """A workout as read back from the event store."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    occurred_at: datetime
    activity: str
    duration_minutes: int
    distance_meters: int | None
    energy_kcal: int | None
