"""The reference Life Event.

``LifeEventRecorded`` is the first concrete event type: the canonical example of
the envelope contract that domains follow. Real domains define richer payloads
in their own tasks; this payload is intentionally minimal.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from mylife.core.events.envelope import LifeEvent

EVENT_TYPE: Final = "timeline.life_event_recorded"


class LifeEventRecordedPayload(BaseModel):
    """Minimal reference payload for :class:`LifeEventRecorded`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    note: str | None = None


class LifeEventRecorded(LifeEvent[LifeEventRecordedPayload]):
    """A user-recorded fact on the timeline — the reference event type."""

    event_type: Literal["timeline.life_event_recorded"] = EVENT_TYPE
    schema_version: Literal[1] = 1
