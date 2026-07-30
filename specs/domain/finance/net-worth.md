# Spec: Finance — Balances, net worth & cash flow (`T4.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.3` — [issue #27](https://github.com/EFACODE/MyLife/issues/27)
- **Bounded context:** Finance
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T4.1` (finance context/accounts/transactions), `T2.2` (auth)

## 1. Purpose & business context

Turn the raw finance facts into the numbers a person actually asks for: **what's
my balance**, **what am I worth**, and **where did the money go**. This adds a new
finance fact — `PositionValued` (an absolute valuation of an account/asset at a
point in time: an opening balance, or a mark-to-market of a non-cash asset) — and
derives three read models from the finance event stream: per-account **balances**,
**net worth** (across accounts, per currency), and **cash flow** (inflow/outflow
over a window). It is the analytical layer that feeds the cross-domain briefing
(`T4.6`) and, later, forecasting (`T8`).

## 2. Scope

- **In scope:**
  - `PositionValued` event (Finance): an absolute valuation of an account
    (`value_minor`, `currency`) at `occurred_at` — appended + published (`T1.2`/
    `T1.3`), like the other finance facts.
  - A `NetWorthService` deriving, **read-time**, from the finance event stream:
    per-account balance, net worth (per currency, with a per-account breakdown),
    and cash flow (inflow/outflow/net over a time window).
  - Authenticated, user-scoped endpoints: `POST /finance/positions`,
    `GET /finance/accounts/{account_id}/balance`, `GET /finance/net-worth`,
    `GET /finance/cash-flow`.
- **Out of scope (later):**
  - Currency **conversion** / a reporting currency (net worth is grouped **per
    currency**, never summed across currencies).
  - A **materialized** balance projection table / subscriber (read-time
    computation now; a projection can follow at scale — same trade-off as `T4.1`).
  - Historical net-worth **time series**, budgets, categorized cash-flow
    breakdowns (cash flow is a single aggregate per currency for the window).

## 3. User stories & acceptance criteria

- As a **user**, I set an opening balance and see my balance track my activity.
  - **AC1:** `POST /finance/positions` (authenticated, my account) records a
    `PositionValued` and returns the account's balance.
  - **AC2:** `GET /finance/accounts/{account_id}/balance` returns the current
    balance = the **latest** `PositionValued` for the account (if any) **plus**
    the signed sum of the transactions recorded after it; with no valuation, it's
    the signed sum of **all** the account's transactions. Foreign/unknown
    account → `404`.
- As a **user**, I see what I'm worth and where money flowed.
  - **AC3:** `GET /finance/net-worth` returns totals **grouped by currency**
    (never summed across currencies) with a per-account breakdown.
  - **AC4:** `GET /finance/cash-flow?occurred_from=…&occurred_to=…` returns
    inflow (sum of positive amounts), outflow (sum of negative amounts) and net,
    per currency, over the (inclusive UTC) window.
- As the **platform**, I keep it exact and scoped.
  - **AC5:** All amounts are integer **minor units**; all endpoints require auth
    (`401`) and act only on the caller's accounts/events.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Event `finance.position_valued` (`schema_version = 1`), payload `{account_id, value_minor (int), currency}`; appended + published (commit-before-publish). `value_minor` is an absolute valuation (may be negative for a liability). |
| FR-2 | Functional | `FinanceService.record_valuation(user_id, account_id, value_minor, currency, *, now, correlation_id)` validates account ownership (`UnknownAccountError`), appends `PositionValued`, returns the resulting `Balance`. |
| FR-3 | Functional | `NetWorthService.account_balance(user_id, account_id)`: balance = latest `PositionValued` (by append order) as anchor + signed sum of `ExpenseCreated`/`TransactionImported` appended **after** the anchor; no anchor → signed sum of all such events. Returns `Balance{account_id, currency, balance_minor, as_of}`. |
| FR-4 | Functional | `NetWorthService.net_worth(user_id)`: per-account balances grouped into per-currency totals. Returns `NetWorth{currencies: [{currency, total_minor}], accounts: [Balance]}`. Never sums across currencies. |
| FR-5 | Functional | `NetWorthService.cash_flow(user_id, *, occurred_from, occurred_to)`: over transaction events (`ExpenseCreated`/`TransactionImported`, **not** `PositionValued`) in the inclusive UTC window, per currency: `inflow_minor` (Σ positive), `outflow_minor` (Σ negative), `net_minor`. Returns `CashFlow{occurred_from, occurred_to, flows: [{currency, inflow_minor, outflow_minor, net_minor}]}`. |
| FR-6 | Functional | Balance currency = the account's currency; a `PositionValued`/transaction whose currency differs from the account's is out of scope here (guarded at write time by `T4.1`/`T4.2`; net worth simply groups by the account currency). |
| FR-7 | Functional | Endpoints (`get_current_user`): `POST /finance/positions`, `GET /finance/accounts/{account_id}/balance`, `GET /finance/net-worth`, `GET /finance/cash-flow`; all user-scoped. |
| NFR-1 | Typing | Passes `mypy --strict`; money is `int` throughout. |
| NFR-2 | Deps/Migration | **No new dependency, no migration** (reads the event store; reuses `accounts`). `alembic check` unaffected. |
| NFR-3 | Testability | Balance (with/without valuation, ordering), net worth (multi-currency, per-account), cash flow (window, in/out/net), scoping/auth, unknown account. |

## 5. API & event contracts

```
POST /finance/positions   { "account_id", "value_minor": 1000000, "currency": "BRL" }  -> 201 Balance
GET  /finance/accounts/{account_id}/balance                                            -> Balance (404 foreign)
GET  /finance/net-worth                                                                -> NetWorth
GET  /finance/cash-flow?occurred_from=…&occurred_to=…                                   -> CashFlow

Balance  = { account_id, currency, balance_minor, as_of }
NetWorth = { currencies: [ { currency, total_minor } ], accounts: [ Balance ] }
CashFlow = { occurred_from, occurred_to,
             flows: [ { currency, inflow_minor, outflow_minor, net_minor } ] }
```

- **Event produced:** `PositionValued` (Finance context).

## 6. Data model & migration strategy

- **No new tables, no migration.** `PositionValued` is an event; balances / net
  worth / cash flow are computed **read-time** from the event store (reusing the
  `T4.1` account registry for scoping and currency). A materialized
  `account_balances` projection (subscriber-updated, like `EntityProjection`) is
  the documented scale path. Proposed layout: `PositionValued` in
  `src/mylife/finance/models.py`, `record_valuation` in
  `src/mylife/finance/service.py`, a new `src/mylife/finance/net_worth.py`
  (`NetWorthService` + `Balance`/`NetWorth`/`CashFlow`), routes in
  `src/mylife/api/finance.py`.

## 7. Privacy, consent, access-control & retention

- All endpoints are authenticated and user-scoped; balances/net worth/cash flow
  are computed only from the caller's own events. Amounts live in event payloads
  and derived responses, never logged. Erasure (`T2.5`) already removes the
  underlying finance events and accounts, so these derived views vanish with them.

## 8. Test plan

- **Valuation + balance (AC1/AC2/FR-3):** anchor with `PositionValued`, add
  transactions after it → balance = anchor + later txns; no anchor → sum of all;
  ordering respected; unknown/foreign account → `404`.
- **Net worth (AC3/FR-4):** accounts in two currencies → grouped totals, never
  cross-summed; per-account breakdown present; user-scoped.
- **Cash flow (AC4/FR-5):** transactions across a window → inflow/outflow/net per
  currency; events outside the window and `PositionValued` excluded.
- **Auth (AC5):** each endpoint `401` without a token.
- **Migration (NFR-2):** none — `alembic check` stays clean in CI.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T4.1` (accounts/transactions/events), `T2.2` (auth).
- **Open decisions (resolved for this spec):**
  - *`PositionValued` semantics.* → an **absolute valuation** anchor (opening
    balance / asset mark); transactions accumulate on top of the latest anchor.
  - *Balance storage.* → **computed read-time** from events (consistent with
    `T4.1` "transactions are events, not a table"); materialized projection is
    the noted scale path.
  - *Multi-currency.* → **group by currency, never convert.** A reporting
    currency / FX is future work.
  - *Cash flow shape.* → one aggregate **per currency** for the window
    (inflow/outflow/net); categorized breakdowns are future work.
  - *Anchor ordering.* → "after" is by **append order** (`global_seq`); precise
    as-of-date historical reconstruction is future work.
- **Risks:**
  - *Reading balances from events* is O(events) per query — acceptable now; the
    materialized projection removes it at scale (noted).
  - *Mixed-currency account inputs* are prevented upstream (`T4.1`/`T4.2`); this
    layer assumes one currency per account.
- **Future work:** materialized balance projection, historical net-worth time
  series, reporting currency/FX, categorized cash flow, `T4.6` briefing hook.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; no migration
      (`alembic check` clean).
- [ ] Endpoints authenticated/in OpenAPI; backlog + spec status updated.
- [ ] Money is integer minor units; net worth grouped per currency; data
      user-scoped; payloads not logged.
