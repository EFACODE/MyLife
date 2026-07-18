# Spec: Entities & relationships projection (`T3.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T3.3` — [issue #21](https://github.com/EFACODE/MyLife/issues/21)
- **Bounded context:** Timeline
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1`–`T1.3` (envelope, store, bus), `T3.2` (capture)

## 1. Purpose & business context

The first **projection**: a governed registry of **entities** and the
**relationships** between them, derived by reacting to the event stream. This is
the seed of the knowledge graph (`T6.4`) and the first consumer of the event bus
(`T1.3`) — proving that "subscribers drive projections". It is **derived data**
(kept distinct from raw and normalized facts): rebuildable from events, and it
never overwrites the underlying events.

## 2. Scope

- **In scope:**
  - Derived tables `entities` and `relationships` (mutable read model) +
    migration.
  - An `EntityProjection` service that **applies** an event (upserting entities
    and their relationships) and **reads** them back.
  - A default, intentionally-simple extractor deriving entities from an event.
  - A bus **subscriber** that applies each published event in its own committed
    session, plus a **rebuild** from the event store.
- **Out of scope (later tasks):**
  - Registering the subscriber inside the running app's composition root — left
    as a small follow-up until per-app bus/session lifecycle lands (`T2`); the
    subscriber is ready to register (see §9).
  - Rich entity extraction (people/places/orgs), entity resolution/merging, and
    a graph query API (`T6`).
  - Applying corrections to the projection (`T1.5` semantics in the graph).

## 3. User stories & acceptance criteria

- As the **platform**, I want each recorded event to update a registry of
  entities and their relationships, so a graph of the user's context emerges.
  - **AC1:** Applying an event upserts its entities: first occurrence creates one
    (occurrences = 1, first/last-seen = event time); a repeat increments
    `occurrences` and advances `last_seen_at`.
  - **AC2:** When an event yields two entities, a relationship between them is
    upserted the same way.
  - **AC3:** Entities/relationships are **user-scoped**; one user's graph never
    includes another's.
- As a **subscriber**, I want to react to published events.
  - **AC4:** Registering the projection on a bus and publishing an event updates
    the projection.
- As a **maintainer**, I want to rebuild the projection from history.
  - **AC5:** `rebuild` clears and recomputes the projection from
    `EventStore.read_all`, yielding the same result as live application.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `entities`: `entity_id` (UUID PK), `user_id`, `entity_type`, `entity_key`, `first_seen_at` (UTC), `last_seen_at` (UTC), `occurrences` (int); unique `(user_id, entity_type, entity_key)`. |
| FR-2 | Functional | Table `relationships`: `relationship_id` (UUID PK), `user_id`, `source_entity_id`, `target_entity_id`, `rel_type`, `first_seen_at`, `last_seen_at`, `occurrences`; unique `(user_id, source_entity_id, target_entity_id, rel_type)`. |
| FR-3 | Functional | `EntityProjection(session).apply(event)` upserts entities/relationships from the event's extraction (AC1/AC2), using `occurred_at` for seen times. |
| FR-4 | Functional | A default extractor derives, per event: a `source` entity (`entity_type="source"`, key = `event.source`); and for `timeline.life_event_recorded`, a `category` entity from `payload["category"]`; and, when both exist, a `records` relationship `source → category`. |
| FR-5 | Functional | Extraction reads only envelope fields + the serialized payload (`model_dump`), so it is decoupled from concrete event classes. |
| FR-6 | Functional | Reads: `list_entities(user_id)` and `list_relationships(user_id)` (ordered deterministically). |
| FR-7 | Functional | `EntityProjectionSubscriber(session_factory).register(bus)` subscribes a handler that applies each published event in its own committed session. |
| FR-8 | Functional | `rebuild(session, events)` clears the user-agnostic projection tables and re-applies a sequence of events (AC5). |
| FR-9 | Functional | The projection is derived/mutable — it may update rows; it must never modify `events`/`raw_records`. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Portability/Migration | Works on SQLite (tests) and Postgres; one Alembic revision creates both tables; `alembic check` clean. |
| NFR-3 | Idempotency | Rebuild is deterministic; live-apply and rebuild converge for the same event set. |

## 5. API & event contracts

No HTTP API in this task (read/query endpoints come with `T6`/later). Python
contract (illustrative):

```python
class EntityRecord(BaseModel):        # frozen
    entity_id: UUID; user_id: UUID; entity_type: str; entity_key: str
    first_seen_at: datetime; last_seen_at: datetime; occurrences: int

class RelationshipRecord(BaseModel):  # frozen
    relationship_id: UUID; user_id: UUID
    source_entity_id: UUID; target_entity_id: UUID; rel_type: str
    first_seen_at: datetime; last_seen_at: datetime; occurrences: int

class EntityProjection:
    def __init__(self, session: Session) -> None: ...
    def apply(self, event: LifeEvent[Any]) -> None: ...
    def list_entities(self, user_id: UUID) -> list[EntityRecord]: ...
    def list_relationships(self, user_id: UUID) -> list[RelationshipRecord]: ...
    def rebuild(self, events: Iterable[LifeEvent[Any]]) -> None: ...

class EntityProjectionSubscriber:
    def __init__(self, session_factory: sessionmaker[Session]) -> None: ...
    def register(self, bus: InProcessEventBus) -> None: ...
```

- **Consumes** any `LifeEvent`; **produces** no events.

## 6. Data model & migration strategy

- SQLAlchemy models `EntityRow`, `RelationshipRow` on `Base`. Proposed location:
  `src/mylife/timeline/entities.py`.
- New Alembic revision `0005_entities_relationships`; `env.py` imports the models
  (via the `mylife.timeline` package import) so `alembic check` sees them.
- These are the first rows in the **derived** store; they are mutable and fully
  rebuildable, distinct from the append-only `events`/`raw_records`.

## 7. Privacy, consent, access-control & retention

- Entities/relationships are personal, user-scoped derived data. Being
  rebuildable, they can be dropped and recomputed; a data-subject deletion
  (`T2.5`) removes a user's projection rows and they simply won't be recomputed
  after the source events are gone.
- No entity keys or payloads are logged.

## 8. Test plan

Integration tests on SQLite:

- **Upsert/increment (AC1):** applying the same-source events twice → one
  `source` entity with `occurrences = 2` and advanced `last_seen_at`.
- **Relationship (AC2/FR-4):** a `life_event_recorded` yields `source` and
  `category` entities and a `records` relationship between them.
- **User scoping (AC3):** two users' events produce disjoint projections.
- **Subscriber (AC4/FR-7):** register on an `InProcessEventBus`, publish, assert
  the projection updated (own-session commit).
- **Rebuild (AC5/FR-8):** rebuild from a set of events equals the live-applied
  result.
- **Derived-only (FR-9):** applying does not change `events` rows.
- **Migration (NFR-2):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), capture (`T3.2`), `mylife.db.base`.
- **Open decisions (resolved for this spec):**
  - *Extraction rules.* → **Deliberately minimal** (source + category + a
    `records` link) to prove the mechanism; richer extractors (people, places,
    orgs) come with real payloads and `T6`.
  - *Update mechanism.* → **Bus subscriber with its own session** (applies after
    the event is committed), plus a **rebuild** from the store for recovery.
  - *Live app registration.* → **Deferred**: registering the subscriber in the
    running app needs a per-app bus/session lifecycle; the subscriber is built
    and tested here and wired into the composition root in a small follow-up
    (with `T2`). This keeps the change focused and the API/session lifecycle
    stable.
  - *Derived vs immutable.* → entities/relationships are **mutable derived**
    data; only `events`/`raw_records` are append-only.
- **Risks:**
  - *Double counting* if live-apply and rebuild both run — mitigated by
    `rebuild` clearing first; documented.
  - *Corrections not yet reflected* in the graph — deferred (future work).
- **Future work:** live registration in the app, correction-aware projection,
  entity resolution/merging, richer extractors, and a graph query API (`T6`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Migration reviewed; backlog + spec status updated.
- [ ] Derived-only guarantee verified (events untouched); no keys/payloads logged.
