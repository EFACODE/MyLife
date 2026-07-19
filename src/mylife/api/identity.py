"""Identity endpoints.

Register and read users and households. See
``specs/domain/identity/user-registration.md`` (T2.1). These are unauthenticated
placeholders until auth (T2.2) and consent (T2.3) land.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import (
    DuplicateUserError,
    Household,
    IdentityService,
    InvalidEmailError,
    UnknownHouseholdError,
    User,
)

router = APIRouter(tags=["identity"])


class RegisterUserRequest(BaseModel):
    """Request to register a user."""

    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    household_id: uuid.UUID | None = None


class CreateHouseholdRequest(BaseModel):
    """Request to create a household."""

    name: str = Field(min_length=1)


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
            now=utcnow(),
            correlation_id=correlation_id,
            household_id=request.household_id,
        )
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc
    except UnknownHouseholdError as exc:
        raise HTTPException(status_code=422, detail="unknown household") from exc
    except InvalidEmailError as exc:
        raise HTTPException(status_code=422, detail="invalid email") from exc


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


@router.post("/households", response_model=Household, status_code=201)
def create_household(
    request: CreateHouseholdRequest,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Household:
    """Create a household."""
    return IdentityService(session, bus).create_household(request.name, now=utcnow())


@router.get("/households/{household_id}", response_model=Household)
def read_household(
    household_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Household:
    """Read a household by id."""
    household = IdentityService(session, bus).get_household(household_id)
    if household is None:
        raise HTTPException(status_code=404, detail="household not found")
    return household
