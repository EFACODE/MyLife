# ADR-0001: Architecture baseline

- **Status:** Accepted
- **Date:** 2026-07-18
- **Deciders:** Founding engineering

## Context

My Life unifies sensitive data across many life domains (health, finance,
calendar, documents, goals) into an explainable digital twin. We need an
architecture that keeps early development fast while preventing the cross-domain
coupling that would make later decomposition painful — and that treats
immutability, provenance and evidence as first-class from day one.

## Decision

We will build a **modular monolith** organized into **DDD bounded contexts**,
integrated through **immutable events** and explicit contracts.

1. **Modular monolith first.** One deployable process with strong internal
   boundaries. Independent workers and connector jobs may scale separately as
   needs emerge; contexts can later be extracted into services without
   rewriting their contracts.
2. **Seven bounded contexts:** Identity, Timeline, Health, Finance, Goals,
   Knowledge, Assistant. Each owns its language, models, APIs, policies, events,
   tests and docs. Contexts integrate through stable events/contracts, never by
   reaching into each other's internals.
3. **Event-sourced core.** Historical facts are immutable Life Events carrying a
   standard envelope (`id`, `occurred_at` UTC, `recorded_at`, `schema_version`,
   `source`, `correlation_id`, `user_id`). Corrections create new events.
4. **Three separated stores:** **raw** (original external payloads, source stays
   authoritative), **normalized** (canonical Life Events), and **derived**
   (projections and insights, with evidence references). Derived data never
   overwrites facts.
5. **AI with least privilege.** The assistant retrieves curated context and
   returns structured claims that must cite evidence and represent uncertainty.
6. **API- and domain-first.** Business behavior lives in contexts and services;
   UI and other clients consume API/event contracts.

Stack (see the product brief): Python, FastAPI, Pydantic, SQLAlchemy, Alembic;
PostgreSQL, Redis, object storage, optional pgvector; a job runner (Celery) for
connectors and async computation.

## Consequences

- **Positive:** fast iteration in one codebase; clear seams for later extraction;
  immutability and provenance baked into the kernel; testable contracts.
- **Negative / trade-offs:** discipline required to respect boundaries inside a
  single process; event-sourcing adds modeling overhead versus CRUD.
- **Follow-ups:** the event kernel (`T1`), identity/consent/audit (`T2`) and the
  connector framework (`T3.4`) implement these decisions.

## Alternatives considered

- **Microservices from the start:** premature; high operational cost before the
  domains and contracts are proven.
- **CRUD over a shared schema:** loses immutability, provenance and the
  event-driven integration the product depends on.
