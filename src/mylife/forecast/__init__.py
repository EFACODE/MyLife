"""Forecast bounded context — transparent, evidence-led decision support (T8).

Projections about the future that must name their assumptions and cite their
evidence, with explicit uncertainty. See ``specs/domain/forecast/``.
"""

from mylife.forecast.contract import (
    Assumption,
    EmptyEvidenceError,
    EmptyForecastError,
    Forecast,
    ForecastDetail,
    ForecastGenerated,
    ForecastPoint,
    ForecastService,
    InvalidIntervalError,
    MissingAssumptionsError,
    UnknownEvidenceError,
    UnknownForecastError,
)
from mylife.forecast.models import (
    CashFlowForecaster,
    ForecastDraft,
    Forecaster,
    ForecastingService,
    GoalCompletionForecaster,
)
from mylife.forecast.scenario import EmptyScenarioError, ScenarioService

__all__ = [
    "Assumption",
    "CashFlowForecaster",
    "EmptyEvidenceError",
    "EmptyForecastError",
    "EmptyScenarioError",
    "Forecast",
    "ForecastDetail",
    "ForecastDraft",
    "ForecastGenerated",
    "ForecastPoint",
    "ForecastService",
    "Forecaster",
    "ForecastingService",
    "GoalCompletionForecaster",
    "InvalidIntervalError",
    "MissingAssumptionsError",
    "ScenarioService",
    "UnknownEvidenceError",
    "UnknownForecastError",
]
