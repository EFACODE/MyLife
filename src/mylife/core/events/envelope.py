"""The Life Event envelope.

Every Life Event carries this immutable envelope, independent of its
domain-specific payload. It is the contract that makes the platform explainable
and auditable: *what* happened, *when* it happened versus when it was recorded,
*where* it came from, and *whom* it belongs to.

See ``specs/domain/timeline/event-envelope.md`` (T1.1).
"""

import uuid
from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

PayloadT = TypeVar("PayloadT", bound=BaseModel)


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as UTC, rejecting naive (timezone-less) datetimes."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return value.astimezone(UTC)


class LifeEvent(BaseModel, Generic[PayloadT]):
    """Immutable envelope shared by every Life Event.

    Domain events specialize this by binding ``payload`` to a concrete model
    and fixing ``event_type``/``schema_version`` (see
    :class:`mylife.core.events.life_event.LifeEventRecorded`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    event_type: str = Field(min_length=1)
    occurred_at: datetime
    recorded_at: datetime = Field(default_factory=utcnow)
    schema_version: int = Field(ge=1)
    source: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    payload: PayloadT

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)
