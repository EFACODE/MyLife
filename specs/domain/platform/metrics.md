# Spec: Platform — Prometheus metrics foundation + HTTP instrumentation (`T9.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Draft — awaiting approval
- **Backlog task:** `T9.1` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (T9 epic)
- **Bounded context:** Platform (cross-cutting)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T0.1` (app shell), `T0.8` (correlation-id middleware / structured logging)

## 1. Purpose & business context

The platform is feature-complete for the backend MVP (Phases 0–5); it now needs to
be **operable**. This task lays the observability foundation: a **Prometheus
metrics endpoint** and automatic **HTTP instrumentation**, so latency, throughput
and error rates are visible per route. It is the first half of the *import →
insight → forecast* traceability story (domain metrics follow in `T9.2`, tracing
later).

Consistent with the codebase's **dependency-light, ports-and-adapters** philosophy
(dependency-free `HashingEmbedder`, filesystem `BlobStore`, rule-based assistant),
this increment ships a **small, self-contained metrics registry** that renders the
Prometheus text exposition format — **no new runtime dependency**. `prometheus_client`
(multiprocess) and OpenTelemetry are documented as the production path.

## 2. Scope

- **In scope:**
  - A metrics registry: `Counter`, `Histogram` (fixed buckets), `Gauge`, each with
    optional label sets, collected in a `CollectorRegistry` that renders valid
    Prometheus text exposition (`# HELP` / `# TYPE` / samples).
  - Default HTTP metrics: `http_requests_total` (counter), `http_request_duration_seconds`
    (histogram), `http_requests_in_flight` (gauge).
  - `MetricsMiddleware` recording those on every request, labelled by `method`, the
    **route template** (e.g. `/forecasts/{forecast_id}`, never the concrete path)
    and `status`.
  - `GET /metrics` returning the exposition (text/plain; unauthenticated).
- **Out of scope (later):**
  - Domain/event metrics + readiness probe (`T9.2`); OpenTelemetry tracing + Grafana
    dashboards; multiprocess metric aggregation; push-gateway; alert rules.

## 3. User stories & acceptance criteria

- As an **operator**, I scrape one endpoint and see how the API behaves.
  - **AC1:** After requests are served, `GET /metrics` returns Prometheus text with
    `http_requests_total`, `http_request_duration_seconds` (`_bucket`/`_sum`/`_count`)
    and `http_requests_in_flight`, each with valid `# HELP`/`# TYPE` headers.
  - **AC2:** Metrics are labelled by `method`, `route` and `status`; the `route`
    label is the **matched route template**, so per-id paths (e.g.
    `/forecasts/<uuid>`) collapse to one series and **no id/PII appears** in labels.
  - **AC3:** An unmatched path (404) is recorded under a fixed `route="__unmatched__"`
    label — never the raw path — so unknown URLs cannot explode cardinality.
  - **AC4:** `http_requests_total` increments per request and the histogram's
    `_count` matches; `http_requests_in_flight` returns to its baseline after a
    request completes (decremented even if the handler raised).
- As a **developer**, I record my own metric.
  - **AC5:** `Counter/Histogram/Gauge` support `.labels(...)` and
    `inc/observe/set`; unlabelled metrics work without `.labels()`; the registry
    renders them all.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `CollectorRegistry` holds metrics and `render()`s the Prometheus text exposition. Module-level default `REGISTRY`; `render_latest()` renders it. Content type `text/plain; version=0.0.4; charset=utf-8`. |
| FR-2 | Functional | `Counter(name, documentation, labelnames=())` with `.labels(**vals).inc(amount=1.0)` (and direct `.inc()` when unlabelled); monotonic, ≥0. |
| FR-3 | Functional | `Histogram(name, documentation, labelnames=(), buckets=DEFAULT)` with `.observe(value)`; cumulative `_bucket{le=…}` (incl. `+Inf`), `_sum`, `_count`. `DEFAULT_BUCKETS = (.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10)`. |
| FR-4 | Functional | `Gauge(name, documentation, labelnames=())` with `inc/dec/set`. |
| FR-5 | Functional | Label values are escaped (`\\`, `\"`, `\n`); sample lines are `name{k="v",…} value`. Metric names/labels validated against `[a-zA-Z_][a-zA-Z0-9_]*`. Thread-safe (a lock) for concurrent requests. |
| FR-6 | Functional | `MetricsMiddleware`: increment `http_requests_in_flight`; time the request; on completion observe `http_request_duration_seconds` and increment `http_requests_total` with `{method, route, status}`; decrement in-flight in a `finally`. `route` = matched route template or `__unmatched__`. |
| FR-7 | Functional | `GET /metrics` → `render_latest()` as `PlainTextResponse` with the exposition content type; unauthenticated; excluded from its own duration metric is **not** required (it may measure itself). |
| NFR-1 | Privacy | Labels carry **no** user id, path parameter value, query string or PII — only method, route template and status. `/metrics` exposes aggregate operational data only; it is intended to be network-restricted in production (documented). |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration**. |
| NFR-3 | Testability | Registry unit tests (counter/histogram/gauge render, label escaping, name validation) + endpoint/middleware tests (metrics present, route-template label, in-flight baseline, 404 handling). |

## 5. API & event contracts

```
GET /metrics   -> 200 text/plain; version=0.0.4
# HELP http_requests_total Total HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/health",status="200"} 1
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",route="/health",status="200",le="0.005"} 1
... le="+Inf" ... _sum ... _count ...
# TYPE http_requests_in_flight gauge
http_requests_in_flight 0
```

- **No events, no auth, no persistence.**

## 6. Data model & migration strategy

- **No tables, no migration.** New module `src/mylife/core/metrics.py` (registry +
  metric types + default HTTP metrics + `render_latest`), `src/mylife/core/metrics_middleware.py`
  (`MetricsMiddleware`), route in `src/mylife/api/metrics.py`; both middleware and
  router wired in `main.py` (metrics middleware added so it observes the whole
  request, i.e. outermost).

## 7. Privacy, consent, access-control & retention

- Metrics are process-local counters with no user data; labels are bounded to
  method/route/status (NFR-1). `/metrics` is unauthenticated by design (standard for
  in-cluster scraping) and should be exposed only on a protected network/port in
  production — noted in the module docstring. Nothing is persisted or logged.

## 8. Test plan

- **Registry (AC5/FR-2–5):** counter increments + renders; histogram buckets/sum/count
  cumulative and correct; gauge set/inc/dec; label escaping; invalid name rejected.
- **Endpoint (AC1):** hit `/health`, then `/metrics` shows the three metrics with
  headers.
- **Route label (AC2):** a request to a parameterised route (e.g. `/forecasts/{id}`,
  or a stub route) is labelled with the **template**, not the concrete id.
- **Unmatched (AC3):** a 404 path is recorded as `route="__unmatched__"`.
- **In-flight (AC4):** `http_requests_in_flight` is back to baseline after requests.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** app shell, correlation-id middleware.
- **Open decisions (resolved):**
  - *Dependency-free registry now.* → mirrors the codebase's adapter philosophy; a
    swap to `prometheus_client`/OpenTelemetry is a documented, isolated change.
  - *Route-template labels only.* → protects cardinality and privacy; unmatched
    paths collapse to a constant label.
  - *`/metrics` unauthenticated.* → matches Prometheus scraping norms; network
    restriction is the production control (documented), not app auth.
- **Risks:**
  - *Per-process metrics* — with multiple workers each exposes its own; a scraper
    aggregates, or multiprocess mode (future) is needed. Documented, acceptable for
    MVP.
  - *`BaseHTTPMiddleware` route access* — the matched route is read from the request
    scope after the downstream app runs; fallback `__unmatched__` covers the gap.
- **Future work:** domain/event metrics + readiness (`T9.2`), OTel tracing, Grafana
  dashboards, multiprocess aggregation, alerting.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no dependency/migration.
- [ ] `/metrics` exposes HTTP metrics with route-template/method/status labels and
      no PII; in-flight gauge is leak-free; backlog + spec status updated.
