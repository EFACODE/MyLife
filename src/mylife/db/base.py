"""Generic SQLAlchemy scaffolding (no domain models).

This module wires the declarative base and the engine/session factories used
across the application. It intentionally carries no business logic — domain
models register against :class:`Base` in later phases.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mylife.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base that all ORM models inherit from."""


@lru_cache
def get_engine() -> Engine:
    """Return the cached SQLAlchemy engine built from application settings."""
    settings = get_settings()
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the cached session factory bound to the application engine."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a database session, closing it when the caller is done.

    Suitable for use as a FastAPI dependency.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
