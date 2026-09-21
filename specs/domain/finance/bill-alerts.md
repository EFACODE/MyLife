# Spec: Finance context — Bill due-date alerts (`T4.8`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.8`
- **Bounded context:** Finance (scan) + Notifications (delivery, see
  `specs/domain/notifications/outbound-delivery.md`)
- **Author / date:** Claude Code / 2026-09-21
- **Depends on:** `T4.7` (recurring bills), Notifications (`outbound-delivery.md`)

## 1. Purpose & business context

Closes the loop on `T4.7`: a user should be reminded, by email and/or
WhatsApp, when a bill is due soon or overdue — not just see it in a report
they have to remember to check. Also introduces the project's first
**periodic** background job (Celery beat), since a daily scan is what makes
reminders automatic rather than something the user has to trigger.

## 2. Scope

- **In scope:**
  - `BillAlertScanner`: finds a user's unpaid bill occurrences that are
    due-soon (in 3, 1 or 0 days) or overdue, reusing `BillsReportService`
    (`T4.7`) rather than a new derived store.
  - `BillAlertsService`: for each alert, renders a message and sends it
    through the user's enabled channels via `NotificationService`
    (Notifications context).
  - `POST /finance/bills/alerts/run` — authenticated, on-demand trigger
    (mirrors `POST /assistant/alerts/run`, `T7.3`).
  - Celery beat task `mylife.send_bill_reminders`, scheduled daily
    (08:00 UTC), scanning every user with an active bill.
- **Out of scope (later):**
  - Configurable reminder cadence/timing per bill or per user (fixed at
    3/1/0 days-before and daily-while-overdue for v1).
  - Digesting multiple due bills into one message (each occurrence sends its
    own notification).

## 3. User stories & acceptance criteria

- As a **user**, I get reminded before a bill is due and while it's overdue.
  - **AC1:** A bill due in exactly 3, 1 or 0 days (and still unpaid) produces
    one reminder per enabled channel.
  - **AC2:** An overdue, unpaid bill produces a reminder every day the scan
    runs, until it's paid.
  - **AC3:** A paid occurrence, or one outside the due-soon/overdue window,
    produces no reminder.
- As a **user**, I choose how I'm reminded (Notifications context, `T4.8`
  `outbound-delivery.md`) — email by default; WhatsApp once I set a number
  and enable it.
- As the **platform**, reminders run automatically, and I can also trigger
  them myself.
  - **AC4:** `POST /finance/bills/alerts/run` runs the scan for the
    authenticated user synchronously and returns the delivery outcomes.
  - **AC5:** The Celery beat schedule runs the same scan daily for every user
    with at least one active bill, without needing to enumerate users
    outside Finance's own registry.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `BillAlertScanner.scan(user_id, now)`: calls `BillsReportService.list_occurrences` with `paid=False` over `[now - 90d, now + 3d]`; flags an occurrence `"overdue"` if `occurrence.overdue`, else `"due_soon"` if `(due_at.date() - now.date()).days` is in `{3, 1, 0}`; otherwise skipped. Each alert's `evidence` is the bill's `BillRegistered` event id (looked up by `bill_id`), when found. |
| FR-2 | Functional | `BillAlertsService.run(user_id, now, correlation_id)`: for each alert, renders a subject/body and calls `NotificationService.send` once per enabled channel (email via the user's account email; WhatsApp via the preference's `whatsapp_phone`, only if `whatsapp_enabled` and a number is set). Returns the list of `NotificationOutcome`. No alerts or no such user → `[]`. |
| FR-3 | Functional | `mylife.send_bill_reminders` (no args): queries `SELECT DISTINCT user_id FROM bills WHERE active`, runs `BillAlertsService.run` per user with a fresh correlation id each, using channels built from settings (`build_channels_from_settings`). Scheduled via `celery_app.conf.beat_schedule` (`crontab(hour=8, minute=0)`, daily). |
| FR-4 | Functional | `POST /finance/bills/alerts/run` — authenticated; builds channels from settings and runs `BillAlertsService` for the caller only. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Testability | Scanner tested for the 3/1/0-day and overdue windows and the paid/out-of-window exclusions; service tested with a fake channel (no real network/SMTP/WhatsApp calls). |

## 5. API & event contracts

```
POST /finance/bills/alerts/run   -> 201 [NotificationOutcome]
```

- No new event types — see `outbound-delivery.md` for
  `NotificationRequested`/`Sent`/`DeliveryFailed`, and `recurring-bills.md`
  for `BillRegistered`/`BillPaid`/`BillCancelled` (evidence source).

## 6. Data model & migration strategy

- No new tables. `src/mylife/finance/bill_alerts.py` (`BillAlertScanner`,
  `BillAlertsService`) sits in Finance and depends on
  `mylife.notifications` + `mylife.identity` (to resolve the user's email) —
  the same cross-domain shape as `assistant/alerts.py`.
- `celery_app.py` gains its first `beat_schedule` entry;
  `docker-compose.prod.yml`/deployment adding a `celery beat` process is
  tracked as follow-up infra work (the app-level schedule is defined either
  way; running `celery -A mylife.workers.celery_app beat` is a deployment
  concern, not a code dependency of this spec).

## 7. Privacy, consent, access-control & retention

- No new consent scope: a bill is the user's own data, not a third-party
  pull. The scan and every send are user-scoped and read only what the
  acting/scanned user owns.
- Message bodies (payee, amounts) are event payloads on the Notifications
  side — never logged (see `outbound-delivery.md` NFR-4).

## 8. Test plan

- **Scanner windows (AC1/AC2/AC3/FR-1):** exactly-3/1/0-days-out unpaid →
  `due_soon`; overdue unpaid → `overdue`, repeatedly across scans; paid or
  out-of-window → excluded; evidence resolves to the bill's registration
  event.
- **Service (FR-2):** a fake channel records calls; email always attempted
  when enabled; WhatsApp only when enabled **and** a phone is set; no alerts
  → no channel calls.
- **Endpoint (AC4/FR-4):** authenticated; returns outcomes for the caller
  only.
- **Task (FR-3):** exercised at the unit level (the query + per-user loop),
  not a real Celery worker run.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T4.7` (bills, `BillsReportService`), Notifications
  (`T4.8` `outbound-delivery.md`), `T2.2` (auth).
- **Open decisions (resolved for this spec):**
  - *Cadence.* → Fixed reminder points (3/1/0 days before, daily while
    overdue) rather than user-configurable — matches the vision's "alertas
    de vencimento" without over-building a scheduling UI in v1.
  - *No dedup store.* → Because reminders are derived from the deterministic
    due-date window (not a persisted "already sent" flag), re-running the
    scan on the same day is idempotent in effect (same alerts recomputed)
    but **not** idempotent in delivery — calling `POST
    /finance/bills/alerts/run` twice on the same day sends the reminder
    twice. Acceptable for v1 (mirrors `POST /assistant/alerts/run`, which
    has the same property); flagged as future work if it proves noisy.
- **Risks:** the fixed 90-day lookback bounds the overdue scan — a bill
  unpaid for longer than 90 days stops generating reminders. Acceptable for
  v1; revisit if real usage needs it.
- **Future work:** configurable cadence, a "already reminded today" guard,
  digest notifications, a notifications history page.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green.
- [ ] Backlog + spec status updated.
- [ ] No secrets logged; every reminder traceable to its bill's evidence.
