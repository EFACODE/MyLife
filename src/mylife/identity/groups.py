"""User groups, roles and shared-data scope resolution (T2.6).

A group (stored as a ``households`` row) has a titular (``owner_user_id``)
whose data in the *shared domains* its members read and write. Admins manage
roles and groups; every change emits Life Events on the affected user's stream
and an audit entry with the admin as actor. See
``specs/domain/identity/user-groups.md``.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.core.events.store import _stored_utc
from mylife.identity.audit import AuditService
from mylife.identity.models import (
    ADMIN_ROLE,
    GroupDetail,
    GroupJoined,
    GroupJoinedPayload,
    GroupLeft,
    GroupLeftPayload,
    GroupMember,
    HouseholdRow,
    Role,
    RoleChanged,
    RoleChangedPayload,
    User,
    UserRow,
)
from mylife.identity.service import IDENTITY_SOURCE, _to_user

logger = logging.getLogger(__name__)

FINANCE_DOMAIN: Final = "finance"
#: Domains whose data a group shares (the owner's data). Others stay per-user.
SHARED_DOMAINS: Final = frozenset({FINANCE_DOMAIN})


class UnknownUserError(Exception):
    """Raised when an admin action targets a user that does not exist."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"no user {user_id}")
        self.user_id = user_id


class UnknownGroupError(Exception):
    """Raised when an admin action targets a group that does not exist."""

    def __init__(self, household_id: uuid.UUID) -> None:
        super().__init__(f"no group {household_id}")
        self.household_id = household_id


class GroupConflictError(Exception):
    """Raised when a group change would break an invariant (409)."""


class LastAdminError(Exception):
    """Raised when demoting the only remaining admin (would lock admins out)."""


def _resource(household_id: uuid.UUID) -> str:
    return f"household:{household_id}"


class GroupService:
    """Admin management of roles and groups, plus shared-scope resolution."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._pending: list[LifeEvent[Any]] = []

    # --- reads -------------------------------------------------------------

    def list_users(self) -> list[User]:
        """Every user, ordered by display name then email."""
        rows = self._session.scalars(select(UserRow).order_by(UserRow.display_name, UserRow.email))
        return [_to_user(row) for row in rows]

    def list_groups(self) -> list[GroupDetail]:
        """Every group with its members, ordered by name."""
        rows = self._session.scalars(select(HouseholdRow).order_by(HouseholdRow.name))
        return [self._detail(row) for row in rows]

    def get_group(self, household_id: uuid.UUID) -> GroupDetail:
        """The group with its members (``UnknownGroupError`` if absent)."""
        return self._detail(self._group_row(household_id))

    def group_of(self, user_id: uuid.UUID) -> GroupDetail | None:
        """The group the user belongs to, or ``None``."""
        user = self._session.get(UserRow, user_id)
        if user is None or user.household_id is None:
            return None
        row = self._session.get(HouseholdRow, user.household_id)
        return self._detail(row) if row is not None else None

    def data_owner_for(self, user_id: uuid.UUID, domain: str) -> uuid.UUID:
        """Whose data ``user_id`` reads/writes in ``domain`` (FR-4).

        The group owner for a shared domain; the user themself when the domain
        isn't shared, they are not grouped, the group has no owner, or the
        owner no longer exists (e.g. erased under T2.5).
        """
        if domain not in SHARED_DOMAINS:
            return user_id
        user = self._session.get(UserRow, user_id)
        if user is None or user.household_id is None:
            return user_id
        group = self._session.get(HouseholdRow, user.household_id)
        if group is None or group.owner_user_id is None:
            return user_id
        owner = self._session.get(UserRow, group.owner_user_id)
        if owner is None or owner.household_id != group.household_id:
            return user_id
        return owner.user_id

    # --- roles -------------------------------------------------------------

    def set_role(
        self,
        user_id: uuid.UUID,
        role: Role,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> User:
        """Change a user's role; refuses to demote the last admin."""
        row = self._user_row(user_id)
        if row.role == role:
            return _to_user(row)
        if row.role == ADMIN_ROLE:
            admins = self._session.scalar(
                select(func.count()).select_from(UserRow).where(UserRow.role == ADMIN_ROLE)
            )
            if (admins or 0) <= 1:
                raise LastAdminError("cannot demote the last admin")
        row.role = role
        self._emit(
            RoleChanged(
                user_id=user_id,
                occurred_at=now,
                source=IDENTITY_SOURCE,
                correlation_id=correlation_id,
                payload=RoleChangedPayload(role=role, by_user_id=by_user_id),
            )
        )
        self._commit_and_audit("admin.role_changed", by_user_id, user_id, None, now, correlation_id)
        return _to_user(row)

    # --- groups ------------------------------------------------------------

    def create_group(
        self,
        name: str,
        owner_user_id: uuid.UUID,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> GroupDetail:
        """Create a group whose owner is its first member."""
        owner = self._user_row(owner_user_id)
        self._ensure_ungrouped(owner)
        group = HouseholdRow(
            household_id=uuid.uuid4(),
            name=name.strip(),
            owner_user_id=owner_user_id,
            created_at=now,
        )
        self._session.add(group)
        self._join(owner, group, by_user_id=by_user_id, now=now, correlation_id=correlation_id)
        self._commit_and_audit(
            "admin.group_created", by_user_id, owner_user_id, group, now, correlation_id
        )
        return self._detail(group)

    def update_group(
        self,
        household_id: uuid.UUID,
        *,
        name: str | None,
        owner_user_id: uuid.UUID | None,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> GroupDetail:
        """Rename a group and/or hand ownership to one of its members."""
        group = self._group_row(household_id)
        if name is not None:
            group.name = name.strip()
        if owner_user_id is not None:
            new_owner = self._user_row(owner_user_id)
            if new_owner.household_id != household_id:
                raise GroupConflictError("the new owner must already be a member of the group")
            group.owner_user_id = owner_user_id
        self._commit_and_audit(
            "admin.group_updated", by_user_id, owner_user_id, group, now, correlation_id
        )
        return self._detail(group)

    def delete_group(
        self,
        household_id: uuid.UUID,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> None:
        """Detach every member, then delete the group (members' own data is untouched)."""
        group = self._group_row(household_id)
        for member in self._member_rows(household_id):
            self._leave(
                member, group, by_user_id=by_user_id, now=now, correlation_id=correlation_id
            )
        self._session.flush()
        self._session.delete(group)
        self._commit_and_audit("admin.group_deleted", by_user_id, None, group, now, correlation_id)

    def add_member(
        self,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> GroupDetail:
        """Add an ungrouped user to the group."""
        group = self._group_row(household_id)
        user = self._user_row(user_id)
        self._ensure_ungrouped(user)
        self._join(user, group, by_user_id=by_user_id, now=now, correlation_id=correlation_id)
        self._commit_and_audit(
            "admin.group_member_added", by_user_id, user_id, group, now, correlation_id
        )
        return self._detail(group)

    def remove_member(
        self,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> None:
        """Remove a non-owner member from the group."""
        group = self._group_row(household_id)
        user = self._user_row(user_id)
        if user.household_id != household_id:
            raise UnknownUserError(user_id)
        if group.owner_user_id == user_id:
            raise GroupConflictError(
                "the owner cannot be removed; change the owner or delete the group"
            )
        self._leave(user, group, by_user_id=by_user_id, now=now, correlation_id=correlation_id)
        self._commit_and_audit(
            "admin.group_member_removed", by_user_id, user_id, group, now, correlation_id
        )

    # --- internals ---------------------------------------------------------

    def _user_row(self, user_id: uuid.UUID) -> UserRow:
        row = self._session.get(UserRow, user_id)
        if row is None:
            raise UnknownUserError(user_id)
        return row

    def _group_row(self, household_id: uuid.UUID) -> HouseholdRow:
        row = self._session.get(HouseholdRow, household_id)
        if row is None:
            raise UnknownGroupError(household_id)
        return row

    def _member_rows(self, household_id: uuid.UUID) -> list[UserRow]:
        return list(
            self._session.scalars(
                select(UserRow)
                .where(UserRow.household_id == household_id)
                .order_by(UserRow.display_name, UserRow.email)
            )
        )

    def _ensure_ungrouped(self, user: UserRow) -> None:
        if user.household_id is not None:
            raise GroupConflictError("the user already belongs to a group")

    def _detail(self, row: HouseholdRow) -> GroupDetail:
        return GroupDetail(
            household_id=row.household_id,
            name=row.name,
            owner_user_id=row.owner_user_id,
            created_at=_stored_utc(row.created_at),
            members=[
                GroupMember(user_id=m.user_id, display_name=m.display_name, email=m.email)
                for m in self._member_rows(row.household_id)
            ],
        )

    def _join(
        self,
        user: UserRow,
        group: HouseholdRow,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> None:
        user.household_id = group.household_id
        self._emit(
            GroupJoined(
                user_id=user.user_id,
                occurred_at=now,
                source=IDENTITY_SOURCE,
                correlation_id=correlation_id,
                payload=GroupJoinedPayload(
                    household_id=group.household_id,
                    group_name=group.name,
                    owner_user_id=group.owner_user_id,
                    by_user_id=by_user_id,
                ),
            )
        )

    def _leave(
        self,
        user: UserRow,
        group: HouseholdRow,
        *,
        by_user_id: uuid.UUID,
        now: datetime,
        correlation_id: str,
    ) -> None:
        user.household_id = None
        self._emit(
            GroupLeft(
                user_id=user.user_id,
                occurred_at=now,
                source=IDENTITY_SOURCE,
                correlation_id=correlation_id,
                payload=GroupLeftPayload(household_id=group.household_id, by_user_id=by_user_id),
            )
        )

    def _emit(self, event: LifeEvent[Any]) -> None:
        EventStore(self._session).append(event)
        self._pending.append(event)

    def _commit_and_audit(
        self,
        action: str,
        by_user_id: uuid.UUID,
        subject_user_id: uuid.UUID | None,
        group: HouseholdRow | None,
        now: datetime,
        correlation_id: str,
    ) -> None:
        """Commit the change + audit entry, then publish the pending events."""
        AuditService(self._session).record(
            action,
            now=now,
            actor_user_id=by_user_id,
            subject_user_id=subject_user_id,
            resource=_resource(group.household_id) if group is not None else None,
            correlation_id=correlation_id,
        )
        pending, self._pending = self._pending, []
        for event in pending:
            try:
                self._bus.publish(event)
            except EventDispatchError:
                logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
