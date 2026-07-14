"""FastAPI application factory and ASGI entrypoint.

Run locally with::

    uvicorn mylife.main:app --reload
"""

from fastapi import FastAPI

from mylife import __version__
from mylife.api import health
from mylife.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
    )
    app.include_router(health.router)
    return app


app = create_app()
