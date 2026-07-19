# My Life — Technical Backlog (`índice de tarefas`)

> The **PR-by-PR construction plan** for My Life. Each row below is one small,
> spec-traceable pull request. Work top to bottom: the order encodes real
> dependencies, and every PR leaves `main` green and shippable.

This backlog is the single source of truth referenced by the
[`README`](./README.md). It turns the product brief
(*My Life — AI-native Personal Operating System*) into a sequence of reviewable
increments so progress is legible one PR at a time.

---

## How to read this backlog

**The product in one paragraph.** My Life is a privacy-first, event-sourced
*digital twin*. Every external signal enters through a **connector**, is
normalized into an **immutable Life Event**, linked to entities and
relationships, and turned into **evidence-led** insights. The architecture is a
**modular monolith** with DDD bounded contexts (Identity, Timeline, Health,
Finance, Goals, Knowledge, Assistant), built with **Spec-Driven Development**.

**Task ID scheme — `T<group>.<n>`.** The group is a thematic workstream, not a
calendar phase; groups are delivered roughly in numeric order but a later group
may start before an earlier one finishes when there is no dependency.

| Group | Workstream |
| ----- | ---------- |
| `T0`  | Foundation & governance (repo, tooling, CI, docs, migrations, workers) |
| `T1`  | Event kernel (envelope, store, bus, provenance, corrections) |
| `T2`  | Identity, consent & audit |
| `T3`  | Timeline domain + connector framework + daily briefing |
| `T4`  | Health & Finance domains |
| `T5`  | Goals domain |
| `T6`  | Knowledge layer |
| `T7`  | Assistant (evidence-led AI) — *epic, detailed later* |
| `T8`  | Forecast & scenarios |
| `T9`  | Platform: observability, web, mobile, IaC — *epics, detailed later* |

**Roadmap phases** (from the brief) map onto the groups like this:

| Phase | Outcome | Groups |
| ----- | ------- | ------ |
| 0 — Foundation | A safe engineering platform | `T0`, `T2` (identity/consent/audit) |
| 1 — Personal timeline | One reliable daily value loop | `T1`, `T3` |
| 2 — Health + finance | Cross-domain understanding | `T4`, `T5` |
| 3 — Knowledge layer | Searchable personal context | `T6` |
| 4 — Assistant | Evidence-led conversations | `T7` |
| 5 — Forecast + scenarios | Transparent decision support | `T8` |

**Spec-Driven Development.** A task marked **Spec: Yes** must have an approved
specification in [`specs/`](./specs/) *before* implementation, using
`specs/TEMPLATE.md` (created in **T0.5**). A spec covers: purpose & scope, user
stories & acceptance criteria, functional/non-functional requirements with IDs,
API & event contracts, data model & migrations, privacy/consent/access/retention,
test plan, and open decisions/risks.

**Definition of Done** (applies to every PR):

- [ ] Spec approved (when required) and implementation is traceable to it.
- [ ] Tests pass — unit + integration + contract as applicable.
- [ ] `ruff` lint + format, `mypy` strict, and security implications addressed.
- [ ] Docs / ADRs / this backlog updated; the PR title carries its `T<group>.<n>` ID.
- [ ] No unsupported AI behavior; conventional-commit history; change stays focused.

**Non-negotiable invariants** (enforced from `T1` onward):

- Every event carries `id`, `occurred_at` (UTC), `recorded_at`, `schema_version`,
  `source`, `correlation_id`, `user_id`.
- **Raw**, **normalized** and **derived** data live in separate stores; the
  external system stays authoritative for raw data.
- History is immutable — **corrections create new events**, never mutations.
- AI claims are traceable to evidence and always represent uncertainty.

**Legend:** ✅ done · 📝 spec in review · 🔜 next · ⬜ planned · 🧭 epic (broken down when its phase begins).

---

## Phase 0 — Foundation · *governance before data volume*

Groups `T0` (platform) and `T2` (identity, consent, audit — the governance the
brief places in Phase 0).

### `T0` — Foundation & governance

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T0.1** | ✅ | Bootstrap repo & tooling | No | FastAPI shell, `ruff`/`mypy`/`pytest`/`pre-commit`, health endpoint. |
| **T0.2** | ✅ | Local env via Docker Compose | No | Postgres + Redis with healthchecks; `.env.example`. |
| **T0.3** | ✅ | Minimal CI | No | GitHub Actions: lint, format-check, types, tests. |
| **T0.4** | ✅ | `CLAUDE.md` operating contract | No | Root behavioral contract for coding agents (brief §10): mission, non-negotiables, delivery checklist, working sequence. Stays short and stable. |
| **T0.5** | ✅ | SDD scaffolding | No | `specs/TEMPLATE.md` (required-spec sections), `docs/` layout, `docs/adr/TEMPLATE.md`, `docs/glossary.md` stub. Wires the SDD process. |
| **T0.6** | ✅ | ADR-0001 architecture baseline + context map | ADR | Records modular monolith, the 7 bounded contexts, event-sourcing, and the raw/normalized/derived split → `docs/adr/0001-architecture-baseline.md`, `docs/context-map.md`. |
| **T0.7** | ✅ | Postgres + Alembic migrations | No | Add `alembic`; env wiring; initial empty migration; migration-drift check in CI; default runtime DB → Postgres. |
| **T0.8** | ✅ | Correlation-id middleware + structured logging | Light | Request-scoped context propagating `correlation_id` (feeds the envelope) and JSON structured logs. |
| **T0.9** | ✅ | Worker scaffolding (Celery + Redis broker) | No | Async job-runner shell for connectors/ingestion — wiring + a no-op task + test; no business jobs yet. |

### `T2` — Identity, consent & audit

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T2.1** | ✅ | Identity context: User/Household + `UserRegistered` | **Yes** | Domain models, `UserRegistered` event, register/read API. Foundation for `user_id` on every event. `specs/domain/identity/user-registration.md`. |
| **T2.2** | ✅ | Authentication (OAuth2/JWT, OIDC-ready) | Yes | Login, session protection, password hashing, least-privilege FastAPI dependencies. `specs/domain/identity/authentication.md`. |
| **T2.3** | ✅ | Consent model + enforcement | **Yes** | `ConsentGranted`/`ConsentRevoked` events, granular per-integration consent, an enforcement dependency connectors must pass. `specs/domain/identity/consent.md`. |
| **T2.4** | ✅ | Audit log (append-only) | **Yes** | Record data access, connector actions, consent changes and the evidence behind AI recommendations. `specs/domain/identity/audit-log.md`. |
| **T2.5** | ✅ | Data-subject rights: export + deletion | **Yes** | LGPD/GDPR export and deletion pathways with source visibility and revocation. `specs/domain/identity/data-subject-rights.md`. |

---

## Phase 1 — Personal timeline · *one reliable daily value loop*

Groups `T1` (event kernel) and `T3` (timeline domain, connectors, briefing).
This phase delivers the **MVP value loop**: capture → understand → briefing.

### `T1` — Event kernel

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T1.1** | ✅ | Life Event envelope | **Yes** | Typed Pydantic envelope enforcing the invariants above; `specs/domain/timeline/event-envelope.md`. The canonical shape every domain event extends. |
| **T1.2** | ✅ | Append-only event store | Yes | `events` table + repository with append + read-by-stream; **no update/delete** at the repo layer; migration. `specs/domain/timeline/event-store.md`. |
| **T1.3** | ✅ | Event bus (Redis) + in-process dispatcher | Yes | Publish `LifeEventRecorded`; subscribers drive projections. Redis broker from `T0.2`/`T0.9`. `specs/domain/timeline/event-bus.md`. |
| **T1.4** | ✅ | Raw ingestion store + provenance link | Yes | Separate `raw_records` table; normalized events reference `raw_record_id` + `source`. Keeps the external system authoritative. `specs/domain/timeline/raw-store.md`. |
| **T1.5** | ✅ | Event correction (`EventCorrected`) | Yes | Corrections are new events that reference the corrected one; history never mutates. `specs/domain/timeline/event-correction.md`. |

### `T3` — Timeline domain, connectors & briefing

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T3.1** | ✅ | Timeline query API | **Yes** | Filter Life Events by user/time/type/source, paginated, provenance included; `specs/domain/timeline/timeline-api.md`. |
| **T3.2** | ✅ | Manual event capture API | Yes | Users record Life Events by hand → `LifeEventRecorded`. Proves the loop with zero connectors. `specs/domain/timeline/manual-capture.md`. |
| **T3.3** | ✅ | Entities & relationships projection | Yes | Governed entity registry + relations derived from events — the knowledge-graph seed (a projection, not a data substitute). `specs/domain/timeline/entity-projection.md`. |
| **T3.4** | ✅ | Connector framework & contract | **Yes** | Ports/adapters + idempotent sync job (via `T0.9` worker): pull → raw store → normalized events. The reusable ingestion spine. `specs/domain/timeline/connector-framework.md`. |
| **T3.5** | ✅ | First connector (Calendar / ICS-CSV import) | Yes | One concrete connector proving the framework end-to-end into the timeline. `specs/domain/timeline/calendar-connector.md`. |
| **T3.6** | ✅ | Daily briefing v1 (rule-based, evidence-linked) | **Yes** | Aggregate recent events into a briefing where **every line links to its source events**; emits `BriefingDelivered`. Seeds the evidence contract. `specs/domain/assistant/daily-briefing.md`. |

---

## Phase 2 — Health + finance · *cross-domain understanding*

Groups `T4` (Health & Finance) and `T5` (Goals). Introduces the first
domain-specific events and the cross-domain correlation that is the product's
signature narrative.

### `T4` — Health & Finance

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T4.1** | ✅ | Finance context: `TransactionImported` / `ExpenseCreated` | **Yes** | Accounts + transactions models + authenticated API; first finance domain events (money = integer minor units). `specs/domain/finance/expense-tracking.md`. |
| **T4.2** | ✅ | Finance connector (bank CSV import) | Yes | Bank CSV import via the `T3.4` framework → `TransactionImported`; first consent-gated (`"bank"`), HTTP-exposed connector (`POST /finance/connectors/bank/import`). `specs/domain/finance/bank-connector.md`. |
| **T4.3** | ✅ | Net-worth / cash-flow (`PositionValued`) | Yes | `PositionValued` valuation event + read-time balances, net worth (per currency) and cash flow from finance events; authenticated endpoints. `specs/domain/finance/net-worth.md`. |
| **T4.4** | ✅ | Health context: `SleepRecorded` / `WorkoutCompleted` | **Yes** | Sleep/workout events + `HealthService` + authenticated `/health/*` endpoints; integer units, events-not-a-table. `specs/domain/health/workout-tracking.md`. |
| **T4.5** | ✅ | Health connector (wearable / Apple Health export) | Yes | Health CSV import via the `T3.4` framework → `SleepRecorded`/`WorkoutCompleted`; consent-gated (`"health"`), `POST /health/connectors/import`. `specs/domain/health/health-connector.md`. |
| **T4.6** | ✅ | Cross-domain briefing v2 | **Yes** | Correlate sleep, training, calendar load and spend (with spend baseline + combined short-sleep/busy-day insight) — the brief's example — still fully evidence-linked, rule-based, same `/briefing` route. `specs/domain/assistant/cross-domain-briefing.md`. |

### `T5` — Goals

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T5.1** | ✅ | Goals context: `GoalCreated` / `GoalMilestoneReached` | **Yes** | Goals registry + milestone events + authenticated `/goals` endpoints; migration 0012; erasure includes `goals`. `specs/domain/goals/goal-tracking.md`. |
| **T5.2** | ✅ | Goal-progress projection | Yes | Read-time `GoalProgressService` deriving progress from finance/health events by metric (net worth / workout minutes+distance / spend; milestone fallback), evidence-linked; `/goals/progress` endpoints. `specs/domain/goals/goal-progress.md`. |
| **T5.3** | ✅ | Goals in the briefing | Yes | Per-goal progress lines + at-risk (overdue) insight in the cross-domain briefing, evidence-linked. `specs/domain/goals/goals-in-briefing.md`. |

---

## Phase 3 — Knowledge layer · *searchable personal context*

### `T6` — Knowledge

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T6.1** | ✅ | Knowledge context: `DocumentIngested` + object-storage upload | **Yes** | `BlobStore` port (filesystem adapter) for document bytes + `documents` registry + `DocumentIngested`; authenticated `/documents` upload/list/download; migration 0013; erasure removes rows + blobs. `specs/domain/knowledge/document-ingest.md`. |
| **T6.2** | ✅ | OCR + text-extraction worker | Yes | Pluggable `TextExtractor` registry (plain-text; OCR/PDF adapters later) → `document_texts` derived store + `DocumentTextExtracted`; `ExtractionService`, Celery task, `POST /documents/{id}/extract` + `GET …/text`; migration 0014; erasure includes `document_texts`. `specs/domain/knowledge/text-extraction.md`. |
| **T6.3** | ✅ | Semantic retrieval (`MemoryIndexed`, retrieval API) | Yes | `Embedder` port (dependency-free `HashingEmbedder`; pgvector/model as production adapters) + `memory_index` (JSON vectors + cosine) + `MemoryIndexed`; `RetrievalService`, `POST /documents/{id}/index` + `GET /memory/search`; migration 0015; erasure includes `memory_index`. `specs/domain/knowledge/semantic-retrieval.md`. |
| **T6.4** | ✅ | Knowledge-graph consolidation | Yes | Cross-domain extractor (finance/health/goals/knowledge) + user-scoped `KnowledgeGraphService.consolidate` reusing the T3.3 projection; `/knowledge-graph/*` (entities/relationships/neighbors); no migration. `specs/domain/knowledge/knowledge-graph.md`. |

---

## Phase 5 — Forecast + scenarios · *transparent decision support*

Group `T8`. Turns the digital twin from *understanding the past* into *reasoning
about the future* — **without false precision**. Every projection is a structured
`ForecastGenerated` that **names its assumptions** the same way an insight cites
its evidence: a forecast with no stated assumptions is refused. Forecasts are
**rule-based / no-LLM** (moving-average / trend extrapolation over the user's own
events), carry explicit uncertainty (confidence intervals that widen with the
horizon), and are re-usable behind a scenario simulator and an outcome/calibration
loop. This makes the brief's Phase 5 promise — *transparent decision support* —
concrete and auditable.

### `T8` — Forecast + scenarios

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T8.1** | ✅ | Forecast contract + assumptions registry: `ForecastGenerated` | **Yes** | Typed `Forecast` (metric, horizon, projected points with lower/upper bounds, **required named `Assumption`s**, method/version, evidence event ids) + `ForecastService` refusing an assumption-free or foreign-evidence forecast + `forecasts` store + authenticated `/forecasts` API; migration 0017; erasure includes `forecasts`. Rule-based. `specs/domain/forecast/forecast-contract.md`. |
| **T8.2** | ✅ | Forecasting models (cash-flow / goal-completion) | Yes | Governed rule-based `Forecaster`s projecting from finance/goals events → `Forecast` via the contract (cash-flow moving-average over the horizon; goal-completion date from the progress trend), each naming its assumptions + citing evidence; `POST /forecasts/run`. No LLM/migration. `specs/domain/forecast/forecasting-models.md`. |
| **T8.3** | ✅ | "What-if" scenario simulation API | Yes | Apply user-supplied **assumption overrides** to a base forecast → a simulated `Forecast` that is transparent about which assumptions changed and **widens** uncertainty (no false precision); `POST /forecasts/{id}/simulate`. No LLM/migration. `specs/domain/forecast/scenario-simulation.md`. |
| **T8.4** | ✅ | Feedback / outcome loops | Yes | Record the **actual outcome** against a past forecast → `ForecastOutcomeRecorded` (evidence-linked) + read-time accuracy/calibration (error vs. stated interval); `POST /forecasts/{id}/outcome`, `GET /forecasts/calibration`. Answers *did the decision improve the outcome?* `specs/domain/forecast/outcome-loops.md`. |

---

## Platform track · *epic, broken into PRs when the phase begins*

These are intentionally coarse now (per the backend/MVP focus) and will be
decomposed into `T<group>.<n>` rows following the same rules when work reaches
them.

## Phase 4 — Assistant · *evidence-led conversations*

Group `T7`. The AI-native layer: every claim is a structured, **evidence-linked**
`InsightGenerated` with explicit confidence, limits and a safe next step — the
brief's non-negotiable made concrete. Grounded strictly on the user's own data
(retrieval `T6.3`, graph `T6.4`, timeline), with an evaluation harness enforcing
the safety rules. Early increments are **rule-based / no-LLM** — they build the
contract, storage, grounding and evaluation so a model can later slot in behind
the same guarantees.

### `T7` — Assistant (evidence-led AI)

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T7.1** | ✅ | AI evidence contract: `InsightGenerated` | **Yes** | Typed `Insight` (claim, rationale, **required** user-owned evidence, confidence 0–1, limitations, next safe action, generator) + `InsightService` refusing evidence-free/foreign-evidence claims + `insights` store + `/insights` API (evidence resolved on read); migration 0016; erasure. `specs/domain/assistant/insight-contract.md`. |
| **T7.2** | ✅ | Retrieval-grounded query API (least-privilege) | **Yes** | Read-only `Tool`s (timeline keyword + document memory) surface user-owned evidence; `AssistantQueryService.answer` grounds → `InsightGenerated` (calibrated confidence) or **refuses** (no fabrication); `POST /assistant/query`. No LLM/migration. `specs/domain/assistant/grounded-query.md`. |
| **T7.3** | ✅ | Alerts & weekly insights | Yes | Governed `Rule`s (overspend / at-risk goal / short-sleep) → evidence-linked `InsightGenerated` via `InsightService`; `AlertsService.run`, `POST /assistant/alerts/run`, Celery `run_weekly_insights`. No LLM/migration. `specs/domain/assistant/alerts.md`. |
| **T7.4** | ✅ | AI-safety evaluation harness | **Yes** | Pure `SafetyEvaluator` (evidence present, uncertainty represented, no unsupported medical/financial conclusions, grounding/refusal consistency) + an eval battery driving the real assistant as a CI gate. No dependency/migration. `specs/domain/assistant/safety-harness.md`. |

### `T9` — 🧭 Platform
- **Observability** — OpenTelemetry traces, Prometheus metrics, Grafana
  dashboards (import → insight traceability).
- **Web** — React / TypeScript / Tailwind / shadcn-ui timeline & briefing
  surfaces.
- **Mobile** — SwiftUI iPhone/iPad app.
- **Infrastructure** — Terraform IaC + deployment pipeline & environments.

---

## Progress snapshot

| Phase | Group(s) | Done | Total (detailed) |
| ----- | -------- | ---- | ---------------- |
| 0 | `T0`, `T2` | 14 | 14 |
| 1 | `T1`, `T3` | 11 | 11 |
| 2 | `T4`, `T5` | 9 | 9 |
| 3 | `T6` | 4 | 4 |
| 4 | `T7` | 4 | 4 |
| 5 | `T8` | 4 | 4 |
| platform | `T9` | — | epic |

_Update the **Status** column and this snapshot as each PR merges._
