"""Metrics endpoint (T9.1).

Exposes the process's Prometheus metrics for scraping. Unauthenticated by
convention — it carries only aggregate operational data (no user data) and should
be exposed on a protected network in production. See
``specs/domain/platform/metrics.md``.
"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from mylife.core.metrics import CONTENT_TYPE, render_latest

router = APIRouter(tags=["system"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Return the Prometheus text exposition of this process's metrics."""
    return PlainTextResponse(render_latest(), media_type=CONTENT_TYPE)
