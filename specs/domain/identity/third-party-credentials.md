# Spec: Third-party credential vault (`T4.9`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.9` — Open Finance connector (see
  [`myLife-indice-tarefas.md`](../../../myLife-indice-tarefas.md))
- **Bounded context:** Identity (shared platform capability, consumed by Finance)
- **Author / date:** Claude Code / 2026-09-23
- **Depends on:** `T2.2` (auth), `T0.2` (settings/config)

## 1. Purpose & business context

Connectors that pull from a live third-party API (starting with the Pierre
Finance Open Finance aggregator, `T4.9`) need a per-user secret — an API key —
to call that API on the user's behalf. Unlike the login credential (`T2.2`,
an Argon2 hash the platform never needs to read back), this is a **secret we
must recover in plaintext** to make outbound calls, so it must be encrypted at
rest rather than hashed. `CredentialVault` is the small, reusable, Identity-
owned capability that stores and returns these third-party secrets, so no
connector reimplements its own ad hoc secret storage or handles secrets in
memory-adjacent code paths (logging, exceptions) unsafely.

## 2. Scope

- **In scope:**
  - `CredentialVault`: `store`, `get`, `delete` for one secret per
    `(user_id, provider)`, encrypted at rest with a symmetric cipher keyed by a
    server-side secret (never the user's password, never derived from data the
    user controls).
  - A new `third_party_credentials` table (Identity-owned).
  - Erasure (`T2.5`) removes a user's rows on account deletion.
- **Out of scope (later):**
  - OAuth authorization-code flows / token refresh (Pierre Finance uses a
    long-lived API key the user copies in, not OAuth — see
    `openfinance-connector.md` §9). A future OAuth-based aggregator would add a
    `refresh_token`/`expires_at` shape; not needed today.
  - Per-institution credentials (one secret already scopes a user's *entire*
    Open Finance connection at the aggregator, not per-bank — see
    `openfinance-connector.md` §9 on the backlog's "per-institution" phrasing).
  - Secret rotation reminders / expiry notifications.
  - A generic multi-tenant KMS integration; a single server-side symmetric key
    from settings is the pragmatic v1 (see §7, §9).

## 3. User stories & acceptance criteria

- As the **platform**, I store a user's third-party API key so a connector can
  use it later without the user re-entering it every sync.
  - **AC1:** `store(user_id, provider, secret, now=...)` upserts one row per
    `(user_id, provider)`; the stored value is ciphertext, never the plaintext
    secret.
  - **AC2:** `get(user_id, provider)` returns the original plaintext secret
    (round-trips exactly) or `None` if none is stored.
  - **AC3:** `delete(user_id, provider)` removes the row (disconnect); a
    second call is a no-op (idempotent).
- As the **platform**, I never leak a stored secret.
  - **AC4:** The ciphertext column is unreadable without the server-side
    encryption key; no code path logs the plaintext secret or returns it from
    an HTTP response (write-only from the API's perspective — see
    `openfinance-connector.md` §5 for the endpoint contract).
  - **AC5:** Erasure (`T2.5`) deletes a user's `third_party_credentials` rows.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `ThirdPartyCredentialRow(user_id, provider)` composite primary key; one secret per provider per user. |
| FR-2 | Functional | `CredentialVault.store/get/delete` as in §3. |
| FR-3 | Functional | Encryption via `cryptography`'s `Fernet` (AES-128-CBC + HMAC, authenticated) keyed by `Settings.credential_encryption_key`. |
| NFR-1 | Security | The encryption key is never hardcoded; `Settings.credential_encryption_key` defaults to a random per-process value (dev/test convenience, mirrors `jwt_secret`) and **must** be set to a stable value via `MYLIFE_CREDENTIAL_ENCRYPTION_KEY` in any deployment that restarts processes or runs more than one, or previously stored secrets become unreadable. |
| NFR-2 | Security | Plaintext secrets never appear in logs, exceptions, or API responses. |
| NFR-3 | Typing/Deps | Passes `mypy --strict`; adds `cryptography` as a runtime dependency. |
| NFR-4 | Testability | Round-trip store/get, delete-then-get returns `None`, wrong-key decrypt fails closed (raises, not silently wrong data). |

## 5. API & event contracts

`CredentialVault` is a plain service class, not exposed directly over HTTP —
each connector's own endpoint (e.g. `POST /finance/connectors/openfinance/credentials`,
see `openfinance-connector.md` §5) calls it with its own `provider` string.
No events are emitted for storing a credential (it is operational
configuration, not a Life Event/business fact); the connector's own sync
still produces ordinary, evidence-linked Life Events.

## 6. Data model & migration strategy

New table, migration `0025`:

```
third_party_credentials
  user_id             uuid        not null
  provider            varchar     not null
  secret_ciphertext   varchar     not null   -- Fernet token (base64), never plaintext
  created_at          timestamptz not null
  updated_at          timestamptz not null
  primary key (user_id, provider)
```

Store: **derived/operational**, not raw or normalized event data — it is
infrastructure the platform needs to act on the user's behalf, analogous to
`credentials` (login) and distinct from both raw source payloads and Life
Events.

## 7. Privacy, consent, access-control & retention

- The vault itself does not enforce *consent* to use the secret (that is the
  connector's job via `ConsentGate`, `T2.3`) — it only stores/retrieves. A
  connector must still check consent before calling `vault.get(...)`.
- The encryption key is a deployment secret (like `jwt_secret`): set via
  environment variable, rotated by re-encrypting (out of scope for v1 — noted
  as a risk below), never committed to the repository.
- Erasure (`T2.5`) hard-deletes a user's row; there is no soft-delete/retention
  window for a third-party secret — once the user disconnects or their account
  is erased, the key value is gone (`DataSubjectService.erase`).
- The export bundle (`T2.5` `export()`) deliberately does **not** include the
  decrypted secret or ciphertext — only "is a credential configured for this
  provider" is a fact a user could reasonably see (not needed for `T4.9` v1;
  the connect/disconnect endpoints already tell the user their own state).

## 8. Test plan

- Round-trip: `store` then `get` returns the original plaintext (AC2).
- `get` for a provider never stored returns `None`.
- `delete` then `get` returns `None`; deleting twice does not raise (AC3).
- Storing twice for the same `(user_id, provider)` updates in place (no
  duplicate row) — `updated_at` changes.
- Ciphertext in the row is not equal to the plaintext and is not trivially
  recoverable without the key (assert the stored column bytes differ from the
  secret).
- Erasure removes the row (extends `test_data_subject.py`).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** none beyond settings/config; consumed first by `T4.9`'s
  Open Finance connector.
- **Open decisions (resolved for this spec):**
  - *Encryption scheme.* → symmetric `Fernet` with a single server-side key,
    not per-user keys or an external KMS — the simplest correct v1 for one
    self-hosted deployment; an external KMS is future work if/when the
    platform runs as a managed multi-tenant service.
  - *One secret per provider, not per institution.* → Pierre Finance's API key
    already scopes the user's whole Open Finance connection (they connect
    individual banks inside Pierre's own product, not through our API — see
    `openfinance-connector.md` §1). A future aggregator needing per-institution
    tokens would add rows keyed `(user_id, provider, institution_id)`; not
    needed now.
- **Risks:**
  - *Key rotation.* Rotating `MYLIFE_CREDENTIAL_ENCRYPTION_KEY` invalidates
    every stored secret (they become undecryptable) since there is no
    re-encryption tool yet. Mitigation: document this loudly in `.env.example`
    and treat rotation as "every user must reconnect," acceptable for v1's
    single external provider.
  - *Single key for all providers.* A key compromise affects every stored
    third-party secret at once. Acceptable for v1 (one provider, one
    deployment); revisit if/when more high-value tokens are stored.
- **Future improvements:** OAuth token shape (refresh token + expiry) for a
  future OAuth-based provider; key rotation tooling; per-institution rows if a
  future aggregator needs them.

## 10. Definition of Done

- [x] Spec approved and implementation traceable to it.
- [x] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [x] Migration applies cleanly; erasure updated; no secret ever logged or
      returned by an API response.
- [x] Backlog status updated.
