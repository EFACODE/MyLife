"""Tests for the Life Event envelope (T1.1).

Covers the acceptance criteria in specs/domain/timeline/event-envelope.md:
required fields, UTC enforcement, defaults, immutability, validation and a
serialization round-trip. Pure unit tests — no DB, no network.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from mylife.core.events import (
    LifeEvent,
    LifeEventRecorded,
    LifeEventRecordedPayload,
)


class _Payload(BaseModel):
    """A trivial payload for exercising the generic envelope directly."""

    value: str


def _make_recorded(**overrides: object) -> LifeEventRecorded:
    kwargs: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "occurred_at": datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        "source": "manual",
        "correlation_id": "corr-1",
        "payload": LifeEventRecordedPayload(title="Morning run", category="health"),
    }
    kwargs.update(overrides)
    return LifeEventRecorded(**kwargs)  # type: ignore[arg-type]


def test_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        LifeEventRecorded(  # type: ignore[call-arg]
            occurred_at=datetime(2026, 7, 18, tzinfo=UTC),
            source="manual",
            correlation_id="corr-1",
            payload=LifeEventRecordedPayload(title="x", category="health"),
        )  # user_id omitted


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_recorded(occurred_at=datetime(2026, 7, 18, 12, 0))  # naive


def test_aware_non_utc_is_normalized_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    event = _make_recorded(occurred_at=datetime(2026, 7, 18, 14, 0, tzinfo=plus_two))

    assert event.occurred_at.utcoffset() == timedelta(0)
    assert event.occurred_at == datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_event_id_defaults_and_is_unique() -> None:
    first = _make_recorded()
    second = _make_recorded()

    assert isinstance(first.event_id, uuid.UUID)
    assert first.event_id != second.event_id


def test_recorded_at_defaults_to_utc_now() -> None:
    before = datetime.now(UTC)
    event = _make_recorded()
    after = datetime.now(UTC)

    assert event.recorded_at.tzinfo is not None
    assert event.recorded_at.utcoffset() == timedelta(0)
    assert before <= event.recorded_at <= after


def test_events_are_immutable() -> None:
    event = _make_recorded()
    with pytest.raises(ValidationError):
        event.source = "tampered"  # type: ignore[misc]


def test_reference_event_type_and_version_are_fixed() -> None:
    event = _make_recorded()
    assert event.event_type == "timeline.life_event_recorded"
    assert event.schema_version == 1

    with pytest.raises(ValidationError):
        _make_recorded(event_type="something.else")
    with pytest.raises(ValidationError):
        _make_recorded(schema_version=2)


def test_envelope_field_validation() -> None:
    base_kwargs: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "event_type": "test.event",
        "occurred_at": datetime(2026, 7, 18, tzinfo=UTC),
        "payload": _Payload(value="x"),
    }

    with pytest.raises(ValidationError):  # schema_version must be >= 1
        LifeEvent[_Payload](**base_kwargs, schema_version=0, source="manual", correlation_id="c")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):  # source must be non-empty
        LifeEvent[_Payload](**base_kwargs, schema_version=1, source="", correlation_id="c")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):  # correlation_id must be non-empty
        LifeEvent[_Payload](**base_kwargs, schema_version=1, source="manual", correlation_id="")  # type: ignore[arg-type]


def test_serialization_round_trip() -> None:
    event = _make_recorded(
        payload=LifeEventRecordedPayload(title="Run", category="health", note="felt good")
    )

    restored = LifeEventRecorded.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.payload.note == "felt good"


def test_wrong_payload_shape_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_recorded(payload=LifeEventRecordedPayload(title="", category="health"))
