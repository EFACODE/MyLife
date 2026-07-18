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
| `T8`  | Forecast & scenarios — *epic, detailed later* |
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
| **T2.1** | ⬜ | Identity context: User/Household + `UserRegistered` | **Yes** | Domain models, `UserRegistered` event, register/read API. Foundation for `user_id` on every event. |
| **T2.2** | ⬜ | Authentication (OAuth2/JWT, OIDC-ready) | Yes | Login, session protection, password hashing, least-privilege FastAPI dependencies. |
| **T2.3** | ⬜ | Consent model + enforcement | **Yes** | `ConsentGranted`/`ConsentRevoked` events, granular per-integration consent, an enforcement dependency connectors must pass. |
| **T2.4** | ⬜ | Audit log (append-only) | **Yes** | Record data access, connector actions, consent changes and the evidence behind AI recommendations. |
| **T2.5** | ⬜ | Data-subject rights: export + deletion | **Yes** | LGPD/GDPR export and deletion pathways with source visibility and revocation. |

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
| **T3.1** | 📝 | Timeline query API | **Yes** | Filter Life Events by user/time/type/source, paginated, provenance included; `specs/domain/timeline/timeline-api.md` — **in review, awaiting approval.** |
| **T3.2** | ⬜ | Manual event capture API | Yes | Users record Life Events by hand → `LifeEventRecorded`. Proves the loop with zero connectors. |
| **T3.3** | ⬜ | Entities & relationships projection | Yes | Governed entity registry + relations derived from events — the knowledge-graph seed (a projection, not a data substitute). |
| **T3.4** | ⬜ | Connector framework & contract | **Yes** | Ports/adapters + idempotent sync job (via `T0.9` worker): pull → raw store → normalized events. The reusable ingestion spine. |
| **T3.5** | ⬜ | First connector (Calendar / ICS-CSV import) | Yes | One concrete connector proving the framework end-to-end into the timeline. |
| **T3.6** | ⬜ | Daily briefing v1 (rule-based, evidence-linked) | **Yes** | Aggregate recent events into a briefing where **every line links to its source events**; emits `BriefingDelivered`. Seeds the evidence contract. |

---

## Phase 2 — Health + finance · *cross-domain understanding*

Groups `T4` (Health & Finance) and `T5` (Goals). Introduces the first
domain-specific events and the cross-domain correlation that is the product's
signature narrative.

### `T4` — Health & Finance

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T4.1** | ⬜ | Finance context: `TransactionImported` / `ExpenseCreated` | **Yes** | Accounts + transactions models + API; first finance domain events. Spec `specs/finance/expense-tracking.md`. |
| **T4.2** | ⬜ | Finance connector (bank CSV/OFX import) | Yes | Bank import via the `T3.4` framework → `TransactionImported`. |
| **T4.3** | ⬜ | Net-worth / cash-flow projection (`PositionValued`) | Yes | Balances, cash flow and net worth over time from finance events. |
| **T4.4** | ⬜ | Health context: `SleepRecorded` / `WorkoutCompleted` | **Yes** | Sleep/workout/metric models + API; first health domain events. Spec `specs/health/workout-tracking.md`. |
| **T4.5** | ⬜ | Health connector (wearable / Apple Health export) | Yes | Health import via the `T3.4` framework → `WorkoutCompleted`/`SleepRecorded`. |
| **T4.6** | ⬜ | Cross-domain briefing v2 | **Yes** | Correlate sleep, training, calendar load and spend — the brief's example — still fully evidence-linked. |

### `T5` — Goals

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T5.1** | ⬜ | Goals context: `GoalCreated` / `GoalMilestoneReached` | **Yes** | Outcomes, targets, plans + API. |
| **T5.2** | ⬜ | Goal-progress projection | Yes | Link finance/health events to goals to compute progress. |
| **T5.3** | ⬜ | Goals in the briefing | Yes | Surface goal progress and risks in the daily briefing. |

---

## Phase 3 — Knowledge layer · *searchable personal context*

### `T6` — Knowledge

| PR | Status | Title | Spec | Scope & acceptance |
| -- | ------ | ----- | ---- | ------------------ |
| **T6.1** | ⬜ | Knowledge context: `DocumentIngested` + object-storage upload | **Yes** | Upload with sensitive-document controls; raw docs to object storage; `DocumentIngested`. |
| **T6.2** | ⬜ | OCR + text-extraction worker | Yes | Async extraction of text from ingested documents. |
| **T6.3** | ⬜ | Semantic retrieval (pgvector) | Yes | Embeddings + `MemoryIndexed` + retrieval API for grounded context. |
| **T6.4** | ⬜ | Knowledge-graph projection consolidation | Yes | Consolidate entities + relations across all domains into the graph projection. |

---

## Phases 4–5 & platform tracks · *epics, broken into PRs when their phase begins*

These are intentionally coarse now (per the backend/MVP focus) and will be
decomposed into `T<group>.<n>` rows following the same rules when work reaches
them.

### `T7` — 🧭 Assistant *(Phase 4 — evidence-led conversations)*
- **AI evidence contract** — structured `InsightGenerated` claim: *claim, why it
  matters, source evidence, confidence, known limitations, next safe action*.
- **Retrieval-grounded query API** — least-privilege tools; curated context;
  structured claims requiring evidence.
- **Alerts & weekly insights** — governed rules combined with evaluated AI.
- **AI-safety evaluation harness** — no unsupported medical/financial
  conclusions; calibrated fallback when evidence is insufficient.

### `T8` — 🧭 Forecast + scenarios *(Phase 5 — transparent decision support)*
- **Forecasting models + assumptions registry** — every projection names its
  assumptions.
- **"What-if" scenario simulation API** — transparent assumptions, no false
  precision.
- **Feedback / outcome loops** — did the decision improve the outcome?

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
| 0 | `T0`, `T2` | 9 | 14 |
| 1 | `T1`, `T3` | 5 | 11 |
| 2 | `T4`, `T5` | 0 | 9 |
| 3 | `T6` | 0 | 4 |
| 4–5 + platform | `T7`–`T9` | — | epics |

_Update the **Status** column and this snapshot as each PR merges._
