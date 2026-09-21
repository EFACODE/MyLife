# Spec: Notifications context — Outbound delivery (`T4.8`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T4.8`
- **Bounded context:** Notifications (new)
- **Author / date:** Claude Code / 2026-09-21
- **Depends on:** `T1.x` (event kernel), `T2.2` (auth)

## 1. Purpose & business context

Introduces **Notifications** as its own bounded context: generic
outbound-delivery infrastructure (a channel protocol, SMTP-email and
WhatsApp-Cloud-API adapters, a per-user preferences registry, and an
audit-trailed send service) that any domain can call when it needs to reach a
user outside the app. Finance's bill due-date scan (`T4.8`, see
`bill-alerts.md`) is the first caller; it is deliberately kept out of
`mylife.finance` so future callers (e.g. a goal-at-risk nudge) don't have to
depend on Finance.

## 2. Scope

- **In scope:**
  - `NotificationChannel` protocol + two stdlib-only adapters:
    `SmtpEmailChannel` (SMTP), `WhatsAppCloudApiChannel` (Meta WhatsApp Cloud
    API, `POST .../messages`). Both accept an injectable transport so tests
    never touch the network.
  - `NotificationRequested` / `NotificationSent` / `NotificationDeliveryFailed`
    events — an immutable audit trail of every send attempt.
  - `NotificationService.send`: request → attempt → record outcome
    (commit-before-publish for each event).
  - A `notification_preferences` registry (per user: `email_enabled`,
    `whatsapp_enabled`, `whatsapp_phone`) + `NotificationPreferenceService`.
  - Authenticated endpoints: `GET/PUT /notifications/preferences`.
  - `build_channels_from_settings`: wires whichever channel(s) a deployment
    has credentials for (unset credentials → that channel is simply absent,
    not an error).
- **Out of scope (later):**
  - Templating beyond plain subject/body strings; other providers
    (transactional email APIs, Twilio); retry/backoff (a failed send is
    recorded, not retried); rate limiting; digest/batching of notifications.

## 3. User stories & acceptance criteria

- As a **user**, I control how I'm reminded.
  - **AC1:** `GET /notifications/preferences` returns my preferences
    (defaults: email on, WhatsApp off, no phone number, if never set).
  - **AC2:** `PUT /notifications/preferences` creates/updates them.
- As the **platform**, every send attempt is auditable and never silently
  swallowed.
  - **AC3:** `NotificationService.send` always emits `NotificationRequested`
    first, then exactly one of `NotificationSent`
    (`provider_message_id` if the provider returned one) or
    `NotificationDeliveryFailed` (`reason`) — including when the requested
    channel has no configured implementation.
  - **AC4:** A channel adapter raises `NotificationChannelError` on any
    transport failure; it never lets a raw provider exception escape.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `notification_preferences`: `user_id` (UUID PK), `email_enabled` (bool), `whatsapp_enabled` (bool), `whatsapp_phone?` (string), `updated_at`. |
| FR-2 | Functional | Events `notifications.requested`, `notifications.sent`, `notifications.delivery_failed` (`schema_version = 1`), appended (`T1.2`) and published (`T1.3`), commit-before-publish. `NotificationRequestedPayload.evidence` carries the immutable event id(s) backing the claim (e.g. the bill's `BillRegistered`), so a reminder is traceable like an insight. |
| FR-3 | Functional | `NotificationChannel.send(recipient, subject, body) -> str \| None`, raising `NotificationChannelError` on failure. `SmtpEmailChannel` (stdlib `smtplib`/`email.message.EmailMessage`) and `WhatsAppCloudApiChannel` (stdlib `urllib.request`, Meta Cloud API `POST /{phone_number_id}/messages`) implement it; both take an injectable transport (`smtp_cls`/`opener`) for testing. |
| FR-4 | Functional | `build_channels_from_settings(settings)` returns a `{"email": ..., "whatsapp": ...}` map containing only the channels whose settings are non-empty. |
| FR-5 | Functional | `NotificationPreferenceService.get`/`.set`, user-scoped; `get` returns sane defaults (not `404`) when a user has never set preferences. |
| NFR-1 | Typing | Passes `mypy --strict`. |
| NFR-2 | Migration | One Alembic revision creates `notification_preferences`; `alembic check` clean. |
| NFR-3 | Testability | Channel adapters tested against fake transports (no real network calls in the suite); service tested for the requested→sent and requested→failed paths, including "no channel configured". |
| NFR-4 | Security | SMTP/WhatsApp credentials come only from settings (`MYLIFE_SMTP_*`, `MYLIFE_WHATSAPP_*`); never hardcoded, never logged. Message bodies are event payloads (never logged). |

## 5. API & event contracts

```
GET /notifications/preferences                                    -> 200 NotificationPreference
PUT /notifications/preferences  { "email_enabled": true, "whatsapp_enabled": true,
                                   "whatsapp_phone": "+5511999999999" }  -> 200 NotificationPreference

NotificationPreference = { email_enabled, whatsapp_enabled, whatsapp_phone, updated_at }
```

- **Events produced:** `NotificationRequested`, `NotificationSent`,
  `NotificationDeliveryFailed` (Notifications context).

## 6. Data model & migration strategy

- `NotificationPreferenceRow` on `Base` (table `notification_preferences`) —
  current-state, like `AccountRow`/`BillRow`; not event-sourced (there is no
  fact worth preserving about a superseded preference). Layout:
  `src/mylife/notifications/` (`models.py`, `channels.py`, `preferences.py`,
  `service.py`).
- New Alembic revision `0020_notification_preferences`; `migrations/env.py`
  imports `mylife.notifications.models`.

## 7. Privacy, consent, access-control & retention

- All endpoints are authenticated and user-scoped. No new connector consent
  scope: sending is triggered by the user's own data (their bills), not a
  third-party pull.
- Erasure (`T2.5`) is extended: `DataSubjectService.export`/`.erase` now
  include `notification_preferences`. `NotificationRequested`/`Sent`/
  `DeliveryFailed` events are covered by the existing generic `events` erasure
  (they are Life Events like any other).

## 8. Test plan

- **Channels (AC4/FR-3):** `SmtpEmailChannel`/`WhatsAppCloudApiChannel`
  against fake transports — success returns the expected shape, a transport
  error raises `NotificationChannelError`.
- **Preferences (AC1/AC2/FR-5):** defaults when unset; set → get round-trip;
  endpoints authenticated.
- **Service (AC3/FR-2):** requested→sent records both events with the
  request/sent linkage; requested→failed (channel raises, or channel
  missing) records `NotificationDeliveryFailed` with a reason; the service
  never raises past `send`.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), auth (`T2.2`); erasure (`T2.5`)
  updated. Consumed by Finance's bill alerts (`T4.8`, see `bill-alerts.md`).
- **Open decisions (resolved for this spec):**
  - *Providers.* → SMTP for email, Meta WhatsApp Cloud API for WhatsApp
    (confirmed with the product owner), both via stdlib HTTP/SMTP clients —
    no new third-party dependency.
  - *Retry.* → None in v1; a failed send is recorded and surfaced (via the
    event stream / a future notifications page), not retried automatically.
- **Risks:** WhatsApp Cloud API requires the recipient to have opted in via
  Meta's rules (a 24-hour session window or a pre-approved template) that
  this v1 does not enforce — a `whatsapp` send outside that window will
  simply fail and be recorded as `NotificationDeliveryFailed`; approved
  message templates are future work.
- **Future work:** retry/backoff, templated messages, a notifications
  history page in the console, additional providers.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check` clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec status updated; erasure includes `notification_preferences`.
- [ ] Credentials only from settings, never logged; every send attempt auditable.
