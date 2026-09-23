"""Finance models and events.

Accounts (a small user-scoped registry) and the first finance facts —
``ExpenseCreated`` (a hand-recorded expense) and ``TransactionImported`` (a
transaction from a source). Both are immutable Life Events; transactions are
read back from the event store, not a dedicated table. Money is always an
integer number of **minor units** (e.g. cents) — never a float. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent, StoredEvent
from mylife.db.base import Base

EXPENSE_CREATED: Final = "finance.expense_created"
TRANSACTION_IMPORTED: Final = "finance.transaction_imported"
TRANSACTION_UPDATED: Final = "finance.transaction_updated"
TRANSACTION_DELETED: Final = "finance.transaction_deleted"
POSITION_VALUED: Final = "finance.position_valued"
FINANCE_SOURCE = "finance"

ExpenseType = Literal["fixed", "variable"]

# The transaction ``kind`` surfaced by the read model, keyed by event type.
KIND_BY_TYPE: Final[dict[str, str]] = {
    EXPENSE_CREATED: "expense",
    TRANSACTION_IMPORTED: "import",
}
# The finance event types that move money (transactions), vs. valuations.
TRANSACTION_TYPES: Final[tuple[str, ...]] = (EXPENSE_CREATED, TRANSACTION_IMPORTED)
# Corrections that edit/void a previously recorded transaction (T4.1 follow-up).
TRANSACTION_CORRECTION_TYPES: Final[tuple[str, ...]] = (TRANSACTION_UPDATED, TRANSACTION_DELETED)


class AccountRow(Base):
    """A user-scoped account transactions are recorded against."""

    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Account(BaseModel):
    """An account as read back from the finance store."""

    model_config = ConfigDict(frozen=True)

    account_id: uuid.UUID
    name: str
    currency: str
    created_at: datetime


class FinancePayload(BaseModel):
    """The payload shared by finance facts.

    ``amount_minor`` is a signed integer in the currency's minor units (money
    out is negative). ``currency`` is an ISO-4217 alphabetic code.
    ``expense_type`` classifies a hand-recorded expense as a fixed or variable
    cost; it is only ever set on ``ExpenseCreated`` facts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: uuid.UUID
    amount_minor: int
    currency: str
    description: str
    category: str | None = None
    external_id: str | None = None
    expense_type: ExpenseType | None = None


class ExpenseCreated(LifeEvent[FinancePayload]):
    """Emitted when a user records an expense (Finance context)."""

    event_type: Literal["finance.expense_created"] = EXPENSE_CREATED
    schema_version: Literal[1] = 1


class TransactionImported(LifeEvent[FinancePayload]):
    """Emitted when a transaction is imported from a source (Finance context)."""

    event_type: Literal["finance.transaction_imported"] = TRANSACTION_IMPORTED
    schema_version: Literal[1] = 1


class TransactionUpdatedPayload(BaseModel):
    """A correction to a previously recorded transaction's editable fields.

    Preserves history (``corrects_event_id`` on the envelope references the
    original fact) rather than mutating it; the read model folds the latest
    correction onto the original when listing transactions and computing
    balances.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    transaction_event_id: uuid.UUID
    amount_minor: int
    currency: str
    description: str
    category: str | None = None
    expense_type: ExpenseType | None = None


class TransactionUpdated(LifeEvent[TransactionUpdatedPayload]):
    """Emitted when a user edits a previously recorded transaction (Finance)."""

    event_type: Literal["finance.transaction_updated"] = TRANSACTION_UPDATED
    schema_version: Literal[1] = 1


class TransactionDeletedPayload(BaseModel):
    """The fact that a previously recorded transaction was deleted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transaction_event_id: uuid.UUID


class TransactionDeleted(LifeEvent[TransactionDeletedPayload]):
    """Emitted when a user deletes a previously recorded transaction (Finance)."""

    event_type: Literal["finance.transaction_deleted"] = TRANSACTION_DELETED
    schema_version: Literal[1] = 1


def fold_transaction_corrections(events: Iterable[StoredEvent]) -> dict[uuid.UUID, StoredEvent]:
    """Collapse transaction corrections onto their base fact, in-order.

    ``events`` must be a user's ``EXPENSE_CREATED``/``TRANSACTION_IMPORTED``/
    ``TRANSACTION_UPDATED``/``TRANSACTION_DELETED`` events in ascending append
    order (e.g. ``EventStore.read_stream``). Returns the resulting *effective*
    transaction events keyed by their original (base) event id, in the same
    relative order as they were first created — corrections never rewrite
    history, they only change how it reads back.
    """
    base: dict[uuid.UUID, StoredEvent] = {}
    for event in events:
        if event.event_type in (EXPENSE_CREATED, TRANSACTION_IMPORTED):
            base[event.event_id] = event
        elif event.event_type == TRANSACTION_UPDATED:
            target_id = uuid.UUID(str(event.payload["transaction_event_id"]))
            existing = base.get(target_id)
            if existing is None:
                continue
            payload = dict(existing.payload)
            payload["amount_minor"] = event.payload["amount_minor"]
            payload["currency"] = event.payload["currency"]
            payload["description"] = event.payload["description"]
            payload["category"] = event.payload.get("category")
            payload["expense_type"] = event.payload.get("expense_type")
            base[target_id] = existing.model_copy(update={"payload": payload})
        elif event.event_type == TRANSACTION_DELETED:
            target_id = uuid.UUID(str(event.payload["transaction_event_id"]))
            base.pop(target_id, None)
    return base


class PositionPayload(BaseModel):
    """An absolute valuation of an account/asset (opening balance or mark)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: uuid.UUID
    value_minor: int
    currency: str


class PositionValued(LifeEvent[PositionPayload]):
    """Emitted when an account/asset is valued at a point in time (Finance)."""

    event_type: Literal["finance.position_valued"] = POSITION_VALUED
    schema_version: Literal[1] = 1


class Transaction(BaseModel):
    """A finance transaction as read back from the event store."""

    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID
    kind: str
    account_id: uuid.UUID
    amount_minor: int
    currency: str
    description: str
    category: str | None
    expense_type: ExpenseType | None = None
    occurred_at: datetime


class CreateAccountCommand(BaseModel):
    """A request to open an account for a user."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)


class CategoryRow(Base):
    """A user-scoped category name transactions and bills can be tagged with."""

    __tablename__ = "categories"

    category_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Category(BaseModel):
    """A category as read back from the category registry."""

    model_config = ConfigDict(frozen=True)

    category_id: uuid.UUID
    name: str
    created_at: datetime
