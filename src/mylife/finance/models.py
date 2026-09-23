"""Finance models and events.

Accounts (a small user-scoped registry) and the first finance facts —
``ExpenseCreated`` (a hand-recorded expense) and ``TransactionImported`` (a
transaction from a source). Both are immutable Life Events; transactions are
read back from the event store, not a dedicated table. Money is always an
integer number of **minor units** (e.g. cents) — never a float. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from mylife.core.events import LifeEvent
from mylife.db.base import Base

EXPENSE_CREATED: Final = "finance.expense_created"
TRANSACTION_IMPORTED: Final = "finance.transaction_imported"
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
