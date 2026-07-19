"""Forecast endpoints — the forecast contract (T8.1).

Authenticated, user-scoped recording and reading of forecasts. Every forecast must
name ≥1 assumption and cite non-empty, user-owned evidence, with a well-formed
uncertainty interval on every point (enforced by ``ForecastService``). See
``specs/domain/forecast/forecast-contract.md``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.forecast.contract import (
    Assumption,
    EmptyEvidenceError,
    EmptyForecastError,
    Forecast,
    ForecastDetail,
    ForecastPoint,
    ForecastService,
    InvalidIntervalError,
    MissingAssumptionsError,
    UnknownEvidenceError,
    UnknownForecastError,
)
from mylife.forecast.models import ForecastingService
from mylife.forecast.scenario import EmptyScenarioError, ScenarioService
from mylife.identity import User

router = APIRouter(tags=["forecast"])

_METHOD = "manual-v1"


class ForecastRunRequest(BaseModel):
    """Optional parameters for a forecasting run."""

    horizon_days: int = Field(default=30, ge=1)


class ScenarioRequest(BaseModel):
    """A what-if over a base forecast (must change the scale or an assumption)."""

    scale: float = Field(default=1.0, gt=0.0)
    overrides: list[Assumption] = Field(default_factory=list)
    label: str | None = None


class ForecastRequest(BaseModel):
    """Request to record a forecast (must name assumptions and cite evidence)."""

    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    horizon_days: int = Field(ge=1)
    points: list[ForecastPoint] = Field(min_length=1)
    assumptions: list[Assumption] = Field(min_length=1)
    evidence: list[uuid.UUID] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: str = Field(min_length=1)


@router.post("/forecasts", response_model=Forecast, status_code=201)
def create_forecast(
    request: ForecastRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Forecast:
    """Record a forecast for the authenticated user (assumptions + evidence enforced)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return ForecastService(session, bus).generate(
            current_user.user_id,
            request.metric,
            request.unit,
            request.horizon_days,
            request.points,
            request.assumptions,
            request.evidence,
            request.confidence,
            request.limitations,
            method=_METHOD,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except MissingAssumptionsError as exc:
        raise HTTPException(
            status_code=422, detail="a forecast must name at least one assumption"
        ) from exc
    except EmptyForecastError as exc:
        raise HTTPException(status_code=422, detail="a forecast must project a point") from exc
    except InvalidIntervalError as exc:
        raise HTTPException(
            status_code=422, detail="each point needs lower <= value <= upper"
        ) from exc
    except EmptyEvidenceError as exc:
        raise HTTPException(status_code=422, detail="a forecast must cite evidence") from exc
    except UnknownEvidenceError as exc:
        raise HTTPException(
            status_code=422, detail="evidence must be one of your own events"
        ) from exc


@router.post("/forecasts/run", response_model=list[Forecast], status_code=201)
def run_forecasts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    request: ForecastRunRequest | None = None,
) -> list[Forecast]:
    """Run the governed forecasting models for the user; record + return forecasts."""
    correlation_id = get_correlation_id() or new_correlation_id()
    horizon_days = (request or ForecastRunRequest()).horizon_days
    return ForecastingService(session, bus).run(
        current_user.user_id,
        now=utcnow(),
        correlation_id=correlation_id,
        horizon_days=horizon_days,
    )


@router.get("/forecasts", response_model=list[Forecast])
def list_forecasts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Forecast]:
    """List the authenticated user's forecasts, newest first."""
    return ForecastService(session, bus).list_forecasts(current_user.user_id)


@router.post("/forecasts/{forecast_id}/simulate", response_model=Forecast, status_code=201)
def simulate_forecast(
    forecast_id: uuid.UUID,
    request: ScenarioRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Forecast:
    """Record a what-if scenario over the user's base forecast."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return ScenarioService(session, bus).simulate(
            current_user.user_id,
            forecast_id,
            scale=request.scale,
            overrides=request.overrides,
            label=request.label,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except EmptyScenarioError as exc:
        raise HTTPException(
            status_code=422, detail="a scenario must change the scale or an assumption"
        ) from exc
    except UnknownForecastError as exc:
        raise HTTPException(status_code=404, detail="forecast not found") from exc


@router.get("/forecasts/{forecast_id}", response_model=ForecastDetail)
def get_forecast(
    forecast_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> ForecastDetail:
    """Return a forecast with its resolved evidence events."""
    service = ForecastService(session, bus)
    forecast = service.get(current_user.user_id, forecast_id)
    if forecast is None:
        raise HTTPException(status_code=404, detail="forecast not found")
    evidence_events = service.resolve_evidence(current_user.user_id, forecast_id)
    return ForecastDetail(**forecast.model_dump(), evidence_events=evidence_events)
