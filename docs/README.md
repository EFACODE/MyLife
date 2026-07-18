# Documentation

Architecture and engineering documentation for My Life. Product and feature
specifications live in [`specs/`](../specs/); this tree holds the durable
"how and why" of the system.

## Layout

```
docs/
  README.md          # this file
  context-map.md     # DDD bounded contexts and their relationships (T0.6)
  glossary.md        # shared ubiquitous language
  adr/               # Architecture Decision Records
    TEMPLATE.md      # copy this for each new ADR
    0001-architecture-baseline.md
```

## Architecture Decision Records (ADRs)

Significant, hard-to-reverse decisions are captured as numbered ADRs. Create a
new one by copying [`adr/TEMPLATE.md`](./adr/TEMPLATE.md) to the next number
(`NNNN-short-title.md`). An ADR is immutable once **Accepted**; to change a
decision, add a new ADR that supersedes it and link both ways.
