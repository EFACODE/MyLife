# Spec: Knowledge — OCR & text-extraction worker (`T6.2`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T6.2` — [issue #35](https://github.com/EFACODE/MyLife/issues/35)
- **Bounded context:** Knowledge
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T6.1` (documents + blob store), `T0.9` (Celery worker),
  `T1.x` (events), `T2.2` (auth)

## 1. Purpose & business context

Turn ingested documents into **searchable text**. An extraction step reads a
document's bytes from the blob store, extracts text via a content-type-selected
**strategy**, and stores the result as **derived data** — a `document_texts` row
plus a `DocumentTextExtracted` event that keeps its **evidence** (the source
document), the **method** and an **extractor version** (per the platform's
derived-observation rule). This is the input to semantic retrieval (`T6.3`).

Extraction is a **pluggable strategy registry**: a dependency-free plain-text
extractor ships now; PDF/image **OCR** adapters (which need optional engines like
pdfminer/tesseract) drop into the same registry later without touching callers.

## 2. Scope

- **In scope:**
  - A `TextExtractor` strategy port + a registry keyed by content type; a
    `PlainTextExtractor` for `text/*` (UTF-8 decode, `errors="replace"`).
  - A `document_texts` derived store (extracted text + method + char count) and a
    `DocumentTextExtracted` event (references the document; text is not in the
    event payload).
  - `ExtractionService.extract_document(user_id, document_id)`: load doc + blob,
    run the extractor, upsert the derived row, append + publish the event.
  - A Celery task `extract_document_text(user_id, document_id)` (async path, the
    `T3.4`/`sync_connector` pattern) and endpoints:
    `POST /documents/{id}/extract` (run now), `GET /documents/{id}/text`.
- **Out of scope (later):**
  - Concrete OCR/PDF engines (pdfminer/tesseract adapters + optional deps);
    language detection; layout/table extraction.
  - Embeddings / semantic retrieval (`T6.3`); auto-enqueue tuning/retries.

## 3. User stories & acceptance criteria

- As a **user**, my uploaded text document becomes readable/searchable text.
  - **AC1:** `POST /documents/{id}/extract` (authenticated, my document) reads the
    blob, extracts text and returns the extraction result (method, char count);
    a foreign/unknown document → `404`.
  - **AC2:** `GET /documents/{id}/text` returns the extracted text (404 if not my
    document or not yet extracted).
  - **AC3:** Extraction emits `DocumentTextExtracted` referencing the document
    (evidence), with `method` and `extractor_version`.
- As the **platform**, extraction is derived, re-runnable and scoped.
  - **AC4:** Re-extracting a document **updates** its `document_texts` row (derived
    data is regenerable — not append-only) and emits a new event; the raw document
    is untouched.
  - **AC5:** An unsupported content type raises `UnsupportedContentTypeError`
    (surfaced as `422` from the endpoint); nothing is stored. All operations are
    user-scoped (`401` without auth).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `TextExtractor` protocol: `content_type_matches(content_type) -> bool`, `extract(data: bytes) -> str`, `method: str`. `ExtractorRegistry.for_content_type(ct)` returns the first matching extractor or raises `UnsupportedContentTypeError`. |
| FR-2 | Functional | `PlainTextExtractor` matches `text/*` and decodes UTF-8 with `errors="replace"`; `method = "plaintext-utf8"`. `EXTRACTOR_VERSION` is a module constant. |
| FR-3 | Functional | Table `document_texts` (derived): `document_id` (UUID PK), `user_id` (UUID, indexed), `method`, `extractor_version`, `char_count` (int), `text` (Text), `extracted_at` (UTC). |
| FR-4 | Functional | Event `knowledge.document_text_extracted` (`schema_version = 1`), payload `{document_id, method, extractor_version, char_count}` — **not** the text; appended + published (commit-before-publish). |
| FR-5 | Functional | `ExtractionService.extract_document(user_id, document_id)`: validate the document is the user's (`UnknownDocumentError`), read the blob, pick the extractor, **upsert** the `document_texts` row, append + publish the event, return `ExtractedText`. `get_text(user_id, document_id)` reads the derived row (or `None`). |
| FR-6 | Functional | Celery task `mylife.extract_document_text(user_id, document_id)` runs the service against a real session + Redis publisher (fails closed on unknown/foreign document). |
| FR-7 | Functional | Endpoints use `get_current_user`; `POST …/extract` → 200 result / `404` / `422`; `GET …/text` → text or `404`. Erasure (`T2.5`) includes `document_texts`. |
| NFR-1 | Typing/Deps | Passes `mypy --strict`; **no new runtime dependency** (plain-text extractor uses stdlib; OCR/PDF engines are future optional adapters). |
| NFR-2 | Migration | One Alembic revision creates `document_texts`; `alembic check` clean. |
| NFR-3 | Testability | Extraction (text → row+event, char count, method), re-extract updates row, unsupported type → error/`422`, scoping/auth/`404`, `get_text`. |

## 5. API & event contracts

```
POST /documents/{id}/extract     -> 200 ExtractedText   (404 foreign / 422 unsupported)
GET  /documents/{id}/text        -> 200 { text }         (404 foreign / not extracted)

ExtractedText = { document_id, method, extractor_version, char_count }
```

- **Event produced:** `DocumentTextExtracted` (Knowledge context), referencing
  the document.

## 6. Data model & migration strategy

- `DocumentTextRow` on `Base` (table `document_texts`) — **derived** data (raw
  document bytes stay authoritative in the blob store). New Alembic revision
  `0014_document_texts`; `env.py` imports the model. Proposed layout:
  `src/mylife/knowledge/extraction.py` (extractors + registry + service +
  `DocumentTextExtracted`), a Celery task in `src/mylife/workers/tasks.py`, routes
  in `src/mylife/api/knowledge.py`.

## 7. Privacy, consent, access-control & retention

- Extracted text is sensitive derived personal data: authenticated, user-scoped,
  never logged. Auto-enqueue on ingest runs in the worker (consent already applied
  at ingest). Erasure (`T2.5`) removes `document_texts` alongside `documents` and
  their blobs.

## 8. Test plan

- **Extract text (AC1/AC3/FR-5):** upload a `text/plain` doc → extract → row +
  `DocumentTextExtracted` with method/version/char_count; text matches.
- **Get text (AC2):** returns the extracted text; `404` before extraction / foreign.
- **Re-extract (AC4):** second run updates the row (one row) and emits another event.
- **Unsupported (AC5):** e.g. `application/pdf` (no adapter yet) → error / `422`;
  nothing stored.
- **Scoping/auth (AC5):** foreign → `404`; unauthenticated → `401`.
- **Erasure/migration:** `document_texts` removed on erase; `alembic check` clean.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T6.1` docs/blobs, `T0.9` Celery, events, auth.
- **Open decisions (resolved):**
  - *Strategy registry.* → content-type-keyed extractors; plain-text ships,
    OCR/PDF are drop-in adapters (optional engines) later.
  - *Derived, regenerable.* → `document_texts` is upserted on re-extract (not
    append-only); the event trail records each extraction.
  - *Text location.* → derived DB row (queryable for `T6.3`), **not** the event
    payload; the event carries method + counts + evidence.
  - *Trigger.* → explicit endpoint + Celery task now; auto-enqueue-on-ingest is
    the production worker path.
- **Risks:**
  - *Large texts in DB* — acceptable for first cut; object-store or chunked
    storage is future work.
  - *OCR quality/engine availability* — deferred to pluggable adapters; the port
    keeps callers stable.
- **Future work:** pdfminer/tesseract adapters (optional deps), language
  detection, retries/backoff, embeddings (`T6.3`).

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check`
      clean.
- [ ] Endpoints authenticated/in OpenAPI; Celery task registered; migration
      reviewed; backlog + spec status updated; erasure includes `document_texts`.
- [ ] Extracted text is derived + evidence-linked (method/version); no new runtime
      dependency; data user-scoped and not logged.
