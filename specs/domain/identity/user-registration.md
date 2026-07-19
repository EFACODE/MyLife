# Spec: Identity — User/Household + UserRegistered (`T2.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T2.1` — [issue #9](https://github.com/EFACODE/MyLife/issues/9)
- **Bounded context:** Identity
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1`/`T1.2`/`T1.3` (event kernel + bus), `T3.2` (bus wiring)

## 1. Purpose & business context

Everything so far treats `user_id` as an opaque parameter. This task creates the
**Identity** context — the real `User` (and a minimal `Household`) aggregate and
the `UserRegistered` event — so the platform has first-class users. It is the
upstream context every other domain references by `user_id`; it is the
foundation authentication (`T2.2`), consent (`T2.3`), audit (`T2.4`) and
data-subject rights (`T2.5`) build on.

Authentication/credentials are **not** in this task (`T2.2`): registration here
establishes the identity record and emits `UserRegistered`; login/passwords come
next.

## 2. Scope

- **In scope:**
  - `users` and `households` tables + an `IdentityService`.
  - Register a user (unique email) → emits `UserRegistered`; read a user.
  - Create/read a minimal household; a user may belong to one.
  - `POST /users`, `GET /users/{id}`, `POST /households`, `GET /households/{id}`.
- **Out of scope (later tasks):**
  - Authentication, passwords, sessions, tokens (`T2.2`).
  - Consent (`T2.3`), audit (`T2.4`), export/deletion (`T2.5`).
  - Profiles beyond `display_name`; household roles/permissions; invitations.
  - A DB foreign key from events to `users` (Identity is upstream; other
    contexts reference `user_id` by value to preserve boundaries).

## 3. User stories & acceptance criteria

- As a **new user**, I register and become a first-class user.
  - **AC1:** `POST /users` with a unique email returns `201` and the created
    `User` (generated `user_id`, normalized email, `status = "active"`).
  - **AC2:** Registering emits and publishes a `UserRegistered` event
    (`source = "identity"`, `user_id` = the new user).
  - **AC3:** A duplicate email returns `409` and creates nothing.
- As a **user**, I can be read by id.
  - **AC4:** `GET /users/{id}` returns the user or `404`.
- As a **household organizer**, I create a household and a user can join it.
  - **AC5:** `POST /households` returns `201`; `POST /users` with a
    `household_id` links the user; an unknown `household_id` returns `422`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `users`: `user_id` (UUID PK), `email` (unique, normalized lowercase/trim), `display_name`, `status` (default `active`), `household_id` (UUID, nullable), `created_at` (UTC). |
| FR-2 | Functional | Table `households`: `household_id` (UUID PK), `name`, `created_at` (UTC). |
| FR-3 | Functional | `IdentityService.register_user(email, display_name, *, now, correlation_id, household_id=None) -> User`: normalizes email, enforces uniqueness (`DuplicateUserError`), validates `household_id` exists (`UnknownHouseholdError`), inserts the user, then appends+publishes `UserRegistered`. |
| FR-4 | Functional | `UserRegistered` is an event (`event_type = "identity.user_registered"`, `schema_version = 1`, payload `{email, display_name}`), appended (`T1.2`) and published (`T1.3`), commit-before-publish (best-effort, mirroring `T3.2`). |
| FR-5 | Functional | `get_user(user_id) -> User | None`; `create_household(name, *, now) -> Household`; `get_household(household_id) -> Household | None`. |
| FR-6 | Functional | Email is validated as non-empty and containing `@` (light validation, no new dependency); normalized to lowercase/trimmed before uniqueness and storage. |
| FR-7 | Functional | Endpoints: `POST /users` (201/409/422), `GET /users/{id}` (200/404), `POST /households` (201), `GET /households/{id}` (200/404). |
| NFR-1 | Typing | Passes `mypy --strict`; typed request/response models. |
| NFR-2 | Migration | One Alembic revision creates `users` + `households`; `alembic check` clean. |
| NFR-3 | Testability | Service unit-tested on SQLite; endpoints via `TestClient`. |
| NFR-4 | Privacy | Email/display_name are PII: never logged; stored in `users` only. |

## 5. API & event contracts

```
POST /users
  body: { "email": "a@b.com", "display_name": "Ada", "household_id": null }
  201 -> User
  409 -> duplicate email     422 -> unknown household / invalid email

GET /users/{user_id}   -> 200 User | 404
POST /households  { "name": "Home" }   -> 201 Household
GET /households/{household_id}         -> 200 Household | 404
```

```python
class User(BaseModel):        # frozen
    user_id: UUID; email: str; display_name: str
    status: str; household_id: UUID | None; created_at: datetime

class Household(BaseModel):    # frozen
    household_id: UUID; name: str; created_at: datetime
```

- **Event produced:** `UserRegistered` (Identity context), appended + published.

## 6. Data model & migration strategy

- SQLAlchemy models `UserRow`, `HouseholdRow` on `Base`; unique index on
  `users.email`. Proposed layout: `src/mylife/identity/models.py` (rows +
  records), `src/mylife/identity/service.py` (`IdentityService` + events),
  `src/mylife/api/identity.py` (routers), registered in the app factory.
- New Alembic revision `0006_identity` creating both tables; `env.py` imports
  the identity models (via the `mylife.identity` package). `alembic check` clean.
- **No FK from `events.user_id` to `users`** — contexts reference `user_id` by
  value.

## 7. Privacy, consent, access-control & retention

- `email`/`display_name` are personal data, stored only in `users` and never
  logged. `UserRegistered`'s payload carries them (as the registration fact);
  event payloads are already never logged.
- No authentication yet: these endpoints are unauthenticated placeholders until
  `T2.2` adds auth and `T2.3` consent; noted as the seam.
- Retention/erasure of identity data is `T2.5`.

## 8. Test plan

- **Register (AC1/AC2/FR-3/FR-4):** `POST /users` → `201` + user; a
  `UserRegistered` event is appended (queryable) and published to a subscribed
  bus; email normalized.
- **Duplicate (AC3):** same email (case/space-insensitive) → `409`, no second
  user, no second event.
- **Read (AC4):** `GET /users/{id}` returns the user; unknown → `404`.
- **Household (AC5):** `POST /households` → `201`; register with its id links the
  user; unknown `household_id` → `422`.
- **Validation (FR-6):** empty/`@`-less email → `422`.
- **Migration (NFR-2):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), bus/`get_event_bus` (`T3.2`),
  `mylife.db.base`.
- **Open decisions (resolved for this spec):**
  - *Email validation.* → **Light** (`@`, non-empty, normalized), no new
    dependency; stricter validation (RFC/`email-validator`) can come later.
  - *Household.* → **Minimal** (record only, no event); roles/invitations later.
  - *Events → users FK.* → **None**; Identity is upstream, others reference by
    value (keeps contexts decoupled and partition-friendly).
  - *Auth.* → **Deferred to `T2.2`**; registration here is unauthenticated.
- **Risks:**
  - *Unauthenticated endpoints pre-`T2.2`* — acceptable in development; the
    endpoints are the seam for auth/consent.
  - *Email uniqueness race* — guarded by the DB unique constraint (atomic).
- **Future work:** authentication (`T2.2`), consent (`T2.3`), audit (`T2.4`),
  export/deletion (`T2.5`), richer profiles and household roles.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints registered/in OpenAPI; migration reviewed; backlog + spec status updated.
- [ ] `UserRegistered` emitted; PII not logged; auth/consent seam documented.
