"""Alerts & weekly insights (T7.3).

Governed, deterministic **rules** over the user's own data that, when they fire,
record an evidence-linked ``InsightGenerated`` (T7.1) — overspend, an at-risk
goal, a short-sleep streak. No LLM: the trigger and evidence stay governed; a
model may phrase later. See ``specs/domain/assistant/alerts.md``.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.assistant.insight import Insight, InsightService
from mylife.core.events import EventBus, InProcessEventBus
from mylife.finance.models import TRANSACTION_TYPES
from mylife.goals import GoalProgressService, GoalsService
from mylife.goals.models import GOAL_CREATED
from mylife.health.models import SLEEP_RECORDED
from mylife.timeline import TimelineEvent, TimelineQueryFilter, TimelineQueryService

_WINDOW = timedelta(days=7)
_MAX_EVENTS = 1000
_OVERSPEND_RATIO = 1.2
_SHORT_SLEEP_MINUTES = 360
_SHORT_SLEEP_NIGHTS = 2
_GENERATOR = "alerts-v1"


class RuleResult(BaseModel):
    """A fired alert — a claim with the events that triggered it."""

    model_config = ConfigDict(frozen=True)

    claim: str
    rationale: str
    evidence: list[uuid.UUID]
    confidence: float
    limitations: str
    next_safe_action: str


@runtime_checkable
class Rule(Protocol):
    """A governed alert rule over the user's data (read-only, user-scoped)."""

    name: str

    def evaluate(self, session: Session, user_id: uuid.UUID, now: datetime) -> list[RuleResult]:
        """Return any fired alerts for ``user_id`` as of ``now``."""
        ...


def _events(
    session: Session,
    user_id: uuid.UUID,
    event_types: tuple[str, ...],
    occurred_from: datetime,
    occurred_to: datetime,
) -> list[TimelineEvent]:
    return (
        TimelineQueryService(session)
        .query(
            TimelineQueryFilter(
                user_id=user_id,
                event_types=event_types,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                limit=_MAX_EVENTS,
            )
        )
        .items
    )


def _money(currency: str, minor: int) -> str:
    return f"{currency} {minor / 100:,.2f}"


class OverspendRule:
    """Fires when recent outflow outpaces the prior week."""

    name = "overspend"

    def evaluate(self, session: Session, user_id: uuid.UUID, now: datetime) -> list[RuleResult]:
        current = _events(session, user_id, TRANSACTION_TYPES, now - _WINDOW, now)
        prior = _events(session, user_id, TRANSACTION_TYPES, now - 2 * _WINDOW, now - _WINDOW)
        results: list[RuleResult] = []
        for currency in self._currencies(current):
            cur_total, cur_ids = self._outflow(current, currency)
            prior_total, _ = self._outflow(prior, currency)
            if cur_total <= 0:
                continue
            if prior_total == 0 or cur_total > prior_total * _OVERSPEND_RATIO:
                excess = cur_total - prior_total
                confidence = min(1.0, max(0.5, excess / cur_total))
                results.append(
                    RuleResult(
                        claim=(
                            f"Your {currency} spending in the last 7 days "
                            f"({_money(currency, cur_total)} out) is above the prior week "
                            f"({_money(currency, prior_total)})."
                        ),
                        rationale="Sum of outflow transactions in each 7-day window.",
                        evidence=cur_ids,
                        confidence=confidence,
                        limitations=(
                            "Based only on your recorded transactions in range; "
                            "not financial advice."
                        ),
                        next_safe_action="Review your recent transactions.",
                    )
                )
        return results

    @staticmethod
    def _currencies(events: list[TimelineEvent]) -> set[str]:
        return {str(e.payload.get("currency", "")) for e in events if _is_outflow(e)}

    @staticmethod
    def _outflow(events: list[TimelineEvent], currency: str) -> tuple[int, list[uuid.UUID]]:
        total = 0
        ids: list[uuid.UUID] = []
        for event in events:
            if _is_outflow(event) and str(event.payload.get("currency", "")) == currency:
                total += -int(event.payload["amount_minor"])  # type: ignore[call-overload]
                ids.append(event.event_id)
        return total, ids


def _is_outflow(event: TimelineEvent) -> bool:
    amount = event.payload.get("amount_minor")
    return isinstance(amount, int) and amount < 0


class AtRiskGoalRule:
    """Fires for each goal past its due date and not achieved."""

    name = "at-risk-goal"

    def evaluate(self, session: Session, user_id: uuid.UUID, now: datetime) -> list[RuleResult]:
        bus = InProcessEventBus()
        goals = GoalsService(session, bus).list_goals(user_id)
        progress_service = GoalProgressService(session)
        created = _goal_created_events(session, user_id)
        results: list[RuleResult] = []
        for goal in goals:
            if goal.due_at is None or goal.due_at >= now:
                continue
            progress = progress_service.progress(user_id, goal)
            if progress.achieved:
                continue
            event_id = created.get(goal.goal_id)
            if event_id is None:
                continue  # cannot cite evidence
            pct = round(progress.progress_ratio * 100)
            results.append(
                RuleResult(
                    claim=f"Goal '{goal.title}' is past its due date and only {pct}% reached.",
                    rationale="The goal's due date has passed and its target is not met.",
                    evidence=[event_id],
                    confidence=min(1.0, max(0.5, 1.0 - progress.progress_ratio)),
                    limitations="Progress is computed from your recorded data only.",
                    next_safe_action="Revisit the goal's target or due date.",
                )
            )
        return results


def _goal_created_events(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    events = _events(session, user_id, (GOAL_CREATED,), _epoch(), _far_future())
    return {uuid.UUID(str(e.payload["goal_id"])): e.event_id for e in events}


class ShortSleepRule:
    """Fires on a short-sleep streak in the last week."""

    name = "short-sleep"

    def evaluate(self, session: Session, user_id: uuid.UUID, now: datetime) -> list[RuleResult]:
        events = _events(session, user_id, (SLEEP_RECORDED,), now - _WINDOW, now)
        short = [
            e
            for e in events
            if isinstance(e.payload.get("duration_minutes"), int)
            and int(e.payload["duration_minutes"]) < _SHORT_SLEEP_MINUTES  # type: ignore[call-overload]
        ]
        if len(short) < _SHORT_SLEEP_NIGHTS:
            return []
        return [
            RuleResult(
                claim=f"You logged short sleep (< 6h) on {len(short)} night(s) in the last week.",
                rationale="Count of recorded sleep sessions under the short-sleep threshold.",
                evidence=[e.event_id for e in short],
                confidence=min(1.0, len(short) / 7),
                limitations="Based only on your recorded sleep sessions; not medical advice.",
                next_safe_action="Consider protecting time for sleep this week.",
            )
        ]


_DEFAULT_RULES: list[Rule] = [OverspendRule(), AtRiskGoalRule(), ShortSleepRule()]


def _epoch() -> datetime:
    from datetime import UTC

    return datetime(1970, 1, 1, tzinfo=UTC)


def _far_future() -> datetime:
    from datetime import UTC

    return datetime(2999, 1, 1, tzinfo=UTC)


class AlertsService:
    """Evaluates governed rules and records evidence-linked alert insights."""

    def __init__(
        self, session: Session, bus: EventBus, rules: Sequence[Rule] | None = None
    ) -> None:
        self._session = session
        self._bus = bus
        self._rules = list(rules) if rules is not None else _DEFAULT_RULES

    def run(self, user_id: uuid.UUID, *, now: datetime, correlation_id: str) -> list[Insight]:
        """Evaluate all rules; record + return an insight per fired alert."""
        insights: list[Insight] = []
        service = InsightService(self._session, self._bus)
        for rule in self._rules:
            for result in rule.evaluate(self._session, user_id, now):
                insights.append(
                    service.generate(
                        user_id,
                        result.claim,
                        result.rationale,
                        result.evidence,
                        result.confidence,
                        result.limitations,
                        next_safe_action=result.next_safe_action,
                        generator=_GENERATOR,
                        now=now,
                        correlation_id=correlation_id,
                    )
                )
        return insights
