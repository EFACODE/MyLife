"""Event corrections.

History is immutable: to correct a recorded event, append a **new** event that
references the one it supersedes via the envelope's ``corrects_event_id``.
``EventCorrected`` is the explicit correction/retraction type; any domain event
may also set ``corrects_event_id`` to supersede a prior one. See
``specs/domain/timeline/event-correction.md`` (T1.5).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from mylife.core.events.envelope import LifeEvent

CORRECTION_EVENT_TYPE: Final = "timeline.event_corrected"


class EventCorrectionPayload(BaseModel):
    """Why a prior event was corrected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)
    note: str | None = None


class EventCorrected(LifeEvent[EventCorrectionPayload]):
    """An explicit correction or retraction of a prior event.

    ``corrects_event_id`` (from the envelope) must be set to the corrected event.
    """

    event_type: Literal["timeline.event_corrected"] = CORRECTION_EVENT_TYPE
    schema_version: Literal[1] = 1


def correct_event(
    corrected_event_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    reason: str,
    source: str,
    correlation_id: str,
    occurred_at: datetime,
    note: str | None = None,
) -> EventCorrected:
    """Build an :class:`EventCorrected` that supersedes ``corrected_event_id``."""
    return EventCorrected(
        user_id=user_id,
        occurred_at=occurred_at,
        source=source,
        correlation_id=correlation_id,
        corrects_event_id=corrected_event_id,
        payload=EventCorrectionPayload(reason=reason, note=note),
    )
