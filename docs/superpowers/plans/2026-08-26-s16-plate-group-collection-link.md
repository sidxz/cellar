# S16 — Plate group → Collection link — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optional `collection_id` on `PlateGroup` (any level), validated on write, names enriched on reads, a reverse read `GET /collections/{id}/plate-groups` with plate/loan counts, and the UI on the group dialog/page/tree card and the collection page.

**Architecture:** Mirrors S15: domain field + persistence + migration 070 + cascade rule (T1); write validation, read enrichment, reverse reader/use case/route (T2); regen; FE (T3). No backfill, no events.

**Spec:** `docs/superpowers/specs/2026-08-26-plate-group-collection-link-spec.md` — read it first.

## Global Constraints
Identical to `docs/superpowers/plans/2026-08-26-s15-run-plate-inventory-link.md` "Global Constraints" (read them): guidelines first, guards order, Railway, workspace scoping, ruff/pytest/biome/tsc commands, `DOCKER_HOST` for API/integration, generated types only, **subagents never commit**, exactly one migration `070_plate_group_collection` (revises `069_run_plate_registered_plate`).

## File map
| Task | Files |
|---|---|
| T1 domain + persistence | `domain/inventory/plate_group.py`; `infrastructure/persistence/sqlalchemy/inventory/models.py` (PlateGroupModel) + the plate-group repository file; `alembic/versions/070_plate_group_collection.py`; `infrastructure/cascade/rules_inventory.py`; tests: `tests/unit/domain/inventory/test_plate_group.py` (find the existing one), integration round-trip next to the existing plate-group repo test, `tests/unit/cascade` must stay green |
| T2 application + API | `application/inventory/plate_groups.py` (create/update/tree/detail), new `application/inventory/collection_plate_groups.py` (+ reader Protocol), `infrastructure/persistence/sqlalchemy/inventory/collection_plate_groups_reader.py`, `domain/research_organization/repository.py` (+ `find_by_ids` if missing) + its SA repo, `infrastructure/di/_screening.py` or `_inventory.py` (wherever the plate-group use cases are bound — `grep -n "CreatePlateGroup" src/cellar/infrastructure/di/*.py`), `interface/dependencies/*`, `interface/routes/plate_groups.py`, `interface/routes/collections.py`; tests: unit for create/update/list use cases, `tests/api/test_plate_group_collections.py` |
| T3 frontend | `features/inventory/hooks/use-plate-groups.ts`, `components/plate-group-dialog.tsx` (+test), `plate-group-page.tsx` (+test), `plate-group-card.tsx` (+test) and `plate-group-tree.tsx` (pass the inherited collection), the collection page component under `features/research-organization/components/` (find via `app/(dashboard)/collections/[id]/page.tsx`) + its test |
| T4 docs (orchestrator) | `docs/domain-model/03-inventory.md`, `05-research-organization.md` |

Waves: **W1** T1 · **W2** T2 · regen · **W3** T3.

---

### Task 1: Domain + persistence + migration 070 + cascade rule
- [ ] Failing tests: domain (`create` with `collection_id`, `update` sets/clears, sentinel untouched); integration round-trip (save a group with `collection_id` pointing at a seeded collection row, reload; clear, reload → NULL); `uv run pytest tests/unit/cascade -q` will fail until the rule exists.
- [ ] Implement: `PlateGroup.create/update` field (follow exactly how `storage_location_id` was added in S8 — same sentinel handling); `PlateGroupModel.collection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("collections.id", ondelete="SET NULL"))` + `Index("ix_plate_groups_collection", "collection_id")` in `__table_args__`; repo mapping in all three mapping methods; migration:

```python
def upgrade() -> None:
    op.add_column("plate_groups", sa.Column("collection_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_plate_groups_collection", "plate_groups", "collections",
                          ["collection_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_plate_groups_collection", "plate_groups", ["collection_id"])

def downgrade() -> None:
    op.drop_index("ix_plate_groups_collection", table_name="plate_groups")
    op.drop_constraint("fk_plate_groups_collection", "plate_groups", type_="foreignkey")
    op.drop_column("plate_groups", "collection_id")
```
  Cascade rule in `rules_inventory.py`: `CascadeRule(child_table="plate_groups", fk_column="collection_id", parent_table="collections", action=A.SET_NULL, label_field="name", display_label="Plate groups (collection link cleared)")`.
- [ ] Run: domain unit, integration round-trip, `tests/unit/cascade`; ruff.

### Task 2: Write validation, read enrichment, reverse read, routes, API tests
- [ ] Failing tests first (unit + `tests/api/test_plate_group_collections.py` per spec §6; build fixtures with the helpers in `tests/api/test_plate_groups.py` and `tests/api/test_plate_loans.py` — a plate on an open loan and one overdue loan via `_mk_loan` with a past `due_date`).
- [ ] Implement per spec §5–§6. Enrichment: collect every `collection_id` in the response (nodes, group, ancestors, children), `CollectionRepository.find_by_ids`, map names; the DTO classes `GroupTreeNodeResponse`, `PlateGroupResponse`, `GroupRefResponse` gain `collection_id: uuid.UUID | None = None`, `collection_name: str | None = None`. Reader SQL sketch:

```sql
WITH RECURSIVE up AS (            -- path for each linked group
  SELECT g.id AS root, g.id, g.parent_group_id, g.name, 0 AS depth FROM plate_groups g
   WHERE g.workspace_id = :ws AND g.collection_id = :cid
  UNION ALL SELECT up.root, p.id, p.parent_group_id, p.name, up.depth + 1
   FROM plate_groups p JOIN up ON p.id = up.parent_group_id
), down AS (                      -- subtree for each linked group
  SELECT g.id AS root, g.id FROM plate_groups g WHERE g.workspace_id = :ws AND g.collection_id = :cid
  UNION ALL SELECT down.root, c.id FROM plate_groups c JOIN down ON c.parent_group_id = down.id
)
SELECT root, string_agg(name, ' › ' ORDER BY depth DESC) AS path FROM up GROUP BY root;
SELECT down.root, count(rp.id) AS subtree_plates,
       count(*) FILTER (WHERE li.id IS NOT NULL) AS on_loan,
       count(*) FILTER (WHERE li.id IS NOT NULL AND l.due_date < current_date) AS overdue
  FROM down JOIN registered_plates rp ON rp.group_id = down.id
  LEFT JOIN plate_loan_items li ON li.plate_id = rp.id AND li.status IN ('requested','approved','checked_out','return_pending')
  LEFT JOIN plate_loans l ON l.id = li.loan_id AND l.status = 'open'
 GROUP BY down.root;
```
  (Write it with SQLAlchemy Core or `text()` — whichever the neighbouring readers use; check the real column/table names for loan items before trusting the sketch.)
- [ ] Route `GET /collections/{collection_id}/plate-groups` in `collections.py` with `ListPlateGroupsForCollectionDep`. Run unit + API tests; ruff.

### Task 3: Frontend (after regen)
- [ ] Failing tests per spec §7, then implement: dialog Collection field (`useCollections()` — read `collection-picker-dialog.tsx` for the list shape; a `SearchableSelect`/`SearchCombobox` from `shared/components` if one fits, else `Select` with a filter input), page row + inherited, card row + inherited (tree passes `inheritedCollection` computed from `hierarchyPointNode.parent` chain via `nodesById`), collection page "Physical plates" card with Request loan (`RequestLoanDialog initialGroupId`), hook `useCollectionPlateGroups`. Run vitest for the touched dirs, biome, tsc.

## Wrap-up (orchestrator)
`make migrate`; backend unit + API for touched modules; `pnpm generate:api`; W3; FE suite; browser check (link SAC1 → a collection, see the card, Request loan); commits backend + frontend (author panda-sas); review; sync note; push; #71.
