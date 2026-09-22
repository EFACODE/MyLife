# Spec: Finance context — Bill editing & occurrence cap (`T4.13`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.13`
- **Bounded context:** Finance
- **Author / date:** Claude Code / 2026-09-22
- **Depends on:** `T4.7` (recurring bills), `T4.8` (due-date alerts, unaffected)

## 1. Purpose & business context

Two gaps in `T4.7`'s bills registry: a bill's fields could not be corrected
after registration (only cancelled and re-registered), and a monthly bill
always recurred indefinitely — there was no way to model a fixed-length
recurring obligation (e.g. a loan paid off in a known number of
installments, a school enrollment fee for N months). This closes both, plus
lays the "Contas cadastradas" list out as a table for readability at scale.

## 2. Scope

- **In scope:**
  - `BillUpdated` — a new immutable Life Event correcting a bill's editable
    fields (payee, amount, currency, category, recurrence, due_day/due_at,
    `max_occurrences`), following the same "correction is a new event, never
    a mutation of the fact" pattern as the rest of the platform. The
    `bills` registry row (a current-state projection, like `BillCancelled`
    already updates in place) is updated to match.
  - `max_occurrences` on a bill: `0` (default) = unlimited monthly
    recurrence (existing behavior, unchanged); a positive integer caps how
    many due occurrences a monthly bill ever generates, counted from its
    registration month as occurrence 1.
  - `PATCH /finance/bills/{id}` endpoint + `BillsService.update_bill`.
  - Web: an "Editar" action on each registered bill (Contas cadastradas
    screen) opening a form pre-filled with the bill's current fields; the
    list itself becomes a table (columns instead of stacked text) for
    readability with many bills; a "Quantidade de ocorrências" field (label:
    "0 = infinita") on both the register and edit forms.
- **Out of scope:** editing which account a bill is billed against (a
  bigger behavioral question — moving historical payments to a different
  account — left for a future increment if requested); a UI to show "N of M
  occurrences remaining" per bill (the cap only affects the bills *report*,
  i.e. which future due dates appear).

## 3. User stories & acceptance criteria

- As a **user**, I can fix a mistake in a bill I already registered without
  cancelling and re-creating it.
  - **AC1:** `PATCH /finance/bills/{id}` (authenticated) updates the bill's
    fields and returns the corrected bill; the same recurrence validation as
    registration applies (`monthly` needs `due_day`, `once` needs `due_at`).
  - **AC2:** Editing a bill emits `BillUpdated`; the bill's event history
    (`BillRegistered` → `BillUpdated`) is preserved, never overwritten.
  - **AC3:** Editing a foreign or unknown bill id → `404`.
- As a **user**, I can register a bill that only recurs a fixed number of
  times (e.g. a 12-installment loan) instead of forever.
  - **AC4:** `max_occurrences=0` (the default) behaves exactly as before —
    unlimited monthly recurrence.
  - **AC5:** `max_occurrences=N>0` on a monthly bill makes the bills report
    stop generating due occurrences for that bill after its Nth occurrence,
    counted from the bill's registration month; occurrences already paid
    stay visible/paid (the cap only affects which *future* candidates are
    generated, not history).
- As a **user**, I see my registered bills laid out for readability.
  - **AC6:** "Contas cadastradas" renders as a table (Beneficiário, Valor,
    Vencimento, Categoria, Ocorrências, Ações) instead of a single stacked
    text line per bill.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `bills.max_occurrences` column (`Integer`, `NOT NULL DEFAULT 0`). |
| FR-2 | Functional | Event `finance.bill_updated` (`schema_version=1`), payload mirrors `BillRegisteredPayload` minus `account_id` (the account is fixed). |
| FR-3 | Functional | `BillsService.update_bill(user_id, bill_id, payee, amount_minor, currency, *, recurrence, category=None, due_day=None, due_at=None, max_occurrences=0, now, correlation_id) -> Bill`; validates recurrence like `register_bill`; raises `UnknownBillError` if not the user's. |
| FR-4 | Functional | `BillsReportService._periods_for_bill` caps a monthly bill's generated candidates to occurrences `1..max_occurrences` (counted from the bill's `created_at` month) when `max_occurrences > 0`; unchanged (unbounded) when `0`. |
| FR-5 | Functional | `PATCH /finance/bills/{id}` (`UpdateBillRequest`, same field constraints as `RegisterBillRequest` minus `account_id`) → `200 Bill`; `404` unknown/foreign; `422` inconsistent recurrence. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision adds `bills.max_occurrences`; `alembic check` clean. |
| NFR-3 | Testability | Service + endpoint tests: update happy path, event emitted, recurrence validation, ownership scoping; report test proving the occurrence cap. |

## 5. API & event contracts

```
PATCH /finance/bills/{id}  { "payee", "amount_minor", "currency", "category"?,
                              "recurrence", "due_day"?, "due_at"?,
                              "max_occurrences"? (default 0) }  -> 200 Bill
POST  /finance/bills       (unchanged shape) + optional "max_occurrences" (default 0) -> 201 Bill

Bill = { bill_id, account_id, payee, amount_minor, currency, category,
         recurrence, due_day, due_at, max_occurrences, active, created_at }
```

- **Events produced:** `BillUpdated` (Finance context).

## 6. Data model & migration strategy

- `BillRow.max_occurrences` added to the existing `bills` table (`src/mylife/finance/bills.py`).
- New Alembic revision `0022_bill_max_occurrences`; `env.py` already imports
  `mylife.finance.bills`, so no further wiring needed. `alembic check` clean.

## 7. Privacy, consent, access-control & retention

- No change: `PATCH /finance/bills/{id}` is authenticated and user-scoped
  like every other bills endpoint; `max_occurrences` flows through the
  existing `bills` export/erasure sweep (`T2.5`) via `_to_bill`, no new
  wiring needed there.

## 8. Test plan

- **Update (AC1/AC2/FR-2/FR-3):** register → update → fields changed,
  `BillUpdated` emitted after `BillRegistered`, `get_bill` reflects the
  correction.
- **Recurrence validation (FR-3):** monthly without `due_day` → `InvalidBillRecurrenceError`.
- **Ownership (AC3):** foreign/unknown bill id → `UnknownBillError`/`404`.
- **Occurrence cap (AC4/AC5/FR-4):** `max_occurrences=0` unchanged behavior
  (regression via existing tests); `max_occurrences=2` on a monthly bill
  registered in September yields exactly the September and October
  occurrences over a wider report window.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T4.7` (bills registry), `T4.8` (alerts — unaffected,
  reads the same capped report).
- **Open decisions (resolved for this spec):**
  - *Edit as event vs. mutation.* → **New `BillUpdated` event** + in-place
    row update, matching `BillCancelled`'s existing precedent — the
    `bills` table is a current-state projection, not the source of truth.
  - *Occurrence numbering anchor.* → **The bill's registration month**
    (`created_at`), counted forward — simple, deterministic, and consistent
    regardless of which report window is later queried.
  - *Editing the account.* → **Out of scope** (not requested; reassigning a
    bill's account raises questions about historical payments this spec
    doesn't need to answer).
- **Risks:** none beyond the existing bills-report read-time derivation
  pattern; the cap is pure filtering logic, no new stored state beyond one
  integer column.
- **Future work:** surfacing "N of M occurrences remaining" in the UI; a
  UI to reassign a bill's account.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoint authenticated/in OpenAPI; migration reviewed; backlog + spec status updated.
