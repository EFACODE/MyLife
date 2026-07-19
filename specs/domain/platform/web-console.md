# Spec: Platform — full web console architecture (`T10`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T10.1` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (platform)
- **Bounded context:** Platform — Web
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T9.4`/`T9.5` (web foundation + surfaces), the full HTTP API

## 1. Purpose & business context

Let a user **manually exercise every backend feature through a real WebUI**. The
`web/` app today covers 4 of ~50 endpoints; this group grows it into a **console**
— one page (form + list/detail) per feature area, behind a navigation shell. `T10.1`
lays the shared architecture the feature tasks (`T10.2`–`T10.9`) plug into; this
spec is the contract they reference. The web consumes only the public API.

## 2. Scope (T10.1 foundation)

- **In scope:**
  - **Navigation shell**: a `Layout` route (`Outlet`) with a sidebar built from a
    `NAV` registry; `RequireAuth` wraps the layout once; `App.tsx` becomes a route
    registry. The dashboard (Briefing + Timeline) moves under the layout.
  - **`MeProvider`/`useMe()`**: resolve `GET /auth/me` once; pages needing the
    `user_id` (timeline, briefing, …) read it from context.
  - **`useAsync` hook**: a `{status: idle|loading|ready|error, data, error, run}`
    state machine so pages don't hand-roll it.
  - **UI primitives**: `Field`, `Button`, `Section`, `ErrorText` (Tailwind).
  - **Auth hardening**: `ApiClient` gets an `onUnauthorized` callback fired on any
    `401`; `useApiClient` wires it to `auth.logout()` (guard → redirect via
    `RequireAuth`).
  - **Multipart**: `ApiClient.upload<T>(path, file)` (FormData) for `POST /documents`.
  - **Dev connectivity**: a committed Vite dev proxy forwarding API path prefixes to
    `http://127.0.0.1:8000`; `web/.env.example`; `web/README.md` runbook.
- **Out of scope (feature tasks):** the per-area pages themselves (`T10.2`–`T10.9`).

## 3. User stories & acceptance criteria

- As a **user**, I navigate the whole app from one shell.
  - **AC1:** After login I land on a layout with a **sidebar**; each nav link routes
    to its page; the active link is highlighted; a **Log out** control clears the
    token and returns me to `/login`.
  - **AC2:** If any API call returns `401`, the app logs me out and redirects to
    `/login` (expired/invalid token handling).
  - **AC3:** `useMe()` exposes the signed-in user; a page can read `user_id` without
    its own `/auth/me` call.
- As a **developer**, the console has reusable building blocks.
  - **AC4:** `useAsync(fn, deps)` runs on mount, exposes `status/data/error` and a
    `run()` to re-invoke; a rejected `fn` yields `status:"error"` with the message.
  - **AC5:** `ApiClient.upload` posts multipart `FormData` with the bearer token.
  - **AC6:** `npm run dev` reaches the API same-origin via the Vite proxy (no CORS);
    `tsc`, `eslint`, `vitest` stay green.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `NAV: NavItem[]` registry (`{path,label}`); `Layout` renders the sidebar (`NavLink`, active state) + `Outlet` + logout. `App.tsx`: `/login` public; all else under `<Route element={<RequireAuth><Layout/></RequireAuth>}>` with child routes (feature tasks append). |
| FR-2 | Functional | `MeProvider` resolves `client.me()` via `useAsync`; `useMe()` returns `{user, status}`. Wraps the layout's outlet. |
| FR-3 | Functional | `useAsync<T>(fn, deps, {immediate=true})` → `{status, data, error, run}`; `run()` sets loading, resolves→ready(data) or rejects→error(message). |
| FR-4 | Functional | `ApiClient` third ctor arg `onUnauthorized?: () => void`; on a `401` in `request`/`upload` it fires the callback before throwing `ApiError`. `useApiClient` passes `() => logout()`. |
| FR-5 | Functional | `ApiClient.upload<T>(path, file: File)`: `POST` `FormData` (`file` field) with bearer token, no JSON content-type; parse JSON or throw `ApiError`. |
| FR-6 | Functional | `web/vite.config.ts` `server.proxy` maps the API path prefixes to `http://127.0.0.1:8000` (dev only). `web/.env.example` (`VITE_API_BASE_URL`), `web/README.md` runbook. |
| FR-7 | Functional | UI primitives `Field`(label+input), `Button`, `Section`(titled card), `ErrorText`(`role="alert"`). |
| NFR-1 | Testability | Vitest: `useAsync` (ready/error/reload); `Layout` (nav links + logout); `ApiClient.upload` + `onUnauthorized` (fetch mocked). |
| NFR-2 | Tooling | `tsc --noEmit`, `eslint`, `vitest run` green; the `web` CI job enforces them. |

## 5. API & event contracts

- **Consumes** the existing API only; no backend change. (Optional, deferred:
  env-gated `CORSMiddleware` via `MYLIFE_CORS_ORIGINS` if a non-proxy origin is ever
  needed — not part of `T10.1`.)

## 6. Data model & migration strategy

- **No backend change, no migration.** New: `web/src/lib/useAsync.ts`,
  `web/src/nav.ts`, `web/src/components/Layout.tsx`, `web/src/auth/MeContext.tsx`,
  `web/src/components/ui/{Field,Button,Section,ErrorText}.tsx`, `web/README.md`,
  `web/.env.example`. Edited: `web/src/App.tsx`, `web/src/api/client.ts`,
  `web/src/api/useApiClient.ts`, `web/src/pages/HomePage.tsx`, `web/vite.config.ts`.

## 7. Privacy, consent, access-control & retention

- No new client persistence beyond the existing `localStorage` token; `401` now
  proactively clears it. All data calls carry the bearer token; the console never
  reaches backend internals — only the public API.

## 8. Test plan

- **useAsync:** immediate run → ready(data); throwing fn → error(message); `run()`
  re-invokes.
- **Layout:** within router+auth (me() stubbed) renders the brand, a nav link and a
  logout that calls `logout`.
- **ApiClient:** `upload` sends `FormData` with the bearer header; a `401` fires
  `onUnauthorized` and throws `ApiError`.

## 9. Feature-page contract (for `T10.2`–`T10.9`)

Each feature task: (a) add typed models to `web/src/api/types.ts` mirroring the
backend request/response models named in `src/mylife/api/*.py` (do **not** invent
fields); (b) add `ApiClient` methods; (c) build page(s) under
`web/src/pages/<area>/` using `useAsync` + the UI primitives, taking a
`Pick<ApiClient, …>` prop so they unit-test against a stub; (d) append `NAV`
entries + child routes; (e) ship `*.test.tsx`. Consent-gated imports surface a
`403` as a "grant consent first" hint. The endpoint→page map lives in the approved
plan.

## 10. Definition of Done (T10.1)

- [ ] Spec approved; implementation traceable.
- [ ] Sidebar shell + `useMe` + `useAsync` + UI primitives + `401` logout + `upload`
      + Vite proxy + `.env.example` + `README` in place.
- [ ] `tsc`/`eslint`/`vitest` green; backlog + spec status updated.
