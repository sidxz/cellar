# SAR full-collection coverage — server-side, unbounded R-group decomposition

**Status.** Brainstormed & approved 2026-06-11. Ready for `writing-plans`.
**Supersedes the framing of** backlog #1 ("full-collection coverage", `docs/backlog/sar-workbench-frontend-followups.md`) and Sub-project 1 of `docs/superpowers/specs/2026-06-11-sar-phase2-handoff.md`.
**Branch context:** `design-6` (SAR Phase-1 + core-selection refinement shipped here).

---

## 1. Why this is bigger than the backlog implied

The backlog item read as a small frontend wiring fix ("analyze the whole collection, not a page"). Exploration on 2026-06-11 showed the premise was stale and the real ask, once pushed on, re-scopes to a **large full-stack feature**. The verified findings:

- **SAR is hosted in exactly one place — `collection-detail.tsx`**, which loads members via `useCollectionSearch` (default `limit = 10_000`). So `props.molecules` is the **10K-capped full collection**, never a 50-row page. The `// visible page from the host` comment in `sar-view.tsx` is stale; `collectionId` is **always present** when SAR renders.
- **Decomposition** already supports `collection_id` in the hook (`use-rgroup-decomposition.ts`); only the `SarView` `useEffect` still passes `moleculeIds`. The route already expands `collection_id` → `COLLECTION_EXPANSION_LIMIT` (100K).
- **Activity** (`use-sar-activity.ts`) posts a `keyword_list` of explicit ids — no collection path — and is the layer the heatmap aggregates over.
- **Table/heatmap render from `props.molecules`.** `buildRGroupRows` joins assignments → `props.molecules` by id for structure + reg# + MW/cLogP/TPSA (the decomposition response carries none of that); `byId.get()` + `?? null` ⇒ any molecule beyond the loaded set is a **blank row**. The heatmap `buildHeatmapGrid` aggregates over **all** assignments and `pickReference` anchors color across **all** cells — so at >10K it **silently under-aggregates** (missing cells, wrong potency reference, wrong counts). That silent-under-count is the real bug, not blank rows.

**Decisions taken during brainstorming (the user chose the maximal option at each fork):**

1. **>10K behavior →** *full fidelity at any size* (not "accept the 10K cap with honest labeling").
2. **Size ceiling →** *don't assume one* — reinterpreted as its honest intent: **aggregates must never silently lie; the table must always be honest about what it shows.**
3. **Scope →** *fully unbounded*: server-aggregated heatmap + async decomposition job + server-paginated table. (Over "materialize-to-100K-ceiling" and over "hybrid".)

This is comparable in size to the activity-cliffs sub-project. R-group decomposition is *semantically* a focused-series tool (it needs a common core; a diverse library has no shared scaffold), so while the **collection** is unbounded, the **matched set against a core** is naturally bounded by congeneric chemistry — which is why "unbounded" is achievable without an absurd build.

---

## 2. Architecture

A collection of any size + a chosen core + an activity channel feed **three server-computed surfaces, each with a bounded payload**. The client never holds the full matched set.

```
 collection_id (any N) ──┐
            core_smiles ──┼─▶  Decomposition Run   (async job, Temporal rails)
                          │      persists assignment ROWS, returns labels + counts
       activity channel ──┼─▶  Activity Projection (async, materializes 1 scalar/mol)
                          │      persists {mol_id → scalar,unit,snapshot} for the channel
                          ▼
   Counts/coverage → scalars (bounded)
   Table           → SQL page: assignment ⋈ molecules ⋈ activity_value   (AG Grid Infinite Row Model)
   Heatmap         → SQL GROUP BY axisY,axisX over activity_value         (bounded by # substituent combos)
```

**The one deliberate divergence from the scaffold-tree pattern.** Scaffold-tree stores its whole result as a JSONB **blob** in the job row (fine — a scaffold tree is small). R-group **assignments scale with collection size**, so a blob can't be paginated or aggregated without loading all of it. Therefore assignments are persisted as **queryable rows**, and the table/heatmap become **SQL queries** (paginate / `GROUP BY`) over them. Everything else mirrors scaffold-tree exactly (job state machine, Temporal orchestrator + Null fallback, id-hash cache, poll route).

**Two decoupled compute steps, not one.** Activity must be *materialized* (it is a Python service, not a SQL column — see §4), and the chemist swaps the color channel without re-decomposing. So:
- **Decomposition run** — keyed by `(membership_hash, core_hash)`. Produces assignment rows + labels + counts.
- **Activity projection** — keyed by `(membership_hash, channel_hash)`, **independent of the core**. Materializes one scalar per molecule so SQL can `ORDER BY` / `GROUP BY` it. Reused across cores; recomputed only when the channel changes. This is also the seam the **activity-cliffs** project will reuse.

This split mirrors how the FE already behaves (core first, channel swapped independently), so it is faithful, not invented.

**Cache invalidation is implicit and version-aware.** `membership_hash = SHA-256` of sorted `(molecule_id, version)` pairs — not just ids. A merge or structure-correction bumps a member's `version` ⇒ new hash ⇒ automatic cache miss ⇒ recompute. This fixes the staleness caveat the id-only scaffold-tree cache documents, at zero cost, and removes the need for explicit invalidation handlers (simpler than MMP's design).

---

## 3. Persistence model

Four tables in two header+rows pairs. Each **header is a DDD aggregate** with scaffold-tree's state machine (`pending→running→ready/failed/cancelled`, `version` optimistic lock). Each **rows table is the aggregate's persisted result projection** (a read-model the repo writes when marking the job ready — not a blob). All carry `workspace_id`.

### Pair 1 — Decomposition (keyed by membership + core)

```
rgroup_decomposition_run                 -- aggregate / job header + cache row
  id, workspace_id, requested_by
  membership_hash  TEXT  idx             -- SHA-256 of sorted (molecule_id, version) pairs
  core_smiles      TEXT                  -- core as drawn
  core_hash        TEXT  idx             -- SHA-256 of RDKit-canonical core (+ fixed RGD opts)
  status, requested_at, started_at, completed_at, error_message
  rgroup_labels    JSONB                 -- ["R1","R2"]  (small)
  matched_count, unmatched_count, total_count  INT
  version
  PARTIAL INDEX (membership_hash, core_hash, completed_at DESC) WHERE status='ready'

rgroup_assignment                        -- result projection (the unbounded part)
  run_id  FK→run (ON DELETE CASCADE), molecule_id, rgroups JSONB   -- {"R1":"…","R2":"…"}
  PK (run_id, molecule_id)
```

### Pair 2 — Activity projection (keyed by membership + channel, core-independent)

```
sar_activity_projection                  -- aggregate / job header + cache row
  id, workspace_id, requested_by
  membership_hash  TEXT  idx             -- same hash as above (reused across cores)
  channel_hash     TEXT  idx             -- SHA-256 of normalized SarColorSpec
  channel_spec     JSONB                 -- protocol_columns + aggregation + run_scopes
  status, timestamps, error, version
  PARTIAL INDEX (membership_hash, channel_hash, completed_at DESC) WHERE status='ready'

sar_activity_value                       -- result projection (SPARSE — only mols with data)
  projection_id FK (CASCADE), molecule_id, scalar FLOAT, unit, qualifier,
  source TEXT, snapshot JSONB            -- snapshot feeds curve-expand on click
  PK (projection_id, molecule_id)
```

### Key decisions
- **Matched rows only; unmatched is a count, not a million rows.** Header carries `unmatched_count`; "which didn't match" is an on-demand set-difference (members − matched), not stored. Honors "surfaced, never silently dropped" without unbounded storage.
- **Activity rows are sparse** — only molecules with a value; missing ⇒ `LEFT JOIN` null ⇒ heatmap gap / uncolored cell, exactly as today.
- **Activity keyed by membership, not run** — genuinely core-independent; swapping cores reuses it.
- **Membership streamed in batches** (~10K/page, CDD-import style) when expanding a collection, so a >100K collection isn't blocked by the single-fetch `COLLECTION_EXPANSION_LIMIT`; the hash is folded incrementally over the stream.

---

## 4. Backend compute & endpoints

**Two job lifecycles, each a copy of scaffold-tree's:** `start_*` (cache check → inline if ≤~500 members else 202+job) → `run_*` (mark running → compute → mark ready/failed) → `get` poll + `cancel`. Temporal orchestrator in prod, Null asyncio fallback in dev. No new job machinery — two new job types.

**Decomposition compute (`RunDecomposition`):**
1. Job input carries `collection_id` (**not** the expanded id list — passing ~1M ids through Temporal history is the anti-pattern; re-expand at run time). Ad-hoc explicit sets carry their bounded id list.
2. **Prepare a labeled core once** — fix the core's attachment-point labels up front so RDKit `RGroupDecomposition` yields **stable labels across batches**. Without a labeled core, per-batch auto-labeling could disagree. *(Plan must confirm the existing `infrastructure/rdkit/rgroup_decomposer.py` labels off the core, not the set — this is the one real chemistry risk.)*
3. **Stream members in batches** → per batch: fetch `(id, smiles, version)`, decompose against the labeled core, collect matched `rgroups`, tally matched/unmatched.
4. Batched-insert **matched** assignment rows; write `rgroup_labels` + counts; mark ready.

**Activity-projection compute (`RunActivityProjection`):** stream members in batches → `MoleculeActivityService.enrich_molecules(batch_ids, protocol_columns, selection_rule, …)` → extract the **one scalar** the channel names (a small server-side port of FE `colorSpecScalar`, `lib/sar-color-spec.ts`) → batched-insert **sparse** `sar_activity_value` rows → mark ready.

> **Why activity must be materialized:** `MoleculeActivityService.enrich_molecules` applies selection rules (`latest_approved_run`, `best_r_squared`, mean/geomean…) over curves/readouts per molecule in Python — it is **not** a SQL subquery. So `ORDER BY activity` / `GROUP BY … color by activity` are impossible until the scalar is written to a joinable column. That single fact is why Pair 2 exists.

**Two read endpoints — pure SQL over the projections, no compute, no jobs:**

- `POST /sar/decomposition/{run_id}/rows` — the AG Grid Infinite-Row-Model datasource.
  Body `{offset, limit, sort:[{col,dir}], filter, projection_id?}` →
  `{rows:[{molecule_id, smiles, registration_number, name, rgroups, mw, clogp, tpsa, activity?}], total}`.
  Joins `assignment ⋈ molecules` (structure/reg#/physchem) `⋈ activity_value` (when `projection_id` given). Sort/filter by physchem → molecules; by R-group → `rgroups->>'R1'`; by activity → joined scalar. **Server-side sort/filter/page = unbounded.**

- `POST /sar/decomposition/{run_id}/heatmap` — `{axis_y, axis_x, projection_id}` →
  `{x_values, y_values, cells:[{y, x, count, best_scalar, best_molecule_id, best_molecule_label, best_snapshot}]}`.
  One `GROUP BY rgroups->>axis_y, rgroups->>axis_x` over `assignment ⋈ activity_value`, `argmin(scalar)` per cell (lower-is-better). **Exact at any size; payload bounded by # substituent combos.** `best_molecule_label` + `best_snapshot` let curve-expand work off-set (no `props.molecules`). FE keeps `pickReference`/`potencyShade`/dr_curve gating and computes the reference from the (small) returned cells — *BE aggregates, FE colors.*

**Endpoint set** (existing `/api/v1/sar` router):
```
POST /sar/decomposition                      start/cache → {run_id, status, labels?, counts?}
GET  /sar/decomposition/jobs/{run_id}        poll
POST /sar/decomposition/jobs/{run_id}/cancel
POST /sar/decomposition/{run_id}/rows        table page (Infinite Row Model)
POST /sar/decomposition/{run_id}/heatmap     server aggregation
POST /sar/activity-projection                start/cache → {projection_id, status}
GET  /sar/activity-projection/jobs/{id}      poll
POST /sar/activity-projection/jobs/{id}/cancel
POST /sar/decomposition/{run_id}/save-collection   {name, project_id, filter?}   (Unit C)
```

**FE orchestration is explicit:** pick core → ensure run (start+poll) → pick channel → ensure projection (start+poll) → `rows`/`heatmap` take the ready `run_id`/`projection_id`. Read endpoints never trigger compute.

**The current synchronous `POST /sar/r-group-decomposition` is replaced, not kept** (no backwards-compat shim). Small sets still feel instant: inline compute marks the job `ready` immediately, then one `rows` fetch.

---

## 5. Frontend rework

The core picker (`rgroup-core-picker.tsx`) is already collection-based (untouched). Everything downstream becomes server-driven.

**Deleted** (work moves server-side):
- `buildRGroupRows` — the client `assignment ⋈ props.molecules` join (source of blank rows).
- `buildHeatmapGrid` — client aggregation.
- `useSarActivity` — the `keyword_list` activity fetch.
- the inline-assignments contract of `useRGroupDecomposition` + the synchronous path.

**Kept verbatim** (pure rendering, no scale dependence):
- `buildRGroupColumns` + all cell renderers (`StructureThumbnail`, `fragmentDisplay`, `AxisFragment`).
- `pickReference` / `potencyShade` / `snapshotFromActivity` + `dr_curve`-only color gating.
- `RGroupColorControl`, `RGroupCorePicker`, `CurveExpandDialog`.

**New:**
- `useDecompositionRun({collectionId|moleculeIds, coreSmiles})` — job-poll hook **cloned from `useScaffoldTree`** → `{runId, labels, counts, status, error}`. CollectionId-preferred query key.
- `useActivityProjection({collectionId|moleculeIds, channelSpec})` — same shape → `{projectionId, status, error}`. Enabled only when a `colorSpec` is set.
- `useDecompositionRows(runId, projectionId?)` — returns an AG Grid `datasource` whose `getRows({startRow, endRow, sortModel, filterModel, success})` POSTs to `/rows`.
- `useHeatmapAggregation({runId, axisY, axisX, projectionId})` → server cells.

**Table** → AG Grid **Infinite Row Model** (Community feature in ag-grid 35.2; only Server-Side Row Model is Enterprise). Extend the shared `DataGrid` with an optional `datasource` prop (present ⇒ `rowModelType="infinite"`; absent ⇒ today's client-side `rowData`) — **purely additive, existing consumers untouched**, theme/columns/empty-state reused. `buildRGroupColumns` + renderers stay; only the data source changes.

**Heatmap** → swap `buildHeatmapGrid(...)` for `useHeatmapAggregation(...)`; JSX grid, axis pickers, gap cells, legend, click-to-expand all unchanged.

**`SarView` orchestration:** `core → useDecompositionRun`; `colorSpec → useActivityProjection`; pass `runId`/`labels`/`counts`/`projectionId` into table/heatmap. Loading states: "Decomposing…", "Computing activity…". **Counts banner is honest by construction** — `matched_count / total_count` come from the server over the full set; the table footer reads "rows 1–100 of N matched."

**`props.molecules`** is no longer used by the SAR table/heatmap (it stays for the other view modes, so `collection-detail`'s 10K load is unchanged — SAR just stops depending on it).

**Save-selection adapts to two honest paths:**
- **"Save all N matched → collection"** (primary) — server-side `/save-collection` inserts matched (filter-honoring) member ids; scales to any size.
- **Row-checkbox save** (secondary) — keeps explicit multi-select for *loaded* rows, for small ad-hoc picks.

---

## 6. Sequencing — three independently-mergeable units

Cut to avoid any interim regression (the heatmap is never half-broken). Within each unit, follow the project layer order (Domain → tests → Persistence → integration tests → Application → API → API tests → UI → E2E).

**Unit A — Backend (no user-visible change; old sync endpoint stays live).**
Both job aggregates + state machines, the four tables + migration, the streamed batch compute (labeled-core decomposition, sparse activity projection), Temporal workflows/activities + Null fallback, the three read/agg endpoints, full test coverage. De-risks the three hard parts — **member streaming, labeled-core label stability, SQL heatmap aggregation** — behind tests before any UI depends on them.

**Unit B — Frontend (atomic swap → ships the unbounded UX).**
Rewire table **and** heatmap to the new endpoints in one move (new hooks, additive Infinite-Row-Model `DataGrid` extension, server-cell heatmap), then delete the old endpoint + `buildRGroupRows` + `buildHeatmapGrid` + `useSarActivity`. Atomic because client table + heatmap must cut over together; the old path stays working until this lands. (Splittable into table-then-heatmap only at the cost of temporary double-decomposition.)

**Unit C — Save + polish + docs.**
Server-side "Save all N matched → collection", loading/empty/cancel states, honest-label copy pass, performance indexes (`rgroups->>'R1'` expression indexes + join indexes), documentation.

---

## 7. Cross-cutting (carried into the plan)

- **Domain-model deviation, documented** — `RGroupDecompositionRun` and `SarActivityProjection` are new SAR aggregates not in `docs/domain-model/04-sar-analysis.md`; Unit C adds them there (same call-out the handoff flagged for `MolecularFingerprint`). Modeled as proper aggregates, not smuggled in as columns.
- **Invalidation is implicit** — version-aware `membership_hash`; no explicit merge/structure-correction handlers.
- **No TTL / no eviction** (mirrors scaffold-tree) — stale rows for prior membership/core are harmless; a cleanup job is explicit YAGNI.
- **Temporal timeout caveat** — large streamed computes need generous activity timeouts, baked at schedule time (timeout params live in workflow history; code changes don't affect running workflows).
- **Known boundary, documented** — the *core picker's* coverage suggestions still come from the scaffold tree's 100K-capped sample, while decomposition itself is unbounded. Beyond ~100K members the *suggested cores* sample the set; decomposition over a chosen core is still exact. Raising the scaffold ceiling is a separate feature, out of scope.
- **GitHub board** — backlog #1 issue updated to reflect the re-scope; per-unit issues created.

---

## 8. Open verification items for the plan
1. **Labeled-core stability** — confirm `infrastructure/rdkit/rgroup_decomposer.py` (`RGroupDecomposer`) labels R-positions off the core, not the aligned set, so per-batch == whole-set. The pivotal correctness test.
2. **Inline threshold** — pick the ≤N-members inline cutoff (scaffold-tree uses 500); same for activity projection.
3. **AG Grid Infinite filter model** — map AG Grid `filterModel` (text/number/set) → the `/rows` `filter` param; decide which columns are server-filterable in v1 (physchem + activity + reg#; R-group filter optional).
4. **Heatmap axis cardinality guard** — pathological cores with thousands of distinct substituents at a position would make a huge grid; decide a cap + honest "top-K substituents" labeling.

---

## 9. Key files (existing — to mirror or modify)

**Mirror (scaffold-tree async-job + cache exemplars):**
- `backend/.../interface/routes/scaffold_tree.py`, `umap_cluster.py`
- `backend/.../application/sar_analysis/start_scaffold_tree_job.py`, `run_scaffold_tree.py`, `build_scaffold_network.py` (`compute_ids_hash`)
- `backend/.../domain/sar_analysis/scaffold_tree_job.py`
- `backend/.../infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py`, `models.py`
- `backend/alembic/versions/038_scaffold_tree_jobs.py`, `039_umap_jobs.py`
- `backend/.../infrastructure/temporal/orchestrators/scaffold_tree.py`, `workflows/scaffold_tree.py`

**Modify / replace:**
- `backend/.../interface/routes/sar_analysis.py` (replace sync endpoint)
- `backend/.../application/sar_analysis/decompose_rgroups.py`, `rgroup_decomposition.py`
- `backend/.../domain/sar_analysis/rgroup_types.py`
- `backend/.../infrastructure/rdkit/rgroup_decomposer.py`
- `frontend/.../sar-analysis/components/sar-view.tsx`, `rgroup-table.tsx`, `rgroup-heatmap.tsx`
- `frontend/.../sar-analysis/hooks/use-rgroup-decomposition.ts`, `use-sar-activity.ts`
- `frontend/.../shared/components/data-grid/data-grid.tsx`

**Reuse (no change):**
- `backend/.../application/screening/molecule_activity_service.py` (`enrich_molecules`)
- `backend/.../domain/shared/aggregation_types.py` (`SelectionRule`, `QualifierHandling`)
- `backend/.../application/research_organization/collection_membership.py` (`ListCollectionMolecules`)
- `backend/.../application/shared/pagination.py` (`COLLECTION_EXPANSION_LIMIT`)
- `frontend/.../shared/hooks/use-job-poll.ts`, `sar-analysis/hooks/use-scaffold-tree.ts`
- `frontend/.../sar-analysis/lib/sar-color-spec.ts`, `rgroup-heatmap-grid.ts`, `sar-fragment-label.ts`
