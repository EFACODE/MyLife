"""Forecasting models — cash-flow & goal-completion (T8.2).

Governed, rule-based forecasters that project the user's own history into the
future with **plain arithmetic** (moving average / linear trend). Each names its
assumptions and cites the events it used, and lets uncertainty **widen with the
horizon** (no false precision). They build drafts only — ``ForecastService`` (T8.1)
records them, so every projection inherits the contract's guarantees. No LLM, no
numeric library. See ``specs/domain/forecast/forecasting-models.md``.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, InProcessEventBus
from mylife.finance.models import TRANSACTION_TYPES
from mylife.forecast.contract import Assumption, Forecast, ForecastPoint, ForecastService
from mylife.goals import GoalProgressService, GoalsService
from mylife.timeline import TimelineEvent, TimelineQueryFilter, TimelineQueryService

_MAX_EVENTS = 1000
_LOOKBACK_DAYS = 28
_BAND_RATIO = 0.5

_CASH_METHOD: Final = "cash-flow-ma-v1"
_CASH_FLOW_CONFIDENCE: Final = 0.5
_CASH_BAND_FLOOR: Final = 100  # 1.00 in minor units — no zero-width money interval

_GOAL_METHOD: Final = "goal-trend-v1"
_GOAL_CONFIDENCE: Final = 0.4
_GOAL_BAND_FLOOR: Final = 1


class ForecastDraft(BaseModel):
    """The inputs a forecaster hands to ``ForecastService.generate``."""

    model_config = ConfigDict(frozen=True)

    metric: str
    unit: str
    horizon_days: int
    points: list[ForecastPoint]
    assumptions: list[Assumption]
    evidence: list[uuid.UUID]
    confidence: float
    limitations: str
    method: str


@runtime_checkable
class Forecaster(Protocol):
    """A governed forecaster over the user's data (read-only, user-scoped)."""

    name: str

    def draft(
        self, session: Session, user_id: uuid.UUID, *, now: datetime, horizon_days: int
    ) -> list[ForecastDraft]:
        """Return zero or more forecast drafts for ``user_id`` as of ``now``."""
        ...


def _horizon_offsets(horizon_days: int) -> list[int]:
    """Weekly day-offsets up to (and including) the horizon."""
    offsets = list(range(7, horizon_days + 1, 7))
    if not offsets or offsets[-1] != horizon_days:
        offsets.append(horizon_days)
    return offsets


def _point(now: datetime, day: int, value: int, floor: int) -> ForecastPoint:
    """A projected point whose interval widens with the projected magnitude."""
    band = max(round(abs(value) * _BAND_RATIO), floor)
    return ForecastPoint(
        at=now + timedelta(days=day), value=value, lower=value - band, upper=value + band
    )


def _events(
    session: Session,
    user_id: uuid.UUID,
    event_types: tuple[str, ...],
    occurred_from: datetime,
    occurred_to: datetime,
) -> list[TimelineEvent]:
    return (
        TimelineQueryService(session)
        .query(
            TimelineQueryFilter(
                user_id=user_id,
                event_types=event_types,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
                limit=_MAX_EVENTS,
            )
        )
        .items
    )


class CashFlowForecaster:
    """Projects cumulative net cash flow per currency from a moving average."""

    name = "cash-flow"

    def draft(
        self, session: Session, user_id: uuid.UUID, *, now: datetime, horizon_days: int
    ) -> list[ForecastDraft]:
        txns = _events(
            session, user_id, TRANSACTION_TYPES, now - timedelta(days=_LOOKBACK_DAYS), now
        )
        offsets = _horizon_offsets(horizon_days)
        drafts: list[ForecastDraft] = []
        for currency in sorted({str(e.payload.get("currency", "")) for e in txns}):
            net = 0
            evidence: list[uuid.UUID] = []
            for event in txns:
                if str(event.payload.get("currency", "")) != currency:
                    continue
                amount = event.payload.get("amount_minor")
                if isinstance(amount, int):
                    net += amount
                    evidence.append(event.event_id)
            if not evidence:
                continue
            avg_daily = net / _LOOKBACK_DAYS
            points = [_point(now, day, round(avg_daily * day), _CASH_BAND_FLOOR) for day in offsets]
            drafts.append(
                ForecastDraft(
                    metric="cash_flow",
                    unit=f"{currency}_minor",
                    horizon_days=horizon_days,
                    points=points,
                    assumptions=[
                        Assumption(
                            name="net_flow_rate",
                            value=f"{round(avg_daily)} {currency}_minor/day",
                            basis=(
                                f"mean daily net flow over the last {_LOOKBACK_DAYS} days "
                                f"({len(evidence)} transactions)"
                            ),
                        ),
                        Assumption(
                            name="no_structural_change",
                            value="the recent pattern continues",
                            basis="no seasonality, one-offs or trend change is modeled",
                        ),
                    ],
                    evidence=evidence,
                    confidence=_CASH_FLOW_CONFIDENCE,
                    limitations=(
                        "Rule-based projection from recent transactions only; not financial advice."
                    ),
                    method=_CASH_METHOD,
                )
            )
        return drafts


class GoalCompletionForecaster:
    """Projects a goal's metric value from its average accumulation rate."""

    name = "goal-completion"

    def draft(
        self, session: Session, user_id: uuid.UUID, *, now: datetime, horizon_days: int
    ) -> list[ForecastDraft]:
        goals = GoalsService(session, InProcessEventBus()).list_goals(user_id)
        progress_service = GoalProgressService(session)
        offsets = _horizon_offsets(horizon_days)
        drafts: list[ForecastDraft] = []
        for goal in goals:
            progress = progress_service.progress(user_id, goal)
            if (
                progress.source != "metric"
                or progress.achieved
                or progress.current_value <= 0
                or not progress.evidence
            ):
                continue
            elapsed_days = max(1, (now - goal.created_at).days)
            rate = progress.current_value / elapsed_days
            points = [
                _point(now, day, progress.current_value + round(rate * day), _GOAL_BAND_FLOOR)
                for day in offsets
            ]
            drafts.append(
                ForecastDraft(
                    metric="goal_progress",
                    unit=goal.unit,
                    horizon_days=horizon_days,
                    points=points,
                    assumptions=[
                        Assumption(
                            name="accumulation_rate",
                            value=f"{round(rate, 2)} {goal.unit}/day",
                            basis=(
                                f"'{goal.title}': {progress.current_value}/"
                                f"{goal.target_value} {goal.unit} over {elapsed_days} day(s)"
                            ),
                        ),
                        Assumption(
                            name="linear_extrapolation",
                            value="progress continues at the recent average rate",
                            basis="no acceleration or plateau is modeled",
                        ),
                    ],
                    evidence=progress.evidence,
                    confidence=_GOAL_CONFIDENCE,
                    limitations=(
                        f"Rule-based linear projection for goal '{goal.title}' "
                        "from recorded data only."
                    ),
                    method=_GOAL_METHOD,
                )
            )
        return drafts


_DEFAULT_FORECASTERS: list[Forecaster] = [CashFlowForecaster(), GoalCompletionForecaster()]


class ForecastingService:
    """Runs governed forecasters and records their forecasts via the contract."""

    def __init__(
        self, session: Session, bus: EventBus, forecasters: Sequence[Forecaster] | None = None
    ) -> None:
        self._session = session
        self._bus = bus
        self._forecasters = list(forecasters) if forecasters is not None else _DEFAULT_FORECASTERS

    def run(
        self,
        user_id: uuid.UUID,
        *,
        now: datetime,
        correlation_id: str,
        horizon_days: int = 30,
    ) -> list[Forecast]:
        """Build drafts from all forecasters and record each; return the forecasts."""
        service = ForecastService(self._session, self._bus)
        forecasts: list[Forecast] = []
        for forecaster in self._forecasters:
            for draft in forecaster.draft(
                self._session, user_id, now=now, horizon_days=horizon_days
            ):
                forecasts.append(
                    service.generate(
                        user_id,
                        draft.metric,
                        draft.unit,
                        draft.horizon_days,
                        draft.points,
                        draft.assumptions,
                        draft.evidence,
                        draft.confidence,
                        draft.limitations,
                        method=draft.method,
                        now=now,
                        correlation_id=correlation_id,
                    )
                )
        return forecasts
