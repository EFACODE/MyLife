"""Tests for the distributed trace context + trace-aware logging (T9.3)."""

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mylife.core.context import get_trace_id, set_trace_context
from mylife.core.logging import JsonFormatter
from mylife.core.tracing import (
    TracingMiddleware,
    clear_spans,
    format_traceparent,
    new_span_id,
    new_trace_id,
    parse_traceparent,
    recent_spans,
    span,
)

_VALID = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


def test_ids_have_expected_widths() -> None:
    assert len(new_trace_id()) == 32
    assert len(new_span_id()) == 16


def test_traceparent_round_trip_and_rejection() -> None:
    parsed = parse_traceparent(_VALID)
    assert parsed == ("0af7651916cd43dd8448eb211c80319c", "b7ad6b7169203331")
    trace_id, span_id = parsed
    assert parse_traceparent(format_traceparent(trace_id, span_id)) == parsed
    # Malformed / all-zero are rejected.
    assert parse_traceparent("not-a-header") is None
    assert parse_traceparent("01-" + "0" * 32 + "-" + "0" * 16 + "-01") is None
    assert parse_traceparent("00-" + "0" * 32 + "-b7ad6b7169203331-01") is None
    assert parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-" + "0" * 16 + "-01") is None


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(TracingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str | None]:
        return {"trace_id": get_trace_id()}

    with TestClient(app) as test_client:
        yield test_client


def test_generates_trace_when_absent(client: TestClient) -> None:
    response = client.get("/ping")
    header = response.headers["traceparent"]
    parsed = parse_traceparent(header)
    assert parsed is not None
    # The handler saw the same trace id that is echoed back.
    assert response.json()["trace_id"] == parsed[0]


def test_continues_inbound_trace_with_new_span(client: TestClient) -> None:
    response = client.get("/ping", headers={"traceparent": _VALID})
    trace_id, span_id = parse_traceparent(response.headers["traceparent"])  # type: ignore[misc]
    assert trace_id == "0af7651916cd43dd8448eb211c80319c"  # trace continued
    assert span_id != "b7ad6b7169203331"  # fresh span


def test_malformed_inbound_is_ignored(client: TestClient) -> None:
    response = client.get("/ping", headers={"traceparent": "garbage"})
    parsed = parse_traceparent(response.headers["traceparent"])
    assert parsed is not None  # a fresh trace was generated


def test_logs_carry_trace_ids() -> None:
    tokens = set_trace_context("a" * 32, "b" * 16)
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", None, None)
        rendered = JsonFormatter().format(record)
    finally:
        from mylife.core.context import reset_trace_context

        reset_trace_context(tokens)
    assert '"trace_id": "' + "a" * 32 + '"' in rendered
    assert '"span_id": "' + "b" * 16 + '"' in rendered


def test_span_recorded_into_bounded_buffer() -> None:
    clear_spans()
    tokens = set_trace_context("c" * 32, "d" * 16)
    try:
        with span("work"):
            pass
    finally:
        from mylife.core.context import reset_trace_context

        reset_trace_context(tokens)
    spans = recent_spans()
    assert spans[-1].name == "work"
    assert spans[-1].trace_id == "c" * 32
    assert spans[-1].duration_seconds >= 0.0
