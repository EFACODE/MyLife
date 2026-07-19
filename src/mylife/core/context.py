"""Request-scoped context.

Holds the correlation ID for the in-flight request in a ``ContextVar`` so any
code (loggers, and later the Life Event envelope's ``correlation_id``) can read
it without threading it through call signatures.
"""

import uuid
from contextvars import ContextVar, Token

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    """Return a fresh correlation ID."""
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Return the current request's correlation ID, if one is set."""
    return _correlation_id.get()


def set_correlation_id(value: str) -> Token[str | None]:
    """Bind ``value`` as the current correlation ID; returns a reset token."""
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    """Restore the correlation ID to its value before ``token`` was set."""
    _correlation_id.reset(token)
