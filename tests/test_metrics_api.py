"""Tests for the /metrics endpoint + HTTP instrumentation (T9.1)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mylife.core.metrics import REQUESTS_IN_FLIGHT
from mylife.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _series_value(body: str, prefix: str) -> float:
    """Return the value of the sample line starting with ``prefix`` (metrics are
    process-global, so the exact count depends on the whole suite — assert on the
    series' presence and positivity, not a fixed number)."""
    for line in body.splitlines():
        if line.startswith(prefix):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"no sample line starting with {prefix!r}")


def test_metrics_endpoint_exposes_http_metrics(client: TestClient) -> None:
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE http_requests_total counter" in body
    assert "# TYPE http_request_duration_seconds histogram" in body
    assert "# TYPE http_requests_in_flight gauge" in body
    prefix = 'http_requests_total{method="GET",route="/health",status="200"}'
    assert _series_value(body, prefix) >= 1
    # The duration histogram's _count matches the same series.
    count_prefix = 'http_request_duration_seconds_count{method="GET",route="/health",status="200"}'
    assert _series_value(body, count_prefix) >= 1


def test_route_label_uses_template_not_id(client: TestClient) -> None:
    # An unauthenticated hit still matches the route (401 from the auth dependency),
    # so the label must be the template, never the concrete UUID.
    client.get("/forecasts/00000000-0000-0000-0000-000000000000")
    body = client.get("/metrics").text
    assert 'route="/forecasts/{forecast_id}"' in body
    assert "00000000-0000-0000-0000-000000000000" not in body


def test_unmatched_path_collapses_to_constant_label(client: TestClient) -> None:
    client.get("/no-such-route-xyz")
    body = client.get("/metrics").text
    assert 'route="__unmatched__"' in body
    assert "no-such-route-xyz" not in body


def test_in_flight_gauge_is_leak_free(client: TestClient) -> None:
    client.get("/health")
    # No request is in flight once the call has returned.
    assert REQUESTS_IN_FLIGHT.value() == 0.0
