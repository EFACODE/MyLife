# Spec: <feature name> (`T<group>.<n>`)

> Spec-Driven Development: this document is written and **approved before**
> implementation. Copy this template to the feature's path under `specs/`
> (see [`specs/README.md`](./README.md)) and fill every section. Delete guidance
> in angle brackets as you go.

- **Status:** Draft | In review | Approved | Implemented
- **Backlog task:** `T<group>.<n>` — <link to issue>
- **Bounded context:** Identity | Timeline | Health | Finance | Goals | Knowledge | Assistant | Platform
- **Author / date:**

## 1. Purpose & business context

<Why this exists and the user value. Link to the product brief where relevant.>

## 2. Scope

- **In scope:** <what this feature covers>
- **Out of scope:** <explicitly excluded, to prevent scope creep>

## 3. User stories & acceptance criteria

- As a <user>, I want <capability>, so that <outcome>.
  - **AC1:** <measurable, testable criterion>
  - **AC2:** …

## 4. Requirements

Give each a stable ID so tests and code can trace to it.

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | <…> |
| NFR-1 | Non-functional | <performance, availability, limits> |

## 5. API & event contracts

- **Events produced/consumed:** <name, envelope fields, payload schema, schema_version>
- **API endpoints:** <method, path, request/response models, error responses>

## 6. Data model & migration strategy

<Tables/entities, relationships, indexes. How the migration is applied and
rolled back. Which store: raw / normalized / derived.>

## 7. Privacy, consent, access-control & retention

<Consent required, least-privilege access, sensitive-data handling, retention &
deletion behavior. LGPD/GDPR considerations.>

## 8. Test plan

<Unit, integration, contract, regression, performance and — where AI is
involved — evaluation. Trace tests back to the requirement IDs above.>

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** <other tasks/specs>
- **Open decisions:** <questions needing an answer before/at implementation>
- **Risks:** <and mitigations>
- **Future improvements:** <deferred, not in this task>

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy`, `pytest` green.
- [ ] API/docs/ADRs and the backlog status updated.
- [ ] Privacy/consent/security implications addressed; no unsupported AI behavior.
