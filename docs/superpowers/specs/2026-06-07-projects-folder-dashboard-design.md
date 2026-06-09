# Projects Folder Dashboard + Reusable Favorites — Design

**Date:** 2026-06-07
**Contexts:** Personalization (new), Research Organization (05)
**Aggregates:** `Favorite` (new), `Project` (stats only)

## Summary

Replace the flat, low-signal **Projects** table with a **folder-style card grid**
optimized for *fast navigation* — getting into the right target/pathway area
quickly. A Project in Cellar is a scope/container that gathers **campaigns**
(every campaign belongs to exactly one project), collections, saved searches,
linked protocols/molecules, members, and tags; in this workspace the projects
read like a TB discovery cascade (intramacrophage, whole-cell aerobic vs.
non-replicating, cell-wall biosynthesis, …). The current table shows four columns
where two are near-constant (Status always "Active", Created By always the same
user) and Description is mostly empty — ~90% of the grid carries no signal.

The redesign delivers, in three independently-testable phases:

1. **Favorites** — a reusable, polymorphic-by-design personalization primitive
   (server-side, per-user) so "pin to top" works for projects now and any entity
   later, with zero cross-context coupling.
2. **Project stats extension** — add `campaign_count`, `last_activity_at`, and
   member info to the existing batch stats endpoint.
3. **Projects folder dashboard** — the card grid, toolbar (filter / tags /
   archived / **sort** / **cards⇄table**), identity-colored folder cards, and
   favorites integration. The existing ag-grid table becomes "table" mode.

### Primary job: fast navigation (decided)

The page is a *finder*, not a KPI dashboard. Counts are quiet supporting detail;
recognition (color identity) does the heavy lifting. Out of scope: a
portfolio-KPI header band, triage sparklines (see YAGNI).

---

## Phase 1 — Favorites (new `personalization` context)

A single tiny aggregate holding only a **soft reference** (`entity_type` string +
`entity_id`). It never imports `Molecule`, `Protocol`, etc., so it stays
self-contained and reusable. UI semantics: a boolean star; the **★ Pinned**
section surfaces a user's favorites at the top of the grid.

### 1. Domain (`backend/src/cellar/domain/personalization/`)

- **`enums.py`** — `FavoriteEntityType(StrEnum)`, starting with
  `PROJECT = "project"`. Documented to grow (`molecule`, `protocol`,
  `collection`, `campaign`) as modules adopt favorites — adding a value is the
  only change needed. StrEnum (not free text) keeps it type-safe while extensible.
- **`favorite.py`** — `Favorite` aggregate: `id`, `workspace_id`, `user_id`,
  `entity_type: FavoriteEntityType`, `entity_id: UUID`, `created_at`, `version`.
  Factory `Favorite.create(workspace_id, user_id, entity_type, entity_id)`.
- **No domain events / no audit trail.** Favorites are personal UI preference,
  not regulated data; emitting audit operations per star toggle would be noise.
  (Deliberate departure from the "events for side effects" default — documented
  here so it isn't mistaken for an omission.)

### 2. Persistence (`backend/src/cellar/infrastructure/persistence/sqlalchemy/personalization/`)

- **`models.py`** — `FavoriteModel`, table `favorites`: `id` (PK),
  `workspace_id`, `user_id`, `entity_type` (String(50)), `entity_id` (UUID),
  `created_at`, `version`.
  - **Unique** `(user_id, workspace_id, entity_type, entity_id)` — one favorite
    per user per entity.
  - **Index** `(user_id, workspace_id, entity_type)` for the list query.
- **Alembic migration** — create `favorites` table.
- **`favorite_repository.py`** — `add` (idempotent on the unique key),
  `remove` (by natural key), `list_for_user(user_id, workspace_id, entity_type)`,
  `exists`.

### 3. Application (`backend/src/cellar/application/personalization/`)

Railway pattern, workspace-scoped, auth-guarded per `backend-code-guidelines.md`.
`workspace_id` and `user_id` come from the auth context (never from the client).

- **`add_favorite.py`** — `AddFavoriteInput(entity_type, entity_id)`; **idempotent**
  (returns the existing favorite if already present, no error).
- **`remove_favorite.py`** — `RemoveFavoriteInput(entity_type, entity_id)`; no-op
  if absent.
- **`list_favorites.py`** — `ListFavoritesInput(entity_type)` → the current
  user's favorites of that type.

### 4. Interface (`backend/src/cellar/interface/routes/favorites.py`)

- `GET  /api/v1/favorites?entity_type=project` → `FavoriteResponse[]`
  (`entity_type`, `entity_id`, `created_at`).
- `POST /api/v1/favorites` `{entity_type, entity_id}` → idempotent create.
- `DELETE /api/v1/favorites/{entity_type}/{entity_id}` → 204.
- Wire DI (Lagom) for the repository + use cases. Regenerate orval.

### 5. Frontend (`frontend/src/shared/hooks/use-favorites.ts`)

Cross-feature, so it lives in `shared/`, calling `customInstance` (dominant
convention; reuse generated `FavoriteResponse` type):

- **`useFavorites(entityType)`** → `Set<string>` of favorited entity ids (+ load
  state).
- **`useToggleFavorite(entityType)`** → mutation with **optimistic update** and
  rollback; invalidates the favorites query key on settle.

### Testing (Phase 1)

- **Domain** — factory builds a valid favorite; entity_type enum round-trips.
- **Persistence** — add/list/remove round-trip; duplicate add is idempotent
  (unique constraint honored, no second row).
- **Application** — add is idempotent; remove of an absent favorite is a no-op;
  list returns only the current user's, current workspace's, requested type.
- **API** — POST then GET returns it; DELETE then GET omits it; another user
  doesn't see it (scoping).

---

## Phase 2 — Project stats extension (`research_organization`)

Extend the **existing** batch endpoint `GET /api/v1/projects/stats?project_ids=…`
(today: `molecule_count`, `protocol_count`, `run_count`). One query change, no
new aggregate.

### Domain / Interface

- **`project_scope_stats.py`** (VO) + `ProjectScopeStats` response gain:
  - `campaign_count: int` — `COUNT(campaign WHERE project_id = ?)`.
  - `last_activity_at: datetime | None` —
    `greatest(project.updated_at, max(campaign.updated_at for project))`, i.e.
    *when screening last moved here*, not just when the name was edited.
  - `member_count: int` and `member_ids: list[UUID]` (capped at the first ~5)
    for the avatar stack.

### Persistence (`…/research_organization/project_repository.py`)

- Extend the scope-stats query with subqueries for the four fields above.
  `member_ids`/`member_count` come from `project_members`. Keep it a single
  batched query over the requested `project_ids` (no per-project N+1).

### Frontend

- `pnpm generate:api` so `ProjectScopeStatsResponse` gains the fields; update
  the consumer in `use-project-scope-stats.ts`.
- **Member avatars:** resolve `member_ids` → name/avatar via the existing
  user/`MemberName` resolution. If that resolves per-user, add/confirm a batched
  user-lookup so a grid of N cards doesn't fire N×members requests. (Flagged as
  an implementation detail to verify during build.)

### Testing (Phase 2)

- **Persistence** — a project with campaigns reports correct `campaign_count`
  and `last_activity_at = max(campaign.updated_at)` when newer than the project;
  a project with no campaigns reports `0` / `project.updated_at`;
  `member_ids`/`member_count` correct and capped.
- **API** — response contract includes the new fields for a batch of ids.

---

## Phase 3 — Projects folder dashboard (Frontend)

`frontend/src/features/research-organization/`. New components alongside the
existing `project-list.tsx`, which becomes the host that toggles **card grid**
⇄ the **existing ag-grid table** (table mode untouched — power users lose
nothing).

### Toolbar (`project-grid-toolbar.tsx` or extend in `project-list.tsx`)

`Filter…` (keep) · `Tags` filter (keep) · `Show archived` toggle (keep) ·
**`Sort`** (Recently active / Name A–Z / Most compounds) · **`[▣ cards | ☰ table]`**
segmented toggle. `view` and `sort` persist in `localStorage`
(`projects:view`, `projects:sort`) — legitimate per-device UI prefs, distinct
from server-side favorites.

### Grid (`project-card-grid.tsx`)

- Responsive: ~4 cards/row wide → 2 (tablet) → 1 (phone), Tailwind grid (matches
  existing grid patterns).
- Two sections: **★ Pinned** (only if the user has favorited any) then
  **All projects**, each ordered by the chosen sort. Default: pinned-first, then
  Recently active (`last_activity_at` desc).
- **Archived** projects appear only with the toggle on — rendered dimmed with an
  `Archived` chip, and not pinnable.
- Empty grid → existing `EmptyState` (FolderKanban icon) with a **New Project**
  action. Loading → skeleton cards.

### Card (`project-card.tsx`) — density "B, trimmed"

```
┌────────────────────────────┐
│▌[▣] Intramacrophage      ☆ │   ▌ color spine · [▣] glyph tile · ☆ pin (on hover/filled)
│     Screening efforts      │   one-line description, muted; "No description" if empty
│ ────────────────────────── │
│   142          3           │   big number / small label
│ compounds   campaigns      │   "No campaigns yet" rendered gracefully at 0
│ ────────────────────────── │
│ (SR)(AK)(MJ)      3d ago    │   member-avatar stack (left) · last activity (right)
└────────────────────────────┘
```

- **Identity color** — deterministic, same every visit → recognition. **v1:** a
  **stable hash of the project name** via `resolveCategoryColor` in
  `shared/lib/category-colors.ts`. Tag-based coloring (single colored tag → use
  it) is deferred: project tags aren't in the projects-list payload, so doing it
  now would force an N+1 (a tag fetch per card). It slots into the same
  `projectIdentityColor` helper once tags ship in the list response — a clean
  follow-up, not a hack. The
  glyph is the shared project mark (`FolderKanban`); color does the
  distinguishing. Helper: `projectIdentityColor(project, tags)`.
- Whole card → `/projects/{id}` (a link; keyboard-focusable). The **pin star** is
  a separate button (`aria-label`, `stopPropagation`) calling
  `useToggleFavorite('project')` with optimistic feedback.
- Hover lifts a subtle shadow (same feel as `results/molecule-card.tsx`).
- Reuses `Card`, `Badge`, `Avatar`, `Skeleton`.

### Testing (Phase 3)

- **Unit** — card renders identity color (tag vs. hash fallback), graceful 0/empty
  states, pin toggle calls the mutation and reflects optimistic state; grid
  splits Pinned vs All and respects sort; archived hidden unless toggled and not
  pinnable; view/sort persist to localStorage.
- **E2E (Playwright)** — switch cards⇄table; pin a project → it moves to ★ Pinned
  and survives reload (server-side); sort changes order; click a card → detail.

---

## Cross-cutting

- Regenerate orval in the **same change** as each backend phase (CLAUDE.md: no
  hand-rolled DTOs). orval never prunes `model/index.ts` — review the diff.
- DI wiring (Lagom) for the new repository + use cases.
- Update the GitHub project board as phases land.
- Commit per phase, tests green before advancing (layer order: Domain → tests →
  Persistence → tests → Application → API → tests → UI → E2E).

## Out of scope (YAGNI)

The favorites primitive *enables* but this change does **not** build:

- Wiring stars onto molecules / protocols / collections / campaigns (later;
  `entity_type` already supports them).
- Ordered pins (a `position` column) — v1 favorites are boolean.
- Triage extras: run/activity **sparklines**, in-flight pulse dots.
- A portfolio-KPI **header band** (that was the "consortium snapshot" job, not
  the chosen "fast navigation" job).
- Per-project **custom icon/color picker** (auto-derive now; manual override
  later) and drag-to-reorder folders.
- "Recently viewed" projects.
