# Design: Tagging Expansion — Run, Campaign, Batch, RegisteredPlate (+ finish Protocol/Project) + Cross-Entity Browse

- **Status:** Draft (approved design, pending spec review)
- **Date:** 2026-06-04
- **Context:** Workspace Config (07) tagging, extended into Screening & Assay (02), Research Organization (05/campaigns), Inventory (03)
- **Author:** Siddhant Rath (with Claude)
- **Builds on:** `docs/superpowers/specs/2026-06-02-tagging-design.md` (the original AWS-style key-value tagging design). Read that first — this spec assumes its model, vocabulary, and layer layout.

---

## 1. Motivation

The key-value tagging system shipped for **Molecule, Protocol, Project, Collection** (branch `kvt`).
Users now want to tag and tag-filter four more entity types — **Run, Campaign, Batch, and the
inventory RegisteredPlate** — and want a single place to see *everything carrying a given tag*
across all entity types. Two of the original four (Protocol, Project) have their backend +
list-filter wired but were never given the detail-page tag editor; that gap is closed here too.

The original backend was deliberately generalized (a `TaggableEntityType` enum, a `TagLinkMixin`,
a generic `SQLAlchemyTagLinkRepository` base + per-type subclasses, a `_REGISTRY`, a generic
assignment router keyed off an `_ENTITY_COLLECTIONS` map, and a shared `tag_filter_subquery`).
Adding an entity type is therefore a **mechanical, additive recipe** with no new patterns. The
only genuinely new design work is the cross-entity browse surface.

---

## 2. Scope

**In scope**
- Make taggable: **Run, Campaign, Batch, RegisteredPlate** (full backend slice + FE).
- **Finish Protocol & Project:** mount the detail-page tag editor (`TagTable`) — backend and list
  filter already exist.
- **List tag-filtering** wired into each entity's existing list surface (no new global dashboards
  for Run/Campaign — they filter within their scoped lists per the decision below).
- **Cross-entity tag-browse:** "everything tagged X" across all entity types — new read endpoint +
  a `/tags` browse page; admin tag-management usage counts become click-through to it.

**Out of scope / explicitly excluded**
- The **assay `Plate`** (`domain/screening_assay/run.py::Plate`, table `plates`): it is an `Entity`
  *owned by* the `Run` aggregate, has **no `workspace_id`**, and no standalone dashboard. Not
  independently taggable. ("Plate" in this spec means **`RegisteredPlate`** — inventory, table
  `registered_plates`, browsable at `/inventory/plates`.) Users who want to annotate assay plates
  tag the parent **Run**.
- Per-user private tags, controlled/governed keys, typed values, tag-based access control — all
  remain non-goals from the original design.
- Bulk CSV tag import (if ever added, must ship a Download-Template button per project convention).

**Decisions settled in brainstorming**
| # | Decision |
|---|----------|
| E1 | "Plate" = inventory **RegisteredPlate**, not the Run-owned assay `Plate`. |
| E2 | Run/Campaign tag-filters live **within their existing scoped lists** (per-protocol Runs tab; per-project Campaign list) — no new top-level dashboards. |
| E3 | **Build the cross-entity tag-browse surface** (a global "everything tagged X" view). |
| E4 | **Finish Protocol & Project** detail-page tag editors so all entities are consistent. |

---

## 3. Target entities — verified facts

All four new targets are workspace-scoped aggregates with an `id` UUID PK and a `workspace_id`
column, so they fit the existing link-table + workspace-defense pattern with zero schema gymnastics.

| Entity | Domain (AggregateRoot) | Model / table | List surface today | Display label for browse |
|--------|------------------------|---------------|--------------------|--------------------------|
| **Run** | `domain/screening_assay/run.py::Run` ✅ ws | `RunModel` → `runs` | `GET /protocols/{id}/runs` (per-protocol, nested) | `"{protocol name} — {run date}"` (runs have no name) |
| **Campaign** | `domain/research_organization/campaign.py::Campaign` ✅ ws | `CampaignModel` → **`campaign`** (singular) | `GET /campaigns?project_id=` (per-project) | campaign `name` |
| **Batch** | `domain/inventory/batch.py::Batch` ✅ ws | `BatchModel` → `batches` | global inventory list + per-molecule | `batch_number` |
| **RegisteredPlate** | `domain/inventory/registered_plate.py::RegisteredPlate` ✅ ws | `RegisteredPlateModel` → `registered_plates` | `GET /api/v1/plates` (global) | `plate_label` (fallback `barcode`) |

> ⚠️ **Campaign table is `campaign` (singular).** The link FK target and the migration must use
> `campaign`, not `campaigns`. The *URL collection* is still `campaigns` (see route map).

For reference, the already-wired four: Molecule filters via the **search-query composer**
(`_tag_clause` in `chemical_registration/_field_clauses.py`); Protocol & Project filter via the
**simpler repository `tags`/`tag_logic` params**. The four new entities follow the **repository
pattern** (their lists don't go through the composer).

---

## 4. Backend slice (per new entity) — the recipe

For each of Run, Campaign, Batch, RegisteredPlate, additive edits to existing files:

1. **Enum** — `domain/workspace_config/tagging/tag.py`, `TaggableEntityType`:
   add `RUN = "Run"`, `CAMPAIGN = "Campaign"`, `BATCH = "Batch"`, `PLATE = "Plate"`.

2. **Link table model** — `infrastructure/persistence/sqlalchemy/tagging/models.py`:
   add `RunTagLinkModel` (`run_tags`), `CampaignTagLinkModel` (`campaign_tags`),
   `BatchTagLinkModel` (`batch_tags`), `RegisteredPlateTagLinkModel` (`registered_plate_tags`).
   Each = `Base, TagLinkMixin` + `<entity>_id` FK (`ON DELETE CASCADE`, `primary_key=True`) +
   `tag_id` FK to `tags.id` (`ON DELETE CASCADE`, `primary_key=True`) + `Index("ix_<t>_tag_id", "tag_id")`.
   FK targets: `runs.id`, `campaign.id`, `batches.id`, `registered_plates.id`.

3. **Link repo subclass + registry** — `infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`:
   one 3-line subclass each (`link_model`, `entity_model`, `entity_id_attr`) + a `_REGISTRY` entry.
   Import `RunModel`, `CampaignModel`, `BatchModel`, `RegisteredPlateModel`. No method overrides
   needed (Molecule's `merged_into_id` override is Molecule-specific; the four new ones use the
   base `entity_exists_in_workspace`).

4. **Route map** — `interface/routes/tags.py`, `_ENTITY_COLLECTIONS`:
   add `"runs": RUN`, `"campaigns": CAMPAIGN`, `"batches": BATCH`, `"plates": PLATE`.
   The generic assignment router (`GET/POST/PUT/DELETE /api/v1/{collection}/{id}/tags`) then
   serves all four with no new route code. (`/api/v1/plates/{id}/tags` resolves to the generic
   tags router; `registered_plates.py` defines no `/tags` subroute, so no collision. Same for
   `/runs`, `/campaigns`, `/batches`.)

No new use cases — `AssignTag`/`UnassignTag`/`SetEntityTags`/`GetTagsForEntity` are already generic
over `TaggableEntityType`. Tagging is allowed even on **locked Runs / closed Campaigns** (tags are
orthogonal annotations, mirroring "tags allowed on locked Protocols").

---

## 5. List filtering — `tags` + `tag_logic` params

Each list endpoint gains `tags: list[UUID]` + `tag_logic: "any"|"all"` (default `any`), threaded
to the repository method, which calls `tag_filter_subquery(<LinkModel>, "<entity>_id", tags,
match_all=tag_logic=="all")` and constrains the main query to `id IN (subquery)` — exactly as
Protocol/Project do today.

| Entity | Endpoint / handler | Repo method to extend |
|--------|--------------------|------------------------|
| Run | `GET /protocols/{id}/runs` → `ListRunsWithCounts` | `RunRepository.find_by_protocol` |
| Campaign | `GET /campaigns?project_id=` → `ListCampaigns` | `CampaignRepository.find_by_project` / `find_by_workspace` |
| Batch | global inventory batch list | the global-batch read method (`list_global`) |
| RegisteredPlate | `GET /api/v1/plates` → `list_plates` | `RegisteredPlateRepository` list method |

Batch: **global list only** gets the filter (the natural workspace-wide surface). The per-molecule
batch list gets chips/editing on detail, not a filter. Run/Campaign filter inside their scoped
lists (E2).

---

## 6. Cross-entity tag-browse — the new surface

### 6.1 Backend (recommended approach A1: UNION-ALL read query with labels)

A new read repository builds a `UNION ALL` across all **eight** link tables; each branch JOINs its
entity table for a `label` expression and filters by `workspace_id` (every taggable entity is
workspace-scoped):

```
SELECT 'Molecule' AS entity_type, m.id AS entity_id, m.<label> AS label, l.assigned_at
  FROM molecule_tags l JOIN molecules m ON m.id = l.molecule_id
 WHERE l.tag_id = :tag_id AND m.workspace_id = :ws AND m.merged_into_id IS NULL
UNION ALL  -- protocol, project, collection, run (JOIN protocols for label), campaign, batch, registered_plate
```

- **Endpoint:** `GET /api/v1/tags/{tag_id}/entities?types=<csv>&cursor=&limit=` → list of
  `{entity_type, entity_id, label, assigned_at}`. Optional `types` filter (entity-type chips).
  **Auth: viewer.** Indexed by each table's `tag_id` index; one round-trip.
- **Read model:** `TagBrowseReadRepository.find_entities_for_tag(workspace_id, tag_id, types?, cursor, limit)`.
  Labels per §3 table; Molecule excludes tombstoned (`merged_into_id IS NULL`), matching the
  link-repo rule.
- **v1 = single-tag drill-in.** Multi-tag AND/OR is a trivial later extension (intersect/union the
  per-tag id sets) and is deferred.
- *Rejected (A2):* FE fans out to each list endpoint's `tags` param and merges — N calls, and
  Run/Campaign lack clean global list endpoints, so it doesn't generalize.

### 6.2 Frontend (recommended approach B1: dedicated `/tags` browse page)

- New **`/tags` browse page**: a `TagFilter`/tag-picker selects a tag → results **grouped by entity
  type**, each row a link to that entity's detail page (molecule → molecule detail, run → run
  detail, etc.). Reuses `TagChip` for the selected tag and the per-type grouping headers.
- **Admin drill-in:** the existing tag-management table (`/admin/tags`) usage counts become
  click-through to `/tags?tag=<id>` — discoverable entry, zero extra surface.
- *Rejected (B2/B3):* admin-only drill-in (browse is a viewer feature, not admin); folding into
  global search (heavier, conflates structured search with tag browse).

---

## 7. Persistence / Migration — one new migration (050)

`alembic/versions/050_tagging_expansion.py` (next after `049`):

1. **Create 4 link tables** — `run_tags`, `campaign_tags`, `batch_tags`, `registered_plate_tags`
   — reusing the `_create_link_table(name, id_col, ref_table)` helper shape from `047_tagging.py`
   (FK `ON DELETE CASCADE`, composite PK, `tag_id` index). FK ref tables: `runs`, `campaign`,
   `batches`, `registered_plates`.
2. **Recreate `tag_links_all`** — `DROP VIEW IF EXISTS tag_links_all` then `CREATE VIEW` unioning
   all **eight** tables, so cross-type usage counts (management page) and the browse fallback stay
   accurate.
3. **No backfill** — these entities have no legacy tag data (only `molecules.tags` existed, handled
   by 047). Migration is create-only and idempotent.
4. **Downgrade** — drop the 4 tables and restore the 4-table view.

---

## 8. Frontend wiring

- **`features/tagging/types.ts`** — `TaggableEntity` union `+= "runs" | "campaigns" | "batches" | "plates"`.
  (`useEntityTags`/`useAssignTag`/`useUnassignTag` are already generic — no hook changes.)
- **Detail editors (`TagTable`, `canEdit` gated on editor role):**
  - **Protocol** detail — overview/main tab (finish).
  - **Project** detail — overview tab (finish).
  - **Run** detail (`run-detail.tsx`, DetailShell) — metadata card.
  - **Campaign** detail — mount in the **shared header strip** so it shows in both the draft
    (`campaign-builder`) and closed (`campaign-view`) variants.
  - **Batch** detail (`batch-detail.tsx`, DetailShell) — metadata card.
  - **RegisteredPlate** detail (`plate-detail.tsx`, DetailShell) — metadata card.
- **List filters (`TagFilter`):** per-protocol Runs tab (`run-list.tsx`), per-project Campaign list
  (`campaign-list.tsx`), global Batch list (`GlobalBatchList`), Plate dashboard (`plate-list.tsx`,
  beside its existing type/status/format filters). (Protocol/Project lists already have it.)
- **Chips (`TagChip`)** on cards/rows where density allows (per the card-density rule: show N then `+k`).
- **New `/tags` browse page** + nav entry; admin usage-count click-through.
- **`orval` regen** for the new browse endpoint + response type. The generic assignment routes need
  no new generated types (already typed); regen is additive — review the `model/` diff.

---

## 9. Error handling

Railway `Result`, unchanged from the original: `NotFoundError` (entity/tag), `ValidationError`
(key rules), `AuthorizationError` (editor for assign/unassign/set; viewer for list/browse; admin
for rename/merge/delete). Workspace defense in every link op via the entity-exists subquery.
Assignment is idempotent (`on_conflict_do_nothing`); the browse endpoint returns an empty list for
an unknown/empty tag, not an error.

---

## 10. Testing strategy

- **Integration (per new entity):** link add/remove, `set_for_entity` reconcile, cascade-on-entity-delete,
  cross-workspace isolation, AND/OR/`tag_logic` filter on the entity's list.
- **Browse:** UNION correctness (all 8 types appear), correct per-type labels, workspace scoping,
  tombstoned-molecule exclusion, pagination, `types` filter.
- **API:** assign/unassign/set/list for `runs|campaigns|batches|plates` collections; auth split;
  filtered lists; browse endpoint (viewer auth, types filter, pagination).
- **E2E (Playwright):** tag a Batch → filter the inventory batch list by that tag → open `/tags`
  browse for the tag and confirm it surfaces the Batch *and* a same-tag entity of another type;
  finish-check that Protocol/Project detail editors assign/remove and reflect in the list filter.

---

## 11. Implementation sequencing (commit-sized; layer order)

1. **Backend foundation** — enum + 4 link models + 4 repo subclasses + `_REGISTRY` + route-map
   entries + **migration 050** (create tables + recreate view). + integration tests (links,
   cascade, isolation).
2. **List filtering** — `tags`/`tag_logic` params on the 4 list endpoints + repo methods + API tests.
3. **Cross-entity browse** — `TagBrowseReadRepository` + `GET /api/v1/tags/{id}/entities` + DI +
   tests; `orval` regen.
4. **FE detail editors** — finish Protocol/Project; add Run, Campaign, Batch, RegisteredPlate `TagTable`.
5. **FE list filters** — wire `TagFilter` into the 4 lists.
6. **FE browse page** — `/tags` page + nav + admin usage-count drill-in.
7. **E2E.**

---

## 12. Open items / risks

- **Run label** — runs have no `name`; use `"{protocol name} — {run date}"`. Requires the browse
  query's run branch to JOIN `protocols` (and a date format). Confirm the run-date field name.
- **Campaign detail variants** — draft (`campaign-builder`) vs closed (`campaign-view`); mount the
  editor in the shared header strip so both render it.
- **Batch route shape** — existing `GET /api/v1/batches/{molecule_id}` takes a *molecule* id; the
  tag route is `/api/v1/batches/{batch_id}/tags` (distinct depth, batch id) — unambiguous, but
  confirm the batch *detail* route resolves by batch id.
- **`campaign` singular table name** — easy to mistype as `campaigns` in the migration/FK; called
  out explicitly.
- **Browse multi-tag** — v1 is single-tag drill-in; AND/OR deferred.
