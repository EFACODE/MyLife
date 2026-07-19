"""HTTP metrics middleware (T9.1).

Records ``http_requests_total``, ``http_request_duration_seconds`` and
``http_requests_in_flight`` for every request, labelled by method, the matched
**route template** (never the concrete path — so per-id URLs collapse to one
series and no id/PII leaks into a label) and status. See
``specs/domain/platform/metrics.md``.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mylife.core.metrics import REQUEST_DURATION, REQUESTS_IN_FLIGHT, REQUESTS_TOTAL

_UNMATCHED = "__unmatched__"


def _route_template(request: Request) -> str:
    """The matched route's path template, or a constant for unmatched paths."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else _UNMATCHED


class MetricsMiddleware(BaseHTTPMiddleware):
    """Instrument each request with count, latency and in-flight metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        REQUESTS_IN_FLIGHT.inc()
        start = time.perf_counter()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            duration = time.perf_counter() - start
            route = _route_template(request)
            REQUESTS_IN_FLIGHT.dec()
            labels = {"method": request.method, "route": route, "status": status}
            REQUEST_DURATION.labels(**labels).observe(duration)
            REQUESTS_TOTAL.labels(**labels).inc()
