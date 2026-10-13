# Spec: Menu customization — reorder and hide sidebar items (`T10.12`)

- **Status:** Implemented (`src/mylife/identity/nav_preferences.py`, `src/mylife/api/identity.py`,
  migration `0028`, tests in `tests/test_nav_preferences.py`; web
  `web/src/pages/settings/MenuSettingsPage.tsx`, `web/src/nav.ts`)
- **Backlog task:** `T10.12`
- **Bounded context:** Identity (stores the preference); web console (applies it)
- **Author / date:** Claude Code / 2026-10-13

## 1. Purpose & business context

The left sidebar lists every module in a fixed order. A user who lives in one
module (e.g. Finanças) wants it on top and the others out of the way. This adds
a per-user menu configuration: reorder every item and hide any of them.

## 2. Scope

- **In scope:** per-user order + hidden set of sidebar items, stored server-side
  (follows the user across devices); a "Personalizar menu" screen; applying the
  preference to the sidebar/drawer.
- **Out of scope:** hiding a module also blocks its route (it does **not** — a
  hidden item is only removed from the menu; links and URLs still work);
  per-group or admin-imposed menus; renaming items or custom icons.

## 3. User stories & acceptance criteria

- As a user, I put Finanças on top and hide every other item.
  - **AC1:** The sidebar shows only the visible items, in my order.
  - **AC2:** The configuration survives logout and is the same on another device.
  - **AC3:** "Personalizar menu" stays reachable from the sidebar footer even
    when every other item is hidden, and at least one item stays visible.
  - **AC4:** "Restaurar padrão" goes back to the default order with nothing hidden.
  - **AC5:** Items added to the app later (not in my saved order) appear after
    my ordered items, visible, in their default order. Unknown saved paths are
    ignored. Admin-only items stay admin-only regardless of the preference.

## 4. Requirements

| ID | Type | Requirement |
| -- | ---- | ----------- |
| FR-1 | Functional | Table `nav_preferences`: `user_id` (PK), `order` (JSON list of item paths), `hidden` (JSON list of item paths), `updated_at`. Current-state row (a UI preference, not a life fact — same pattern as `notification_preferences`). |
| FR-2 | Functional | `GET /users/me/nav-preferences` → `{order, hidden, updated_at}` (empty lists and `updated_at = null` when never set). |
| FR-3 | Functional | `PUT /users/me/nav-preferences {order, hidden}` replaces the preference. Each path must start with `/`, be ≤ 64 chars, lists ≤ 50 entries; duplicates are removed (first wins). `422` otherwise. |
| FR-4 | Functional | The backend stores paths opaquely; the web console owns the item registry (`NAV`) and resolves the preference against it (AC5). |
| FR-5 | Functional | Data-subject export includes the preference; erasure deletes it. |
| NFR-1 | Usability | Reordering uses up/down buttons (keyboard- and touch-friendly, 44px targets on mobile). |

## 5. API contract

```
GET /users/me/nav-preferences          -> 200 NavPreferences
PUT /users/me/nav-preferences {order: string[], hidden: string[]}
                                       -> 200 NavPreferences | 401 | 422
NavPreferences = {order: string[], hidden: string[], updated_at: datetime | null}
```

## 6. Data model & migration

Migration `0028` creates `nav_preferences`; downgrade drops it.

## 7. Privacy & access control

Authenticated, self-scoped only. No personal data beyond UI choices.

## 8. Test plan

- `tests/test_nav_preferences.py`: defaults, round-trip, de-duplication,
  validation (`422`), auth (`401`), per-user isolation, export/erase (FR-1–FR-5).
- Web: `nav.test.ts` (resolution rules, AC5), `MenuSettingsPage.test.tsx`
  (reorder/hide/restore, last-visible guard), `Layout.test.tsx` (applied order,
  footer link).

## 9. Open decisions, risks & future work

- **Hiding ≠ access control** (chosen): hiding is a convenience, not a
  permission. Restricting modules per user would be a separate, admin-owned
  feature.
- **Future:** drag-and-drop reordering; group-level default menus.
