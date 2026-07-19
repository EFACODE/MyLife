"""Health CSV connector (T4.5).

Imports wearable / Apple Health export rows into the Health context as
``SleepRecorded`` / ``WorkoutCompleted`` events (T4.4), implementing the T3.4
``Connector`` contract with no new dependency. A ``kind`` column selects the fact
per row. Consent-gated on ``source = "health"`` when run through the connector
runner. See ``specs/domain/health/health-connector.md``.

CSV columns: ``kind`` (``sleep``|``workout``) and ``occurred_at`` (ISO-8601 UTC)
required. Sleep: ``duration_minutes``, ``quality?``. Workout: ``activity``,
``duration_minutes``, ``distance_meters?``, ``energy_kcal?``. ``external_id``
optional.
"""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from mylife.connectors.base import FetchContext, RawPayload
from mylife.core.events import LifeEvent, StoredRawRecord
from mylife.core.events.envelope import ensure_utc
from mylife.health.models import (
    HEALTH_SOURCE,
    SleepPayload,
    SleepRecorded,
    WorkoutCompleted,
    WorkoutPayload,
)

_SLEEP = "sleep"
_WORKOUT = "workout"


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid occurred_at {value!r}") from exc
    return ensure_utc(parsed)


def _parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field} {value!r}") from exc


def _optional_int(value: str | None, field: str) -> int | None:
    if not value:
        return None
    return _parse_int(value, field)


class HealthCsvConnector:
    """Imports sleep and workout rows from a health export CSV."""

    source = HEALTH_SOURCE

    def __init__(self, csv_text: str, *, fetched_at: datetime) -> None:
        self._csv_text = csv_text
        self._fetched_at = ensure_utc(fetched_at)

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        reader = csv.DictReader(io.StringIO(self._csv_text))
        payloads: list[RawPayload] = []
        for row in reader:
            external_id = (row.get("external_id") or "").strip() or None
            content = {
                "kind": (row.get("kind") or "").strip().lower(),
                "occurred_at": (row.get("occurred_at") or "").strip(),
                "duration_minutes": (row.get("duration_minutes") or "").strip(),
                "quality": (row.get("quality") or "").strip() or None,
                "activity": (row.get("activity") or "").strip(),
                "distance_meters": (row.get("distance_meters") or "").strip() or None,
                "energy_kcal": (row.get("energy_kcal") or "").strip() or None,
                "external_id": external_id,
            }
            payloads.append(
                RawPayload(content=content, fetched_at=self._fetched_at, external_id=external_id)
            )
        return payloads

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        kind = content.get("kind")
        occurred_at = _parse_utc(content["occurred_at"]) if content.get("occurred_at") else None
        if occurred_at is None:
            raise ValueError("missing required health field 'occurred_at'")
        if kind == _SLEEP:
            yield self._sleep(raw, content, occurred_at)
        elif kind == _WORKOUT:
            yield self._workout(raw, content, occurred_at)
        else:
            raise ValueError(f"unknown health kind {kind!r}")

    def _sleep(self, raw: StoredRawRecord, content: Any, occurred_at: datetime) -> SleepRecorded:
        if not content.get("duration_minutes"):
            raise ValueError("missing required sleep field 'duration_minutes'")
        return SleepRecorded(
            user_id=raw.user_id,
            occurred_at=occurred_at,
            source=self.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=SleepPayload(
                duration_minutes=_parse_int(content["duration_minutes"], "duration_minutes"),
                quality=content.get("quality"),
            ),
        )

    def _workout(
        self, raw: StoredRawRecord, content: Any, occurred_at: datetime
    ) -> WorkoutCompleted:
        for field in ("activity", "duration_minutes"):
            if not content.get(field):
                raise ValueError(f"missing required workout field {field!r}")
        return WorkoutCompleted(
            user_id=raw.user_id,
            occurred_at=occurred_at,
            source=self.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=WorkoutPayload(
                activity=content["activity"],
                duration_minutes=_parse_int(content["duration_minutes"], "duration_minutes"),
                distance_meters=_optional_int(content.get("distance_meters"), "distance_meters"),
                energy_kcal=_optional_int(content.get("energy_kcal"), "energy_kcal"),
            ),
        )
