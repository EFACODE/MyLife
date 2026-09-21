"""Bills report — paid, unpaid and overdue due occurrences.

Derives, **read-time**, the due occurrences of a user's bills over a window
and folds ``BillPaid`` events onto them. A bill's due occurrences are never
persisted as events — they are computed deterministically from its
recurrence rule (a monthly due-day, clamped to the month's length, or a fixed
one-off date), the same way :mod:`mylife.finance.net_worth` derives balances
from the finance event stream rather than a projection table. See
``specs/domain/finance/recurring-bills.md`` (T4.7).
"""

import calendar
import uuid
from collections.abc import Iterator
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events.store import _stored_utc
from mylife.finance.bills import BILL_PAID, BillRow
from mylife.timeline.query import TimelineQueryFilter, TimelineQueryService

_UNBOUNDED = 1_000_000


class BillOccurrence(BaseModel):
    """One due occurrence (period) of a bill, with its paid/overdue status."""

    model_config = ConfigDict(frozen=True)

    bill_id: uuid.UUID
    account_id: uuid.UUID
    payee: str
    category: str | None
    currency: str
    amount_minor: int
    period: str
    due_at: datetime
    paid: bool
    paid_at: datetime | None
    overdue: bool


def _month_range(start: datetime, end: datetime) -> Iterator[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _monthly_due_at(year: int, month: int, due_day: int, *, tzinfo: object) -> datetime:
    days_in_month = calendar.monthrange(year, month)[1]
    day = min(due_day, days_in_month)
    return datetime(year, month, day, tzinfo=tzinfo)  # type: ignore[arg-type]


def _periods_for_bill(row: BillRow, due_from: datetime, due_to: datetime) -> list[datetime]:
    """The bill's due occurrences that fall within ``[due_from, due_to]``.

    Deliberately **not** bounded by the bill's own ``created_at`` — a user
    registering a bill today can backfill and pay past periods it covers
    (e.g. logging rent that was already being paid before they started using
    the report). Callers that must not surface pre-registration periods (the
    due-date alert scanner, T4.8) filter those out themselves.
    """
    if row.recurrence == "once":
        if row.due_at is not None:
            due_at = _stored_utc(row.due_at)
            if due_from <= due_at <= due_to:
                return [due_at]
        return []
    if row.recurrence == "monthly" and row.due_day is not None:
        candidates = (
            _monthly_due_at(year, month, row.due_day, tzinfo=due_from.tzinfo)
            for year, month in _month_range(due_from, due_to)
        )
        return [due_at for due_at in candidates if due_from <= due_at <= due_to]
    return []


class BillsReportService:
    """Read-time paid/unpaid/overdue report over a user's bills."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _bills(self, user_id: uuid.UUID, account_id: uuid.UUID | None) -> list[BillRow]:
        stmt = select(BillRow).where(BillRow.user_id == user_id)
        if account_id is not None:
            stmt = stmt.where(BillRow.account_id == account_id)
        return list(self._session.scalars(stmt.order_by(BillRow.created_at)))

    def _payments(self, user_id: uuid.UUID) -> dict[tuple[str, str], datetime]:
        """The latest ``paid_at`` per ``(bill_id, period)`` the user has recorded."""
        page = TimelineQueryService(self._session).query(
            TimelineQueryFilter(user_id=user_id, event_types=(BILL_PAID,), limit=_UNBOUNDED)
        )
        payments: dict[tuple[str, str], datetime] = {}
        for item in page.items:
            key = (str(item.payload["bill_id"]), str(item.payload["period"]))
            paid_at = item.occurred_at
            if key not in payments or paid_at > payments[key]:
                payments[key] = paid_at
        return payments

    def list_occurrences(
        self,
        user_id: uuid.UUID,
        *,
        due_from: datetime,
        due_to: datetime,
        as_of: datetime,
        account_id: uuid.UUID | None = None,
        paid: bool | None = None,
        overdue: bool | None = None,
    ) -> list[BillOccurrence]:
        """Return due occurrences in ``[due_from, due_to]``, optionally filtered."""
        payments = self._payments(user_id)
        occurrences: list[BillOccurrence] = []
        for row in self._bills(user_id, account_id):
            for due_at in _periods_for_bill(row, due_from, due_to):
                period = due_at.date().isoformat()
                paid_at = payments.get((str(row.bill_id), period))
                is_paid = paid_at is not None
                occurrences.append(
                    BillOccurrence(
                        bill_id=row.bill_id,
                        account_id=row.account_id,
                        payee=row.payee,
                        category=row.category,
                        currency=row.currency,
                        amount_minor=row.amount_minor,
                        period=period,
                        due_at=due_at,
                        paid=is_paid,
                        paid_at=paid_at,
                        overdue=(not is_paid) and due_at < as_of,
                    )
                )
        if paid is not None:
            occurrences = [o for o in occurrences if o.paid == paid]
        if overdue is not None:
            occurrences = [o for o in occurrences if o.overdue == overdue]
        occurrences.sort(key=lambda o: o.due_at)
        return occurrences
