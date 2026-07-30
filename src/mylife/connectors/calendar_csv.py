"""Calendar CSV connector (T3.5).

The first concrete connector: imports calendar events from a CSV file into the
timeline, implementing the T3.4 ``Connector`` contract with no new dependency.
See ``specs/domain/timeline/calendar-connector.md``.

CSV columns: ``title``, ``category``, ``occurred_at`` (ISO-8601 UTC) required;
``external_id``, ``description`` optional.
"""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from mylife.connectors.base import FetchContext, RawPayload
from mylife.core.events import (
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
    StoredRawRecord,
)
from mylife.core.events.envelope import ensure_utc

CALENDAR_SOURCE = "calendar"
_REQUIRED_FIELDS = ("title", "category", "occurred_at")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid occurred_at {value!r}") from exc
    return ensure_utc(parsed)


class CalendarCsvConnector:
    """Imports calendar events from CSV text."""

    source = CALENDAR_SOURCE

    def __init__(self, csv_text: str, *, fetched_at: datetime) -> None:
        self._csv_text = csv_text
        self._fetched_at = ensure_utc(fetched_at)

    def fetch(self, context: FetchContext) -> Iterable[RawPayload]:
        reader = csv.DictReader(io.StringIO(self._csv_text))
        payloads: list[RawPayload] = []
        for row in reader:
            external_id = (row.get("external_id") or "").strip() or None
            content = {
                "title": (row.get("title") or "").strip(),
                "category": (row.get("category") or "").strip(),
                "occurred_at": (row.get("occurred_at") or "").strip(),
                "description": (row.get("description") or "").strip() or None,
                "external_id": external_id,
            }
            payloads.append(
                RawPayload(content=content, fetched_at=self._fetched_at, external_id=external_id)
            )
        return payloads

    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]:
        content: Any = raw.content
        for field in _REQUIRED_FIELDS:
            if not content.get(field):
                raise ValueError(f"missing required calendar field {field!r}")
        occurred_at = _parse_utc(content["occurred_at"])
        yield LifeEventRecorded(
            user_id=raw.user_id,
            occurred_at=occurred_at,
            source=self.source,
            correlation_id=raw.correlation_id,
            raw_record_id=raw.raw_record_id,
            payload=LifeEventRecordedPayload(
                title=content["title"],
                category=content["category"],
                note=content.get("description"),
            ),
        )
