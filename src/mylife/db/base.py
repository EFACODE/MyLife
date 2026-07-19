"""Generic SQLAlchemy scaffolding (no domain models).

This module wires the declarative base and the engine/session factories used
across the application. It intentionally carries no business logic — domain
models register against :class:`Base` in later phases.
"""

import sqlite3
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from mylife.core.config import get_settings


# --- SQLite transaction correctness -----------------------------------------
# pysqlite emits BEGIN implicitly and COMMITs before DDL, which breaks atomic
# rollback across SAVEPOINTs. The documented SQLAlchemy fix: stop the driver
# from managing transactions and emit BEGIN ourselves. Applied globally so both
# the app (which defaults to SQLite in dev) and tests get atomic transactions.
# No effect on non-SQLite engines.
@event.listens_for(Engine, "connect")
def _sqlite_disable_driver_transactions(dbapi_connection: Any, _record: Any) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.isolation_level = None


@event.listens_for(Engine, "begin")
def _sqlite_emit_begin(conn: Connection) -> None:
    if conn.engine.dialect.name == "sqlite":
        conn.exec_driver_sql("BEGIN")


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
