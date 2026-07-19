"""Identity models and events.

The ``User`` and ``Household`` aggregates and the ``UserRegistered`` event. See
``specs/domain/identity/user-registration.md`` (T2.1).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

USER_REGISTERED: Final = "identity.user_registered"
ACTIVE_STATUS: Final = "active"


class HouseholdRow(Base):
    """A household users may belong to."""

    __tablename__ = "households"

    household_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    """A registered user."""

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    household_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(BaseModel):
    """A user as read back from the identity store."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    email: str
    display_name: str
    status: str
    household_id: uuid.UUID | None
    created_at: datetime


class Household(BaseModel):
    """A household as read back from the identity store."""

    model_config = ConfigDict(frozen=True)

    household_id: uuid.UUID
    name: str
    created_at: datetime


class UserRegisteredPayload(BaseModel):
    """The registration fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str
    display_name: str


class UserRegistered(LifeEvent[UserRegisteredPayload]):
    """Emitted when a user registers (Identity context)."""

    event_type: Literal["identity.user_registered"] = USER_REGISTERED
    schema_version: Literal[1] = 1
