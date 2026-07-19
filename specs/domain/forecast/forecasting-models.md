# Spec: Forecast — forecasting models (cash-flow / goal-completion) (`T8.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T8.2` — [issue #39](https://github.com/EFACODE/MyLife/issues/39) (T8 epic)
- **Bounded context:** Forecast
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T8.1` (forecast contract), `T4.x` (finance), `T5.x` (goals)

## 1. Purpose & business context

`T8.1` gave the shape; this task fills it with **governed, rule-based
forecasters** that project the user's own history into the future — each **naming
its assumptions** and **citing the events it used**, with uncertainty that **widens
over the horizon** (no false precision). Two concrete models prove the pattern:
**cash-flow** (per currency) and **goal-completion** (projected metric value). They
run through `ForecastService` (`T8.1`), so every projection they emit inherits the
contract's guarantees. Still **no LLM, no numeric library** — plain arithmetic over
the event stream.

## 2. Scope

- **In scope:**
  - A `Forecaster` protocol and a `ForecastDraft` (the inputs to
    `ForecastService.generate`).
  - `CashFlowForecaster`: for each currency active in a lookback window, project the
    cumulative net flow at weekly steps to the horizon from the **average daily net
    flow**; interval widens with the horizon; evidence = the transactions used.
  - `GoalCompletionForecaster`: for each not-yet-achieved goal with a known metric
    and positive progress, project the metric value at weekly steps from the
    **average accumulation rate since the goal started**; evidence = the goal's
    progress events.
  - `ForecastingService.run(user_id, *, now, correlation_id, horizon_days=30)`:
    build drafts from all forecasters and record each via `ForecastService`,
    returning the stored `Forecast`s.
  - Authenticated `POST /forecasts/run` (optional `{horizon_days}`) → `[Forecast]`.
- **Out of scope (later):**
  - "What-if" overrides (`T8.3`); outcome/calibration (`T8.4`); seasonality,
    regression, confidence calibration, multi-metric correlation; scheduled runs.

## 3. User stories & acceptance criteria

- As a **user**, I get forward-looking projections grounded in my own data.
  - **AC1:** With transactions in range, `run` records a **cash-flow** `Forecast`
    per active currency: `metric = "cash_flow"`, `unit = "{CUR}_minor"`, weekly
    points to the horizon, ≥1 assumption, evidence = the transactions used, each
    point a well-formed widening interval.
  - **AC2:** With a not-yet-achieved, known-metric goal that has positive progress,
    `run` records a **goal-completion** `Forecast`: `metric = "goal_progress"`,
    `unit = goal.unit`, projected values at weekly steps, ≥1 assumption, evidence =
    the goal's progress events.
  - **AC3:** Every produced forecast passes the `T8.1` contract (≥1 assumption, ≥1
    user-owned evidence id, `lower ≤ value ≤ upper` on every point) — i.e. the
    forecasters never construct a forecast the service would reject.
  - **AC4:** With **no** usable data (no transactions / no eligible goal), `run`
    records nothing and returns `[]` — no fabricated projection.
  - **AC5:** `POST /forecasts/run` requires auth (`401`), is user-scoped, and
    returns the stored forecasts; they also appear in `GET /forecasts`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `ForecastDraft` = the `generate` inputs (`metric, unit, horizon_days, points, assumptions, evidence, confidence, limitations, method`). `Forecaster` protocol: `name: str`; `draft(session, user_id, *, now, horizon_days) -> list[ForecastDraft]` (read-only, user-scoped). |
| FR-2 | Functional | `CashFlowForecaster` (`method = "cash-flow-ma-v1"`): over a **28-day** lookback, per currency with ≥1 transaction, `avg_daily = net_minor / 28`; project `value(d) = round(avg_daily * d)` at day offsets `7, 14, …` up to `horizon_days` (plus `horizon_days` if not a multiple of 7); band `= max(round(abs(value)*0.5), 100)`, `lower = value - band`, `upper = value + band`; evidence = the lookback transaction ids (non-empty required); `confidence = 0.5`. |
| FR-3 | Functional | `GoalCompletionForecaster` (`method = "goal-trend-v1"`): for each goal with `progress.source == "metric"`, not `achieved`, `current_value > 0`, non-empty progress evidence, and `elapsed_days ≥ 1`: `rate = current_value / elapsed_days`; project `value(d) = current_value + round(rate * d)` at the same weekly offsets; band `= max(round(abs(value)*0.5), 1)`; evidence = `progress.evidence`; `confidence = 0.4`. |
| FR-4 | Functional | Each forecaster **names its assumptions** (e.g. cash-flow: `net_flow_rate`, `no_structural_change`; goal: `accumulation_rate`, `linear_extrapolation`) with a human-readable `value`/`basis`, and sets non-empty `limitations` (rule-based, not advice). |
| FR-5 | Functional | `ForecastingService.run(...)` iterates a governed forecaster list, calls `ForecastService.generate` per draft (contract enforced), returns the stored `Forecast`s. Empty data → `[]`. |
| FR-6 | Functional | `POST /forecasts/run` (auth, optional `{horizon_days ≥ 1}`, default 30) → `[Forecast]`, user-scoped. |
| NFR-1 | Non-functional | Uncertainty **widens** with the horizon (absolute band grows with the projected magnitude); no degenerate zero-width interval (band floor). No false precision. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration**. |
| NFR-3 | Testability | Unit tests per forecaster (points, widening interval, assumptions, evidence), the empty-data no-op, and the `/forecasts/run` endpoint (auth + records). |

## 5. API & event contracts

```
POST /forecasts/run   { "horizon_days": 30 }   ->  [Forecast]   # 201-style create list
```

- **Events produced:** one `ForecastGenerated` (`T8.1`) per recorded forecast. No
  new event type, no new endpoint schema beyond the run trigger.

## 6. Data model & migration strategy

- **No new tables, no migration.** New module `src/mylife/forecast/models.py`
  (`Forecaster`, `ForecastDraft`, `CashFlowForecaster`, `GoalCompletionForecaster`,
  `ForecastingService`); route added to `src/mylife/api/forecast.py`.

## 7. Privacy, consent, access-control & retention

- Read-only over the user's own finance/goal events; writes go through the
  user-scoped `ForecastService`. Nothing logged. Erasure already removes
  `forecasts` (`T8.1`).

## 8. Test plan

- **Cash-flow (AC1/FR-2):** seed transactions → a `cash_flow` forecast per currency
  with weekly points, widening intervals, transaction evidence.
- **Goal-completion (AC2/FR-3):** seed a known-metric goal with progress → a
  `goal_progress` forecast with projected values and goal evidence.
- **Contract (AC3):** every produced forecast has ≥1 assumption, user-owned
  evidence, valid intervals (it round-trips through `ForecastService`).
- **Empty (AC4):** no data → `run` returns `[]`, records nothing.
- **API (AC5):** `POST /forecasts/run` needs auth; returns forecasts; they appear in
  `GET /forecasts`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T8.1`, finance (`T4.x`), goals (`T5.x`).
- **Open decisions (resolved):**
  - *Simple, explainable arithmetic.* → moving-average / linear-trend, no
    regression or ML; every number is reconstructable from the cited events.
  - *Uncertainty is structural and widening.* → an absolute band that grows with the
    projected magnitude, with a floor so no interval is zero-width.
  - *Forecasters can decline.* → thin/empty data records nothing (no fabrication),
    honouring "no false precision".
  - *Reuse the contract.* → forecasters only build drafts; `ForecastService`
    enforces assumptions/evidence/intervals, so they can't bypass the guarantees.
- **Risks:**
  - *Linear extrapolation is naive* — fine for an MVP with explicit low confidence
    and wide bands; seasonality/regression is future work.
  - *Confidence is a fixed heuristic here* — calibration comes with `T8.4`.
- **Future work:** scenario overrides (`T8.3`), outcome/calibration (`T8.4`),
  richer models, scheduled weekly forecasts.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] `run` records cash-flow + goal-completion forecasts through the contract,
      declines on empty data, and is exposed at `POST /forecasts/run`; backlog +
      spec status updated.
