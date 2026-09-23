"""Identity service.

Registers users (emitting ``UserRegistered``) and reads users/households. See
``specs/domain/identity/user-registration.md`` (T2.1).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.core.events.store import _stored_utc
from mylife.identity.models import (
    ACTIVE_STATUS,
    CredentialRow,
    Household,
    HouseholdRow,
    User,
    UserRegistered,
    UserRegisteredPayload,
    UserRow,
    UserUpdated,
    UserUpdatedPayload,
)
from mylife.identity.security import hash_password, verify_password

logger = logging.getLogger(__name__)

IDENTITY_SOURCE = "identity"


class DuplicateUserError(Exception):
    """Raised when registering an email that already exists."""

    def __init__(self, email: str) -> None:
        super().__init__(f"a user with email {email!r} already exists")
        self.email = email


class UnknownHouseholdError(Exception):
    """Raised when registering into a household that does not exist."""

    def __init__(self, household_id: uuid.UUID) -> None:
        super().__init__(f"no household {household_id}")
        self.household_id = household_id


class InvalidEmailError(ValueError):
    """Raised when an email fails validation."""


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise InvalidEmailError(f"invalid email {email!r}")
    return normalized


def _to_user(row: UserRow) -> User:
    return User(
        user_id=row.user_id,
        email=row.email,
        display_name=row.display_name,
        status=row.status,
        household_id=row.household_id,
        created_at=_stored_utc(row.created_at),
    )


def _to_household(row: HouseholdRow) -> Household:
    return Household(
        household_id=row.household_id, name=row.name, created_at=_stored_utc(row.created_at)
    )


class IdentityService:
    """Registers and reads identities."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def register_user(
        self,
        email: str,
        display_name: str,
        *,
        password: str,
        now: datetime,
        correlation_id: str,
        household_id: uuid.UUID | None = None,
    ) -> User:
        """Register a user (unique email) with a credential, emit ``UserRegistered``."""
        normalized = _normalize_email(email)
        if household_id is not None and self._session.get(HouseholdRow, household_id) is None:
            raise UnknownHouseholdError(household_id)
        if self._session.scalars(select(UserRow).where(UserRow.email == normalized)).one_or_none():
            raise DuplicateUserError(normalized)

        user_id = uuid.uuid4()
        row = UserRow(
            user_id=user_id,
            email=normalized,
            display_name=display_name,
            status=ACTIVE_STATUS,
            household_id=household_id,
            created_at=now,
        )
        credential = CredentialRow(
            user_id=user_id, password_hash=hash_password(password), updated_at=now
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.add(credential)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateUserError(normalized) from exc

        event = UserRegistered(
            user_id=user_id,
            occurred_at=now,
            source=IDENTITY_SOURCE,
            correlation_id=correlation_id,
            payload=UserRegisteredPayload(email=normalized, display_name=display_name),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return _to_user(row)

    def authenticate(self, email: str, password: str) -> User | None:
        """Return the user if the email+password are valid, else ``None``."""
        normalized = email.strip().lower()
        user_row = self._session.scalars(
            select(UserRow).where(UserRow.email == normalized)
        ).one_or_none()
        if user_row is None:
            return None
        credential = self._session.get(CredentialRow, user_row.user_id)
        if credential is None or not verify_password(password, credential.password_hash):
            return None
        return _to_user(user_row)

    def get_user(self, user_id: uuid.UUID) -> User | None:
        """Return the user or ``None``."""
        row = self._session.get(UserRow, user_id)
        return _to_user(row) if row is not None else None

    def update_display_name(
        self, user_id: uuid.UUID, display_name: str, *, now: datetime, correlation_id: str
    ) -> User:
        """Update the user's display name (email is immutable), emitting ``UserUpdated``."""
        row = self._session.get(UserRow, user_id)
        assert row is not None  # the caller resolved this user via authentication
        normalized = display_name.strip()
        row.display_name = normalized

        event = UserUpdated(
            user_id=user_id,
            occurred_at=now,
            source=IDENTITY_SOURCE,
            correlation_id=correlation_id,
            payload=UserUpdatedPayload(display_name=normalized),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return _to_user(row)

    def create_household(self, name: str, *, now: datetime) -> Household:
        """Create and return a household."""
        row = HouseholdRow(household_id=uuid.uuid4(), name=name, created_at=now)
        self._session.add(row)
        self._session.commit()
        return _to_household(row)

    def get_household(self, household_id: uuid.UUID) -> Household | None:
        """Return the household or ``None``."""
        row = self._session.get(HouseholdRow, household_id)
        return _to_household(row) if row is not None else None
