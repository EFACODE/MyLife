# Spec: Authentication (`T2.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T2.2` — [issue #10](https://github.com/EFACODE/MyLife/issues/10)
- **Bounded context:** Identity
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T2.1` (Identity: users/households + `UserRegistered`)

## 1. Purpose & business context

Give users **credentials** and the platform a way to **authenticate** them:
password hashing, a login endpoint issuing a JWT, and a least-privilege
`get_current_user` dependency that other endpoints will use to identify the
caller instead of trusting a `user_id` parameter. This is the security backbone
consent (`T2.3`) and audit (`T2.4`) build on.

## 2. Scope

- **In scope:**
  - A `credentials` table + password hashing (Argon2).
  - Registration sets a password (evolves `T2.1`): the credential is created in
    the same transaction as the user.
  - `POST /auth/login` (OAuth2 password flow) → a signed JWT.
  - An `OAuth2`-based `get_current_user` dependency (401 on missing/invalid/
    expired token) and `GET /auth/me`.
  - Settings for the JWT secret/algorithm/TTL/issuer.
- **Out of scope (later tasks):**
  - **Retrofitting existing endpoints** (timeline/briefing/…) to require the
    authenticated user and drop the `user_id` parameter — deferred to a focused
    follow-up alongside consent (`T2.3`); this task provides the dependency.
  - Refresh tokens, logout/blocklist, password reset, MFA, OAuth social login.
  - RS256/OIDC provider integration (kept *ready* via structured claims).
  - Roles/permissions beyond "authenticated user".

## 3. User stories & acceptance criteria

- As a **user**, I set a password at registration and log in to get a token.
  - **AC1:** `POST /users` now requires a `password`; the credential is stored
    **hashed** (Argon2), never plaintext.
  - **AC2:** `POST /auth/login` with the correct email+password returns
    `{access_token, token_type: "bearer", expires_in}`; wrong credentials →
    `401`.
- As an **authenticated caller**, I access protected routes with the token.
  - **AC3:** `GET /auth/me` with a valid `Authorization: Bearer <jwt>` returns
    the current `User`; missing/invalid/expired token → `401`.
  - **AC4:** The JWT carries `sub` (user_id), `iss`, `iat`, `exp`; an expired or
    tampered token is rejected.
- As a **security reviewer**, I want secrets handled safely.
  - **AC5:** The signing secret comes from configuration (never hardcoded);
    passwords and tokens are never logged.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `credentials`: `user_id` (UUID PK), `password_hash` (str), `updated_at` (UTC). One credential per user. |
| FR-2 | Functional | `hash_password`/`verify_password` use **Argon2** (`argon2-cffi`). Hashes are opaque strings; plaintext is never stored or logged. |
| FR-3 | Functional | `IdentityService.register_user(..., password)` creates the user **and** its credential atomically (one transaction) before emitting `UserRegistered`; `UserRegistered`'s payload is unchanged (no secret). |
| FR-4 | Functional | `authenticate(email, password) -> User | None`: normalizes email, loads the credential, verifies the password (constant-time via the hasher); returns the user or `None`. |
| FR-5 | Functional | `POST /auth/login` accepts OAuth2 password form (`username`=email, `password`), returns a signed JWT on success, `401` otherwise. |
| FR-6 | Functional | JWT is HS256, claims `{sub, iss, iat, exp}`; `create_access_token(user_id)` / `decode_access_token(token) -> claims` (raising `TokenError` on invalid/expired). |
| FR-7 | Functional | `get_current_user` (FastAPI dependency using `OAuth2PasswordBearer`, `tokenUrl=/auth/login`) resolves the bearer token to a `User`; `401` on missing/invalid/expired/unknown user. |
| FR-8 | Functional | `GET /auth/me` returns the current user via `get_current_user`. |
| FR-9 | Config | Settings: `jwt_secret` (**no hardcoded value** — a random per-process default via `default_factory`; override with `MYLIFE_JWT_SECRET` in production), `jwt_algorithm` (`HS256`), `access_token_ttl_seconds` (`3600`), `jwt_issuer` (`mylife`). |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision creates `credentials`; `alembic check` clean. |
| NFR-3 | Testability | Hashing, token round-trip, `authenticate`, and endpoints tested (register→login→/auth/me; wrong password; expired/tampered token). |
| NFR-4 | Security | Argon2 defaults; short-lived tokens; secret from config; passwords/tokens never logged; uniform `401` (no user-enumeration signal on login). |

## 5. API & event contracts

```
POST /users   (evolved)  body adds "password"
  { "email": "...", "display_name": "...", "password": "min 8 chars", "household_id": null }
  201 -> User    409/422 as before

POST /auth/login   (application/x-www-form-urlencoded)
  username=<email>&password=<password>
  200 -> { "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600 }
  401 -> invalid credentials

GET /auth/me   Authorization: Bearer <jwt>
  200 -> User    401 -> unauthenticated
```

```python
def hash_password(password: str) -> str: ...
def verify_password(password: str, password_hash: str) -> bool: ...
def create_access_token(user_id: UUID, *, now: datetime) -> str: ...
def decode_access_token(token: str) -> TokenClaims: ...   # raises TokenError

def get_current_user(...) -> User: ...   # FastAPI dependency
```

- **No new event type.** (`UserRegistered` from `T2.1` is unchanged; auth events
  like login are audit concerns for `T2.4`.)

## 6. Data model & migration strategy

- SQLAlchemy `CredentialRow` on `Base` (table `credentials`). Proposed layout:
  `src/mylife/identity/security.py` (hashing + JWT), `CredentialRow` in
  `identity/models.py`, `authenticate` in `identity/service.py`, and
  `src/mylife/api/auth.py` (login, `/auth/me`, `get_current_user`), registered in
  the app factory.
- New Alembic revision `0007_credentials`; `env.py` already imports identity
  models. `alembic check` clean.
- **Dependencies added:** `pyjwt` (HS256 — needs no `cryptography`) and
  `argon2-cffi` (Argon2 hashing).

## 7. Privacy, consent, access-control & retention

- Passwords are stored only as Argon2 hashes; plaintext and tokens are never
  logged. Login returns a uniform `401` regardless of whether the email exists
  (no account enumeration).
- The JWT secret is configuration, defaulting to a **random per-process** value
  (no hardcoded secret); production must set `MYLIFE_JWT_SECRET` (shared across
  processes). Tokens are short-lived (default 1h).
- `get_current_user` is the least-privilege seam: subsequent tasks replace
  `user_id` parameters with the authenticated identity and enforce consent
  (`T2.3`).

## 8. Test plan

- **Hashing (FR-2):** `verify_password` accepts the right password, rejects a
  wrong one; the hash is not the plaintext.
- **Token (FR-6/AC4):** round-trip decodes `sub`/claims; an expired token (past
  `exp`) and a tampered/garbage token raise `TokenError`.
- **Register+login (AC1/AC2):** `POST /users` with a password, then
  `POST /auth/login` → token; wrong password → `401`.
- **Protected route (AC3):** `GET /auth/me` with the token → the user; without/
  with a bad token → `401`.
- **Migration (NFR-2):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T2.1`; adds `pyjwt`, `argon2-cffi`.
- **Open decisions (resolved for this spec):**
  - *Libraries.* → **PyJWT (HS256)** — avoids the `cryptography` Rust binding
    used by RS/ES; **Argon2 (`argon2-cffi`)** — cffi-based, no Rust; both fit the
    environment and are OIDC-upgradeable later (RS256).
  - *Password at registration.* → **Required now** (evolves `T2.1`): user +
    credential created atomically. `T2.1` tests updated to pass a password.
  - *Secret handling.* → **Random per-process default** via `default_factory`
    (no hardcoded secret); prod sets `MYLIFE_JWT_SECRET`.
  - *Endpoint retrofit.* → **Deferred**: this task ships the dependency and
    `/auth/me`; replacing `user_id` params with the authenticated user across
    timeline/briefing lands with consent (`T2.3`) to keep this PR focused.
- **Risks:**
  - *Per-process secret in multi-worker prod* — mitigated by requiring
    `MYLIFE_JWT_SECRET`; documented.
  - *No refresh/logout yet* — acceptable for v1 (short TTL); future work.
- **Future work:** refresh tokens/logout, password reset, MFA, RS256/OIDC,
  roles/permissions, and the endpoint retrofit + consent gating (`T2.3`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints registered/in OpenAPI (Swagger "Authorize" works); migration reviewed; backlog + spec status updated; `T2.1` spec notes the password evolution.
- [ ] Passwords hashed (Argon2), secret from config, nothing sensitive logged, uniform 401.
