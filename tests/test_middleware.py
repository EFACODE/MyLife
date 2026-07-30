"""Tests for the correlation-id middleware and structured logging."""

import json
import logging

from fastapi.testclient import TestClient

from mylife.core.context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from mylife.core.logging import JsonFormatter
from mylife.core.middleware import CORRELATION_ID_HEADER


def test_generates_correlation_id_when_absent(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers.get(CORRELATION_ID_HEADER)


def test_echoes_provided_correlation_id(client: TestClient) -> None:
    response = client.get("/health", headers={CORRELATION_ID_HEADER: "abc-123"})

    assert response.headers[CORRELATION_ID_HEADER] == "abc-123"


def test_correlation_id_does_not_leak_between_requests(client: TestClient) -> None:
    first = client.get("/health", headers={CORRELATION_ID_HEADER: "id-1"})
    second = client.get("/health")

    assert first.headers[CORRELATION_ID_HEADER] == "id-1"
    assert second.headers[CORRELATION_ID_HEADER] != "id-1"
    # Context is reset after each request, so nothing bleeds into the caller.
    assert get_correlation_id() is None


def test_json_formatter_includes_correlation_id() -> None:
    token = set_correlation_id("cid-42")
    try:
        record = logging.LogRecord(
            name="mylife.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_correlation_id(token)

    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["correlation_id"] == "cid-42"
