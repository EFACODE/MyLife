# Spec: Finance connector — Bank CSV import (`T4.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.2` — [issue #26](https://github.com/EFACODE/MyLife/issues/26)
- **Bounded context:** Finance (ingestion)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T3.4` (connector framework), `T4.1` (finance context/accounts),
  `T2.2` (auth), `T2.3` (consent enforcement)

## 1. Purpose & business context

Bring **bank transactions** into finance through the ingestion spine instead of
by hand. A `BankCsvConnector` implements the `T3.4` `Connector` contract and maps
each statement row to a `TransactionImported` event (`T4.1`) against one of the
user's accounts — reusing the whole pipeline (pull → raw → normalize → append →
publish, idempotent, provenance-linked). It is the first **consent-gated**
connector (`T2.3`) and the first exposed over HTTP, so a user can upload a bank
export and see the transactions on their timeline and in `GET /finance/transactions`.

CSV (not OFX) is chosen first for the same reasons as the calendar connector
(`T3.5`): no new dependency, deterministic to test, still exercises the full
contract. OFX/other formats can follow as additional connectors.

## 2. Scope

- **In scope:**
  - `BankCsvConnector` (`source = "bank"`) implementing the `T3.4` contract:
    parse CSV text into `RawPayload`s and normalize each into a
    `TransactionImported` (`T4.1`) linked to its raw record and to a target
    account.
  - An authenticated, **consent-gated** import endpoint
    `POST /finance/connectors/bank/import` that validates account ownership,
    runs `ConnectorRunner.sync(..., consent=...)`, and returns the sync counts.
  - Registration in the connector registry (`source = "bank"`).
- **Out of scope (later):**
  - OFX/QIF parsing; live bank APIs (Open Finance / OAuth tokens).
  - Categorization rules, transfer/duplicate reconciliation across accounts,
    currency conversion (`currency` must match the account — validated).
  - Net-worth / balances (`T4.3`); scheduling/worker cron for periodic pulls.

## 3. User stories & acceptance criteria

- As a **user**, I upload a bank statement CSV and its rows become transactions.
  - **AC1:** `POST /finance/connectors/bank/import` (authenticated) with an
    `account_id` I own and CSV text creates one raw record and one
    `TransactionImported` per row (`source = "bank"`, `raw_record_id` set,
    account/amount/currency/description from the row) and returns the counts
    (`raw_ingested`, `events_created`, `skipped_duplicates`).
  - **AC2:** The imported transactions appear in `GET /finance/transactions`
    (`T4.1`) and on the timeline (`T3.1`), newest first, filterable by account.
  - **AC3:** Re-importing the same CSV is idempotent (rows skipped, no
    duplicates) — inherited from `T3.4`.
- As the **platform**, I keep finance ingestion consented, scoped and exact.
  - **AC4:** Import **fails closed** without consent for scope `"bank"` → `403`;
    importing into an account that isn't the caller's → `404`;
    unauthenticated → `401`.
  - **AC5:** Amounts are integer **minor units**, signed as given (debits
    negative, credits positive) — never floats. A bad row (missing field,
    non-integer amount, naive/malformed `occurred_at`, or a `currency` that does
    not match the account) fails the batch (no partial ingest).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `BankCsvConnector(csv_text: str, *, account_id: uuid.UUID, account_currency: str, fetched_at: datetime)` with `source = "bank"`, implementing the `T3.4` `Connector` protocol. |
| FR-2 | Functional | `fetch` parses `csv_text` (header row) via stdlib `csv`; each data row becomes a `RawPayload` whose `content` holds the row fields and whose `external_id` is the row's `external_id` (if present); `fetched_at` is the import time (UTC). |
| FR-3 | Functional | Required columns: `amount_minor` (signed int), `occurred_at` (ISO-8601 **UTC**), `description`. Optional: `currency` (defaults to the account's), `category`, `external_id`. |
| FR-4 | Functional | `normalize(raw)` yields a `TransactionImported` with `occurred_at` parsed to UTC, `source = "bank"`, `raw_record_id = raw.raw_record_id`, and a `FinancePayload` `{account_id, amount_minor, currency, description, category?, external_id?}`. |
| FR-5 | Functional | Validation → `ValueError` (runner rolls back the batch, AC5): missing required field; `amount_minor` not a base-10 integer; naive/unparseable `occurred_at`; row `currency` present and ≠ the account's currency. |
| FR-6 | Functional | Endpoint `POST /finance/connectors/bank/import` (`get_current_user`): loads the account (`404` if not the caller's), builds the connector, runs `ConnectorRunner.sync(connector, FetchContext(user_id, correlation_id), consent=ConsentService(...))`; a `ConsentRequiredError` → `403`; returns a `SyncResult` view. |
| FR-7 | Functional | The connector registers itself under `source = "bank"` in the connector registry (`T3.5` pattern). |
| NFR-1 | Security | Consent scope `"bank"` enforced fail-closed; raw statement text stored in `raw_records`, never logged; endpoint is user-scoped. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; stdlib `csv`/`io` only — **no new dependency, no migration** (reuses `raw_records`/`events` + `T4.1` `accounts`). |
| NFR-3 | Testability | Connector tested via `ConnectorRunner` on SQLite (import → transactions queryable + provenance; idempotent; bad-row rollback; currency mismatch) and endpoint tested (auth, consent `403`, foreign account `404`, happy path). |

## 5. API & event contracts

```
POST /finance/connectors/bank/import   (auth + consent "bank")
  { "account_id": "…", "csv": "amount_minor,occurred_at,description,category,external_id\n-4599,2026-07-18T12:00:00+00:00,Coffee,food,tx-1\n" }
  -> 201 { "source": "bank", "raw_ingested": 1, "events_created": 1, "skipped_duplicates": 0 }
  401 (no token) · 403 (no "bank" consent) · 404 (foreign/unknown account)
```

CSV contract (header + rows):

```
amount_minor,occurred_at,description,currency,category,external_id
-4599,2026-07-18T12:00:00+00:00,Coffee,BRL,food,tx-1
250000,2026-07-19T08:00:00+00:00,Salary,BRL,income,tx-2
```

- **Event produced:** `TransactionImported` (`source = "bank"`), one per row,
  provenance-linked to its raw record, scoped to the target account.

## 6. Data model & migration strategy

- **No new tables, no migration.** Reuses `raw_records`/`events` and the `T4.1`
  `accounts` table. Proposed layout: `src/mylife/finance/bank_csv.py` (connector)
  and a new route in `src/mylife/api/finance.py`.

## 7. Privacy, consent, access-control & retention

- Finance is highly sensitive: the endpoint is authenticated and user-scoped, and
  ingestion is **consent-gated** on scope `"bank"` (fail-closed via `T2.3`). Raw
  statement text is persisted verbatim in `raw_records` and never logged; amounts
  and descriptions live only in event payloads. Erasure (`T2.5`) already removes a
  user's `raw_records`, `events` and (from `T4.1`) `accounts`.

## 8. Test plan

- **Import (AC1/AC2/FR-4):** a 2-row CSV → 2 `TransactionImported`, correct
  account/amount/currency/description, provenance set, visible via
  `GET /finance/transactions` and `T3.1`.
- **Idempotency (AC3):** re-import → all rows skipped, no new events.
- **Consent (AC4/FR-6):** without `"bank"` consent → `403` and nothing ingested;
  after `POST /consents {scope:"bank"}` → success.
- **Scoping (AC4):** importing into another user's account → `404`;
  unauthenticated → `401`.
- **Bad row (AC5/FR-5):** missing field / non-integer amount / naive
  `occurred_at` / currency ≠ account → raises, batch rolls back (nothing
  persisted).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.4` framework, `T4.1` finance/accounts, `T2.2` auth,
  `T2.3` consent; stdlib only.
- **Open decisions (resolved for this spec):**
  - *Format.* → **CSV first** (no dependency, deterministic); OFX/QIF later.
  - *Target account.* → the caller **passes `account_id`**; the endpoint validates
    ownership before sync (connector emits events against that account).
  - *Sign.* → amounts kept **as given** (import semantics, `T4.1`): debits
    negative, credits positive.
  - *Consent.* → gated on scope **`"bank"`**, fail-closed; first connector wired
    through the runner's `consent=` gate.
  - *Currency.* → row `currency` optional, **defaults to the account's**; a
    mismatch fails the row (multi-currency is future work).
  - *Registry (FR-7 revised).* → **not registered.** The connector registry
    (`T3.4`) maps a source to a **pre-constructed connector instance** invoked by
    a worker with only `(source, user_id)` (see `workers/tasks.py`). A CSV-upload
    connector needs the uploaded file + target account per request, so — like the
    calendar connector (`T3.5`) — it is **constructed per request in the
    endpoint**, not held in the registry. `BANK_SOURCE` is exported for
    discoverability. Registering *pull* connectors (live bank APIs) fits the
    registry and comes with a later task.
- **Risks:**
  - *Large statements in one transaction* — acceptable for first import;
    batching/streaming is future work.
  - *Duplicate detection across re-exports* relies on content addressing +
    `external_id`; banks that renumber rows may under-dedupe (noted).
- **Future work:** OFX/Open-Finance connectors, worker scheduling, categorization
  rules, transfer reconciliation, net worth (`T4.3`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green (no migration;
      `alembic check` unaffected).
- [ ] Endpoint authenticated + consent-gated in OpenAPI; connector constructed
      per-request (registry deferred, see §9); backlog + spec status updated.
- [ ] End-to-end proven (CSV → `TransactionImported` queryable, provenance-linked);
      money is integer minor units; raw text not logged.
