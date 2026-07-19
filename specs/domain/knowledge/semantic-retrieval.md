# Spec: Knowledge — Semantic retrieval (`T6.3`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T6.3` — [issue #36](https://github.com/EFACODE/MyLife/issues/36)
- **Bounded context:** Knowledge
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T6.2` (extracted text), `T6.1` (documents), `T2.2` (auth)

## 1. Purpose & business context

Make a user's documents **searchable by meaning**: index the extracted text
(`T6.2`) as vectors and answer similarity queries. Indexing emits `MemoryIndexed`
(referencing the source document text as evidence); search returns the most
relevant documents with a **score**. This is the retrieval layer the assistant
(`T7`) will ground answers on.

Following the platform's ports discipline (as with `BlobStore` and the text
extractors), embeddings and the vector index are **ports**: a dependency-free,
deterministic adapter ships for dev/test, and pgvector + a real embedding model
are documented **production adapters** that drop in without changing callers.

## 2. Scope

- **In scope:**
  - An `Embedder` port (`embed(text) -> vector`, fixed dimension) + a
    `HashingEmbedder` (deterministic bag-of-words hashing, L2-normalized, stdlib
    only).
  - A `memory_index` store (one memory per document text) with the vector; search
    computes **cosine similarity** over the user's memories.
  - A `MemoryIndexed` event (references the document; vector/text not in payload).
  - `RetrievalService`: `index_document` (embed the extracted text, upsert the
    memory, emit the event) and `search(user_id, query, *, limit)`.
  - Authenticated endpoints: `POST /documents/{id}/index`,
    `GET /memory/search?q=…&limit=…`.
- **Out of scope (later):**
  - pgvector adapter + real embedding model (optional deps); chunking long
    documents; hybrid/keyword search; re-ranking; cross-domain memory
    (non-document events).

## 3. User stories & acceptance criteria

- As a **user**, I search my documents by meaning.
  - **AC1:** `POST /documents/{id}/index` (authenticated, my document that has
    extracted text) embeds the text, stores a memory and emits `MemoryIndexed`;
    a foreign/unknown document → `404`; a document without extracted text → `409`.
  - **AC2:** `GET /memory/search?q=…` returns my indexed documents ranked by
    cosine similarity to the query (descending `score`), each with `document_id`,
    `score` and a text `preview`; `limit` bounds results (default 5).
  - **AC3:** Re-indexing a document **updates** its memory (one memory per
    document) and emits a new event.
- As the **platform**, retrieval is scoped and traceable.
  - **AC4:** Search returns only my memories; endpoints require auth (`401`).
    `MemoryIndexed` references the document (evidence) and records the embedder +
    dimension.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `Embedder` protocol: `name: str`, `dimension: int`, `embed(text: str) -> list[float]`. `HashingEmbedder(dimension=256)`: tokenize (lowercased alphanumeric runs), hash each token (stable, `hashlib`) into `[0, dimension)`, accumulate, **L2-normalize** (zero vector for empty text); `name = "hashing-v1"`. |
| FR-2 | Functional | Table `memory_index`: `memory_id` (UUID PK), `user_id` (UUID, indexed), `document_id` (UUID, unique per document), `embedder` (str), `dimension` (int), `vector` (JSON list[float]), `indexed_at` (UTC). |
| FR-3 | Functional | Event `knowledge.memory_indexed` (`schema_version = 1`), payload `{memory_id, document_id, embedder, dimension}` — not the vector/text; appended + published (commit-before-publish). |
| FR-4 | Functional | `RetrievalService.index_document(user_id, document_id, *, now, correlation_id)`: require the user's document text (`DocumentTextRow`; else a "not extracted" error), embed it, **upsert** the `memory_index` row, append + publish `MemoryIndexed`, return the memory metadata. |
| FR-5 | Functional | `RetrievalService.search(user_id, query, *, limit=5)`: embed the query, load the user's memories, score each by **cosine similarity** (dot product of L2-normalized vectors), return the top `limit` as `SearchHit{document_id, score, preview}` (preview = first N chars of the document text), descending; ties broken deterministically. |
| FR-6 | Functional | Endpoints use `get_current_user`; `POST …/index` → 200 / `404` / `409`; `GET /memory/search` → `[SearchHit]`. Erasure (`T2.5`) includes `memory_index`. |
| NFR-1 | Typing/Deps | Passes `mypy --strict`; **no new runtime dependency** (hashing embedder + in-DB cosine; pgvector/model are future optional adapters). Vectors stored as JSON so it works on SQLite and Postgres. |
| NFR-2 | Migration | One Alembic revision creates `memory_index`; `alembic check` clean. |
| NFR-3 | Testability | Index (memory + event), re-index updates one memory, search ranks by similarity (a query overlapping one doc ranks it first), scoping/auth, `404`/`409`. |

## 5. API & event contracts

```
POST /documents/{id}/index          -> 200 Memory        (404 foreign / 409 no text)
GET  /memory/search?q=…&limit=5     -> [ SearchHit ]

Memory   = { memory_id, document_id, embedder, dimension, indexed_at }
SearchHit = { document_id, score, preview }
```

- **Event produced:** `MemoryIndexed` (Knowledge context), referencing the document.

## 6. Data model & migration strategy

- `MemoryRow` on `Base` (table `memory_index`) storing the vector as **JSON**
  (portable across SQLite/Postgres); cosine similarity is computed in Python over
  the user's rows (brute force). The **pgvector** adapter (an indexed `vector`
  column + ANN search) is the documented production scale path behind the same
  `RetrievalService`/index port. New Alembic revision `0015_memory_index`;
  `env.py` imports the model. Proposed layout:
  `src/mylife/knowledge/retrieval.py` (embedder + service + `MemoryIndexed`),
  routes in `src/mylife/api/knowledge.py`.

## 7. Privacy, consent, access-control & retention

- Memories are sensitive derived data: authenticated, user-scoped; search only
  ever scans the caller's rows; query text and vectors are never logged. Erasure
  (`T2.5`) removes `memory_index` alongside `document_texts`, `documents` and blobs.

## 8. Test plan

- **Index (AC1/FR-4):** a document with text → memory row + `MemoryIndexed` with
  embedder/dimension; no text → error/`409`.
- **Search ranking (AC2/FR-5):** index two documents; a query overlapping one
  ranks it first with a higher score; `limit` respected; preview present.
- **Re-index (AC3):** second index updates the single memory + emits a new event.
- **Scoping/auth (AC4):** another user's memories never returned; endpoints `401`.
- **Erasure/migration:** `memory_index` removed on erase; `alembic check` clean.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T6.2` text, `T6.1` docs, auth.
- **Open decisions (resolved):**
  - *Embeddings as a port.* → deterministic `HashingEmbedder` ships; real models
    (sentence-transformers/API) are future optional adapters.
  - *Vector store.* → JSON column + in-Python cosine now (portable, dependency-
    free); **pgvector** is the documented production adapter.
  - *Granularity.* → one memory per document text for now; chunking is future work.
  - *Vector/text not in the event.* → `MemoryIndexed` carries a reference +
    embedder metadata (evidence), like the other knowledge events.
- **Risks:**
  - *Hashing embedding is lexical, not semantic* — adequate to prove the pipeline
    and tests; real semantics arrive with a model adapter (noted).
  - *Brute-force search is O(memories)* — fine at small scale; pgvector/ANN later.
- **Future work:** pgvector adapter, real embedding model, chunking, hybrid
  search, indexing non-document memories, assistant grounding (`T7`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check`
      clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec
      status updated; erasure includes `memory_index`.
- [ ] Embeddings + vector index behind ports; no new runtime dependency; retrieval
      user-scoped and evidence-linked.
