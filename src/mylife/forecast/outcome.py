"""Feedback / outcome loops (T8.4).

Closes the forecast loop: the user records the **actual observed value** for a past
forecast (an immutable ``ForecastOutcomeRecorded`` event + row), and calibration is
read back — how far the projection was and whether reality landed **inside the
stated uncertainty interval**. That makes forecasts accountable rather than
fire-and-forget. Corrections are new outcomes, never mutations. See
``specs/domain/forecast/outcome-loops.md``.
"""

import logging
import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent
from mylife.core.events.store import _stored_utc
from mylife.db.base import Base
from mylife.forecast.contract import (
    FORECAST_SOURCE,
    Forecast,
    ForecastPoint,
    ForecastService,
    UnknownForecastError,
)

logger = logging.getLogger(__name__)

OUTCOME_RECORDED: Final = "forecast.outcome_recorded"


class OutcomeRow(Base):
    """An observed outcome recorded against a forecast (immutable)."""

    __tablename__ = "forecast_outcomes"

    outcome_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    forecast_id: Mapped[uuid.UUID] = mapped_column(index=True)
    observed_value: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Outcome(BaseModel):
    """An observed outcome as read back."""

    model_config = ConfigDict(frozen=True)

    outcome_id: uuid.UUID
    forecast_id: uuid.UUID
    observed_value: int
    observed_at: datetime
    note: str | None
    recorded_at: datetime


class CalibrationRecord(BaseModel):
    """One outcome compared to its forecast's nearest point."""

    model_config = ConfigDict(frozen=True)

    forecast_id: uuid.UUID
    metric: str
    observed_value: int
    predicted_value: int
    error: int
    within_interval: bool
    observed_at: datetime


class Calibration(BaseModel):
    """How the user's forecasts held up against recorded outcomes."""

    model_config = ConfigDict(frozen=True)

    total: int
    within_interval: int
    hit_rate: float
    mean_abs_error: int
    records: list[CalibrationRecord]


class OutcomeRecordedPayload(BaseModel):
    """The outcome fact — the observation against a forecast."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome_id: uuid.UUID
    forecast_id: uuid.UUID
    observed_value: int
    observed_at: datetime


class ForecastOutcomeRecorded(LifeEvent[OutcomeRecordedPayload]):
    """Emitted when an actual outcome is recorded against a forecast."""

    event_type: Literal["forecast.outcome_recorded"] = OUTCOME_RECORDED
    schema_version: Literal[1] = 1


def _to_outcome(row: OutcomeRow) -> Outcome:
    return Outcome(
        outcome_id=row.outcome_id,
        forecast_id=row.forecast_id,
        observed_value=row.observed_value,
        observed_at=_stored_utc(row.observed_at),
        note=row.note,
        recorded_at=_stored_utc(row.recorded_at),
    )


def _nearest_point(forecast: Forecast, observed_at: datetime) -> ForecastPoint:
    return min(forecast.points, key=lambda p: abs((p.at - observed_at).total_seconds()))


class OutcomeService:
    """Records outcomes against forecasts and reads back calibration."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def record(
        self,
        user_id: uuid.UUID,
        forecast_id: uuid.UUID,
        observed_value: int,
        observed_at: datetime,
        *,
        note: str | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Outcome:
        """Record an actual outcome against one of the user's forecasts."""
        forecast = ForecastService(self._session, self._bus).get(user_id, forecast_id)
        if forecast is None:
            raise UnknownForecastError(forecast_id)

        outcome_id = uuid.uuid4()
        payload = OutcomeRecordedPayload(
            outcome_id=outcome_id,
            forecast_id=forecast_id,
            observed_value=observed_value,
            observed_at=observed_at,
        )
        row = OutcomeRow(
            outcome_id=outcome_id,
            user_id=user_id,
            forecast_id=forecast_id,
            observed_value=observed_value,
            observed_at=observed_at,
            note=note,
            recorded_at=now,
        )
        self._session.add(row)
        event = ForecastOutcomeRecorded(
            user_id=user_id,
            occurred_at=now,
            source=FORECAST_SOURCE,
            correlation_id=correlation_id,
            payload=payload,
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return _to_outcome(row)

    def list_outcomes(self, user_id: uuid.UUID) -> list[Outcome]:
        """Return the user's recorded outcomes, newest first."""
        rows = self._session.scalars(
            select(OutcomeRow)
            .where(OutcomeRow.user_id == user_id)
            .order_by(OutcomeRow.recorded_at.desc())
        )
        return [_to_outcome(row) for row in rows]

    def calibrate(self, user_id: uuid.UUID) -> Calibration:
        """Compare each outcome to its forecast's nearest point and aggregate."""
        service = ForecastService(self._session, self._bus)
        records: list[CalibrationRecord] = []
        for outcome in self.list_outcomes(user_id):
            forecast = service.get(user_id, outcome.forecast_id)
            if forecast is None or not forecast.points:
                continue  # forecast since erased / degenerate
            point = _nearest_point(forecast, outcome.observed_at)
            records.append(
                CalibrationRecord(
                    forecast_id=outcome.forecast_id,
                    metric=forecast.metric,
                    observed_value=outcome.observed_value,
                    predicted_value=point.value,
                    error=outcome.observed_value - point.value,
                    within_interval=point.lower <= outcome.observed_value <= point.upper,
                    observed_at=outcome.observed_at,
                )
            )
        total = len(records)
        within = sum(1 for record in records if record.within_interval)
        hit_rate = round(within / total, 4) if total else 0.0
        mean_abs_error = round(sum(abs(r.error) for r in records) / total) if total else 0
        return Calibration(
            total=total,
            within_interval=within,
            hit_rate=hit_rate,
            mean_abs_error=mean_abs_error,
            records=records,
        )
