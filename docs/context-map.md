# Context map

The bounded contexts of My Life and how they relate. Integration is through
**events** (immutable Life Events on the shared kernel) and explicit API
contracts — never by reaching into another context's internals. See
[`docs/adr/0001-architecture-baseline.md`](./adr/0001-architecture-baseline.md).

## Contexts

| Context | Owns | Representative events |
| ------- | ---- | --------------------- |
| **Identity** | Users, households, consent, profiles | `UserRegistered`, `ConsentGranted` |
| **Timeline** | Canonical Life Events and provenance | `LifeEventRecorded`, `EventCorrected` |
| **Health** | Sleep, workouts, metrics, medical records | `SleepRecorded`, `WorkoutCompleted` |
| **Finance** | Accounts, transactions, positions, net worth | `TransactionImported`, `PositionValued` |
| **Goals** | Outcomes, targets, plans, progress | `GoalCreated`, `GoalMilestoneReached` |
| **Knowledge** | Documents, notes, semantic retrieval | `DocumentIngested`, `MemoryIndexed` |
| **Assistant** | Queries, explanations, interventions | `InsightGenerated`, `BriefingDelivered` |
| **Notifications** | Outbound delivery (email/WhatsApp), channel preferences | `NotificationRequested`, `NotificationSent` |

## Relationships

- **Timeline is the shared kernel.** Every domain publishes its facts as Life
  Events into the timeline; the timeline owns the envelope and provenance.
- **Identity is upstream of everything.** It supplies `user_id` and the consent
  decisions that gate connectors and data access (Customer/Supplier).
- **Health, Finance, Goals, Knowledge are peer domains.** They react to the
  event stream but do not depend on each other's internals; cross-domain views
  (e.g. the briefing) are built by the Assistant from published events.
- **Assistant is downstream.** It consumes projections and events, retrieves
  curated context with least privilege, and emits evidence-backed insights.
- **Connectors** feed raw records and normalized events into the timeline under
  Identity's consent rules; the external system stays authoritative for raw data.
- **Notifications is a downstream service, not an event-stream consumer.** It
  has no domain logic of its own — a peer domain (Finance's bill due-date
  scan is the first caller) decides *that* a user should be notified and
  calls `NotificationService` directly; Notifications owns *how* the message
  reaches the user (channel adapters, delivery preferences) and records
  every attempt as its own evidence-linked events.

```
                 Identity (consent, user_id)
                        │  gates
                        ▼
Connectors ──raw──▶ Timeline (kernel: Life Events) ◀── Health / Finance / Goals / Knowledge
                        │  event stream
                        ▼
                    Assistant ──▶ evidence-backed insights & briefings
```
