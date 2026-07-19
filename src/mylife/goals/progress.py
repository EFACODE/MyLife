"""Goal progress from domain events (T5.2).

Derives a goal's current value from the domain events that measure it — net worth
(finance), workout minutes/distance (health), spend (finance) — selected by the
goal's ``metric``. Unknown metrics fall back to the latest milestone. Computed
**read-time** and **evidence-linked**. See ``specs/domain/goals/goal-progress.md``.
"""

import uuid
from typing import Final

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventStore, StoredEvent
from mylife.finance.models import POSITION_VALUED, TRANSACTION_TYPES
from mylife.finance.net_worth import NetWorthService
from mylife.goals.models import MILESTONE_REACHED, Goal, GoalRow
from mylife.goals.service import _to_goal
from mylife.health.models import WORKOUT_COMPLETED

_UNBOUNDED = 1_000_000

METRIC_NET_WORTH: Final = "net_worth"
METRIC_WORKOUT_MINUTES: Final = "workout_minutes"
METRIC_WORKOUT_DISTANCE: Final = "workout_distance"
METRIC_SPEND: Final = "spend"
KNOWN_METRICS: Final = frozenset(
    {METRIC_NET_WORTH, METRIC_WORKOUT_MINUTES, METRIC_WORKOUT_DISTANCE, METRIC_SPEND}
)


class GoalProgress(BaseModel):
    """A goal's current progress, derived read-time and evidence-linked."""

    model_config = ConfigDict(frozen=True)

    goal_id: uuid.UUID
    metric: str
    current_value: int
    target_value: int
    progress_ratio: float
    achieved: bool
    source: str
    evidence: list[uuid.UUID]


def _sum_workout(events: list[StoredEvent], field: str) -> tuple[int, list[uuid.UUID]]:
    total = 0
    evidence: list[uuid.UUID] = []
    for event in events:
        if event.event_type != WORKOUT_COMPLETED:
            continue
        value = event.payload.get(field)
        if isinstance(value, int):
            total += value
            evidence.append(event.event_id)
    return total, evidence


def _spend_outflow(events: list[StoredEvent]) -> tuple[int, list[uuid.UUID]]:
    total = 0
    evidence: list[uuid.UUID] = []
    for event in events:
        if event.event_type not in TRANSACTION_TYPES:
            continue
        amount = event.payload.get("amount_minor")
        if isinstance(amount, int) and amount < 0:
            total += -amount
            evidence.append(event.event_id)
    return total, evidence


def _net_worth_evidence(events: list[StoredEvent], currency: str | None) -> list[uuid.UUID]:
    evidence: list[uuid.UUID] = []
    finance_types = {*TRANSACTION_TYPES, POSITION_VALUED}
    for event in events:
        if event.event_type not in finance_types:
            continue
        if currency is None or str(event.payload.get("currency", "")) == currency:
            evidence.append(event.event_id)
    return evidence


def _latest_milestone(events: list[StoredEvent], goal_id: uuid.UUID) -> tuple[int, list[uuid.UUID]]:
    # Events are ascending; the last matching milestone is the most recent.
    latest: StoredEvent | None = None
    for event in events:
        if event.event_type == MILESTONE_REACHED and str(event.payload.get("goal_id", "")) == str(
            goal_id
        ):
            latest = event
    if latest is None:
        return 0, []
    value = latest.payload.get("value")
    return (int(value) if isinstance(value, int) else 0), [latest.event_id]


class GoalProgressService:
    """Computes goal progress from a user's domain events (read-time)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def progress(self, user_id: uuid.UUID, goal: Goal) -> GoalProgress:
        """Compute progress for ``goal`` from the user's events."""
        events = EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
        source = "metric" if goal.metric in KNOWN_METRICS else "milestone"

        if goal.metric == METRIC_NET_WORTH:
            worth = NetWorthService(self._session).net_worth(user_id)
            if goal.currency is None:
                current = sum(total.total_minor for total in worth.currencies)
            else:
                current = next(
                    (t.total_minor for t in worth.currencies if t.currency == goal.currency), 0
                )
            evidence = _net_worth_evidence(events, goal.currency)
        elif goal.metric == METRIC_WORKOUT_MINUTES:
            current, evidence = _sum_workout(events, "duration_minutes")
        elif goal.metric == METRIC_WORKOUT_DISTANCE:
            current, evidence = _sum_workout(events, "distance_meters")
        elif goal.metric == METRIC_SPEND:
            current, evidence = _spend_outflow(events)
        else:
            current, evidence = _latest_milestone(events, goal.goal_id)

        ratio = round(current / goal.target_value, 4) if goal.target_value else 0.0
        return GoalProgress(
            goal_id=goal.goal_id,
            metric=goal.metric,
            current_value=current,
            target_value=goal.target_value,
            progress_ratio=ratio,
            achieved=current >= goal.target_value,
            source=source,
            evidence=evidence,
        )

    def progress_all(self, user_id: uuid.UUID) -> list[GoalProgress]:
        """Compute progress for every one of the user's goals (by creation order)."""
        rows = self._session.scalars(
            select(GoalRow).where(GoalRow.user_id == user_id).order_by(GoalRow.created_at)
        )
        return [self.progress(user_id, _to_goal(row)) for row in rows]
