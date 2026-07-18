# Spec: Connector framework & contract (`T3.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T3.4` — [issue #22](https://github.com/EFACODE/MyLife/issues/22)
- **Bounded context:** Timeline (ingestion)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1`/`T1.2` (envelope, store), `T1.4` (raw store + provenance), `T1.3` (bus), `T0.9` (worker)

## 1. Purpose & business context

Everything after manual entry enters through a **connector**. This task builds
the reusable ingestion spine: a **ports/adapters contract** for connectors and
an idempotent **sync** that pulls from a source, writes **raw records** (`T1.4`),
normalizes them into **Life Events** (`T1.2`) linked back to their raw record
(provenance), and publishes them (`T1.3`) — runnable from a **worker** (`T0.9`).
The first concrete connector is `T3.5`; this task provides the framework and a
fake connector for tests.

## 2. Scope

- **In scope:**
  - A `Connector` protocol (`source`, `fetch`, `normalize`) and the
    `RawPayload`/`FetchContext` value types.
  - A `ConnectorRunner` orchestrating pull → raw store → normalize → append →
    publish, **idempotent** via the raw store's content addressing.
  - A `ConnectorRegistry` (register/lookup by `source`).
  - A Celery task wrapper that runs a registered connector for a user.
- **Out of scope (later tasks):**
  - Any concrete connector (`T3.5`, `T4.2`, `T4.5`).
  - Scheduling/cron of syncs, incremental cursors/backfill windows, rate limits,
    OAuth/token storage (future; connectors may add their own state later).
  - Auth/consent gating of who may sync (`T2.3`).

## 3. User stories & acceptance criteria

- As a **connector author**, I implement a small contract and get durable,
  provenance-linked ingestion for free.
  - **AC1:** `ConnectorRunner.sync(connector, context)` stores each fetched
    payload as a raw record, normalizes new raw records into events, appends and
    publishes them, and returns a `SyncResult` (counts).
  - **AC2:** Normalized events reference their raw record (`raw_record_id`), so
    every ingested event is traceable to its source payload.
- As the **platform**, I want re-running a sync to be safe.
  - **AC3:** Re-syncing the same payloads stores no duplicate raw records and
    creates no duplicate events (idempotent via `(source, checksum)`); duplicates
    are counted as skipped.
  - **AC4:** A changed payload (new checksum) ingests as a new raw record and new
    event(s).
- As an **operator**, I want to run a sync from a worker.
  - **AC5:** A Celery task resolves a connector by `source` from the registry and
    runs the sync.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `Connector` protocol: attribute `source: str`; `fetch(context: FetchContext) -> Iterable[RawPayload]`; `normalize(raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]`. |
| FR-2 | Functional | `RawPayload`: `content` (JSON), `fetched_at` (UTC), `external_id` (optional), `content_type` (default `application/json`). `FetchContext`: `user_id`, `correlation_id`. |
| FR-3 | Functional | `ConnectorRunner.sync` stores each payload via `RawRecordStore`; on `DuplicateRawRecordError` it **skips** (no normalize) and increments a skipped counter. |
| FR-4 | Functional | For each newly-stored raw record, `connector.normalize` is called; returned events are appended via `EventStore`; each event must carry `raw_record_id = raw.raw_record_id` (provenance) — the runner validates this and rejects events whose provenance doesn't match. |
| FR-5 | Functional | The transaction is committed before publishing; events are then published on the bus (best-effort, `EventDispatchError` logged) — mirroring `T3.2`. |
| FR-6 | Functional | `sync` returns `SyncResult(source, raw_ingested, events_created, skipped_duplicates)`. |
| FR-7 | Functional | `ConnectorRegistry.register(connector)` / `get(source)` (raising `UnknownConnectorError` if absent) / `all()`. A default module-level registry is provided. |
| FR-8 | Functional | A Celery task `mylife.sync_connector(source, user_id)` resolves the connector from the registry, builds a session (`get_session_factory`) and a Redis publisher (`settings.redis_url`), and runs the sync. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Testability | `ConnectorRunner`/registry unit-tested with a fake connector, an in-memory session and an in-process bus; the Celery task's registration is asserted. |
| NFR-3 | Idempotency | Re-running `sync` with unchanged payloads is a no-op for the stored data (AC3). |

## 5. API & event contracts

No HTTP API. Python contract (illustrative):

```python
class FetchContext(BaseModel):        # frozen
    user_id: UUID
    correlation_id: str

class RawPayload(BaseModel):          # frozen
    content: JsonValue
    fetched_at: datetime              # UTC
    external_id: str | None = None
    content_type: str = "application/json"

class Connector(Protocol):
    source: str
    def fetch(self, context: FetchContext) -> Iterable[RawPayload]: ...
    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]: ...

@dataclass(frozen=True)
class SyncResult:
    source: str
    raw_ingested: int
    events_created: int
    skipped_duplicates: int

class ConnectorRunner:
    def __init__(self, session: Session, bus: EventBus) -> None: ...
    def sync(self, connector: Connector, context: FetchContext) -> SyncResult: ...

class ConnectorRegistry:
    def register(self, connector: Connector) -> None: ...
    def get(self, source: str) -> Connector: ...        # UnknownConnectorError if absent
    def all(self) -> list[Connector]: ...
```

- **Worker task:** `mylife.sync_connector(source: str, user_id: str) -> dict`
  (returns the `SyncResult` counts). Publishing from the worker uses the Redis
  stream (`T1.3`) so in-process subscribers in the app react.

## 6. Data model & migration strategy

- **No new tables, no migration.** Reuses `raw_records` (`T1.4`) and `events`
  (`T1.2`). Proposed layout: `src/mylife/connectors/base.py` (contract + runner),
  `src/mylife/connectors/registry.py` (registry), and a `sync_connector` task in
  `src/mylife/workers/tasks.py`.

## 7. Privacy, consent, access-control & retention

- Connectors ingest the most sensitive data; the raw payload is stored verbatim
  in `raw_records` and never logged by the framework.
- **Consent gating is deferred to `T2.3`:** once consent exists, `sync` must
  check the user granted consent for `source` before ingesting; the runner is the
  seam for that check. Until then, syncs are initiated explicitly by trusted
  callers/operators.

## 8. Test plan

Integration tests on SQLite with a fake connector:

- **Ingest (AC1/AC2):** `sync` stores raw records, creates normalized events with
  `raw_record_id` set, publishes them, and returns correct counts; events are
  queryable and provenance-linked.
- **Idempotency (AC3):** a second `sync` of the same payloads stores/creates
  nothing new and counts them as skipped.
- **Change (AC4):** a payload with new content ingests as new raw + event.
- **Provenance enforcement (FR-4):** a connector whose `normalize` omits/mismatches
  `raw_record_id` is rejected.
- **Registry (FR-7):** register/get/all; `get` of an unknown source raises
  `UnknownConnectorError`.
- **Worker (AC5/FR-8):** `mylife.sync_connector` is registered on the Celery app.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T1.2`/`T1.4` (stores), `T1.3` (bus), `T0.9` (worker),
  `redis` (already available).
- **Open decisions (resolved for this spec):**
  - *Idempotency key.* → **The raw record's `(source, checksum)`**: only
    newly-stored raw records are normalized, so re-syncs never duplicate events.
  - *Provenance responsibility.* → **The connector sets `raw_record_id`** on the
    events it emits; the runner **validates** it matches the raw record.
  - *Worker publishing.* → **Redis stream** (cross-process), since in-process
    subscribers live in the web app.
  - *Consent.* → **Deferred to `T2.3`**; the runner is the enforcement seam.
- **Risks:**
  - *Partial failure mid-normalize* — the whole sync runs in one transaction and
    commits once; a failure rolls back the batch (no partial raw/event split).
  - *Non-idempotent connectors* that mutate content nondeterministically would
    create churn — documented as a connector-authoring contract.
- **Future work:** incremental cursors/backfill, scheduling, token/secret
  storage, consent gating (`T2.3`), and concrete connectors (`T3.5`, `T4.x`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Backlog + spec status updated; worker task registered.
- [ ] Idempotency and provenance verified; raw content never logged; consent seam documented.
