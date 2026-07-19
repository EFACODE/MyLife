# Spec: Goals in the briefing (`T5.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T5.3` — [issue #33](https://github.com/EFACODE/MyLife/issues/33)
- **Bounded context:** Assistant × Goals
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T5.1`/`T5.2` (goals + progress), `T4.6` (cross-domain briefing)

## 1. Purpose & business context

Close the goals loop: surface **goal progress and risks** in the daily briefing so
the user sees, alongside sleep/spend/training, how they are tracking toward their
targets. Rule-based and **evidence-linked** (reusing `T5.2` progress evidence),
this makes the briefing goal-aware — the last piece of Phase 2.

## 2. Scope

- **In scope:**
  - Extend `BriefingService` to append, per goal, a `goal` progress line and an
    `insight` when a goal is **at risk** (past its `due_at` and not achieved).
  - Reuse `GoalProgressService` (`T5.2`) for values/evidence; lines carry that
    evidence.
- **Out of scope (later):**
  - Pace/velocity/ETA projections, reminders/notifications, per-goal windows.

## 3. User stories & acceptance criteria

- As a **user**, my briefing shows how my goals are tracking.
  - **AC1:** For each of my goals, the briefing includes a `goal` line with the
    title and progress (percent + current/target), evidence = the progress
    evidence event ids. Achieved goals are marked reached.
  - **AC2:** A goal past its `due_at` (relative to the briefing `now`) and not
    achieved adds an `insight` line flagging it at risk (same evidence).
  - **AC3:** With no goals, the briefing is unchanged (no goal/insight lines);
    an empty window still yields only the v1 total line.
- As the **platform**, goal lines stay traceable and scoped.
  - **AC4:** Every goal/insight line carries `evidence`; goals are the caller's
    only (progress is user-scoped).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | After the cross-domain lines, for each of the user's goals (creation order) append a `goal` line: `"Goal '<title>': <pct>% toward <target> <unit>"` (+ " — reached" when `achieved`), `evidence = progress.evidence`. |
| FR-2 | Functional | `pct = round(progress_ratio * 100)`; money metrics (goal has `currency`) format target as major units, else `target_value <unit>`. |
| FR-3 | Functional | If `goal.due_at` is set, `< now`, and not `achieved`, append an `insight` line: `"Goal '<title>' is past its due date and not yet reached"`, same evidence. |
| FR-4 | Functional | No goals → no goal/insight lines; the empty-window briefing still returns only the `total` line. Goal progress is all-time (not windowed) — documented. |
| FR-5 | Functional | Goal lines use `GoalProgressService` (`T5.2`) and the user's goals; user-scoped. `BriefingDelivered` event unchanged. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Deps/Migration | **No new dependency, no migration.** v1/v2 briefing tests still pass. |
| NFR-3 | Testability | Goal line (percent/evidence), achieved marker, at-risk insight (past due), no-goals unchanged, scoping. |

## 5. API & event contracts

`GET /briefing` (unchanged route) — `Briefing.lines` may now include:

```
goal     "Goal 'Emergency fund': 60% toward BRL 10,000.00"   [ …progress evidence ]
insight  "Goal 'Marathon' is past its due date and not yet reached"  [ …evidence ]
```

- **No new events**; `BriefingDelivered` unchanged.

## 6. Data model & migration strategy

- **No new tables, no migration.** Extends `src/mylife/assistant/briefing.py`
  with a goal-lines builder using `GoalProgressService`.

## 7. Privacy, consent, access-control & retention

- User-scoped (via `get_current_user` on `/briefing`); reads only the caller's
  goals/events. No payloads logged.

## 8. Test plan

- **Goal line (AC1/FR-1/FR-2):** a goal with progress → correct percent + evidence;
  achieved goal marked reached.
- **At risk (AC2/FR-3):** past-due unachieved goal → the at-risk insight.
- **No goals (AC3):** briefing unchanged; empty window still one line.
- **Scoping (AC4):** another user's goals never appear.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T5.1`/`T5.2` goals + progress, `T4.6` briefing.
- **Open decisions (resolved):**
  - *All-time progress.* → goal lines use `T5.2` all-time progress (not the
    briefing window); windowed pace is future work.
  - *At risk.* → **past due + not achieved** for now; pace-based risk is future work.
- **Risks:** N goals → N event-stream reads (via `T5.2`); acceptable now, a
  progress projection is the noted scale path.
- **Future work:** pace/ETA, reminders, goal categories in the briefing.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration; v1/v2
      briefing tests still pass.
- [ ] Goal/insight lines evidence-linked; data user-scoped; backlog + spec status
      updated.
