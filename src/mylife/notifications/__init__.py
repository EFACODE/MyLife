"""Notifications bounded context.

Generic outbound-delivery infrastructure (not Finance-specific): a channel
protocol with SMTP-email and WhatsApp-Cloud-API adapters, a user-scoped
preferences registry, and a service that records every send attempt as an
immutable, evidence-linked audit trail (``NotificationRequested`` /
``NotificationSent`` / ``NotificationDeliveryFailed``). Finance's bill
due-date scan (T4.8) is its first caller. See
``specs/domain/notifications/outbound-delivery.md``.
"""

from mylife.notifications.channels import (
    NotificationChannel,
    NotificationChannelError,
    SmtpEmailChannel,
    WhatsAppCloudApiChannel,
    build_channels_from_settings,
)
from mylife.notifications.models import (
    NOTIFICATION_DELIVERY_FAILED,
    NOTIFICATION_REQUESTED,
    NOTIFICATION_SENT,
    AlertEmail,
    AlertEmailRow,
    AlertPhone,
    AlertPhoneRow,
    NotificationDeliveryFailed,
    NotificationDeliveryFailedPayload,
    NotificationPreference,
    NotificationPreferenceRow,
    NotificationRequested,
    NotificationRequestedPayload,
    NotificationSent,
    NotificationSentPayload,
)
from mylife.notifications.preferences import (
    DuplicateAlertEmailError,
    DuplicateAlertPhoneError,
    NotificationPreferenceService,
    UnknownAlertEmailError,
    UnknownAlertPhoneError,
)
from mylife.notifications.service import NotificationOutcome, NotificationService

__all__ = [
    "NOTIFICATION_DELIVERY_FAILED",
    "NOTIFICATION_REQUESTED",
    "NOTIFICATION_SENT",
    "AlertEmail",
    "AlertEmailRow",
    "AlertPhone",
    "AlertPhoneRow",
    "DuplicateAlertEmailError",
    "DuplicateAlertPhoneError",
    "NotificationChannel",
    "NotificationChannelError",
    "NotificationDeliveryFailed",
    "NotificationDeliveryFailedPayload",
    "NotificationOutcome",
    "NotificationPreference",
    "NotificationPreferenceRow",
    "NotificationPreferenceService",
    "NotificationRequested",
    "NotificationRequestedPayload",
    "NotificationSent",
    "NotificationSentPayload",
    "NotificationService",
    "SmtpEmailChannel",
    "UnknownAlertEmailError",
    "UnknownAlertPhoneError",
    "WhatsAppCloudApiChannel",
    "build_channels_from_settings",
]
