# Spec: Platform — Web surfaces (timeline + daily briefing) (`T9.5`)

> Spec-Driven Development artifact. **Approve before implementation.**

- **Status:** Approved
- **Backlog task:** `T9.5` — [issue #40](https://github.com/EFACODE/MyLife/issues/40) (T9 epic)
- **Bounded context:** Platform — Web
- **Author / date:** Claude Code / 2026-07-19
- **Depends on:** `T9.4` (web foundation), `T3.1` (timeline API), `T3.6`/`T4.6` (briefing)

## 1. Purpose & business context

The first product surfaces: after login, the user sees their **timeline** (recent
Life Events, filterable by type) and can deliver their **daily briefing**
(rule-based, evidence-linked). The web consumes the existing API only. Because the
timeline/briefing endpoints still take an explicit `user_id` (pending `T2` gating),
the app first resolves the signed-in user via `GET /auth/me`, then queries
`GET /timeline/events?user_id=…` and `POST /briefing`.

## 2. Scope

- **In scope:**
  - `ApiClient` methods: `me()` (`GET /auth/me`), `getTimeline(userId, {eventType?,
    limit?, offset?})` (`GET /timeline/events`), `deliverBriefing(userId,
    windowHours?)` (`POST /briefing`).
  - A `useApiClient()` hook (client bound to the auth token).
  - `Timeline` component: fetch + render events (type, time, source), filter by
    `event_type`, empty/error states.
  - `Briefing` component: deliver a briefing, render each line (kind, summary,
    evidence count), empty/error states.
  - `HomePage`: resolve `me()`, then render `Briefing` + `Timeline`.
- **Out of scope (later):**
  - Pagination controls beyond a "load more"/limit; event detail drill-down;
    creating events from the UI; charts; the forecast/insight surfaces.

## 3. User stories & acceptance criteria

- As a **user**, after signing in I see my recent activity and my briefing.
  - **AC1:** `HomePage` resolves `me()` and renders the timeline for that `user_id`;
    events show their type, time and source.
  - **AC2:** Filtering by an `event_type` re-queries and shows only matching events;
    an empty result shows an empty state (not an error).
  - **AC3:** Delivering a briefing calls `POST /briefing` and renders each line's
    summary with its evidence count; before delivery, a prompt/button is shown.
  - **AC4:** A failed call shows an inline error, not a crash.
- As a **developer**, the surfaces are gated.
  - **AC5:** `tsc`, `eslint` and `vitest` remain green, including component tests for
    Timeline (renders events, filter) and Briefing (renders lines).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `ApiClient.me(): Promise<User>`; `getTimeline(userId, opts?): Promise<TimelinePage>` building a query string (`user_id`, optional `event_type`, `limit`, `offset`); `deliverBriefing(userId, windowHours=24): Promise<Briefing>` (POST). All authenticated. |
| FR-2 | Functional | Types match the API: `TimelineEvent{event_id,user_id,event_type,occurred_at,recorded_at,source,…,payload}`, `TimelinePage{items,limit,offset,has_more}`, `Briefing{user_id,generated_at,window_hours,event_count,lines}`, `BriefingLine{kind,summary,evidence}`, `User{user_id,email,display_name,…}`. |
| FR-3 | Functional | `Timeline`: loads on mount + when the filter changes; loading/empty/error states; each row shows `event_type`, localized `occurred_at`, `source`. |
| FR-4 | Functional | `Briefing`: a deliver action → renders `lines` (each `kind` + `summary` + `evidence.length`), `event_count`; loading/error states. |
| FR-5 | Functional | `HomePage` resolves `me()` (loading/error), then renders `Briefing` + `Timeline` with the resolved `user_id`; `Header` logout intact. |
| NFR-1 | Testability | Vitest component tests with a stubbed client: Timeline renders events and applies the filter; Briefing renders lines after delivery. |
| NFR-2 | Tooling | `tsc --noEmit`, `eslint`, `vitest run` green. |

## 5. API & event contracts

- **Consumes** (no backend change): `GET /auth/me`, `GET /timeline/events?user_id=…&event_type=…&limit=…&offset=…`, `POST /briefing {user_id, window_hours}`.

## 6. Data model & migration strategy

- **No backend change, no migration.** New `web/src/api/useApiClient.ts`,
  `web/src/components/{Timeline,Briefing}.tsx` (+ tests), `getTimeline/deliverBriefing/me`
  on `ApiClient`, corrected `web/src/api/types.ts`, expanded `web/src/pages/HomePage.tsx`.

## 7. Privacy, consent, access-control & retention

- All calls carry the bearer token; the timeline/briefing are scoped to the resolved
  `user_id` (the signed-in user). No new client-side persistence; evidence is shown
  as ids/counts, not copied data.

## 8. Test plan

- **Timeline (AC1/AC2/FR-3):** stub `getTimeline` → rows render; changing the filter
  re-queries with the `event_type`; empty result → empty state.
- **Briefing (AC3/FR-4):** stub `deliverBriefing` → clicking deliver renders the
  lines + evidence counts.
- **Errors (AC4):** a rejected call renders an inline error.

## 9. Dependencies, open decisions, risks & future work

- **Dependencies:** `T9.4`, timeline/briefing APIs.
- **Open decisions (resolved):**
  - *Resolve `user_id` via `/auth/me`.* → the timeline/briefing endpoints still take
    an explicit `user_id` (pre-`T2` gating); the web bridges it with the
    authenticated `me()` call, so nothing leaks cross-user.
  - *Components take a `client` prop.* → trivially testable with a stub; `HomePage`
    injects the real `useApiClient()`.
- **Risks:**
  - *Endpoints not yet auth-gated* — when `T2` gates them (dropping the `user_id`
    param), only the client methods change; components stay put.
- **Future work:** pagination controls, event detail, insight/forecast surfaces,
  shadcn/ui, data caching.

## 10. Definition of Done

- [ ] Spec approved and implementation traceable to it.
- [ ] Timeline + briefing render from the API; filter + deliver work; error states
      handled; `tsc`/`eslint`/`vitest` green; backlog + spec status updated.
