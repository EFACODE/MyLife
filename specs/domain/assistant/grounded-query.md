# Spec: Assistant — Retrieval-grounded query API (`T7.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** In review
- **Backlog task:** `T7.2` — [issue #39](https://github.com/EFACODE/MyLife/issues/39)
- **Bounded context:** Assistant
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T7.1` (insight contract), `T6.3` (retrieval), `T3.1`
  (timeline query), `T2.2` (auth)

## 1. Purpose & business context

Answer a user's question **only from their own data**, and only with a claim that
**cites the events grounding it** — or **refuse** (a calibrated fallback) when the
evidence is insufficient. Grounding runs through a small set of **least-privilege
tools**: read-only, user-scoped retrievers (timeline keyword match, document
memory search) that surface candidate **evidence events**. A grounded answer is
recorded as an `InsightGenerated` (`T7.1`), so it inherits the evidence contract
end-to-end. This increment is **rule-based / no-LLM**: it builds the tool
harness, the grounding, and the honest-refusal behaviour, into which a model
later slots — given exactly these tools and forced to cite their evidence.

## 2. Scope

- **In scope:**
  - A `Tool` port: read-only, user-scoped retrievers returning scored
    `EvidenceCandidate`s (an event id + relevance + snippet). Two adapters:
    `TimelineKeywordTool` (keyword overlap over the user's events) and
    `DocumentMemoryTool` (`T6.3` search → the documents' `DocumentIngested`
    events).
  - `AssistantQueryService.answer(user_id, question)`: run the tools, merge/rank
    candidates, and either **record a grounded `InsightGenerated`** (evidence =
    the top events) or **refuse** with a calibrated fallback when evidence is thin.
  - An authenticated endpoint `POST /assistant/query`.
- **Out of scope (later):**
  - LLM answer generation (the tools + contract stay; a model plugs in behind
    them); alerts/weekly insights (`T7.3`); the safety-eval harness (`T7.4`);
    multi-turn conversation, tool-use planning, re-ranking.

## 3. User stories & acceptance criteria

- As a **user**, I ask a question and get an answer grounded in my own data.
  - **AC1:** `POST /assistant/query` with a question that matches my data returns
    a **grounded** answer: `grounded = true`, a recorded `Insight` whose
    `evidence` are the matched events, the tools used, and an evidence count.
  - **AC2:** A grounded answer's evidence are **only my own events** (via `T7.1`),
    and the answer text **does not assert anything beyond what the evidence
    shows** (it reports/points to evidence, not domain conclusions).
  - **AC3:** When no tool finds sufficient evidence, the API **refuses**:
    `grounded = false`, a calibrated fallback message, **no `Insight` recorded**,
    no fabricated claim.
- As the **platform**, grounding is least-privilege and scoped.
  - **AC4:** Tools are read-only and operate only on the caller's data; the
    endpoint requires auth (`401`). Confidence is **calibrated** to evidence
    strength (more/stronger matches → higher, capped at 1.0).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `EvidenceCandidate{event_id, score (0–1), tool, snippet}`. `Tool` protocol: `name: str`, `gather(session, user_id, question) -> list[EvidenceCandidate]` (read-only, user-scoped). |
| FR-2 | Functional | `TimelineKeywordTool`: tokenize the question; score each of the user's recent events by the overlap between question tokens and the event's `event_type`/`source`/`category`/string payload values (Jaccard-ish, 0–1); keep positive-score matches; snippet = a short event descriptor. |
| FR-3 | Functional | `DocumentMemoryTool`: `RetrievalService.search(user_id, question)`; for each hit, use the document's `DocumentIngested` event as the evidence id; score = the hit's similarity; snippet = the document filename/preview. |
| FR-4 | Functional | `AssistantQueryService.answer(user_id, question, *, now, correlation_id)`: run all tools, **merge candidates by event id** (max score), rank descending, take the top `k` (default 5). If none, or the best score `< MIN_SCORE`, **refuse**. |
| FR-5 | Functional | On grounding: `confidence = min(1.0, sum(top scores) / k)` (calibrated); record an `InsightGenerated` via `InsightService` with `evidence = top event ids`, a templated `claim` that only reports what was found, `rationale` naming the tools/matches, `limitations` (rule-based match over your own data; not professional advice), `next_safe_action` (review the cited events), `generator = "grounded-query-v1"`. Return the grounded `Answer`. |
| FR-6 | Functional | On refusal: return `Answer{grounded=false, answer=<calibrated fallback>, insight=None, tools_used, evidence_count=0}`; **no insight recorded**, nothing fabricated. |
| FR-7 | Functional | Endpoint `POST /assistant/query` (`get_current_user`) → `Answer`; user-scoped. |
| NFR-1 | Security/Safety | Tools are **read-only** and user-scoped (least privilege); every grounded claim is an `Insight` (evidence enforced by `T7.1`); the answer never asserts unsupported domain conclusions; query text not logged. |
| NFR-2 | Typing/Deps | Passes `mypy --strict`; **no new dependency, no migration** (reuses `insights`, retrieval, timeline). |
| NFR-3 | Testability | Grounded answer (evidence = matched events, insight recorded), refusal on no match (no insight), confidence calibration/monotonicity, tool least-privilege scoping, auth. |

## 5. API & event contracts

```
POST /assistant/query   { "question": "what did I spend on food?" }   -> 200 Answer

Answer = { grounded: bool, answer: str, insight: Insight | null,
           tools_used: [str], evidence_count: int }
```

- **Event produced:** `InsightGenerated` (`T7.1`) **only** when grounded.

## 6. Data model & migration strategy

- **No new tables, no migration.** Grounded answers persist through the `T7.1`
  `insights` store; tools read existing stores. Proposed layout:
  `src/mylife/assistant/query.py` (tools + `AssistantQueryService` + `Answer`),
  route in `src/mylife/api/assistant.py`.

## 7. Privacy, consent, access-control & retention

- Authenticated and user-scoped; every tool reads only the caller's data. Query
  text and evidence snippets are never logged. Grounded answers are `insights`
  (removed by erasure, `T2.5`); refusals persist nothing.

## 8. Test plan

- **Grounded (AC1/AC2/FR-5):** seed matching events (e.g. a food expense) → query
  → `grounded=true`, an `Insight` recorded whose evidence are those events; the
  answer reports, not concludes.
- **Refusal (AC3/FR-6):** a query with no matching data → `grounded=false`, no
  insight recorded, fallback message.
- **Calibration (AC4/FR-5):** more/stronger matches yield ≥ confidence than fewer.
- **Least-privilege/scoping (NFR-1):** another user's data never grounds an answer.
- **Auth:** `POST /assistant/query` `401` without a token.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T7.1` insights, `T6.3` retrieval, `T3.1` timeline, auth.
- **Open decisions (resolved):**
  - *No LLM yet.* → deterministic tools + templated, evidence-only answer; a model
    slots in behind the same tools + the evidence contract later.
  - *Grounding = events.* → tools return **event ids** (timeline events, a
    document's `DocumentIngested`), so evidence satisfies `T7.1`.
  - *Refuse over guess.* → below `MIN_SCORE`/no candidates → a calibrated fallback,
    never a fabricated claim.
  - *Calibrated confidence.* → from aggregate match score, capped at 1.0.
- **Risks:**
  - *Keyword/lexical matching is shallow* — enough to prove grounding + refusal;
    semantic matching improves with a model/better embedder (noted).
  - *Answer templates are intentionally modest* — they report evidence, not
    conclusions; richer synthesis is the LLM's job under `T7.4` guardrails.
- **Future work:** LLM generation behind the tools, tool planning/iteration,
  re-ranking, more tools (finance/health/goals summaries), multi-turn.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests pass; `ruff`, `mypy --strict`, `pytest` green; no migration.
- [ ] Endpoint authenticated/in OpenAPI; backlog + spec status updated.
- [ ] Grounded answers cite user-owned evidence (via `T7.1`); insufficient
      evidence refuses; tools least-privilege; nothing fabricated.
