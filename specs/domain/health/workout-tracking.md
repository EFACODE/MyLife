# Spec: Health context — Sleep & Workouts (`T4.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T4.4` — [issue #28](https://github.com/EFACODE/MyLife/issues/28)
- **Bounded context:** Health
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel + bus), `T2.2` (auth)

## 1. Purpose & business context

Open the **Health** bounded context with its first two facts —
`SleepRecorded` (a sleep session) and `WorkoutCompleted` (a workout). Like every
domain, health publishes **immutable Life Events** into the kernel; a query reads
them back. This is the foundation for the health connector (`T4.5`, wearable /
Apple Health export) and the cross-domain briefing (`T4.6`), which correlates
sleep and training with calendar load and spend — the brief's narrative example.

## 2. Scope

- **In scope:**
  - `SleepRecorded` / `WorkoutCompleted` events (Health context).
  - `HealthService`: record a sleep session; record a workout (append + publish);
    list sleep sessions and workouts (read from the event store).
  - Authenticated endpoints (`get_current_user`, `T2.2`): `POST /health/sleep`,
    `POST /health/workouts`, `GET /health/sleep`, `GET /health/workouts`.
- **Out of scope (later):**
  - The wearable connector (`T4.5`); derived health metrics/trends, HR zones,
    readiness/recovery scores.
  - Editing/deleting (corrections use `EventCorrected`, `T1.5`).
  - The `T4.6` cross-domain correlation (separate task).

## 3. User stories & acceptance criteria

- As a **user**, I record last night's sleep and today's workout, and read them
  back on my health timeline.
  - **AC1:** `POST /health/sleep` (authenticated) records a `SleepRecorded` and
    returns the resulting sleep view.
  - **AC2:** `POST /health/workouts` records a `WorkoutCompleted` and returns the
    workout view.
  - **AC3:** `GET /health/sleep` / `GET /health/workouts` list the user's
    sessions/workouts, newest first.
- As the **platform**, I keep health metrics exact and scoped.
  - **AC4:** Durations are integer **minutes**, distance integer **meters**,
    energy integer **kcal** — never floats. All endpoints require authentication
    (`401` otherwise) and act only on the caller's data.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Event `health.sleep_recorded` (`schema_version = 1`), payload `{duration_minutes (int > 0), quality?}` where `quality` is an optional label (e.g. `"good"`); `occurred_at` (envelope) is the sleep start. |
| FR-2 | Functional | Event `health.workout_completed` (`schema_version = 1`), payload `{activity (str), duration_minutes (int > 0), distance_meters? (int ≥ 0), energy_kcal? (int ≥ 0)}`; `occurred_at` is the workout start. |
| FR-3 | Functional | Events appended (`T1.2`) and published (`T1.3`), commit-before-publish (best-effort publish). |
| FR-4 | Functional | `HealthService`: `record_sleep`, `record_workout`, `list_sleep(user_id, *, limit)`, `list_workouts(user_id, *, limit)`. |
| FR-5 | Functional | `list_*` read the health event types for the user from the event store and map payloads to `SleepSession` / `Workout` views (with `event_id`, `occurred_at`), newest first. |
| FR-6 | Functional | All measures are integers in fixed units (minutes/meters/kcal); no floating-point health data. |
| FR-7 | Functional | Endpoints use `get_current_user`; health data is always scoped to the caller. |
| NFR-1 | Typing | Passes `mypy --strict`; measures are `int`, validated (`> 0` / `≥ 0`). |
| NFR-2 | Deps/Migration | **No new dependency, no migration** (events only, like `T4.1` transactions). `alembic check` unaffected. |
| NFR-3 | Testability | Service + endpoints tested (record sleep/workout, list, newest-first, scoping, auth, validation). |

## 5. API & event contracts

```
POST /health/sleep      { "occurred_at": "2026-07-19T00:30:00+00:00",
                          "duration_minutes": 465, "quality": "good" }   -> 201 SleepSession
POST /health/workouts   { "occurred_at": "2026-07-19T07:00:00+00:00",
                          "activity": "run", "duration_minutes": 42,
                          "distance_meters": 8000, "energy_kcal": 520 }   -> 201 Workout
GET  /health/sleep                                                        -> [SleepSession]
GET  /health/workouts                                                     -> [Workout]

SleepSession = { event_id, occurred_at, duration_minutes, quality }
Workout      = { event_id, occurred_at, activity, duration_minutes, distance_meters, energy_kcal }
```

- **Events produced:** `SleepRecorded`, `WorkoutCompleted` (Health context).

## 6. Data model & migration strategy

- **No new tables, no migration.** Sessions/workouts are **events**, not a table
  — `list_*` reads the event store (health event types) and maps payloads to
  views (consistent with `T4.1` "transactions are events, not a table"). A
  materialized health projection can follow at scale. Proposed layout:
  `src/mylife/health/` (models, service) + `src/mylife/api/health.py` — note the
  existing `api/health.py` is the service **health check**; the new domain
  router lives in a distinct module (e.g. `api/health_tracking.py`) to avoid a
  name clash, mounted under `/health/*`.

## 7. Privacy, consent, access-control & retention

- Health is sensitive; all endpoints are authenticated and user-scoped. Payloads
  (durations, activities) are event payloads, never logged. Manual entry needs no
  connector consent; the **wearable connector** (`T4.5`) will be consent-gated
  (scope `"health"`) via `T2.3`. Erasure (`T2.5`) already removes a user's events,
  so health facts are erased with them.

## 8. Test plan

- **Sleep (AC1/FR-1):** record → `SleepRecorded` emitted/published; view returned;
  invalid `duration_minutes` (≤ 0) rejected.
- **Workout (AC2/FR-2):** record → `WorkoutCompleted`; optional distance/energy
  handled; view returned.
- **List (AC3/FR-5):** both kinds newest-first; user-scoped (another user's data
  not returned).
- **Endpoints/auth (AC4):** authenticated flow; `401` without a token.
- **Migration (NFR-2):** none — `alembic check` stays clean in CI.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), auth (`T2.2`).
- **Open decisions (resolved for this spec):**
  - *Units.* → **integer minutes / meters / kcal**, no floats (mirrors finance's
    integer-minor-units discipline).
  - *Storage.* → **events, not a table** (read via the event store); materialized
    projection is the noted scale path.
  - *Sleep model.* → `duration_minutes` + `occurred_at` (start) + optional
    `quality` label; sleep **stages** (deep/REM) are future work.
  - *Router naming.* → new domain router in a **distinct module** so it doesn't
    clash with the existing `/health` service health check.
- **Risks:**
  - *`quality` as a free label* may need an enum later (noted).
  - *Reading from events* may need a projection at scale (noted, as in `T4.1`).
- **Future work:** wearable connector (`T4.5`), sleep stages, HR/zones, readiness
  scores, health metrics/trends, `T4.6` cross-domain briefing.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; no migration
      (`alembic check` clean).
- [ ] Endpoints authenticated/in OpenAPI; backlog + spec status updated.
- [ ] Measures are integers in fixed units; health data user-scoped; payloads not
      logged.
