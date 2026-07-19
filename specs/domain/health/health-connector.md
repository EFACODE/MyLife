# Spec: Health connector — Wearable CSV import (`T4.5`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T4.5` — [issue #29](https://github.com/EFACODE/MyLife/issues/29)
- **Bounded context:** Health (ingestion)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T3.4` (connector framework), `T4.4` (health context),
  `T2.2` (auth), `T2.3` (consent enforcement)

## 1. Purpose & business context

Bring **wearable / Apple Health** data into the Health context through the
ingestion spine instead of by hand. A `HealthCsvConnector` implements the `T3.4`
`Connector` contract and maps each export row to a `SleepRecorded` or
`WorkoutCompleted` event (`T4.4`) — reusing the whole pipeline (pull → raw →
normalize → append → publish, idempotent, provenance-linked). Like the bank
connector (`T4.2`) it is **consent-gated** (`T2.3`) and HTTP-exposed, so a user
can upload a health export and see the sessions/workouts on their timeline and in
`GET /health/sleep` / `GET /health/workouts`. It completes the health data flow
feeding the cross-domain briefing (`T4.6`).

CSV (not the Apple Health XML) is chosen first, consistent with the calendar and
bank connectors: no new dependency, deterministic to test, still exercises the
contract. XML/HealthKit parsing can follow as another connector.

## 2. Scope

- **In scope:**
  - `HealthCsvConnector` (`source = "health"`) implementing the `T3.4` contract:
    parse CSV rows (a `kind` column selects sleep vs. workout) into `RawPayload`s
    and normalize each into a `SleepRecorded` / `WorkoutCompleted` (`T4.4`) linked
    to its raw record.
  - An authenticated, **consent-gated** import endpoint
    `POST /health/connectors/import` that runs
    `ConnectorRunner.sync(..., consent=...)` and returns the sync counts.
- **Out of scope (later):**
  - Apple Health **XML**/HealthKit, Google Fit, live device APIs (OAuth tokens).
  - Derived metrics/trends, HR zones, readiness scores, sleep stages.
  - The connector **registry** entry (a file-upload connector is built per
    request, as established in `T4.2`).

## 3. User stories & acceptance criteria

- As a **user**, I upload a health export CSV and its rows become sessions/workouts.
  - **AC1:** `POST /health/connectors/import` (authenticated) with CSV text
    creates one raw record and one `SleepRecorded`/`WorkoutCompleted` per row
    (correct kind, `source = "health"`, `raw_record_id` set) and returns the
    counts (`raw_ingested`, `events_created`, `skipped_duplicates`).
  - **AC2:** The imported rows appear in `GET /health/sleep` /
    `GET /health/workouts` (`T4.4`) and on the timeline (`T3.1`), newest first.
  - **AC3:** Re-importing the same CSV is idempotent (rows skipped, no
    duplicates) — inherited from `T3.4`.
- As the **platform**, I keep health ingestion consented, scoped and exact.
  - **AC4:** Import **fails closed** without consent for scope `"health"` →
    `403`; unauthenticated → `401`.
  - **AC5:** Measures are integer minutes/meters/kcal — never floats. A bad row
    (unknown `kind`, missing field, non-integer measure, or naive/malformed
    `occurred_at`) fails the batch (no partial ingest).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `HealthCsvConnector(csv_text: str, *, fetched_at: datetime)` with `source = "health"`, implementing the `T3.4` `Connector` protocol. |
| FR-2 | Functional | `fetch` parses `csv_text` (header row) via stdlib `csv`; each data row becomes a `RawPayload` whose `content` holds the row fields and whose `external_id` is the row's `external_id` (if present); `fetched_at` is the import time (UTC). |
| FR-3 | Functional | Columns: `kind` (`sleep`\|`workout`) and `occurred_at` (ISO-8601 **UTC**) required. Sleep: `duration_minutes` (int > 0), `quality?`. Workout: `activity`, `duration_minutes` (int > 0), `distance_meters?` (int ≥ 0), `energy_kcal?` (int ≥ 0). Optional `external_id`. |
| FR-4 | Functional | `normalize(raw)` yields a `SleepRecorded` (kind `sleep`) or `WorkoutCompleted` (kind `workout`) with `occurred_at` parsed to UTC, `source = "health"`, `raw_record_id = raw.raw_record_id`, and the `T4.4` payload. |
| FR-5 | Functional | Validation → `ValueError` (runner rolls back the batch, AC5): unknown `kind`; missing required field for the kind; a measure that is not a base-10 integer (or ≤ 0 / < 0 per `T4.4`); naive/unparseable `occurred_at`. |
| FR-6 | Functional | Endpoint `POST /health/connectors/import` (`get_current_user`): builds the connector, runs `ConnectorRunner.sync(connector, FetchContext(user_id, correlation_id), consent=ConsentService(...))`; a `ConsentRequiredError` → `403`; returns a `SyncResult` view. |
| NFR-1 | Security | Consent scope `"health"` enforced fail-closed; raw export text stored in `raw_records`, never logged; endpoint user-scoped. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; stdlib `csv`/`io` only — **no new dependency, no migration** (reuses `raw_records`/`events`). |
| NFR-3 | Testability | Connector tested via `ConnectorRunner` on SQLite (mixed sleep/workout import + provenance; idempotency; bad-row rollback) and endpoint tested (auth, consent `403`, happy path). |

## 5. API & event contracts

```
POST /health/connectors/import   (auth + consent "health")
  { "csv": "kind,occurred_at,duration_minutes,quality,activity,distance_meters,energy_kcal,external_id\n
            sleep,2026-07-19T00:30:00+00:00,465,good,,,,s-1\n
            workout,2026-07-19T07:00:00+00:00,42,,run,8000,520,w-1\n" }
  -> 201 { "source": "health", "raw_ingested": 2, "events_created": 2, "skipped_duplicates": 0 }
  401 (no token) · 403 (no "health" consent)
```

CSV contract (single header; per-row columns depend on `kind`):

```
kind,occurred_at,duration_minutes,quality,activity,distance_meters,energy_kcal,external_id
sleep,2026-07-19T00:30:00+00:00,465,good,,,,s-1
workout,2026-07-19T07:00:00+00:00,42,,run,8000,520,w-1
```

- **Events produced:** `SleepRecorded` / `WorkoutCompleted` (`source = "health"`),
  one per row, provenance-linked to its raw record.

## 6. Data model & migration strategy

- **No new tables, no migration.** Reuses `raw_records`/`events`. Proposed layout:
  `src/mylife/health/health_csv.py` (connector) and a new route in
  `src/mylife/api/health_tracking.py`.

## 7. Privacy, consent, access-control & retention

- Health is sensitive: the endpoint is authenticated and user-scoped, and
  ingestion is **consent-gated** on scope `"health"` (fail-closed via `T2.3`). Raw
  export text is persisted verbatim in `raw_records` and never logged; measures
  live only in event payloads. Erasure (`T2.5`) already removes a user's
  `raw_records` and `events`.

## 8. Test plan

- **Import (AC1/AC2/FR-4):** a mixed 2-row CSV (one sleep, one workout) → 2
  events of the right kinds, provenance set, visible via `GET /health/sleep` /
  `GET /health/workouts` and `T3.1`.
- **Idempotency (AC3):** re-import → all rows skipped, no new events.
- **Consent (AC4/FR-6):** without `"health"` consent → `403` and nothing
  ingested; after `POST /consents {scope:"health"}` → success.
- **Auth (AC4):** unauthenticated → `401`.
- **Bad row (AC5/FR-5):** unknown `kind` / missing field / non-integer measure /
  naive `occurred_at` → raises, batch rolls back (nothing persisted).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.4` framework, `T4.4` health context, `T2.2` auth, `T2.3`
  consent; stdlib only.
- **Open decisions (resolved for this spec):**
  - *Format.* → **CSV first** (no dependency, deterministic); Apple Health XML /
    device APIs later.
  - *One connector, `kind` column.* → a single connector handles both facts via a
    `kind` discriminator (one upload for a mixed export), rather than two.
  - *Consent.* → gated on scope **`"health"`**, fail-closed, through the runner's
    `consent=` gate.
  - *Registry.* → **not registered** (file-upload connector built per request, as
    with `T4.2`); registering *pull* connectors (device APIs) is future work.
- **Risks:**
  - *Wide, sparse CSV* (kind-specific columns left blank) — acceptable; a
    per-kind upload or JSON can follow.
  - *Large exports in one transaction* — acceptable for first import; batching is
    future work.
- **Future work:** Apple Health XML/HealthKit and device-API connectors, sleep
  stages, HR/zones, `T4.6` cross-domain briefing.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green (no migration;
      `alembic check` unaffected).
- [ ] Endpoint authenticated + consent-gated in OpenAPI; connector built
      per-request (registry deferred, as `T4.2`); backlog + spec status updated.
- [ ] End-to-end proven (CSV → sleep/workout events queryable, provenance-linked);
      measures integer; raw text not logged.
