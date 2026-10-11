# Spec: User groups with shared Finance + admin console (`T2.6`)

> Spec-Driven Development artifact.

- **Status:** Implemented (`src/mylife/identity/groups.py`, `src/mylife/api/admin.py`,
  migration `0027`, tests in `tests/test_groups.py` + `tests/test_groups_api.py`,
  web `web/src/pages/admin/AdminPage.tsx`)
- **Backlog task:** `T2.6`
- **Bounded context:** Identity (upstream); Finance consumes the scope contract
- **Author / date:** Claude Code / 2026-10-11
- **Depends on:** `T2.1` (users/households), `T2.2` (auth), `T2.4` (audit), `T4.*` (Finance)

## 1. Purpose & business context

Two or more people (e.g. a couple) want to see and manage **the same Finance
content** — accounts, transactions, categories, bills, Open Finance sync — from
their own logins. Today every Finance row is scoped to the caller's `user_id`,
so each person sees an isolated ledger.

This task turns the dormant `T2.1` *household* into a **group**: a named set of
users with a **titular (owner)** whose Finance data the group shares. It adds an
`admin` role and an admin console ("Usuários e grupos") where admins manage
users' roles and the groups.

## 2. Scope

- **In scope:**
  - User role: `member` (default) | `admin`, with bootstrap via config.
  - Group CRUD (create, rename, change owner, delete) and membership
    (add/remove) — admin only.
  - Finance data resolution: a group member's Finance requests read/write the
    group owner's Finance data.
  - `GET /groups/me` so any member sees which group/ledger they are in.
  - Web: admin page (nav entry visible to admins only) + a "shared" banner in
    Finanças.
- **Out of scope (future):**
  - Sharing other domains (Health, Goals, Knowledge…) — Finance only now; the
    scope resolver is per-domain so others can opt in later.
  - Per-member permissions inside a group (read-only members), invitations
    accepted by the invitee, membership in more than one group.
  - Merging a member's pre-existing personal Finance data into the group.
  - Cross-domain consumers (briefing, goals progress, assistant) reading the
    shared ledger — they keep reading the caller's own events.

## 3. User stories & acceptance criteria

- As an **admin**, I see every user and can promote/demote admins.
  - **AC1:** `GET /admin/users` lists users with `role` and `household_id`;
    non-admins get `403`.
  - **AC2:** `PATCH /admin/users/{id}/role` changes the role; demoting the
    **last** admin returns `409` (no lockout).
- As an **admin**, I manage groups.
  - **AC3:** `POST /admin/groups {name, owner_user_id}` creates a group with
    the owner as its first member; an owner already in another group → `409`.
  - **AC4:** Adding a user already in a group → `409`; removing the owner →
    `409` (change owner or delete the group instead).
  - **AC5:** Deleting a group detaches all members (their personal data is
    untouched and visible again).
- As a **group member**, I see and edit the shared Finance content.
  - **AC6:** A transaction recorded by a member is listed for the owner and
    every other member, and vice-versa.
  - **AC7:** After leaving the group the member sees only their own Finance
    data again.
  - **AC8:** Only the owner may store/delete the Open Finance API key (`403`
    for other members); any member may trigger a sync (owner's key/consent).

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | `users.role` (`member`\|`admin`, default `member`). |
| FR-2 | Functional | `households.owner_user_id` (nullable for legacy rows). The owner is always a member. A user belongs to at most one group (`users.household_id`). |
| FR-3 | Functional | `MYLIFE_ADMIN_EMAILS` (comma-separated): a user whose email is listed is made `admin` at registration and promoted at login (bootstrap of the first admin; no secret involved). |
| FR-4 | Functional | `GroupService.data_owner_for(user_id, domain)` → the group owner for shared domains (`finance`), else the user. Falls back to the user when not grouped, the group has no owner, or the owner no longer exists. |
| FR-5 | Functional | Every Finance endpoint resolves its data scope via FR-4. |
| FR-6 | Functional | Public registration no longer accepts `household_id` (`422`): joining a group grants access to someone else's data, so only an admin may do it. The unauthenticated `POST /households` / `GET /households/{id}` placeholders are replaced by the admin API. |
| FR-7 | Functional | Membership and role changes emit Life Events on the affected user's stream (`identity.group_joined`, `identity.group_left`, `identity.role_changed`); every admin action is also written to the audit log with the admin as actor. |
| NFR-1 | Security | All `/admin/*` routes require an authenticated `admin` (`401`/`403`). |
| NFR-2 | Typing/quality | `mypy --strict`, `ruff`, `tsc`, eslint, vitest green. |

## 5. API & event contracts

```
GET    /admin/users                              -> 200 [AdminUser]
PATCH  /admin/users/{user_id}/role  {role}       -> 200 AdminUser | 404 | 409 last admin | 422
GET    /admin/groups                             -> 200 [GroupDetail]
POST   /admin/groups  {name, owner_user_id}      -> 201 GroupDetail | 404 user | 409 user grouped
PATCH  /admin/groups/{id}  {name?, owner_user_id?} -> 200 GroupDetail | 404 | 409 owner not a member
DELETE /admin/groups/{id}                        -> 204 | 404
POST   /admin/groups/{id}/members  {user_id}     -> 201 GroupDetail | 404 | 409 already grouped
DELETE /admin/groups/{id}/members/{user_id}      -> 204 | 404 | 409 is owner
GET    /groups/me                                -> 200 GroupDetail | null
```

`GroupDetail = {household_id, name, owner_user_id, created_at, members: [{user_id, display_name, email}]}`.
`User` gains `role`.

Events (schema_version 1, `source = "identity"`):

| event_type | user_id | payload |
| ---------- | ------- | ------- |
| `identity.group_joined` | member | `{household_id, group_name, owner_user_id, by_user_id}` |
| `identity.group_left` | member | `{household_id, by_user_id}` |
| `identity.role_changed` | target | `{role, by_user_id}` (`by_user_id` null for config bootstrap) |

Audit actions: `admin.role_changed`, `admin.group_created`, `admin.group_updated`,
`admin.group_deleted`, `admin.group_member_added`, `admin.group_member_removed`
(resource `household:<id>`).

## 6. Data model & migration strategy

Migration `0027`: add `users.role` (`String`, NOT NULL, server default
`'member'`) and `households.owner_user_id` (`Uuid`, nullable). Downgrade drops
both columns. Shared Finance rows/events keep `user_id = owner` (the data
subject of the ledger); the acting member is recorded in the audit log and in
the `correlation_id` trail. No Finance rows are moved or rewritten.

## 7. Privacy, consent, access-control & retention

- Joining a group exposes the **owner's** Finance data to members; the member's
  own Finance data is hidden (not shared, not deleted) while grouped. This is a
  deliberate admin decision, recorded as events + audit entries.
- The owner's Open Finance consent and key are used for group syncs; only the
  owner may change the key.
- Data-subject erasure of the owner erases the shared ledger (it is the
  owner's data); the group then falls back to each member's own data (FR-4).
- Emails of fellow members are visible to group members via `/groups/me`.

## 8. Test plan

- `tests/test_groups.py` (service): role bootstrap, create/add/remove/delete,
  conflicts (AC3–AC5), last-admin guard (AC2), `data_owner_for` fallbacks (FR-4),
  events emitted (FR-7).
- `tests/test_groups_api.py` (HTTP): admin gating (NFR-1, AC1), shared Finance
  round-trip (AC6, AC7), Open Finance key owner-only (AC8), registration rejects
  `household_id` (FR-6).
- Web: `AdminPage.test.tsx`, `Layout.test.tsx` (admin-only nav entry).

## 9. Dependencies, open decisions, risks & future work

- **Open decisions (defaults chosen, revisit if needed):**
  1. *Shared ledger = owner's data* (chosen) vs. union of all members' data
     (rejected: ids/ownership checks across users, merge semantics unclear).
  2. *Admins are global* (chosen) vs. per-group admins.
  3. *Finance only* (chosen) — the user asked "como finanças"; other domains
     are opt-in later via `SHARED_DOMAINS`.
- **Risks:** an admin can expose an owner's finances to others — mitigated by
  admin-only access, audit trail and events on the member's stream.
- **Future:** invitations with consent from the owner, read-only members,
  sharing more domains, briefing/goals reading the shared ledger.

## 10. Definition of Done

- [x] Spec written and implementation traceable to it.
- [x] Tests (per §8) pass; `ruff`, `mypy`, `pytest` green.
- [x] API/docs and the backlog status updated.
- [x] Privacy/consent/security implications addressed.
