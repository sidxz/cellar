# SAR Unit C · Item 1 — Server-side "Save all N matched → collection" (design)

**Created:** 2026-06-15 · **Branch:** `design-7` · **Slice of:** `docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md` (item 1).

## Problem
The SAR table's "Save as collection" only saves the **selected/loaded** rows
(`SarView` → `SaveSelectionDialog` → create-collection + bulk-add by id). Over a
full collection of any size the chemist can't save *all* matches — or all matches
under the current column filter — without scrolling every page.

## Decisions (approved 2026-06-15)
- **Filter-aware, single button.** The saved set equals exactly what the table
  shows. No filter → "Save all N matched"; column filter active → "Save N
  filtered". The live `filterModel` (and `projection_id`, when an activity filter
  is in play) is sent so the saved set honors it.
- **Orchestration A (reuse).** The new use case reuses the existing
  `CreateCollection` + `AddMoleculesToCollection` use cases (uuid refs), mirroring
  today's two-call FE flow moved server-side — full auth/event reuse. Partial
  failure = "empty collection created", same mode as today's FE two-call path.
  (Rejected B: drop to `CollectionRepository.add_molecules` in one UoW for
  atomicity — reimplements creation, skips resolver/events.)
- Per-row selection save **stays** (unchanged path).

## Backend

### Reader — `fetch_matched_ids`
`infrastructure/.../sar_analysis/decomposition_row_reader.py` + the
`DecompositionRowReader` Protocol in `application/.../decomposition_rows.py`.

```python
async def fetch_matched_ids(
    self, run_id: UUID, *, workspace_id: UUID,
    projection_id: UUID | None = None, filter: dict[str, Any] | None = None,
) -> list[UUID]: ...
```
Mirrors `count_rows` exactly but `select(RGroupAssignmentModel.molecule_id)` —
reuses `_scoped_join` + `_activity_join` + `_apply_filter`, so the id set is
identical to what `count_rows`/`fetch_rows` return for the same
`(filter, projection_id)`. One row per molecule per run (same invariant the rows
query relies on); no `DISTINCT` needed.

### Use case — `SaveDecompositionCollection`
New `application/sar_analysis/save_decomposition_collection.py`.

Input: `run_id, workspace_id, requested_by, name, project_id?, filter?, projection_id?`.
1. Load run (workspace-scoped) → `NotFoundError("RGroupDecompositionRun", …)` if missing.
2. If `projection_id` given, validate projection ownership (workspace-scoped) →
   `NotFoundError("SarActivityProjection", …)`. Mirrors `FetchDecompositionRows`;
   keeps the activity-filter join tenant-safe.
3. `ids = reader.fetch_matched_ids(run_id, workspace_id=…, projection_id=…, filter=…)`.
4. Reuse `CreateCollection` → new collection (`type="generic"`, default visibility,
   `created_by=requested_by`, `project_id`).
5. Reuse `AddMoleculesToCollection` with `refs=[MoleculeReference(str(id), RefType.UUID) …]`.
6. Return `collection.id` (wrapped `Result`).

DI: register the use case; both reused use cases are already wired. `require_editor`
is enforced transitively by the reused use cases.

### Route
`POST /api/v1/sar/decomposition/{run_id}/save-collection` in
`interface/routes/sar_analysis.py`.

- Request `SaveCollectionRequest { name: str, project_id: UUID | None = None,
  filter: dict[str, Any] | None = None, projection_id: UUID | None = None }`.
- Reject empty `name` (`400`).
- Pass `auth` (AuthDep) through to the use case (forwarded to the reused use cases
  for `require_editor` / `require_same_workspace`).
- Response `SaveCollectionResponse { collection_id: UUID }`.
- New `SaveDecompositionCollectionDep` in `interface/dependencies/_sar_analysis.py`.

## Frontend

### `useDecompositionRows` — expose live filter + total
`features/sar-analysis/hooks/use-decomposition-rows.ts`. Inside `getRows`, also
`setFilterParam(body.filter)` and `setTotal(res.total)`; return
`{ datasource, activityReference, filterParam, total }`. Same no-refetch pattern
as the existing `setActivityReference` (datasource stays memoized on
`[runId, projectionId, fetchFn]`).

### New hook — `useSaveDecompositionCollection`
`features/sar-analysis/hooks/use-save-decomposition-collection.ts`. Hand-written
`customInstance` POST to the new route (FE convention), reusing the orval-generated
request/response types; `fetchFn` injection seam for the unit test.
Signature: `saveAll({ runId, name, projectId, filter?, projectionId? }) → { collection_id }`.

### `SaveSelectionDialog` — name/project collector
`features/sar-analysis/components/save-selection-dialog.tsx`. Refactor to:
- take `count: number` (drives title + save-gating) instead of deriving from
  `selectedMolecules.length`;
- take an **optional** `preview?: MoleculeLite[]` (render the preview grid only
  when provided);
- `onSave({ name, projectId })` — drop `moleculeIds` (the caller owns "what to
  save").
The existing per-selection path passes its rows as `preview` and keeps its id list
in `SarView` state.

### `RGroupTable` — always-visible toolbar action
`features/sar-analysis/components/rgroup-table.tsx`. Use `DataGrid`'s existing
`toolbarActions` slot (rendered even in empty/loading states):
- `filterActive = !!filterParam && Object.keys(filterParam).length > 0`.
- `count = total ?? matchedCount ?? null` (new `matchedCount?: number` prop from
  `SarView` for the pre-first-page baseline).
- Label: `filterActive ? "Save {count} filtered" : "Save all {count} matched"`.
- Disabled when `count` is null or `0`.
- Click → `onSaveAll({ count, filter: filterActive ? filterParam : undefined, projectionId })`.

### `SarView` — discriminated save intent
`features/sar-analysis/components/sar-view.tsx`. `saveIntent` becomes:
```ts
type SaveIntent =
  | { mode: "selection"; rows: SaveRow[] }
  | { mode: "all"; count: number; filter?: Record<string, unknown>; projectionId?: string | null };
```
`onSave` switches: `selection` → today's `createCollection` + add-by-id;
`all` → `useSaveDecompositionCollection`. Both reuse the one dialog (passing
`count` and, for selection, `preview`). Pass `matchedCount={run.counts?.matched}`
and `projectionId` to `RGroupTable`.

## Edge cases
- Filter → 0 matches ⇒ button disabled ("Save 0 filtered").
- No projection / no colorSpec ⇒ `projection_id` omitted; filter carries only
  physchem/rgroup/name (activity column isn't shown without a colorSpec).
- Activity-column filter ⇒ `projection_id` sent so the saved set honors it.
- Partial failure (collection created, add fails) ⇒ surface a retry toast (parity
  with today's selection path).

## Tests (TDD)
**Backend**
- Reader integration (`tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`):
  `fetch_matched_ids` — all ids (no filter); text + number filter; activity filter
  + projection; workspace/merged scoping; empty result.
- API (`tests/api/test_sar_analysis_routes.py`): save-collection happy path
  (collection + members created, returns `collection_id`); filtered subset;
  activity-filtered subset (with `projection_id`); `404` unknown run; `404`
  unknown projection; `400` empty name; workspace isolation.

**Frontend**
- `use-decomposition-rows` — exposes `filterParam` + `total` after a `getRows` call.
- `use-save-decomposition-collection` — posts the correct body, returns `collection_id`
  (via `fetchFn` seam).
- `save-selection-dialog` — `count` + optional-`preview` modes (title, save-gating).
- Full component render-flow stays **deferred to the E2E** (handoff item 6).

## Out of scope
Perf indexes (item 2), navigation-to-new-collection after save (applies to both
paths; revisit separately), E2E (item 6).
