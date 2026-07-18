# Spec: Life Event envelope (`T1.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/core/events/`, tests in `tests/test_event_envelope.py`)
- **Evolution:** `T1.4` added an optional provenance field `raw_record_id: UUID | None`; `T1.5` added `corrects_event_id: UUID | None` (both additive, backward-compatible).
- **Backlog task:** `T1.1` — [issue #14](https://github.com/EFACODE/MyLife/issues/14)
- **Bounded context:** Timeline (shared kernel)
- **Author / date:** Claude Code / 2026-07-18

## 1. Purpose & business context

Everything in My Life is a **Life Event**. Before any domain can publish facts,
we need one canonical, immutable **envelope** that every Life Event carries —
independent of its domain-specific payload. The envelope is what makes the
platform explainable and auditable: it records *what* happened, *when* it
happened versus when we learned it, *where it came from*, and *whom* it belongs
to. It is the foundation the event store (`T1.2`), event bus (`T1.3`),
provenance link (`T1.4`) and corrections (`T1.5`) all build on.

This task delivers the envelope **model and its validation rules only** — not
persistence, not transport. It also defines the first concrete event type,
`LifeEventRecorded`, as the reference implementation of the envelope contract.

## 2. Scope

- **In scope:**
  - A typed, immutable envelope model (`LifeEvent`) shared by all domains.
  - Field definitions, invariants and validation (UTC enforcement, required
    fields, immutability).
  - Deterministic JSON serialization/deserialization (round-trip).
  - A generic mechanism for domain events to attach a **typed payload**.
  - The first concrete event, `LifeEventRecorded`, as the canonical example.
- **Out of scope (later tasks):**
  - Persisting events (`T1.2`), publishing them (`T1.3`).
  - Raw-record provenance storage (`T1.4`) — the envelope only *carries* the
    provenance reference fields; the raw store itself is `T1.4`.
  - Corrections/`EventCorrected` (`T1.5`).
  - Any domain-specific payloads beyond the reference event.

## 3. User stories & acceptance criteria

- As a **domain author**, I want a single envelope base so that every event I
  emit automatically carries consistent, validated metadata.
  - **AC1:** Constructing a `LifeEvent` without any required field raises a
    validation error naming the missing field.
  - **AC2:** A domain event is declared by subclassing/parameterizing the
    envelope with a typed payload; its `event_type` and `schema_version` are
    fixed on the type.
- As an **auditor/AI consumer**, I want every event to state when it occurred,
  when it was recorded, its source and correlation ID, so that I can trace and
  explain it.
  - **AC3:** `occurred_at` and `recorded_at` are always timezone-aware UTC.
  - **AC4:** An event serializes to JSON and deserializes back to an equal
    value (round-trip), with datetimes in ISO-8601 UTC.
- As a **platform maintainer**, I want events to be immutable so history cannot
  be silently rewritten.
  - **AC5:** Attempting to mutate any field on a constructed event raises an
    error; a "change" is only possible by creating a new event.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | The envelope defines exactly these fields: `event_id`, `user_id`, `event_type`, `occurred_at`, `recorded_at`, `schema_version`, `source`, `correlation_id`, `payload`. |
| FR-2 | Functional | `event_id` is a UUID (default: a newly generated UUIDv4). It satisfies the brief's `id` invariant. |
| FR-3 | Functional | `occurred_at` (when the fact happened) and `recorded_at` (when the system recorded it) are timezone-aware UTC `datetime`s. Naive datetimes are rejected; non-UTC aware datetimes are normalized to UTC. |
| FR-4 | Functional | `recorded_at` defaults to the current UTC time at construction if not supplied. |
| FR-5 | Functional | `schema_version` is a positive integer, fixed per `event_type` (starts at 1). |
| FR-6 | Functional | `source` is a non-empty string identifying origin (e.g. `"manual"` or a connector id). |
| FR-7 | Functional | `correlation_id` is a non-empty string; producers set it from the request context (`mylife.core.context.get_correlation_id`, T0.8), generating a fresh one when absent. |
| FR-8 | Functional | `payload` is a typed model specific to the `event_type`; the envelope is generic over the payload type so domain payloads are statically typed. |
| FR-9 | Functional | Events are immutable (frozen): field mutation after construction raises an error. |
| FR-10 | Functional | Events serialize to JSON and deserialize back to an equal value; datetimes use ISO-8601 with a UTC offset. |
| FR-11 | Functional | `LifeEventRecorded` is provided as the first concrete event type (`event_type = "timeline.life_event_recorded"`, `schema_version = 1`) with a minimal reference payload. |
| NFR-1 | Typing | Fully typed; passes `mypy --strict`. Payload typing is preserved through the generic (no `Any` leakage in consumers). |
| NFR-2 | Quality | 100% of the envelope's branches covered by unit tests; passes `ruff` + `ruff format`. |
| NFR-3 | Compatibility | `schema_version` enables forward evolution: consumers must tolerate reading a known `event_type` at its declared version. |

## 5. API & event contracts

No HTTP API in this task. The **event contract** is the envelope itself.

**Envelope fields**

| Field | Type | Notes |
| ----- | ---- | ----- |
| `event_id` | `UUID` | Unique id; default UUIDv4. |
| `user_id` | `UUID` | Owner of the event. |
| `event_type` | `str` | Dotted, context-prefixed (e.g. `timeline.life_event_recorded`). Fixed per event type. |
| `occurred_at` | `datetime` (UTC) | When the real-world fact happened. |
| `recorded_at` | `datetime` (UTC) | When the system recorded it; defaults to now. |
| `schema_version` | `int` (≥1) | Version of this `event_type`'s schema. |
| `source` | `str` | Origin: `"manual"` or connector id. |
| `correlation_id` | `str` | Trace id linking the event to the request/job that produced it. |
| `payload` | typed model | Domain-specific data for this `event_type`. |

**Reference event — `LifeEventRecorded`**

- `event_type`: `"timeline.life_event_recorded"`, `schema_version`: `1`.
- Payload (v1, minimal reference): `title: str`, `category: str`, optional
  `note: str | None`. Real domains define richer payloads in their own tasks.

**Illustrative JSON** (shape, not final field values):

```json
{
  "event_id": "3f1c...",
  "user_id": "9ab2...",
  "event_type": "timeline.life_event_recorded",
  "occurred_at": "2026-07-18T12:00:00+00:00",
  "recorded_at": "2026-07-18T12:00:03+00:00",
  "schema_version": 1,
  "source": "manual",
  "correlation_id": "b7e6f0c9d2a14e1c",
  "payload": { "title": "Morning run", "category": "health", "note": null }
}
```

## 6. Data model & migration strategy

- Pure in-memory model in this task — **no database tables, no migration.**
  Persistence is `T1.2` (which adds the `events` table and its Alembic
  migration, and maps this envelope to storage).
- Implementation: a Pydantic v2 model, generic over payload type, with
  `frozen=True` and UTC-normalizing validators. Proposed location:
  `src/mylife/core/events/envelope.py`; the reference event and its payload in
  `src/mylife/core/events/life_event.py` (or a `timeline` context module —
  resolve at implementation).

## 7. Privacy, consent, access-control & retention

- The envelope links every event to a `user_id` (personal-data association) and
  a `correlation_id`. It carries no credentials or secrets.
- Payloads may hold sensitive data; payload-level privacy rules belong to the
  owning domain's spec, not here. The envelope must not log payload contents.
- Consent/access enforcement is applied by producers/consumers (`T2.3`), not by
  the envelope. Retention is handled by the store (`T1.2`) and data-subject
  rights (`T2.5`).

## 8. Test plan

Unit tests (no DB, no network):

- **Required fields:** missing any required field → validation error (AC1).
- **UTC enforcement:** naive `occurred_at`/`recorded_at` rejected; aware
  non-UTC normalized to UTC (AC3, FR-3).
- **Defaults:** `event_id` auto-generated and unique; `recorded_at` defaults to
  now-UTC (FR-2, FR-4).
- **Immutability:** field assignment after construction raises (AC5, FR-9).
- **Validation:** `schema_version < 1`, empty `source`/`correlation_id`
  rejected (FR-5, FR-6, FR-7).
- **Serialization round-trip:** `dump → load` yields an equal event; datetimes
  ISO-8601 UTC (AC4, FR-10).
- **Typed payload:** `LifeEventRecorded` carries its payload type; wrong payload
  shape rejected; `mypy` proves payload typing (FR-8, FR-11, NFR-1).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `mylife.core.context` (T0.8) for correlation IDs. Pydantic v2
  (already a dependency).
- **Open decisions (resolved for this spec):**
  - *Field name `event_id` vs `id`.* → **`event_id`**, to avoid shadowing the
    Python builtin and to read clearly in event-sourcing code; it fulfills the
    brief's `id` invariant.
  - *Payload typing mechanism.* → **Generic envelope** (`LifeEvent[PayloadT]`)
    so payloads stay statically typed end to end.
- **Risks:**
  - *Datetime handling bugs* (naive vs aware) — mitigated by explicit validators
    and dedicated tests.
  - *Pydantic generic + `frozen` ergonomics* — validated by the reference event
    and its tests before other domains depend on it.
- **Future work:** persistence & indexing (`T1.2`), publishing (`T1.3`),
  provenance link to raw records (`T1.4`), corrections (`T1.5`), and a schema
  registry if `event_type`/version management grows.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] `specs/README.md` link and the backlog status updated.
- [ ] Privacy note honored (no payload/secret logging); no unsupported AI behavior.
