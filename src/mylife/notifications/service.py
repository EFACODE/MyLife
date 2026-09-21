"""Notification service.

Sends a notification through a configured channel and records the attempt as
immutable Life Events: ``NotificationRequested`` always, then
``NotificationSent`` or ``NotificationDeliveryFailed`` depending on the
outcome (commit-before-publish, like the rest of the platform). This is the
audit trail for every outbound message the platform sends. See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.notifications.channels import NotificationChannel, NotificationChannelError
from mylife.notifications.models import (
    NOTIFICATIONS_SOURCE,
    Channel,
    NotificationDeliveryFailed,
    NotificationDeliveryFailedPayload,
    NotificationRequested,
    NotificationRequestedPayload,
    NotificationSent,
    NotificationSentPayload,
)

logger = logging.getLogger(__name__)


class NotificationOutcome(BaseModel):
    """The result of one notification send attempt."""

    model_config = ConfigDict(frozen=True)

    request_event_id: uuid.UUID
    channel: Channel
    recipient: str
    delivered: bool
    provider_message_id: str | None
    reason: str | None


class NotificationService:
    """Requests and delivers notifications through configured channels."""

    def __init__(
        self,
        session: Session,
        bus: EventBus,
        channels: Mapping[str, NotificationChannel],
    ) -> None:
        self._session = session
        self._bus = bus
        self._channels = channels

    def send(
        self,
        user_id: uuid.UUID,
        *,
        channel: Channel,
        template: str,
        subject: str,
        body: str,
        recipient: str,
        evidence: Sequence[uuid.UUID] = (),
        now: datetime,
        correlation_id: str,
    ) -> NotificationOutcome:
        """Request delivery of a notification and attempt to send it."""
        requested = NotificationRequested(
            user_id=user_id,
            occurred_at=now,
            source=NOTIFICATIONS_SOURCE,
            correlation_id=correlation_id,
            payload=NotificationRequestedPayload(
                channel=channel,
                template=template,
                subject=subject,
                body=body,
                recipient=recipient,
                evidence=list(evidence),
            ),
        )
        stored = EventStore(self._session).append(requested)
        self._session.commit()
        self._publish(requested)

        implementation = self._channels.get(channel)
        if implementation is None:
            return self._fail(
                user_id,
                stored.event_id,
                channel,
                recipient,
                f"no {channel} channel configured",
                now=now,
                correlation_id=correlation_id,
            )
        try:
            provider_message_id = implementation.send(recipient, subject, body)
        except NotificationChannelError as exc:
            return self._fail(
                user_id,
                stored.event_id,
                channel,
                recipient,
                str(exc),
                now=now,
                correlation_id=correlation_id,
            )

        sent = NotificationSent(
            user_id=user_id,
            occurred_at=now,
            source=NOTIFICATIONS_SOURCE,
            correlation_id=correlation_id,
            payload=NotificationSentPayload(
                request_event_id=stored.event_id,
                channel=channel,
                recipient=recipient,
                provider_message_id=provider_message_id,
            ),
        )
        EventStore(self._session).append(sent)
        self._session.commit()
        self._publish(sent)
        return NotificationOutcome(
            request_event_id=stored.event_id,
            channel=channel,
            recipient=recipient,
            delivered=True,
            provider_message_id=provider_message_id,
            reason=None,
        )

    def _fail(
        self,
        user_id: uuid.UUID,
        request_event_id: uuid.UUID,
        channel: Channel,
        recipient: str,
        reason: str,
        *,
        now: datetime,
        correlation_id: str,
    ) -> NotificationOutcome:
        failed = NotificationDeliveryFailed(
            user_id=user_id,
            occurred_at=now,
            source=NOTIFICATIONS_SOURCE,
            correlation_id=correlation_id,
            payload=NotificationDeliveryFailedPayload(
                request_event_id=request_event_id,
                channel=channel,
                recipient=recipient,
                reason=reason,
            ),
        )
        EventStore(self._session).append(failed)
        self._session.commit()
        self._publish(failed)
        return NotificationOutcome(
            request_event_id=request_event_id,
            channel=channel,
            recipient=recipient,
            delivered=False,
            provider_message_id=None,
            reason=reason,
        )

    def _publish(
        self, event: NotificationRequested | NotificationSent | NotificationDeliveryFailed
    ) -> None:
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
