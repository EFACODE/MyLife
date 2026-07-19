# Glossary — ubiquitous language

Shared terms used across specs, code and docs. Keep definitions precise; when a
bounded context refines a term, note the context.

| Term | Definition |
| ---- | ---------- |
| **Life Event** | An immutable, normalized fact about the user, carrying the standard envelope (`id`, `occurred_at`, `recorded_at`, `schema_version`, `source`, `correlation_id`, `user_id`) plus a typed payload. |
| **Envelope** | The standard metadata every Life Event carries, independent of its payload. |
| **Raw record** | The original external payload as received from a source, stored separately and never mutated. The source system stays authoritative. |
| **Normalized event** | A Life Event derived from one or more raw records into the canonical model. |
| **Derived insight** | An observation/recommendation computed from events; keeps evidence references, model/rule version, confidence and generation time. Never overwrites facts. |
| **Correction** | A new event that supersedes an earlier one; history is never mutated. |
| **Bounded context** | A domain boundary that owns its language, models, APIs, events, tests and docs (Identity, Timeline, Health, Finance, Goals, Knowledge, Assistant). |
| **Connector** | An adapter that ingests data from an external source into raw records and normalized events. |
| **Projection** | A read model (e.g. the entity/relationship graph) built by reacting to the event stream; not a substitute for transactional data. |
| **Evidence contract** | The structured explanation every AI claim must return: claim, why it matters, source evidence, confidence, limitations and next safe action. |
