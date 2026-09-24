"""Tests for the third-party credential vault (T4.9)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.db.base import Base
from mylife.identity.credential_vault import CredentialVault, ThirdPartyCredentialRow

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
KEY = Fernet.generate_key().decode()


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


def test_store_then_get_round_trips(session: Session) -> None:
    user = uuid.uuid4()
    vault = CredentialVault(session, KEY)

    vault.store(user, "pierre_finance", "sk-secret-123", now=NOW)

    assert vault.get(user, "pierre_finance") == "sk-secret-123"


def test_get_missing_returns_none(session: Session) -> None:
    vault = CredentialVault(session, KEY)
    assert vault.get(uuid.uuid4(), "pierre_finance") is None


def test_store_twice_updates_in_place(session: Session) -> None:
    user = uuid.uuid4()
    vault = CredentialVault(session, KEY)

    vault.store(user, "pierre_finance", "sk-old", now=NOW)
    vault.store(user, "pierre_finance", "sk-new", now=NOW)

    assert vault.get(user, "pierre_finance") == "sk-new"
    rows = session.scalars(
        select(ThirdPartyCredentialRow).where(ThirdPartyCredentialRow.user_id == user)
    ).all()
    assert len(rows) == 1


def test_delete_then_get_returns_none(session: Session) -> None:
    user = uuid.uuid4()
    vault = CredentialVault(session, KEY)
    vault.store(user, "pierre_finance", "sk-secret", now=NOW)

    vault.delete(user, "pierre_finance")

    assert vault.get(user, "pierre_finance") is None


def test_delete_twice_is_a_noop(session: Session) -> None:
    vault = CredentialVault(session, KEY)
    user = uuid.uuid4()
    vault.delete(user, "pierre_finance")
    vault.delete(user, "pierre_finance")  # does not raise


def test_ciphertext_is_not_the_plaintext(session: Session) -> None:
    user = uuid.uuid4()
    vault = CredentialVault(session, KEY)
    vault.store(user, "pierre_finance", "sk-secret-123", now=NOW)

    row = session.get(ThirdPartyCredentialRow, (user, "pierre_finance"))
    assert row is not None
    assert "sk-secret-123" not in row.secret_ciphertext


def test_wrong_key_fails_closed(session: Session) -> None:
    user = uuid.uuid4()
    CredentialVault(session, KEY).store(user, "pierre_finance", "sk-secret", now=NOW)

    other_vault = CredentialVault(session, Fernet.generate_key().decode())
    assert other_vault.get(user, "pierre_finance") is None
