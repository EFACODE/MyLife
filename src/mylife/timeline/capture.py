"""Manual timeline capture.

The write side of the timeline: a command service that records a
``LifeEventRecorded`` by hand — appending it to the store and publishing it on
the event bus. Completes the capture→read loop with no connectors. See
``specs/domain/timeline/manual-capture.md`` (T3.2).
"""

import logging
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from mylife.core.events import (
    EventBus,
    EventDispatchError,
    EventStore,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    StoredEvent,
)
from mylife.core.events.envelope import ensure_utc

logger = logging.getLogger(__name__)


class RecordLifeEventCommand(BaseModel):
    """A user's request to record a Life Event by hand."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    occurred_at: datetime
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    note: str | None = None
    source: str = Field(default="manual", min_length=1)

    @field_validator("occurred_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class TimelineWriter:
    """Records Life Events: append to the store, then publish on the bus."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def record(self, command: RecordLifeEventCommand, *, correlation_id: str) -> StoredEvent:
        """Append and publish a ``LifeEventRecorded`` from ``command``.

        The event is committed (durable) before publishing; a publish failure is
        logged but does not roll back the stored event.
        """
        event = LifeEventRecorded(
            user_id=command.user_id,
            occurred_at=command.occurred_at,
            source=command.source,
            correlation_id=correlation_id,
            payload=LifeEventRecordedPayload(
                title=command.title, category=command.category, note=command.note
            ),
        )
        stored = EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return stored
