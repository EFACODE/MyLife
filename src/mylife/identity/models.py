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
USER_UPDATED: Final = "identity.user_updated"
ROLE_CHANGED: Final = "identity.role_changed"
GROUP_JOINED: Final = "identity.group_joined"
GROUP_LEFT: Final = "identity.group_left"
ACTIVE_STATUS: Final = "active"

Role = Literal["member", "admin"]
MEMBER_ROLE: Final = "member"
ADMIN_ROLE: Final = "admin"


class HouseholdRow(Base):
    """A household (user group) users may belong to.

    ``owner_user_id`` is the titular whose shared-domain data (Finance) the
    group's members read and write (T2.6). ``None`` only for legacy rows.
    """

    __tablename__ = "households"

    household_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CredentialRow(Base):
    """A user's login credential (Argon2 password hash). One per user."""

    __tablename__ = "credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    """A registered user."""

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default=MEMBER_ROLE, server_default=MEMBER_ROLE)
    household_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(BaseModel):
    """A user as read back from the identity store."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    email: str
    display_name: str
    status: str
    role: Role = "member"
    household_id: uuid.UUID | None
    created_at: datetime


class Household(BaseModel):
    """A household as read back from the identity store."""

    model_config = ConfigDict(frozen=True)

    household_id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None = None
    created_at: datetime


class GroupMember(BaseModel):
    """A member of a group, as shown to admins and fellow members."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    display_name: str
    email: str


class GroupDetail(BaseModel):
    """A group with its members (T2.6)."""

    model_config = ConfigDict(frozen=True)

    household_id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None
    created_at: datetime
    members: list[GroupMember]


class UserRegisteredPayload(BaseModel):
    """The registration fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str
    display_name: str


class UserRegistered(LifeEvent[UserRegisteredPayload]):
    """Emitted when a user registers (Identity context)."""

    event_type: Literal["identity.user_registered"] = USER_REGISTERED
    schema_version: Literal[1] = 1


class UserUpdatedPayload(BaseModel):
    """A correction to a user's editable profile fields (email is immutable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str


class UserUpdated(LifeEvent[UserUpdatedPayload]):
    """Emitted when a user edits their profile (Identity context)."""

    event_type: Literal["identity.user_updated"] = USER_UPDATED
    schema_version: Literal[1] = 1


class RoleChangedPayload(BaseModel):
    """A user's role changed; ``by_user_id`` is ``None`` for the config bootstrap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Role
    by_user_id: uuid.UUID | None


class RoleChanged(LifeEvent[RoleChangedPayload]):
    """Emitted on the target user's stream when their role changes (T2.6)."""

    event_type: Literal["identity.role_changed"] = ROLE_CHANGED
    schema_version: Literal[1] = 1


class GroupJoinedPayload(BaseModel):
    """The user was added to a group whose owner's shared data they now access."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    household_id: uuid.UUID
    group_name: str
    owner_user_id: uuid.UUID | None
    by_user_id: uuid.UUID


class GroupJoined(LifeEvent[GroupJoinedPayload]):
    """Emitted on the member's stream when they join a group (T2.6)."""

    event_type: Literal["identity.group_joined"] = GROUP_JOINED
    schema_version: Literal[1] = 1


class GroupLeftPayload(BaseModel):
    """The user left (or was removed from, or lost by deletion) a group."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    household_id: uuid.UUID
    by_user_id: uuid.UUID


class GroupLeft(LifeEvent[GroupLeftPayload]):
    """Emitted on the member's stream when they leave a group (T2.6)."""

    event_type: Literal["identity.group_left"] = GROUP_LEFT
    schema_version: Literal[1] = 1
