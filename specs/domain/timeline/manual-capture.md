# Spec: Manual event capture API (`T3.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/timeline/capture.py`, `POST` in `src/mylife/api/timeline.py`, tests in `tests/test_timeline_capture.py` + `tests/test_timeline_api.py`)
- **Backlog task:** `T3.2` — [issue #20](https://github.com/EFACODE/MyLife/issues/20)
- **Bounded context:** Timeline
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1`/`T1.2`/`T1.3` (envelope, store, bus), `T3.1` (query API), `T0.8` (correlation id)

## 1. Purpose & business context

The timeline can be read (`T3.1`); now it must be **written**. This task adds the
manual capture endpoint: a user records a Life Event by hand, the system appends
it to the store and publishes it on the in-process bus. This completes the
minimal capture→read loop **with zero connectors**, and is the first place the
"append then publish" wiring the bus (`T1.3`) deferred is actually done.

## 2. Scope

- **In scope:**
  - A command service that builds a `LifeEventRecorded`, appends it (`T1.2`) and
    publishes it on the in-process bus (`T1.3`).
  - `POST /timeline/events` accepting the manual input and returning the created
    event (201).
  - Correlation id taken from the request context (`T0.8`), not the body.
  - A shared in-process `EventBus` dependency for the app.
- **Out of scope (later tasks):**
  - Connector-driven ingestion / raw records (`T3.4`, `T1.4` write path).
  - Projections/subscribers that react to the published event (`T3.3`).
  - Redis publishing to workers (wired when a consumer exists).
  - Auth/consent (`T2`) — `user_id` stays an explicit field for now.
  - Correcting/superseding via the API (the kernel supports it; no endpoint yet).

## 3. User stories & acceptance criteria

- As a **user**, I want to record an event by hand so it appears on my timeline.
  - **AC1:** `POST /timeline/events` with a valid body returns `201` and the
    created event, including a generated `event_id` and `recorded_at`.
  - **AC2:** After posting, `GET /timeline/events?user_id=…` (`T3.1`) returns the
    event.
  - **AC3:** The created event is a `LifeEventRecorded` with
    `source` (default `"manual"`), `raw_record_id = null`,
    `corrects_event_id = null`, and `correlation_id` from the request context.
  - **AC4:** A naive (timezone-less) `occurred_at`, or a missing required field,
    returns `422`.
- As a **projection author**, I want the event published so subscribers can
  react.
  - **AC5:** Recording invokes in-process subscribers with the event; a
    subscriber failure does not undo the already-durable event.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `POST /timeline/events` body: `user_id` (UUID), `occurred_at` (UTC datetime), `title` (non-empty), `category` (non-empty), `note` (optional), `source` (default `"manual"`, non-empty). |
| FR-2 | Functional | The service creates a `LifeEventRecorded` with a generated `event_id`, `recorded_at = now (UTC)`, and `correlation_id` from `mylife.core.context.get_correlation_id()` (falling back to a fresh id). |
| FR-3 | Functional | The event is appended via `EventStore.append` and the transaction committed before publishing (the fact is durable first). |
| FR-4 | Functional | After commit, the event is published on the in-process `EventBus`; an `EventDispatchError` is logged but does **not** fail the request or roll back the event (AC5). |
| FR-5 | Functional | The endpoint returns `201` with the created event in the `TimelineEvent` shape (`T3.1`). |
| FR-6 | Functional | `occurred_at` must be timezone-aware UTC; naive input → `422` (FR/AC4). |
| FR-7 | Functional | A shared app-level in-process `EventBus` is provided via a FastAPI dependency (`get_event_bus`). |
| NFR-1 | Typing | Passes `mypy --strict`; request/response are typed models. |
| NFR-2 | Testability | Command service unit-tested (append+publish) on SQLite; endpoint tested via `TestClient` (post → 201 → visible via GET); a subscriber failure is exercised. |
| NFR-3 | Security | `user_id` is an explicit field (pre-`T2`); payloads are never logged. |

## 5. API & event contracts

```
POST /timeline/events
  body: {
    "user_id": "<uuid>",
    "occurred_at": "2026-07-18T12:00:00+00:00",
    "title": "Morning run",
    "category": "health",
    "note": null,
    "source": "manual"
  }
  201 -> TimelineEvent   (same shape as GET /timeline/events items)
  422 -> validation error (naive datetime, missing/empty field)
```

- **Event produced:** `LifeEventRecorded` (`event_type
  = "timeline.life_event_recorded"`, `schema_version = 1`), appended and
  published.

Command/service shape (illustrative):

```python
class RecordLifeEventCommand(BaseModel):     # frozen; occurred_at validated UTC
    user_id: UUID
    occurred_at: datetime
    title: str
    category: str
    note: str | None = None
    source: str = "manual"

class TimelineWriter:
    def __init__(self, session: Session, bus: EventBus) -> None: ...
    def record(self, command: RecordLifeEventCommand, *, correlation_id: str) -> StoredEvent: ...
```

## 6. Data model & migration strategy

- **No schema change, no migration** (reuses `events`, `T1.2`).
- Proposed layout: `src/mylife/timeline/capture.py` (command + `TimelineWriter`);
  the `POST` route added to `src/mylife/api/timeline.py`; a shared bus provider in
  a small `src/mylife/api/deps.py` (or the timeline api module).

## 7. Privacy, consent, access-control & retention

- Pre-`T2`: `user_id` is supplied in the body; once Identity/consent land, the
  authenticated user replaces it and consent is checked. The write path is the
  seam for that change.
- Payload contents (`title`/`note`) are user data and are never logged; only ids
  and `event_type`/`correlation_id` may be logged.

## 8. Test plan

- **Service (AC1/AC3/AC5):** `record` appends an event readable via the query
  service, sets `source`/`correlation_id`, and publishes to a subscribed bus; a
  raising subscriber does not undo the stored event.
- **Endpoint (AC1/AC2/AC4):** `POST` returns `201` + created event; a subsequent
  `GET` (T3.1) returns it; naive `occurred_at` and missing fields → `422`.
- **Durability (FR-3/FR-4):** the event remains after a publish failure.
- **Read-back parity:** the posted event's fields match the `GET` result.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), query schema (`T3.1`), correlation id
  (`T0.8`).
- **Open decisions (resolved for this spec):**
  - *Commit vs publish order.* → **Commit first, then publish** (best-effort);
    the durable fact must not depend on subscriber success.
  - *Bus scope.* → **Shared app-level in-process bus** via a dependency; Redis
    publishing is wired later when a consumer exists.
  - *Correlation id source.* → **Request context** (`T0.8`), not the request
    body — clients cannot spoof provenance metadata.
- **Risks:**
  - *Silent projection failure* after commit — mitigated by logging the
    `EventDispatchError`; durable events allow later replay.
  - *No auth yet* — mitigated by keeping the endpoint `user_id`-scoped;
    hardened in `T2`.
- **Future work:** connector ingestion (`T3.4`), correction endpoint, Redis
  publish to workers, auth/consent (`T2`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Endpoint registered and in OpenAPI; backlog + spec status updated.
- [ ] Commit-before-publish honored; payloads not logged; pre-`T2` caveat recorded.
