"""Bill due-date alerts.

Scans a user's unpaid bill occurrences (via :class:`BillsReportService`,
read-time, same as the report endpoint) for ones due soon or overdue, and
sends a reminder through the user's enabled notification channels
(:mod:`mylife.notifications`). No new event type is needed for "due soon" or
"overdue" — they are read-time facts derived from the same recurrence rule as
the report; each reminder's evidence links back to the bill's
``BillRegistered`` event. See ``specs/domain/finance/bill-alerts.md`` (T4.8).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus
from mylife.core.events.store import _stored_utc
from mylife.finance.bills import BILL_REGISTERED, BillRow
from mylife.finance.bills_report import BillOccurrence, BillsReportService
from mylife.identity.service import IdentityService
from mylife.notifications import NotificationChannel, NotificationOutcome, NotificationService
from mylife.notifications.preferences import NotificationPreferenceService
from mylife.timeline.query import TimelineQueryFilter, TimelineQueryService

_LOOKBACK = timedelta(days=90)
_UPCOMING_DAYS = (3, 1, 0)
_UNBOUNDED = 1_000_000
_TEMPLATE = "bill_reminder"

Reason = Literal["due_soon", "overdue"]


class BillAlert(BaseModel):
    """A due occurrence that warrants a reminder."""

    model_config = ConfigDict(frozen=True)

    bill_id: uuid.UUID
    account_id: uuid.UUID
    payee: str
    currency: str
    amount_minor: int
    due_at: datetime
    reason: Reason
    evidence: list[uuid.UUID]


def _bill_registered_events(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    page = TimelineQueryService(session).query(
        TimelineQueryFilter(user_id=user_id, event_types=(BILL_REGISTERED,), limit=_UNBOUNDED)
    )
    return {uuid.UUID(str(item.payload["bill_id"])): item.event_id for item in page.items}


def _bill_created_at(session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
    rows = session.scalars(select(BillRow).where(BillRow.user_id == user_id))
    return {row.bill_id: _stored_utc(row.created_at) for row in rows}


def _money(currency: str, minor: int) -> str:
    return f"{currency} {minor / 100:,.2f}"


def _render(alert: BillAlert) -> tuple[str, str]:
    amount = _money(alert.currency, alert.amount_minor)
    when = alert.due_at.strftime("%d/%m/%Y")
    if alert.reason == "overdue":
        return (
            f"Conta vencida: {alert.payee}",
            f"A conta '{alert.payee}' no valor de {amount} venceu em {when} e ainda não foi paga.",
        )
    return (
        f"Conta a vencer: {alert.payee}",
        f"A conta '{alert.payee}' no valor de {amount} vence em {when}.",
    )


class BillAlertScanner:
    """Finds a user's due-soon/overdue, unpaid bill occurrences."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def scan(self, user_id: uuid.UUID, *, now: datetime) -> list[BillAlert]:
        """Return at most one alert per bill: its most relevant unpaid occurrence.

        A recurring bill can have several unpaid occurrences in the lookback
        window (e.g. unpaid for three months); this reports only the most
        recent overdue one (or, absent any overdue occurrence, the next
        due-soon one) so a bill nags once per scan, not once per missed
        period.
        """
        occurrences = BillsReportService(self._session).list_occurrences(
            user_id,
            due_from=now - _LOOKBACK,
            due_to=now + timedelta(days=max(_UPCOMING_DAYS)),
            as_of=now,
            paid=False,
        )
        created_at = _bill_created_at(self._session, user_id)
        by_bill: dict[uuid.UUID, list[BillOccurrence]] = {}
        for occurrence in occurrences:
            # A bill can't be overdue for a period that predates its own
            # registration (unlike the general report, which allows
            # backfilling past periods for record-keeping).
            registered_at = created_at.get(occurrence.bill_id)
            if registered_at is not None and occurrence.due_at < registered_at:
                continue
            by_bill.setdefault(occurrence.bill_id, []).append(occurrence)

        registrations = _bill_registered_events(self._session, user_id)
        alerts: list[BillAlert] = []
        for bill_id, bill_occurrences in by_bill.items():
            bill_occurrences.sort(key=lambda o: o.due_at)
            overdue = [o for o in bill_occurrences if o.overdue]
            if overdue:
                chosen, reason = overdue[-1], "overdue"
            else:
                due_soon = [
                    o
                    for o in bill_occurrences
                    if (o.due_at.date() - now.date()).days in _UPCOMING_DAYS
                ]
                if not due_soon:
                    continue
                chosen, reason = due_soon[0], "due_soon"
            registered_event_id = registrations.get(bill_id)
            evidence = [registered_event_id] if registered_event_id is not None else []
            alerts.append(
                BillAlert(
                    bill_id=chosen.bill_id,
                    account_id=chosen.account_id,
                    payee=chosen.payee,
                    currency=chosen.currency,
                    amount_minor=chosen.amount_minor,
                    due_at=chosen.due_at,
                    reason=reason,
                    evidence=evidence,
                )
            )
        return alerts


class BillAlertsService:
    """Scans a user's bills and sends reminders through their enabled channels."""

    def __init__(
        self,
        session: Session,
        bus: EventBus,
        channels: Mapping[str, NotificationChannel],
    ) -> None:
        self._session = session
        self._notifications = NotificationService(session, bus, channels)
        self._identity = IdentityService(session, bus)
        self._preferences = NotificationPreferenceService(session)

    def run(
        self, user_id: uuid.UUID, *, now: datetime, correlation_id: str
    ) -> list[NotificationOutcome]:
        """Scan the user's bills and send a reminder per due-soon/overdue occurrence."""
        alerts = BillAlertScanner(self._session).scan(user_id, now=now)
        if not alerts:
            return []
        user = self._identity.get_user(user_id)
        if user is None:
            return []
        preference = self._preferences.get(user_id)

        outcomes: list[NotificationOutcome] = []
        for alert in alerts:
            subject, body = _render(alert)
            if preference.email_enabled:
                outcomes.append(
                    self._notifications.send(
                        user_id,
                        channel="email",
                        template=_TEMPLATE,
                        subject=subject,
                        body=body,
                        recipient=user.email,
                        evidence=alert.evidence,
                        now=now,
                        correlation_id=correlation_id,
                    )
                )
            if preference.whatsapp_enabled and preference.whatsapp_phone:
                outcomes.append(
                    self._notifications.send(
                        user_id,
                        channel="whatsapp",
                        template=_TEMPLATE,
                        subject=subject,
                        body=body,
                        recipient=preference.whatsapp_phone,
                        evidence=alert.evidence,
                        now=now,
                        correlation_id=correlation_id,
                    )
                )
        return outcomes
