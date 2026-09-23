"""Notification preferences.

A small user-scoped registry of which channels are enabled, plus the
registries of email addresses and WhatsApp numbers alerts may be sent to
(multiple of each allowed). The enabled-channels row is not event-sourced —
like ``AccountRow``/``BillRow`` it is a current-state row a user updates
directly; there is no immutable fact to preserve about "what the preference
used to be". The alert email/phone registries follow the same current-state
pattern as the category registry (``CategoryRow``). See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events.store import _stored_utc
from mylife.notifications.models import (
    AlertEmail,
    AlertEmailRow,
    AlertPhone,
    AlertPhoneRow,
    NotificationPreference,
    NotificationPreferenceRow,
)

_DEFAULT = NotificationPreference(
    email_enabled=True,
    whatsapp_enabled=False,
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
)


def _to_preference(row: NotificationPreferenceRow) -> NotificationPreference:
    return NotificationPreference(
        email_enabled=row.email_enabled,
        whatsapp_enabled=row.whatsapp_enabled,
        updated_at=_stored_utc(row.updated_at),
    )


class DuplicateAlertEmailError(Exception):
    """Raised when a user already has an identical alert email registered."""

    def __init__(self, email: str) -> None:
        super().__init__(f"alert email {email!r} already registered")
        self.email = email


class UnknownAlertEmailError(Exception):
    """Raised when an alert email is missing or not owned by the acting user."""

    def __init__(self, alert_email_id: uuid.UUID) -> None:
        super().__init__(f"alert email {alert_email_id} not found")
        self.alert_email_id = alert_email_id


class DuplicateAlertPhoneError(Exception):
    """Raised when a user already has an identical alert phone registered."""

    def __init__(self, phone: str) -> None:
        super().__init__(f"alert phone {phone!r} already registered")
        self.phone = phone


class UnknownAlertPhoneError(Exception):
    """Raised when an alert phone is missing or not owned by the acting user."""

    def __init__(self, alert_phone_id: uuid.UUID) -> None:
        super().__init__(f"alert phone {alert_phone_id} not found")
        self.alert_phone_id = alert_phone_id


class NotificationPreferenceService:
    """Reads and updates a user's notification preferences and alert contacts."""

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
        now: datetime,
    ) -> NotificationPreference:
        """Create or update which channels the user has enabled."""
        row = self._session.get(NotificationPreferenceRow, user_id)
        if row is None:
            row = NotificationPreferenceRow(user_id=user_id)
            self._session.add(row)
        row.email_enabled = email_enabled
        row.whatsapp_enabled = whatsapp_enabled
        row.updated_at = now
        self._session.commit()
        return _to_preference(row)

    def add_alert_email(self, user_id: uuid.UUID, email: str, *, now: datetime) -> AlertEmail:
        """Register an alert email for ``user_id``, rejecting an exact duplicate."""
        normalized = email.strip().lower()
        existing = self._session.scalars(
            select(AlertEmailRow).where(AlertEmailRow.user_id == user_id)
        )
        if any(row.email == normalized for row in existing):
            raise DuplicateAlertEmailError(normalized)
        row = AlertEmailRow(
            alert_email_id=uuid.uuid4(), user_id=user_id, email=normalized, created_at=now
        )
        self._session.add(row)
        self._session.commit()
        return AlertEmail(alert_email_id=row.alert_email_id, email=row.email, created_at=now)

    def list_alert_emails(self, user_id: uuid.UUID) -> list[AlertEmail]:
        """Return all of a user's registered alert emails, oldest first."""
        rows = self._session.scalars(
            select(AlertEmailRow)
            .where(AlertEmailRow.user_id == user_id)
            .order_by(AlertEmailRow.created_at)
        )
        return [
            AlertEmail(
                alert_email_id=row.alert_email_id,
                email=row.email,
                created_at=_stored_utc(row.created_at),
            )
            for row in rows
        ]

    def delete_alert_email(self, user_id: uuid.UUID, alert_email_id: uuid.UUID) -> None:
        """Remove a user's alert email; raises :class:`UnknownAlertEmailError` if not theirs."""
        row = self._session.scalars(
            select(AlertEmailRow).where(
                AlertEmailRow.alert_email_id == alert_email_id, AlertEmailRow.user_id == user_id
            )
        ).one_or_none()
        if row is None:
            raise UnknownAlertEmailError(alert_email_id)
        self._session.delete(row)
        self._session.commit()

    def add_alert_phone(self, user_id: uuid.UUID, phone: str, *, now: datetime) -> AlertPhone:
        """Register an alert WhatsApp phone for ``user_id``, rejecting an exact duplicate."""
        normalized = phone.strip()
        existing = self._session.scalars(
            select(AlertPhoneRow).where(AlertPhoneRow.user_id == user_id)
        )
        if any(row.phone == normalized for row in existing):
            raise DuplicateAlertPhoneError(normalized)
        row = AlertPhoneRow(
            alert_phone_id=uuid.uuid4(), user_id=user_id, phone=normalized, created_at=now
        )
        self._session.add(row)
        self._session.commit()
        return AlertPhone(alert_phone_id=row.alert_phone_id, phone=row.phone, created_at=now)

    def list_alert_phones(self, user_id: uuid.UUID) -> list[AlertPhone]:
        """Return all of a user's registered alert phones, oldest first."""
        rows = self._session.scalars(
            select(AlertPhoneRow)
            .where(AlertPhoneRow.user_id == user_id)
            .order_by(AlertPhoneRow.created_at)
        )
        return [
            AlertPhone(
                alert_phone_id=row.alert_phone_id,
                phone=row.phone,
                created_at=_stored_utc(row.created_at),
            )
            for row in rows
        ]

    def delete_alert_phone(self, user_id: uuid.UUID, alert_phone_id: uuid.UUID) -> None:
        """Remove a user's alert phone; raises :class:`UnknownAlertPhoneError` if not theirs."""
        row = self._session.scalars(
            select(AlertPhoneRow).where(
                AlertPhoneRow.alert_phone_id == alert_phone_id, AlertPhoneRow.user_id == user_id
            )
        ).one_or_none()
        if row is None:
            raise UnknownAlertPhoneError(alert_phone_id)
        self._session.delete(row)
        self._session.commit()
