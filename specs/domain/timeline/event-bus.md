# Spec: Event bus + in-process dispatcher (`T1.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/core/events/bus.py`, tests in `tests/test_event_bus.py`)
- **Backlog task:** `T1.3` — [issue #16](https://github.com/EFACODE/MyLife/issues/16)
- **Bounded context:** Timeline (shared kernel)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1` (envelope), `T1.2` (store), `T0.2`/`T0.9` (Redis)

## 1. Purpose & business context

Once an event is appended (`T1.2`), other parts of the system must be able to
**react** to it: projections (entities/relationships, `T3.3`), the briefing
(`T3.6`), and out-of-process workers. This task adds the **event bus**:

- an **in-process dispatcher** for synchronous, same-process subscribers
  (projections that update inside the request), and
- a **Redis stream publisher** so out-of-process consumers (Celery workers,
  `T0.9`) can react asynchronously.

The bus only *transports* events; it does not persist them (that is `T1.2`) and
it does not itself hook into `append` — application services wire "append then
publish" in later tasks.

## 2. Scope

- **In scope:**
  - An in-process bus: subscribe handlers (optionally filtered by `event_type`)
    and publish an event to all matching handlers synchronously.
  - Per-handler error isolation with an aggregated failure surfaced to the
    publisher.
  - A Redis stream publisher that serializes an event and `XADD`s it to a
    configured stream for external consumers.
  - Deterministic serialization reusing the T1.1 envelope JSON.
- **Out of scope (later tasks):**
  - Consuming the Redis stream in a worker loop / consumer groups, retries,
    dead-lettering (infra + `T3.4`).
  - Wiring append→publish into a concrete flow (`T3.2`).
  - Ordering guarantees beyond what a single Redis stream provides.

## 3. User stories & acceptance criteria

- As a **projection author**, I want to subscribe to an event type and be called
  synchronously when one is published, so my read model stays current.
  - **AC1:** A handler subscribed to `event_type` X is invoked with the event
    when X is published; a handler subscribed to "all" is invoked for every
    event.
  - **AC2:** A handler subscribed to X is **not** invoked when a different type
    is published.
  - **AC3:** Multiple handlers are invoked in subscription order.
- As a **platform maintainer**, I want one failing subscriber not to silently
  swallow the failure or block the others.
  - **AC4:** If a handler raises, remaining handlers still run, the error is
    logged, and `publish` raises an aggregated `EventDispatchError` afterward.
- As a **worker author**, I want published events to land on Redis so an
  out-of-process consumer can read them.
  - **AC5:** Publishing via the Redis publisher appends one entry to the
    configured stream whose data deserializes back to an equal event.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `InProcessEventBus.subscribe(handler, *, event_type=None)` registers a handler; `event_type=None` means all events. |
| FR-2 | Functional | `publish(event)` invokes every matching handler synchronously, in subscription order (FR-1, AC1–AC3). |
| FR-3 | Functional | Handler signature is `Callable[[LifeEvent[BaseModel]], None]`. |
| FR-4 | Functional | If one or more handlers raise, `publish` runs all handlers, logs each error (with `correlation_id`), then raises `EventDispatchError` aggregating them (AC4). |
| FR-5 | Functional | `RedisStreamPublisher.publish(event)` serializes the envelope to JSON and `XADD`s a single entry `{ "data": <json> }` to the configured stream. |
| FR-6 | Functional | The Redis stream name is configurable (setting, default `mylife:events`). |
| FR-7 | Functional | A published Redis entry deserializes back to an equal event (via `StoredEvent`/model rehydration) (AC5). |
| FR-8 | Functional | Both buses share a common `EventBus` protocol exposing `publish(event) -> None`, so callers can depend on the abstraction. |
| NFR-1 | Typing | Passes `mypy --strict`; handler and publisher types are explicit. |
| NFR-2 | Testability | In-process bus fully unit-tested; Redis publisher tested with `fakeredis` (no running broker). |
| NFR-3 | Observability | Publish and handler errors are logged via the structured logger (`T0.8`), never with payload secrets. |

## 5. API & event contracts

Illustrative signatures:

```python
Handler = Callable[[LifeEvent[BaseModel]], None]


class EventDispatchError(Exception):
    errors: list[Exception]


class EventBus(Protocol):
    def publish(self, event: LifeEvent[BaseModel]) -> None: ...


class InProcessEventBus:  # EventBus
    def subscribe(self, handler: Handler, *, event_type: str | None = None) -> None: ...
    def publish(self, event: LifeEvent[BaseModel]) -> None: ...


class RedisStreamPublisher:  # EventBus
    def __init__(self, client: redis.Redis, *, stream: str = "mylife:events") -> None: ...
    def publish(self, event: LifeEvent[BaseModel]) -> None: ...
```

- **Redis entry contract:** stream `mylife:events`, one field `data` holding the
  full envelope JSON (`event.model_dump_json()`). Consumers filter by the
  `event_type` inside the JSON.

## 6. Data model & migration strategy

- No database changes, no migration. In-memory registry for the in-process bus;
  Redis stream for the publisher. Proposed location:
  `src/mylife/core/events/bus.py`.
- Redis client is provided by the caller (built from `settings.redis_url`); the
  bus does not own connection lifecycle.

## 7. Privacy, consent, access-control & retention

- Events on the bus carry `user_id` and may carry sensitive payloads; the bus
  must not log payload contents (only ids, `event_type`, `correlation_id`).
- Redis stream retention/trimming (e.g. `MAXLEN`) and access control are infra
  concerns configured with the deployment; noted as future hardening.
- Consumers remain subject to consent/access rules (`T2.3`) when they act on
  events.

## 8. Test plan

Unit tests (in-process, no network) + `fakeredis` for the publisher:

- **Routing (AC1–AC3):** typed subscription receives matching events only;
  "all" subscription receives everything; handler order preserved.
- **Error isolation (AC4):** one raising handler → others still run; error
  logged; `EventDispatchError` raised aggregating the failure(s).
- **Redis publish (AC5, FR-5/FR-7):** publishing `XADD`s one entry; reading the
  stream back and rehydrating yields an equal event.
- **Config (FR-6):** custom stream name is honored.
- **Typing (NFR-1):** `mypy --strict` proves handler/publisher signatures.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T1.1`/`T1.2` (event + store), `redis` (already provided via
  `celery[redis]`), `mylife.core.logging` (T0.8). Adds **`fakeredis`** to the
  dev extras for testing.
- **Open decisions (resolved for this spec):**
  - *In-process error policy.* → **Isolate + aggregate**: run all handlers, log
    each failure, then raise `EventDispatchError`. Keeps failures visible
    without letting one subscriber suppress others.
  - *Redis transport.* → **Streams (`XADD`)** rather than pub/sub, so entries
    persist for consumer groups later (at-least-once).
  - *Topology.* → **Single stream** with `event_type` as a JSON field; consumers
    filter. Per-type streams can be added later without changing producers.
- **Risks:**
  - *Sync in-process handlers can slow the request* — heavy work belongs on the
    Redis/worker path; documented.
  - *At-least-once on Redis* — consumers (later tasks) must be idempotent; the
    unique `event_id` (T1.2) supports that.
- **Future work:** consumer groups + worker loop, retries/dead-letter, stream
  trimming, and append→publish wiring in application services (`T3.2`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Backlog + spec status updated.
- [ ] No payload/secret logging; consumers' idempotency need documented.
