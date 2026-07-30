# Spec: Audit log (`T2.4`)

> Spec-Driven Development artifact.

- **Status:** Approved — implemented (`src/mylife/identity/audit.py`, `src/mylife/api/audit.py`, migration `0010`, tests in `tests/test_audit.py` + `tests/test_audit_api.py`)
- **Backlog task:** `T2.4` — [issue #12](https://github.com/EFACODE/MyLife/issues/12)
- **Bounded context:** Identity
- **Author / date:** Claude Code / 2026-07-18
- **Depends on:** `T1.x` (event bus), `T2.1`/`T2.2` (identity/auth)

## 1. Purpose & business context

Trust requires an **append-only audit trail** of security-relevant activity:
data access, connector actions, consent changes and the evidence behind AI
recommendations. Most of these are already **domain events**, so the audit log
is built primarily as a **subscriber over the event stream** (every published
event becomes an audit entry), plus an explicit `record` for non-event actions
(e.g. login). Users can read their own trail.

## 2. Scope

- **In scope:** an append-only `audit_log` table; `AuditService.record` +
  `list_for_subject`; an `AuditSubscriber` that records one entry per published
  event; an authenticated `GET /audit` (current user's entries); login recorded
  explicitly.
- **Out of scope:** admin/cross-user audit views, tamper-proofing/signing,
  retention policies, exhaustive per-read access logging (the subscriber + login
  demonstrate the mechanism).

## 3. Acceptance criteria

- **AC1:** Publishing a domain event records an audit entry with `action =
  event_type`, `subject_user_id = event.user_id`, `resource = event_id`,
  `correlation_id`, and the event's `occurred_at`.
- **AC2:** `AuditService.record(...)` appends an entry for a non-event action
  (e.g. `auth.login`).
- **AC3:** `GET /audit` (authenticated) returns the current user's entries,
  newest first; `401` without a token.
- **AC4:** The audit log is append-only (no update/delete surface) and stores no
  payload/secret content — only ids, action and correlation.

## 4. Requirements

| ID | Requirement |
| -- | ----------- |
| FR-1 | Table `audit_log`: `audit_id` (PK), `action` (str), `actor_user_id` (UUID?, who), `subject_user_id` (UUID?, indexed, whose data), `resource` (str?), `correlation_id` (str?), `occurred_at` (UTC), `recorded_at` (UTC). |
| FR-2 | `AuditService(session).record(action, *, now, actor_user_id=None, subject_user_id=None, resource=None, correlation_id=None, occurred_at=None) -> AuditEntry`; `list_for_subject(user_id, *, limit) -> list[AuditEntry]` (newest first). No update/delete. |
| FR-3 | `AuditSubscriber(session_factory).register(bus)` records one entry per published event (own committed session), action = `event_type`. |
| FR-4 | `GET /audit` (authenticated) returns the current user's entries. |
| FR-5 | Login (`POST /auth/login`) records an `auth.login` entry for the user on success. |
| NFR | `mypy --strict`, migration + `alembic check`, no sensitive content logged/stored. |

## 5. Data model & migration

`AuditLogRow` on `Base`; new revision `0010_audit_log`. `env.py` imports the
model. Append-only at the repository layer.

## 6. Privacy

Audit stores only ids/action/correlation — never payloads or secrets. Entries
are a user's own security trail (subject-scoped for reads). Erasure (`T2.5`)
removes a user's audit entries along with their data.

## 7. Test plan

Subscriber records per event; `record` appends; `list_for_subject` newest-first
and scoped; append-only (no update/delete); endpoint auth + returns entries;
login writes an entry.

## 8. Open decisions

- **Audit-as-projection**: primarily a bus subscriber (covers events); explicit
  `record` for non-event actions. Live app-registration of the subscriber is
  deferred like other subscribers; the endpoint + login use `AuditService`
  directly so the feature is demonstrable now.
