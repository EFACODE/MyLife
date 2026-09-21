"""Notification preferences.

A small user-scoped registry of which channels are enabled and the WhatsApp
number to use. Not event-sourced — like ``AccountRow``/``BillRow`` it is a
current-state row a user updates directly; there is no immutable fact to
preserve about "what the preference used to be". See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from mylife.core.events.store import _stored_utc
from mylife.notifications.models import NotificationPreference, NotificationPreferenceRow

_DEFAULT = NotificationPreference(
    email_enabled=True,
    whatsapp_enabled=False,
    whatsapp_phone=None,
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
)


def _to_preference(row: NotificationPreferenceRow) -> NotificationPreference:
    return NotificationPreference(
        email_enabled=row.email_enabled,
        whatsapp_enabled=row.whatsapp_enabled,
        whatsapp_phone=row.whatsapp_phone,
        updated_at=_stored_utc(row.updated_at),
    )


class NotificationPreferenceService:
    """Reads and updates a user's notification preferences."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> NotificationPreference:
        """Return the user's preferences, or sane defaults if never set."""
        row = self._session.get(NotificationPreferenceRow, user_id)
        return _to_preference(row) if row is not None else _DEFAULT

    def set(
        self,
        user_id: uuid.UUID,
        *,
        email_enabled: bool,
        whatsapp_enabled: bool,
        whatsapp_phone: str | None,
        now: datetime,
    ) -> NotificationPreference:
        """Create or update the user's notification preferences."""
        row = self._session.get(NotificationPreferenceRow, user_id)
        if row is None:
            row = NotificationPreferenceRow(user_id=user_id)
            self._session.add(row)
        row.email_enabled = email_enabled
        row.whatsapp_enabled = whatsapp_enabled
        row.whatsapp_phone = whatsapp_phone.strip() if whatsapp_phone else None
        row.updated_at = now
        self._session.commit()
        return _to_preference(row)
