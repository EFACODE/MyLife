# Spec: Platform — domain instrumentation + readiness probe (`T9.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T9.2` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (T9 epic)
- **Bounded context:** Platform (cross-cutting)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T9.1` (metrics registry), `T1.2` (event store), `T0.7` (DB session)

## 1. Purpose & business context

`T9.1` made HTTP traffic observable; this task makes the **domain** observable and
the service **deployable**. It instruments the one chokepoint every context flows
through — `EventStore.append` — with a counter labelled by `event_type`, so a
single metric shows the whole *import → normalize → insight → forecast* pipeline
(insights and forecasts are themselves appended events, so they are counted for
free). It also adds a **readiness probe** that checks database connectivity, so an
orchestrator can tell *live* (process up) from *ready* (dependencies reachable).

Still **dependency-free** (reuses the `T9.1` registry); no migration.

## 2. Scope

- **In scope:**
  - `mylife_events_appended_total{event_type}` — incremented on every successful
    `EventStore.append`, covering all domains (timeline, finance, health, goals,
    knowledge, assistant insights, forecasts, outcomes).
  - `GET /health/ready` — a readiness probe running a trivial `SELECT 1` on the
    request-scoped session: `200 {status:"ready"}` when the DB answers, `503`
    otherwise. Liveness `GET /health` is unchanged.
- **Out of scope (later):**
  - Latency/error metrics per domain service; Redis/Celery readiness; OpenTelemetry
    tracing; Grafana dashboards; transactional/rollback-accurate counting.

## 3. User stories & acceptance criteria

- As an **operator**, I see event throughput by type and whether the app is ready.
  - **AC1:** After events are appended, `GET /metrics` shows
    `mylife_events_appended_total{event_type="..."}` with a count per type (e.g.
    `assistant.insight_generated`, `forecast.forecast_generated`,
    `finance.expense_created`).
  - **AC2:** `EventStore.append` increments the counter for the appended event's
    `event_type` exactly once per successful append; a duplicate append that raises
    `DuplicateEventError` does **not** increment it.
  - **AC3:** `GET /health/ready` returns `200 {status, version}` when the database
    responds, and `503` when the DB query raises. It is unauthenticated (like
    `/health`).
  - **AC4:** `GET /health` (liveness) still returns `200` and is independent of the
    database.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Add `EVENTS_APPENDED = Counter("mylife_events_appended_total", …, ("event_type",))` to the metrics module. |
| FR-2 | Functional | `EventStore.append` increments `EVENTS_APPENDED.labels(event_type=event.event_type)` **after** the row is flushed successfully; on `DuplicateEventError` (or any flush failure) it does not increment. |
| FR-3 | Functional | `GET /health/ready` depends on the DB session, executes `SELECT 1`; success → `ReadinessResponse{status="ready", version}`; on exception → `HTTPException(503)`. |
| FR-4 | Functional | `Counter.value(*labelvalues)` accessor (parity with `Gauge.value`) for assertions/introspection. |
| NFR-1 | Privacy | The event counter's only label is `event_type` (a bounded, non-identifying enum-like string). No `user_id`, payload or PII. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration**. |
| NFR-3 | Testability | Counter increments on append (and not on duplicate); readiness returns 200 on a live session and 503 when the query raises; liveness unaffected. |

## 5. API & event contracts

```
GET /health/ready  -> 200 { "status": "ready", "version": "…" }   | 503 (DB down)
# and, in /metrics:
mylife_events_appended_total{event_type="assistant.insight_generated"} 3
```

- **No new events, no persistence, no auth.**

## 6. Data model & migration strategy

- **No tables, no migration.** Touches `src/mylife/core/metrics.py`
  (`EVENTS_APPENDED`, `Counter.value`), `src/mylife/core/events/store.py` (increment
  in `append`), and `src/mylife/api/health.py` (readiness route).

## 7. Privacy, consent, access-control & retention

- Counter labelled only by `event_type`; no user data. Readiness runs a constant
  query and returns no data. Both endpoints are unauthenticated operational probes.

## 8. Test plan

- **Append counter (AC1/AC2):** append an event → the `event_type` counter rises by
  1; a duplicate append raises and does not increment.
- **Readiness (AC3):** a working session → `200 {status:"ready"}`; a session whose
  `execute` raises → `503`.
- **Liveness (AC4):** `/health` still `200`, no DB needed.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T9.1`, event store, DB session.
- **Open decisions (resolved):**
  - *Instrument the append chokepoint, not each service.* → one hook covers every
    context (insights/forecasts included), with no per-service coupling.
  - *Readiness ≠ liveness.* → liveness proves the process; readiness proves the DB
    dependency, so a DB blip fails readiness without killing the pod.
- **Risks:**
  - *Counting is best-effort, not transactional* — a counted append inside an outer
    transaction that later rolls back slightly over-counts. Acceptable for an
    operational gauge; documented.
- **Future work:** Redis/Celery readiness, per-domain latency metrics, OTel tracing,
  dashboards, transactional counting.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no dependency/migration.
- [ ] `mylife_events_appended_total` visible per type; `/health/ready` reflects DB
      health; liveness intact; backlog + spec status updated.
