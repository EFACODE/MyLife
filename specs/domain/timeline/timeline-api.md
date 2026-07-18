# Spec: Timeline query API (`T3.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T3.1` — [issue #19](https://github.com/EFACODE/MyLife/issues/19)
- **Bounded context:** Timeline
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.1`–`T1.5` (event kernel)

## 1. Purpose & business context

With the event kernel in place, users (and later the briefing/assistant) need a
**read API** over the timeline: list a user's Life Events, filtered by time,
type and source, with **provenance included**, paginated. This is the first HTTP
surface of the Timeline context and the foundation the manual-capture flow
(`T3.2`) and briefing (`T3.6`) read from.

Identity does not exist yet (`T2`), so `user_id` is an explicit request
parameter for now; §7 records how this endpoint becomes auth/consent-gated once
`T2` lands. The endpoint always filters by `user_id`, so it cannot leak across
users.

## 2. Scope

- **In scope:**
  - A read-only query service over the `events` table and a FastAPI endpoint
    `GET /timeline/events`.
  - Filters: `user_id` (required), `occurred_from`/`occurred_to`, `event_type`
    (repeatable), `source` (repeatable).
  - Offset/limit pagination with a `has_more` flag; deterministic ordering.
  - Response includes provenance (`raw_record_id`, `corrects_event_id`).
- **Out of scope (later tasks):**
  - Writing/capturing events (`T3.2`).
  - Applying corrections to produce an "effective" view / hiding superseded
    events (`T3.3`, briefing).
  - Authentication/authorization and consent enforcement (`T2`).
  - Full-text/semantic search (`T6`).

## 3. User stories & acceptance criteria

- As a **client**, I want to list a user's events filtered by time/type/source,
  so I can render a timeline.
  - **AC1:** `GET /timeline/events?user_id=U` returns only user `U`'s events.
  - **AC2:** `occurred_from`/`occurred_to` restrict to that inclusive UTC window;
    `event_type`/`source` (repeatable) restrict to those values (OR within a
    field, AND across fields).
  - **AC3:** Results are ordered newest-first by `occurred_at` (tie-break by
    append order), and each item includes `raw_record_id` and
    `corrects_event_id`.
  - **AC4:** `limit`/`offset` paginate; the response reports `has_more` without
    requiring a separate count.
- As an **API consumer**, I want validation errors for bad input.
  - **AC5:** Missing `user_id`, `limit` out of range, or a naive datetime yields
    `422`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `GET /timeline/events` accepts `user_id` (UUID, required), `occurred_from`/`occurred_to` (UTC datetimes, optional), `event_type` (repeatable, optional), `source` (repeatable, optional), `limit` (default 50, 1–200), `offset` (default 0, ≥0). |
| FR-2 | Functional | The query always filters by `user_id`; time bounds are inclusive; `event_type`/`source` are OR-within / AND-across filters. |
| FR-3 | Functional | Ordering is `occurred_at DESC, global_seq DESC` (stable, deterministic). |
| FR-4 | Functional | Response is `{ items: [TimelineEvent], limit, offset, has_more }`; `has_more` is computed by fetching `limit + 1` rows (no count query). |
| FR-5 | Functional | `TimelineEvent` includes `event_id, user_id, event_type, occurred_at, recorded_at, schema_version, source, correlation_id, raw_record_id, corrects_event_id, payload`. |
| FR-6 | Functional | A read-only `TimelineQueryService(session).query(filter) -> TimelinePage` encapsulates the query; the router maps HTTP ↔ service. |
| FR-7 | Functional | Datetimes are serialized as ISO-8601 UTC; naive datetime inputs are rejected (422). |
| FR-8 | Functional | The service performs no writes. |
| NFR-1 | Typing | Passes `mypy --strict`; request/response are typed Pydantic models. |
| NFR-2 | Testability | Service unit-tested on SQLite; endpoint tested via `TestClient` with a dependency-overridden session. |
| NFR-3 | Security | Endpoint always scopes to `user_id` (no cross-user leakage); documented as a pre-`T2` placeholder for real auth. |

## 5. API & event contracts

```
GET /timeline/events
  query: user_id=<uuid>            (required)
         occurred_from=<iso8601>   (optional, UTC)
         occurred_to=<iso8601>     (optional, UTC)
         event_type=<str>          (optional, repeatable)
         source=<str>              (optional, repeatable)
         limit=<int, 1..200=50>
         offset=<int, >=0=0>
  200 -> {
    "items": [ {
      "event_id": "...", "user_id": "...", "event_type": "timeline.life_event_recorded",
      "occurred_at": "2026-07-18T12:00:00+00:00", "recorded_at": "...",
      "schema_version": 1, "source": "manual", "correlation_id": "...",
      "raw_record_id": null, "corrects_event_id": null,
      "payload": { ... }
    } ],
    "limit": 50, "offset": 0, "has_more": false
  }
  422 -> validation error
```

- No events are produced by this task (read-only).

## 6. Data model & migration strategy

- **No schema change, no migration.** Reads the existing `events` table (`T1.2`).
- Proposed layout: `src/mylife/timeline/query.py` (filter, page and
  `TimelineQueryService`) and `src/mylife/api/timeline.py` (router). The router is
  registered in the app factory (`create_app`), and uses the existing
  `mylife.db.base.get_session` FastAPI dependency.

## 7. Privacy, consent, access-control & retention

- **Pre-`T2` placeholder:** `user_id` is currently an explicit parameter with no
  authentication. When Identity/consent land (`T2.2`/`T2.3`), the caller's
  identity replaces the parameter (or is authorized against it) and consent is
  enforced; this spec's endpoint is the seam for that change.
- The query is always `user_id`-scoped, so even now it cannot return another
  user's events. Payload contents are returned to the caller but never logged.

## 8. Test plan

- **Service filters (AC1–AC3):** seed events across users/types/sources/times;
  assert user scoping, time-window, type/source filtering, and ordering.
- **Provenance (AC3/FR-5):** items include `raw_record_id`/`corrects_event_id`.
- **Pagination (AC4/FR-4):** `limit`/`offset` slice correctly; `has_more` true
  when more remain, false on the last page.
- **API (NFR-2):** `TestClient` with an overridden session returns 200 + shape;
  missing `user_id`, out-of-range `limit`, and naive datetime return 422 (AC5).
- **Read-only (FR-8):** service exposes no write path (structural check).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), FastAPI, `mylife.db.base` session.
- **Open decisions (resolved for this spec):**
  - *Ordering.* → **`occurred_at DESC, global_seq DESC`** — chronological
    newest-first, with append order as a stable tie-break.
  - *Pagination.* → **offset/limit + `has_more`** (via `limit+1`) for a simple
    first API; keyset pagination can replace it later if needed.
  - *Effective view.* → **Not applied here**: this returns raw history including
    superseded events; applying corrections is a projection concern (`T3.3`).
- **Risks:**
  - *Offset drift* on concurrent appends — acceptable for v1; documented.
  - *`user_id` without auth* — mitigated by always scoping; hardened in `T2`.
- **Future work:** auth/consent gating (`T2`), effective/corrected view, richer
  filters and keyset pagination, search (`T6`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Endpoint registered and documented (OpenAPI at `/docs`); backlog + spec status updated.
- [ ] Always `user_id`-scoped; payloads not logged; pre-`T2` auth caveat recorded.
