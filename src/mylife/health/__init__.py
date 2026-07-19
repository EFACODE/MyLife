"""Health bounded context.

Sleep and workouts recorded as immutable Life Events and read back as sessions
and workouts. Measures are integers in fixed units. The wearable connector
(T4.5) and the cross-domain briefing (T4.6) build on this. See
``specs/domain/health/workout-tracking.md`` (T4.4).
"""

from mylife.health.models import (
    SLEEP_RECORDED,
    WORKOUT_COMPLETED,
    SleepPayload,
    SleepRecorded,
    SleepSession,
    Workout,
    WorkoutCompleted,
    WorkoutPayload,
)
from mylife.health.service import HealthService

__all__ = [
    "SLEEP_RECORDED",
    "WORKOUT_COMPLETED",
    "HealthService",
    "SleepPayload",
    "SleepRecorded",
    "SleepSession",
    "Workout",
    "WorkoutCompleted",
    "WorkoutPayload",
]
