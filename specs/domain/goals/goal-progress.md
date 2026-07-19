# Spec: Goals — progress from domain events (`T5.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T5.2` — [issue #32](https://github.com/EFACODE/MyLife/issues/32)
- **Bounded context:** Goals
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T5.1` (goals/milestones), `T4.1`–`T4.4` (finance/health), `T2.2`

## 1. Purpose & business context

Make goals **self-updating**: instead of only manual milestones, derive a goal's
current value from the domain events that measure it — net worth from finance,
workout minutes/distance from health, spend from finance. A goal's `metric` picks
the source; progress is computed **read-time** and stays **evidence-linked** (the
events behind the number), feeding the briefing (`T5.3`).

## 2. Scope

- **In scope:**
  - `GoalProgressService` computing, per goal, `current_value`, `progress_ratio`,
    `achieved`, the `source` used, and the `evidence` event ids.
  - A known metric set mapping `metric` → computation: `net_worth`,
    `workout_minutes`, `workout_distance`, `spend`; unknown metrics fall back to
    the **latest milestone** (`T5.1`).
  - Authenticated endpoints: `GET /goals/progress`, `GET /goals/{goal_id}/progress`.
- **Out of scope (later):**
  - Goals in the briefing (`T5.3`); trend/velocity/ETA; per-period windows;
    configurable metric definitions; a materialized progress projection.

## 3. User stories & acceptance criteria

- As a **user**, my goals show real progress from my data.
  - **AC1:** `GET /goals/{goal_id}/progress` returns `current_value`,
    `target_value`, `progress_ratio` and `achieved`, computed from the goal's
    metric; a foreign/unknown goal → `404`.
  - **AC2:** For `net_worth` the current value is my net worth in the goal's
    currency; for `workout_minutes`/`workout_distance` it is my summed workout
    minutes/metres; for `spend` it is my total outflow (magnitude).
  - **AC3:** An unknown/`manual` metric uses my latest milestone value for that
    goal (0 if none).
  - **AC4:** `GET /goals/progress` returns progress for all my goals.
- As the **platform**, progress is traceable and scoped.
  - **AC5:** Every progress result carries `evidence` (the event ids it was
    derived from) and is computed only from the caller's events. `progress_ratio`
    is a ratio (may exceed 1.0 when a target is beaten); values are integers.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `GoalProgressService.progress(user_id, goal)` → `GoalProgress{goal_id, metric, current_value (int), target_value (int), progress_ratio (float), achieved (bool), source (str), evidence (list[event_id])}`. |
| FR-2 | Functional | Metric map: `net_worth` → net worth in `goal.currency` (sum across currencies if `currency` is null); `workout_minutes` → Σ `duration_minutes`; `workout_distance` → Σ `distance_meters`; `spend` → Σ magnitude of finance outflow. |
| FR-3 | Functional | Unknown metric → latest `GoalMilestoneReached.value` for the goal (0 if none), `source = "milestone"`; known metrics use `source = "metric"`. |
| FR-4 | Functional | `progress_ratio = current_value / target_value` (0.0 when `target_value == 0`), rounded to 4 dp; `achieved = current_value >= target_value`. |
| FR-5 | Functional | `evidence` = the ids of the events the value was derived from (finance/health events for metrics; the milestone event for the fallback). |
| FR-6 | Functional | `progress_all(user_id)` returns progress for every goal, ordered by goal creation. |
| FR-7 | Functional | Endpoints use `get_current_user`; `404` for a goal that isn't the caller's. |
| NFR-1 | Typing | Passes `mypy --strict`; values integer, ratio float. |
| NFR-2 | Deps/Migration | **No new dependency, no migration** (read-time over the event store + `T4.3` net worth). |
| NFR-3 | Testability | Each metric (net worth, minutes, distance, spend), the milestone fallback, `achieved`, evidence, scoping, auth, `404`. |

## 5. API & event contracts

```
GET /goals/{goal_id}/progress   -> GoalProgress   (404 foreign)
GET /goals/progress             -> [GoalProgress]

GoalProgress = { goal_id, metric, current_value, target_value,
                 progress_ratio, achieved, source, evidence: [event_id] }
```

- **No events produced** (read-only projection).

## 6. Data model & migration strategy

- **No new tables, no migration.** Computed read-time from the event store
  (reusing `T4.3` `NetWorthService` for `net_worth`). Proposed layout:
  `src/mylife/goals/progress.py` (`GoalProgressService` + `GoalProgress`), routes
  added to `src/mylife/api/goals.py`.

## 7. Privacy, consent, access-control & retention

- Authenticated and user-scoped; progress reads only the caller's events. No
  payloads logged. Erasure (`T2.5`) removes the underlying events/goals, so
  progress reflects only surviving data.

## 8. Test plan

- **net_worth (AC2):** positions/txns → current value = net worth in currency;
  `achieved` when ≥ target; evidence includes the finance events.
- **workout minutes/distance (AC2):** workouts → summed value + evidence.
- **spend (AC2):** expenses → outflow magnitude + evidence.
- **milestone fallback (AC3):** unknown metric → latest milestone value/evidence.
- **progress_all (AC4)** and **scoping/auth/404 (AC1/AC5).**

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T5.1` goals, `T4.1`–`T4.4` finance/health, `T4.3` net worth.
- **Open decisions (resolved):**
  - *Metric set.* → `net_worth`, `workout_minutes`, `workout_distance`, `spend`;
    others fall back to milestones.
  - *All-time totals.* → metrics sum over all of the user's history (no window);
    per-period goals are future work.
  - *Read-time.* → no projection table (consistent with finance/health reads).
- **Risks:** metric/currency mismatches (e.g. `net_worth` goal without currency →
  cross-currency sum) — documented; `T5.x` can tighten.
- **Future work:** velocity/ETA vs `due_at`, windowed metrics, materialized
  projection, richer metric registry.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] Endpoints authenticated/in OpenAPI; backlog + spec status updated.
- [ ] Progress evidence-linked; values integer; data user-scoped.
