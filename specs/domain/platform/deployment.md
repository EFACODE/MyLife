# Spec: Platform — deployment (VPS + Docker Compose) (`T11`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T11.1` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (platform)
- **Bounded context:** Platform (deployment)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** the whole app; `T0.2` (dev compose), `T9.2` (readiness probe)

## 1. Purpose & business context

Ship My Life to a **single VPS** (Hostinger/Hetzner/DigitalOcean) with **Docker
Compose**: the API, the Celery worker, Postgres, Redis and a Caddy reverse proxy on
one box. To avoid CORS entirely, the **SPA is served same-origin by the API** — the
built web bundle is mounted by FastAPI so one origin serves both the app and the
API; Caddy in front only terminates TLS and proxies the domain. This task (`T11.1`)
containerizes the app and adds the same-origin static serving; `T11.2` adds the
production compose + Caddy + migrations; `T11.3` is the deploy runbook.

## 2. Scope (T11.1)

- **In scope:**
  - A multi-stage **`Dockerfile`**: stage 1 builds the web SPA (`web/` → `dist`);
    stage 2 is the Python runtime that installs the package, copies the built SPA to
    `/app/static`, and runs `uvicorn`.
  - **Same-origin SPA serving**: when `MYLIFE_STATIC_DIR` is set, FastAPI mounts the
    directory at `/` with **SPA history fallback** (unknown non-API paths →
    `index.html`), added **after** all API routers so API routes win.
  - `MYLIFE_STATIC_DIR` setting (default `None` → no static serving, unchanged dev
    behaviour); `.dockerignore`.
- **Out of scope:** the production compose + Caddy + release/migrate (`T11.2`); the
  runbook (`T11.3`); an S3 blob adapter (future); CI image publishing.

## 3. User stories & acceptance criteria

- As an **operator**, one container serves the app and the API on one origin.
  - **AC1:** With `MYLIFE_STATIC_DIR` set to a dir containing `index.html`, `GET /`
    returns that HTML; a client-side route (e.g. `GET /finance`) also returns
    `index.html` (SPA fallback); a static asset (e.g. `GET /assets/app.js`) is served.
  - **AC2:** API routes still win: `GET /health` returns the health JSON (not the
    SPA); unknown **API-looking** 404s from real routes are unaffected.
  - **AC3:** With `MYLIFE_STATIC_DIR` unset (default), no static mount is added — dev
    behaviour is unchanged.
  - **AC4:** `docker build .` succeeds and the image runs `uvicorn` serving `/health`.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `Settings.static_dir: str \| None = None` (env `MYLIFE_STATIC_DIR`). |
| FR-2 | Functional | `SpaStaticFiles(StaticFiles)` returns `index.html` on a 404 (SPA history fallback). `create_app` mounts it at `/` **after** all routers when `static_dir` is set and exists. |
| FR-3 | Functional | Multi-stage `Dockerfile`: `node:22-slim` builds `web/` (`npm ci && npm run build`); `python:3.11-slim` installs the package (`pip install .`), copies `web/dist` → `/app/static`, sets `MYLIFE_STATIC_DIR=/app/static`, `EXPOSE 8000`, `CMD uvicorn mylife.main:app --host 0.0.0.0 --port 8000`. Copies `alembic.ini` + `migrations/` so the image can run migrations. |
| FR-4 | Functional | `.dockerignore` excludes `.git`, `**/node_modules`, `**/__pycache__`, `.venv`, `*.sqlite3`, `var/`, `web/dist`, test caches. |
| NFR-1 | Security | No secrets in the image or repo; `MYLIFE_JWT_SECRET` etc. come from the environment at run time (documented in `T11.3`). The image runs as a non-root user. |
| NFR-2 | Typing/Deps | `ruff`, `mypy --strict`, `pytest` stay green; no new Python dependency (uses FastAPI's bundled `StaticFiles`). |
| NFR-3 | Testability | Tests: SPA fallback + asset served + API route wins + no-mount default. `docker build` verified locally. |

## 5. API & event contracts

- No new HTTP endpoints; static files mounted at `/`. No events, no migration.

## 6. Data model & migration strategy

- **No schema change.** New: `Dockerfile`, `.dockerignore`,
  `src/mylife/api/spa.py` (`SpaStaticFiles`); edits to `src/mylife/main.py`
  (conditional mount) and `src/mylife/core/config.py` (`static_dir`).

## 7. Privacy, consent, access-control & retention

- Static serving exposes only the public SPA bundle (no secrets baked in — the SPA
  reads the API same-origin). All data access remains authenticated via the API.

## 8. Test plan

- **SPA fallback (AC1):** temp dir with `index.html` + `assets/app.js`; `MYLIFE_STATIC_DIR`
  set; `/`, `/finance`, `/assets/app.js` all serve correctly.
- **API precedence (AC2):** `/health` returns health JSON with the mount active.
- **Default (AC3):** no `MYLIFE_STATIC_DIR` → `/` is not the SPA (404/route as before).
- **Image (AC4):** `docker build .` succeeds (verified during implementation).

## 9. Dependencies, open decisions, risks & future work

- **Open decisions (resolved):**
  - *Same-origin SPA via the API.* → one origin serves SPA + API, so **no CORS**
    is needed; Caddy only does TLS/domain (`T11.2`).
  - *SPA fallback in a `StaticFiles` subclass.* → client-side routes work on refresh.
  - *Static serving is env-gated.* → zero change to dev/test defaults.
- **Risks:** the blob store is still filesystem — production needs a **persistent
  volume** for `MYLIFE_BLOB_STORE_PATH` (handled in `T11.2` compose); an S3 adapter
  is future work.
- **Future work:** S3-compatible blob adapter, CI image build/publish, healthcheck
  tuning, gunicorn worker count.

## 10. Definition of Done (T11.1)

- [ ] Spec approved; implementation traceable.
- [ ] `Dockerfile` builds; API serves the SPA same-origin with history fallback and
      API precedence; env-gated (default off).
- [ ] `ruff`/`mypy`/`pytest` green; backlog + spec status updated.
