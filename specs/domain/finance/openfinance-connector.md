# Spec: Open Finance connector — Pierre Finance (`T4.9`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.9` — Open Finance connector (Safra, XP via aggregator)
  (see [`myLife-indice-tarefas.md`](../../../myLife-indice-tarefas.md))
- **Bounded context:** Finance (ingestion)
- **Author / date:** Claude Code / 2026-09-23
- **Depends on:** `T3.4` (connector framework), `T4.1` (finance context/accounts),
  `T2.2` (auth), `T2.3` (consent enforcement), `T4.9`'s own
  `specs/domain/identity/third-party-credentials.md` (`CredentialVault`)

## 1. Purpose & business context

Bring **bank and credit-card transactions** into Finance automatically,
without a manual CSV export, via **Pierre Finance** — a Brazilian Open Finance
aggregator (`https://www.pierre.finance`) that exposes already-connected
accounts and transactions over a REST API.

**Important, and central to this design:** Pierre Finance's API has **no
endpoint to connect a bank account**. The user links their bank(s) to Pierre
*inside Pierre's own product* (a WhatsApp flow, or `pierre.finance/connect`) —
our API only *reads back* what Pierre has already aggregated, authenticated
with a per-user Pierre **API key** (`Authorization: Bearer sk-...`, from
`pierre.finance/api-key`). So "connecting" a bank in My Life means: the user
pastes their Pierre API key into My Life once (`CredentialVault`, see
`specs/domain/identity/third-party-credentials.md`); from then on, `POST
/finance/connectors/openfinance/sync` (or a future scheduled worker run) pulls
accounts + transactions and imports them via the `T3.4` `ConnectorRunner`,
exactly like the CSV connectors (`T4.2`, `T3.5`) but without a file upload.

## 2. Scope

- **In scope:**
  - Storing/removing the user's Pierre API key (`CredentialVault`, provider
    `"pierre_finance"`).
  - `PierreFinanceConnector` (`source = "openfinance"`) implementing the
    `T3.4` `Connector` contract:
    - Fetches the user's accounts (`GET /tools/api/get-accounts`) and
      auto-creates/links a My Life `Account` per Pierre account (no manual
      account-mapping step).
    - Fetches transactions for a trailing window (`GET
      /tools/api/get-transactions`, `includeStatus=POSTED` only — see §9) and
      normalizes each into an `OpenFinanceTransactionImported` event.
    - Emits one `PositionValued(source="openfinance")` per account per sync
      from the account's current balance, keeping net worth (`T4.3`) current
      without the user recording valuations by hand.
  - `POST /finance/connectors/openfinance/sync` — authenticated,
    consent-gated (`"openfinance"`), synchronous (mirrors `T4.2`'s import
    endpoint) manual trigger.
  - `GET/POST/DELETE /finance/connectors/openfinance/credentials` — check
    connection status / store / remove the Pierre API key (the `GET` never
    returns the secret itself — see §5).
  - A web console section (Finanças → Configurações) to connect/disconnect
    and trigger a manual sync, mirroring the bank CSV import section.
- **Out of scope (later):**
  - Scheduled/periodic sync (Celery beat) — the connector is written so a
    worker *can* run it (its `fetch` needs only `(source, user_id)`, like
    `T3.4` intends for pull connectors), but registering it for automatic
    background runs is deferred, same call the bank connector spec made for
    live bank APIs (`bank-connector.md` §9).
  - Bill/installment import (`get-bills`, `get-installments`) — transactions
    and balances only, per the backlog's "checking + credit-card accounts."
  - Automatic categorization beyond passing through Pierre's own `category`
    field as given (rule-based re-categorization is `T4.10`).
  - Multi-currency accounts (Pierre is BRL-first; see §9).
  - Per-institution consent scopes (single `"openfinance"` scope covers the
    whole connector — see §9 and the vault spec's §9).

## 3. User stories & acceptance criteria

- As a **user**, I connect my already-aggregated bank accounts to My Life by
  pasting my Pierre API key once.
  - **AC1:** `POST /finance/connectors/openfinance/credentials {"api_key":
    "sk-..."}` (authenticated) stores the key; a second call replaces it.
  - **AC2:** `DELETE /finance/connectors/openfinance/credentials`
    disconnects (future syncs fail with "not connected" until reconnected).
  - **AC2b:** `GET /finance/connectors/openfinance/credentials` returns
    `{"connected": bool, "updated_at": …|null}` reflecting the current state —
    never the key itself — so the web console can show a connected/not-
    connected indicator without ever handling the secret after it's sent.
- As a **user**, I sync my transactions and see them in My Life.
  - **AC3:** `POST /finance/connectors/openfinance/sync` (authenticated,
    consent `"openfinance"` granted, key stored) creates/links one `Account`
    per Pierre account (first sync) and imports each fetched transaction as
    `OpenFinanceTransactionImported`, plus a `PositionValued` per account.
  - **AC4:** Transactions and the updated balance appear in `GET
    /finance/transactions` and `GET /finance/net-worth`.
  - **AC5:** Re-running sync is idempotent — unchanged transactions/balances
    are skipped as duplicate raw records (`T3.4`/`T1.4` content addressing);
    nothing double-counts net worth.
- As the **platform**, I keep this consented, scoped, and safe when Pierre or
  the user's setup is not ready.
  - **AC6:** Sync without consent for `"openfinance"` → `403`; nothing
    ingested.
  - **AC7:** Sync without a stored Pierre API key → `409` with a clear
    "connect your Pierre Finance account first" message.
  - **AC8:** A Pierre API error (expired key, no active subscription, 5xx)
    surfaces as `502` with the upstream error, not a silent no-op or `500`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `PierreFinanceClient`: thin `httpx`-based client for `GET /tools/api/get-accounts` and `GET /tools/api/get-transactions?startDate=&endDate=&includeStatus=POSTED&format=raw`, Bearer-authenticated, base URL `https://www.pierre.finance` (overridable via settings for tests/sandboxes). |
| FR-2 | Functional | `PierreFinanceConnector(session, vault, client, *, now, lookback_days=30)`, `source = "openfinance"`, implementing the `T3.4` `Connector` protocol. |
| FR-3 | Functional | `fetch`: reads the caller's API key from `CredentialVault`; raises `MissingCredentialError` if none is stored (fails the sync, mapped to `409` at the endpoint). Calls `get-accounts`, upserts a My Life `Account` per Pierre account (matched on `(user_id, external_source="openfinance", external_id=accountId)`), then calls `get-transactions` for `[now - lookback_days, now]`. Emits one `RawPayload` per transaction (`kind="transaction"`, the verbatim Pierre transaction dict plus the resolved My Life `account_id`) and one `RawPayload` per account (`kind="balance"`, the account's current balance/currency plus the resolved `account_id`). |
| FR-4 | Functional | `normalize`: for `kind="balance"`, yields `PositionValued(source="openfinance", payload=PositionPayload(account_id, value_minor, currency))`. For `kind="transaction"`, validates and maps the stored Pierre row into `FinancePayload` (see §9 for the exact field mapping and its documented uncertainty) and yields `OpenFinanceTransactionImported`. |
| FR-5 | Functional | Money conversion: Pierre returns amounts as **decimal reais** (e.g. `150.00`), never minor units; the connector converts via `Decimal(str(amount)) * 100` rounded to the nearest integer cent — never a raw `float * 100` (avoids binary float rounding artifacts on money). |
| FR-6 | Functional | New event `OpenFinanceTransactionImported` (`finance.openfinance_transaction_imported`, schema v1, payload = `FinancePayload`, same shape as `TransactionImported`) — a distinct type from the generic `TransactionImported`/`"bank"` so this data's provenance (aggregator-sourced, not a manual CSV) stays visible on the timeline and in evidence. Registered in `KIND_BY_TYPE` (kind `"openfinance_import"`) and `TRANSACTION_TYPES` so it appears in `GET /finance/transactions` and net worth/cash flow (`T4.3`) like any other transaction. |
| FR-7 | Functional | `Account` gains nullable `external_source`/`external_id` columns (unique together with `user_id` when set) so a Pierre account is only ever created once per user across syncs. |
| FR-8 | Functional | `POST /finance/connectors/openfinance/sync` (`get_current_user`): builds the connector, runs `ConnectorRunner.sync(..., consent=ConsentService(...))` synchronously; `ConsentRequiredError` → `403`; `MissingCredentialError` → `409`; `PierreApiError` → `502`. Returns a `SyncResult` view, like `T4.2`'s bank import endpoint. |
| FR-9 | Functional | `POST /finance/connectors/openfinance/credentials {api_key}` / `DELETE .../credentials` store/remove the key via `CredentialVault` under provider `"pierre_finance"`. Both require auth only (not consent — storing a key is not itself "ingesting"; the sync call is what's consent-gated, matching `T4.2`'s pattern of gating ingestion, not account setup). |
| FR-10 | Functional | `GET /finance/connectors/openfinance/credentials` returns `OpenFinanceCredentialStatus {connected, updated_at}` — auth only, never returns the secret. `connected` reflects whether the stored secret still *decrypts* (`CredentialVault.get(...)`), not merely whether a row exists: if `MYLIFE_CREDENTIAL_ENCRYPTION_KEY` ever changes (e.g. a deployment that never pinned it — see `Settings.credential_encryption_key` — defaults to a new random key every restart), every previously stored secret becomes permanently undecryptable even though its row/`updated_at` persists; reporting "connected" in that case strands the user, since the web console's "connected" branch (FR-11) hides the credential form. `updated_at` is only returned when `connected` is `true`. Backs the web console's connected/not-connected indicator (FR-11). |
| FR-11 | Functional | Web console (Finanças → Configurações → "Open Finance (Pierre Finance)"): not connected → a masked (password-style, with a "Mostrar"/"Ocultar" reveal toggle) API-key input + "Conectar" (`POST .../credentials`); connected → "Conectado desde `<data>`", a "Sincronizar agora" button (`POST .../sync`, shows the resulting counts on success and refreshes the Visão geral/Transações data; on failure shows a friendly message for `403`/`409`, or for any other status the backend's own `detail` text — e.g. the upstream Pierre API error — appended to the generic message, rather than a bare status code) and a "Desconectar" action (`DELETE .../credentials`). |
| FR-12 | Functional | When "Sincronizar agora" fails with `403` (no `"openfinance"` consent), the web console also shows a "Conceder consentimento e sincronizar" button that calls the generic `POST /consents {scope: "openfinance"}` (`T10.2`) and immediately retries the sync — so granting consent and completing the first sync no longer requires navigating away to the Consentimentos page and typing the scope by hand. |
| NFR-1 | Security | Consent scope `"openfinance"` enforced fail-closed on sync (`T2.3`); the Pierre API key is never logged, never echoed back by any endpoint (including the status check, FR-10), stored only via `CredentialVault`. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; adds `httpx` (already a dev/test dependency) as a runtime dependency and `cryptography` (via the vault spec). |
| NFR-3 | Testability | `PierreFinanceClient` takes an injectable `httpx.Client`/transport so tests run against `httpx.MockTransport` — no real network call in the test suite (consistent with this environment's network egress policy). Connector tested via `ConnectorRunner` on SQLite (sync → accounts auto-created, transactions + balance queryable, provenance-linked, idempotent on re-run); endpoint tested (auth, consent `403`, missing-credential `409`, happy path). |

## 5. API & event contracts

```
GET /finance/connectors/openfinance/credentials     (auth only)
  -> 200 { "connected": true, "updated_at": "2026-09-24T12:00:00Z" }

POST /finance/connectors/openfinance/credentials   (auth only)
  { "api_key": "sk-..." }
  -> 204

DELETE /finance/connectors/openfinance/credentials  (auth only)
  -> 204

POST /finance/connectors/openfinance/sync   (auth + consent "openfinance")
  -> 201 { "source": "openfinance", "raw_ingested": 7, "events_created": 7, "skipped_duplicates": 0 }
  401 (no token) · 403 (no "openfinance" consent)
  · 409 (no Pierre API key stored) · 502 (Pierre API error)
```

- **Events produced:**
  - `OpenFinanceTransactionImported` (`source = "openfinance"`), one per
    imported transaction, provenance-linked to its raw record.
  - `PositionValued` (`source = "openfinance"`), one per account per sync.

## 6. Data model & migration strategy

- **Migration `0025`** (shared with the vault spec): `third_party_credentials`
  table.
- **Migration `0026`**: `accounts` gains nullable `external_source` (`String`)
  and `external_id` (`String`) columns, plus a unique constraint on
  `(user_id, external_source, external_id)` (partial/where-not-null in
  practice, enforced at the application level for SQLite compatibility — see
  `FinanceService.get_or_create_external_account`). No change to the
  `events`/`raw_records` tables — reuses `T1.2`/`T1.4` as-is.

## 7. Privacy, consent, access-control & retention

- Finance is highly sensitive: both endpoints are authenticated and
  user-scoped; **sync is consent-gated** on scope `"openfinance"`
  (fail-closed, `T2.3`), same posture as `"bank"` (`T4.2`) and `"health"`
  (`T4.5`).
- The Pierre API key is encrypted at rest (`CredentialVault`) and never
  returned by any response, logged, or included in the data-subject export
  (`T2.5` — see the vault spec §7). Erasure removes the stored key
  (`third_party_credentials`) and every imported event/raw record, same as
  any other connector's data.
- Raw Pierre payloads (transaction dicts, account balances) are stored
  verbatim in `raw_records` — never logged — preserving the ADR's "external
  system stays authoritative for raw data" even though our mapping of that
  raw data into `FinancePayload` fields carries the uncertainty noted in §9:
  if a field-name assumption turns out wrong, the verbatim data is still
  there to re-derive from, nothing is lost.

## 8. Test plan

- **Vault-gated sync (AC6/AC7):** no consent → `403`, nothing ingested; no
  API key stored → `409`, nothing ingested; both satisfied → succeeds.
- **First sync creates accounts (AC3):** a fake Pierre API (via
  `httpx.MockTransport`) returning two accounts + transactions for each →
  two `Account` rows created (matched by `external_id`), transactions linked
  to the right account, one `PositionValued` per account.
- **Idempotency (AC5):** re-running sync with the same fake responses →
  `skipped_duplicates` covers every row, no duplicate accounts, no double
  counting in `GET /finance/net-worth`.
- **Balance change (AC4):** a second sync with a different `accountBalance`
  → a fresh `PositionValued` (content-addressed, so only *changed* balances
  produce a new raw record/event).
- **Bad/missing transaction fields:** a synthetic transaction missing every
  recognized amount/date/description key → `ValueError`, batch rolls back
  (fail-closed, consistent with `T4.2`/`T3.5`).
- **Upstream error (AC8):** a fake 401/500 from Pierre → `PierreApiError` →
  endpoint returns `502`.
- **Credential status (AC2b, FR-10):** not connected → `{connected: false,
  updated_at: null}`; after connecting → `connected: true` with a timestamp;
  after disconnecting → back to `false`/`null`.
- **Credential status fails closed on key rotation (FR-10):** connect, then
  rotate `MYLIFE_CREDENTIAL_ENCRYPTION_KEY` so the stored secret no longer
  decrypts (its row still exists) → status reports `{connected: false,
  updated_at: null}`, and sync still returns `409` (not a silent success
  with a bad key).
- **Web console (FR-11):** not connected → the API-key form, masked by
  default with a working reveal toggle; submitting calls `connectOpenFinance`
  and refreshes status. Connected → "Sincronizar agora" shows the resulting
  counts and refreshes the accounts/transactions lists, a `403` shows the
  consent hint, a `409` shows the "connect first" hint, any other status
  (e.g. a `502` from the Pierre API) shows the backend's `detail` text
  rather than a generic "could not sync" with no explanation; "Desconectar"
  calls `disconnectOpenFinance` and refreshes status back to the form.
- **API client surfaces `detail` (FR-11):** `ApiClient`'s error path reads
  the failed response body's `detail` field and uses it as the thrown
  `ApiError`'s message when present, falling back to the generic
  `"<method> <path> -> <status>"` only when the body has none — so any
  backend-provided explanation (Pierre API errors, consent/credential
  hints, etc.) reaches the UI instead of being discarded.
- **Web console consent shortcut (FR-12):** a `403` on sync shows a
  "Conceder consentimento e sincronizar" button; clicking it calls
  `grantConsent("openfinance")` then re-runs the sync, landing on the same
  success state as a normal sync (no round trip through Consentimentos).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.4` framework, `T4.1` finance/accounts, `T4.3` net
  worth, `T2.2` auth, `T2.3` consent, this task's own `CredentialVault`
  (`specs/domain/identity/third-party-credentials.md`).
- **Open decisions (resolved for this spec):**
  - *No account-mapping step.* → Pierre accounts are auto-created/linked by
    `external_id` rather than asking the user to pick an existing My Life
    account, unlike `T4.2`'s CSV import (which targets a caller-chosen
    account). Justification: Pierre already knows the account's identity
    (bank, type, currency) and CSV import's "pick an account" step exists
    only because a CSV has no such metadata.
  - *Which transactions.* → `includeStatus=POSTED` only; `PENDING`
    transactions are excluded from v1 because their amount/category can still
    change before settling, and Life Events are immutable (re-importing a
    since-changed pending transaction under the same `external_id` would
    either silently keep stale data or require a correction event this spec
    doesn't design). Importing settled transactions only avoids that problem;
    pending-transaction support is future work if needed.
  - *Sync window, not a cursor.* → Pierre's `get-transactions` has no
    "since" cursor, only `startDate`/`endDate`. Each sync re-requests a
    trailing 30-day window; `T1.4` content addressing makes re-fetching
    already-imported transactions a no-op (`skipped_duplicates`), so this is
    correct, just not bandwidth-optimal. Acceptable for a manually-triggered
    v1; a stored per-user "last synced date" is future work if/when this runs
    on a schedule.
  - *Per-institution consent.* → the backlog mentions "per-institution/product
    consent scopes"; this spec uses a single `"openfinance"` scope because
    Pierre's API key already grants access to everything the user connected
    inside Pierre (there is no per-bank token to scope separately at our
    layer — see the vault spec §9). Finer scopes are future work only if a
    future aggregator exposes per-institution credentials.
  - *Distinct event type.* → `OpenFinanceTransactionImported` rather than
    reusing `TransactionImported(source="openfinance")`, per the backlog's
    explicit naming; the payload shape is identical to `FinancePayload`
    (no new fields needed — the event *type* itself is the provenance
    signal), keeping this a thin, low-risk addition to `finance/models.py`.
- **Risks (the important one first):**
  - **Pierre's `Transaction`/`Account` JSON schema was not published, and the
    original inferred mapping turned out wrong.** Pierre's own OpenAPI spec
    declares `"Transaction": {}` — an empty schema — and no prose on this
    integration's source documentation lists its fields either. The mapping
    was **verified on 2026-10-06 against a real `get-accounts`/
    `get-transactions` call with a live Pierre API key**, and the account
    fields originally guessed (`accountId`, `accountCurrencyCode`,
    `accountBalance`, `accountMarketingName`/`accountName`) were **all
    wrong** — real field names are `id`, `currencyCode`, `balance` (a numeric
    string, not a float), and `marketingName`/`name`. Before this fix,
    `_account_external_id` raised `ValueError` on the very first real
    account, so **no real sync ever succeeded**. The transaction→account
    link was also wrong (`accountId` vs. the real `account_id`,
    snake_case), which would have silently dropped every transaction even
    after the account fields were fixed. The transaction field names used for
    `amount`, `description`, `category`, `id` and `date` (first of
    `date`/`postDate`/`transactionDate` tried) were confirmed correct as-is
    against 209 real transactions; `postDate`/`transactionDate`/
    `merchantName`/`memo`/`transactionId` remain untested fallbacks, kept only
    as defensive extras. Mitigation already built in: raw payloads are stored
    verbatim (see §7) regardless of mapping accuracy, so a future field-name
    fix loses no data, only requires re-normalizing. Field-name misses fail
    loudly (`ValueError`, batch rolled back) rather than silently importing
    wrong data.
  - *Amount sign convention.* Assumed signed (debits negative, credits
    positive), matching this codebase's `FinancePayload.amount_minor`
    convention and common aggregator behavior (Pluggy/Belvo); the 2026-10-06
    verification confirmed `amount` is a signed float, consistent with this
    assumption, but the exact sign-per-transaction-type mapping was not
    exhaustively checked against every `type`/`operation_type` combination.
  - *Multi-currency.* The minor-unit conversion (FR-5) assumes 2 decimal
    places (correct for BRL, the only currency Pierre's docs show in
    examples); a future non-2-decimal currency would need a currency→exponent
    table (not built, since Pierre is BRL-first).
  - *Pierre-side subscription/plan gating.* Several Pierre endpoints require
    an "active subscription" on Pierre's side (independent of ours); a
    lapsed Pierre subscription surfaces as a `401`/`403` from Pierre, mapped
    to our `502` (AC8) rather than a confusing `500`.
- **Future improvements:** scheduled sync (Celery beat, registering the
  connector in `mylife.connectors.registry`), pending-transaction handling,
  bills/installments import, per-institution consent if Pierre exposes it,
  automatic categorization (`T4.10`) on top of Pierre's own categories, a
  "last synced at" cursor to shrink the re-fetch window.

## 10. Definition of Done

- [x] Spec approved and implementation traceable to it.
- [x] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; two new
      migrations apply cleanly (`alembic upgrade head` from empty).
- [x] Endpoints authenticated + consent-gated in OpenAPI; erasure and backlog
      status updated.
- [x] End-to-end proven against a mocked Pierre API (no real network call in
      CI); the Transaction-schema risk (§9) is documented, not hidden, and
      flagged to the user as needing live verification before production use.
- [x] Web console section (Finanças → Configurações) to connect/disconnect
      and trigger a sync; `npm test`/`lint`/`typecheck` green.
