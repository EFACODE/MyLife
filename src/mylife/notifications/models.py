"""Notifications models and events.

A ``notification_preferences`` registry (one row per user: which channels are
enabled and the WhatsApp number to use) plus the Notifications facts —
``NotificationRequested``, ``NotificationSent`` and
``NotificationDeliveryFailed`` — immutable Life Events recording every
outbound delivery attempt as an audit trail. See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

NOTIFICATION_REQUESTED: Final = "notifications.requested"
NOTIFICATION_SENT: Final = "notifications.sent"
NOTIFICATION_DELIVERY_FAILED: Final = "notifications.delivery_failed"
NOTIFICATIONS_SOURCE = "notifications"

Channel = Literal["email", "whatsapp"]


class NotificationPreferenceRow(Base):
    """A user's notification delivery preferences (current state)."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationPreference(BaseModel):
    """A user's notification preferences as read back from the registry."""

    model_config = ConfigDict(frozen=True)

    email_enabled: bool
    whatsapp_enabled: bool
    updated_at: datetime


class AlertEmailRow(Base):
    """A user-scoped email address alerts may be sent to (multiple allowed)."""

    __tablename__ = "alert_emails"

    alert_email_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertEmail(BaseModel):
    """An alert email address as read back from the registry."""

    model_config = ConfigDict(frozen=True)

    alert_email_id: uuid.UUID
    email: str
    created_at: datetime


class AlertPhoneRow(Base):
    """A user-scoped WhatsApp phone number alerts may be sent to (multiple allowed)."""

    __tablename__ = "alert_phones"

    alert_phone_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    phone: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertPhone(BaseModel):
    """An alert WhatsApp phone number as read back from the registry."""

    model_config = ConfigDict(frozen=True)

    alert_phone_id: uuid.UUID
    phone: str
    created_at: datetime


class NotificationRequestedPayload(BaseModel):
    """The fact that a notification was requested, before any send attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    template: str
    subject: str
    body: str
    recipient: str
    evidence: list[uuid.UUID] = []


class NotificationSentPayload(BaseModel):
    """A notification was successfully delivered to its channel's provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_event_id: uuid.UUID
    channel: Channel
    recipient: str
    provider_message_id: str | None = None


class NotificationDeliveryFailedPayload(BaseModel):
    """A notification's delivery attempt failed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_event_id: uuid.UUID
    channel: Channel
    recipient: str
    reason: str


class NotificationRequested(LifeEvent[NotificationRequestedPayload]):
    """Emitted when a notification is requested (Notifications context)."""

    event_type: Literal["notifications.requested"] = NOTIFICATION_REQUESTED
    schema_version: Literal[1] = 1


class NotificationSent(LifeEvent[NotificationSentPayload]):
    """Emitted when a notification is delivered to its channel (Notifications)."""

    event_type: Literal["notifications.sent"] = NOTIFICATION_SENT
    schema_version: Literal[1] = 1


class NotificationDeliveryFailed(LifeEvent[NotificationDeliveryFailedPayload]):
    """Emitted when a notification's delivery attempt fails (Notifications)."""

    event_type: Literal["notifications.delivery_failed"] = NOTIFICATION_DELIVERY_FAILED
    schema_version: Literal[1] = 1
