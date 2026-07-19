"""Finance endpoints.

Authenticated, user-scoped access to accounts and transactions. A user opens
accounts, records expenses, imports transactions and lists them back. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.connectors import ConnectorRunner, ConsentRequiredError, FetchContext
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.finance import Account, FinanceService, Transaction, UnknownAccountError
from mylife.finance.bank_csv import BankCsvConnector
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
