"""Identity endpoints.

Register and read users, and read the caller's group. See
``specs/domain/identity/user-registration.md`` (T2.1) and
``specs/domain/identity/user-groups.md`` (T2.6). Group management itself is
admin-only and lives in ``mylife.api.admin``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.core.config import get_settings
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import (
    DuplicateUserError,
    GroupDetail,
    GroupService,
    IdentityService,
    InvalidEmailError,
    User,
)

router = APIRouter(tags=["identity"])


class RegisterUserRequest(BaseModel):
    """Request to register a user.

    Unknown fields are rejected: in particular ``household_id`` — joining a
    group grants access to its owner's data, so only an admin may do it (T2.6).
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=8)


class UpdateUserRequest(BaseModel):
    """Request to edit the authenticated user's editable profile fields.

    The account email is immutable and not included here.
    """

    display_name: str = Field(min_length=1)


@router.post("/users", response_model=User, status_code=201)
def register_user(
    request: RegisterUserRequest,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> User:
    """Register a new user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return IdentityService(session, bus).register_user(
            request.email,
            request.display_name,
            password=request.password,
            now=utcnow(),
            correlation_id=correlation_id,
            admin_emails=get_settings().admin_email_set,
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc
    except InvalidEmailError as exc:
        raise HTTPException(status_code=422, detail="invalid email") from exc


@router.patch("/users/me", response_model=User)
def update_current_user(
    request: UpdateUserRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> User:
    """Edit the authenticated user's display name (email cannot be changed)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return IdentityService(session, bus).update_display_name(
        current_user.user_id,
        request.display_name,
        now=utcnow(),
        correlation_id=correlation_id,
    )


@router.get("/users/{user_id}", response_model=User)
def read_user(
    user_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> User:
    """Read a user by id."""
    user = IdentityService(session, bus).get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("/groups/me", response_model=GroupDetail | None)
def read_my_group(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> GroupDetail | None:
    """The authenticated user's group (with its members), or ``null``."""
    return GroupService(session, bus).group_of(current_user.user_id)
