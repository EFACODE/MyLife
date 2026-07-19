"""Distributed trace context — dependency-free (T9.3).

A request carries a ``trace_id`` (shared across its work and across service hops
via the W3C ``traceparent`` header) and a per-request ``span_id``, stamped onto
every structured log line so a single import → normalize → insight → forecast flow
is followable end to end. ``span(name)`` records lightweight in-process spans into a
bounded ring buffer for introspection/tests.

No runtime dependency (mirrors the T9.1 metrics registry); the OpenTelemetry SDK +
a collector are the documented production adapter. Ids are random and non-identifying;
span names are developer-supplied and must not carry PII. See
``specs/domain/platform/tracing.md``.
"""

import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mylife.core.context import (
    get_span_id,
    get_trace_id,
    reset_trace_context,
    set_trace_context,
)

TRACEPARENT_HEADER: Final = "traceparent"
_HEX_RE: Final = re.compile(r"^[0-9a-f]+$")
_SPAN_BUFFER_SIZE: Final = 512


def new_trace_id() -> str:
    """Return a fresh 32-hex trace id."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """Return a fresh 16-hex span id."""
    return secrets.token_hex(8)


def parse_traceparent(header: str) -> tuple[str, str] | None:
    """Parse a W3C ``traceparent`` into ``(trace_id, span_id)``, or ``None``."""
    parts = header.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, parent_id, _flags = (part.lower() for part in parts)
    if version != "00":
        return None
    if len(trace_id) != 32 or not _HEX_RE.match(trace_id) or trace_id == "0" * 32:
        return None
    if len(parent_id) != 16 or not _HEX_RE.match(parent_id) or parent_id == "0" * 16:
        return None
    return trace_id, parent_id


def format_traceparent(trace_id: str, span_id: str, *, sampled: bool = True) -> str:
    """Format a W3C ``traceparent`` header value."""
    return f"00-{trace_id}-{span_id}-{'01' if sampled else '00'}"


@dataclass(frozen=True)
class Span:
    """A recorded span (name + timing under the current trace)."""

    name: str
    trace_id: str | None
    span_id: str | None
    duration_seconds: float


_spans: deque[Span] = deque(maxlen=_SPAN_BUFFER_SIZE)
_spans_lock = threading.Lock()


@contextmanager
def span(name: str) -> Iterator[None]:
    """Record a span for ``name`` under the current trace (bounded buffer)."""
    start = time.perf_counter()
    try:
        yield
    finally:
        record = Span(
            name=name,
            trace_id=get_trace_id(),
            span_id=get_span_id(),
            duration_seconds=time.perf_counter() - start,
        )
        with _spans_lock:
            _spans.append(record)


def recent_spans() -> list[Span]:
    """Return the recorded spans (most-recent last)."""
    with _spans_lock:
        return list(_spans)


def clear_spans() -> None:
    """Drop all recorded spans (mainly for tests)."""
    with _spans_lock:
        _spans.clear()


class TracingMiddleware(BaseHTTPMiddleware):
    """Establish a trace context per request and propagate ``traceparent``."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound = request.headers.get(TRACEPARENT_HEADER)
        parsed = parse_traceparent(inbound) if inbound else None
        trace_id = parsed[0] if parsed else new_trace_id()
        span_id = new_span_id()
        tokens = set_trace_context(trace_id, span_id)
        try:
            response = await call_next(request)
        finally:
            reset_trace_context(tokens)
        response.headers[TRACEPARENT_HEADER] = format_traceparent(trace_id, span_id)
        return response
