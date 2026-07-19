# Spec: Forecast — "what-if" scenario simulation (`T8.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T8.3` — [issue #39](https://github.com/EFACODE/MyLife/issues/39) (T8 epic)
- **Bounded context:** Forecast
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T8.1` (forecast contract), `T8.2` (forecasting models)

## 1. Purpose & business context

Decision support means asking *"what if?"* — and doing so **honestly**. A scenario
takes an existing forecast as its base, applies **explicit, named assumption
overrides** and a scaling factor to the projection, and records the result as a new
`Forecast`. Because a hypothetical is less certain than the base, the simulation
**widens the relative uncertainty** and **discounts confidence** — never presenting
a what-if as a firmer prediction. A scenario *is* a forecast (same contract, same
evidence), so it inherits every guarantee and shows up alongside the base. Still
**no LLM** — plain, transparent arithmetic.

## 2. Scope

- **In scope:**
  - `ScenarioService.simulate(user_id, forecast_id, *, scale, overrides, label, now,
    correlation_id) -> Forecast`: load the user's base forecast, transform each
    point by `scale`, **widen** the interval, **merge** the named assumption
    overrides into the base assumptions (replace-by-name or append), add a
    `scenario` assumption naming the base, **discount** confidence, and record a new
    `Forecast` via `ForecastService` (same evidence).
  - A scenario must **change something** (`scale != 1.0` or at least one override),
    else it is rejected.
  - Authenticated `POST /forecasts/{forecast_id}/simulate`.
- **Out of scope (later):**
  - Recording actual outcomes / calibration (`T8.4`); optimisation ("find the scale
    that hits target"); multi-base blending; persisted scenario/base linkage columns.

## 3. User stories & acceptance criteria

- As a **user**, I explore a what-if over one of my forecasts, transparently.
  - **AC1:** `simulate` on my forecast with `scale = 1.2` records a new `Forecast`
    with the same `metric`/`unit`/`horizon`/evidence, point values scaled (~×1.2),
    a `scenario` assumption naming the base, and **lower confidence** than the base.
  - **AC2:** An `overrides` entry with the **same name** as a base assumption
    **replaces** its `value`/`basis` (the change is explicit); a new name is
    appended. The base forecast is left unchanged (a new one is recorded).
  - **AC3:** The simulated forecast's **relative uncertainty widens** — for every
    point, `band/│value│` is greater than the base's — so a what-if is never firmer
    than its base.
  - **AC4:** A no-op scenario (`scale == 1.0` and no overrides) is rejected (`422`);
    an unknown/foreign base forecast is `404`; the endpoint requires auth (`401`).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `ScenarioService.simulate`: load base via `ForecastService.get` (`UnknownForecastError` → 404). For each base point: `value' = round(value * scale)`; `band' = max(round(base_half_band * scale * WIDEN), FLOOR)`; `lower' = value' - band'`, `upper' = value' + band'` (`WIDEN = 1.5`, `FLOOR = 1`). |
| FR-2 | Functional | Assumptions: replace each base assumption whose `name` matches an override with the override's `value`/`basis`; append overrides with new names; then append `Assumption(name="scenario", value=label or f"scaled ×{scale}", basis=f"what-if over base forecast {base_id}")`. |
| FR-3 | Functional | `confidence' = round(base.confidence * CONFIDENCE_DISCOUNT, 4)` (`0.8`); `method = "scenario-v1"`; `metric`/`unit`/`horizon_days`/`evidence` copied from base; `limitations` prefixed with a "hypothetical scenario, not a prediction" note referencing the base id. Recorded via `ForecastService.generate` (contract enforced). |
| FR-4 | Functional | Reject a no-op scenario (`scale == 1.0` **and** no overrides) with `EmptyScenarioError`. `scale` must be `> 0`. |
| FR-5 | Functional | `POST /forecasts/{forecast_id}/simulate` (auth): body `{scale?=1.0, overrides?=[], label?}`; `422` on no-op/invalid, `404` on unknown base. |
| NFR-1 | Non-functional | Relative uncertainty strictly widens vs. the base (the `WIDEN` factor); confidence strictly decreases. A what-if never reads as firmer than its base. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration** (a scenario reuses the `forecasts` store). |
| NFR-3 | Testability | Unit tests: scale + widening + confidence discount, override replace-by-name, base-unchanged, no-op rejection, unknown base; API auth/404/422/201. |

## 5. API & event contracts

```
POST /forecasts/{id}/simulate  { "scale": 1.2,
                                 "overrides": [ { "name": "net_flow_rate",
                                                  "value": "20% higher",
                                                  "basis": "assume a raise" } ],
                                 "label": "optimistic" }        -> 201 Forecast

ScenarioRequest = { scale: float > 0 = 1.0, overrides: [Assumption] = [], label?: str }
```

- **Event produced:** a new `ForecastGenerated` (`T8.1`) for the simulated forecast.

## 6. Data model & migration strategy

- **No new tables, no migration.** New module `src/mylife/forecast/scenario.py`
  (`ScenarioService`, `EmptyScenarioError`); route added to
  `src/mylife/api/forecast.py`. Base↔scenario provenance is carried in the
  `scenario` assumption + `limitations` text (a persisted link column is future
  work).

## 7. Privacy, consent, access-control & retention

- Operates only on the user's own base forecast and events; the simulation is
  recorded user-scoped through `ForecastService`. Nothing logged. Erasure already
  removes `forecasts` (`T8.1`).

## 8. Test plan

- **Scale + discount (AC1):** simulate ×1.2 → new forecast, scaled values, lower
  confidence, `scenario` assumption, same evidence.
- **Override (AC2):** same-name override replaces value/basis; base forecast still
  present and unchanged.
- **Widening (AC3):** every simulated point has a larger `band/│value│` than the
  base point.
- **Guards (AC4):** no-op → `422`; unknown/foreign base → `404`; no auth → `401`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T8.1`, `T8.2`.
- **Open decisions (resolved):**
  - *A scenario is just another forecast.* → reuses the contract + store + evidence;
    no schema change, and it participates in listing and (later) outcomes.
  - *Honesty is enforced.* → relative uncertainty widens and confidence is
    discounted, so a what-if can never look firmer than its base.
  - *Changes must be explicit.* → overrides are named and merged transparently; a
    no-op scenario is refused.
- **Risks:**
  - *Scaling is a coarse lever* — it models "the same shape, more/less of it", not a
    structural change; richer parameterised scenarios are future work.
- **Future work:** persisted base↔scenario linkage, target-seeking optimisation,
  outcome/calibration (`T8.4`), scenario comparison views.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] `simulate` scales + widens + discounts, merges named overrides, refuses no-op,
      records via the contract, and is exposed at `POST /forecasts/{id}/simulate`;
      backlog + spec status updated.
