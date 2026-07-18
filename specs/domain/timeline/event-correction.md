# Spec: Event correction (`T1.5`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T1.5` — [issue #18](https://github.com/EFACODE/MyLife/issues/18)
- **Bounded context:** Timeline (shared kernel)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1` (envelope), `T1.2` (event store)

## 1. Purpose & business context

A non-negotiable invariant: **history is immutable — corrections create new
events, never mutations.** This task adds the mechanism to *correct* a
previously recorded event without ever changing or deleting it: a new event that
**references the event it supersedes**. This closes the event kernel (`T1`) and
is what lets the digital twin stay both faithful (nothing is rewritten) and
accurate (the latest understanding is discoverable).

## 2. Scope

- **In scope:**
  - A general supersession link on the envelope: `corrects_event_id: UUID |
    None`, so **any** event can declare it corrects/supersedes a prior one.
  - A dedicated `EventCorrected` event type for explicit corrections or
    retractions (a reason, no domain replacement).
  - Persisting the link (event store + migration) and a read to find the
    corrections of an event.
- **Out of scope (later tasks):**
  - Computing the "effective" timeline (hiding superseded events) — that is a
    projection / the query API (`T3.1`/`T3.3`).
  - Enforcing that the target event exists via a DB foreign key (kept as a plain
    reference for now; see §9).
  - UI/flows for issuing corrections.

## 3. User stories & acceptance criteria

- As a **data steward**, I want to correct a wrong event by recording a new
  event that points at it, so history is preserved and the correction is
  traceable.
  - **AC1:** An `EventCorrected` event references the corrected event via
    `corrects_event_id` and carries a `reason`; appending it leaves the original
    event unchanged and present.
  - **AC2:** `read_corrections(event_id)` returns the events that correct a given
    event, in `global_seq` order.
- As a **domain author**, I want any event to be able to supersede a prior one,
  so a re-import with better data links back to what it replaces.
  - **AC3:** A domain event (e.g. `LifeEventRecorded`) may set
    `corrects_event_id`; it round-trips through the store.
- As a **platform maintainer**, I want corrections to never mutate history.
  - **AC4:** After a correction, the original event is still readable, byte-for-
    byte unchanged; the correction is a separate row with its own `global_seq`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | The Life Event envelope gains `corrects_event_id: UUID \| None = None`. |
| FR-2 | Functional | The `events` table gains a nullable `corrects_event_id` column, carried through `append`/reads/`StoredEvent`/`rehydrate`. |
| FR-3 | Functional | An indexed reverse lookup supports finding corrections by target. |
| FR-4 | Functional | `EventCorrected` is a concrete event type (`event_type = "timeline.event_corrected"`, `schema_version = 1`) whose payload is `EventCorrectionPayload(reason: str, note: str \| None)`. |
| FR-5 | Functional | `EventStore.read_corrections(event_id, *, limit, after_seq) -> list[StoredEvent]` returns events whose `corrects_event_id == event_id` in ascending `global_seq`. |
| FR-6 | Functional | Correcting does not update or delete any existing row (the store remains append-only). |
| FR-7 | Functional | `corrects_event_id` defaults to `None`; ordinary events are unaffected. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision adds the column + index; `alembic check` clean. |
| NFR-3 | Integrity | A correction referencing a non-existent id is *allowed at the store layer* (validation is a higher-layer concern, §9) but must never corrupt or hide the original. |

## 5. API & event contracts

```python
class EventCorrectionPayload(BaseModel):     # frozen
    reason: str
    note: str | None = None

class EventCorrected(LifeEvent[EventCorrectionPayload]):
    event_type: Literal["timeline.event_corrected"] = "timeline.event_corrected"
    schema_version: Literal[1] = 1
    # corrects_event_id (from the envelope) must be set to the target event.

# EventStore gains:
def read_corrections(self, event_id: UUID, *, limit: int = 100,
                     after_seq: int | None = None) -> list[StoredEvent]: ...
```

- **Envelope change:** `LifeEvent.corrects_event_id: UUID | None = None` —
  additive and backward-compatible (existing events serialize with `null`).
- A helper `correct_event(target, *, reason, note=None, source, correlation_id,
  occurred_at)` may be provided to build an `EventCorrected` for a
  `StoredEvent`/id, setting `corrects_event_id`.

## 6. Data model & migration strategy

- Add nullable `corrects_event_id` to `EventRow` with an index
  (`ix_events_corrects_event_id`) for the reverse lookup.
- New Alembic revision `0004_event_correction` adds the column + index;
  `alembic check` clean.
- `EventCorrected`/`EventCorrectionPayload` live beside the reference event
  (e.g. `src/mylife/core/events/life_event.py` or a `correction.py` module).

## 7. Privacy, consent, access-control & retention

- A correction's `reason`/`note` are user data; not logged as payload contents.
- Corrections are the sanctioned way to "change" data while honoring
  immutability; true erasure for data-subject rights (`T2.5`) remains a separate,
  audited path and does not go through this mechanism.

## 8. Test plan

Integration tests on SQLite:

- **Correction round-trip (AC1):** append an original, then an `EventCorrected`
  with `corrects_event_id` = original id; both are readable; original unchanged.
- **Reverse lookup (AC2/FR-5):** `read_corrections(original_id)` returns the
  correction(s) in order; unrelated events excluded.
- **Domain supersession (AC3):** a `LifeEventRecorded` with `corrects_event_id`
  round-trips (incl. `rehydrate`).
- **Immutability (AC4/FR-6):** original row's fields are identical before/after
  the correction; the correction has a distinct `global_seq`.
- **Default (FR-7):** ordinary events have `corrects_event_id is None`.
- **Migration (NFR-2):** covered by CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T1.1` (envelope, extended here), `T1.2` (store, extended
  here).
- **Open decisions (resolved for this spec):**
  - *Supersession link location.* → **Envelope field `corrects_event_id`**
    (uniform for any event), mirroring how `raw_record_id` was added in `T1.4`.
  - *Explicit vs implicit correction.* → **Both**: a dedicated `EventCorrected`
    type for retractions/annotations, and the generic link for domain events
    that replace prior data.
  - *Referential integrity.* → **No DB foreign key** now; the target is a plain
    id reference. Existence/authorization checks belong to the application layer
    that issues corrections, keeping the append-only store simple and
    partition-friendly.
- **Risks:**
  - *Correction chains / cycles* (A corrects B corrects A) — out of scope here;
    the effective-view projection (`T3.x`) will define resolution rules.
  - *Orphan corrections* (target missing) — allowed at the store layer; flagged
    as an app-layer validation concern.
- **Future work:** effective-timeline projection that applies corrections
  (`T3.1`/`T3.3`); app-layer validation that the target exists and belongs to the
  same user; correction of corrections semantics.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Migration reviewed; backlog + spec status updated; T1.1/T1.2 docs note the extension.
- [ ] Immutability verified (original unchanged after correction); no payload/secret logging.
