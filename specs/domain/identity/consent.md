# Spec: Consent model + enforcement (`T2.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/identity/consent.py`, `src/mylife/api/consent.py`, migration `0009`, tests in `tests/test_consent.py` + `tests/test_consent_api.py`)
- **Backlog task:** `T2.3` — [issue #11](https://github.com/EFACODE/MyLife/issues/11)
- **Bounded context:** Identity
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T2.1`/`T2.2` (identity + auth), `T3.4` (connector runner seam)

## 1. Purpose & business context

Users must **explicitly consent** before the platform ingests from a source. This
task adds **granular per-scope consent** — recorded as immutable
`ConsentGranted`/`ConsentRevoked` events with a current-state projection — and an
**enforcement gate** the connector runner checks before ingesting (the seam
`T3.4` left open). It also makes consent the **first authenticated surface**: a
user manages their own consent via the `get_current_user` dependency (`T2.2`).

## 2. Scope

- **In scope:**
  - `ConsentGranted`/`ConsentRevoked` events + a `consents` projection (current
    state per `(user, scope)`).
  - `ConsentService`: `grant`, `revoke`, `is_granted`, `list_consents`.
  - A `ConsentGate` the `ConnectorRunner` can enforce before ingesting
    (`ConsentRequiredError` when absent).
  - Authenticated endpoints: `POST /consents`, `DELETE /consents/{scope}`,
    `GET /consents` (current user only).
- **Out of scope (later):**
  - Consent expiry/versioning, consent receipts/audit trail UI (`T2.4` audit
    records the events), purpose-based consent taxonomies.
  - Retrofitting **all** endpoints to enforce consent — this task wires
    connector ingestion; broader enforcement follows per feature.

## 3. User stories & acceptance criteria

- As a **user**, I grant/revoke consent for a source and see my current consents.
  - **AC1:** `POST /consents {scope}` (authenticated) records consent and emits
    `ConsentGranted`; `GET /consents` lists it as granted.
  - **AC2:** `DELETE /consents/{scope}` emits `ConsentRevoked`; the scope then
    reads as not granted. Re-granting works (new event, state granted again).
  - **AC3:** These endpoints require a valid bearer token (`401` otherwise) and
    operate only on the **authenticated** user (no cross-user access).
- As the **platform**, I refuse ingestion without consent.
  - **AC4:** When the `ConnectorRunner` is given a `ConsentGate`, syncing a source
    the user has **not** granted raises `ConsentRequiredError` and ingests
    nothing; a granted source proceeds normally.
- As a **maintainer**, I want consent history preserved.
  - **AC5:** Grant/revoke are immutable events; the `consents` table is a derived
    current-state projection (rebuildable), never the source of truth.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Events `identity.consent_granted` / `identity.consent_revoked` (`schema_version = 1`, payload `{scope}`), appended (`T1.2`) and published (`T1.3`), commit-before-publish. |
| FR-2 | Functional | Table `consents` (projection): `(user_id, scope)` unique, `granted` (bool), `updated_at` (UTC). |
| FR-3 | Functional | `ConsentService(session, bus)`: `grant(user_id, scope, *, now, correlation_id)`, `revoke(...)` — each emits the event and upserts the projection in one transaction; `is_granted(user_id, scope) -> bool`; `list_consents(user_id) -> list[Consent]`. |
| FR-4 | Functional | `scope` is a non-empty string (typically a connector `source`, e.g. `"calendar"`); normalized (trimmed). |
| FR-5 | Functional | A `ConsentGate` protocol (`is_granted(user_id, scope) -> bool`); `ConsentService` satisfies it. |
| FR-6 | Functional | `ConnectorRunner.sync(connector, context, *, consent=None)`: when `consent` is provided and `consent.is_granted(user_id, connector.source)` is false, raise `ConsentRequiredError` before any ingestion. When `consent` is `None`, no gate is applied (dev/test; the worker wires a real gate). |
| FR-7 | Functional | Endpoints (authenticated via `get_current_user`): `POST /consents` (201), `DELETE /consents/{scope}` (204), `GET /consents` (200, list); all scoped to the current user. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision creates `consents`; `alembic check` clean. |
| NFR-3 | Testability | Service (grant/revoke/is_granted, event emission), runner enforcement, and endpoints (auth required, grant→list→revoke) tested. |
| NFR-4 | Security | Consent is per authenticated user; scopes not logged as sensitive; enforcement fails closed (no consent ⇒ no ingest). |

## 5. API & event contracts

```
POST /consents          Authorization: Bearer <jwt>   body { "scope": "calendar" }
  201 -> Consent   401 -> unauthenticated
DELETE /consents/{scope}  Authorization: Bearer <jwt>
  204            401 -> unauthenticated
GET /consents           Authorization: Bearer <jwt>
  200 -> [Consent]

Consent = { "scope": "calendar", "granted": true, "updated_at": "..." }
```

```python
class ConsentGate(Protocol):
    def is_granted(self, user_id: UUID, scope: str) -> bool: ...


class ConsentRequiredError(Exception): ...  # raised by ConnectorRunner
```

- **Events produced:** `ConsentGranted`, `ConsentRevoked` (Identity context).

## 6. Data model & migration strategy

- `ConsentRow` (table `consents`) on `Base`; unique `(user_id, scope)`. Events +
  service in `src/mylife/identity/consent.py`; `ConsentGate`/`ConsentRequiredError`
  in `src/mylife/connectors/base.py` (structural protocol — no import cycle);
  endpoints in `src/mylife/api/consent.py` (registered in the app factory).
- New Alembic revision `0008_consents`; `env.py` already imports identity models
  (add the consent model to that import). `alembic check` clean.
- The `sync_connector` worker task passes a `ConsentService` as the gate.

## 7. Privacy, consent, access-control & retention

- Consent is the control surface for the whole platform: enforcement **fails
  closed** (no explicit grant ⇒ no ingestion when a gate is present).
- Endpoints operate only on the authenticated user; no `user_id` parameter.
- Grant/revoke are immutable events (auditable in `T2.4`); the projection is
  rebuildable and safe to drop on erasure (`T2.5`).

## 8. Test plan

- **Grant/revoke/state (AC1/AC2/FR-3):** grant → `is_granted` true + event
  emitted/published; revoke → false + event; re-grant → true.
- **Enforcement (AC4/FR-6):** runner with a gate refuses an ungranted source
  (`ConsentRequiredError`, nothing ingested); a granted source ingests; no gate
  ⇒ ingests (back-compat).
- **Endpoints (AC1–AC3/FR-7):** authenticated grant→`GET`→revoke; unauthenticated
  → `401`.
- **Migration (NFR-2):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T2.1`/`T2.2`, `T3.4` (runner), event kernel.
- **Open decisions (resolved for this spec):**
  - *State model.* → **Events are source of truth; `consents` is a derived
    current-state projection** (mirrors T3.3's derived-data pattern).
  - *Enforcement wiring.* → **Optional `ConsentGate` on `sync`** (default `None`
    keeps existing callers/tests working); the worker/composition root injects a
    real gate. Not made mandatory to avoid a breaking signature change.
  - *Consent surface.* → **Authenticated, current-user only** (first real use of
    `get_current_user`); `scope` is a free-form string (typically a connector
    `source`).
  - *Fail closed.* → When a gate is present, absence of consent blocks ingestion.
- **Risks:**
  - *Runner callers that forget to pass a gate* ingest without consent — mitigated
    by wiring the gate in the worker and documenting it; a future task can make
    the gate mandatory once all callers pass one.
  - *Scope sprawl* — mitigated by using connector `source` names; a taxonomy can
    come later.
- **Future work:** consent expiry/versioning, purpose taxonomies, mandatory gate,
  broader per-endpoint enforcement, and export/erasure of consent (`T2.5`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status updated.
- [ ] Enforcement fails closed; grant/revoke are immutable events; projection rebuildable.
