"""Bills service.

Registers, cancels and records payments against recurring/one-off bills.
Registering a bill writes a ``bills`` registry row and emits
``BillRegistered``; cancelling emits ``BillCancelled`` and flips the row's
``active`` flag; paying a due occurrence emits ``BillPaid`` (commit-before-
publish, like the rest of the platform). Payments are read back from the
event store — see :mod:`mylife.finance.bills_report` for the derived
paid/unpaid/overdue view. All operations are user-scoped. See
``specs/domain/finance/recurring-bills.md`` (T4.7).
"""

import logging
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore
from mylife.core.events.store import _stored_utc
from mylife.finance.bills import (
    BILLS_SOURCE,
    Bill,
    BillCancelled,
    BillCancelledPayload,
    BillPaid,
    BillPaidPayload,
    BillRegistered,
    BillRegisteredPayload,
    BillRow,
    BillUpdated,
    BillUpdatedPayload,
    Recurrence,
)
from mylife.finance.models import AccountRow
from mylife.finance.service import UnknownAccountError

logger = logging.getLogger(__name__)


class UnknownBillError(Exception):
    """Raised when a bill is missing or not owned by the acting user."""

    def __init__(self, bill_id: uuid.UUID) -> None:
        super().__init__(f"bill {bill_id} not found")
        self.bill_id = bill_id


class InvalidBillRecurrenceError(Exception):
    """Raised when a bill's recurrence rule is inconsistent.

    A ``"monthly"`` bill needs a ``due_day`` (1-31); a ``"once"`` bill needs a
    fixed ``due_at``.
    """


class BillPayment(BaseModel):
    """A payment recorded against one due occurrence of a bill."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    bill_id: uuid.UUID
    period: str
    due_at: datetime
    amount_minor: int
    paid_at: datetime
    transaction_id: uuid.UUID | None


def _to_bill(row: BillRow) -> Bill:
    return Bill(
        bill_id=row.bill_id,
        account_id=row.account_id,
        payee=row.payee,
        amount_minor=row.amount_minor,
        currency=row.currency,
        category=row.category,
        recurrence=row.recurrence,
        due_day=row.due_day,
        due_at=_stored_utc(row.due_at) if row.due_at is not None else None,
        max_occurrences=row.max_occurrences,
        occurrence_anchor_year=row.occurrence_anchor_year,
        occurrence_anchor_month=row.occurrence_anchor_month,
        active=row.active,
        created_at=_stored_utc(row.created_at),
    )


class BillsService:
    """Registers bills and records cancellations/payments for a user."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def register_bill(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        payee: str,
        amount_minor: int,
        currency: str,
        *,
        recurrence: Recurrence,
        category: str | None = None,
        due_day: int | None = None,
        due_at: datetime | None = None,
        max_occurrences: int = 0,
        occurrence_anchor_year: int | None = None,
        occurrence_anchor_month: int | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Bill:
        """Register a bill and emit ``BillRegistered``.

        ``max_occurrences`` caps how many due occurrences a monthly bill
        generates; ``0`` means unlimited (the default — most bills recur
        indefinitely). The cap is counted from ``occurrence_anchor_year``/
        ``occurrence_anchor_month`` as occurrence 1 — this defaults to the
        registration month (``now``) but can be set explicitly, since a bill
        registered today may model an obligation that actually started (or
        will start) in a different month.
        """
        self._require_account(user_id, account_id)
        if recurrence == "monthly" and due_day is None:
            raise InvalidBillRecurrenceError("a monthly bill needs a due_day (1-31)")
        if recurrence == "once" and due_at is None:
            raise InvalidBillRecurrenceError("a one-off bill needs a due_at")

        resolved_anchor_year = (
            occurrence_anchor_year if occurrence_anchor_year is not None else now.year
        )
        resolved_anchor_month = (
            occurrence_anchor_month if occurrence_anchor_month is not None else now.month
        )
        bill_id = uuid.uuid4()
        normalized_currency = currency.strip().upper()
        row = BillRow(
            bill_id=bill_id,
            user_id=user_id,
            account_id=account_id,
            payee=payee.strip(),
            amount_minor=abs(amount_minor),
            currency=normalized_currency,
            category=category,
            recurrence=recurrence,
            due_day=due_day,
            due_at=due_at,
            max_occurrences=max_occurrences,
            occurrence_anchor_year=resolved_anchor_year,
            occurrence_anchor_month=resolved_anchor_month,
            active=True,
            created_at=now,
        )
        self._session.add(row)
        event = BillRegistered(
            user_id=user_id,
            occurred_at=now,
            source=BILLS_SOURCE,
            correlation_id=correlation_id,
            payload=BillRegisteredPayload(
                bill_id=bill_id,
                account_id=account_id,
                payee=row.payee,
                amount_minor=row.amount_minor,
                currency=normalized_currency,
                category=category,
                recurrence=recurrence,
                due_day=due_day,
                due_at=due_at,
                max_occurrences=max_occurrences,
                occurrence_anchor_year=resolved_anchor_year,
                occurrence_anchor_month=resolved_anchor_month,
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return _to_bill(row)

    def update_bill(
        self,
        user_id: uuid.UUID,
        bill_id: uuid.UUID,
        payee: str,
        amount_minor: int,
        currency: str,
        *,
        recurrence: Recurrence,
        category: str | None = None,
        due_day: int | None = None,
        due_at: datetime | None = None,
        max_occurrences: int = 0,
        occurrence_anchor_year: int | None = None,
        occurrence_anchor_month: int | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Bill:
        """Edit a bill's fields and emit ``BillUpdated`` (a correction, not a mutation).

        As with :meth:`register_bill`, an unset occurrence anchor defaults to
        the bill's existing anchor (left unchanged), not the edit's ``now``.
        """
        row = self._require_bill(user_id, bill_id)
        assert row is not None  # _require_bill raises otherwise
        if recurrence == "monthly" and due_day is None:
            raise InvalidBillRecurrenceError("a monthly bill needs a due_day (1-31)")
        if recurrence == "once" and due_at is None:
            raise InvalidBillRecurrenceError("a one-off bill needs a due_at")

        resolved_anchor_year = (
            occurrence_anchor_year
            if occurrence_anchor_year is not None
            else row.occurrence_anchor_year
        )
        resolved_anchor_month = (
            occurrence_anchor_month
            if occurrence_anchor_month is not None
            else row.occurrence_anchor_month
        )
        normalized_currency = currency.strip().upper()
        row.payee = payee.strip()
        row.amount_minor = abs(amount_minor)
        row.currency = normalized_currency
        row.category = category
        row.recurrence = recurrence
        row.due_day = due_day
        row.due_at = due_at
        row.max_occurrences = max_occurrences
        row.occurrence_anchor_year = resolved_anchor_year
        row.occurrence_anchor_month = resolved_anchor_month
        event = BillUpdated(
            user_id=user_id,
            occurred_at=now,
            source=BILLS_SOURCE,
            correlation_id=correlation_id,
            payload=BillUpdatedPayload(
                bill_id=bill_id,
                payee=row.payee,
                amount_minor=row.amount_minor,
                currency=normalized_currency,
                category=category,
                recurrence=recurrence,
                due_day=due_day,
                due_at=due_at,
                max_occurrences=max_occurrences,
                occurrence_anchor_year=resolved_anchor_year,
                occurrence_anchor_month=resolved_anchor_month,
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return _to_bill(row)

    def get_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill | None:
        """Return the user's bill, or ``None`` if missing/not theirs."""
        row = self._require_bill(user_id, bill_id, raising=False)
        return _to_bill(row) if row is not None else None

    def list_bills(self, user_id: uuid.UUID, *, account_id: uuid.UUID | None = None) -> list[Bill]:
        """Return all of a user's bills, ordered by creation time."""
        stmt = select(BillRow).where(BillRow.user_id == user_id)
        if account_id is not None:
            stmt = stmt.where(BillRow.account_id == account_id)
        rows = self._session.scalars(stmt.order_by(BillRow.created_at))
        return [_to_bill(row) for row in rows]

    def cancel_bill(
        self, user_id: uuid.UUID, bill_id: uuid.UUID, *, now: datetime, correlation_id: str
    ) -> Bill:
        """Cancel a bill (soft — stops future due occurrences) and emit ``BillCancelled``."""
        row = self._require_bill(user_id, bill_id)
        assert row is not None  # _require_bill raises otherwise
        row.active = False
        event = BillCancelled(
            user_id=user_id,
            occurred_at=now,
            source=BILLS_SOURCE,
            correlation_id=correlation_id,
            payload=BillCancelledPayload(bill_id=bill_id),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return _to_bill(row)

    def pay_bill(
        self,
        user_id: uuid.UUID,
        bill_id: uuid.UUID,
        due_at: datetime,
        *,
        amount_minor: int | None = None,
        paid_at: datetime | None = None,
        transaction_id: uuid.UUID | None = None,
        now: datetime,
        correlation_id: str,
    ) -> BillPayment:
        """Mark a bill's due occurrence (identified by ``due_at``) as paid."""
        row = self._require_bill(user_id, bill_id)
        assert row is not None  # _require_bill raises otherwise
        period = due_at.date().isoformat()
        resolved_paid_at = paid_at or now
        resolved_amount = amount_minor if amount_minor is not None else row.amount_minor
        event = BillPaid(
            user_id=user_id,
            occurred_at=now,
            source=BILLS_SOURCE,
            correlation_id=correlation_id,
            payload=BillPaidPayload(
                bill_id=bill_id,
                period=period,
                due_at=due_at,
                amount_minor=resolved_amount,
                paid_at=resolved_paid_at,
                transaction_id=transaction_id,
            ),
        )
        stored = EventStore(self._session).append(event)
        self._session.commit()
        self._publish(event)
        return BillPayment(
            event_id=stored.event_id,
            bill_id=bill_id,
            period=period,
            due_at=due_at,
            amount_minor=resolved_amount,
            paid_at=resolved_paid_at,
            transaction_id=transaction_id,
        )

    def _require_account(self, user_id: uuid.UUID, account_id: uuid.UUID) -> AccountRow:
        row = self._session.scalars(
            select(AccountRow).where(
                AccountRow.account_id == account_id, AccountRow.user_id == user_id
            )
        ).one_or_none()
        if row is None:
            raise UnknownAccountError(account_id)
        return row

    def _require_bill(
        self, user_id: uuid.UUID, bill_id: uuid.UUID, *, raising: bool = True
    ) -> BillRow | None:
        row = self._session.scalars(
            select(BillRow).where(BillRow.bill_id == bill_id, BillRow.user_id == user_id)
        ).one_or_none()
        if row is None and raising:
            raise UnknownBillError(bill_id)
        return row

    def _publish(self, event: BillRegistered | BillUpdated | BillCancelled | BillPaid) -> None:
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
