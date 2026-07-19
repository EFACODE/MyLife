"""Finance bounded context.

Accounts and the first finance facts — ``ExpenseCreated`` and
``TransactionImported`` — recorded as immutable Life Events and read back as
transactions. Money is always integer minor units. The bank connector (T4.2)
and net-worth/cash-flow (T4.3) build on this. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

from mylife.finance.bank_csv import BANK_SOURCE, BankCsvConnector
from mylife.finance.models import (
    EXPENSE_CREATED,
    TRANSACTION_IMPORTED,
    Account,
    AccountRow,
    ExpenseCreated,
    FinancePayload,
    Transaction,
    TransactionImported,
)
from mylife.finance.service import FinanceService, UnknownAccountError

__all__ = [
    "BANK_SOURCE",
    "EXPENSE_CREATED",
    "TRANSACTION_IMPORTED",
    "Account",
    "AccountRow",
    "BankCsvConnector",
    "ExpenseCreated",
    "FinancePayload",
    "FinanceService",
    "Transaction",
    "TransactionImported",
    "UnknownAccountError",
]
