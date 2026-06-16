# SAR Unit B — frontend atomic swap to the server endpoints (+ server-side filtering)

**Status.** Brainstormed & approved 2026-06-15. Ready for `writing-plans`.
**Builds on.** Unit A (Part 2 backend — activity projection + heatmap + `/rows` activity) is **done on `design-7`**: the
endpoints below exist, are tested, and are CI-clean. This unit rewires the SAR workbench frontend to them.
**Parent design.** `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` §5 (frontend rework) + §8.3
(the AG-Grid `filterModel` → `/rows` `filter` mapping, which this unit designs **and builds**).

---

## 1. Why / the headline win

Today the SAR workbench computes everything client-side over `props.molecules` — the collection's **loaded 10K page**.
The table joins assignments → `props.molecules` (blank rows past the page), and `buildHeatmapGrid` aggregates over only
the loaded assignments (**silent under-count**: missing cells, wrong potency reference, wrong counts at >10K). Unit B
makes the table and heatmap **server-driven and correct over the full collection of any size**, with an honest
"rows 1–N of M matching" footer. The matched set against a chosen core is congeneric (naturally bounded), so this is
achievable without an absurd client.

**Atomic.** The old sync endpoint is gone (replaced in Unit A), so the SAR FE is currently broken against this backend —
table **and** heatmap must cut over together in one move. (Splittable only at the cost of temporary double-decomposition.)

---

## 2. The Unit-A endpoints this FE consumes (as built)

```
POST /api/v1/sar/decomposition                    {collection_id|molecule_ids, core_smiles}
   → 200 ready / 202 pending  {run_id, status, rgroup_labels[], matched_count, unmatched_count, total_count, error_message?}
GET  /api/v1/sar/decomposition/jobs/{run_id}       (poll, same shape)
POST /api/v1/sar/decomposition/jobs/{run_id}/cancel
POST /api/v1/sar/decomposition/{run_id}/rows       {offset, limit, sort:[{col,dir}], filter?, projection_id?}
   → {rows:[{molecule_id, smiles, registration_number, name, rgroups, mw, clogp, tpsa, activity?}], total}
POST /api/v1/sar/activity-projection               {collection_id|molecule_ids, channel}
   → 200 ready / 202 pending  {projection_id, status, value_count, error_message?}
GET  /api/v1/sar/activity-projection/jobs/{id}     (poll)
POST /api/v1/sar/activity-projection/jobs/{id}/cancel
POST /api/v1/sar/decomposition/{run_id}/heatmap    {axis_y, axis_x, projection_id}
   → {x_values[], y_values[], cells:[{y, x, count, best_scalar, best_molecule_id, best_molecule_label, best_snapshot}],
      y_total, x_total, truncated}
```

`channel` (= the server `ActivityChannelRequest`) is built from the FE's `SarColorSpec` + `AggregationMode`:
`{ column, source, intercept_key: interceptKey, selection_rule: aggregationModeToWire(aggMode), label,
   protocol_id: protocolId }` — `qualifier_handling`/`run_scopes` ride their defaults (the FE sends neither today).

**Regenerate orval first** (`pnpm generate:api`, backend up on `:8000`) so `model/` gains `DecompositionRunResponse`,
`ActivityProjectionResponse`, `HeatmapResponse`, the `projection_id`/`activity` row fields, and the channel request type.
Hooks remain **hand-written** against the generated types (the dominant convention) — never hand-roll a DTO shape.

---

## 3. Architecture — orchestration + the four hooks

`SarView` keeps its layout; the data path inverts. It now prefers **`collectionId`** (always present when SAR renders)
over `moleculeIds`, so analysis covers the **whole collection**, not the loaded page.

- **`useDecompositionRun({collectionId|moleculeIds, coreSmiles})`** — cloned from `useScaffoldTree` over `useJobPoll`:
  start (POST, cache-keyed, may return inline-ready or a 202 job) → poll `/jobs/{run_id}` → `{runId, labels, counts:
  {matched,unmatched,total}, status, error}`. Fires when a core is chosen.
- **`useActivityProjection({collectionId|moleculeIds, channel})`** — same job-poll shape → `{projectionId, status, error}`.
  Enabled only when a `colorSpec` is set; `channel` derives from `colorSpec` + `aggMode`.
- **`useDecompositionRows(runId, projectionId?)`** — returns an AG-Grid **`IDatasource`** whose
  `getRows({startRow, endRow, sortModel, filterModel, success, fail})` POSTs `/rows` with
  `{offset:startRow, limit:endRow-startRow, sort: sortModel.map(...), filter: agFilterModelToParam(filterModel),
  projection_id}` and calls `success(rows, total)`. Returns a **stable** datasource (memoized on `runId`/`projectionId`)
  so identity changes only when the run/projection changes.
- **`useHeatmapAggregation({runId, projectionId, axisY, axisX})`** — React-Query GET-style POST to `/heatmap`, keyed on
  `(runId, projectionId, axisY, axisX)` so axis re-swaps are instant from cache. Payload bounded (≤30×30 + `truncated`).

**Shared `DataGrid` — one additive prop.** `datasource?: IDatasource`. Present ⇒ `rowModelType="infinite"` +
`datasource={datasource}` + `rowData` omitted; absent ⇒ today's client-side `rowData`. Theme/columns/selection/empty-state
reused; **all existing consumers untouched**. This establishes the app's first infinite-row-model grid.

**`SarView` orchestration.** `core → useDecompositionRun`; `colorSpec → useActivityProjection`; pass
`runId`/`labels`/`counts`/`projectionId` into the table + heatmap. Counts banner is **honest by construction**
(`matched_count / total_count` from the server over the full set). Loading: "Decomposing…", "Computing activity…".

**Stable-ref footgun (call-out).** `runId`/`projectionId` (and the derived `job` objects) MUST be memoized stable refs
before entering datasource/poll deps — an inline-derived object recreates the datasource each render and resets the grid
(the same gotcha that caused the poll-storm + grid-thrash before). Mirror `useScaffoldTree`'s `useMemo(job, [startJob])`.

---

## 4. Server-side filtering (§8.3) — the one new design surface

AG-Grid Community exposes a `filterModel` on `getRows` (Text + Number filters; **Set filter is Enterprise**, so R-group
columns use a Text filter). A pure `agFilterModelToParam(filterModel)` maps it to an **AG-Grid-agnostic** contract; the
backend applies it. Filterable columns v1: **MW, cLogP, TPSA, activity** (numeric) · **registration_number, name, R1/R2/…**
(text).

```ts
// FE → wire
filter: { [colKey: string]: FilterClause }
type FilterClause =
  | { kind: "number"; op: "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"between"; value: number; value2?: number }
  | { kind: "text";   op: "contains"|"eq"|"startsWith"|"endsWith"|"neq"; value: string }
// colKey ∈ { molecular_weight, logp, tpsa, activity, registration_number, name, R1, R2, … }
```

AG-Grid → clause mapping (pure, unit-tested): text `contains/equals/startsWith/endsWith/notEqual` → the matching text
op; number `equals/notEqual/greaterThan(OrEqual)/lessThan(OrEqual)` → the matching op, `inRange` → `between` with
`value2 = filterTo`. Blank/unsupported entries are dropped.

**Backend (`decomposition_row_reader` + `decomposition_rows`).** Add a `filter: dict | None` to `FetchDecompositionRowsInput`
(the route already accepts a `filter` param — currently ignored). The reader builds WHERE conditions per clause:
numeric → the physchem molecule columns / the joined `activity` scalar (activity filter requires `projection_id`; ignored
otherwise); text → `registration_number`/`name` via `ILIKE` (`contains`→`%v%`, `startsWith`→`v%`, …) or `rgroups->>'Rn'`.
A central, lenient `_apply_filter(stmt, filter)` shared by **both `fetch_rows` and `count_rows`** so the `total` reflects
the filtered set (the footer reads "of N **matching**"). Unknown col/op → clause skipped (lenient, like the sort handling).
Workspace scoping + the `projection_id` ownership check are unchanged.

---

## 5. Delete / keep / new

**Delete** (work moved server-side or contract changed):
- `lib/rgroup-heatmap-grid.ts` `buildHeatmapGrid` + `rgroup-heatmap.tsx` local `bestMoleculeId` (server `/heatmap` aggregates).
- `rgroup-table.tsx` `buildRGroupRows` (the client `assignment ⋈ props.molecules` join — source of blank rows).
- `hooks/use-sar-activity.ts` (the `keyword_list`→search activity fetch).
- the old sync/inline-assignments contract of `hooks/use-rgroup-decomposition.ts`.

**Keep verbatim** (pure rendering, no scale dependence):
- `buildRGroupColumns` + `buildActivityColumns` + cell renderers (`StructureThumbnail`, `fragmentDisplay`, `AxisFragment`).
- `pickReference` / `potencyShade` / `snapshotFromActivity` + `colorSpecScalar` + `dr_curve`-only color gating.
- `RGroupColorControl`, `RGroupCorePicker` (collection-based, untouched), `CurveExpandDialog`, `SaveSelectionDialog`.
- `sar-fragment-label.ts`, `sar-core-candidates.ts`, `sar-color-spec.ts` (`colorSpecScalar`/`whereOptionToColorSpec`).

**New (FE):** the four hooks (§3); `agFilterModelToParam` (`lib/`); the `DataGrid` `datasource` extension. The table + heatmap
keep their renderers — only the data source changes. **Heatmap** reads cells from the server (`best_molecule_label` +
`best_snapshot` drive curve-expand off-set; `pickReference`/`potencyShade` compute the ramp from the small returned cells).
**Table** rows come from `/rows` (physchem/reg#/activity already joined server-side); `props.molecules` is no longer used by
the SAR table/heatmap (it stays for other view modes, so `collection-detail`'s load is unchanged).

**New (BE):** the filter handling in `decomposition_row_reader` + `decomposition_rows` (§4).

---

## 6. Save, states, testing (staging)

- **Save (Unit B):** keep the **row-checkbox** "Save selected (N)" over *loaded* rows — the existing create-collection →
  `POST /collections/{id}/molecules` path, unchanged. The server-side **"Save all N matched → collection"** stays in **Unit C**
  (it needs the new `/sar/decomposition/{run_id}/save-collection` endpoint). In infinite mode, selection spans only loaded
  rows; that's the documented Unit-B interim until Unit C's bulk save.
- **States (Unit B):** functional only — "Decomposing…" / "Computing activity…" spinners; empty (no core / no match),
  failed, and cancel handled enough to not break. The **honest-label copy polish** is Unit C.
- **Testing:**
  - Unit (vitest): `agFilterModelToParam` (text/number/inRange/blank); the four hooks via the existing
    `startFn`/`pollFn`/`decomposeFn`-override pattern (inline-ready, 202→poll→ready, failed, cancel); the `DataGrid`
    datasource branch (renders infinite when `datasource` present, client when absent).
  - Backend (pytest): extend `test_decomposition_row_reader` + the rows API test with filter cases (numeric range on
    physchem/activity, text contains on reg#/R-group) and **filtered-count** correctness; lenient drop of unknown clauses.
  - E2E (Playwright): core → run → channel → projection → table renders a server page + sorts + filters; heatmap renders
    server cells + axis swap + curve-expand. (May trim to a smoke E2E if the component/hook coverage is strong; deeper E2E
    can fall to Unit C.)

---

## 7. Cross-cutting / known boundaries

- **Full-collection behavior change (intended):** SAR now analyzes the whole `collectionId`, not `props.molecules`. The table
  paginates server-side ("rows 1–N of M matching"); the chemist scrolls and pages load. This is the headline correctness win.
- **No interim regression:** the old path is already gone; this unit restores SAR against the new backend in one cut.
- **Core picker boundary (documented, unchanged):** its coverage *suggestions* still sample the scaffold tree's 100K cap;
  decomposition over a *chosen* core is exact at any size. Out of scope (separate feature).
- **Orval regen hygiene:** regen is all-or-nothing for `model/`; review the diff; orval never prunes `model/index.ts` —
  remove any dangling barrel line by hand if a schema is dropped.

---

## 8. Locked decisions (brainstorm 2026-06-15)

1. **Server-side filtering is built in Unit B** (not deferred). Filterable v1: MW/cLogP/TPSA/activity (numeric) +
   registration_number/name/R-group (text). AG-Grid-agnostic `filter` contract (§4); BE applies it in `fetch_rows` **and**
   `count_rows`; lenient on unknown clauses. (User chose "build now" over defer / loaded-rows-only.)
2. **Atomic table + heatmap swap**; both cut to the server endpoints together; old client builders + `useSarActivity` deleted.
3. **`DataGrid` gains an additive `datasource` prop** (infinite when present); existing consumers untouched.
4. **Save-all-N + loading/empty/cancel copy polish + perf indexes stay in Unit C.** Unit B keeps the loaded-rows checkbox save
   and functional-only states.
5. **`props.molecules` is dropped from the SAR table/heatmap**; rows + heatmap cells + curve-expand snapshots come from the
   server. Stable memoized `runId`/`projectionId` refs feed the datasource/poll hooks (grid-reset footgun).
