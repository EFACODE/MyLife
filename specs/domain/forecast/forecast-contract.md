# Spec: Forecast — forecast contract + assumptions registry (`ForecastGenerated`) (`T8.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T8.1` — [issue #39](https://github.com/EFACODE/MyLife/issues/39) (T8 epic)
- **Bounded context:** Forecast *(new — the platform's decision-support context)*
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel), `T2.2` (auth), `T2.5` (erasure); consumes
  evidence from every domain's events. Sibling of `T7.1` (the Assistant evidence
  contract) — this is the **Forecast** analog for the future.

## 1. Purpose & business context

Phase 5 turns the digital twin from *understanding the past* into *reasoning about
the future* — **without false precision**. The brief's promise is *transparent
decision support*: a projection is only trustworthy if it says **what it assumed**
and **how uncertain it is**. This task makes that a **typed, enforced contract**,
exactly as `T7.1` did for AI claims.

`ForecastGenerated` is a structured projection that must carry: the **metric** and
**horizon** it covers, a **trajectory** of points each with an explicit
**uncertainty interval** (lower/upper), a **non-empty registry of named
assumptions** (each with its basis), the **evidence** (user-owned Life Events it
derives from), an overall **confidence** and **limitations**, and the **method**
(rule/model version). `ForecastService` **refuses to record a forecast with no
assumptions, no evidence, foreign evidence, or a malformed interval**, so the
guarantee holds for every caller — the manual API now, the forecasting models
(`T8.2`), the scenario simulator (`T8.3`) and the outcome loop (`T8.4`) later.
This increment is **rule-based / no-LLM**: it establishes the contract, storage and
enforcement; concrete forecasters plug in behind the same guarantees next.

## 2. Scope

- **In scope:**
  - An `Assumption` value object: `name`, `value`, `basis` (a human-readable,
    auditable statement of what was assumed and why).
  - A `ForecastPoint`: `at` (UTC), `value` (int), `lower` (int), `upper` (int) —
    integer units throughout (money in minor units, minutes, days, counts — never
    floats), with `lower ≤ value ≤ upper`.
  - A `Forecast` contract: `metric`, `unit`, `horizon_days`, `points` (≥1),
    `assumptions` (**≥1**), `evidence` (**≥1** event id), `confidence` (0–1),
    `limitations`, `method` (rule/model version), `generated_at`.
  - `ForecastGenerated` event (Forecast context) whose payload is forecast
    metadata + evidence ids (evidence is **references**, not copied data).
  - `ForecastService`: `generate` (validate assumptions non-empty, evidence
    non-empty **and every id one of the user's events**, points non-empty and each
    interval well-formed; append + publish; store), `get`, `list`, and
    `resolve_evidence` (return the referenced stored events).
  - Authenticated endpoints: `POST /forecasts`, `GET /forecasts`,
    `GET /forecasts/{forecast_id}` (with resolved evidence).
- **Out of scope (later):**
  - Concrete forecasting models (cash-flow / goal-completion) — `T8.2`.
  - "What-if" scenario simulation with assumption overrides — `T8.3`.
  - Recording actual outcomes + calibration — `T8.4`.
  - Any LLM generation; forecast supersession/correction.

## 3. User stories & acceptance criteria

- As the **platform**, I record forecasts that are always assumption-transparent,
  evidence-traceable and honest about uncertainty.
  - **AC1:** `POST /forecasts` with a metric, ≥1 point (well-formed interval), ≥1
    named assumption and ≥1 evidence event id (all the user's) records a
    `ForecastGenerated` and returns the stored forecast (generated id, fields,
    `generated_at`).
  - **AC2:** A forecast with **no assumptions** is rejected (`422`) — *every
    projection names its assumptions*.
  - **AC3:** A forecast with **empty evidence**, or an evidence id **not one of the
    user's events**, is rejected (`422`) — projections must trace to the user's own
    data.
  - **AC4:** A point whose interval is malformed (`lower > value` or
    `value > upper`) is rejected (`422`); `confidence` outside `[0, 1]` is rejected;
    `limitations` is required (uncertainty is always represented).
- As a **user**, I read my forecasts with their evidence.
  - **AC5:** `GET /forecasts` / `GET /forecasts/{id}` return my forecasts; the
    single view includes the **resolved evidence** (the referenced events).
    Foreign/unknown → `404`. All endpoints require auth (`401`); everything is
    user-scoped.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `Assumption` model: `name` (non-empty), `value` (non-empty), `basis` (non-empty). `ForecastPoint` model: `at` (UTC datetime), `value: int`, `lower: int`, `upper: int` with `lower ≤ value ≤ upper`. |
| FR-2 | Functional | `Forecast` model: `forecast_id`, `metric` (non-empty), `unit` (non-empty), `horizon_days: int` (≥1), `points: list[ForecastPoint]` (**≥1**), `assumptions: list[Assumption]` (**≥1**), `confidence: float` (`0 ≤ c ≤ 1`), `limitations` (non-empty), `method` (non-empty), `evidence: list[uuid]` (**≥1**), `generated_at`. |
| FR-3 | Functional | Table `forecasts`: `forecast_id` (UUID PK), `user_id` (UUID, indexed), `metric`, `unit`, `horizon_days` (int), `method`, `confidence` (float), `limitations`, `points` (JSON: list of `{at, value, lower, upper}`), `assumptions` (JSON: list of `{name, value, basis}`), `evidence` (JSON list of event-id strings), `generated_at` (UTC). |
| FR-4 | Functional | Event `forecast.forecast_generated` (`schema_version = 1`), payload `{forecast_id, metric, method, confidence, evidence}` (evidence = event-id references); appended + published (commit-before-publish, failure logged not raised). |
| FR-5 | Functional | `ForecastService.generate(user_id, metric, unit, horizon_days, points, assumptions, evidence, confidence, limitations, *, method, now, correlation_id)`: reject empty assumptions (`MissingAssumptionsError`); reject empty points (`EmptyForecastError`) and any malformed interval (`InvalidIntervalError`); reject empty evidence (`EmptyEvidenceError`) and verify **every** evidence id is one of the user's events (`UnknownEvidenceError`); persist the row, append + publish the event, return the `Forecast`. |
| FR-6 | Functional | `ForecastService.get`/`list` (user-scoped, newest first); `resolve_evidence(user_id, forecast_id)` returns the referenced `StoredEvent`s (skipping any since-erased). |
| FR-7 | Functional | Endpoints use `get_current_user`; validation failures → `422`, foreign/unknown forecast → `404`. Erasure (`T2.5`) includes `forecasts`. |
| NFR-1 | Security/Safety | The contract is enforced in the **service**, not just the API — no code path records an assumption-free, evidence-free or foreign-evidence forecast. Metric/assumption/limitation text is payload/row data, never logged. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency** (no LLM, no numeric/ML library here). |
| NFR-3 | Migration | One Alembic revision `0017_forecasts` creates `forecasts`; `env.py` imports the model; `alembic check` clean. |
| NFR-4 | Testability | Generate (event + row + resolved evidence), missing-assumptions rejection, empty-/foreign-evidence rejection, malformed-interval rejection, confidence bounds, scoping, auth, `404`. |

## 5. API & event contracts

```
POST /forecasts  { "metric": "cash_flow",
                   "unit": "BRL_minor",
                   "horizon_days": 30,
                   "points": [ { "at": "2026-08-18T00:00:00+00:00",
                                 "value": -120000, "lower": -180000, "upper": -60000 } ],
                   "assumptions": [ { "name": "recurring_income",
                                      "value": "steady at last 90d average",
                                      "basis": "3 salary credits, low variance" } ],
                   "evidence": ["<event_id>", "<event_id>"],
                   "confidence": 0.6,
                   "limitations": "Assumes no one-off large expenses in the window",
                   "method": "manual-v1" }                      -> 201 Forecast
GET  /forecasts                                                 -> [Forecast]
GET  /forecasts/{id}                                            -> ForecastDetail (404)

Assumption      = { name, value, basis }
ForecastPoint   = { at, value, lower, upper }        # ints; lower <= value <= upper
Forecast        = { forecast_id, metric, unit, horizon_days, points, assumptions,
                    confidence, limitations, method, evidence, generated_at }
ForecastDetail  = Forecast + { evidence_events: [StoredEvent] }
```

- **Event produced:** `ForecastGenerated` (Forecast context), evidence-referencing.

## 6. Data model & migration strategy

- `ForecastRow` on `Base` (table `forecasts`) — a **derived** record; evidence is
  stored as **event-id references** (JSON), never copied event data (raw /
  normalized / derived separation). `points` and `assumptions` are structured JSON
  columns (small, forecast-owned metadata, not a copy of source facts). New Alembic
  revision `0017_forecasts`; `migrations/env.py` imports the model. Proposed layout:
  `src/mylife/forecast/contract.py` (models + `Forecast*` + `ForecastGenerated` +
  `ForecastService`), routes in `src/mylife/api/forecast.py`, wired in `main.py`.

## 7. Privacy, consent, access-control & retention

- Forecasts are sensitive derived data: authenticated, user-scoped; evidence must be
  the caller's own events. Metric/assumption/limitation text is never logged. Erasure
  (`T2.5`) removes `forecasts`; since evidence is by-reference, erasing the underlying
  events also strips a forecast's support (surfaced by `resolve_evidence`).

## 8. Test plan

- **Generate (AC1/FR-5):** valid forecast → `ForecastGenerated` + row + returned
  fields; `resolve_evidence` returns the events.
- **Missing assumptions (AC2):** rejected; nothing stored.
- **Evidence (AC3):** empty evidence → rejected; an id not in the user's stream →
  rejected.
- **Interval/bounds (AC4):** a point with `lower > value` or `value > upper` →
  rejected; `confidence` <0 or >1 → rejected; missing `limitations` → rejected.
- **Read/scoping (AC5):** list/detail user-scoped; foreign → `404`; auth `401`.
- **Erasure/migration:** `forecasts` removed on erase; `alembic check` clean.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel, auth, erasure; evidence spans all domains' events.
- **Open decisions (resolved):**
  - *Assumptions are first-class and required.* → a forecast with no named
    assumption is refused in the **service**, mirroring how an insight with no
    evidence is refused (`T7.1`). "Transparent decision support" is enforced, not
    advisory.
  - *Uncertainty is structural.* → every point carries `lower`/`upper`; a single
    number without an interval cannot be recorded. Overall `confidence` (bounded)
    and `limitations` (non-empty) are mandatory.
  - *Integer units.* → point values and bounds are integers in a named `unit`
    (money = minor units), consistent with the codebase's no-floats rule for
    money/health. `confidence` remains a bounded float (a derived measure).
  - *Evidence by reference.* → store event **ids**, resolve on read (never copy
    event data into the forecast).
  - *Forecast is a new bounded context.* → decision-support is distinct from the
    Assistant (which answers about the past); it reuses the same evidence
    discipline. The context map / ADRs are updated when the models land (`T8.2`).
  - *No LLM / no model here.* → this is the contract + store; concrete forecasters
    are `T8.2`, behind the same guarantees.
- **Risks:**
  - *Values are caller-supplied here* — real projection logic and calibrated
    intervals come with `T8.2`/`T8.4`; this task only guarantees the shape.
  - *Evidence can be erased* after the fact — `resolve_evidence` reflects only
    surviving events (honest degradation).
- **Future work:** forecasting models (`T8.2`), scenario simulation (`T8.3`),
  outcome/calibration loops (`T8.4`), forecast supersession via `EventCorrected`.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status
      updated; erasure includes `forecasts`.
- [ ] No forecast without ≥1 named assumption and user-owned evidence; every point
      carries a well-formed interval; confidence + limitations required; evidence
      stored by reference; data user-scoped and not logged.
