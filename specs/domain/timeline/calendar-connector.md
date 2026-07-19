# Spec: First connector — Calendar CSV import (`T3.5`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved — implemented (`src/mylife/connectors/calendar_csv.py`, tests in `tests/test_calendar_connector.py`)
- **Backlog task:** `T3.5` — [issue #23](https://github.com/EFACODE/MyLife/issues/23)
- **Bounded context:** Timeline (ingestion)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T3.4` (connector framework), `T1.1`/`T1.2`/`T1.4`

## 1. Purpose & business context

The first **concrete connector**, proving the framework end-to-end: importing
calendar events from a **CSV** file into the timeline. It turns each row into a
raw record and a normalized `LifeEventRecorded`, so the whole pipeline (pull →
raw → normalize → append → publish, idempotent, provenance-linked) is exercised
with real data and no new dependencies.

CSV (not ICS) is chosen deliberately for the first connector: it needs no new
library, is deterministic to test, and still demonstrates the contract. ICS
support can follow as another connector.

## 2. Scope

- **In scope:**
  - `CalendarCsvConnector` implementing the `T3.4` `Connector` contract
    (`source = "calendar"`): parse CSV text into `RawPayload`s and normalize each
    into a `LifeEventRecorded` linked to its raw record.
  - Strict validation of the required columns and UTC timestamps.
- **Out of scope (later):**
  - ICS parsing; fetching from a live calendar API (OAuth/tokens).
  - An HTTP upload endpoint (the connector is invoked via `ConnectorRunner`;
    an upload/import route can come later).
  - Scheduling and the registry/worker path (this connector is invoked ad-hoc
    with the file content; registered pull-connectors come with `T4.x`).

## 3. User stories & acceptance criteria

- As a **user**, I want to import my calendar as CSV so those events appear on my
  timeline.
  - **AC1:** Running `ConnectorRunner.sync(CalendarCsvConnector(csv), context)`
    creates one raw record and one `LifeEventRecorded` per row, with
    `source = "calendar"`, the row's `title`/`category`/`occurred_at`, and
    `raw_record_id` set (provenance).
  - **AC2:** The imported events are returned by the timeline query API
    (`T3.1`).
  - **AC3:** Re-importing the same CSV is idempotent (no duplicate raw
    records/events) — inherited from `T3.4`.
- As the **platform**, I want bad input rejected clearly.
  - **AC4:** A row with a missing required field, or a naive/malformed
    `occurred_at`, fails the import (batch rolls back — no partial ingest).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `CalendarCsvConnector(csv_text: str, *, fetched_at: datetime)` with `source = "calendar"`. |
| FR-2 | Functional | `fetch` parses `csv_text` (header row) via the stdlib `csv` module; each data row becomes a `RawPayload` whose `content` holds the row's fields and whose `external_id` is the row's `external_id` (if present). `fetched_at` is the provided import time (UTC). |
| FR-3 | Functional | Required columns: `title`, `category`, `occurred_at` (ISO-8601 **UTC**). Optional: `external_id`, `description`. |
| FR-4 | Functional | `normalize(raw)` yields a `LifeEventRecorded` with `occurred_at` parsed to UTC, `source = "calendar"`, `raw_record_id = raw.raw_record_id`, and payload `{title, category, note = description or None}`. |
| FR-5 | Functional | A missing required field or a naive/unparseable `occurred_at` raises a `ValueError` (propagated by the runner → batch rollback, AC4). |
| FR-6 | Functional | No new third-party dependency (stdlib `csv`/`io` only); no migration. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Testability | Tested via `ConnectorRunner` on SQLite: import → events queryable + provenance; idempotent re-import; bad-row rollback; `external_id` preserved. |

## 5. API & event contracts

No HTTP API. CSV contract (header + rows):

```
external_id,title,category,occurred_at,description
evt-1,Standup,work,2026-07-18T09:00:00+00:00,Daily sync
evt-2,Gym,health,2026-07-18T18:00:00+00:00,
```

- **Event produced:** `LifeEventRecorded` (`source = "calendar"`), one per row,
  provenance-linked to its raw record.

Illustrative shape:

```python
class CalendarCsvConnector:            # implements T3.4 Connector
    source = "calendar"
    def __init__(self, csv_text: str, *, fetched_at: datetime) -> None: ...
    def fetch(self, context: FetchContext) -> Iterable[RawPayload]: ...
    def normalize(self, raw: StoredRawRecord) -> Iterable[LifeEvent[Any]]: ...
```

## 6. Data model & migration strategy

- **No new tables, no migration.** Reuses `raw_records`/`events`. Proposed
  location: `src/mylife/connectors/calendar_csv.py`.

## 7. Privacy, consent, access-control & retention

- The CSV holds personal calendar data; the raw text is stored verbatim in
  `raw_records` and never logged. Import remains subject to consent (`T2.3`) once
  it exists; for now the caller supplies the file explicitly.

## 8. Test plan

Integration tests on SQLite via `ConnectorRunner`:

- **Import (AC1/AC2/FR-4):** a 2-row CSV yields 2 events with the right
  title/category/occurred_at, `source = "calendar"`, provenance set, and
  queryable via `T3.1`; `description` maps to `note`.
- **Idempotency (AC3):** re-import → all rows skipped, no new events.
- **External id (FR-2):** the raw record carries the row's `external_id`.
- **Bad row (AC4/FR-5):** a missing field or naive `occurred_at` raises and the
  batch rolls back (nothing persisted).

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T3.4` framework; stdlib only.
- **Open decisions (resolved for this spec):**
  - *Format.* → **CSV first** (no dependency, deterministic); ICS later.
  - *Strictness.* → **Fail the batch on a bad row** (no partial import); a
    lenient/skip-bad-rows mode can be added later.
  - *Invocation.* → **Ad-hoc via `ConnectorRunner`** with the file content; an
    upload endpoint and registry/worker scheduling come later.
- **Risks:**
  - *Large CSVs in one transaction* — acceptable for first import; batching/
    streaming is future work.
  - *Timezone ambiguity* — mitigated by requiring explicit UTC offsets.
- **Future work:** ICS connector, upload endpoint, live calendar API connector,
  lenient parsing mode, consent gating (`T2.3`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Backlog + spec status updated.
- [ ] End-to-end proven (CSV → events queryable, provenance-linked); raw text not logged.
