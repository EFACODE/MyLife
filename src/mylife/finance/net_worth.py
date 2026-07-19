"""Net worth, balances and cash flow.

Derives, **read-time**, three views from the finance event stream: per-account
balances (a ``PositionValued`` anchor plus the signed transactions appended after
it), net worth (grouped per currency, never summed across them), and cash flow
(inflow/outflow/net over a window). No projection table — see
``specs/domain/finance/net-worth.md`` (T4.3).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from mylife.core.events import EventStore, StoredEvent
from mylife.finance.models import (
    POSITION_VALUED,
    TRANSACTION_TYPES,
    AccountRow,
)

# Read the whole finance history for a user; a materialized projection is the
# documented scale path (spec §6/§9).
_UNBOUNDED = 1_000_000


class Balance(BaseModel):
    """An account's current balance in its own currency."""

    model_config = ConfigDict(frozen=True)

    account_id: uuid.UUID
    currency: str
    balance_minor: int
    as_of: datetime | None


class CurrencyTotal(BaseModel):
    """A net-worth total for a single currency."""

    model_config = ConfigDict(frozen=True)

    currency: str
    total_minor: int


class NetWorth(BaseModel):
    """Net worth grouped per currency, with a per-account breakdown."""

    model_config = ConfigDict(frozen=True)

    currencies: list[CurrencyTotal]
    accounts: list[Balance]


class CurrencyFlow(BaseModel):
    """Cash flow for a single currency over a window."""

    model_config = ConfigDict(frozen=True)

    currency: str
    inflow_minor: int
    outflow_minor: int
    net_minor: int


class CashFlow(BaseModel):
    """Inflow/outflow/net per currency over an inclusive UTC window."""

    model_config = ConfigDict(frozen=True)

    occurred_from: datetime
    occurred_to: datetime
    flows: list[CurrencyFlow]


class _Accumulator:
    """Folds finance events into a running balance for one account."""

    __slots__ = ("balance_minor", "as_of", "seen")

    def __init__(self) -> None:
        self.balance_minor = 0
        self.as_of: datetime | None = None
        self.seen = False

    def apply(self, event: StoredEvent) -> None:
        if event.event_type == POSITION_VALUED:
            self.balance_minor = int(event.payload["value_minor"])  # type: ignore[call-overload]
        else:
            self.balance_minor += int(event.payload["amount_minor"])  # type: ignore[call-overload]
        self.as_of = event.occurred_at
        self.seen = True


class NetWorthService:
    """Read-time balances, net worth and cash flow over the finance events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _accounts(self, user_id: uuid.UUID) -> dict[str, AccountRow]:
        rows = self._session.scalars(
            select(AccountRow).where(AccountRow.user_id == user_id).order_by(AccountRow.created_at)
        )
        return {str(row.account_id): row for row in rows}

    def _finance_events(self, user_id: uuid.UUID) -> list[StoredEvent]:
        """The user's finance events in ascending append order (``global_seq``)."""
        finance_types = {*TRANSACTION_TYPES, POSITION_VALUED}
        return [
            event
            for event in EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
            if event.event_type in finance_types
        ]

    def _balances(self, user_id: uuid.UUID) -> dict[str, Balance]:
        accounts = self._accounts(user_id)
        accumulators = {account_id: _Accumulator() for account_id in accounts}
        for event in self._finance_events(user_id):
            account_id = str(event.payload["account_id"])
            accumulator = accumulators.get(account_id)
            if accumulator is not None:
                accumulator.apply(event)
        return {
            account_id: Balance(
                account_id=row.account_id,
                currency=row.currency,
                balance_minor=accumulators[account_id].balance_minor,
                as_of=accumulators[account_id].as_of,
            )
            for account_id, row in accounts.items()
        }

    def account_balance(self, user_id: uuid.UUID, account_id: uuid.UUID) -> Balance | None:
        """Return the account's current balance, or ``None`` if not the user's."""
        return self._balances(user_id).get(str(account_id))

    def net_worth(self, user_id: uuid.UUID) -> NetWorth:
        """Return net worth grouped per currency with a per-account breakdown."""
        balances = list(self._balances(user_id).values())
        totals: dict[str, int] = {}
        for balance in balances:
            totals[balance.currency] = totals.get(balance.currency, 0) + balance.balance_minor
        currencies = [
            CurrencyTotal(currency=currency, total_minor=total)
            for currency, total in sorted(totals.items())
        ]
        return NetWorth(currencies=currencies, accounts=balances)

    def cash_flow(
        self, user_id: uuid.UUID, *, occurred_from: datetime, occurred_to: datetime
    ) -> CashFlow:
        """Return inflow/outflow/net per currency over the inclusive UTC window."""
        inflow: dict[str, int] = {}
        outflow: dict[str, int] = {}
        for event in self._finance_events(user_id):
            if event.event_type == POSITION_VALUED:
                continue
            if not occurred_from <= event.occurred_at <= occurred_to:
                continue
            currency = str(event.payload["currency"])
            amount = int(event.payload["amount_minor"])  # type: ignore[call-overload]
            if amount >= 0:
                inflow[currency] = inflow.get(currency, 0) + amount
            else:
                outflow[currency] = outflow.get(currency, 0) + amount
        currencies = sorted({*inflow, *outflow})
        flows = [
            CurrencyFlow(
                currency=currency,
                inflow_minor=inflow.get(currency, 0),
                outflow_minor=outflow.get(currency, 0),
                net_minor=inflow.get(currency, 0) + outflow.get(currency, 0),
            )
            for currency in currencies
        ]
        return CashFlow(occurred_from=occurred_from, occurred_to=occurred_to, flows=flows)
