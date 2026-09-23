"""Finance service.

Opens accounts and records the first finance facts. Recording an expense or
importing a transaction appends an immutable Life Event and publishes it
(commit-before-publish, like the rest of the platform); transactions are read
back from the event store rather than a projection table. All operations are
user-scoped. See ``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventBus, EventDispatchError, EventStore, StoredEvent
from mylife.core.events.store import _stored_utc
from mylife.finance.models import (
    EXPENSE_CREATED,
    FINANCE_SOURCE,
    KIND_BY_TYPE,
    TRANSACTION_DELETED,
    TRANSACTION_IMPORTED,
    TRANSACTION_UPDATED,
    Account,
    AccountRow,
    Category,
    CategoryRow,
    ExpenseCreated,
    ExpenseType,
    FinancePayload,
    PositionPayload,
    PositionValued,
    Transaction,
    TransactionDeleted,
    TransactionDeletedPayload,
    TransactionImported,
    TransactionUpdated,
    TransactionUpdatedPayload,
    fold_transaction_corrections,
)
from mylife.finance.net_worth import Balance, NetWorthService

logger = logging.getLogger(__name__)

# A page large enough to hold a user's finance history when filtering in Python.
_UNBOUNDED = 1_000_000

_TRANSACTION_EVENT_TYPES = {
    EXPENSE_CREATED,
    TRANSACTION_IMPORTED,
    TRANSACTION_UPDATED,
    TRANSACTION_DELETED,
}


class UnknownAccountError(Exception):
    """Raised when an account is missing or not owned by the acting user."""

    def __init__(self, account_id: uuid.UUID) -> None:
        super().__init__(f"account {account_id} not found")
        self.account_id = account_id


class UnknownCategoryError(Exception):
    """Raised when a category is missing or not owned by the acting user."""

    def __init__(self, category_id: uuid.UUID) -> None:
        super().__init__(f"category {category_id} not found")
        self.category_id = category_id


class DuplicateCategoryError(Exception):
    """Raised when a user already has a category with the given name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"category {name!r} already exists")
        self.name = name


class UnknownTransactionError(Exception):
    """Raised when a transaction is missing or not owned by the acting user."""

    def __init__(self, transaction_event_id: uuid.UUID) -> None:
        super().__init__(f"transaction {transaction_event_id} not found")
        self.transaction_event_id = transaction_event_id


def _to_transaction(event: StoredEvent) -> Transaction:
    payload = event.payload
    category = payload.get("category")
    expense_type = payload.get("expense_type")
    return Transaction(
        event_id=event.event_id,
        kind=KIND_BY_TYPE.get(event.event_type, event.event_type),
        account_id=uuid.UUID(str(payload["account_id"])),
        amount_minor=int(payload["amount_minor"]),  # type: ignore[call-overload]
        currency=str(payload["currency"]),
        description=str(payload["description"]),
        category=str(category) if category is not None else None,
        expense_type=expense_type,
        occurred_at=event.occurred_at,
    )


class FinanceService:
    """Manages accounts and records/reads finance transactions for a user."""

    def __init__(self, session: Session, bus: EventBus) -> None:
        self._session = session
        self._bus = bus

    def create_account(
        self, user_id: uuid.UUID, name: str, currency: str, *, now: datetime
    ) -> Account:
        """Open an account for ``user_id``."""
        row = AccountRow(
            account_id=uuid.uuid4(),
            user_id=user_id,
            name=name.strip(),
            currency=currency.strip().upper(),
            created_at=now,
        )
        self._session.add(row)
        self._session.commit()
        return Account(
            account_id=row.account_id,
            name=row.name,
            currency=row.currency,
            created_at=now,
        )

    def get_account(self, user_id: uuid.UUID, account_id: uuid.UUID) -> Account | None:
        """Return the user's account, or ``None`` if missing/not theirs."""
        row = self._require_account(user_id, account_id, raising=False)
        if row is None:
            return None
        return Account(
            account_id=row.account_id,
            name=row.name,
            currency=row.currency,
            created_at=_stored_utc(row.created_at),
        )

    def list_accounts(self, user_id: uuid.UUID) -> list[Account]:
        """Return all of a user's accounts, ordered by creation time."""
        rows = self._session.scalars(
            select(AccountRow).where(AccountRow.user_id == user_id).order_by(AccountRow.created_at)
        )
        return [
            Account(
                account_id=row.account_id,
                name=row.name,
                currency=row.currency,
                created_at=_stored_utc(row.created_at),
            )
            for row in rows
        ]

    def create_category(self, user_id: uuid.UUID, name: str, *, now: datetime) -> Category:
        """Register a category for ``user_id``, rejecting a case-insensitive duplicate."""
        normalized = name.strip()
        existing = self._session.scalars(select(CategoryRow).where(CategoryRow.user_id == user_id))
        if any(row.name.casefold() == normalized.casefold() for row in existing):
            raise DuplicateCategoryError(normalized)
        row = CategoryRow(
            category_id=uuid.uuid4(), user_id=user_id, name=normalized, created_at=now
        )
        self._session.add(row)
        self._session.commit()
        return Category(category_id=row.category_id, name=row.name, created_at=now)

    def list_categories(self, user_id: uuid.UUID) -> list[Category]:
        """Return all of a user's categories, alphabetically."""
        rows = self._session.scalars(
            select(CategoryRow).where(CategoryRow.user_id == user_id).order_by(CategoryRow.name)
        )
        return [
            Category(
                category_id=row.category_id, name=row.name, created_at=_stored_utc(row.created_at)
            )
            for row in rows
        ]

    def delete_category(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        """Remove a user's category; raises :class:`UnknownCategoryError` if not theirs."""
        row = self._session.scalars(
            select(CategoryRow).where(
                CategoryRow.category_id == category_id, CategoryRow.user_id == user_id
            )
        ).one_or_none()
        if row is None:
            raise UnknownCategoryError(category_id)
        self._session.delete(row)
        self._session.commit()

    def record_expense(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        description: str,
        *,
        category: str | None = None,
        expense_type: ExpenseType | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Transaction:
        """Record an ``ExpenseCreated`` (money out — amount stored negative)."""
        self._require_account(user_id, account_id)
        payload = FinancePayload(
            account_id=account_id,
            amount_minor=-abs(amount_minor),
            currency=currency.strip().upper(),
            description=description,
            category=category,
            expense_type=expense_type,
        )
        event = ExpenseCreated(
            user_id=user_id,
            occurred_at=now,
            source=FINANCE_SOURCE,
            correlation_id=correlation_id,
            payload=payload,
        )
        return self._append_and_publish(event)

    def import_transaction(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        description: str,
        *,
        category: str | None = None,
        external_id: str | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Transaction:
        """Record a ``TransactionImported`` (amount kept as given, signed)."""
        self._require_account(user_id, account_id)
        payload = FinancePayload(
            account_id=account_id,
            amount_minor=amount_minor,
            currency=currency.strip().upper(),
            description=description,
            category=category,
            external_id=external_id,
        )
        event = TransactionImported(
            user_id=user_id,
            occurred_at=now,
            source=FINANCE_SOURCE,
            correlation_id=correlation_id,
            payload=payload,
        )
        return self._append_and_publish(event)

    def record_valuation(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        value_minor: int,
        currency: str,
        *,
        now: datetime,
        correlation_id: str,
    ) -> Balance:
        """Record a ``PositionValued`` (an absolute account valuation/anchor)."""
        self._require_account(user_id, account_id)
        event = PositionValued(
            user_id=user_id,
            occurred_at=now,
            source=FINANCE_SOURCE,
            correlation_id=correlation_id,
            payload=PositionPayload(
                account_id=account_id,
                value_minor=value_minor,
                currency=currency.strip().upper(),
            ),
        )
        EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        balance = NetWorthService(self._session).account_balance(user_id, account_id)
        assert balance is not None  # the account was just validated as the user's
        return balance

    def list_transactions(
        self,
        user_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Transaction]:
        """Return the user's finance transactions, newest first.

        Reads the finance event stream (base facts plus any edits/deletes),
        folds corrections onto their base transaction (see
        :func:`fold_transaction_corrections`), and maps the result to
        :class:`Transaction` views; optionally filters by account.
        """
        events = [
            event
            for event in EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
            if event.event_type in _TRANSACTION_EVENT_TYPES
        ]
        folded = list(fold_transaction_corrections(events).values())
        folded.sort(key=lambda event: (event.occurred_at, event.global_seq), reverse=True)
        transactions = [_to_transaction(event) for event in folded]
        if account_id is not None:
            transactions = [t for t in transactions if t.account_id == account_id]
        return transactions[:limit]

    def update_transaction(
        self,
        user_id: uuid.UUID,
        transaction_event_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        description: str,
        *,
        category: str | None = None,
        expense_type: ExpenseType | None = None,
        now: datetime,
        correlation_id: str,
    ) -> Transaction:
        """Edit a previously recorded transaction, appending a ``TransactionUpdated``.

        The account a transaction is recorded against cannot be changed (like
        bill edits). Raises :class:`UnknownTransactionError` if the
        transaction is missing or not the user's.
        """
        existing = self._get_transaction(user_id, transaction_event_id)
        payload = TransactionUpdatedPayload(
            transaction_event_id=transaction_event_id,
            amount_minor=amount_minor,
            currency=currency.strip().upper(),
            description=description,
            category=category,
            expense_type=expense_type,
        )
        event = TransactionUpdated(
            user_id=user_id,
            occurred_at=now,
            source=FINANCE_SOURCE,
            correlation_id=correlation_id,
            corrects_event_id=transaction_event_id,
            payload=payload,
        )
        self._append(event)
        return Transaction(
            event_id=existing.event_id,
            kind=existing.kind,
            account_id=existing.account_id,
            amount_minor=payload.amount_minor,
            currency=payload.currency,
            description=payload.description,
            category=payload.category,
            expense_type=payload.expense_type,
            occurred_at=existing.occurred_at,
        )

    def delete_transaction(
        self,
        user_id: uuid.UUID,
        transaction_event_id: uuid.UUID,
        *,
        now: datetime,
        correlation_id: str,
    ) -> None:
        """Delete a previously recorded transaction, appending a ``TransactionDeleted``.

        Raises :class:`UnknownTransactionError` if the transaction is missing
        or not the user's.
        """
        self._get_transaction(user_id, transaction_event_id)
        event = TransactionDeleted(
            user_id=user_id,
            occurred_at=now,
            source=FINANCE_SOURCE,
            correlation_id=correlation_id,
            corrects_event_id=transaction_event_id,
            payload=TransactionDeletedPayload(transaction_event_id=transaction_event_id),
        )
        self._append(event)

    def _get_transaction(self, user_id: uuid.UUID, transaction_event_id: uuid.UUID) -> Transaction:
        for transaction in self.list_transactions(user_id, limit=_UNBOUNDED):
            if transaction.event_id == transaction_event_id:
                return transaction
        raise UnknownTransactionError(transaction_event_id)

    def _require_account(
        self, user_id: uuid.UUID, account_id: uuid.UUID, *, raising: bool = True
    ) -> AccountRow | None:
        row = self._session.scalars(
            select(AccountRow).where(
                AccountRow.account_id == account_id, AccountRow.user_id == user_id
            )
        ).one_or_none()
        if row is None and raising:
            raise UnknownAccountError(account_id)
        return row

    def _append_and_publish(self, event: ExpenseCreated | TransactionImported) -> Transaction:
        stored = self._append(event)
        return Transaction(
            event_id=stored.event_id,
            kind=KIND_BY_TYPE[event.event_type],
            account_id=event.payload.account_id,
            amount_minor=event.payload.amount_minor,
            currency=event.payload.currency,
            description=event.payload.description,
            category=event.payload.category,
            expense_type=event.payload.expense_type,
            occurred_at=stored.occurred_at,
        )

    def _append(
        self, event: ExpenseCreated | TransactionImported | TransactionUpdated | TransactionDeleted
    ) -> StoredEvent:
        stored = EventStore(self._session).append(event)
        self._session.commit()
        try:
            self._bus.publish(event)
        except EventDispatchError:
            logger.exception("failed to publish %s (%s)", event.event_type, event.event_id)
        return stored
