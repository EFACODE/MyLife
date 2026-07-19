"""Health service.

Records the first health facts and reads them back. Recording a sleep session or
a workout appends an immutable Life Event and publishes it (commit-before-publish,
like the rest of the platform); sessions/workouts are read from the event store
rather than a projection table. All operations are user-scoped. See
``specs/domain/health/workout-tracking.md`` (T4.4).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.health.models import (
    HEALTH_SOURCE,
    SLEEP_RECORDED,
    WORKOUT_COMPLETED,
    SleepPayload,
    SleepRecorded,
    SleepSession,
    Workout,
    WorkoutCompleted,
    WorkoutPayload,
)
from mylife.timeline.query import TimelineEvent, TimelineQueryFilter, TimelineQueryService

logger = logging.getLogger(__name__)


def _to_sleep(event: TimelineEvent) -> SleepSession:
    payload = event.payload
    quality = payload.get("quality")
    return SleepSession(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        duration_minutes=int(payload["duration_minutes"]),  # type: ignore[call-overload]
        quality=str(quality) if quality is not None else None,
    )


def _to_workout(event: TimelineEvent) -> Workout:
    payload = event.payload
    distance = payload.get("distance_meters")
    energy = payload.get("energy_kcal")
    return Workout(
        event_id=event.event_id,
        occurred_at=event.occurred_at,
        activity=str(payload["activity"]),
        duration_minutes=int(payload["duration_minutes"]),  # type: ignore[call-overload]
        distance_meters=int(distance) if distance is not None else None,  # type: ignore[call-overload]
        energy_kcal=int(energy) if energy is not None else None,  # type: ignore[call-overload]
    )


class HealthService:
    """Records and reads a user's sleep sessions and workouts."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def record_sleep(
        self,
        user_id: uuid.UUID,
        occurred_at: datetime,
        duration_minutes: int,
        *,
        quality: str | None = None,
        correlation_id: str,
    ) -> SleepSession:
        """Record a ``SleepRecorded`` for the user."""
        event = SleepRecorded(
            user_id=user_id,
            occurred_at=occurred_at,
            source=HEALTH_SOURCE,
            correlation_id=correlation_id,
            payload=SleepPayload(duration_minutes=duration_minutes, quality=quality),
        )
        stored = self._append_and_publish(event)
        return SleepSession(
            event_id=stored,
            occurred_at=event.occurred_at,
            duration_minutes=event.payload.duration_minutes,
            quality=event.payload.quality,
        )

    def record_workout(
        self,
        user_id: uuid.UUID,
        occurred_at: datetime,
        activity: str,
        duration_minutes: int,
        *,
        distance_meters: int | None = None,
        energy_kcal: int | None = None,
        correlation_id: str,
    ) -> Workout:
        """Record a ``WorkoutCompleted`` for the user."""
        event = WorkoutCompleted(
            user_id=user_id,
            occurred_at=occurred_at,
            source=HEALTH_SOURCE,
            correlation_id=correlation_id,
            payload=WorkoutPayload(
                activity=activity,
                duration_minutes=duration_minutes,
                distance_meters=distance_meters,
                energy_kcal=energy_kcal,
            ),
        )
        stored = self._append_and_publish(event)
        return Workout(
            event_id=stored,
            occurred_at=event.occurred_at,
            activity=event.payload.activity,
            duration_minutes=event.payload.duration_minutes,
            distance_meters=event.payload.distance_meters,
            energy_kcal=event.payload.energy_kcal,
        )

    def list_sleep(self, user_id: uuid.UUID, *, limit: int = 50) -> list[SleepSession]:
        """Return the user's sleep sessions, newest first."""
        page = TimelineQueryService(self._session).query(
            TimelineQueryFilter(user_id=user_id, event_types=(SLEEP_RECORDED,), limit=limit)
        )
        return [_to_sleep(item) for item in page.items]

    def list_workouts(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Workout]:
        """Return the user's workouts, newest first."""
        page = TimelineQueryService(self._session).query(
            TimelineQueryFilter(user_id=user_id, event_types=(WORKOUT_COMPLETED,), limit=limit)
        )
        return [_to_workout(item) for item in page.items]

    def _append_and_publish(self, event: SleepRecorded | WorkoutCompleted) -> uuid.UUID:
        stored = EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return stored.event_id
