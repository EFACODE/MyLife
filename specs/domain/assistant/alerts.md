# Spec: Assistant — Alerts & weekly insights (`T7.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T7.3` — [issue #40](https://github.com/EFACODE/MyLife/issues/40)
- **Bounded context:** Assistant
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T7.1` (insight contract), `T4` (finance/health), `T5.2` (goal
  progress), `T0.9` (worker), `T2.2` (auth)

## 1. Purpose & business context

Proactively surface **governed, evidence-linked alerts** — overspend, an at-risk
goal, a short-sleep streak — as `InsightGenerated`s (`T7.1`). Each alert is a
**rule** over the user's own data that, when it fires, produces a claim citing the
events that triggered it. Rules are deterministic and transparent (no LLM); a
model may later phrase them, but the trigger and evidence stay governed. Runs on
demand and, via the worker (`T0.9`), on a weekly schedule.

## 2. Scope

- **In scope:**
  - A `Rule` port: `evaluate(session, user_id, now) -> list[RuleResult]` (a
    fired alert = claim/rationale/evidence event ids/confidence/limitations/next
    safe action). Three rules: `OverspendRule` (finance), `AtRiskGoalRule`
    (goals), `ShortSleepRule` (health).
  - `AlertsService.run(user_id, *, now, correlation_id)`: evaluate all rules and
    record an `InsightGenerated` per fired result via `InsightService`; return the
    insights.
  - A Celery task `run_weekly_insights(user_id)` and an authenticated endpoint
    `POST /assistant/alerts/run`.
- **Out of scope (later):**
  - LLM phrasing; user-configurable thresholds/rule toggles; notification delivery
    (email/push); dedup/suppression of repeat alerts; the safety harness (`T7.4`).

## 3. User stories & acceptance criteria

- As a **user**, I get proactive, evidence-backed alerts about my data.
  - **AC1:** `POST /assistant/alerts/run` evaluates the rules over **my** data and
    records one `InsightGenerated` per fired alert, returning them; each cites the
    triggering events as evidence.
  - **AC2:** **Overspend** — when my outflow in the last 7 days exceeds the prior
    7 days beyond a margin, an alert fires citing the recent outflow events.
  - **AC3:** **At-risk goal** — for each goal past its `due_at` and not achieved,
    an alert fires citing that goal's `GoalCreated` event.
  - **AC4:** **Short sleep** — when I logged short-sleep nights (< threshold) on
    ≥ N nights in the last 7 days, an alert fires citing those sleep events.
  - **AC5:** When no rule fires, no insight is recorded (empty result).
- As the **platform**, alerts stay governed and scoped.
  - **AC6:** Every alert is an `Insight` (evidence enforced, `T7.1`); rules read
    only the caller's data; the endpoint requires auth (`401`). Alerts state their
    limitations and never assert unsupported conclusions.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `RuleResult{claim, rationale, evidence: list[uuid], confidence, limitations, next_safe_action}`. `Rule` protocol: `name`, `evaluate(session, user_id, now) -> list[RuleResult]` (read-only, user-scoped). |
| FR-2 | Functional | `OverspendRule`: over the user's finance events, sum outflow (negative `amount_minor` magnitude) in `[now-7d, now]` vs `[now-14d, now-7d]` per currency; fire when current > prior × `OVERSPEND_RATIO` (or prior = 0 and current > 0); evidence = the current-window outflow event ids; `confidence` from the ratio (capped 1.0). |
| FR-3 | Functional | `AtRiskGoalRule`: for each goal (`T5.1`) with `due_at < now` and not achieved (`T5.2` progress), fire one result; evidence = that goal's `goals.goal_created` event id; `confidence` from how far short of target. |
| FR-4 | Functional | `ShortSleepRule`: count the user's `health.sleep_recorded` in `[now-7d, now]` with `duration_minutes < SHORT_SLEEP_MINUTES`; fire when count ≥ `SHORT_SLEEP_NIGHTS`; evidence = those sleep event ids. |
| FR-5 | Functional | `AlertsService.run` evaluates all rules; for each `RuleResult` calls `InsightService.generate(..., generator="alerts-v1")`; returns the recorded insights (empty if none fired). |
| FR-6 | Functional | Celery task `mylife.run_weekly_insights(user_id)` runs `AlertsService` against a real session + Redis publisher. Endpoint `POST /assistant/alerts/run` (`get_current_user`) → `[Insight]`. |
| NFR-1 | Security/Safety | Alerts are `Insight`s (evidence enforced); rules are read-only + user-scoped; thresholds are documented constants; claim text reports the trigger, not a domain conclusion. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration** (reuses `insights` + domain reads). |
| NFR-3 | Testability | Each rule (fires with the right evidence / stays silent), `run` records insights per fired alert, no-fire → empty, scoping, auth. |

## 5. API & event contracts

```
POST /assistant/alerts/run   -> 200 [ Insight ]   (one per fired alert; [] if none)
```

- **Event produced:** `InsightGenerated` (`T7.1`), one per fired alert.
- **Worker task:** `mylife.run_weekly_insights(user_id)`.

## 6. Data model & migration strategy

- **No new tables, no migration.** Alerts persist as `insights` (`T7.1`). Proposed
  layout: `src/mylife/assistant/alerts.py` (rules + `AlertsService`), a Celery task
  in `src/mylife/workers/tasks.py`, a route in `src/mylife/api/assistant.py`.

## 7. Privacy, consent, access-control & retention

- Authenticated and user-scoped; rules read only the caller's data; thresholds and
  claims are non-sensitive; underlying amounts/durations live in the cited events,
  never logged. Erasure (`T2.5`) removes the resulting `insights`.

## 8. Test plan

- **Overspend (AC2):** seed a big prior-week + small current-week (no fire) and a
  big current-week (fire with the current outflow events as evidence).
- **At-risk goal (AC3):** an overdue unachieved goal fires citing its
  `GoalCreated`; an on-track/undue goal does not.
- **Short sleep (AC4):** ≥ N short nights fire citing those events; fewer stays silent.
- **Run (AC1/AC5):** fired rules → insights recorded; nothing fired → `[]`.
- **Scoping/auth (AC6):** another user's data never triggers; endpoint `401`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T7.1`, finance/health events, `T5.1`/`T5.2` goals, `T0.9`.
- **Open decisions (resolved):**
  - *Governed rules, not LLM.* → deterministic triggers + evidence; a model may
    phrase later, trigger/evidence stay governed.
  - *Thresholds as constants* (`OVERSPEND_RATIO`, `SHORT_SLEEP_MINUTES`,
    `SHORT_SLEEP_NIGHTS`); user config is future work.
  - *Each run emits* — dedup/suppression of repeat alerts is future work (noted).
- **Risks:**
  - *Repeat alerts on repeated runs* — acceptable for MVP; suppression later.
  - *Weekly windows are fixed* — configurable periods later.
- **Future work:** notification delivery, dedup/suppression, configurable rules,
  more rules (net-worth drop, goal-pace), LLM phrasing under `T7.4` guardrails.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] Endpoint + Celery task; backlog + spec status updated.
- [ ] Every alert is an evidence-linked `Insight`; rules least-privilege + scoped;
      nothing fabricated.
