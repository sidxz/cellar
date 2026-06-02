# Design: AWS-Style Key-Value Tagging

- **Status:** Draft (approved design, pending spec review)
- **Date:** 2026-06-02
- **Context:** Workspace Config (07), cross-cutting into Chemical Registration (01), Screening & Assay (02), Research Organization (05)
- **Author:** Siddhant Rath (with Claude)

---

## 1. Motivation

Users need to attach arbitrary, user-defined **key + optional-value** tags (AWS-style) to
domain objects — starting with **Molecule, Protocol, Project, Collection** — and then filter
by those tags across every dashboard and search surface. Tags are shared workspace-wide,
discoverable via autocomplete, and carry provenance ("who created this tag"). The system must
stay fast and efficient at **hundreds of thousands** of tags / tag-assignments.

This is a cross-cutting capability: more taggable entity types will be added later, so the
mechanism must generalize without rework.

---

## 2. Decisions (and why)

These were settled during brainstorming and drive the rest of the design.

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Shared, workspace-wide tags with provenance** (not per-user-private). | Collaborative filtering is the point; "see tags I created" is served by a `created_by` filter + a *created-by-me* view, not by privacy scoping. |
| D2 | **Free-form (AWS-style)** — anyone types any key/value; autocomplete suggests existing ones. No admin gatekeeping of which keys/values may exist. | Maximum flexibility; drift curbed by autocomplete + case-insensitive dedup. Governed/controlled keys are a documented future extension. |
| D3 | **A tag is a `key` with an OPTIONAL `value`.** | Unifies plain labels and `key=value` into one model. The existing free-text `Molecule.tags` strings migrate cleanly as **value-less** tags. |
| D4 | **Normalized registry + per-entity assignment link tables** (not JSONB-on-entity, not a single polymorphic link table). | Registry gives O(1) indexed autocomplete / provenance / usage / rename. Per-entity link tables keep indexes small and discriminator-free (faster hot-path filtering), give real FKs + `ON DELETE CASCADE` (DB-enforced integrity, no orphan accumulation, 21 CFR alignment), and match the existing `collection_molecules` / `project_members` convention. A `UNION ALL` view recovers the one thing polymorphic does better (cross-type "everything tagged X"). |
| D5 | **Case-insensitive dedup/match; original casing preserved for display.** | Curbs near-duplicate drift ("Env"/"env") in a free-form system while keeping display fidelity. |

**Rejected — JSONB `tags` column as source of truth:** reads fast but fights every stated
goal at scale — autocomplete / "all tags" / "created by me" would scan 100Ks of entity rows
across four tables instead of one indexed registry lookup; per-tag provenance has nowhere to
live; renaming a tag rewrites every entity row. Also breaks the codebase's join-table
convention. A denormalized JSONB read-cache *on top of* the normalized tables remains a valid
future optimization if list filtering is ever measured too slow (YAGNI now — indexed joins
handle 100Ks comfortably).

---

## 3. Goals / Non-Goals

**Goals (v1)**
- Key + optional-value tags on Molecule, Protocol, Project, Collection.
- Shared workspace-wide, with `created_by` provenance and a *created-by-me* view.
- Free-form creation via assignment; autocomplete over existing keys/values.
- Case-insensitive dedup.
- Assign / unassign; batch-set an entity's tags from the detail page.
- Filter by tags (AND / OR) on all four dashboards, in the advanced-search DSL, and persisted in SavedSearch.
- Tag-management screen: usage counts, search, created-by, **rename / merge / delete**.
- Migrate existing `Molecule.tags` into the new system; repoint all readers; drop the legacy column.
- Audit every tag mutation (append-only, via domain events).

**Non-Goals (future, but not precluded by the model)**
- Per-user private tags.
- Admin-governed / controlled keys (fixed value sets) — the "hybrid governance" option.
- Bulk CSV tag import (when added: **must** ship a Download-Template button per project convention).
- Denormalized JSONB read-cache.
- Typed values (numbers/dates/ranges) — values are strings.
- Tag-based access control / permissions.

---

## 4. Domain Layer

New capability under **Workspace Config** (`domain/workspace_config/tagging/`), beside
`ControlledVocabulary` (which is *not* reused — it models protocol pick-lists, a 1-to-many
reference concept, orthogonal to user-curated cross-cutting tags).

### 4.1 `Tag` (aggregate root)

Extends `AggregateRoot` (so: `id`, `version`, `created_at`, `updated_at`, domain events).

```
Tag
  id:               UUID
  workspace_id:     UUID
  key:              str            # display casing preserved
  value:            str | None     # None => plain label
  normalized_key:   str            # lower+trim, for dedup/match
  normalized_value: str | None     # lower+trim
  created_by:       UUID
  (created_at, updated_at, version from base)

  classmethod create(workspace_id, name: TagName, created_by) -> Tag   # emits TagCreated
  rename(new: TagName)                                                 # emits TagRenamed; bumps version
```

`Tag` does **not** hold its assignments in memory (mirrors `Collection` not holding its
molecule list). Assignment is managed by `TagLinkRepository`.

### 4.2 `TagName` (value object)

Frozen Pydantic model — single home for normalization + validation so the rules live in one
place:
- trim key/value; **key required & non-empty** after trim; value optional.
- length caps: key ≤ 128, value ≤ 256 (AWS-ish).
- reject control characters.
- expose `normalized_key` / `normalized_value` (casefold + trim) for dedup/match.

### 4.3 Domain events

Frozen dataclasses extending `DomainEvent` (carry `workspace_id`, `aggregate_id`,
`aggregate_type="Tag"`, plus target ref where relevant):
`TagCreated`, `TagAssigned`, `TagUnassigned`, `TagRenamed`, `TagMerged`, `TagDeleted`.
All are caught by the existing catch-all `AuditEventHandler` → append-only audit.

### 4.4 Repository interfaces (domain)

- **`TagRepository`** (aggregate): `find_by_id_in_workspace`, `get_or_create(workspace_id, TagName, created_by)`, `search(workspace_id, q, created_by=None, sort, cursor, limit)`, `save`, `delete`.
- **`TagLinkRepository`** (links — *not* an aggregate repo; lightweight, direct SQL, like `ProjectMemberRepository`): `add(workspace_id, entity_type, entity_id, tag_id, assigned_by)`, `remove(...)`, `set_for_entity(...)`, `find_tags_for_entity(workspace_id, entity_type, entity_id)`, `find_entity_ids_for_tags(workspace_id, entity_type, tag_ids, logic)`, `repoint(from_tag_id, to_tag_id)` (for merge).

---

## 5. Persistence Layer

`infrastructure/persistence/sqlalchemy/workspace_config/` (+ link tables referenced from each
context's models module as needed for FK targets).

### 5.1 `tags` table

`EntityModelMixin + WorkspaceIdMixin + VersionMixin` plus:
`key (text)`, `value (text null)`, `normalized_key (text)`, `normalized_value (text null)`,
`created_by (uuid)`.

Indexes:
- `UNIQUE (workspace_id, normalized_key, normalized_value) NULLS NOT DISTINCT` — dedup,
  including value-less tags (PG16 `NULLS NOT DISTINCT`).
- `GIN (normalized_key gin_trgm_ops)` and `GIN (normalized_value gin_trgm_ops)` — autocomplete
  (requires `pg_trgm` extension; add in the migration if absent).
- `(workspace_id, created_by)` — created-by-me.

### 5.2 Per-entity link tables

`molecule_tags`, `protocol_tags`, `project_tags`, `collection_tags`. Shared `TagLinkMixin`
contributes the common shape:
```
tag_id      uuid  FK -> tags.id        ON DELETE CASCADE
<entity>_id uuid  FK -> <entity>.id    ON DELETE CASCADE
assigned_by uuid
assigned_at timestamptz default now()
PRIMARY KEY (<entity>_id, tag_id)
INDEX (tag_id)                          # reverse lookup: entities for a tag
```
No `version` column (these are links, not aggregates — same as `collection_molecules`).

### 5.3 `tag_links_all` view

`CREATE VIEW tag_links_all AS SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
tag_id, assigned_by, assigned_at FROM molecule_tags UNION ALL …` (all four). Backs cross-type
"everything tagged X" and management usage counts.

### 5.4 Repositories

- `SQLAlchemyTagRepository` — standard data-mapper (`_to_domain`/`_to_model`/`_update_model`).
  `get_or_create` uses `INSERT … ON CONFLICT (workspace_id, normalized_key, normalized_value)
  DO NOTHING` then re-select, so concurrent first-use is race-safe via the unique index.
- `SQLAlchemyTagLinkRepository` — **one generic base** parametrized by `(model_class,
  entity_fk_attr)`, with four 3-line subclasses. `add` uses `on_conflict_do_nothing`
  (idempotent). Workspace defense-in-depth: subquery confirms the entity belongs to the
  workspace before insert/delete (same pattern as `project_member_repository`).

### 5.5 Migrations

**Migration 047 (next after 046) — create + backfill:**
1. `CREATE EXTENSION IF NOT EXISTS pg_trgm`.
2. Create `tags` + four link tables + indexes + `tag_links_all` view.
3. **Backfill:** for each `molecules.tags` string element → `get_or_create` a value-less tag +
   insert `molecule_tags` link (`assigned_by` = molecule `created_by` or a system actor;
   `assigned_at` = molecule `created_at`). Idempotent, batched.

**Migration 048 — drop legacy column (ships in step 6, after all readers are repointed per §7):**
Drop the `molecules.tags` column. No read-compat shim.

> Sequencing: 047 leaves `molecules.tags` in place and populated, so old and new coexist while
> readers are migrated; 048 removes the column in the same change set as the code that stops
> reading it, so code never references a dropped column.

---

## 6. Application Layer

Use cases (each: `async __call__(cmd, auth) -> Result[…, DomainError]`, guard first, queries
before mutations, `uow.commit()` collects events, dispatch after commit):

| Use case | Auth | Notes |
|----------|------|-------|
| `AssignTag` | editor + same-workspace | `get_or_create` registry tag (emits `TagCreated` if new) → link upsert. Validates entity exists in workspace. |
| `UnassignTag` | editor | Remove link. |
| `SetEntityTags` | editor | Batch reconcile an entity's tag set (detail-page editor). |
| `ListTags` | viewer | Filters: `q`, key prefix, `created_by=me`, sort by name/usage; cursor-paginated. Backs autocomplete **and** management. |
| `GetTagsForEntity` | viewer | Chips on detail/cards. |
| `RenameTag` | **admin** | Optimistic concurrency on `Tag`. |
| `MergeTags` | **admin** | `repoint` links A→B (dedup), delete A. |
| `DeleteTag` | **admin** | Delete registry row; links cleared by CASCADE. |

**Auth split:** assign/unassign/create-by-assign = **editor**; rename/merge/delete
(workspace-wide effect) = **admin**.

**Filtering integration:**
- New **`tag` criterion** in `compose_criteria` (`infrastructure/.../search_query_composer.py`
  + a new `_tag_clauses.py`). Shape: `{type: "tag", tag_ids: [...], logic: "all" | "any",
  negate?: bool}`. Builds an `IN` subquery against the entity's link table; `all` →
  `GROUP BY <entity>_id HAVING count(DISTINCT tag_id) = N`.
- `tags` + `tag_logic` query params added to the simpler list endpoints
  (projects, collections, protocols) that don't go through the composer.

---

## 7. Migration Landmines (handle, don't shim)

Confirm and repoint **in the same change set** as the column drop:
1. **`keyword_list` search criterion** — verify it currently targets `Molecule.tags`; repoint
   to the new `tag` criterion (or translate at the composer).
2. **Any UI reading `molecule.tags`** — switch to the tag endpoints/chips.
3. **CDD / DataSource import mapping** that may populate tags — route through `AssignTag` so
   imported tags land in the new system.

---

## 8. Interface Layer (API)

All thin shells → command → use case; `workspace_id` from auth; responses via `from_domain`.
**No user ever types a tag/entity UUID** — always key/value or an autocomplete selection.

**Management**
- `GET /api/v1/tags` — list / search / autocomplete (`q`, `key`, `created_by=me`, sort, cursor, limit).
- `PATCH /api/v1/tags/{id}` — rename.
- `POST /api/v1/tags/{id}/merge` — merge into another tag.
- `DELETE /api/v1/tags/{id}` — delete.
- (`POST /api/v1/tags` explicit-create optional; assignment auto-creates.)

**Assignment** (nested per entity — typed, matches membership routes)
- `GET  /api/v1/{molecules|protocols|projects|collections}/{id}/tags` — list the entity's tags.
- `POST /api/v1/{…}/{id}/tags` — add one tag `{key, value?}` (backs `AssignTag`; idempotent).
- `PUT  /api/v1/{…}/{id}/tags` — replace the entity's full tag set (reconcile; backs `SetEntityTags`).
- `DELETE /api/v1/{…}/{id}/tags/{tagId}` — remove one tag (backs `UnassignTag`).

**Filtering**
- `tags` + `tag_logic` params on the four list endpoints.
- `tag` criterion in `POST /api/v1/search/execute`; persists in `SavedSearch.query` with **no
  schema change** (query already stores arbitrary criteria).

---

## 9. Frontend

`shared/components/tags/`:
- **`TagChip`** — compact `key=value` / `key`; density-aware on cards (show N, then `+k`, per
  card-density rule).
- **`TagEditor`** — autocomplete combobox (key, then optional value); **explicit** add/save,
  **no autosave** on consequential actions.
- **`TagFilter`** — multi-select picker with AND/OR toggle + **live result count** (matches the
  search-UX pass).

Wiring:
- `TagFilter` into all four dashboards; `TagChip` on cards + detail; `TagEditor` on detail pages.
- New **TagSection** in the advanced-search form so tag filters round-trip through SavedSearch.
- **Tag-management page** (workspace settings): table with usage counts, created-by, search,
  *created-by-me*, rename / merge / delete (admin). Proper form controls — **no JSON UI**.
- `orval` regen → TanStack Query hooks; active-filter state in URL/Zustand per existing convention.

---

## 10. Error Handling

Railway `Result`. `NotFoundError` (entity/tag), `ValidationError` (empty key, length, control
chars), `AuthorizationError` (role/workspace), optimistic-concurrency on `Tag` for
rename/merge. Tagging is **allowed even on locked Protocols** — tags are orthogonal annotations,
not protocol content.

---

## 11. Performance & Scale

- Registry: even 100K+ distinct `(key,value)` rows is small for Postgres; unique btree +
  trigram GIN make dedup and autocomplete indexed lookups.
- Links: composite PK + `tag_id` index serve both directions; AND-filtering via indexed
  `GROUP BY … HAVING`. Per-type tables keep indexes small and free of an `entity_type`
  discriminator; `CASCADE` keeps them free of orphan rows.
- Cross-type queries use `tag_links_all`.
- Escape hatch if list filtering is ever measured too slow: add a denormalized JSONB tag cache
  per entity (kept in sync from the link tables) — explicitly deferred.

---

## 12. Testing Strategy

- **Domain (unit):** `TagName` normalization/dedup, value-optional, length/control-char
  validation; `Tag.create`/`rename` emit correct events.
- **Integration:** concurrent `get_or_create` dedup (unique-index race), link add/remove,
  cascade-on-entity-delete, cross-workspace isolation, AND/OR/negate filter queries,
  migration-047 backfill correctness.
- **API:** assign/unassign/set/list/autocomplete/rename/merge/delete; auth split (editor vs
  admin, workspace); filtered lists; pagination.
- **E2E (Playwright):** tag a compound → filter a dashboard by tag → created-by-me → rename in
  management reflects everywhere.

---

## 13. Implementation Sequencing

Per project layer order (Domain → Domain tests → Persistence → Integration tests → Application
→ API → API tests → UI → E2E), suggested as commit-sized steps:

1. Domain: `TagName` VO, `Tag` aggregate, events, repo interfaces (+ unit tests).
2. Persistence: `tags` + link tables, mixins, view, `TagRepository`, generic `TagLinkRepository`
   + subclasses; **migration 047** (create + backfill, *without* the column drop yet)
   (+ integration tests).
3. Application: `AssignTag`/`UnassignTag`/`SetEntityTags`/`ListTags`/`GetTagsForEntity` + DI.
4. API: assignment + management routes (+ API tests).
5. Filtering: `tag` criterion in the composer + `tags` params on list endpoints; repoint
   `keyword_list`; CDD import mapping (+ tests).
6. Migration cleanup: drop `molecules.tags` column + domain field once all readers are repointed.
7. Admin: `RenameTag`/`MergeTags`/`DeleteTag` + routes (+ tests).
8. Frontend: `TagChip`/`TagEditor`/`TagFilter`, dashboard wiring, advanced-search TagSection,
   management page; `orval` regen.
9. E2E.

---

## 14. Open Questions / Risks

- **`keyword_list` semantics** — must confirm it maps to `Molecule.tags` before repointing
  (step 5). If it means something else, the migration's reader list changes.
- **CDD import** — confirm whether/where it writes tags; ensure imported tags route through the
  new system.
- **`assigned_by` for backfilled molecule tags** — use molecule `created_by`, falling back to a
  system actor where null.
- **Management usage counts at very high cardinality** — computed via aggregate query
  (paginated) for v1; add a maintained counter only if measured slow.
