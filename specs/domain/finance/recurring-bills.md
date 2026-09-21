# Spec: Finance context — Recurring bills (contas a pagar) (`T4.7`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.7`
- **Bounded context:** Finance
- **Author / date:** Claude Code / 2026-09-21
- **Depends on:** `T4.1` (accounts, event kernel wiring), `T2.2` (auth)

## 1. Purpose & business context

Adds **contas a pagar** (bills a user owes, recurring or one-off) to the
Finance context: registration, marking due occurrences paid, and a
paid/unpaid/overdue report filterable by period, account and status. This is
the first increment of the finance-vision roadmap (backlog `T4.7`–`T4.11`);
due-date alerts (email/WhatsApp, `T4.8`), the Open Finance connector (`T4.9`),
automatic categorization (`T4.10`) and richer dashboards (`T4.11`) build on
top of it.

## 2. Scope

- **In scope:**
  - A `bills` registry (register/get/list/cancel), user-scoped, referencing an
    existing account.
  - `BillRegistered` / `BillPaid` / `BillCancelled` events (Finance context).
  - `BillsService`: register a bill; cancel a bill; record a payment against a
    due occurrence.
  - `BillsReportService`: read-time paid/unpaid/overdue report over a
    period, derived from the bill's recurrence rule + `BillPaid` events —
    no persisted "due" event and no projection table (see §9).
  - Authenticated endpoints: `POST/GET /finance/bills`,
    `DELETE /finance/bills/{id}`, `POST /finance/bills/{id}/pay`,
    `GET /finance/bills/report`.
- **Out of scope (later):**
  - Due-date alerts / outbound notifications (`T4.8`).
  - Open Finance-sourced bills, automatic categorization (`T4.9`/`T4.10`).
  - Editing a bill's amount/schedule in place (`BillUpdated`) — for now a
    bill is cancelled and re-registered; partial payments (a period is
    "paid" once any `BillPaid` exists for it, not by summing amounts).

## 3. User stories & acceptance criteria

- As a **user**, I register a recurring or one-off bill against an account.
  - **AC1:** `POST /finance/bills` (authenticated) creates a bill; `recurrence
    = "monthly"` requires `due_day` (1-31); `recurrence = "once"` requires
    `due_at`. An unknown/foreign `account_id` → `404`; an inconsistent
    recurrence → `422`.
  - **AC2:** `GET /finance/bills` lists the user's bills, optionally filtered
    by `account_id`.
  - **AC3:** `DELETE /finance/bills/{id}` cancels the bill (emits
    `BillCancelled`, stops future due occurrences); a foreign/unknown bill →
    `404`.
- As a **user**, I mark a bill as paid and see what's due/overdue.
  - **AC4:** `POST /finance/bills/{id}/pay` records a payment against a due
    occurrence (`due_at`), emitting `BillPaid`; defaults `amount_minor` to the
    bill's amount and `paid_at` to now; a foreign/unknown bill → `404`.
  - **AC5:** `GET /finance/bills/report?due_from=...&due_to=...` returns the
    due occurrences in that window, each flagged `paid` and `overdue`
    (`due_at` in the past and not paid), filterable by `account_id`, `paid`
    and `overdue`.
- As the **platform**, I keep money exact and everything user-scoped.
  - **AC6:** Amounts are integer minor units with an ISO-4217 `currency`.
  - **AC7:** All endpoints require authentication (`401` otherwise) and act
    only on the authenticated user's data.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `bills`: `bill_id` (UUID PK), `user_id` (indexed), `account_id`, `payee`, `amount_minor` (int, positive), `currency`, `category?`, `recurrence` (`"monthly"`\|`"once"`), `due_day?` (1-31), `due_at?`, `active` (bool), `created_at`. |
| FR-2 | Functional | Events `finance.bill_registered`, `finance.bill_paid`, `finance.bill_cancelled` (`schema_version = 1`), appended (`T1.2`) and published (`T1.3`), commit-before-publish. |
| FR-3 | Functional | `BillsService`: `register_bill`, `get_bill`, `list_bills`, `cancel_bill`, `pay_bill`. Registering validates the account belongs to the user and the recurrence rule is consistent (`InvalidBillRecurrenceError` otherwise). |
| FR-4 | Functional | `BillsReportService.list_occurrences(user_id, due_from, due_to, as_of, account_id?, paid?, overdue?)`: for each active-or-cancelled bill, computes its due occurrences in `[due_from, due_to]` from the recurrence rule (monthly due-day clamped to the month's length; one-off fixed date), folds `BillPaid` events keyed by `(bill_id, period)` (`period` = the occurrence's date, ISO), and flags `overdue = due_at < as_of and not paid`. |
| FR-5 | Functional | `pay_bill` identifies the occurrence by `due_at` (from which `period` is derived); a period is `paid` once any `BillPaid` exists for it (no partial-payment accounting in v1). |
| FR-6 | Functional | Endpoints use `get_current_user`; bill/report data is always scoped to the caller. |
| NFR-1 | Typing | Passes `mypy --strict`; money is `int`, currency validated. |
| NFR-2 | Migration | One Alembic revision creates `bills`; `alembic check` clean. |
| NFR-3 | Testability | Service + report + endpoints tested (register, cancel, pay, report filters, scoping, auth, unknown account/bill, invalid recurrence). |

## 5. API & event contracts

```
POST /finance/bills   { "account_id", "payee": "Aluguel", "amount_minor": 250000,
                         "currency": "BRL", "category": "moradia",
                         "recurrence": "monthly", "due_day": 5 }        -> 201 Bill
GET  /finance/bills?account_id=...                                     -> [Bill]
DELETE /finance/bills/{id}                                             -> 204
POST /finance/bills/{id}/pay  { "due_at": "2026-09-05T00:00:00Z" }      -> 201 BillPayment
GET  /finance/bills/report?due_from=...&due_to=...&paid=false&overdue=true
                                                                         -> [BillOccurrence]

Bill          = { bill_id, account_id, payee, amount_minor, currency, category,
                  recurrence, due_day, due_at, active, created_at }
BillPayment   = { event_id, bill_id, period, due_at, amount_minor, paid_at, transaction_id }
BillOccurrence = { bill_id, account_id, payee, category, currency, amount_minor,
                    period, due_at, paid, paid_at, overdue }
```

- **Events produced:** `BillRegistered`, `BillPaid`, `BillCancelled` (Finance context).

## 6. Data model & migration strategy

- `BillRow` on `Base` (table `bills`) — the current-state registry, alongside
  `AccountRow`/`GoalRow`. Due occurrences and payment status are **not**
  stored — `BillsReportService` derives them read-time. New file layout:
  `src/mylife/finance/bills.py` (models/events), `bills_service.py`
  (`BillsService`), `bills_report.py` (`BillsReportService`).
- New Alembic revision `0019_bills`; `migrations/env.py` imports
  `mylife.finance.bills` so autogenerate/`alembic check` see the table.

## 7. Privacy, consent, access-control & retention

- Bills are user-entered data like `ExpenseCreated`/`GoalCreated` — no new
  connector consent scope needed. All endpoints are authenticated and
  user-scoped; payloads (payee, amounts) are never logged.
- Erasure (`T2.5`) is extended: `DataSubjectService.export`/`.erase` now
  include `bills`.

## 8. Test plan

- **Register (AC1/FR-1/FR-3):** monthly/once bills create the row + event;
  unknown/foreign account → `404`; inconsistent recurrence → `422`.
- **List/cancel (AC2/AC3):** listing scoped + filterable; cancel emits
  `BillCancelled`, flips `active`; foreign/unknown bill → `404`.
- **Pay (AC4/FR-5):** emits `BillPaid`; defaults amount/paid_at; foreign/
  unknown bill → `404`.
- **Report (AC5/FR-4):** monthly due-day clamped at month end (e.g. `due_day
  = 31` in February); occurrences outside `[due_from, due_to]` excluded;
  `paid`/`overdue` flags correct; filters by account/paid/overdue.
- **Endpoints/auth (AC6/AC7):** authenticated flow; `401` without token;
  user-scoping across all bill endpoints.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), accounts (`T4.1`), auth (`T2.2`);
  erasure (`T2.5`) updated to include `bills`.
- **Open decisions (resolved for this spec):**
  - *Due occurrences.* → **Derived read-time from the recurrence rule**,
    not a persisted `BillDueGenerated` event. The original finance-vision
    roadmap sketch called for a scheduler-generated "due" event per period;
    since no periodic scheduler exists yet (Celery beat lands in `T4.8`),
    and since the due date is fully deterministic from `due_day`/`due_at`,
    deriving it at read time avoids a premature dependency on `T4.8` and
    matches the codebase's existing "no projection table, fold at read
    time" convention (`net_worth.py`, `goals/progress.py`). `T4.8`'s alert
    scan will call the same `BillsReportService` rather than reading a
    separate event stream.
  - *Payment identity.* → A due occurrence's `period` key is the ISO date of
    its computed `due_at`; `pay_bill` takes the caller-supplied `due_at`
    (as returned by the report) rather than a `bill_due_id`, since no such
    event is persisted.
  - *Partial payments.* → Deferred; a period is binary paid/unpaid.
- **Risks:**
  - A bill's `due_day`/`due_at` is immutable once registered in this
    increment (no `BillUpdated`); correcting a mistake means cancelling and
    re-registering. Acceptable for v1; flagged as future work.
- **Future work:** `BillUpdated` (in-place schedule/amount correction),
  partial-payment accounting, due-date alerts (`T4.8`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status updated; erasure includes `bills`.
- [ ] Money is integer minor units; bill data user-scoped; payloads not logged.
