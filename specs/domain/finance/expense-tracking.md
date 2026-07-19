# Spec: Finance context — Transactions & Expenses (`T4.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T4.1` — [issue #25](https://github.com/EFACODE/MyLife/issues/25)
- **Bounded context:** Finance
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel + bus), `T2.2` (auth)

## 1. Purpose & business context

Start the **Finance** bounded context: accounts and the first finance facts —
`ExpenseCreated` (a hand-recorded expense) and `TransactionImported` (a
transaction from a source). Like every domain, finance publishes **immutable
Life Events** into the kernel; a query reads them back as transactions. This is
the foundation for the finance connector (`T4.2`) and net-worth/cash-flow
(`T4.3`), and begins the cross-domain understanding of Phase 2.

## 2. Scope

- **In scope:**
  - An `accounts` registry (create/read/list), user-scoped.
  - `ExpenseCreated` / `TransactionImported` events (Finance context).
  - `FinanceService`: create accounts; record an expense; import a transaction
    (append + publish); list transactions (read from the event store).
  - Authenticated endpoints (`get_current_user`, `T2.2`): `POST/GET /accounts`,
    `POST /finance/expenses`, `POST /finance/transactions`,
    `GET /finance/transactions`.
- **Out of scope (later):**
  - The bank connector (`T4.2`), net worth / positions / cash flow (`T4.3`).
  - Categorization rules, currency conversion, budgets, splits/transfers.
  - Editing/deleting transactions (corrections use `EventCorrected`, `T1.5`).

## 3. User stories & acceptance criteria

- As a **user**, I create an account and record an expense against it.
  - **AC1:** `POST /accounts` (authenticated) returns the created account
    (generated id, name, currency).
  - **AC2:** `POST /finance/expenses` records an `ExpenseCreated` for the user's
    account and returns the resulting transaction view (money out).
  - **AC3:** `POST /finance/transactions` records a `TransactionImported`.
  - **AC4:** `GET /finance/transactions` lists the user's transactions (both
    kinds), newest first, filterable by `account_id`.
- As the **platform**, I keep money exact and scoped.
  - **AC5:** Amounts are integer **minor units** (e.g. cents) with an ISO-4217
    `currency` — never floats. Referencing an account that isn't the user's →
    `404`.
  - **AC6:** All endpoints require authentication (`401` otherwise) and act only
    on the authenticated user's data.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `accounts`: `account_id` (UUID PK), `user_id` (UUID, indexed), `name`, `currency` (ISO-4217, 3 letters), `created_at` (UTC). |
| FR-2 | Functional | Events `finance.expense_created` and `finance.transaction_imported` (`schema_version = 1`), payload `{account_id, amount_minor (int, signed), currency, description, category?, external_id?}`; appended (`T1.2`) and published (`T1.3`), commit-before-publish. |
| FR-3 | Functional | `amount_minor` is a signed integer in the currency's minor units (money out is negative for expenses); no floating-point money anywhere. |
| FR-4 | Functional | `FinanceService`: `create_account`, `get_account`, `list_accounts`, `record_expense`, `import_transaction`, `list_transactions(user_id, *, account_id=None, limit)`. |
| FR-5 | Functional | `record_expense`/`import_transaction` validate the referenced `account_id` exists and belongs to the user (`UnknownAccountError`); the expense amount is stored as negative if given positive. |
| FR-6 | Functional | `list_transactions` reads finance events for the user from the event store and maps them to `Transaction` views (kind, account_id, amount_minor, currency, category, description, occurred_at, event_id), newest first. |
| FR-7 | Functional | Endpoints use `get_current_user`; account/transaction data is always scoped to the caller. |
| NFR-1 | Typing | Passes `mypy --strict`; money is `int`, currency validated. |
| NFR-2 | Migration | One Alembic revision creates `accounts`; `alembic check` clean. |
| NFR-3 | Testability | Service + endpoints tested (create account, record expense/import, list, scoping, auth, unknown account). |

## 5. API & event contracts

```
POST /accounts        { "name": "Checking", "currency": "BRL" }              -> 201 Account
GET  /accounts                                                               -> [Account]
POST /finance/expenses      { "account_id", "amount_minor": 4599, "currency": "BRL",
                              "category": "food", "description": "Lunch" }    -> 201 Transaction (money out)
POST /finance/transactions  { "account_id", "amount_minor": -4599, "currency": "BRL",
                              "description": "Card 1234", "external_id": "tx-1" } -> 201 Transaction
GET  /finance/transactions?account_id=...                                    -> [Transaction]

Account     = { account_id, name, currency, created_at }
Transaction = { event_id, kind, account_id, amount_minor, currency, category, description, occurred_at }
```

- **Events produced:** `ExpenseCreated`, `TransactionImported` (Finance context).

## 6. Data model & migration strategy

- `AccountRow` on `Base` (table `accounts`). Transactions are **events**, not a
  table — `list_transactions` reads the event store (finance event types) and
  maps payloads to `Transaction` views. Proposed layout:
  `src/mylife/finance/` (models, events, service) + `src/mylife/api/finance.py`.
- New Alembic revision `0011_accounts`; `env.py` imports the finance model.
  `alembic check` clean.

## 7. Privacy, consent, access-control & retention

- Finance is highly sensitive; all endpoints are authenticated and user-scoped.
  Payload amounts/descriptions are event payloads (never logged).
- Manual expense/import need no connector consent; the **bank connector** (`T4.2`)
  will be consent-gated via `T2.3`. Erasure (`T2.5`) already removes finance
  events; accounts are added to the erasure sweep.

## 8. Test plan

- **Account (AC1/FR-1):** create → returned + listed; scoped to user.
- **Expense (AC2/FR-3/FR-5):** record → `ExpenseCreated` emitted/published;
  amount stored negative; unknown/foreign account → error.
- **Import (AC3):** record → `TransactionImported`.
- **List (AC4/FR-6):** returns both kinds newest-first; `account_id` filter;
  user-scoped.
- **Endpoints/auth (AC6):** authenticated flow; `401` without token; `404` for a
  foreign account.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), auth (`T2.2`); erasure (`T2.5`) updated
  to include `accounts`.
- **Open decisions (resolved for this spec):**
  - *Money.* → **Integer minor units + ISO-4217 currency**, signed
    (`amount_minor`); no floats.
  - *Transactions storage.* → **Events, not a table** (read via the event store);
    a dedicated transactions projection can be added if query needs grow.
  - *Auth from the start.* → Finance endpoints are **authenticated/user-scoped**
    (no `user_id` parameter), unlike the pre-auth timeline endpoints.
  - *Expense sign.* → expenses stored **negative**; income/import as given.
- **Risks:**
  - *Multi-currency accounting* is deferred; a transaction's `currency` should
    match its account's (validated) — cross-currency is future work.
  - *Reading transactions from events* may need a projection at scale (noted).
- **Future work:** bank connector (`T4.2`), net worth/cash flow (`T4.3`),
  categories/budgets, transfers, multi-currency.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status updated; erasure includes `accounts`.
- [ ] Money is integer minor units; finance data user-scoped; payloads not logged.
