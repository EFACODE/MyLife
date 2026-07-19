"""Goals bounded context.

Measurable targets and the milestones toward them, recorded as immutable Life
Events. Auto-progress from finance/health events (T5.2) and goals in the briefing
(T5.3) build on this. See ``specs/domain/goals/goal-tracking.md`` (T5.1).
"""

from mylife.goals.models import (
    GOAL_CREATED,
    MILESTONE_REACHED,
    Goal,
    GoalCreated,
    GoalMilestoneReached,
    GoalRow,
    Milestone,
)
from mylife.goals.progress import GoalProgress, GoalProgressService
from mylife.goals.service import GoalsService, UnknownGoalError

__all__ = [
    "GOAL_CREATED",
    "MILESTONE_REACHED",
    "Goal",
    "GoalCreated",
    "GoalMilestoneReached",
    "GoalProgress",
    "GoalProgressService",
    "GoalRow",
    "GoalsService",
    "Milestone",
    "UnknownGoalError",
]
