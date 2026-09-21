"""Notification delivery channels.

Two stdlib-only channel adapters — SMTP email and the Meta WhatsApp Cloud
API — behind a small ``NotificationChannel`` protocol, plus
``build_channels_from_settings`` which wires the channels a deployment has
credentials for. Neither channel is exercised over the network in tests: both
accept an injectable transport so the request/message building can be tested
without I/O. See ``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import json
import smtplib
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import AbstractContextManager
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

from mylife.core.config import Settings


class _UrlResponse(Protocol):
    """The subset of ``http.client.HTTPResponse`` this channel needs."""

    def read(self) -> bytes: ...


class NotificationChannelError(Exception):
    """Raised when a channel fails to deliver a notification."""


@runtime_checkable
class NotificationChannel(Protocol):
    """A channel capable of delivering a notification to a recipient."""

    def send(self, recipient: str, subject: str, body: str) -> str | None:
        """Deliver the message; return a provider message id, if any."""
        ...


class SmtpEmailChannel:
    """Sends email via SMTP (stdlib ``smtplib``)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_address: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        smtp_cls: Callable[[str, int], smtplib.SMTP] = smtplib.SMTP,
    ) -> None:
        self._host = host
        self._port = port
        self._from_address = from_address
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._smtp_cls = smtp_cls

    def send(self, recipient: str, subject: str, body: str) -> str | None:
        """Send an email; raises :class:`NotificationChannelError` on failure."""
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_address
        message["To"] = recipient
        message.set_content(body)
        try:
            with self._smtp_cls(self._host, self._port) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password or "")
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationChannelError(str(exc)) from exc
        return None


class WhatsAppCloudApiChannel:
    """Sends a text message via the Meta WhatsApp Cloud API (stdlib ``urllib``)."""

    def __init__(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        api_base: str = "https://graph.facebook.com/v19.0",
        opener: Callable[..., AbstractContextManager[_UrlResponse]] = urllib.request.urlopen,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._api_base = api_base
        self._opener = opener

    def send(self, recipient: str, subject: str, body: str) -> str | None:
        """Send a WhatsApp text; raises :class:`NotificationChannelError` on failure."""
        url = f"{self._api_base}/{self._phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": body},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=10) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise NotificationChannelError(str(exc)) from exc
        messages = result.get("messages") or []
        return str(messages[0]["id"]) if messages else None


def build_channels_from_settings(settings: Settings) -> dict[str, NotificationChannel]:
    """Build the channel map for the channels a deployment has credentials for."""
    channels: dict[str, NotificationChannel] = {}
    if settings.smtp_host:
        channels["email"] = SmtpEmailChannel(
            host=settings.smtp_host,
            port=settings.smtp_port,
            from_address=settings.smtp_from_address,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        )
    if settings.whatsapp_phone_number_id and settings.whatsapp_access_token:
        channels["whatsapp"] = WhatsAppCloudApiChannel(
            phone_number_id=settings.whatsapp_phone_number_id,
            access_token=settings.whatsapp_access_token,
        )
    return channels
