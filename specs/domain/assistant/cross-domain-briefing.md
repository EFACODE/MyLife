# Spec: Cross-domain briefing v2 (`T4.6`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T4.6` — [issue #30](https://github.com/EFACODE/MyLife/issues/30)
- **Bounded context:** Assistant
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T3.6` (briefing v1), `T4.1`–`T4.3` (finance), `T4.4`–`T4.5`
  (health), `T3.1`/`T3.5` (timeline/calendar), `T2.2` (auth)

## 1. Purpose & business context

Evolve the daily briefing from "counts of recent events" (`T3.6`) into the
brief's narrative example: **correlate sleep, training, calendar load and spend**
into a few plain-language observations — *"you slept 5h, have 3 meetings today,
and spending is above your recent average."* It stays **rule-based** (no AI) and
keeps the platform's non-negotiable: **every line links to the source events**
behind it. This is the payoff of Phase 2 — the first briefing that reasons across
Finance, Health and Timeline — and the seed for the AI evidence contract (`T7`).

## 2. Scope

- **In scope:**
  - Extend `BriefingService` to compute **domain signals** over the window from
    the event stream: sleep (`SleepRecorded`), training (`WorkoutCompleted`),
    calendar load (timeline events with `source = "calendar"`), spend (finance
    `ExpenseCreated`/`TransactionImported` outflow).
  - Add **domain-summary lines** (`sleep`, `training`, `calendar`, `spend`) and
    **correlation insight lines** (`insight`) that combine signals — each
    evidence-linked to the events it derives from.
  - A **spend baseline**: compare window outflow to the immediately preceding
    window of equal length ("above/below your recent average").
  - Preserve v1 lines (`total`/`category`/`source`) — v2 is a **superset**; the
    same `GET /briefing` returns the enriched briefing.
- **Out of scope (later):**
  - AI-generated narrative, forecasting/what-if (`T7`/`T8`).
  - Configurable thresholds/preferences, weekly/period rollups.
  - New persisted projections — signals are computed read-time.

## 3. User stories & acceptance criteria

- As a **user**, my daily briefing correlates how I slept, trained, my calendar
  and my spending.
  - **AC1:** When the window has a `SleepRecorded`, the briefing includes a
    `sleep` line (last night's duration) whose evidence is that event.
  - **AC2:** When the window has `WorkoutCompleted` events, a `training` line
    summarizes count/total minutes with those events as evidence; when it has
    none, an `insight` line notes no workout was logged (evidence: empty).
  - **AC3:** When the window has calendar events, a `calendar` line summarizes the
    load (e.g. "3 meetings"); its evidence is those events.
  - **AC4:** When the window has finance outflow, a `spend` line reports the total
    out per currency; an `insight` line compares it to the preceding window
    ("above/below your recent average") — evidence is the contributing txns.
  - **AC5:** A **combined insight** fires when signals coincide — e.g. short sleep
    (< threshold) **and** high calendar load (≥ threshold) → one line citing both
    the sleep event and the calendar events.
- As the **platform**, insights stay honest and traceable.
  - **AC6:** **Every** line (v1 and v2) carries `evidence` (event ids it is
    derived from). Insights are framed as observations, never predictions. All is
    computed only from the authenticated user's events.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Over the window, partition events by domain: sleep (`health.sleep_recorded`), training (`health.workout_completed`), calendar (`source == "calendar"`), spend (`finance.expense_created`/`finance.transaction_imported` with `amount_minor < 0`). |
| FR-2 | Functional | `sleep` line: most recent sleep session's `duration_minutes` (as `h m`); evidence = that event id. |
| FR-3 | Functional | `training` line: workout count + total minutes; evidence = those event ids. If zero workouts in the window, an `insight` line "No workout logged in the last Nh". |
| FR-4 | Functional | `calendar` line: count of calendar events ("N meetings"); evidence = those event ids. |
| FR-5 | Functional | `spend` line: total outflow per currency (sum of negative `amount_minor`, as minor units); evidence = those txn event ids. |
| FR-6 | Functional | Spend baseline `insight`: compare window outflow to the immediately preceding equal-length window per currency → "above/below/in line with your recent average"; evidence = the current window's txn event ids. |
| FR-7 | Functional | Combined `insight` (AC5): if last sleep `duration_minutes < SHORT_SLEEP_MINUTES` **and** calendar events `≥ BUSY_DAY_EVENTS`, emit one line citing the sleep event **and** the calendar event ids. Thresholds are module constants (documented). |
| FR-8 | Functional | v1 lines preserved; v2 lines appended. `BriefingLine` unchanged (`kind`, `summary`, `evidence`); new `kind`s: `sleep`, `training`, `calendar`, `spend`, `insight`. |
| FR-9 | Functional | `BriefingDelivered` event unchanged (`window_hours`, `event_count`, `line_count`) — `line_count` naturally reflects the richer briefing (no event schema change). |
| NFR-1 | Typing | Passes `mypy --strict`; money integer minor units; durations integer minutes. |
| NFR-2 | Deps/Migration | **No new dependency, no migration** (read-time over the event store). `alembic check` unaffected. |
| NFR-3 | Testability | Each domain line + each insight (present/absent, threshold boundaries, baseline above/below), evidence correctness, user-scoping, auth. |

## 5. API & event contracts

`GET /briefing?window_hours=24` (authenticated, unchanged route) → enriched
`Briefing`:

```
Briefing = { user_id, generated_at, window_hours, event_count,
             lines: [ BriefingLine ] }
BriefingLine = { kind, summary, evidence: [event_id] }
  kind ∈ { total, category, source,            # v1 (preserved)
           sleep, training, calendar, spend,    # v2 domain summaries
           insight }                            # v2 correlations
```

Example lines (window with short sleep + 3 meetings + overspend):

```
sleep     "Slept 5h 0m last night"                         [sleep-evt]
calendar  "3 meetings in the last 24h"                     [cal-1, cal-2, cal-3]
spend     "BRL 1,250.00 out in the last 24h"               [tx-1, tx-2]
insight   "Short sleep and a busy day (3 meetings) —       [sleep-evt, cal-1, cal-2, cal-3]
           protect focus time"
insight   "Spending is above your recent average"          [tx-1, tx-2]
```

- **Event produced:** `BriefingDelivered` (Assistant context), unchanged.

## 6. Data model & migration strategy

- **No new tables, no migration.** Signals are computed read-time from the event
  store within the window (and the preceding window for the spend baseline).
  Implemented by extending `src/mylife/assistant/briefing.py` (helper builders
  for domain lines + insights); the `/briefing` route is unchanged.

## 7. Privacy, consent, access-control & retention

- The briefing reads only the authenticated user's events (user-scoped via
  `get_current_user`). No payload text is logged; the response echoes only
  summaries and event ids. Erasure (`T2.5`) removes the underlying events, so
  briefings reflect only surviving data.

## 8. Test plan

- **Sleep (AC1/FR-2):** window with a sleep event → `sleep` line + correct
  evidence/duration.
- **Training (AC2/FR-3):** with workouts → `training` line; with none → the
  "no workout" insight.
- **Calendar (AC3/FR-4):** calendar events → `calendar` line, correct count/evidence.
- **Spend (AC4/FR-5/FR-6):** outflow → `spend` line per currency; baseline insight
  above vs. below by seeding the preceding window.
- **Combined insight (AC5/FR-7):** short sleep + busy day → one line citing both;
  boundary (exactly at threshold) does/does not fire as specified.
- **Evidence & scope (AC6):** every line has evidence; another user's events never
  appear. Auth: `GET /briefing` `401` without a token.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.6` briefing, `T4.1`–`T4.5` finance/health, timeline/calendar.
- **Open decisions (resolved for this spec):**
  - *Still rule-based.* → deterministic correlations, evidence-linked; AI narrative
    is `T7`.
  - *Superset, same route.* → v2 **enriches** the existing `/briefing` (v1 lines
    kept) rather than a new endpoint — backward compatible.
  - *Spend baseline.* → the **immediately preceding equal-length window**; richer
    baselines (rolling average) are future work.
  - *Thresholds.* → module constants (`SHORT_SLEEP_MINUTES`, `BUSY_DAY_EVENTS`);
    user-configurable preferences are future work.
  - *Read-time.* → computed from the event store (no projection), consistent with
    the finance/health read models.
- **Risks:**
  - *Threshold arbitrariness* — documented constants, evidence lets the user judge.
  - *Window scans* are O(events); acceptable now, projections later (noted).
- **Future work:** AI-generated narrative (`T7`), configurable thresholds, weekly
  rollups, goal-aware briefing (`T5.3`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; no migration
      (`alembic check` clean); v1 briefing tests still pass.
- [ ] `/briefing` enriched in OpenAPI; backlog + spec status updated.
- [ ] Every line evidence-linked; insights framed as observations; data
      user-scoped; payloads not logged.
