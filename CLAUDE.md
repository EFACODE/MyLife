# My Life — CLAUDE.md

This file is a **stable behavioral contract** for coding agents (and humans)
working in this repository. It changes rarely. Evolving requirements live in
[`specs/`](./specs/), architecture decisions in [`docs/adr/`](./docs/adr/), and
detailed domain rules beside their owning bounded context.

## Mission

Build a privacy-first, AI-native Personal Operating System that creates an
**explainable digital twin** of the user. Favor long-term maintainability,
safety and evidence over speed.

## Non-negotiables

- **Read the applicable spec and architecture notes before changing code.** See
  [`docs/adr/0001-architecture-baseline.md`](./docs/adr/0001-architecture-baseline.md)
  and [`docs/context-map.md`](./docs/context-map.md).
- **Do not invent product requirements.** Surface ambiguity and propose options.
- **Preserve immutable history:** corrections create new events, never mutations.
- **Keep raw source data, normalized events and derived insights distinct.** The
  external system stays authoritative for raw data.
- **Keep business logic inside its bounded context;** UI and other contexts
  consume API/event contracts, never reach into internals.
- **Every AI claim must be traceable to evidence** and represent uncertainty.
- **Never hardcode secrets** or weaken authentication/authorization.

## Event & data invariants

Every Life Event carries: `id`, `occurred_at` (UTC), `recorded_at`,
`schema_version`, `source`, `correlation_id`, `user_id`. Derived observations
keep their evidence references, model/rule version, confidence and generation
time — they never overwrite facts.

## Delivery checklist

A change is complete only when its **spec** (when required), **tests**,
**documentation**, **linting**, **typing** and **security implications** are all
addressed. Use conventional commits, prefix the work with its backlog task ID
(`T<group>.<n>`, see [`myLife-indice-tarefas.md`](./myLife-indice-tarefas.md)),
and keep each change focused.

## Agent working sequence

1. Read the relevant specs, ADRs and domain contracts.
2. State assumptions, dependencies, risks and an implementation plan.
3. Add or update tests and contracts before/alongside implementation.
4. Implement the smallest coherent change, preserving domain boundaries.
5. Run the quality gates and summarize spec alignment, test evidence and open risks.

## Quality gates

```bash
ruff check .        # lint
ruff format --check .# formatting
mypy                # strict typing
pytest              # tests
```
