"""Health-check endpoints.

Liveness (``/health``) proves the application shell is wired up; readiness
(``/health/ready``, T9.2) additionally proves the database dependency is
reachable. Both carry no business logic and are safe to expose unauthenticated.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from mylife import __version__
from mylife.db.base import get_session

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Response payload for the health-check endpoints."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return the application liveness status (independent of dependencies)."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/health/ready", response_model=HealthResponse)
def readiness(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    """Return readiness — 200 when the database answers, 503 otherwise."""
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means not ready
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return HealthResponse(status="ready", version=__version__)
