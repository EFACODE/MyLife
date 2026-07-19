# Spec: Platform — distributed trace context + trace-aware logging (`T9.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T9.3` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (T9 epic)
- **Bounded context:** Platform (cross-cutting)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T0.8` (correlation-id middleware + structured logging), `T9.1`/`T9.2`

## 1. Purpose & business context

Metrics (`T9.1`/`T9.2`) show *how much*; tracing shows *which request did what*.
This task adds a **distributed trace context** — a `trace_id` shared across a
request's work and a per-request `span_id` — propagated with the **W3C
`traceparent`** header and stamped onto every structured log line, so a single
import → normalize → insight → forecast flow is followable end to end (and across
service hops).

Consistent with the codebase's dependency-light philosophy (the `T9.1` metrics
registry, `HashingEmbedder`, etc.), this ships a **dependency-free** trace layer;
the OpenTelemetry SDK + a collector are documented as the production adapter.

## 2. Scope

- **In scope:**
  - A trace context: request-scoped `trace_id` (32 hex) and `span_id` (16 hex) in
    `ContextVar`s, with getters (beside the existing `correlation_id`).
  - W3C `traceparent` parse/format (`00-<trace>-<span>-<flags>`): reuse an inbound
    header's trace id, else generate; always assign a fresh span id; echo
    `traceparent` on the response.
  - A `span(name)` context manager that records name + duration into a **bounded,
    in-process ring buffer** (introspection/tests) under the current trace.
  - JSON logs carry `trace_id` and `span_id` (extending `T0.8`).
  - `TracingMiddleware` establishing/clearing the context per request.
- **Out of scope (later):**
  - OpenTelemetry SDK/exporter + collector; cross-process span export; sampling
    strategies; DB/HTTP client auto-instrumentation; baggage.

## 3. User stories & acceptance criteria

- As an **operator**, I follow one request across logs and hops.
  - **AC1:** A request with **no** `traceparent` gets a generated `trace_id` +
    `span_id`; the response carries a valid `traceparent` echoing them.
  - **AC2:** A request **with** a valid inbound `traceparent` **reuses** its
    `trace_id` (continuing the trace) and assigns a **new** `span_id`; a malformed
    header is ignored (treated as absent).
  - **AC3:** Log lines emitted during the request include the same `trace_id`/`span_id`
    (JSON formatter); outside any request they are `null`.
  - **AC4:** `span("work")` records a span (name, non-negative duration, current
    trace id) into the buffer; the buffer is bounded (old spans drop).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Context: `get_trace_id()`, `get_span_id()`, `set_trace_context(trace_id, span_id) -> token`, `reset_trace_context(token)` in `core/context.py` (alongside correlation id). Ids are lowercase hex; `new_trace_id()` (16 bytes), `new_span_id()` (8 bytes). |
| FR-2 | Functional | `parse_traceparent(header) -> (trace_id, span_id) | None` (validates `version=00`, 32-hex trace ≠ all-zero, 16-hex parent ≠ all-zero); `format_traceparent(trace_id, span_id, sampled=True) -> str`. |
| FR-3 | Functional | `TracingMiddleware`: from inbound `traceparent` reuse the trace id (new span id) else generate both; bind context for the request; set the response `traceparent`; reset in `finally`. |
| FR-4 | Functional | `span(name)` context manager: capture start/end (monotonic), append `Span{name, trace_id, span_id, duration_seconds}` to a bounded deque (`maxlen`); expose `recent_spans()` and `clear_spans()` (tests/introspection). No I/O. |
| FR-5 | Functional | `JsonFormatter` adds `trace_id`/`span_id` (from context; `null` when unset). |
| NFR-1 | Privacy | Trace/span ids are random, non-identifying; no user data enters ids, headers or the span buffer (span `name` is developer-supplied and must not carry PII — documented). |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration**. |
| NFR-3 | Testability | traceparent parse/format round-trip + rejection of malformed; middleware generate vs. continue; logs carry ids; span recorded + buffer bound. |

## 5. API & event contracts

```
Request  traceparent: 00-<32hex trace>-<16hex parent>-01   (optional, inbound)
Response traceparent: 00-<trace>-<span>-01                 (always)
Log line { ..., "correlation_id": "...", "trace_id": "...", "span_id": "..." }
```

- **No business API, no events, no persistence.**

## 6. Data model & migration strategy

- **No tables, no migration.** New `src/mylife/core/tracing.py` (ids, traceparent,
  `span`, buffer, `TracingMiddleware`); extend `src/mylife/core/context.py` and
  `src/mylife/core/logging.py`; wire `TracingMiddleware` in `main.py` (so the trace
  context is set before request handling and logging).

## 7. Privacy, consent, access-control & retention

- Ids are random and hold no user data; the span buffer is in-process, bounded and
  never persisted or logged as data. `traceparent` is safe to expose (no PII).

## 8. Test plan

- **traceparent (AC1/AC2/FR-2):** generate when absent; continue trace id + new span
  on valid inbound; malformed → treated as absent; format/parse round-trip.
- **Logging (AC3):** capture a log record inside a bound context → carries the ids;
  outside → `null`.
- **Span (AC4):** `span("x")` appends one span with the current trace id and
  duration ≥ 0; exceeding `maxlen` drops the oldest.
- **Middleware:** response has a valid `traceparent`; context reset after the request.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** correlation-id middleware/logging.
- **Open decisions (resolved):**
  - *Dependency-free now.* → W3C-compatible ids + propagation; OTel SDK/collector is
    the documented production swap, mirroring the metrics approach.
  - *In-process span buffer.* → bounded ring buffer for tests/introspection, not a
    real exporter (which is future work).
  - *Don't touch the immutable event envelope.* → tracing lives in the request/log
    plane; the envelope keeps its existing `correlation_id`.
- **Risks:**
  - *No cross-process export yet* — spans stay in-process; the traceparent still
    propagates the trace across hops, so an OTel exporter can be added later without
    changing call sites.
- **Future work:** OTel SDK + collector, span export, sampling, auto-instrumentation,
  Grafana/Tempo dashboards.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no dependency/migration.
- [ ] Requests carry/echo `traceparent`; logs include trace/span ids; `span()` records
      into a bounded buffer; backlog + spec status updated.
