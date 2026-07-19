# Spec: Goals context — Goals & milestones (`T5.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T5.1` — [issue #31](https://github.com/EFACODE/MyLife/issues/31)
- **Bounded context:** Goals
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel + bus), `T2.2` (auth)

## 1. Purpose & business context

Open the **Goals** bounded context: a user sets measurable targets (e.g. "save
BRL 10,000", "run 500 km") and records milestones toward them. `GoalCreated`
registers a target; `GoalMilestoneReached` records progress. Goals are the frame
that later ties finance/health facts to intent — `T5.2` derives progress from
domain events automatically, and `T5.3` surfaces goals in the briefing.

## 2. Scope

- **In scope:**
  - A `goals` registry (create/read/list), user-scoped, keyed by a `metric`.
  - `GoalCreated` / `GoalMilestoneReached` events (Goals context).
  - `GoalsService`: create a goal; read/list goals; record a milestone; list a
    goal's milestones.
  - Authenticated endpoints: `POST/GET /goals`, `GET /goals/{goal_id}`,
    `POST /goals/{goal_id}/milestones`, `GET /goals/{goal_id}/milestones`.
- **Out of scope (later):**
  - Automatic progress from finance/health events (`T5.2`); goals in the briefing
    (`T5.3`); goal editing/closing (corrections use `EventCorrected`, `T1.5`).

## 3. User stories & acceptance criteria

- As a **user**, I set a goal and record milestones toward it.
  - **AC1:** `POST /goals` (authenticated) returns the created goal (generated
    id, title, metric, target, unit).
  - **AC2:** `POST /goals/{goal_id}/milestones` records a `GoalMilestoneReached`
    and returns the milestone; a goal that isn't mine → `404`.
  - **AC3:** `GET /goals` / `GET /goals/{goal_id}` / `GET
    /goals/{goal_id}/milestones` return my goals/milestones (newest-first
    milestones); user-scoped.
- As the **platform**, targets are exact and scoped.
  - **AC4:** `target_value` and milestone `value` are integers (money in minor
    units, counts/distance in fixed units) — never floats. All endpoints require
    auth (`401`) and act only on the caller's data.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `goals`: `goal_id` (UUID PK), `user_id` (UUID, indexed), `title`, `metric` (str key, e.g. `net_worth`/`workout_minutes`), `target_value` (int), `unit` (str), `currency` (nullable, ISO-4217 for money metrics), `due_at` (nullable UTC), `created_at` (UTC). |
| FR-2 | Functional | Event `goals.goal_created` (`schema_version = 1`), payload `{goal_id, title, metric, target_value, unit, currency?, due_at?}`; appended + published (commit-before-publish). |
| FR-3 | Functional | Event `goals.milestone_reached` (`schema_version = 1`), payload `{goal_id, value (int), note?}`; appended + published. |
| FR-4 | Functional | `GoalsService`: `create_goal`, `get_goal`, `list_goals`, `record_milestone`, `list_milestones(goal_id, *, limit)`. `record_milestone` validates the goal belongs to the user (`UnknownGoalError`). |
| FR-5 | Functional | `list_milestones` reads `goals.milestone_reached` events for the user, filters by `goal_id`, maps to `Milestone` views (value, note, occurred_at, event_id), newest first. |
| FR-6 | Functional | Endpoints use `get_current_user`; goal/milestone data is always scoped to the caller. Erasure (`T2.5`) includes `goals`. |
| NFR-1 | Typing | Passes `mypy --strict`; targets/values are `int`. |
| NFR-2 | Migration | One Alembic revision creates `goals`; `alembic check` clean. |
| NFR-3 | Testability | Service + endpoints tested (create, milestone, list, scoping, auth, unknown goal). |

## 5. API & event contracts

```
POST /goals   { "title": "Emergency fund", "metric": "net_worth",
                "target_value": 1000000, "unit": "BRL", "currency": "BRL",
                "due_at": "2026-12-31T00:00:00+00:00" }        -> 201 Goal
GET  /goals                                                    -> [Goal]
GET  /goals/{goal_id}                                          -> Goal (404 foreign)
POST /goals/{goal_id}/milestones  { "value": 250000, "note": "Q1" } -> 201 Milestone
GET  /goals/{goal_id}/milestones                               -> [Milestone]

Goal      = { goal_id, title, metric, target_value, unit, currency, due_at, created_at }
Milestone = { event_id, goal_id, value, note, occurred_at }
```

- **Events produced:** `GoalCreated`, `GoalMilestoneReached` (Goals context).

## 6. Data model & migration strategy

- `GoalRow` on `Base` (table `goals`). Milestones are **events** (read from the
  event store), not a table — consistent with finance/health. New Alembic
  revision `0012_goals`; `env.py` imports the goals model. Proposed layout:
  `src/mylife/goals/` (models, service) + `src/mylife/api/goals.py`.

## 7. Privacy, consent, access-control & retention

- All endpoints authenticated and user-scoped; targets/notes are event/row data,
  never logged. Erasure (`T2.5`) removes a user's `goals` (added to the sweep) and
  their goal events with the rest of their events.

## 8. Test plan

- **Goal (AC1/FR-1):** create → returned + listed; scoped to user.
- **Milestone (AC2/FR-3/FR-4):** record → `GoalMilestoneReached` emitted; foreign
  goal → error.
- **List (AC3/FR-5):** milestones newest-first, filtered by goal; user-scoped.
- **Endpoints/auth (AC4):** authenticated flow; `401` without token; `404` foreign
  goal.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), auth (`T2.2`); erasure (`T2.5`) updated
  to include `goals`.
- **Open decisions (resolved for this spec):**
  - *Metric key.* → a free `metric` string (e.g. `net_worth`, `workout_minutes`);
    `T5.2` maps metrics to the domain events that measure them.
  - *Milestone storage.* → **events, not a table** (read via the event store),
    like finance/health.
  - *Registry.* → `goals` **is** a table (a managed aggregate with title/target/
    due), unlike transactions.
- **Risks:** metric strings are unvalidated here — `T5.2` defines the known set.
- **Future work:** auto-progress (`T5.2`), goals in briefing (`T5.3`), goal
  closing/archival, reminders.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec
      status updated; erasure includes `goals`.
- [ ] Targets/values integer; goal data user-scoped; payloads not logged.
