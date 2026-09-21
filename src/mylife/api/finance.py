"""Finance endpoints.

Authenticated, user-scoped access to accounts and transactions. A user opens
accounts, records expenses, imports transactions and lists them back. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.connectors import ConnectorRunner, ConsentRequiredError, FetchContext
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import ensure_utc, utcnow
from mylife.db.base import get_session
from mylife.finance import (
    Account,
    Balance,
    Bill,
    BillOccurrence,
    BillPayment,
    BillsReportService,
    BillsService,
    CashFlow,
    FinanceService,
    InvalidBillRecurrenceError,
    NetWorth,
    NetWorthService,
    Transaction,
    UnknownAccountError,
    UnknownBillError,
)
from mylife.finance.bank_csv import BankCsvConnector
from mylife.finance.bills import Recurrence
from mylife.identity import User
from mylife.identity.consent import ConsentService

router = APIRouter(tags=["finance"])


class CreateAccountRequest(BaseModel):
    """Request to open an account."""

    name: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)


class ExpenseRequest(BaseModel):
    """Request to record a hand-entered expense."""

    account_id: uuid.UUID
    amount_minor: int
    currency: str = Field(min_length=3, max_length=3)
    description: str = Field(min_length=1)
    category: str | None = None


class TransactionRequest(BaseModel):
    """Request to import a transaction from a source."""

    account_id: uuid.UUID
    amount_minor: int
    currency: str = Field(min_length=3, max_length=3)
    description: str = Field(min_length=1)
    category: str | None = None
    external_id: str | None = None


class PositionRequest(BaseModel):
    """Request to record an absolute valuation of an account."""

    account_id: uuid.UUID
    value_minor: int
    currency: str = Field(min_length=3, max_length=3)


class BankImportRequest(BaseModel):
    """Request to import a bank statement CSV into an account."""

    account_id: uuid.UUID
    csv: str = Field(min_length=1)


class BankImportResult(BaseModel):
    """The outcome of a bank CSV import."""

    source: str
    raw_ingested: int
    events_created: int
    skipped_duplicates: int


class RegisterBillRequest(BaseModel):
    """Request to register a recurring or one-off bill."""

    account_id: uuid.UUID
    payee: str = Field(min_length=1)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    category: str | None = None
    recurrence: Recurrence
    due_day: int | None = Field(default=None, ge=1, le=31)
    due_at: datetime | None = None


class PayBillRequest(BaseModel):
    """Request to mark a bill's due occurrence as paid."""

    due_at: datetime
    amount_minor: int | None = None
    paid_at: datetime | None = None
    transaction_id: uuid.UUID | None = None


@router.post("/accounts", response_model=Account, status_code=201)
def create_account(
    request: CreateAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Account:
    """Open an account for the authenticated user."""
    return FinanceService(session, bus).create_account(
        current_user.user_id, request.name, request.currency, now=utcnow()
    )


@router.get("/accounts", response_model=list[Account])
def list_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Account]:
    """List the authenticated user's accounts."""
    return FinanceService(session, bus).list_accounts(current_user.user_id)


@router.post("/finance/expenses", response_model=Transaction, status_code=201)
def record_expense(
    request: ExpenseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Transaction:
    """Record an expense against one of the user's accounts (money out)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return FinanceService(session, bus).record_expense(
            current_user.user_id,
            request.account_id,
            request.amount_minor,
            request.currency,
            request.description,
            category=request.category,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownAccountError as exc:
        raise HTTPException(status_code=404, detail="account not found") from exc


@router.post("/finance/transactions", response_model=Transaction, status_code=201)
def import_transaction(
    request: TransactionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Transaction:
    """Import a transaction against one of the user's accounts."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return FinanceService(session, bus).import_transaction(
            current_user.user_id,
            request.account_id,
            request.amount_minor,
            request.currency,
            request.description,
            category=request.category,
            external_id=request.external_id,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownAccountError as exc:
        raise HTTPException(status_code=404, detail="account not found") from exc


@router.get("/finance/transactions", response_model=list[Transaction])
def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Transaction]:
    """List the authenticated user's transactions, newest first."""
    return FinanceService(session, bus).list_transactions(
        current_user.user_id, account_id=account_id, limit=limit
    )


@router.post("/finance/positions", response_model=Balance, status_code=201)
def record_position(
    request: PositionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Balance:
    """Record an absolute valuation for one of the user's accounts."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return FinanceService(session, bus).record_valuation(
            current_user.user_id,
            request.account_id,
            request.value_minor,
            request.currency,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownAccountError as exc:
        raise HTTPException(status_code=404, detail="account not found") from exc


@router.get("/finance/accounts/{account_id}/balance", response_model=Balance)
def get_balance(
    account_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Balance:
    """Return the current balance of one of the user's accounts."""
    balance = NetWorthService(session).account_balance(current_user.user_id, account_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="account not found")
    return balance


@router.get("/finance/net-worth", response_model=NetWorth)
def get_net_worth(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> NetWorth:
    """Return the user's net worth, grouped per currency."""
    return NetWorthService(session).net_worth(current_user.user_id)


@router.get("/finance/cash-flow", response_model=CashFlow)
def get_cash_flow(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    occurred_from: Annotated[datetime, Query()],
    occurred_to: Annotated[datetime, Query()],
) -> CashFlow:
    """Return inflow/outflow/net per currency over the (inclusive UTC) window."""
    return NetWorthService(session).cash_flow(
        current_user.user_id,
        occurred_from=ensure_utc(occurred_from),
        occurred_to=ensure_utc(occurred_to),
    )


@router.post("/finance/connectors/bank/import", response_model=BankImportResult, status_code=201)
def import_bank_csv(
    request: BankImportRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> BankImportResult:
    """Import a bank statement CSV into one of the user's accounts.

    Consent-gated on scope ``"bank"`` (fail-closed): without consent → ``403``;
    a foreign/unknown account → ``404``. Each row becomes a ``TransactionImported``.
    """
    account = FinanceService(session, bus).get_account(current_user.user_id, request.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    correlation_id = get_correlation_id() or new_correlation_id()
    connector = BankCsvConnector(
        request.csv,
        account_id=account.account_id,
        account_currency=account.currency,
        fetched_at=utcnow(),
    )
    try:
        result = ConnectorRunner(session, bus).sync(
            connector,
            FetchContext(user_id=current_user.user_id, correlation_id=correlation_id),
            consent=ConsentService(session, bus),
        )
    except ConsentRequiredError as exc:
        raise HTTPException(status_code=403, detail="consent required for 'bank'") from exc
    return BankImportResult(
        source=result.source,
        raw_ingested=result.raw_ingested,
        events_created=result.events_created,
        skipped_duplicates=result.skipped_duplicates,
    )


@router.post("/finance/bills", response_model=Bill, status_code=201)
def register_bill(
    request: RegisterBillRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Bill:
    """Register a recurring or one-off bill against one of the user's accounts."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return BillsService(session, bus).register_bill(
            current_user.user_id,
            request.account_id,
            request.payee,
            request.amount_minor,
            request.currency,
            recurrence=request.recurrence,
            category=request.category,
            due_day=request.due_day,
            due_at=ensure_utc(request.due_at) if request.due_at is not None else None,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownAccountError as exc:
        raise HTTPException(status_code=404, detail="account not found") from exc
    except InvalidBillRecurrenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/finance/bills", response_model=list[Bill])
def list_bills(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[Bill]:
    """List the authenticated user's bills."""
    return BillsService(session, bus).list_bills(current_user.user_id, account_id=account_id)


@router.delete("/finance/bills/{bill_id}", status_code=204)
def cancel_bill(
    bill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> None:
    """Cancel one of the user's bills (stops future due occurrences)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        BillsService(session, bus).cancel_bill(
            current_user.user_id, bill_id, now=utcnow(), correlation_id=correlation_id
        )
    except UnknownBillError as exc:
        raise HTTPException(status_code=404, detail="bill not found") from exc


@router.post("/finance/bills/{bill_id}/pay", response_model=BillPayment, status_code=201)
def pay_bill(
    bill_id: uuid.UUID,
    request: PayBillRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> BillPayment:
    """Mark one of the user's bills as paid for a given due occurrence."""
    correlation_id = get_correlation_id() or new_correlation_id()
    try:
        return BillsService(session, bus).pay_bill(
            current_user.user_id,
            bill_id,
            ensure_utc(request.due_at),
            amount_minor=request.amount_minor,
            paid_at=ensure_utc(request.paid_at) if request.paid_at is not None else None,
            transaction_id=request.transaction_id,
            now=utcnow(),
            correlation_id=correlation_id,
        )
    except UnknownBillError as exc:
        raise HTTPException(status_code=404, detail="bill not found") from exc


@router.get("/finance/bills/report", response_model=list[BillOccurrence])
def get_bills_report(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    due_from: Annotated[datetime, Query()],
    due_to: Annotated[datetime, Query()],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    paid: Annotated[bool | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> list[BillOccurrence]:
    """Return the user's bill due occurrences in ``[due_from, due_to]``.

    Filterable by account, paid/unpaid and overdue/not-overdue.
    """
    return BillsReportService(session).list_occurrences(
        current_user.user_id,
        due_from=ensure_utc(due_from),
        due_to=ensure_utc(due_to),
        as_of=utcnow(),
        account_id=account_id,
        paid=paid,
        overdue=overdue,
    )
