"""Tests for the notifications channels, preferences and service (T4.8)."""

import json
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from types import TracebackType

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import EventStore, InProcessEventBus
from mylife.db.base import Base
from mylife.notifications import (
    NOTIFICATION_DELIVERY_FAILED,
    NOTIFICATION_REQUESTED,
    NOTIFICATION_SENT,
    NotificationChannelError,
    NotificationPreferenceService,
    NotificationService,
    SmtpEmailChannel,
    WhatsAppCloudApiChannel,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
USER = uuid.uuid4()


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


class _FakeSmtp:
    """Records what would have been sent; satisfies the ``smtplib.SMTP`` shape."""

    sent: list[object] = []
    fail = False

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def __enter__(self) -> "_FakeSmtp":
        if self.fail:
            raise OSError("connection refused")
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        pass

    def login(self, username: str, password: str) -> None:
        pass

    def send_message(self, message: object) -> None:
        self.sent.append(message)


def test_smtp_channel_sends_message() -> None:
    _FakeSmtp.sent = []
    _FakeSmtp.fail = False
    channel = SmtpEmailChannel(
        host="smtp.example.com",
        port=587,
        from_address="noreply@example.com",
        smtp_cls=_FakeSmtp,  # type: ignore[arg-type]
    )

    result = channel.send("ada@example.com", "Subject", "Body")

    assert result is None
    assert len(_FakeSmtp.sent) == 1


def test_smtp_channel_wraps_failure() -> None:
    _FakeSmtp.fail = True
    channel = SmtpEmailChannel(
        host="smtp.example.com",
        port=587,
        from_address="noreply@example.com",
        smtp_cls=_FakeSmtp,  # type: ignore[arg-type]
    )
    with pytest.raises(NotificationChannelError):
        channel.send("ada@example.com", "Subject", "Body")
    _FakeSmtp.fail = False


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


def _opener(payload: dict[str, object]) -> object:
    def opener(request: object, timeout: int) -> AbstractContextManager[_FakeResponse]:
        return _FakeResponse(payload)

    return opener


def test_whatsapp_channel_returns_message_id() -> None:
    channel = WhatsAppCloudApiChannel(
        phone_number_id="123",
        access_token="token",
        opener=_opener({"messages": [{"id": "wamid.abc"}]}),  # type: ignore[arg-type]
    )

    result = channel.send("+5511999999999", "ignored", "Body")

    assert result == "wamid.abc"


def test_whatsapp_channel_wraps_failure() -> None:
    def opener(request: object, timeout: int) -> object:
        raise TimeoutError("timed out")

    channel = WhatsAppCloudApiChannel(
        phone_number_id="123",
        access_token="token",
        opener=opener,  # type: ignore[arg-type]
    )
    with pytest.raises(NotificationChannelError):
        channel.send("+5511999999999", "ignored", "Body")


def test_preferences_default_when_unset(session: Session) -> None:
    preference = NotificationPreferenceService(session).get(USER)

    assert preference.email_enabled is True
    assert preference.whatsapp_enabled is False
    assert preference.whatsapp_phone is None


def test_preferences_set_and_get_round_trip(session: Session) -> None:
    service = NotificationPreferenceService(session)
    saved = service.set(
        USER,
        email_enabled=False,
        whatsapp_enabled=True,
        whatsapp_phone=" +5511999999999 ",
        now=NOW,
    )

    assert saved.whatsapp_phone == "+5511999999999"
    fetched = service.get(USER)
    assert fetched.email_enabled is False
    assert fetched.whatsapp_enabled is True


class _RecordingChannel:
    def __init__(self, *, message_id: str | None = "id-1") -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._message_id = message_id

    def send(self, recipient: str, subject: str, body: str) -> str | None:
        self.calls.append((recipient, subject, body))
        return self._message_id


class _FailingChannel:
    def send(self, recipient: str, subject: str, body: str) -> str | None:
        raise NotificationChannelError("provider down")


def test_service_records_requested_and_sent(session: Session) -> None:
    channel = _RecordingChannel()
    service = NotificationService(session, InProcessEventBus(), {"email": channel})

    outcome = service.send(
        USER,
        channel="email",
        template="t",
        subject="Subject",
        body="Body",
        recipient="ada@example.com",
        evidence=[uuid.uuid4()],
        now=NOW,
        correlation_id="c",
    )

    assert outcome.delivered is True
    assert outcome.provider_message_id == "id-1"
    assert channel.calls == [("ada@example.com", "Subject", "Body")]
    events = [e.event_type for e in EventStore(session).read_stream(USER)]
    assert events == [NOTIFICATION_REQUESTED, NOTIFICATION_SENT]


def test_service_records_requested_and_failed(session: Session) -> None:
    service = NotificationService(session, InProcessEventBus(), {"email": _FailingChannel()})

    outcome = service.send(
        USER,
        channel="email",
        template="t",
        subject="Subject",
        body="Body",
        recipient="ada@example.com",
        now=NOW,
        correlation_id="c",
    )

    assert outcome.delivered is False
    assert outcome.reason == "provider down"
    events = [e.event_type for e in EventStore(session).read_stream(USER)]
    assert events == [NOTIFICATION_REQUESTED, NOTIFICATION_DELIVERY_FAILED]


def test_service_records_failure_for_unconfigured_channel(session: Session) -> None:
    service = NotificationService(session, InProcessEventBus(), {})

    outcome = service.send(
        USER,
        channel="whatsapp",
        template="t",
        subject="Subject",
        body="Body",
        recipient="+5511999999999",
        now=NOW,
        correlation_id="c",
    )

    assert outcome.delivered is False
    assert "no whatsapp channel configured" in (outcome.reason or "")
