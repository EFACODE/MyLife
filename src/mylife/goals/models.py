"""Goals models and events.

A ``goals`` registry (managed aggregates with a title, metric and target) plus
the Goals facts — ``GoalCreated`` and ``GoalMilestoneReached``. Milestones are
immutable Life Events read back from the event store; targets/values are integers
(money in minor units, counts/distance in fixed units) — never floats. See
``specs/domain/goals/goal-tracking.md`` (T5.1).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

GOAL_CREATED: Final = "goals.goal_created"
MILESTONE_REACHED: Final = "goals.milestone_reached"
GOALS_SOURCE = "goals"


class GoalRow(Base):
    """A user-scoped goal (a measurable target)."""

    __tablename__ = "goals"

    goal_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String)
    metric: Mapped[str] = mapped_column(String)
    target_value: Mapped[int] = mapped_column()
    unit: Mapped[str] = mapped_column(String)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Goal(BaseModel):
    """A goal as read back from the goals store."""

    model_config = ConfigDict(frozen=True)

    goal_id: uuid.UUID
    title: str
    metric: str
    target_value: int
    unit: str
    currency: str | None
    due_at: datetime | None
    created_at: datetime


class Milestone(BaseModel):
    """A milestone as read back from the event store."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    goal_id: uuid.UUID
    value: int
    note: str | None
    occurred_at: datetime


class GoalCreatedPayload(BaseModel):
    """The goal-registration fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal_id: uuid.UUID
    title: str
    metric: str
    target_value: int
    unit: str
    currency: str | None = None
    due_at: datetime | None = None


class MilestonePayload(BaseModel):
    """A recorded milestone toward a goal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal_id: uuid.UUID
    value: int
    note: str | None = None


class GoalCreated(LifeEvent[GoalCreatedPayload]):
    """Emitted when a user creates a goal (Goals context)."""

    event_type: Literal["goals.goal_created"] = GOAL_CREATED
    schema_version: Literal[1] = 1


class GoalMilestoneReached(LifeEvent[MilestonePayload]):
    """Emitted when a user records a milestone toward a goal (Goals context)."""

    event_type: Literal["goals.milestone_reached"] = MILESTONE_REACHED
    schema_version: Literal[1] = 1


class CreateGoalCommand(BaseModel):
    """A request to create a goal."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    target_value: int
    unit: str = Field(min_length=1)
    currency: str | None = None
    due_at: datetime | None = None
