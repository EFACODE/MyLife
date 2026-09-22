# Spec: Finance context — Category registry (`T4.12`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.12`
- **Bounded context:** Finance
- **Author / date:** Claude Code / 2026-09-22
- **Depends on:** `T4.1` (accounts, finance facts), `T2.2` (auth), `T2.5` (data-subject export/erasure)

## 1. Purpose & business context

Categories have existed since `T4.1` only as a free-text field typed on an
expense/transaction/bill — there was no way to see, name consistently, or
manage the set of categories a user actually uses. The web console's
Categorias tab could only show a derived spend-by-category breakdown, with no
"cadastro" (registration) area, which is the gap this spec closes: a small
user-scoped **category registry**, following the same pattern already used
for `accounts` (`T4.1`) — a plain lookup table, not a Life Event stream,
since a category name is reference data a user curates, not a fact that
happened.

## 2. Scope

- **In scope:**
  - A `categories` registry (create/list/delete), user-scoped, one row per
    category name.
  - `FinanceService.create_category` / `list_categories` / `delete_category`.
  - Authenticated endpoints: `POST/GET /finance/categories`,
    `DELETE /finance/categories/{category_id}`.
  - Data-subject export/erasure updated to include `categories`.
  - Web console: a "Cadastrar categoria" + "Categorias cadastradas" area in
    the Categorias tab, alongside the existing derived spend breakdown.
- **Out of scope (later, `T4.10`):** automatically *classifying* a
  transaction into a category (rule-based, evidence-linked
  `TransactionCategorized`) and wiring the free-text `category` fields on
  transactions/bills to this registry (e.g. turning them into a select) —
  this spec only adds the registry itself.

## 3. User stories & acceptance criteria

- As a **user**, I register the categories I use so I have a consistent,
  reusable list instead of retyping free text.
  - **AC1:** `POST /finance/categories` (authenticated) creates a category
    and returns it (generated id, name, created_at).
  - **AC2:** `GET /finance/categories` lists the user's categories,
    alphabetically.
  - **AC3:** `DELETE /finance/categories/{category_id}` removes one of the
    user's categories.
  - **AC4:** Registering a name that already exists for that user
    (case-insensitive) is rejected (`409`) rather than creating a duplicate.
- As the **platform**, I keep categories scoped and exported/erased with the
  rest of a user's data.
  - **AC5:** All endpoints require authentication (`401` otherwise) and act
    only on the authenticated user's categories; deleting/reading another
    user's category id → `404`.
  - **AC6:** Data-subject export includes `categories`; erasure removes them.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `categories`: `category_id` (UUID PK), `user_id` (UUID, indexed), `name`, `created_at` (UTC). |
| FR-2 | Functional | `FinanceService.create_category(user_id, name, *, now)` rejects a case-insensitive duplicate name for that user (`DuplicateCategoryError`). |
| FR-3 | Functional | `FinanceService.list_categories(user_id)` returns the user's categories ordered by name. |
| FR-4 | Functional | `FinanceService.delete_category(user_id, category_id)` raises `UnknownCategoryError` if the category is missing or not the user's. |
| FR-5 | Functional | Endpoints use `get_current_user`; `POST` → `201`, `GET` → `200`, `DELETE` → `204`; duplicate name → `409`; unknown/foreign id → `404`. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision creates `categories`; `alembic check` clean. |
| NFR-3 | Testability | Service + endpoint tests: create/list/delete, scoping, duplicate rejection, auth. |

## 5. API contracts

```
POST   /finance/categories        { "name": "Moradia" }   -> 201 Category
GET    /finance/categories                                 -> [Category]
DELETE /finance/categories/{id}                             -> 204

Category = { category_id, name, created_at }
```

No new events are produced — this is a plain registry, like `accounts`.

## 6. Data model & migration strategy

- `CategoryRow` on `Base` (table `categories`), in
  `src/mylife/finance/models.py` next to `AccountRow`.
- New Alembic revision `0021_categories`; `env.py` already imports
  `mylife.finance.models`, so no further wiring is needed. `alembic check`
  clean.

## 7. Privacy, consent, access-control & retention

- Authenticated and user-scoped, like accounts. No consent scope needed (the
  user directly enters category names, same as `T4.1`'s manual expenses).
  `DataSubjectService` export/erasure (`T2.5`) updated to cover `categories`.

## 8. Test plan

- **Create/list (AC1/AC2/FR-1..3):** create → returned + listed alphabetically; scoped to user.
- **Duplicate (AC4/FR-2):** creating an existing name (any case) → `409`/`DuplicateCategoryError`.
- **Delete (AC3/FR-4):** delete → gone from the list; foreign/unknown id → `404`/`UnknownCategoryError`.
- **Auth (AC5):** `401` without a token.
- **Export/erasure (AC6):** `DataSubjectService.export` includes categories; `.erase` removes them.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** auth (`T2.2`); erasure (`T2.5`) updated to include `categories`.
- **Open decisions (resolved for this spec):**
  - *Registry vs. event-sourced.* → **Plain lookup table**, matching
    `accounts` — a category name is reference data the user curates and
    corrects in place (delete + re-add), not an immutable fact.
  - *Uniqueness.* → Enforced in the service (case-insensitive check before
    insert), not a DB constraint, to keep the error message user-friendly
    and consistent with how other duplicate checks in this codebase are
    handled at the service layer.
- **Risks:** none beyond the existing accounts registry pattern.
- **Future work:** `T4.10` (rule-based automatic categorization) and wiring
  the free-text `category` fields on transactions/bills to this registry
  (e.g. a select populated from it) are natural next steps, deliberately
  left out of this increment's scope.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status updated; erasure includes `categories`.
