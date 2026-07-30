"""The AI evidence contract — ``InsightGenerated`` (T7.1).

Makes the platform's non-negotiable concrete: an insight is a **structured claim
that must carry its evidence** (the Life Events it derives from), its
**confidence**, its **limitations** and a **safe next action**. ``InsightService``
refuses to record an insight without non-empty, **user-owned** evidence, so the
guarantee holds for every caller (the API now, grounded generation later). Rule-
based — no LLM here. See ``specs/domain/assistant/insight-contract.md``.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Float, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent, StoredEvent
from mylife.core.events.store import EventRow, _stored_utc, _to_stored
from mylife.db.base import Base

logger = logging.getLogger(__name__)

ASSISTANT_SOURCE = "assistant"
INSIGHT_GENERATED: Final = "assistant.insight_generated"
_UNBOUNDED = 1_000_000


class EmptyEvidenceError(Exception):
    """Raised when generating an insight with no evidence — the contract forbids it."""


class UnknownEvidenceError(Exception):
    """Raised when an evidence id is not one of the user's events."""

    def __init__(self, event_id: uuid.UUID) -> None:
        super().__init__(f"evidence {event_id} is not one of the user's events")
        self.event_id = event_id


class UnknownInsightError(Exception):
    """Raised when an insight is missing or not owned by the acting user."""

    def __init__(self, insight_id: uuid.UUID) -> None:
        super().__init__(f"insight {insight_id} not found")
        self.insight_id = insight_id


class InsightRow(Base):
    """A recorded insight (derived; evidence stored by reference)."""

    __tablename__ = "insights"

    insight_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    claim: Mapped[str] = mapped_column(String)
    rationale: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    limitations: Mapped[str] = mapped_column(String)
    next_safe_action: Mapped[str | None] = mapped_column(String, nullable=True)
    generator: Mapped[str] = mapped_column(String)
    evidence: Mapped[list[str]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Insight(BaseModel):
    """An insight as read back — a claim with its evidence, confidence and limits."""

    model_config = ConfigDict(frozen=True)

    insight_id: uuid.UUID
    claim: str
    rationale: str
    confidence: float
    limitations: str
    next_safe_action: str | None
    generator: str
    evidence: list[uuid.UUID]
    generated_at: datetime


class InsightDetail(Insight):
    """An insight plus its resolved evidence events."""

    evidence_events: list[StoredEvent]


class InsightGeneratedPayload(BaseModel):
    """The insight fact — claim metadata + evidence references (not copied data)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight_id: uuid.UUID
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    generator: str
    evidence: list[uuid.UUID]


class InsightGenerated(LifeEvent[InsightGeneratedPayload]):
    """Emitted when an insight is generated (Assistant context)."""

    event_type: Literal["assistant.insight_generated"] = INSIGHT_GENERATED
    schema_version: Literal[1] = 1


def _to_insight(row: InsightRow) -> Insight:
    return Insight(
        insight_id=row.insight_id,
        claim=row.claim,
        rationale=row.rationale,
        confidence=row.confidence,
        limitations=row.limitations,
        next_safe_action=row.next_safe_action,
        generator=row.generator,
        evidence=[uuid.UUID(value) for value in row.evidence],
        generated_at=_stored_utc(row.generated_at),
    )


class InsightService:
    """Records and reads insights, enforcing the evidence contract."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def generate(
        self,
        user_id: uuid.UUID,
        claim: str,
        rationale: str,
        evidence: Sequence[uuid.UUID],
        confidence: float,
        limitations: str,
        *,
        next_safe_action: str | None = None,
        generator: str,
        now: datetime,
        correlation_id: str,
    ) -> Insight:
        """Record an ``InsightGenerated`` — rejecting unsupported claims.

        The evidence must be non-empty and every id must be one of the user's own
        events, so the claim is always traceable to the user's data.
        """
        if not evidence:
            raise EmptyEvidenceError("an insight must cite at least one evidence event")
        owned = {
            stored.event_id
            for stored in EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
        }
        for event_id in evidence:
            if event_id not in owned:
                raise UnknownEvidenceError(event_id)

        insight_id = uuid.uuid4()
        payload = InsightGeneratedPayload(
            insight_id=insight_id,
            claim=claim,
            confidence=confidence,
            generator=generator,
            evidence=list(evidence),
        )
        row = InsightRow(
            insight_id=insight_id,
            user_id=user_id,
            claim=claim,
            rationale=rationale,
            confidence=confidence,
            limitations=limitations,
            next_safe_action=next_safe_action,
            generator=generator,
            evidence=[str(event_id) for event_id in evidence],
            generated_at=now,
        )
        self._session.add(row)
        event = InsightGenerated(
            user_id=user_id,
            occurred_at=now,
            source=ASSISTANT_SOURCE,
            correlation_id=correlation_id,
            payload=payload,
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return _to_insight(row)

    def get(self, user_id: uuid.UUID, insight_id: uuid.UUID) -> Insight | None:
        """Return the user's insight, or ``None`` if missing/not theirs."""
        row = self._require_insight(user_id, insight_id, raising=False)
        return _to_insight(row) if row is not None else None

    def list_insights(self, user_id: uuid.UUID) -> list[Insight]:
        """Return the user's insights, newest first."""
        rows = self._session.scalars(
            select(InsightRow)
            .where(InsightRow.user_id == user_id)
            .order_by(InsightRow.generated_at.desc())
        )
        return [_to_insight(row) for row in rows]

    def resolve_evidence(self, user_id: uuid.UUID, insight_id: uuid.UUID) -> list[StoredEvent]:
        """Return the (surviving) events an insight cites, user-scoped."""
        row = self._require_insight(user_id, insight_id)
        assert row is not None
        ids = [uuid.UUID(value) for value in row.evidence]
        if not ids:
            return []
        rows = self._session.scalars(
            select(EventRow).where(EventRow.user_id == user_id, EventRow.event_id.in_(ids))
        )
        return [_to_stored(event_row) for event_row in rows]

    def _require_insight(
        self, user_id: uuid.UUID, insight_id: uuid.UUID, *, raising: bool = True
    ) -> InsightRow | None:
        row = self._session.scalars(
            select(InsightRow).where(
                InsightRow.insight_id == insight_id, InsightRow.user_id == user_id
            )
        ).one_or_none()
        if row is None and raising:
            raise UnknownInsightError(insight_id)
        return row
