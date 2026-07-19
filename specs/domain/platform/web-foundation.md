# Spec: Platform — Web foundation (app shell + API client + auth) (`T9.4`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T9.4` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (T9 epic)
- **Bounded context:** Platform — Web (new `web/` subproject)
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T2.2` (auth / `POST /auth/login`), the existing HTTP API

## 1. Purpose & business context

The backend is complete; the product needs a **surface**. This task stands up the
Web client foundation — a Vite + React + TypeScript + Tailwind app in `web/` — with
a **typed API client**, a **login flow** (JWT), and an **app shell** with routing
and an auth guard. It is deliberately thin: the timeline and briefing views land in
`T9.5`. The web app consumes the public API/contracts only (no backend internals),
honouring the context-boundary rule.

## 2. Scope

- **In scope:**
  - `web/` subproject: Vite + React 18 + TypeScript (strict) + TailwindCSS.
  - A typed `ApiClient`: base-URL fetch wrapper that attaches the bearer token,
    parses JSON, and raises a typed `ApiError` on non-2xx; `login(email, password)`
    → token, plus typed getters used later (`getTimeline`, `getBriefing`).
  - `AuthProvider`/`useAuth`: token persisted in `localStorage`, login/logout,
    `isAuthenticated`.
  - App shell: router (`/login`, `/` protected), a header with logout, a
    `RequireAuth` guard redirecting to `/login`.
  - Tooling + gates: `tsc --noEmit` (typecheck), `eslint`, `vitest run` (jsdom +
    Testing Library).
- **Out of scope (later):**
  - Timeline & briefing views (`T9.5`); design-system/shadcn components; data
    caching libraries; SSR; e2e tests; deployment (a deferred epic).

## 3. User stories & acceptance criteria

- As a **user**, I sign in and reach a protected home.
  - **AC1:** Visiting `/` while unauthenticated redirects to `/login`.
  - **AC2:** Submitting valid credentials calls `POST /auth/login`, stores the token
    and lands on `/`; the header shows a working logout that clears the token and
    returns to `/login`.
  - **AC3:** `ApiClient` attaches `Authorization: Bearer <token>` to authenticated
    calls and raises `ApiError{status}` on a non-2xx response.
- As a **developer**, the project is gated.
  - **AC4:** `npm run typecheck`, `npm run lint` and `npm run test` all pass.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `web/` builds with Vite; TypeScript `strict`; Tailwind wired via PostCSS; scripts `dev`, `build`, `typecheck`, `lint`, `test`. |
| FR-2 | Functional | `ApiClient(baseUrl, getToken)`: `request<T>(path, {method, body, auth})` attaches the bearer token when `auth`, sets JSON headers, returns parsed `T`, throws `ApiError` (with `status`) on non-2xx. `login(email, password)` posts form-encoded credentials to `/auth/login` and returns the `access_token`. |
| FR-3 | Functional | `AuthProvider` stores the token in `localStorage` (`mylife.token`), exposes `token`, `isAuthenticated`, `login()`, `logout()`; `useAuth()` hook. |
| FR-4 | Functional | Routing: `/login` (form) and `/` (protected by `RequireAuth`, redirecting unauthenticated users to `/login`); a header with the app name + logout. |
| FR-5 | Non-functional | The client depends only on the public HTTP API; the API base URL comes from `import.meta.env.VITE_API_BASE_URL` (default `/`). No secrets in the repo. |
| NFR-1 | Testability | Vitest (jsdom) + Testing Library: `ApiClient` attaches the token + maps errors (fetch mocked); `RequireAuth` redirects; login stores the token. |
| NFR-2 | Tooling | `tsc --noEmit`, `eslint` and `vitest run` are green; committed lockfile; `node_modules` git-ignored. |

## 5. API & event contracts

- **Consumes** (no new endpoints): `POST /auth/login` (OAuth2 password form →
  `{access_token}`); later `GET /timeline`, `GET /briefing` (typed in the client for
  `T9.5`). No backend change.

## 6. Data model & migration strategy

- **No backend change, no migration.** New `web/` tree:
  `web/{package.json,tsconfig*.json,vite.config.ts,tailwind.config.js,postcss.config.js,index.html,eslint.config.js}`,
  `web/src/{main.tsx,App.tsx,index.css}`, `web/src/api/{client.ts,types.ts}`,
  `web/src/auth/{AuthContext.tsx}`, `web/src/pages/{LoginPage.tsx,HomePage.tsx}`,
  `web/src/components/{RequireAuth.tsx,Header.tsx}`, tests alongside. `web/node_modules`
  is git-ignored; `web/package-lock.json` is committed.

## 7. Privacy, consent, access-control & retention

- The token lives in `localStorage` for the session and is cleared on logout; no
  other user data is persisted client-side in this task. All data calls are
  authenticated and user-scoped by the backend. No secrets committed.

## 8. Test plan

- **ApiClient (AC3/NFR-1):** mock `fetch`; assert the bearer header on an authed
  call, form body on `login`, and `ApiError{status}` on a 401.
- **Auth (AC2/FR-3):** `login()` stores the token → `isAuthenticated` true; `logout()`
  clears it.
- **Guard (AC1/FR-4):** `RequireAuth` renders a redirect to `/login` when
  unauthenticated and children when authenticated.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** backend auth + API.
- **Open decisions (resolved):**
  - *Vite + React + TS + Tailwind, no design-system yet.* → smallest real modern
    stack; shadcn/ui components are additive later.
  - *Token in `localStorage`.* → simplest working auth for the MVP; httpOnly-cookie
    hardening is future work (noted).
  - *Gates = tsc + eslint + vitest.* → typecheck, lint and unit/component tests run
    in CI-equivalent commands.
- **Risks:**
  - *`localStorage` tokens are XSS-exposed* — acceptable for the MVP surface;
    documented, with cookie hardening as future work.
- **Future work:** timeline/briefing views (`T9.5`), shadcn/ui, data caching,
  hardened auth, e2e, deployment.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] `web/` typechecks, lints and tests green; login + guard + typed client work.
- [ ] `node_modules` ignored, lockfile committed; backlog + spec status updated.
