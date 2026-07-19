"""The forecast contract — ``ForecastGenerated`` (T8.1).

The Phase 5 analog of the AI evidence contract (`T7.1`): a forecast is a
**structured projection that must name its assumptions and cite its evidence**, and
must carry an explicit **uncertainty interval** on every point. ``ForecastService``
refuses to record a forecast with no assumptions, no (or foreign) evidence, or a
malformed interval, so *transparent decision support* holds for every caller (the
manual API now, the forecasting models later). Rule-based — no LLM, no numeric
library here. See ``specs/domain/forecast/forecast-contract.md``.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Float, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events import EventBus, EventDispatchError, EventStore, LifeEvent, StoredEvent
from mylife.core.events.store import EventRow, _stored_utc, _to_stored
from mylife.db.base import Base

logger = logging.getLogger(__name__)

FORECAST_SOURCE = "forecast"
FORECAST_GENERATED: Final = "forecast.forecast_generated"
_UNBOUNDED = 1_000_000


class MissingAssumptionsError(Exception):
    """Raised when a forecast names no assumptions — the contract forbids it."""


class EmptyForecastError(Exception):
    """Raised when a forecast has no projected points."""


class InvalidIntervalError(Exception):
    """Raised when a point's interval is malformed (not ``lower <= value <= upper``)."""

    def __init__(self, at: datetime) -> None:
        super().__init__(f"forecast point at {at.isoformat()} has a malformed interval")
        self.at = at


class EmptyEvidenceError(Exception):
    """Raised when a forecast cites no evidence — the contract forbids it."""


class UnknownEvidenceError(Exception):
    """Raised when an evidence id is not one of the user's events."""

    def __init__(self, event_id: uuid.UUID) -> None:
        super().__init__(f"evidence {event_id} is not one of the user's events")
        self.event_id = event_id


class UnknownForecastError(Exception):
    """Raised when a forecast is missing or not owned by the acting user."""

    def __init__(self, forecast_id: uuid.UUID) -> None:
        super().__init__(f"forecast {forecast_id} not found")
        self.forecast_id = forecast_id


class ForecastRow(Base):
    """A recorded forecast (derived; evidence stored by reference)."""

    __tablename__ = "forecasts"

    forecast_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    metric: Mapped[str] = mapped_column(String)
    unit: Mapped[str] = mapped_column(String)
    horizon_days: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    limitations: Mapped[str] = mapped_column(String)
    points: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    assumptions: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    evidence: Mapped[list[str]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Assumption(BaseModel):
    """A named, auditable statement of what a forecast assumed and why."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: str
    basis: str


class ForecastPoint(BaseModel):
    """A projected value with its explicit uncertainty interval (integer units)."""

    model_config = ConfigDict(frozen=True)

    at: datetime
    value: int
    lower: int
    upper: int


class Forecast(BaseModel):
    """A forecast as read back — a projection with its assumptions and evidence."""

    model_config = ConfigDict(frozen=True)

    forecast_id: uuid.UUID
    metric: str
    unit: str
    horizon_days: int
    points: list[ForecastPoint]
    assumptions: list[Assumption]
    confidence: float
    limitations: str
    method: str
    evidence: list[uuid.UUID]
    generated_at: datetime


class ForecastDetail(Forecast):
    """A forecast plus its resolved evidence events."""

    evidence_events: list[StoredEvent]


class ForecastGeneratedPayload(BaseModel):
    """The forecast fact — projection metadata + evidence references (not copied data)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    forecast_id: uuid.UUID
    metric: str
    method: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[uuid.UUID]


class ForecastGenerated(LifeEvent[ForecastGeneratedPayload]):
    """Emitted when a forecast is generated (Forecast context)."""

    event_type: Literal["forecast.forecast_generated"] = FORECAST_GENERATED
    schema_version: Literal[1] = 1


def _to_forecast(row: ForecastRow) -> Forecast:
    return Forecast(
        forecast_id=row.forecast_id,
        metric=row.metric,
        unit=row.unit,
        horizon_days=row.horizon_days,
        points=[
            ForecastPoint(
                at=_stored_utc(datetime.fromisoformat(str(point["at"]))),
                value=int(point["value"]),  # type: ignore[call-overload]
                lower=int(point["lower"]),  # type: ignore[call-overload]
                upper=int(point["upper"]),  # type: ignore[call-overload]
            )
            for point in row.points
        ],
        assumptions=[Assumption(**assumption) for assumption in row.assumptions],
        confidence=row.confidence,
        limitations=row.limitations,
        method=row.method,
        evidence=[uuid.UUID(value) for value in row.evidence],
        generated_at=_stored_utc(row.generated_at),
    )


class ForecastService:
    """Records and reads forecasts, enforcing the assumptions/evidence contract."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def generate(
        self,
        user_id: uuid.UUID,
        metric: str,
        unit: str,
        horizon_days: int,
        points: Sequence[ForecastPoint],
        assumptions: Sequence[Assumption],
        evidence: Sequence[uuid.UUID],
        confidence: float,
        limitations: str,
        *,
        method: str,
        now: datetime,
        correlation_id: str,
    ) -> Forecast:
        """Record a ``ForecastGenerated`` — rejecting untraceable projections.

        Every forecast must name at least one assumption, project at least one
        point with a well-formed interval, and cite non-empty evidence that is all
        the user's own — so a projection is always assumption-transparent and
        traceable to the user's data.
        """
        if not assumptions:
            raise MissingAssumptionsError("a forecast must name at least one assumption")
        if not points:
            raise EmptyForecastError("a forecast must project at least one point")
        for point in points:
            if not point.lower <= point.value <= point.upper:
                raise InvalidIntervalError(point.at)
        if not evidence:
            raise EmptyEvidenceError("a forecast must cite at least one evidence event")
        owned = {
            stored.event_id
            for stored in EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
        }
        for event_id in evidence:
            if event_id not in owned:
                raise UnknownEvidenceError(event_id)

        forecast_id = uuid.uuid4()
        payload = ForecastGeneratedPayload(
            forecast_id=forecast_id,
            metric=metric,
            method=method,
            confidence=confidence,
            evidence=list(evidence),
        )
        row = ForecastRow(
            forecast_id=forecast_id,
            user_id=user_id,
            metric=metric,
            unit=unit,
            horizon_days=horizon_days,
            method=method,
            confidence=confidence,
            limitations=limitations,
            points=[
                {
                    "at": point.at.isoformat(),
                    "value": point.value,
                    "lower": point.lower,
                    "upper": point.upper,
                }
                for point in points
            ],
            assumptions=[assumption.model_dump() for assumption in assumptions],
            evidence=[str(event_id) for event_id in evidence],
            generated_at=now,
        )
        self._session.add(row)
        event = ForecastGenerated(
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
        return _to_forecast(row)

    def get(self, user_id: uuid.UUID, forecast_id: uuid.UUID) -> Forecast | None:
        """Return the user's forecast, or ``None`` if missing/not theirs."""
        row = self._require_forecast(user_id, forecast_id, raising=False)
        return _to_forecast(row) if row is not None else None

    def list_forecasts(self, user_id: uuid.UUID) -> list[Forecast]:
        """Return the user's forecasts, newest first."""
        rows = self._session.scalars(
            select(ForecastRow)
            .where(ForecastRow.user_id == user_id)
            .order_by(ForecastRow.generated_at.desc())
        )
        return [_to_forecast(row) for row in rows]

    def resolve_evidence(self, user_id: uuid.UUID, forecast_id: uuid.UUID) -> list[StoredEvent]:
        """Return the (surviving) events a forecast cites, user-scoped."""
        row = self._require_forecast(user_id, forecast_id)
        assert row is not None
        ids = [uuid.UUID(value) for value in row.evidence]
        if not ids:
            return []
        rows = self._session.scalars(
            select(EventRow).where(EventRow.user_id == user_id, EventRow.event_id.in_(ids))
        )
        return [_to_stored(event_row) for event_row in rows]

    def _require_forecast(
        self, user_id: uuid.UUID, forecast_id: uuid.UUID, *, raising: bool = True
    ) -> ForecastRow | None:
        row = self._session.scalars(
            select(ForecastRow).where(
                ForecastRow.forecast_id == forecast_id, ForecastRow.user_id == user_id
            )
        ).one_or_none()
        if row is None and raising:
            raise UnknownForecastError(forecast_id)
        return row
