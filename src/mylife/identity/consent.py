"""Consent model and service.

Granular per-scope consent, recorded as immutable ``ConsentGranted`` /
``ConsentRevoked`` events with a rebuildable current-state projection
(``consents``). ``ConsentService`` also satisfies the connector ``ConsentGate``.
See ``specs/domain/identity/consent.md`` (T2.3).
"""

import logging
import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.core.events.store import _stored_utc
from mylife.db.base import Base

logger = logging.getLogger(__name__)

CONSENT_GRANTED: Final = "identity.consent_granted"
CONSENT_REVOKED: Final = "identity.consent_revoked"
IDENTITY_SOURCE = "identity"


class ConsentRow(Base):
    """Current consent state per ``(user, scope)`` (derived projection)."""

    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("user_id", "scope", name="uq_consents_user_scope"),)

    consent_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    scope: Mapped[str] = mapped_column(String)
    granted: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Consent(BaseModel):
    """A user's consent for a scope, as read back."""

    model_config = ConfigDict(frozen=True)

    scope: str
    granted: bool
    updated_at: datetime


class ConsentPayload(BaseModel):
    """The scope a consent decision applies to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: str


class ConsentGranted(LifeEvent[ConsentPayload]):
    """Emitted when a user grants consent for a scope."""

    event_type: Literal["identity.consent_granted"] = CONSENT_GRANTED
    schema_version: Literal[1] = 1


class ConsentRevoked(LifeEvent[ConsentPayload]):
    """Emitted when a user revokes consent for a scope."""

    event_type: Literal["identity.consent_revoked"] = CONSENT_REVOKED
    schema_version: Literal[1] = 1


class ConsentService:
    """Records consent decisions (as events + projection) and reads them."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def grant(
        self, user_id: uuid.UUID, scope: str, *, now: datetime, correlation_id: str
    ) -> Consent:
        """Grant consent for ``scope``."""
        return self._decide(user_id, scope, granted=True, now=now, correlation_id=correlation_id)

    def revoke(
        self, user_id: uuid.UUID, scope: str, *, now: datetime, correlation_id: str
    ) -> Consent:
        """Revoke consent for ``scope``."""
        return self._decide(user_id, scope, granted=False, now=now, correlation_id=correlation_id)

    def _decide(
        self, user_id: uuid.UUID, scope: str, *, granted: bool, now: datetime, correlation_id: str
    ) -> Consent:
        normalized = scope.strip()
        row = self._session.scalars(
            select(ConsentRow).where(ConsentRow.user_id == user_id, ConsentRow.scope == normalized)
        ).one_or_none()
        if row is None:
            self._session.add(
                ConsentRow(
                    consent_id=uuid.uuid4(),
                    user_id=user_id,
                    scope=normalized,
                    granted=granted,
                    updated_at=now,
                )
            )
        else:
            row.granted = granted
            row.updated_at = now

        event_cls = ConsentGranted if granted else ConsentRevoked
        event = event_cls(
            user_id=user_id,
            occurred_at=now,
            source=IDENTITY_SOURCE,
            correlation_id=correlation_id,
            payload=ConsentPayload(scope=normalized),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)

        return Consent(scope=normalized, granted=granted, updated_at=now)

    def is_granted(self, user_id: uuid.UUID, scope: str) -> bool:
        """Return whether ``user_id`` has granted consent for ``scope``."""
        row = self._session.scalars(
            select(ConsentRow).where(
                ConsentRow.user_id == user_id, ConsentRow.scope == scope.strip()
            )
        ).one_or_none()
        return bool(row is not None and row.granted)

    def list_consents(self, user_id: uuid.UUID) -> list[Consent]:
        """Return all of a user's consent entries, ordered by scope."""
        rows = self._session.scalars(
            select(ConsentRow).where(ConsentRow.user_id == user_id).order_by(ConsentRow.scope)
        )
        return [
            Consent(scope=row.scope, granted=row.granted, updated_at=_stored_utc(row.updated_at))
            for row in rows
        ]
