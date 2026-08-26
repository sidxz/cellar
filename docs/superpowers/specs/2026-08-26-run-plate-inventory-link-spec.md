# Spec: Run plate ↔ inventory plate link (S15)

**Date:** 2026-08-26 · **Status:** APPROVED 2026-08-26 (user: "yes lets do that and build the UI for it — registered_plate_id, optional, not mandatory")
**Contexts touched:** Screening & Assay (02) — `Run.Plate`; Inventory (03) — read model + resolver. **Backend + frontend.**
**Builds on:** `2026-08-25-loans-plates-ux-pass-spec.md` (S13–S14). Session **S15**.
**Tracking:** sidxz/cellar#71

## 1. Problem

Inventory plates (`RegisteredPlate`, table `registered_plates`) and run plates (`Run.Plate`, table `plates`) are unrelated today: no FK, no barcode join, nothing in `application/screening` ever looks a run plate up in inventory. Consequences: a loan says nothing about which run the plate went into; an inventory plate cannot show "used in runs"; a run plate cannot reach the physical plate. The run-file import stores the file's plate name in `plates.plate_map->>'name'` (e.g. `SAC3-014-3070`) and leaves `plates.barcode` NULL; plate setup creates plates with neither.

## 2. Decisions

| # | Decision |
|---|---|
| Link | `Run.Plate.registered_plate_id: UUID \| None` — **optional**, FK → `registered_plates.id` `ON DELETE SET NULL`, indexed. Never required; nothing else changes meaning when it is null. |
| Resolution | One helper, `resolve_plate_reference(repo, ws, raw)`: the existing barcode chain (`resolve_barcode`: exact → zero-pad-to-6 → strip-leading-zeros) **then** exact `plate_label` match, accepted only when exactly one plate carries that label. Same helper for import auto-link and manual link. |
| Visibility | A link is only made to a plate the actor may view (`PlateVisibilityService.can_view` with the borrowed carve-out; `auth=None` worker calls see everything). Hidden == "not found" (404) on manual link. The plate-map read does **not** filter linked details — the run already exposes the file's plate name; the link target (`/inventory/plates/{id}`) enforces visibility itself. Recorded residual. |
| Auto-link | Run-file import: every **new** plate it creates is resolved by its file name (`plate_map.name`); a miss leaves the link null and is not an error. Plate setup (no name) never auto-links. |
| Manual link | `POST /runs/{run_id}/plates/{plate_id}:link {barcode}` / `:unlink`. Editor, same workspace, run must not be locked (`ConflictError` **409** — the existing `Run._guard_not_locked` convention shared by every locked-run mutation; the spec's first draft said 423). `barcode` accepts a barcode **or** a plate label (same helper). Relinking overwrites. |
| Backfill | Migration **069** back-fills existing rows in SQL: exact `plates.barcode` = `registered_plates.barcode`, else `plates.plate_map->>'name'` = `registered_plates.plate_label`, same workspace as the run, only when exactly one candidate matches. `ponytail:` no zero-pad variants in SQL — the app resolver covers new links; re-run the statement by hand if ever needed. |
| Reads | `PlateData` (run plate map) gains `registered_plate_id`, `registered_plate_barcode`, `registered_plate_label` (null when unlinked). New `GET /plates/{plate_id}/runs` → runs that carry this plate, newest first; plate visibility enforced (hidden == 404). |
| Events | None new. `Run.update` registers no event today; `link_plate` follows it. Audit is unchanged. |
| Delete | Deleting an inventory plate nulls the link (FK `SET NULL`); deleting a run cascades its plates as before. |

## 3. Domain — `domain/screening_assay/run.py`

- `Plate.__init__(..., registered_plate_id: uuid.UUID | None = None)`; attribute `self.registered_plate_id`.
- `Run.link_plate(plate_id: uuid.UUID, registered_plate_id: uuid.UUID | None) -> None`: `_guard_not_locked()`; the plate must belong to this run (`NotFoundError("Plate", str(plate_id))` otherwise); sets the field; bumps `updated_at`. `None` unlinks.
- Unit tests in `tests/unit/domain/screening_assay/test_run.py`: link, unlink, unknown plate → NotFoundError, locked run → DataLockedError.

## 4. Persistence

- `PlateModel.registered_plate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("registered_plates.id", ondelete="SET NULL"), index=True)`.
- `SQLAlchemyRunRepository`: `_to_domain` and `_plate_to_model` carry the field (the repo rebuilds plate rows from the aggregate on update, so that is the whole write path).
- `PlateMapReader` (`infrastructure/.../plate_map_reader.py`): `PlateMapData` gains the three fields; one extra `select(RegisteredPlateModel.id, .barcode, .plate_label).where(id.in_(linked_ids))` per run.
- Migration `069_run_plate_registered_plate` (revises 068): add column, FK `fk_plates_registered_plate` (`ON DELETE SET NULL`), index `ix_plates_registered_plate`, then execute the module-level `BACKFILL_SQL`:

```sql
WITH candidates AS (
  SELECT p.id AS plate_id, rp.id AS registered_plate_id
  FROM plates p
  JOIN runs r ON r.id = p.run_id
  JOIN registered_plates rp ON rp.workspace_id = r.workspace_id
   AND (rp.barcode = p.barcode OR rp.plate_label = p.plate_map->>'name')
  WHERE p.registered_plate_id IS NULL
), unique_candidates AS (
  SELECT plate_id, MIN(registered_plate_id::text)::uuid AS registered_plate_id
  FROM candidates GROUP BY plate_id HAVING COUNT(*) = 1
)
UPDATE plates p SET registered_plate_id = u.registered_plate_id
FROM unique_candidates u WHERE u.plate_id = p.id;
```

- Downgrade drops index, FK, column. Integration test `tests/integration/test_migration_069_backfill.py` loads the migration module by path, inserts a run plate + matching/ambiguous registered plates, executes `BACKFILL_SQL`, asserts the unique match links and the ambiguous one stays NULL. Round-trip of the field is asserted in `tests/integration/test_run_repository_find_by_ids.py` (or a sibling).

## 5. Application

### 5.1 `application/inventory/plate_reference.py`
```python
async def resolve_plate_reference(repo: RegisteredPlateRepository, workspace_id: UUID, raw: str) -> RegisteredPlate | None
```
`resolve_barcode(repo, ws, raw)` first; else `repo.find_by_label(ws, raw.strip())` and return the plate only when that list has exactly one element. `RegisteredPlateRepository.find_by_label(workspace_id, label) -> list[RegisteredPlate]` is added to the protocol and the SA repo (exact match) and to the in-memory fake used by unit tests.

### 5.2 `application/screening/link_run_plate.py`
- `LinkRunPlateCommand(workspace_id, run_id, plate_id, barcode: str)` → `LinkRunPlate(uow, run_repo, plate_repo, visibility, dispatcher)`: `require_authenticated` → `require_editor` → `require_same_workspace` → load run (404 `Run`) → `resolve_plate_reference` → `visibility.can_view(plate, auth, excluded, borrowed)` else `NotFoundError("RegisteredPlate", barcode)` → `run.link_plate(plate_id, plate.id)` → save → commit → dispatch. Returns `RunPlateLink(plate_id, registered_plate_id, barcode, plate_label)`.
- `UnlinkRunPlateCommand(workspace_id, run_id, plate_id)` → `UnlinkRunPlate(uow, run_repo, dispatcher)`: same guards → `run.link_plate(plate_id, None)`.
- Unit tests with `FakeAuth` + in-memory fakes: success (barcode / zero-padded / label), unknown → NotFound, hidden foreign-org plate → NotFound, locked run → DataLockedError, wrong plate → NotFound, viewer → AuthorizationError.

### 5.3 Import auto-link — `application/screening/import_plan.py` (+ its caller)
Where a new `Plate(... plate_map={"name": plate_name})` is created, resolve `plate_name` through `resolve_plate_reference` (visibility-checked with the importing auth) and pass `registered_plate_id=`. The plan builder gains the plate repo + visibility as explicit parameters wired from the import use case's DI; misses are silent. Unit test: a file plate whose name equals a registered plate's label comes out linked; a miss stays null.

### 5.4 `application/inventory/list_runs_for_plate.py`
`ListRunsForPlateQuery(workspace_id, plate_id)` → `ListRunsForPlate(uow, plate_repo, visibility, reader)`: `require_workspace_role(auth, "viewer")` → `require_same_workspace` → load plate + `can_view` (borrowed carve-out) else 404 → `reader.runs_for_plate(ws, plate_id)`. `PlateRunsReader` Protocol in `application/inventory/plate_runs_reader.py`; SA impl `infrastructure/persistence/sqlalchemy/inventory/plate_runs_reader.py` joining `plates → runs → protocols`, returning `PlateRunRow(run_id, run_date, run_status, protocol_id, protocol_name, plate_number, created_at)` ordered by `runs.created_at DESC`. Runs have no name column; `run_date` is the run's identity (the run page titles itself `Run {run_date}`).

## 6. API

| Route | Body → Response |
|---|---|
| `POST /api/v1/runs/{run_id}/plates/{plate_id}:link` (in `plate_setup.py`) | `{barcode: str}` → 200 `RunPlateLinkResponse{plate_id, registered_plate_id, barcode, plate_label}` |
| `POST /api/v1/runs/{run_id}/plates/{plate_id}:unlink` | — → 200 `RunPlateLinkResponse{plate_id, registered_plate_id: null, barcode: null, plate_label: null}` |
| `GET /api/v1/plates/{plate_id}/runs` (in `registered_plates.py`) | → `list[PlateRunResponse{run_id, run_date, run_status, protocol_id, protocol_name, plate_number, created_at}]` |
| `GET /api/v1/runs/{run_id}/plate-map` | `PlateData` + `registered_plate_id`, `registered_plate_barcode`, `registered_plate_label` |

API tests `tests/api/test_run_plate_links.py`: link by exact barcode, by zero-padded barcode, by label; unknown → 404; hidden foreign-org plate → 404 (`editor_client_other_org`); locked run → 409; relink overwrites; unlink; plate-map carries the fields; `GET /plates/{id}/runs` lists the run once and 404s for a hidden plate; viewer cannot link (403).

## 7. Frontend

- `pnpm generate:api` after the backend lands (review the `model/` diff; barrel never prunes).
- `features/screening-assay/hooks/use-plate-setup.ts`: `useLinkRunPlate(runId)` / `useUnlinkRunPlate(runId)` mutations (invalidate `PLATE_MAP_KEY`), success toasts "Plate linked" / "Plate unlinked".
- `features/screening-assay/components/run-plate-link.tsx` — `RunPlateLink({ runId, plate, readOnly })`: linked → `<Link href="/inventory/plates/{registered_plate_id}">` showing the barcode (label muted after it) + an `Unlink` ghost button (hidden when `readOnly`); unlinked → `Link plate` ghost button → `Dialog` with one input "Barcode or plate name" → link mutation; errors via the global toast. Rendered in the plate header of `run-data-panel.tsx` (interactive) and `run-heatmap-panel.tsx` (`readOnly`). `readOnly` is also forced when the run is locked or the viewer cannot edit (`useCanEdit`).
- `features/inventory/hooks/use-plates.ts`: `usePlateRuns(plateId)`.
- `plate-detail.tsx`: **Used in runs** card, right column above History: one row per run — protocol name · `Run {run_date}` · `Plate n` · `StatusBadge(run_status)` — the row links to `/assays/runs/{run_id}`; empty copy "Not used in any run yet."
- Tests: `run-plate-link.test.tsx` (linked renders link + unlink posts `:unlink`; unlinked opens dialog and posts `:link` with the typed value; `readOnly` hides controls); `plate-detail.test.tsx` gains the runs-card case.

## 8. Docs
`docs/domain-model/02-screening-assay.md` Plate table: add `registered_plate_id | UUID? | FK → RegisteredPlate (inventory) — optional physical-plate link`. `03-inventory.md`: one line under RegisteredPlate relationships.

## 9. Out of scope
Pre-filling a run's plate map from the inventory `well_map`; linking from the loan/kiosk flows; a run-side picker that browses inventory (the input takes a barcode/name, per the no-UUID-inputs rule); per-org filtering of linked details on the plate-map read (residual above).
