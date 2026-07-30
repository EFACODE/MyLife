# Spec: Forecast — feedback / outcome loops (`T8.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T8.4` — [issue #39](https://github.com/EFACODE/MyLife/issues/39) (T8 epic)
- **Bounded context:** Forecast
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T8.1` (forecast contract), `T8.2` (models), `T2.5` (erasure)

## 1. Purpose & business context

A forecast only earns trust if we check it against reality. This task closes the
loop: the user records the **actual observed value** for a past forecast, and the
system reads back **calibration** — how close the projection was and whether the
outcome fell **inside the stated uncertainty interval**. That answers *"did the
projection hold up?"* and makes the forecasts **accountable** rather than
fire-and-forget. Recording an outcome is an **immutable event** (corrections are
new events, never mutations), consistent with the platform's invariants.

## 2. Scope

- **In scope:**
  - A `ForecastOutcomeRecorded` event + a `forecast_outcomes` store: an observed
    value at an observed time, recorded against one of the user's forecasts.
  - `OutcomeService.record(user_id, forecast_id, observed_value, observed_at, *,
    note=None, now, correlation_id)`: verify the forecast is the user's, persist +
    append + publish; `list_outcomes`.
  - `OutcomeService.calibrate(user_id) -> Calibration`: for each outcome, compare
    the observed value to the forecast's **nearest point** — error, and whether it
    landed **within the interval** — and aggregate (count, within-interval count,
    hit-rate, mean absolute error).
  - Authenticated `POST /forecasts/{forecast_id}/outcome` and
    `GET /forecasts/calibration`.
- **Out of scope (later):**
  - Feeding calibration back into confidence automatically; per-metric calibration
    dashboards; outcome connectors; scoring rules (Brier/CRPS); alerting on drift.

## 3. User stories & acceptance criteria

- As a **user**, I record what actually happened and see how good my forecasts were.
  - **AC1:** `POST /forecasts/{id}/outcome` with an observed value + time records a
    `ForecastOutcomeRecorded` and returns the stored outcome. Unknown/foreign
    forecast → `404`; auth required (`401`).
  - **AC2:** `GET /forecasts/calibration` returns, per recorded outcome, the
    forecast's nearest-point predicted value, the **error** (`observed - predicted`)
    and **within-interval** flag, plus aggregates: `total`, `within_interval`,
    `hit_rate`, `mean_abs_error`.
  - **AC3:** An outcome that lands inside the forecast's interval counts as a hit;
    one outside does not — so a well-calibrated forecast raises the hit-rate.
  - **AC4:** With no outcomes, calibration is an empty, zeroed report (no error).
    Everything is user-scoped; erasure removes `forecast_outcomes`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `forecast_outcomes`: `outcome_id` (UUID PK), `user_id` (UUID, indexed), `forecast_id` (UUID, indexed), `observed_value` (int), `observed_at` (UTC), `note` (nullable), `recorded_at` (UTC). |
| FR-2 | Functional | Event `forecast.outcome_recorded` (`schema_version = 1`), payload `{outcome_id, forecast_id, observed_value, observed_at}`; appended + published (commit-before-publish). |
| FR-3 | Functional | `OutcomeService.record(...)`: verify the forecast is the user's via `ForecastService.get` (`UnknownForecastError` otherwise); persist the row, append + publish, return the `Outcome`. `list_outcomes(user_id)` newest-first. |
| FR-4 | Functional | `calibrate(user_id)`: for each outcome, load its forecast, pick the point whose `at` is nearest `observed_at`; `error = observed - predicted`; `within_interval = lower ≤ observed ≤ upper`. Aggregate: `total`, `within_interval` (count), `hit_rate = within/total`, `mean_abs_error = mean(|error|)`. Skip outcomes whose forecast was since erased. |
| FR-5 | Functional | `POST /forecasts/{id}/outcome` (auth, `{observed_value, observed_at, note?}`, `404` unknown); `GET /forecasts/calibration` (auth) → `Calibration`. |
| FR-6 | Non-functional | Outcomes are immutable (append-only event + row); a correction is a new outcome, never a mutation. Erasure (`T2.5`) includes `forecast_outcomes`. |
| NFR-1 | Typing/Deps | Passes `mypy --strict`; **no new dependency**. |
| NFR-2 | Migration | One Alembic revision `0018_forecast_outcomes`; `env.py` imports the model; `alembic check` clean. |
| NFR-3 | Testability | Record + read; nearest-point + within-interval calibration; hit vs miss; empty report; unknown forecast `404`; auth; user-scoping. |

## 5. API & event contracts

```
POST /forecasts/{id}/outcome  { "observed_value": -95000,
                                "observed_at": "2026-08-18T00:00:00+00:00",
                                "note": "actual month-end cash flow" }   -> 201 Outcome
GET  /forecasts/calibration                                             -> Calibration

Outcome            = { outcome_id, forecast_id, observed_value, observed_at, note,
                       recorded_at }
CalibrationRecord  = { forecast_id, metric, observed_value, predicted_value, error,
                       within_interval, observed_at }
Calibration        = { total, within_interval, hit_rate, mean_abs_error,
                       records: [CalibrationRecord] }
```

- **Event produced:** `ForecastOutcomeRecorded` (Forecast context).

## 6. Data model & migration strategy

- `OutcomeRow` on `Base` (table `forecast_outcomes`) — an immutable observation
  linked to a forecast by id. New Alembic revision `0018_forecast_outcomes`;
  `migrations/env.py` imports it. Proposed layout: `src/mylife/forecast/outcome.py`
  (`Outcome`, `Calibration`, `OutcomeService`, `ForecastOutcomeRecorded`); routes in
  `src/mylife/api/forecast.py`.

## 7. Privacy, consent, access-control & retention

- Outcomes are the user's own observations: authenticated, user-scoped; recorded
  only against the caller's forecasts. Erasure (`T2.5`) removes `forecast_outcomes`.
  Notes are row data, never logged.

## 8. Test plan

- **Record (AC1/FR-3):** valid outcome → `ForecastOutcomeRecorded` + row; unknown
  forecast → error/`404`.
- **Calibration (AC2/AC3/FR-4):** an outcome inside the interval → hit; outside →
  miss; aggregates (`hit_rate`, `mean_abs_error`) reflect the records; nearest point
  is chosen by `observed_at`.
- **Empty (AC4):** no outcomes → zeroed report.
- **Erasure/migration/scoping:** `forecast_outcomes` removed on erase; `alembic
  check` clean; calibration user-scoped; auth `401`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T8.1`, `T8.2`, erasure.
- **Open decisions (resolved):**
  - *Outcomes are immutable events.* → corrections are new outcomes; history never
    mutates (platform invariant).
  - *Compare to the nearest point.* → an outcome is matched to the forecast point
    closest in time, so calibration is well-defined for multi-point trajectories.
  - *Interval hit-rate is the headline metric.* → "did reality fall inside the
    stated uncertainty?" is the honest test of a probabilistic forecast; richer
    scoring rules are future work.
- **Risks:**
  - *Small samples make hit-rate noisy* — reported as raw counts, not over-claimed;
    calibration feedback into confidence is deliberately future work.
- **Future work:** auto-adjust model confidence from calibration, per-metric
  dashboards, proper scoring rules, outcome connectors, drift alerts.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Outcomes recorded immutably against a user's forecast; calibration reports
      error + interval hit-rate; endpoints authenticated; erasure includes
      `forecast_outcomes`; backlog + spec status updated.
