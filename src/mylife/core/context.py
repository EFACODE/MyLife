"""Request-scoped context.

Holds the correlation ID for the in-flight request in a ``ContextVar`` so any
code (loggers, and later the Life Event envelope's ``correlation_id``) can read
it without threading it through call signatures.
"""

import uuid
from contextvars import ContextVar, Token

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


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


def get_trace_id() -> str | None:
    """Return the current request's trace ID, if one is set."""
    return _trace_id.get()


def get_span_id() -> str | None:
    """Return the current request's span ID, if one is set."""
    return _span_id.get()


def set_trace_context(trace_id: str, span_id: str) -> tuple[Token[str | None], Token[str | None]]:
    """Bind the trace/span IDs for the current context; returns reset tokens."""
    return _trace_id.set(trace_id), _span_id.set(span_id)


def reset_trace_context(tokens: tuple[Token[str | None], Token[str | None]]) -> None:
    """Restore the trace/span IDs to their values before ``tokens`` were set."""
    trace_token, span_token = tokens
    _trace_id.reset(trace_token)
    _span_id.reset(span_token)
