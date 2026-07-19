"""Daily briefing — rule-based and evidence-linked.

Aggregates a user's recent Life Events into a few factual observations where
**every line links to the source events** behind it (seeding the AI evidence
contract, T7). v1 (T3.6) counts events by category/source; v2 (T4.6) adds
**cross-domain** observations — sleep, training, calendar load and spend — and
rule-based **insights** that correlate them (e.g. short sleep on a busy day,
spending above the recent average). Still no AI. Delivering a briefing emits a
``BriefingDelivered`` event. See ``specs/domain/assistant/daily-briefing.md``
(T3.6) and ``specs/domain/assistant/cross-domain-briefing.md`` (T4.6).
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.finance.models import TRANSACTION_TYPES
from mylife.health.models import SLEEP_RECORDED, WORKOUT_COMPLETED
from mylife.timeline import TimelineEvent, TimelineQueryFilter, TimelineQueryService

logger = logging.getLogger(__name__)

ASSISTANT_SOURCE = "assistant"
BRIEFING_DELIVERED: Final = "assistant.briefing_delivered"
CALENDAR_SOURCE = "calendar"
_MAX_EVENTS = 500

# Correlation thresholds (documented constants; user-configurable later, T4.6 §9).
SHORT_SLEEP_MINUTES: Final = 360  # under 6h counts as short sleep
BUSY_DAY_EVENTS: Final = 3  # this many calendar events is a "busy day"


class BriefingDeliveredPayload(BaseModel):
    """Summary of a delivered briefing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_hours: int
    event_count: int
    line_count: int


class BriefingDelivered(LifeEvent[BriefingDeliveredPayload]):
    """Records that a briefing was delivered (Assistant context)."""

    event_type: Literal["assistant.briefing_delivered"] = BRIEFING_DELIVERED
    schema_version: Literal[1] = 1


class BriefingLine(BaseModel):
    """One observation with the events it is derived from."""

    model_config = ConfigDict(frozen=True)

    kind: str
    summary: str
    evidence: list[uuid.UUID]


class Briefing(BaseModel):
    """A rule-based briefing over a window of recent events."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    generated_at: datetime
    window_hours: int
    event_count: int
    lines: list[BriefingLine]


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _build_lines(events: list[TimelineEvent], window_hours: int) -> list[BriefingLine]:
    lines = [
        BriefingLine(
            kind="total",
            summary=f"{_count(len(events), 'event')} in the last {window_hours}h",
            evidence=[event.event_id for event in events],
        )
    ]

    by_category: dict[str, list[uuid.UUID]] = {}
    for event in events:
        category = event.payload.get("category")
        if isinstance(category, str) and category:
            by_category.setdefault(category, []).append(event.event_id)
    for category in sorted(by_category):
        evidence = by_category[category]
        lines.append(
            BriefingLine(
                kind="category",
                summary=_count(len(evidence), f"{category} event"),
                evidence=evidence,
            )
        )

    by_source: dict[str, list[uuid.UUID]] = {}
    for event in events:
        by_source.setdefault(event.source, []).append(event.event_id)
    for source in sorted(by_source):
        evidence = by_source[source]
        lines.append(
            BriefingLine(
                kind="source",
                summary=f"{_count(len(evidence), 'event')} from {source}",
                evidence=evidence,
            )
        )

    return lines


def _format_duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def _format_money(currency: str, minor: int) -> str:
    """Format minor units as major units with two decimals (no FX)."""
    return f"{currency} {minor / 100:,.2f}"


def _outflow_by_currency(events: list[TimelineEvent]) -> dict[str, int]:
    """Total money out (positive magnitude) per currency over ``events``."""
    totals: dict[str, int] = {}
    for event in events:
        if event.event_type not in TRANSACTION_TYPES:
            continue
        amount = event.payload.get("amount_minor")
        if isinstance(amount, int) and amount < 0:
            currency = str(event.payload.get("currency", ""))
            totals[currency] = totals.get(currency, 0) + (-amount)
    return totals


def _build_cross_domain_lines(
    events: list[TimelineEvent], previous: list[TimelineEvent], window_hours: int
) -> list[BriefingLine]:
    """Domain-summary and correlation lines (T4.6). ``events`` are newest-first."""
    lines: list[BriefingLine] = []

    sleeps = [e for e in events if e.event_type == SLEEP_RECORDED]
    workouts = [e for e in events if e.event_type == WORKOUT_COMPLETED]
    calendar = [e for e in events if e.source == CALENDAR_SOURCE]
    spend = [
        e
        for e in events
        if e.event_type in TRANSACTION_TYPES
        and isinstance(e.payload.get("amount_minor"), int)
        and int(e.payload["amount_minor"]) < 0  # type: ignore[call-overload]
    ]

    # Sleep — most recent session (events are newest-first).
    if sleeps:
        last = sleeps[0]
        minutes = last.payload.get("duration_minutes")
        if isinstance(minutes, int):
            lines.append(
                BriefingLine(
                    kind="sleep",
                    summary=f"Slept {_format_duration(minutes)} last night",
                    evidence=[last.event_id],
                )
            )

    # Training — count + total minutes, or a nudge when the day was active but had none.
    if workouts:
        total_minutes = sum(
            int(w.payload["duration_minutes"])  # type: ignore[call-overload]
            for w in workouts
            if isinstance(w.payload.get("duration_minutes"), int)
        )
        lines.append(
            BriefingLine(
                kind="training",
                summary=f"{_count(len(workouts), 'workout')}, {total_minutes} min total",
                evidence=[w.event_id for w in workouts],
            )
        )
    elif events:  # non-empty day, but no workout logged
        lines.append(
            BriefingLine(
                kind="insight",
                summary=f"No workout logged in the last {window_hours}h",
                evidence=[],
            )
        )

    # Calendar load.
    if calendar:
        lines.append(
            BriefingLine(
                kind="calendar",
                summary=f"{_count(len(calendar), 'meeting')} in the last {window_hours}h",
                evidence=[e.event_id for e in calendar],
            )
        )

    # Spend — total out per currency, plus a baseline comparison to the prior window.
    current_out = _outflow_by_currency(spend)
    previous_out = _outflow_by_currency(previous)
    for currency in sorted(current_out):
        out = current_out[currency]
        evidence = [e.event_id for e in spend if str(e.payload.get("currency", "")) == currency]
        lines.append(
            BriefingLine(
                kind="spend",
                summary=f"{_format_money(currency, out)} out in the last {window_hours}h",
                evidence=evidence,
            )
        )
        baseline = previous_out.get(currency, 0)
        if baseline == 0:
            trend = "above your recent average" if out > 0 else "in line with your recent average"
        elif out > baseline:
            trend = "above your recent average"
        elif out < baseline:
            trend = "below your recent average"
        else:
            trend = "in line with your recent average"
        lines.append(
            BriefingLine(
                kind="insight",
                summary=f"Spending ({currency}) is {trend}",
                evidence=evidence,
            )
        )

    # Combined insight — short sleep on a busy day.
    if sleeps and calendar:
        minutes = sleeps[0].payload.get("duration_minutes")
        if (
            isinstance(minutes, int)
            and minutes < SHORT_SLEEP_MINUTES
            and len(calendar) >= BUSY_DAY_EVENTS
        ):
            lines.append(
                BriefingLine(
                    kind="insight",
                    summary=(
                        f"Short sleep ({_format_duration(minutes)}) and a busy day "
                        f"({_count(len(calendar), 'meeting')}) — protect focus time"
                    ),
                    evidence=[sleeps[0].event_id, *[e.event_id for e in calendar]],
                )
            )

    return lines


class BriefingService:
    """Builds and delivers rule-based briefings."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def deliver(
        self,
        user_id: uuid.UUID,
        *,
        now: datetime,
        correlation_id: str,
        window_hours: int = 24,
    ) -> Briefing:
        """Build the briefing over the window, record delivery, and return it."""
        since = now - timedelta(hours=window_hours)
        query = TimelineQueryService(self._session)
        items = query.query(
            TimelineQueryFilter(
                user_id=user_id, occurred_from=since, occurred_to=now, limit=_MAX_EVENTS
            )
        ).items
        # Exclude system events (e.g. prior briefings) from the aggregation.
        recent = [item for item in items if not item.event_type.startswith("assistant.")]

        # The immediately preceding equal-length window, for the spend baseline (T4.6).
        previous = query.query(
            TimelineQueryFilter(
                user_id=user_id,
                occurred_from=since - timedelta(hours=window_hours),
                occurred_to=since,
                limit=_MAX_EVENTS,
            )
        ).items

        lines = _build_lines(recent, window_hours)
        lines.extend(_build_cross_domain_lines(recent, previous, window_hours))
        briefing = Briefing(
            user_id=user_id,
            generated_at=now,
            window_hours=window_hours,
            event_count=len(recent),
            lines=lines,
        )

        event = BriefingDelivered(
            user_id=user_id,
            occurred_at=now,
            source=ASSISTANT_SOURCE,
            correlation_id=correlation_id,
            payload=BriefingDeliveredPayload(
                window_hours=window_hours, event_count=len(recent), line_count=len(lines)
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return briefing
