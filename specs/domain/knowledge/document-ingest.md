# Spec: Knowledge context — Document ingest & storage (`T6.1`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T6.1` — [issue #34](https://github.com/EFACODE/MyLife/issues/34)
- **Bounded context:** Knowledge
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T1.x` (event kernel + bus, raw/normalized separation), `T2.2`
  (auth), `T2.5` (erasure)

## 1. Purpose & business context

Open the **Knowledge** bounded context: let a user ingest personal **documents**
(statements, contracts, notes) as the raw material for search and retrieval
(`T6.2` OCR, `T6.3` semantic retrieval). A document's **bytes are the raw source
data** — stored in **object storage** (the authoritative external system,
matching the raw/normalized/derived split) — while the kernel records an immutable
`DocumentIngested` event and a `documents` registry row referencing the blob by
key + checksum. Documents are highly sensitive, so access is authenticated,
user-scoped and auditable.

## 2. Scope

- **In scope:**
  - A `BlobStore` port (put/get/delete/exists) with a filesystem-backed adapter
    for local/dev; the store is the authoritative home for document **bytes**.
  - A `documents` registry (metadata: filename, content type, size, checksum,
    storage key), user-scoped.
  - `DocumentIngested` event (Knowledge context) referencing the blob (key +
    checksum) — never the bytes.
  - `KnowledgeService`: ingest a document (store blob + row + event), read
    metadata, list, fetch content; delete a user's documents+blobs (for erasure).
  - Authenticated endpoints: `POST /documents` (upload), `GET /documents`,
    `GET /documents/{document_id}`, `GET /documents/{document_id}/content`.
- **Out of scope (later):**
  - OCR / text extraction (`T6.2`); semantic retrieval / embeddings (`T6.3`);
    knowledge-graph consolidation (`T6.4`).
  - Virus scanning, versioning, sharing, S3/GCS adapters (port allows them later).

## 3. User stories & acceptance criteria

- As a **user**, I upload a document and get it back.
  - **AC1:** `POST /documents` (authenticated, multipart) stores the bytes in the
    blob store, writes a `documents` row and emits `DocumentIngested`; it returns
    the document metadata (id, filename, content type, size, checksum).
  - **AC2:** `GET /documents` / `GET /documents/{id}` return my documents'
    metadata; `GET /documents/{id}/content` streams the stored bytes with the
    original content type. A foreign/unknown document → `404`.
- As the **platform**, documents stay private, exact and erasable.
  - **AC3:** All endpoints require auth (`401`) and act only on the caller's
    documents. The blob **key is namespaced by `user_id`**; content is never
    logged.
  - **AC4:** The stored `checksum` (SHA-256) matches the uploaded bytes; re-fetch
    returns identical bytes.
  - **AC5:** Erasure (`T2.5`) deletes the user's `documents` rows **and** their
    blobs from the store.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `BlobStore` protocol: `put(key, data: bytes) -> None`, `get(key) -> bytes`, `delete(key) -> None`, `exists(key) -> bool`. `FilesystemBlobStore(root)` writes under `root`, creating parent dirs; `get` of a missing key raises `BlobNotFoundError`. |
| FR-2 | Functional | Table `documents`: `document_id` (UUID PK), `user_id` (UUID, indexed), `filename`, `content_type`, `byte_size` (int), `checksum` (SHA-256 hex), `storage_key`, `created_at` (UTC). |
| FR-3 | Functional | Event `knowledge.document_ingested` (`schema_version = 1`), payload `{document_id, filename, content_type, byte_size, checksum, storage_key}` — the blob reference, **not** the bytes; appended + published (commit-before-publish). |
| FR-4 | Functional | `KnowledgeService.ingest_document(user_id, filename, content_type, data, *, now, correlation_id)`: compute checksum, `storage_key = f"{user_id}/{document_id}"`, `blob.put`, add row, append + publish event, return `Document`. On a failure after `put`, the blob is best-effort deleted (no orphan row). |
| FR-5 | Functional | `KnowledgeService`: `get_document`, `list_documents`, `get_content(user_id, document_id) -> (Document, bytes)` (reads the blob), all user-scoped; `delete_user_documents(user_id)` removes rows + blobs (for erasure). |
| FR-6 | Functional | Endpoints use `get_current_user`; `POST /documents` accepts a multipart file; `GET …/content` returns the bytes with the stored `content_type`. Unknown/foreign document → `404`. |
| NFR-1 | Security/Privacy | Documents are sensitive: authenticated, user-scoped, blob keys namespaced by user; bytes/filenames never logged. Erasure removes rows + blobs (AC5). |
| NFR-2 | Migration | One Alembic revision creates `documents`; `alembic check` clean. |
| NFR-3 | Typing/Deps | Passes `mypy --strict`; stdlib `hashlib`/`pathlib` only (no new dependency); `python-multipart` (already a dep) handles uploads. |
| NFR-4 | Testability | Ingest → stored+event+metadata; content round-trips identical bytes; checksum matches; scoping/auth/404; erasure deletes rows+blobs. |

## 5. API & event contracts

```
POST /documents            (multipart: file=@statement.pdf)     -> 201 Document
GET  /documents                                                 -> [Document]
GET  /documents/{id}                                            -> Document (404 foreign)
GET  /documents/{id}/content                                    -> bytes (original content type)

Document = { document_id, filename, content_type, byte_size, checksum, created_at }
```

- **Event produced:** `DocumentIngested` (Knowledge context), referencing the blob.

## 6. Data model & migration strategy

- `DocumentRow` on `Base` (table `documents`); blob **bytes** live in the
  `BlobStore` (object storage), keyed `f"{user_id}/{document_id}"` — the raw
  source stays outside the kernel (external system authoritative). New Alembic
  revision `0013_documents`; `env.py` imports the model. Proposed layout:
  `src/mylife/knowledge/` (models, blob_store, service) + `src/mylife/api/knowledge.py`.
  Blob root is configured in settings (`blob_store_path`, default under a local
  data dir; tests use a temp dir or an in-memory store).

## 7. Privacy, consent, access-control & retention

- All endpoints authenticated and user-scoped; blob keys namespaced by `user_id`;
  document bytes and filenames are never logged. Manual upload of one's own
  documents needs no connector consent (consistent with manual capture); a future
  document **connector** would be consent-gated (`T2.3`). Erasure (`T2.5`) removes
  the user's `documents` rows and deletes their blobs — the sanctioned override of
  append-only for personal data.

## 8. Test plan

- **Ingest (AC1/FR-3/FR-4):** upload → blob stored, row written, `DocumentIngested`
  emitted, metadata returned; checksum matches.
- **Content round-trip (AC4):** `get_content` returns identical bytes.
- **List/get + scoping (AC2/AC3):** user sees only their docs; foreign → `404`.
- **Auth (AC3):** endpoints `401` without a token.
- **Erasure (AC5):** after erase, rows gone and blobs deleted from the store.
- **Migration (NFR-2):** CI `alembic upgrade head && alembic check`.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** event kernel (`T1.x`), auth (`T2.2`), erasure (`T2.5`);
  stdlib + `python-multipart` (existing).
- **Open decisions (resolved):**
  - *Bytes location.* → **object storage via a `BlobStore` port** (filesystem
    adapter now; S3/GCS later) — raw source data outside the kernel.
  - *Event carries a reference.* → `DocumentIngested` stores the blob **key +
    checksum**, never the bytes (raw/normalized separation).
  - *Key namespacing.* → `f"{user_id}/{document_id}"` for isolation + easy
    per-user erasure.
  - *Consent.* → manual upload needs none; a document connector (future) is
    consent-gated.
- **Risks:**
  - *Large uploads* buffered in memory for checksum/put — acceptable for first
    cut; streaming/multipart-to-store is future work.
  - *Blob/row consistency* — best-effort blob cleanup on post-put failure; a
    reconcile sweep is future work.
- **Future work:** OCR (`T6.2`), retrieval (`T6.3`), S3/GCS adapter, streaming
  uploads, document connector (consent-gated), size/type limits.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Tests (per §8) pass; `ruff`, `mypy --strict`, `pytest` green; `alembic check`
      clean.
- [ ] Endpoints authenticated/in OpenAPI; migration reviewed; backlog + spec
      status updated; erasure removes documents rows + blobs.
- [ ] Bytes in object storage (never in events/logs); checksum verified; document
      data user-scoped.
