"""Finance bounded context.

Accounts and the first finance facts — ``ExpenseCreated`` and
``TransactionImported`` — recorded as immutable Life Events and read back as
transactions. Money is always integer minor units. The bank connector (T4.2)
and net-worth/cash-flow (T4.3) build on this. See
``specs/domain/finance/expense-tracking.md`` (T4.1).
"""

from mylife.finance.bank_csv import BANK_SOURCE, BankCsvConnector
from mylife.finance.bill_alerts import BillAlert, BillAlertScanner, BillAlertsService
from mylife.finance.bills import (
    BILL_CANCELLED,
    BILL_PAID,
    BILL_REGISTERED,
    Bill,
    BillCancelled,
    BillCancelledPayload,
    BillPaid,
    BillPaidPayload,
    BillRegistered,
    BillRegisteredPayload,
    BillRow,
)
from mylife.finance.bills_report import BillOccurrence, BillsReportService
from mylife.finance.bills_service import (
    BillPayment,
    BillsService,
    InvalidBillRecurrenceError,
    UnknownBillError,
)
from mylife.finance.models import (
    EXPENSE_CREATED,
    POSITION_VALUED,
    TRANSACTION_IMPORTED,
    Account,
    AccountRow,
    Category,
    CategoryRow,
    ExpenseCreated,
    FinancePayload,
    PositionPayload,
    PositionValued,
    Transaction,
    TransactionImported,
)
from mylife.finance.net_worth import (
    Balance,
    CashFlow,
    CurrencyFlow,
    CurrencyTotal,
    NetWorth,
    NetWorthService,
)
from mylife.finance.service import (
    DuplicateCategoryError,
    FinanceService,
    UnknownAccountError,
    UnknownCategoryError,
)

__all__ = [
    "BANK_SOURCE",
    "BILL_CANCELLED",
    "BILL_PAID",
    "BILL_REGISTERED",
    "EXPENSE_CREATED",
    "POSITION_VALUED",
    "TRANSACTION_IMPORTED",
    "Account",
    "AccountRow",
    "Balance",
    "BankCsvConnector",
    "Bill",
    "BillAlert",
    "BillAlertScanner",
    "BillAlertsService",
    "BillCancelled",
    "BillCancelledPayload",
    "BillOccurrence",
    "BillPaid",
    "BillPaidPayload",
    "BillPayment",
    "BillRegistered",
    "BillRegisteredPayload",
    "BillRow",
    "BillsReportService",
    "BillsService",
    "CashFlow",
    "Category",
    "CategoryRow",
    "CurrencyFlow",
    "CurrencyTotal",
    "DuplicateCategoryError",
    "ExpenseCreated",
    "FinancePayload",
    "FinanceService",
    "InvalidBillRecurrenceError",
    "NetWorth",
    "NetWorthService",
    "PositionPayload",
    "PositionValued",
    "Transaction",
    "TransactionImported",
    "UnknownAccountError",
    "UnknownBillError",
    "UnknownCategoryError",
]
