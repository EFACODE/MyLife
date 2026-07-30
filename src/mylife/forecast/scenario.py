"""What-if scenario simulation (T8.3).

Takes an existing forecast as its base, applies **named assumption overrides** and
a scaling factor, and records the result as a new ``Forecast``. A hypothetical is
less certain than its base, so the simulation **widens the relative uncertainty**
and **discounts confidence** — a what-if never reads as firmer than the forecast it
came from. A scenario is just another forecast (same contract, same evidence). No
LLM — plain, transparent arithmetic. See
``specs/domain/forecast/scenario-simulation.md``.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from mylife.core.events import EventBus
from mylife.forecast.contract import (
    Assumption,
    Forecast,
    ForecastPoint,
    ForecastService,
    UnknownForecastError,
)

_SCENARIO_METHOD: Final = "scenario-v1"
_WIDEN: Final = 1.5
_CONFIDENCE_DISCOUNT: Final = 0.8
_BAND_FLOOR: Final = 1


class EmptyScenarioError(Exception):
    """Raised when a scenario changes nothing (scale == 1.0 and no overrides)."""


def _merge_assumptions(
    base: Sequence[Assumption], overrides: Sequence[Assumption]
) -> list[Assumption]:
    """Replace base assumptions by name with overrides; append new-named overrides."""
    by_name = {override.name: override for override in overrides}
    merged = [by_name.pop(assumption.name, assumption) for assumption in base]
    merged.extend(by_name.values())
    return merged


def _scale_point(point: ForecastPoint, scale: float) -> ForecastPoint:
    value = round(point.value * scale)
    base_half = max(point.upper - point.value, point.value - point.lower)
    band = max(round(base_half * scale * _WIDEN), _BAND_FLOOR)
    return ForecastPoint(at=point.at, value=value, lower=value - band, upper=value + band)


class ScenarioService:
    """Simulates a what-if over a base forecast, recording it via the contract."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def simulate(
        self,
        user_id: uuid.UUID,
        forecast_id: uuid.UUID,
        *,
        scale: float = 1.0,
        overrides: Sequence[Assumption] = (),
        label: str | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Forecast:
        """Record a scenario forecast over the user's base forecast.

        The projection is scaled by ``scale`` with widened intervals and discounted
        confidence, and the named ``overrides`` are merged into the assumptions so
        every change is explicit. A scenario that changes nothing is refused.
        """
        if scale == 1.0 and not overrides:
            raise EmptyScenarioError("a scenario must change the scale or an assumption")
        base = ForecastService(self._session, self._bus).get(user_id, forecast_id)
        if base is None:
            raise UnknownForecastError(forecast_id)

        points = [_scale_point(point, scale) for point in base.points]
        assumptions = _merge_assumptions(base.assumptions, overrides)
        assumptions.append(
            Assumption(
                name="scenario",
                value=label or f"scaled ×{scale}",
                basis=f"what-if over base forecast {base.forecast_id}",
            )
        )
        confidence = round(base.confidence * _CONFIDENCE_DISCOUNT, 4)
        limitations = (
            f"Hypothetical scenario (not a prediction) over base forecast "
            f"{base.forecast_id}. {base.limitations}"
        )
        return ForecastService(self._session, self._bus).generate(
            user_id,
            base.metric,
            base.unit,
            base.horizon_days,
            points,
            assumptions,
            base.evidence,
            confidence,
            limitations,
            method=_SCENARIO_METHOD,
            now=now,
            correlation_id=correlation_id,
        )
