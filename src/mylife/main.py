"""FastAPI application factory and ASGI entrypoint.

Run locally with::

    uvicorn mylife.main:app --reload
"""

import os

from fastapi import FastAPI

from mylife import __version__
from mylife.api import (
    assistant,
    audit,
    auth,
    briefing,
    consent,
    data_subject,
    finance,
    forecast,
    goals,
    health,
    health_tracking,
    identity,
    insight,
    knowledge,
    knowledge_graph,
    metrics,
    timeline,
)
from mylife.api.spa import SpaStaticFiles
from mylife.core.config import get_settings
from mylife.core.logging import configure_logging
from mylife.core.metrics_middleware import MetricsMiddleware
from mylife.core.middleware import CorrelationIdMiddleware
from mylife.core.tracing import TracingMiddleware


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(identity.router)
    app.include_router(consent.router)
    app.include_router(audit.router)
    app.include_router(data_subject.router)
    app.include_router(timeline.router)
    app.include_router(finance.router)
    app.include_router(health_tracking.router)
    app.include_router(goals.router)
    app.include_router(knowledge.router)
    app.include_router(knowledge_graph.router)
    app.include_router(insight.router)
    app.include_router(forecast.router)
    app.include_router(assistant.router)
    app.include_router(briefing.router)
    # Serve the built SPA same-origin (production) — mounted last so API routes win.
    if settings.static_dir and os.path.isdir(settings.static_dir):
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="spa")
    return app


app = create_app()
