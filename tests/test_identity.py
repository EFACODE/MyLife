"""Tests for the identity service (T2.1)."""

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
    DuplicateUserError,
    IdentityService,
    InvalidEmailError,
    UnknownHouseholdError,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


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


def test_register_creates_user_and_emits_event(session: Session) -> None:
    bus = InProcessEventBus()
    published: list[LifeEvent[object]] = []
    bus.subscribe(published.append)
    service = IdentityService(session, bus)

    user = service.register_user(
        "  Ada@Example.COM ", "Ada", password="s3cretpw", now=NOW, correlation_id="cid"
    )

    assert user.email == "ada@example.com"  # normalized
    assert user.status == "active"
    assert service.get_user(user.user_id) == user
    assert [e.event_type for e in published] == ["identity.user_registered"]
    stored = EventStore(session).read_stream(user.user_id)
    assert [e.event_type for e in stored] == ["identity.user_registered"]


def test_duplicate_email_rejected(session: Session) -> None:
    service = IdentityService(session, InProcessEventBus())
    service.register_user(
        "ada@example.com", "Ada", password="s3cretpw", now=NOW, correlation_id="c"
    )

    with pytest.raises(DuplicateUserError):
        service.register_user(
            "ADA@example.com", "Ada 2", password="s3cretpw", now=NOW, correlation_id="c"
        )

    assert len(EventStore(session).read_all()) == 1


def test_invalid_email_rejected(session: Session) -> None:
    service = IdentityService(session, InProcessEventBus())
    with pytest.raises(InvalidEmailError):
        service.register_user("not-an-email", "X", password="s3cretpw", now=NOW, correlation_id="c")


def test_household_link_and_unknown(session: Session) -> None:
    service = IdentityService(session, InProcessEventBus())
    household = service.create_household("Home", now=NOW)

    user = service.register_user(
        "a@b.com",
        "A",
        password="s3cretpw",
        now=NOW,
        correlation_id="c",
        household_id=household.household_id,
    )
    assert user.household_id == household.household_id
    assert service.get_household(household.household_id) == household

    with pytest.raises(UnknownHouseholdError):
        service.register_user(
            "c@d.com",
            "C",
            password="s3cretpw",
            now=NOW,
            correlation_id="c",
            household_id=uuid.uuid4(),
        )


def test_get_missing_returns_none(session: Session) -> None:
    service = IdentityService(session, InProcessEventBus())
    assert service.get_user(uuid.uuid4()) is None
    assert service.get_household(uuid.uuid4()) is None
