"""Health-check endpoint.

A liveness probe that proves the application shell is wired up end to end. It
carries no business logic and is safe to expose unauthenticated.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from mylife import __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Response payload for the health-check endpoint."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return the application liveness status."""
    return HealthResponse(status="ok", version=__version__)
