"""Daily briefing v1 — rule-based and evidence-linked.

Aggregates a user's recent Life Events into a few factual observations where
**every line links to the source events** behind it (seeding the AI evidence
contract, T7). Delivering a briefing emits a ``BriefingDelivered`` event. No AI.
See ``specs/domain/assistant/daily-briefing.md`` (T3.6).
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.timeline import TimelineEvent, TimelineQueryFilter, TimelineQueryService

logger = logging.getLogger(__name__)

ASSISTANT_SOURCE = "assistant"
BRIEFING_DELIVERED: Final = "assistant.briefing_delivered"
_MAX_EVENTS = 500


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
        items = (
            TimelineQueryService(self._session)
            .query(
                TimelineQueryFilter(
                    user_id=user_id, occurred_from=since, occurred_to=now, limit=_MAX_EVENTS
                )
            )
            .items
        )
        # Exclude system events (e.g. prior briefings) from the aggregation.
        recent = [item for item in items if not item.event_type.startswith("assistant.")]
        lines = _build_lines(recent, window_hours)
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
