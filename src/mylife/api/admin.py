"""Admin endpoints: user roles and groups (T2.6).

Every route requires an authenticated ``admin`` (``require_admin``). See
``specs/domain/identity/user-groups.md``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import require_admin
from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import (
    GroupConflictError,
    GroupDetail,
    GroupService,
    LastAdminError,
    Role,
    UnknownGroupError,
    UnknownUserError,
    User,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[Session, Depends(get_session)]
Bus = Annotated[EventBus, Depends(get_event_bus)]


class SetRoleRequest(BaseModel):
    """Request to change a user's role."""

    role: Role


class CreateGroupRequest(BaseModel):
    """Request to create a group; the owner becomes its first member."""

    name: str = Field(min_length=1)
    owner_user_id: uuid.UUID


class UpdateGroupRequest(BaseModel):
    """Request to rename a group and/or hand ownership to a member."""

    name: str | None = Field(default=None, min_length=1)
    owner_user_id: uuid.UUID | None = None


class AddMemberRequest(BaseModel):
    """Request to add a user to a group."""

    user_id: uuid.UUID


def _correlation_id() -> str:
    return get_correlation_id() or new_correlation_id()


def _not_found(exc: UnknownUserError | UnknownGroupError) -> HTTPException:
    detail = "user not found" if isinstance(exc, UnknownUserError) else "group not found"
    return HTTPException(status_code=404, detail=detail)


@router.get("/users", response_model=list[User])
def list_users(admin: AdminUser, session: DbSession, bus: Bus) -> list[User]:
    """Every user with their role and group."""
    return GroupService(session, bus).list_users()


@router.patch("/users/{user_id}/role", response_model=User)
def set_user_role(
    user_id: uuid.UUID, request: SetRoleRequest, admin: AdminUser, session: DbSession, bus: Bus
) -> User:
    """Promote or demote a user; the last admin cannot be demoted (409)."""
    try:
        return GroupService(session, bus).set_role(
            user_id,
            request.role,
            by_user_id=admin.user_id,
            now=utcnow(),
            correlation_id=_correlation_id(),
        )
    except UnknownUserError as exc:
        raise _not_found(exc) from exc
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/groups", response_model=list[GroupDetail])
def list_groups(admin: AdminUser, session: DbSession, bus: Bus) -> list[GroupDetail]:
    """Every group with its members."""
    return GroupService(session, bus).list_groups()


@router.post("/groups", response_model=GroupDetail, status_code=201)
def create_group(
    request: CreateGroupRequest, admin: AdminUser, session: DbSession, bus: Bus
) -> GroupDetail:
    """Create a group whose owner's Finance data its members share."""
    try:
        return GroupService(session, bus).create_group(
            request.name,
            request.owner_user_id,
            by_user_id=admin.user_id,
            now=utcnow(),
            correlation_id=_correlation_id(),
        )
    except UnknownUserError as exc:
        raise _not_found(exc) from exc
    except GroupConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/groups/{household_id}", response_model=GroupDetail)
def update_group(
    household_id: uuid.UUID,
    request: UpdateGroupRequest,
    admin: AdminUser,
    session: DbSession,
    bus: Bus,
) -> GroupDetail:
    """Rename a group and/or change its owner (must already be a member)."""
    try:
        return GroupService(session, bus).update_group(
            household_id,
            name=request.name,
            owner_user_id=request.owner_user_id,
            by_user_id=admin.user_id,
            now=utcnow(),
            correlation_id=_correlation_id(),
        )
    except (UnknownUserError, UnknownGroupError) as exc:
        raise _not_found(exc) from exc
    except GroupConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/groups/{household_id}", status_code=204)
def delete_group(household_id: uuid.UUID, admin: AdminUser, session: DbSession, bus: Bus) -> None:
    """Delete a group, detaching its members (their own data is untouched)."""
    try:
        GroupService(session, bus).delete_group(
            household_id, by_user_id=admin.user_id, now=utcnow(), correlation_id=_correlation_id()
        )
    except UnknownGroupError as exc:
        raise _not_found(exc) from exc


@router.post("/groups/{household_id}/members", response_model=GroupDetail, status_code=201)
def add_group_member(
    household_id: uuid.UUID,
    request: AddMemberRequest,
    admin: AdminUser,
    session: DbSession,
    bus: Bus,
) -> GroupDetail:
    """Add a user (not yet in any group) to the group."""
    try:
        return GroupService(session, bus).add_member(
            household_id,
            request.user_id,
            by_user_id=admin.user_id,
            now=utcnow(),
            correlation_id=_correlation_id(),
        )
    except (UnknownUserError, UnknownGroupError) as exc:
        raise _not_found(exc) from exc
    except GroupConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/groups/{household_id}/members/{user_id}", status_code=204)
def remove_group_member(
    household_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: AdminUser,
    session: DbSession,
    bus: Bus,
) -> None:
    """Remove a member (not the owner) from the group."""
    try:
        GroupService(session, bus).remove_member(
            household_id,
            user_id,
            by_user_id=admin.user_id,
            now=utcnow(),
            correlation_id=_correlation_id(),
        )
    except (UnknownUserError, UnknownGroupError) as exc:
        raise _not_found(exc) from exc
    except GroupConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
