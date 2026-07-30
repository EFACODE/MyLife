# Spec: Assistant — AI evidence contract (`InsightGenerated`) (`T7.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T7.1` — [issue #38](https://github.com/EFACODE/MyLife/issues/38)
- **Bounded context:** Assistant
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel), `T2.2` (auth); consumes evidence from
  every domain's events

## 1. Purpose & business context

Make the platform's non-negotiable — *"every AI claim must be traceable to
evidence and represent uncertainty"* — a **typed, enforced contract**. This task
defines `InsightGenerated`: a structured claim carrying its **evidence** (the Life
Events it derives from), **confidence**, **limitations** and a **safe next
action**, plus an `InsightService` that **refuses to record an insight without
user-owned evidence**. It is the spine every later assistant increment (grounded
Q&A `T7.2`, alerts `T7.3`, the safety harness `T7.4`) is built on. This increment
is **rule-based / no-LLM** — it establishes the contract, storage and enforcement;
a model plugs in behind the same guarantees later.

## 2. Scope

- **In scope:**
  - An `Insight` contract: `claim`, `rationale`, `evidence` (≥1 event id),
    `confidence` (0–1), `limitations`, `next_safe_action?`, `generator`
    (rule/model version), `generated_at`.
  - `InsightGenerated` event (Assistant context) whose payload is the insight
    metadata + evidence ids (evidence is **references**, not copied data).
  - `InsightService`: `generate` (validate evidence is non-empty **and every id is
    one of the user's events**, append + publish, store), `get`, `list`, and
    `resolve_evidence` (return the referenced stored events).
  - Authenticated endpoints: `POST /insights`, `GET /insights`,
    `GET /insights/{insight_id}` (with resolved evidence).
- **Out of scope (later):**
  - LLM generation / retrieval-grounded Q&A (`T7.2`); scheduled alerts (`T7.3`);
    the evaluation harness (`T7.4`); insight corrections/supersession.

## 3. User stories & acceptance criteria

- As the **platform**, I record insights that are always traceable and honest.
  - **AC1:** `POST /insights` with a claim and ≥1 evidence event id (all the
    user's) records an `InsightGenerated` and returns the stored insight
    (generated id, fields, `generated_at`).
  - **AC2:** An insight with **empty evidence** is rejected (`422`) — the contract
    forbids unsupported claims.
  - **AC3:** An evidence id that is **not one of the user's events** is rejected
    (`422`) — claims must trace to the user's own data.
  - **AC4:** `confidence` outside `[0, 1]` is rejected (`422`); `limitations` is
    required (uncertainty is always represented).
- As a **user**, I read my insights with their evidence.
  - **AC5:** `GET /insights` / `GET /insights/{id}` return my insights; the single
    view includes the **resolved evidence** (the referenced events). Foreign/unknown
    → `404`. All endpoints require auth (`401`); everything is user-scoped.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `Insight` model: `insight_id`, `claim` (non-empty), `rationale` (non-empty), `evidence: list[uuid]` (**≥1**), `confidence: float` (`0 ≤ c ≤ 1`), `limitations` (non-empty), `next_safe_action: str \| None`, `generator` (non-empty), `generated_at`. |
| FR-2 | Functional | Table `insights`: `insight_id` (UUID PK), `user_id` (UUID, indexed), `claim`, `rationale`, `confidence` (float), `limitations`, `next_safe_action` (nullable), `generator`, `evidence` (JSON list of event-id strings), `generated_at` (UTC). |
| FR-3 | Functional | Event `assistant.insight_generated` (`schema_version = 1`), payload `{insight_id, claim, confidence, generator, evidence}` (evidence = event-id references); appended + published (commit-before-publish). |
| FR-4 | Functional | `InsightService.generate(user_id, claim, rationale, evidence, confidence, limitations, *, next_safe_action=None, generator, now, correlation_id)`: reject empty evidence (`EmptyEvidenceError`); verify **every** evidence id is one of the user's events via the event store (`UnknownEvidenceError` otherwise); persist the row, append + publish the event, return the `Insight`. |
| FR-5 | Functional | `InsightService.get`/`list` (user-scoped); `resolve_evidence(user_id, insight_id)` returns the referenced `StoredEvent`s (skipping any since-erased). |
| FR-6 | Functional | Endpoints use `get_current_user`; validation failures → `422`, foreign/unknown insight → `404`. Erasure (`T2.5`) includes `insights`. |
| NFR-1 | Security/Safety | The contract is enforced in the **service**, not just the API — no code path records an evidence-free or foreign-evidence insight. Claims/rationale are payload/row data, never logged. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency** (no LLM here). |
| NFR-3 | Migration | One Alembic revision creates `insights`; `alembic check` clean. |
| NFR-4 | Testability | Generate (event + row + resolved evidence), empty-evidence rejection, foreign-evidence rejection, confidence bounds, scoping, auth, `404`. |

## 5. API & event contracts

```
POST /insights   { "claim": "You overspent on food this week",
                   "rationale": "Food outflow exceeded your recent average",
                   "evidence": ["<event_id>", "<event_id>"],
                   "confidence": 0.8,
                   "limitations": "Based only on categorized transactions in range",
                   "next_safe_action": "Review the food transactions" }   -> 201 Insight
GET  /insights                                                            -> [Insight]
GET  /insights/{id}                                                       -> InsightDetail (404)

Insight        = { insight_id, claim, rationale, confidence, limitations,
                   next_safe_action, generator, evidence, generated_at }
InsightDetail  = Insight + { evidence_events: [StoredEvent] }
```

- **Event produced:** `InsightGenerated` (Assistant context), evidence-referencing.

## 6. Data model & migration strategy

- `InsightRow` on `Base` (table `insights`) — a derived record; evidence is stored
  as **event-id references** (JSON), never copied event data (raw/normalized/
  derived separation). New Alembic revision `0016_insights`; `env.py` imports the
  model. Proposed layout: `src/mylife/assistant/insight.py` (contract + service +
  `InsightGenerated`), routes in `src/mylife/api/insight.py`.

## 7. Privacy, consent, access-control & retention

- Insights are sensitive derived data: authenticated, user-scoped; evidence must be
  the caller's own events. Claim/rationale text is never logged. Erasure (`T2.5`)
  removes `insights`; since evidence is by-reference, erasing the underlying events
  also strips an insight's support (surfaced by `resolve_evidence`).

## 8. Test plan

- **Generate (AC1/FR-4):** valid insight → `InsightGenerated` + row + returned
  fields; `resolve_evidence` returns the events.
- **Empty evidence (AC2):** rejected; nothing stored.
- **Foreign evidence (AC3):** an id not in the user's stream → rejected.
- **Bounds (AC4):** `confidence` <0 or >1 → rejected; missing `limitations` → rejected.
- **Read/scoping (AC5):** list/detail user-scoped; foreign → `404`; auth `401`.
- **Erasure/migration:** `insights` removed on erase; `alembic check` clean.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel, auth; evidence spans all domains' events.
- **Open decisions (resolved):**
  - *Evidence by reference.* → store event **ids**, resolve on read (never copy
    event data into the insight).
  - *Enforced in the service.* → the non-empty, user-owned evidence rule lives in
    `InsightService`, so every caller (API, future `T7.2`/`T7.3`) inherits it.
  - *No LLM yet.* → this is the contract + store; generation grounded on retrieval
    is `T7.2`, behind the same guarantees.
  - *Uncertainty required.* → `confidence` (bounded) and `limitations` (non-empty)
    are mandatory fields.
- **Risks:**
  - *Confidence is caller-supplied here* — calibration/rules come with `T7.3`/`T7.4`.
  - *Evidence can be erased* after the fact — `resolve_evidence` reflects only
    surviving events (honest degradation).
- **Future work:** grounded generation (`T7.2`), alerts (`T7.3`), safety evals
  (`T7.4`), insight supersession via `EventCorrected`.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status
      updated; erasure includes `insights`.
- [ ] No insight without user-owned evidence; confidence + limitations required;
      evidence stored by reference; data user-scoped and not logged.
