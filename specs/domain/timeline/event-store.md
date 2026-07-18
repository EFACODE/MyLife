# Spec: Append-only event store (`T1.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/core/events/store.py`, migration `0002`, tests in `tests/test_event_store.py`)
- **Evolution:** `T1.4` added a nullable `raw_record_id` column (migration `0003`) carried through `append`/reads/`StoredEvent`/`rehydrate`.
- **Backlog task:** `T1.2` — [issue #15](https://github.com/EFACODE/MyLife/issues/15)
- **Bounded context:** Timeline (shared kernel)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1` (Life Event envelope), `T0.7` (Alembic)

## 1. Purpose & business context

Life Events must be **durably stored and never rewritten**. This task adds the
append-only store: the `events` table plus a repository that can **append** an
event and **read a stream** of events back, in stable order, with no way to
update or delete. It is the persistence substrate the event bus (`T1.3`),
provenance link (`T1.4`), corrections (`T1.5`) and every projection depend on.

## 2. Scope

- **In scope:**
  - An `events` table (SQLAlchemy model + Alembic migration).
  - A repository with exactly two capabilities: `append` and read
    (`read_stream` for one user; `read_all` for projections).
  - Stable global ordering for deterministic replay.
  - Idempotent append: re-appending the same `event_id` is rejected.
  - Persisting the full `T1.1` envelope; reading back a `StoredEvent`
    (envelope metadata + `payload` as a JSON mapping) with an opt-in helper to
    rehydrate into a typed event model.
- **Out of scope (later tasks):**
  - Publishing appended events (`T1.3`).
  - Raw-record provenance storage/linkage (`T1.4`).
  - Corrections / `EventCorrected` (`T1.5`).
  - A global event-type registry for automatic typed rehydration (future work).
  - Any query API surface (`T3.1`).

## 3. User stories & acceptance criteria

- As a **domain/producer**, I want to append an event and trust it is stored
  immutably and exactly once.
  - **AC1:** `append(event)` persists all envelope fields and the payload;
    reading the stream returns an equal event.
  - **AC2:** Appending an event whose `event_id` already exists raises a
    well-defined duplicate error and stores nothing new.
- As a **projection/consumer**, I want to read a user's events in a stable
  order so replay is deterministic.
  - **AC3:** `read_stream(user_id)` returns that user's events ordered by a
    monotonic global sequence, and never returns another user's events.
  - **AC4:** `read_all()` returns every event across users in global-sequence
    order (for building projections).
- As a **platform maintainer**, I want the store to be structurally
  append-only.
  - **AC5:** The repository exposes no update or delete method; history can only
    grow.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `events` stores one row per Life Event with columns: `global_seq` (monotonic, PK for ordering), `event_id` (UUID, unique), `user_id` (UUID), `event_type`, `occurred_at`, `recorded_at`, `schema_version`, `source`, `correlation_id`, `payload` (JSON). |
| FR-2 | Functional | `global_seq` is a database-assigned, strictly increasing integer establishing total append order. |
| FR-3 | Functional | `event_id` has a unique constraint; a second append with the same id raises `DuplicateEventError` and commits nothing. |
| FR-4 | Functional | `append(event: LifeEvent) -> StoredEvent` serializes the envelope and payload and inserts one row. |
| FR-5 | Functional | `read_stream(user_id, *, limit, after_seq) -> list[StoredEvent]` returns that user's events in ascending `global_seq`, supporting simple keyset pagination via `after_seq`. |
| FR-6 | Functional | `read_all(*, limit, after_seq) -> list[StoredEvent]` returns events across all users in ascending `global_seq`. |
| FR-7 | Functional | `StoredEvent` exposes every envelope field plus `global_seq` and `payload` as a read-only mapping, and a `rehydrate(model_type)` helper returning a typed `LifeEvent` subclass. |
| FR-8 | Functional | The repository exposes **no** update or delete operation. |
| FR-9 | Functional | Indexes support the read patterns: `(user_id, global_seq)` and `event_id` (unique). `occurred_at` indexed for later time queries. |
| FR-10 | Functional | Datetimes persist and read back as timezone-aware UTC (per T1.1). |
| NFR-1 | Portability | Works on both PostgreSQL (JSONB) and SQLite (JSON) via SQLAlchemy's `JSON` type; tests run on SQLite. |
| NFR-2 | Typing | Passes `mypy --strict`; `StoredEvent` payload typing is explicit. |
| NFR-3 | Migration | A real Alembic migration creates the table; `alembic check` reports no drift (env.py imports the model). |
| NFR-4 | Integrity | Appends are atomic: on any failure (e.g. duplicate) the transaction leaves the store unchanged. |

## 5. API & event contracts

No HTTP API. Python contract (illustrative signatures):

```python
class DuplicateEventError(Exception): ...

class StoredEvent(BaseModel):        # frozen
    global_seq: int
    event_id: UUID
    user_id: UUID
    event_type: str
    occurred_at: datetime            # UTC
    recorded_at: datetime            # UTC
    schema_version: int
    source: str
    correlation_id: str
    payload: Mapping[str, object]
    def rehydrate(self, model_type: type[EventT]) -> EventT: ...

class EventStore:
    def __init__(self, session: Session) -> None: ...
    def append(self, event: LifeEvent[BaseModel]) -> StoredEvent: ...
    def read_stream(self, user_id: UUID, *, limit: int = 100,
                    after_seq: int | None = None) -> list[StoredEvent]: ...
    def read_all(self, *, limit: int = 100,
                 after_seq: int | None = None) -> list[StoredEvent]: ...
```

- A "stream" in this task is a **user's timeline** (keyed by `user_id`). If
  finer-grained streams are needed later, a nullable `stream_id` can be added
  without breaking this contract.

## 6. Data model & migration strategy

- SQLAlchemy model `EventRow(Base)` (table `events`), mapped onto
  `mylife.db.base.Base`. Proposed location: `src/mylife/core/events/store.py`.
- `payload` stored with SQLAlchemy `JSON` (JSONB on Postgres, JSON on SQLite).
- New Alembic revision `0002_create_events_table` (autogenerated then
  reviewed). `migrations/env.py` imports the model so autogenerate/`alembic
  check` see it.
- Append-only is enforced at the repository layer (no update/delete methods). A
  DB-level guard (trigger/permission) is deferred; noted as future hardening.

## 7. Privacy, consent, access-control & retention

- Rows are personal data keyed by `user_id`; `read_stream` is always
  user-scoped so one user's events cannot leak into another's read (AC3).
- The store persists payloads as given; payload-level minimization/consent is
  the producing domain's responsibility (`T2.3`). No payload contents are
  logged.
- Deletion/export for data-subject rights is `T2.5`; the store stays
  append-only, so those flows operate through dedicated, audited paths rather
  than ad-hoc row deletes.

## 8. Test plan

Integration tests against an in-memory/temp SQLite database (no network):

- **Round-trip (AC1):** append then `read_stream` returns an equal event;
  payload and UTC datetimes preserved (FR-4, FR-10).
- **Ordering (AC3/AC4):** multiple appends read back in `global_seq` order;
  `read_all` spans users; `read_stream` filters to one user.
- **Isolation (AC3):** a second user's events never appear in the first user's
  stream.
- **Duplicate (AC2/FR-3):** re-appending the same `event_id` raises
  `DuplicateEventError` and adds no row (count unchanged).
- **Pagination (FR-5):** `after_seq`/`limit` return the expected slice.
- **Append-only (AC5/FR-8):** assert `EventStore` has no `update`/`delete`
  attribute.
- **Rehydrate (FR-7):** `StoredEvent.rehydrate(LifeEventRecorded)` yields the
  original typed event.
- **Migration (NFR-3):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T1.1` envelope; `mylife.db.base` (engine/session/Base);
  Alembic (`T0.7`).
- **Open decisions (resolved for this spec):**
  - *Stream granularity.* → **User-scoped** stream now; optional `stream_id`
    later.
  - *Typed rehydration.* → **Opt-in** via `StoredEvent.rehydrate(model_type)`;
    no global registry yet (avoids coupling the kernel to every domain).
  - *Ordering key.* → **DB-assigned `global_seq`** (monotonic) rather than
    relying on timestamps, which can collide or arrive out of order.
- **Risks:**
  - *SQLite vs Postgres JSON differences* — mitigated by SQLAlchemy `JSON` and
    running tests on SQLite while targeting Postgres in deployment.
  - *`global_seq` gaps under rollback* — acceptable; only ordering matters, not
    contiguity.
- **Future work:** DB-level append-only enforcement; typed-event registry;
  batch append; the read/query API (`T3.1`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Migration reviewed; backlog + spec status updated.
- [ ] Append-only guarantee verified (no update/delete surface); no payload/secret logging.
