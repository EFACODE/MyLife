"""Tests for user groups, roles and shared-scope resolution (T2.6)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus, LifeEvent
from mylife.db.base import Base
from mylife.identity import (
    FINANCE_DOMAIN,
    GroupConflictError,
    GroupService,
    IdentityService,
    LastAdminError,
    UnknownUserError,
    User,
)
from mylife.identity.audit import AuditService
from mylife.identity.models import UserRow

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
CID = "corr-groups"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def _user(session: Session, email: str, *, admin: bool = False) -> User:
    return IdentityService(session, InProcessEventBus()).register_user(
        email,
        email.split("@")[0],
        password="s3cretpw",
        now=NOW,
        correlation_id=CID,
        admin_emails=frozenset({email}) if admin else frozenset(),
    )


def _event_types(session: Session, user_id: uuid.UUID) -> list[str]:
    return [e.event_type for e in EventStore(session).read_stream(user_id)]


def test_admin_bootstrap_at_registration_and_login(session: Session) -> None:
    admin = _user(session, "root@example.com", admin=True)
    member = _user(session, "ann@example.com")
    assert admin.role == "admin"
    assert member.role == "member"

    promoted = IdentityService(session, InProcessEventBus()).authenticate(
        "ann@example.com",
        "s3cretpw",
        admin_emails=frozenset({"ann@example.com"}),
        now=NOW,
        correlation_id=CID,
    )
    assert promoted is not None and promoted.role == "admin"
    assert "identity.role_changed" in _event_types(session, member.user_id)


def test_set_role_refuses_to_demote_last_admin(session: Session) -> None:
    admin = _user(session, "root@example.com", admin=True)
    other = _user(session, "ann@example.com")
    service = GroupService(session, InProcessEventBus())

    with pytest.raises(LastAdminError):
        service.set_role(
            admin.user_id, "member", by_user_id=admin.user_id, now=NOW, correlation_id=CID
        )

    service.set_role(other.user_id, "admin", by_user_id=admin.user_id, now=NOW, correlation_id=CID)
    demoted = service.set_role(
        admin.user_id, "member", by_user_id=other.user_id, now=NOW, correlation_id=CID
    )
    assert demoted.role == "member"
    with pytest.raises(UnknownUserError):
        service.set_role(
            uuid.uuid4(), "admin", by_user_id=other.user_id, now=NOW, correlation_id=CID
        )


def test_group_lifecycle_and_scope_resolution(session: Session) -> None:
    admin = _user(session, "root@example.com", admin=True)
    owner = _user(session, "owner@example.com")
    member = _user(session, "member@example.com")
    loner = _user(session, "loner@example.com")
    published: list[LifeEvent[object]] = []
    bus = InProcessEventBus()
    bus.subscribe(published.append, event_type="identity.group_joined")
    service = GroupService(session, bus)

    group = service.create_group(
        "Casa", owner.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
    )
    assert group.owner_user_id == owner.user_id
    assert [m.user_id for m in group.members] == [owner.user_id]

    group = service.add_member(
        group.household_id, member.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
    )
    assert {m.user_id for m in group.members} == {owner.user_id, member.user_id}
    assert len(published) == 2

    # Members resolve to the owner's ledger for shared domains only.
    assert service.data_owner_for(member.user_id, FINANCE_DOMAIN) == owner.user_id
    assert service.data_owner_for(owner.user_id, FINANCE_DOMAIN) == owner.user_id
    assert service.data_owner_for(member.user_id, "health") == member.user_id
    assert service.data_owner_for(loner.user_id, FINANCE_DOMAIN) == loner.user_id
    assert service.group_of(member.user_id) == group
    assert service.group_of(loner.user_id) is None

    # Conflicts: already grouped, removing the owner, foreign owner.
    with pytest.raises(GroupConflictError):
        service.add_member(
            group.household_id,
            member.user_id,
            by_user_id=admin.user_id,
            now=NOW,
            correlation_id=CID,
        )
    with pytest.raises(GroupConflictError):
        service.create_group(
            "Outro", member.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
        )
    with pytest.raises(GroupConflictError):
        service.remove_member(
            group.household_id, owner.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
        )
    with pytest.raises(GroupConflictError):
        service.update_group(
            group.household_id,
            name=None,
            owner_user_id=loner.user_id,
            by_user_id=admin.user_id,
            now=NOW,
            correlation_id=CID,
        )

    # Hand ownership to the member, then remove the former owner.
    group = service.update_group(
        group.household_id,
        name="Família",
        owner_user_id=member.user_id,
        by_user_id=admin.user_id,
        now=NOW,
        correlation_id=CID,
    )
    assert group.name == "Família"
    service.remove_member(
        group.household_id, owner.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
    )
    assert service.data_owner_for(owner.user_id, FINANCE_DOMAIN) == owner.user_id
    assert "identity.group_left" in _event_types(session, owner.user_id)

    service.delete_group(group.household_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID)
    assert service.list_groups() == []
    assert service.data_owner_for(member.user_id, FINANCE_DOMAIN) == member.user_id

    actions = [e.action for e in AuditService(session).list_for_subject(owner.user_id)]
    assert "admin.group_created" in actions
    assert "admin.group_member_removed" in actions


def test_scope_falls_back_when_owner_is_gone(session: Session) -> None:
    admin = _user(session, "root@example.com", admin=True)
    owner = _user(session, "owner@example.com")
    member = _user(session, "member@example.com")
    service = GroupService(session, InProcessEventBus())
    group = service.create_group(
        "Casa", owner.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
    )
    service.add_member(
        group.household_id, member.user_id, by_user_id=admin.user_id, now=NOW, correlation_id=CID
    )

    # Simulate a T2.5 erasure of the owner (hard-deletes the user row).
    row = session.get(UserRow, owner.user_id)
    assert row is not None
    session.delete(row)
    session.commit()

    assert service.data_owner_for(member.user_id, FINANCE_DOMAIN) == member.user_id
