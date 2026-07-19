# Spec: Daily briefing v1 (`T3.6`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/assistant/briefing.py`, `src/mylife/api/briefing.py`, tests in `tests/test_briefing.py` + `tests/test_briefing_api.py`)
- **Backlog task:** `T3.6` — [issue #24](https://github.com/EFACODE/MyLife/issues/24)
- **Bounded context:** Assistant
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.x` (event kernel), `T3.1` (query), `T3.2` (bus wiring)

## 1. Purpose & business context

The MVP value loop's final step: **advise**. This task delivers a **rule-based,
evidence-linked daily briefing** — it aggregates a user's recent Life Events into
a few plain observations where **every line links to the exact source events**
behind it. No AI yet; this **seeds the AI evidence contract** (`T7`): a claim is
never made without its evidence. Generating a briefing emits a
`BriefingDelivered` event, so deliveries are themselves auditable on the
timeline. This closes Phase 1: capture → understand → **advise (with evidence)**.

## 2. Scope

- **In scope:**
  - A `BriefingService` that builds a briefing for a user over a time window from
    recent events, with each line carrying its evidence (source `event_id`s).
  - Deterministic, rule-based lines (totals, by category, by source).
  - Emitting `BriefingDelivered` (append + publish) on delivery.
  - `POST /briefing` returning the briefing.
- **Out of scope (later):**
  - Any AI/LLM reasoning, recommendations or natural-language generation (`T7`).
  - Cross-domain correlations (sleep/spend/etc.) — that is `T4.6` once those
    domains exist.
  - Scheduling/delivery channels (email/push); confidence/uncertainty scoring.
  - Auth/consent (`T2`) — `user_id` remains an explicit field.

## 3. User stories & acceptance criteria

- As a **user**, I want a short briefing of my recent activity where I can see
  the evidence behind every statement.
  - **AC1:** `POST /briefing` for a user returns a `Briefing` with a `total` line
    and per-`category` / per-`source` lines over the window.
  - **AC2:** **Every** line includes an `evidence` list of the `event_id`s it is
    derived from; the totals line's evidence is exactly the recent events.
  - **AC3:** Only the user's events within the window are considered; system
    events (`assistant.*`, e.g. prior briefings) are excluded from aggregation.
- As the **platform**, I want each delivery recorded.
  - **AC4:** Delivering a briefing appends and publishes a `BriefingDelivered`
    event (`source = "assistant"`) with the window/counts.
- As an **API consumer**, I want validation.
  - **AC5:** A missing `user_id` or out-of-range `window_hours` returns `422`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `BriefingService(session, bus).deliver(user_id, *, now, window_hours=24, correlation_id) -> Briefing`. |
| FR-2 | Functional | Recent events = the user's events with `occurred_at` in `[now - window_hours, now]`, **excluding** `assistant.*` event types. |
| FR-3 | Functional | Lines (deterministic order): a `total` line (all recent events as evidence); one `category` line per distinct payload `category` (its events as evidence); one `source` line per distinct `source` (its events as evidence). |
| FR-4 | Functional | Each `BriefingLine` has `kind`, `summary` (plain text) and `evidence: list[UUID]`; a `Briefing` has `user_id`, `generated_at`, `window_hours`, `event_count`, `lines`. |
| FR-5 | Functional | On delivery, append and publish a `BriefingDelivered` (`event_type = "assistant.briefing_delivered"`, `schema_version = 1`, payload `{window_hours, event_count, line_count}`, `source = "assistant"`), commit-before-publish (best-effort, mirroring `T3.2`). |
| FR-6 | Functional | `POST /briefing` body `{user_id, window_hours?}` returns `201` + the `Briefing`; `window_hours` defaults 24, range 1–720. |
| FR-7 | Functional | Empty window → a `total` line of `0` events (empty evidence) and no category/source lines. |
| NFR-1 | Typing | Passes `mypy --strict`; typed request/response models. |
| NFR-2 | Testability | Service unit-tested (deterministic `now`) and endpoint via `TestClient`. |
| NFR-3 | Security | Always `user_id`-scoped; payload text not logged; pre-`T2` caveat. |

## 5. API & event contracts

```
POST /briefing
  body: { "user_id": "<uuid>", "window_hours": 24 }
  201 -> {
    "user_id": "...", "generated_at": "...", "window_hours": 24, "event_count": 3,
    "lines": [
      { "kind": "total",    "summary": "3 events in the last 24h",   "evidence": ["<id>", "<id>", "<id>"] },
      { "kind": "category", "summary": "2 health events",            "evidence": ["<id>", "<id>"] },
      { "kind": "source",   "summary": "1 event from calendar",      "evidence": ["<id>"] }
    ]
  }
  422 -> validation error
```

- **Event produced:** `BriefingDelivered` (Assistant context), appended and
  published.

Illustrative shapes:

```python
class BriefingLine(BaseModel):
    kind: str          # "total" | "category" | "source"
    summary: str
    evidence: list[UUID]

class Briefing(BaseModel):
    user_id: UUID
    generated_at: datetime
    window_hours: int
    event_count: int
    lines: list[BriefingLine]
```

## 6. Data model & migration strategy

- **No new tables, no migration.** Reads `events` (`T1.2`); emits an event.
  Proposed layout: `src/mylife/assistant/briefing.py` (service + models +
  `BriefingDelivered`) and `src/mylife/api/briefing.py` (router), registered in
  the app factory. This starts the Assistant context.

## 7. Privacy, consent, access-control & retention

- The briefing is computed per user and returned only to the caller; summaries
  are derived from the user's own events. Payload text is not logged.
- Pre-`T2`: `user_id` is an explicit field; the endpoint is the seam for
  auth/consent gating (`T2.2`/`T2.3`).
- The evidence linkage (each line → its `event_id`s) is the auditability
  foundation the AI evidence contract (`T7`) builds on.

## 8. Test plan

- **Lines + evidence (AC1/AC2/FR-3):** seed events across categories/sources in
  the window; assert total/category/source lines with correct summaries and that
  each line's evidence matches the contributing `event_id`s.
- **Window + exclusion (AC3/FR-2):** events outside the window and `assistant.*`
  events are excluded.
- **Delivery event (AC4/FR-5):** a `BriefingDelivered` is appended (queryable)
  and published to a subscribed bus.
- **Empty (FR-7):** no events → single `total` line with `0`/empty evidence.
- **Endpoint (AC5/NFR-2):** `POST /briefing` → `201` + shape; missing `user_id`
  and out-of-range `window_hours` → `422`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel, query service (`T3.1`), bus + `get_event_bus`
  (`T3.2`).
- **Open decisions (resolved for this spec):**
  - *Read vs action.* → **`POST /briefing`**: generating a briefing is an action
    with a side effect (it emits `BriefingDelivered`), so it is not a pure GET.
  - *Exclude system events.* → **Yes**: `assistant.*` events (including prior
    briefings) are excluded from aggregation to avoid self-reference.
  - *Rules, not AI.* → v1 is **deterministic rules**; the AI evidence contract
    and reasoning are `T7`. Evidence linkage is established now.
  - *Window cap.* → **1–720 hours** (up to 30 days) for a bounded scan.
- **Risks:**
  - *Large windows* scanning many events — bounded by the window cap and a query
    limit; keyset/streaming is future work.
  - *False sense of insight* from counts — mitigated by keeping summaries factual
    and evidence-linked; no advice/claims beyond the data.
- **Future work:** cross-domain briefing (`T4.6`), AI evidence contract (`T7`),
  scheduling/delivery channels, confidence/uncertainty.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Endpoint registered/in OpenAPI; backlog + spec status updated.
- [ ] Every line evidence-linked; `BriefingDelivered` emitted; payloads not logged.
