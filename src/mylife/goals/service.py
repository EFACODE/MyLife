"""Goals service.

Registers goals and records milestones toward them. Creating a goal writes a
``goals`` registry row and emits ``GoalCreated``; recording a milestone appends
``GoalMilestoneReached`` (commit-before-publish). Milestones are read back from
the event store. All operations are user-scoped. See
``specs/domain/goals/goal-tracking.md`` (T5.1).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.core.events.envelope import ensure_utc
from mylife.core.events.store import _stored_utc
from mylife.goals.models import (
    GOALS_SOURCE,
    MILESTONE_REACHED,
    Goal,
    GoalCreated,
    GoalCreatedPayload,
    GoalMilestoneReached,
    GoalRow,
    Milestone,
    MilestonePayload,
)
from mylife.timeline.query import TimelineEvent, TimelineQueryFilter, TimelineQueryService

logger = logging.getLogger(__name__)

_UNBOUNDED = 1_000_000


class UnknownGoalError(Exception):
    """Raised when a goal is missing or not owned by the acting user."""

    def __init__(self, goal_id: uuid.UUID) -> None:
        super().__init__(f"goal {goal_id} not found")
        self.goal_id = goal_id


def _to_goal(row: GoalRow) -> Goal:
    return Goal(
        goal_id=row.goal_id,
        title=row.title,
        metric=row.metric,
        target_value=row.target_value,
        unit=row.unit,
        currency=row.currency,
        due_at=_stored_utc(row.due_at) if row.due_at is not None else None,
        created_at=_stored_utc(row.created_at),
    )


def _to_milestone(event: TimelineEvent) -> Milestone:
    payload = event.payload
    note = payload.get("note")
    return Milestone(
        event_id=event.event_id,
        goal_id=uuid.UUID(str(payload["goal_id"])),
        value=int(payload["value"]),  # type: ignore[call-overload]
        note=str(note) if note is not None else None,
        occurred_at=event.occurred_at,
    )


class GoalsService:
    """Manages goals and records/reads milestones for a user."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def create_goal(
        self,
        user_id: uuid.UUID,
        title: str,
        metric: str,
        target_value: int,
        unit: str,
        *,
        currency: str | None = None,
        due_at: datetime | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Goal:
        """Register a goal and emit ``GoalCreated``."""
        goal_id = uuid.uuid4()
        normalized_currency = currency.strip().upper() if currency else None
        normalized_due = ensure_utc(due_at) if due_at is not None else None
        row = GoalRow(
            goal_id=goal_id,
            user_id=user_id,
            title=title.strip(),
            metric=metric.strip(),
            target_value=target_value,
            unit=unit.strip(),
            currency=normalized_currency,
            due_at=normalized_due,
            created_at=now,
        )
        self._session.add(row)
        event = GoalCreated(
            user_id=user_id,
            occurred_at=now,
            source=GOALS_SOURCE,
            correlation_id=correlation_id,
            payload=GoalCreatedPayload(
                goal_id=goal_id,
                title=row.title,
                metric=row.metric,
                target_value=target_value,
                unit=row.unit,
                currency=normalized_currency,
                due_at=normalized_due,
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return _to_goal(row)

    def get_goal(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal | None:
        """Return the user's goal, or ``None`` if missing/not theirs."""
        row = self._require_goal(user_id, goal_id, raising=False)
        return _to_goal(row) if row is not None else None

    def list_goals(self, user_id: uuid.UUID) -> list[Goal]:
        """Return all of a user's goals, ordered by creation time."""
        rows = self._session.scalars(
            select(GoalRow).where(GoalRow.user_id == user_id).order_by(GoalRow.created_at)
        )
        return [_to_goal(row) for row in rows]

    def record_milestone(
        self,
        user_id: uuid.UUID,
        goal_id: uuid.UUID,
        value: int,
        *,
        note: str | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Milestone:
        """Record a ``GoalMilestoneReached`` for one of the user's goals."""
        self._require_goal(user_id, goal_id)
        event = GoalMilestoneReached(
            user_id=user_id,
            occurred_at=now,
            source=GOALS_SOURCE,
            correlation_id=correlation_id,
            payload=MilestonePayload(goal_id=goal_id, value=value, note=note),
        )
        stored = EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return Milestone(
            event_id=stored.event_id,
            goal_id=goal_id,
            value=value,
            note=note,
            occurred_at=stored.occurred_at,
        )

    def list_milestones(
        self, user_id: uuid.UUID, goal_id: uuid.UUID, *, limit: int = 50
    ) -> list[Milestone]:
        """Return a goal's milestones, newest first (user-scoped)."""
        page = TimelineQueryService(self._session).query(
            TimelineQueryFilter(user_id=user_id, event_types=(MILESTONE_REACHED,), limit=_UNBOUNDED)
        )
        milestones = [_to_milestone(item) for item in page.items]
        return [m for m in milestones if m.goal_id == goal_id][:limit]

    def _require_goal(
        self, user_id: uuid.UUID, goal_id: uuid.UUID, *, raising: bool = True
    ) -> GoalRow | None:
        row = self._session.scalars(
            select(GoalRow).where(GoalRow.goal_id == goal_id, GoalRow.user_id == user_id)
        ).one_or_none()
        if row is None and raising:
            raise UnknownGoalError(goal_id)
        return row

    def _publish(self, event: GoalCreated | GoalMilestoneReached) -> None:
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
