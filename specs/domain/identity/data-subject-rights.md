# Spec: Data-subject rights — export + deletion (`T2.5`)

> Spec-Driven Development artifact.

- **Status:** Approved — implemented (`src/mylife/identity/data_subject.py`, `src/mylife/api/data_subject.py`, tests in `tests/test_data_subject.py` + `tests/test_data_subject_api.py`)
- **Backlog task:** `T2.5` — [issue #13](https://github.com/EFACODE/MyLife/issues/13)
- **Bounded context:** Identity (cross-cutting)
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** all prior identity/timeline tables (`T1.x`, `T2.1`–`T2.4`, `T3.x`)

## 1. Purpose & business context

LGPD/GDPR give users the right to **access** (export) and **erase** their data.
This task adds both, over the authenticated user: a complete export bundle and a
hard erasure across every store. Erasure is the **sanctioned path that overrides
append-only immutability** — the only way facts leave the system.

## 2. Scope

- **In scope:** `DataSubjectService.export`/`erase`; authenticated
  `GET /me/export` and `DELETE /me`.
- **Out of scope:** async/large export jobs, partial/selective erasure,
  soft-delete/retention windows, legal-hold, crypto-shredding (a hard delete is
  used now).

## 3. Acceptance criteria

- **AC1:** `GET /me/export` returns the user's identity, consents, audit,
  events, raw records, entities and relationships.
- **AC2:** `DELETE /me` removes all of that user's rows across every table and
  reports per-table counts; another user's data is untouched.
- **AC3:** After deletion the account no longer exists (a token for it resolves
  to `401`).
- **AC4:** Both endpoints require authentication and act only on the
  authenticated user.

## 4. Requirements

| ID | Requirement |
| -- | ----------- |
| FR-1 | `DataSubjectService(session).export(user_id) -> ExportBundle` gathering `user`, `consents`, `audit`, `events`, `raw_records`, `entities`, `relationships`. |
| FR-2 | `erase(user_id) -> ErasureResult{deleted: {table: count}}` hard-deletes the user's rows from `audit_log`, `relationships`, `entities`, `consents`, `raw_records`, `events`, `credentials`, `users`. |
| FR-3 | `GET /me/export` (authenticated) returns the bundle; `DELETE /me` (authenticated) erases and returns the counts. |
| FR-4 | Erasure is transactional (one commit). |
| NFR | `mypy --strict`; no migration (operates on existing tables); privacy — the export is returned only to the authenticated owner. |

## 5. Data model & migration

No new tables, no migration. `DataSubjectService` in
`src/mylife/identity/data_subject.py`; endpoints in
`src/mylife/api/data_subject.py`.

## 6. Privacy & security

- Export is the user's own data, returned only to them (auth required).
- Erasure is irreversible and is the **only** sanctioned way to remove otherwise
  append-only events/raw records; it is authenticated and self-service.
- A production system would also record an erasure audit entry in a separate,
  retained log; here erasure removes the user's own audit rows (documented).

## 7. Test plan

Export gathers seeded data (event/consent/audit); erase removes everything for
the user and leaves another user intact; endpoints require auth; post-delete the
token resolves to 401.

## 8. Open decisions

- **Hard delete** now (simple, complete); crypto-shredding/soft-delete are future
  work. Erasure overrides append-only by design (the documented exception).
