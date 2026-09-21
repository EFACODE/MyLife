"""Recurring bills (contas a pagar).

A ``bills`` registry (like accounts/goals) of recurring or one-off bills a
user owes, plus the Bills facts — ``BillRegistered``, ``BillPaid`` and
``BillCancelled`` — immutable Life Events. Due occurrences are **not**
persisted as events: they are derived read-time from a bill's recurrence rule
(a monthly due-day or a fixed one-off date) by
:mod:`mylife.finance.bills_report`, the same way net worth is derived from the
finance event stream rather than a projection table. See
``specs/domain/finance/recurring-bills.md`` (T4.7).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

BILL_REGISTERED: Final = "finance.bill_registered"
BILL_PAID: Final = "finance.bill_paid"
BILL_CANCELLED: Final = "finance.bill_cancelled"
BILLS_SOURCE = "finance"

Recurrence = Literal["monthly", "once"]


class BillRow(Base):
    """A user-scoped recurring/one-off bill definition (current state)."""

    __tablename__ = "bills"

    bill_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    account_id: Mapped[uuid.UUID] = mapped_column()
    payee: Mapped[str] = mapped_column(String)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    recurrence: Mapped[str] = mapped_column(String)
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Bill(BaseModel):
    """A bill definition as read back from the bills registry."""

    model_config = ConfigDict(frozen=True)

    bill_id: uuid.UUID
    account_id: uuid.UUID
    payee: str
    amount_minor: int
    currency: str
    category: str | None
    recurrence: Recurrence
    due_day: int | None
    due_at: datetime | None
    active: bool
    created_at: datetime


class BillRegisteredPayload(BaseModel):
    """The bill-registration fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bill_id: uuid.UUID
    account_id: uuid.UUID
    payee: str
    amount_minor: int
    currency: str
    category: str | None = None
    recurrence: Recurrence
    due_day: int | None = None
    due_at: datetime | None = None


class BillPaidPayload(BaseModel):
    """A payment recorded against one due occurrence (period) of a bill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bill_id: uuid.UUID
    period: str
    due_at: datetime
    amount_minor: int
    paid_at: datetime
    transaction_id: uuid.UUID | None = None


class BillCancelledPayload(BaseModel):
    """The bill-cancellation fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bill_id: uuid.UUID


class BillRegistered(LifeEvent[BillRegisteredPayload]):
    """Emitted when a user registers a recurring/one-off bill (Finance)."""

    event_type: Literal["finance.bill_registered"] = BILL_REGISTERED
    schema_version: Literal[1] = 1


class BillPaid(LifeEvent[BillPaidPayload]):
    """Emitted when a user marks a bill's due occurrence as paid (Finance)."""

    event_type: Literal["finance.bill_paid"] = BILL_PAID
    schema_version: Literal[1] = 1


class BillCancelled(LifeEvent[BillCancelledPayload]):
    """Emitted when a user cancels a bill (Finance)."""

    event_type: Literal["finance.bill_cancelled"] = BILL_CANCELLED
    schema_version: Literal[1] = 1
