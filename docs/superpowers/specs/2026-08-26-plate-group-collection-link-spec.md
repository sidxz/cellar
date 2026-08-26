# Spec: Plate group → Collection link (S16)

**Date:** 2026-08-26 · **Status:** APPROVED 2026-08-26 (user: "agreed on what you said. any group.")
**Contexts touched:** Inventory (03) — `PlateGroup`; Research Organization (05) — read only. Backend + frontend.
**Builds on:** `2026-08-25-plate-tracker-revamp-spec.md` §5 (group metadata), `2026-08-26-run-plate-inventory-link-spec.md` (S15 — same shape of change). Session **S16**.
**Tracking:** sidxz/cellar#71

## 1. Problem

A `Collection` says *which compounds* (abstract, project-scoped, drives run coverage "SACCZ 0/900"). A `PlateGroup` says *which physical containers, where, whose* (org-owned library › set tree, loans, kiosk). Nothing connects them, so a chemist screening a collection cannot find its plates or their custody, and a `hit_collection` set has lost the hit list it was plated from. Compound-level bridges (well maps → molecules) are phase 2 — the migrated fleet has no wells yet.

## 2. Decisions

| # | Decision |
|---|---|
| Link | `PlateGroup.collection_id: UUID \| None` — **optional**, allowed at **any level** (a library realizes "SACCZ"; a `hit_collection` set realizes "NadD hits"). FK → `collections.id` `ON DELETE SET NULL`, indexed. Many groups → one collection; one collection per group (a subset is its own collection). |
| Inheritance | Display only: a group without its own link is shown as "part of X (via Ancestor)" from the nearest linked ancestor. Nothing is stored. |
| Validation | On create/update the collection must exist in the workspace (`CollectionRepository.find_by_id_in_workspace`) → `NotFoundError("Collection")` 404 otherwise. No further visibility gate (matches `GetCollection`: viewer + same workspace). |
| Reverse read | `GET /collections/{collection_id}/plate-groups` → the groups (any level) linked to it that the caller may see (`PlateVisibilityService.can_view_owner`), each with counts; the collection itself must exist (404). |
| Names | Tree nodes, group detail (`group`, `ancestors`, `children`) carry `collection_id` **and** `collection_name` (one batched collection fetch per response) so the FE never fans out per group. |
| Events | `PlateGroupUpdated` unchanged; `collection_id` rides the existing create/update paths (`...` sentinel on update). |
| Cascade | Tier-2 `CascadeRule(child="plate_groups", fk="collection_id", parent="collections", SET_NULL)` in `rules_inventory.py` (FK owner declares it; `collections` is a Tier-1 parent — mirror the existing rule in `rules_research_organization.py:58`). |
| Not now | Auto-link by name (admin does it in the dialog; 17 libraries), plated-coverage / "create collection from group" / coverage-remaining → plates (all need well maps), run-page link-through. |

## 3. Domain — `domain/inventory/plate_group.py`
`create(..., collection_id: UUID | None = None)`, `update(..., collection_id: UUID | None = ...)` (sentinel convention as the S8 fields). Unit tests: create with/without; update sets and clears; sentinel leaves it alone.

## 4. Persistence
`PlateGroupModel.collection_id` (`ForeignKey("collections.id", ondelete="SET NULL")`, index `ix_plate_groups_collection` via `__table_args__`); repo `_to_domain`/`_to_model`/`_update_model`. Migration **070_plate_group_collection** (revises 069): add column, FK `fk_plate_groups_collection`, index; downgrade reverse. No backfill. Round-trip integration test. Cascade rule + `test_fk_coverage` green.

## 5. Application
- `CreatePlateGroup` / `UpdatePlateGroup`: accept `collection_id`; when non-null, load the collection (404). Unit tests: unknown → `Failure(NotFoundError)`; cross-workspace → 404; null clears.
- Enrichment: `GetGroupTree`, `GetPlateGroup` (and the create/update responses) resolve `collection_name` for every node/ref via `CollectionRepository.find_by_ids(ws, ids)` (add `find_by_ids` if the protocol lacks it — same shape as the plate repo's).
- `ListPlateGroupsForCollection(workspace_id, collection_id)` (`application/inventory/collection_plate_groups.py`): `require_workspace_role(viewer)` → `require_same_workspace` → collection exists (404) → `reader.groups_for_collection(ws, collection_id)` → filter `can_view_owner(g.owner_org_id, excluded)`. Reader Protocol `CollectionPlateGroupsReader`, row `CollectionPlateGroupRow(group_id, name, group_type, owner_org_id, path, plate_count, subtree_plate_count, on_loan_count, overdue_count)`; SA impl: groups with `collection_id = :id`; `path` = ancestor names + own joined " › " (recursive CTE up); `subtree_plate_count` = plates in the group's subtree (recursive CTE down); `on_loan_count` = those plates with an item in an ACTIVE status on an OPEN loan; `overdue_count` = same with `due_date < today` (`current_date`). Order by `path`.

## 6. API
| Route | Shape |
|---|---|
| `POST /plate-groups`, `PUT /plate-groups/{id}` | body `collection_id?: UUID \| null` |
| `GET /plate-groups/tree`, `GET /plate-groups/{id}` | nodes / `group` / `ancestors[]` / `children[]` gain `collection_id`, `collection_name` (nullable) |
| `GET /collections/{collection_id}/plate-groups` (in `collections.py`, calls the inventory use case) | `list[CollectionPlateGroupResponse{group_id, name, group_type, owner_org_id, path, plate_count, subtree_plate_count, on_loan_count, overdue_count}]` |

API tests `tests/api/test_plate_group_collections.py`: create with collection → response carries id+name; unknown collection → 404; update clears; tree + detail carry names (ancestor too); `GET /collections/{id}/plate-groups` lists a linked library and a linked set with correct counts (one plate on an open loan, one overdue), hides a foreign-org group from `editor_client_other_org`, 404 for an unknown collection. Cascade: deleting the collection nulls the link (assert via the DB or the group GET after the admin delete route).

## 7. Frontend
- orval regen (`PlateGroupResponse`, `GroupTreeNodeResponse`, `GroupRefResponse`, `Create/UpdatePlateGroupBody`, `CollectionPlateGroupResponse`).
- `plate-group-dialog.tsx`: **Collection** field — searchable select over `useCollections()` (name search client-side, same component family as the picker dialog), "None" option, explicit Save; sends `collection_id`.
- `plate-group-page.tsx` Details: **Collection** row → `Link /collections/{id}`; when unset and an ancestor is linked: `part of {name} · via {ancestor}` (muted, both linked).
- `plate-group-card.tsx` (tree): row `Collection · {name}` for own links; `part of {name}` (muted) inherited — the tree computes it by walking `hierarchyPointNode.parent` and looking ancestors up in `nodesById`.
- Collection page: **Physical plates** card — one row per group: `path` (link to the group page) · type badge · `n plates` (subtree) · `x on loan` (warning) · `y overdue` (destructive) · **Request loan** (editors; `RequestLoanDialog orgId=owner_org_id initialGroupId=group_id`; only when `subtree_plate_count > 0`). Empty: "No plate groups realize this collection yet — link one from a group's Edit dialog."
- Hook `useCollectionPlateGroups(collectionId)` in `features/inventory/hooks/use-plate-groups.ts`.
- Tests: dialog submits `collection_id`; page shows own + inherited rows; card shows own/inherited; collection card rows/empty/Request loan opens the dialog in group mode.

## 8. Docs
`docs/domain-model/03-inventory.md` (cross-context note gains the group→collection line), `05-research-organization.md` (Collection relationships: physical plate groups).

## 9. Out of scope
Everything under "Not now" in §2; many-to-many; deriving links from well maps.

## S16 sync note (2026-08-26) — shipped reality vs. §2–§8

- Shipped in `f72548c5` (backend + client), `e3706cd4` (frontend), `438d9fdf` (group loan requests cover the subtree), `51477aac` (review fix); plan `docs/superpowers/plans/2026-08-26-s16-plate-group-collection-link.md`, three tasks in three waves, one whole-branch review (**APPROVE WITH FIXES** → the recursive CTEs now carry `workspace_id` on every hop).
- Beyond the text: group detail `ancestors` are now full `GroupTreeNode`s (real `plate_count`/`plate_format`, plus `collection_*`); create/update return `SavedGroup(group, collection_name)` so routes never touch repos; the reader Protocol lives with its use case in `application/inventory/collection_plate_groups.py`; the tree's root node also shows `Collection · {name}`; `0 on loan` is hidden like `0 overdue`; an `UNSET` update re-resolves the existing link's name without re-validating it (a stale link shows `collection_name: null`, not 404).
- **Group-mode loan requests stay direct-members-only (user ruling 2026-08-26, `5f59f317`).** While verifying, "Request loan" on a library root (0 direct plates, 832 below) answered 422 "Group has no plates"; `438d9fdf` briefly made a group request sweep the subtree, and the user reverted that: *a loan is of a set* — people request the group that holds the plates, and that habit is the default. The UI is made honest instead: "Request loan" renders only where the group itself holds plates (tree card, group page header, collection card); the dialog's group labels show direct counts and the copy reads "Requests every plate directly in the selected group — sub-groups are loaned separately." API test `test_by_group_id_is_direct_members_only` pins it.
- Migration 070 applied to the local dev DB. Suites: backend unit 3125 passed (2 known pre-existing failures), 189 unit + 121 API in the touched areas, 63 loan API tests; frontend **1123 passed**, tsc/biome clean. Browser-verified on saclab-dev: Edit SAC1 → Collection picker → save → Details row `Collection · My Collection 1`; collection page card `SAC1 · 832 plates · 9 on loan · 9 overdue · Request loan` → dialog opens in group mode pre-selected; test link removed afterwards.
- Residuals: label matching/auto-link by name not built (17 libraries are linked by hand); compound-level bridges wait for well maps (§2 "Not now").
