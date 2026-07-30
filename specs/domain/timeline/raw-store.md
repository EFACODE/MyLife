# Spec: Raw ingestion store + provenance link (`T1.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/core/events/raw_store.py`, migration `0003`, tests in `tests/test_raw_store.py`)
- **Backlog task:** `T1.4` — [issue #17](https://github.com/EFACODE/MyLife/issues/17)
- **Bounded context:** Timeline (shared kernel)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1` (envelope), `T1.2` (event store), `T0.7` (Alembic)

## 1. Purpose & business context

A core architectural rule: **raw external data is kept separate from normalized
events, and the external system stays authoritative** for it. This task adds the
**raw ingestion store** — the original payloads exactly as received from a
source — and the **provenance link** that lets a normalized Life Event point
back to the raw record it was derived from. This is what makes every inference
auditable down to its source.

Connectors (later, `T3.4`/`T4.x`) will write raw records and then emit
normalized events referencing them; this task provides the store and the link,
not the connectors themselves.

## 2. Scope

- **In scope:**
  - A `raw_records` table + `RawRecordStore` repository: append-only `store`
    plus reads (`get`, `get_by_checksum`).
  - Content-addressed idempotency: a `(source, checksum)` uniqueness guard so
    the same payload from a source is not stored twice.
  - A **provenance field** added to the Life Event envelope
    (`raw_record_id: UUID | None`) and persisted by the event store (`T1.2`),
    with a migration.
- **Out of scope (later tasks):**
  - Connectors that produce raw records / the normalization pipeline
    (`T3.4`, `T4.x`).
  - Large/binary blob storage (that is object storage in Knowledge, `T6.1`).
  - Publishing/consuming (`T1.3`), corrections (`T1.5`).

## 3. User stories & acceptance criteria

- As a **connector author**, I want to persist a source payload immutably and
  get a stable id back, so normalized events can reference it.
  - **AC1:** `store(raw)` persists the payload and returns a `StoredRawRecord`
    with a `raw_record_id`; `get(id)` returns an equal record.
  - **AC2:** Storing the same `(source, checksum)` twice raises
    `DuplicateRawRecordError` and stores nothing new; `get_by_checksum` finds
    the existing one (supporting idempotent re-ingestion).
- As an **auditor**, I want a normalized event to reference its raw source.
  - **AC3:** A `LifeEvent` may carry `raw_record_id`; the event store persists
    and reads it back, and it defaults to `None` for manually-entered events.
- As a **platform maintainer**, I want raw data kept separate and immutable.
  - **AC4:** The raw store exposes no update or delete method; raw records live
    in their own table, distinct from `events`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `raw_records` with columns: `raw_record_id` (UUID, PK), `user_id` (UUID), `source` (str), `external_id` (str, nullable), `content_type` (str), `content` (JSON), `checksum` (str), `fetched_at` (UTC), `recorded_at` (UTC), `correlation_id` (str). |
| FR-2 | Functional | `checksum` is the SHA-256 hex of the canonical JSON serialization of `content`; computed by the store, not trusted from the caller. |
| FR-3 | Functional | Unique constraint on `(source, checksum)`; a duplicate `store` raises `DuplicateRawRecordError` atomically (nothing persisted). |
| FR-4 | Functional | `store(raw: RawRecord) -> StoredRawRecord` inserts one row; `RawRecord` is the caller-supplied input (no `raw_record_id`/`checksum`/`recorded_at`, which the store assigns). |
| FR-5 | Functional | `get(raw_record_id) -> StoredRawRecord \| None` and `get_by_checksum(source, checksum) -> StoredRawRecord \| None`. |
| FR-6 | Functional | The raw store exposes **no** update or delete operation. |
| FR-7 | Functional | The Life Event envelope gains `raw_record_id: UUID \| None = None` (provenance). Manual events leave it `None`. |
| FR-8 | Functional | The event store (`events` table) gains a nullable `raw_record_id` column; `append`/reads/`StoredEvent`/`rehydrate` carry it through. |
| FR-9 | Functional | Indexes: `(source, external_id)` and `user_id` on `raw_records`; `raw_record_id` unique already covers lookups by id. |
| FR-10 | Functional | `fetched_at`/`recorded_at` are timezone-aware UTC (per T1.1 rules); `recorded_at` defaults to now. |
| NFR-1 | Portability | Works on PostgreSQL (JSONB) and SQLite (JSON); tests on SQLite. |
| NFR-2 | Typing | Passes `mypy --strict`. |
| NFR-3 | Migration | One Alembic revision creates `raw_records` and adds `events.raw_record_id`; `alembic check` clean. |
| NFR-4 | Integrity | Store is append-only and atomic (duplicate leaves the store unchanged). |

## 5. API & event contracts

Illustrative (no HTTP API):

```python
class DuplicateRawRecordError(Exception): ...

class RawRecord(BaseModel):           # caller input (frozen)
    user_id: UUID
    source: str
    external_id: str | None = None
    content_type: str = "application/json"
    content: JsonValue               # structured payload as received
    fetched_at: datetime             # UTC
    correlation_id: str

class StoredRawRecord(BaseModel):     # frozen
    raw_record_id: UUID
    user_id: UUID
    source: str
    external_id: str | None
    content_type: str
    content: Mapping[str, object] | list[object] | str | int | float | bool | None
    checksum: str
    fetched_at: datetime             # UTC
    recorded_at: datetime            # UTC
    correlation_id: str

class RawRecordStore:
    def __init__(self, session: Session) -> None: ...
    def store(self, raw: RawRecord) -> StoredRawRecord: ...
    def get(self, raw_record_id: UUID) -> StoredRawRecord | None: ...
    def get_by_checksum(self, source: str, checksum: str) -> StoredRawRecord | None: ...
```

- **Envelope change:** `LifeEvent.raw_record_id: UUID | None = None`. This is an
  additive, backward-compatible field; existing events serialize with
  `raw_record_id: null`.

## 6. Data model & migration strategy

- SQLAlchemy model `RawRecordRow(Base)` (table `raw_records`), `content` via
  `JSON`. Proposed location: `src/mylife/core/events/raw_store.py`.
- Add nullable `raw_record_id` to `EventRow` (`events`).
- New Alembic revision `0003_raw_records_and_provenance`: creates `raw_records`
  (+ indexes/constraints) and adds `events.raw_record_id`. `migrations/env.py`
  already imports the events module; it will import the raw-store model too.
- Append-only enforced at the repository layer (no update/delete). DB-level
  guard deferred (future hardening).

## 7. Privacy, consent, access-control & retention

- Raw records are the most sensitive data (verbatim source payloads), keyed by
  `user_id`; the store never logs `content`.
- Keeping raw separate supports **source visibility** and **revocation**: a
  consent revocation or data-subject deletion (`T2.5`) can target raw records
  for a `(user_id, source)` through dedicated, audited paths — the store staying
  append-only means such changes are explicit operations, not ad-hoc deletes.
- Access to raw content is least-privilege; only ingestion/audit paths read it.

## 8. Test plan

Integration tests on SQLite:

- **Round-trip (AC1):** `store` then `get` returns an equal record; UTC
  datetimes and `content` preserved (FR-4, FR-10).
- **Checksum (FR-2):** identical `content` yields identical `checksum`;
  different content differs.
- **Dedup (AC2/FR-3):** second `store` of same `(source, checksum)` raises
  `DuplicateRawRecordError`; row count unchanged; `get_by_checksum` returns the
  first.
- **Append-only (AC4/FR-6):** `RawRecordStore` has no `update`/`delete`.
- **Provenance (AC3/FR-7/FR-8):** a `LifeEvent` with a `raw_record_id` is
  appended and read back with it; a manual event round-trips with `None`.
- **Migration (NFR-3):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T1.1` (envelope, extended here), `T1.2` (event store,
  extended here), `mylife.db.base`, Alembic.
- **Open decisions (resolved for this spec):**
  - *Idempotency key.* → **Content-addressed `(source, checksum)`**, so
    re-fetching an unchanged payload is a no-op; `external_id` is kept for
    source-native lookups but is not the uniqueness key (some sources lack one).
  - *Provenance location.* → **A field on the envelope** (`raw_record_id`),
    matching the brief ("normalized events reference raw_record_id + source"),
    rather than a side table.
  - *Content storage.* → **JSON** for structured/text payloads now; binary/large
    blobs belong to object storage (`T6.1`).
- **Risks:**
  - *Checksum canonicalization* (key order/encoding) must be deterministic —
    mitigated by serializing with sorted keys and tested explicitly.
  - *Large payloads in a JSON column* — acceptable for early sources; revisit
    with object storage when needed.
- **Future work:** DB-level append-only enforcement; raw-record retention &
  deletion flows (`T2.5`); connector ingestion that writes raw then emits
  normalized events (`T3.4`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Migration reviewed; backlog + spec status updated; T1.1/T1.2 docs note the envelope/store extension.
- [ ] Raw content never logged; append-only guarantee verified.
