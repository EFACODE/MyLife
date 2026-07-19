"""HTTP middleware.

:class:`CorrelationIdMiddleware` gives every request a correlation ID — reusing
an inbound ``X-Correlation-ID`` header when present, otherwise generating one —
binds it to the request context for the duration of the request, and echoes it
back on the response so clients can correlate their calls with server logs.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mylife.core.context import (
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a correlation ID to each request and echo it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or new_correlation_id()
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
