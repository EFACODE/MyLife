# Spec: Knowledge-graph consolidation (`T6.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T6.4` — [issue #37](https://github.com/EFACODE/MyLife/issues/37)
- **Bounded context:** Knowledge × Timeline (entity projection)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T3.3` (entity/relationship projection), `T4`/`T5`/`T6`
  (domain events), `T2.2` (auth)

## 1. Purpose & business context

Consolidate the user's **entities and relationships across every domain** into one
knowledge graph. `T3.3` seeded a generic projection over timeline events; this
task adds a **cross-domain extractor** (finance, health, goals, knowledge) so the
graph spans the whole twin, plus a read API (list + neighborhood) and an explicit,
user-scoped **consolidation** that rebuilds the graph from the user's event
stream. It is the connective tissue the assistant (`T7`) will traverse.

## 2. Scope

- **In scope:**
  - A **consolidated extractor** deriving entities/relationships from domain
    events: finance (`spent_on` a category), health (`performed` an activity),
    goals (`pursues` a goal, `measured_by` a metric), knowledge (`ingested` a
    document) — all also linked from the event `source`.
  - Reusing the `T3.3` projection machinery: `EntityProjection` gains an injectable
    extractor and a **user-scoped rebuild** + a **neighbors** query.
  - `KnowledgeGraphService`: `consolidate(user_id)` (rebuild the user's graph from
    their events), `entities`, `relationships`, `neighbors(entity_id)`.
  - Authenticated endpoints: `POST /knowledge-graph/consolidate`,
    `GET /knowledge-graph/entities`, `GET /knowledge-graph/relationships`,
    `GET /knowledge-graph/entities/{entity_id}/neighbors`.
- **Out of scope (later):**
  - Auto-subscribing the consolidated projection to the live bus (the `T3.3`
    subscriber stays timeline-only); entity resolution/merging; graph queries
    beyond one-hop neighbors; document-content entity extraction (NER).

## 3. User stories & acceptance criteria

- As a **user**, my graph reflects all my domains, and I can explore it.
  - **AC1:** `POST /knowledge-graph/consolidate` rebuilds my entities/relationships
    from **my** events across finance/health/goals/knowledge/timeline and returns
    the counts.
  - **AC2:** `GET /knowledge-graph/entities` / `…/relationships` return my
    consolidated nodes/edges (user-scoped).
  - **AC3:** `GET /knowledge-graph/entities/{id}/neighbors` returns the entity, its
    one-hop neighbor entities and the connecting edges; a foreign/unknown entity
    → `404`.
- As the **platform**, consolidation is scoped and rebuildable.
  - **AC4:** Consolidation rebuilds only the caller's rows (other users untouched);
    endpoints require auth (`401`). Re-running consolidation is idempotent (same
    graph, occurrences reflect event counts).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | A consolidated `extract(event)` maps domain events to entities/relationships: `finance.expense_created`/`transaction_imported` → `category` (rel `spent_on`) when present; `health.workout_completed` → `activity` (rel `performed`); `goals.goal_created` → `goal` (rel `pursues`) + `metric` (rel `measured_by` from goal); `knowledge.document_ingested` → `document` (rel `ingested`); every event still yields its `source` node (as `T3.3`). Unknown types yield just the source. |
| FR-2 | Functional | `EntityProjection(session, extract=…)` takes an injectable extractor (default = the `T3.3` timeline extractor); `rebuild_for_user(user_id, events)` deletes only that user's entities/relationships then applies `events`; `neighbors(user_id, entity_id)` returns the entity + one-hop neighbors + edges. |
| FR-3 | Functional | `KnowledgeGraphService(session)`: `consolidate(user_id)` reads the user's events (`EventStore.read_stream`, unbounded) and `rebuild_for_user`; `entities`/`relationships`/`neighbors` delegate to the projection with the consolidated extractor. Returns counts from `consolidate`. |
| FR-4 | Functional | Endpoints use `get_current_user`; consolidation/reads are user-scoped; unknown/foreign entity → `404`. |
| FR-5 | Non-functional | **No new table, no migration** (reuses `entities`/`relationships`); **no new dependency**. The cross-domain extractor lives in the Knowledge context (which may depend on all domains); Timeline's extractor stays generic. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Testability | Cross-domain extraction (each domain contributes the right nodes/edges), user-scoped rebuild (other users untouched), neighbors, idempotent re-consolidation, endpoints (auth, `404`). |

## 5. API & event contracts

```
POST /knowledge-graph/consolidate                       -> 200 { entities, relationships }
GET  /knowledge-graph/entities                          -> [EntityRecord]
GET  /knowledge-graph/relationships                     -> [RelationshipRecord]
GET  /knowledge-graph/entities/{entity_id}/neighbors    -> Neighborhood (404 foreign)

Neighborhood = { entity: EntityRecord, neighbors: [EntityRecord], edges: [RelationshipRecord] }
```

- **No events produced** (read/rebuild over existing events).

## 6. Data model & migration strategy

- **No new tables, no migration.** Reuses the `T3.3` `entities`/`relationships`
  projection. Proposed layout: extend `src/mylife/timeline/entities.py`
  (injectable extractor + `rebuild_for_user` + `neighbors`); a consolidated
  extractor + `KnowledgeGraphService` in `src/mylife/knowledge/graph.py`; routes in
  `src/mylife/api/knowledge_graph.py`.

## 7. Privacy, consent, access-control & retention

- Authenticated and user-scoped; consolidation reads and rebuilds only the caller's
  rows. Entity keys are derived from event payloads (categories, activities, goal
  titles, filenames) — not logged. Erasure (`T2.5`) already removes a user's
  `entities`/`relationships`.

## 8. Test plan

- **Cross-domain extraction (AC1/FR-1):** seed finance/health/goals/knowledge
  events → consolidate → the expected typed entities and edges exist.
- **User-scoped rebuild (AC4/FR-2):** consolidating one user leaves another's graph
  intact; re-running is idempotent.
- **Neighbors (AC3):** an entity's neighbors + edges are returned; foreign → `404`.
- **Endpoints/auth (AC2/AC4):** authenticated flow; `401` without a token.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.3` projection, domain event constants, auth.
- **Open decisions (resolved):**
  - *Explicit consolidation.* → user-scoped **rebuild on demand** (safe, scoped),
    rather than auto-subscribing a second projection to the singleton bus.
  - *Extractor placement.* → the cross-domain extractor lives in **Knowledge**
    (may depend on all domains); Timeline's extractor stays generic (injectable).
  - *One-hop neighbors.* → sufficient for exploration/grounding now; multi-hop
    traversal is future work.
- **Risks:**
  - *Entity-key collisions* across domains are namespaced by `entity_type`
    (`category`/`activity`/`goal`/`metric`/`document`/`source`).
  - *Rebuild cost* is O(user events); fine at MVP scale.
- **Future work:** live consolidated subscriber, entity resolution/merge, NER over
  document text, multi-hop graph queries, assistant grounding (`T7`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] Endpoints authenticated/in OpenAPI; backlog + spec status updated.
- [ ] Cross-domain graph consolidates from events; user-scoped; no new dependency.
