# SAR full-collection — Part 2 handoff (activity projection + heatmap) + Unit B/C

**Purpose.** Orient a **fresh session** to implement **Part 2** of the server-side, unbounded SAR
feature (activity projection + the server-aggregated heatmap endpoint + the activity column on
`/rows`), then carry on into **Unit B** (frontend swap) and **Unit C** (save + polish + docs) "in one
pass" as far as the session gets. **Part 1a (compute+persist foundation) and Part 1b (async job +
decomposition endpoints) are DONE, reviewed, tested, and merged to `main`.** Start with
`superpowers:brainstorming` for the few genuinely-open Part 2 decisions, then `writing-plans` →
implement task-by-task with `superpowers:subagent-driven-development`.

**Read first (in order):**
1. `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` — the design **source of
   truth**. Especially **§3 Pair 2** (activity-projection tables), **§4** (activity compute + the
   `/heatmap` and `/rows` endpoints), §5 (frontend rework), §6 (sequencing: Units A→B→C), §7
   (cross-cutting), §8 (open items 3 & 4 are Part-2/Unit-B).
2. `docs/superpowers/plans/2026-06-15-sar-decomposition-async-endpoints.md` — the Part 1b plan: the
   **exact pattern Part 2 mirrors** (job aggregate → repo+cache → member stream → start/run/get/cancel
   use cases → Temporal workflow/activity + Null + DI → routes + tests).
3. `docs/superpowers/plans/2026-06-11-sar-decomposition-run-foundation.md` — the Part 1a plan.
4. This file.

**Branch:** branch off `main` (Part 1a+1b are on `main`). Migration head: `057`; Part 2 adds **`058`**.
Docker + dev Postgres up; integration tests use testcontainers (conftest applies migrations).
Tests set `TEMPORAL_DISABLED=1` (`tests/api/conftest.py`) → the DI Null-orchestrator fallback is what
makes api/wiring tests work; mirror that for the new projection orchestrator.

---

## What Part 1b already gives you (merged to main; mirror, don't rebuild)

The decomposition slice is the **exact template** for activity projection. Reuse/mirror:

- **Hashing (reuse as-is)** — `application/sar_analysis/hashing.py`:
  `compute_membership_hash(pairs: list[tuple[UUID,int]])` (version-aware; **reuse for the projection's
  `membership_hash`** — projections are keyed by the *same* membership as a decomposition run) and
  `sha256_hex(text)` (use for `channel_hash` = sha256 of the normalized `SarColorSpec`).
- **Member stream (reuse as-is)** — `application/sar_analysis/decomposition_members.py`
  `DecompositionMemberStream.stream(*, workspace_id, collection_id, molecule_ids)` yields
  `(id, smiles, version)` batches. Activity projection streams the **same membership** to enrich — but
  it needs **ids** (smiles optional). Reuse the stream; ignore smiles, or add a sibling that yields
  just `(id, version)` if you want a leaner fetch (check `fetch_for_decomposition` first).
- **Job lifecycle (mirror exactly)** — for the decomposition run:
  `domain/sar_analysis/rgroup_decomposition_run.py` (aggregate + `pending→running→ready/failed/cancelled`
  state machine), `application/sar_analysis/{start,run,get,cancel}_decomposition_run.py`,
  `infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`
  (`find_cached(membership_hash, core_hash)` partial-index pattern → yours keys on
  `(membership_hash, channel_hash)`).
- **Temporal (mirror exactly)** — `infrastructure/temporal/{activities,workflows,orchestrators}/rgroup_decomposition.py`
  (Temporal + Null asyncio fallback, source-as-strings boundary, 1h baked timeout, worker registration in
  `infrastructure/temporal/worker.py`, lifespan binding in `interface/app.py`). The projection input
  carries `collection_id | molecule_ids` (source) + the **channel spec** — never the expanded membership.
- **DI (mirror)** — `infrastructure/di/_sar_analysis.py`: per-resolve UoW shared across the use case +
  member stream + repo; Null orchestrator under `TEMPORAL_DISABLED==1`; live one bound in app lifespan.
- **`/rows` read-model (extend)** — `application/sar_analysis/decomposition_rows.py` +
  `infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py`. Part 2 adds an
  **optional `projection_id`** → `LEFT JOIN sar_activity_value` → adds `activity` to each row + enables
  **sort-by-activity**. The reader join already does `assignment ⋈ molecules` workspace+merged-scoped;
  add the activity LEFT JOIN keyed on `(projection_id, molecule_id)`.
- **Routes (extend the same file)** — `interface/routes/sar_analysis.py` (router `/api/v1/sar`).
  Existing: `POST /decomposition`, `GET …/jobs/{run_id}`, `POST …/jobs/{run_id}/cancel`,
  `POST …/{run_id}/rows`. Mirror the 200/202 + poll + cancel shape for activity-projection; add the
  heatmap route. Dep aliases live in `interface/dependencies/_sar_analysis.py`.

**The exact decomposition seam names** (for the `/rows` activity extension + the heatmap join):
`RGroupAssignmentModel(run_id, molecule_id, rgroups JSONB)`, R-group keys are **uppercase `R1`/`R2`**,
sort via `RGroupAssignmentModel.rgroups[label].as_string()` (the `->>` idiom). Molecule physchem are
direct columns on `molecules` (`molecular_weight`, `logp`, `tpsa`, `smiles`, `registration_number`,
`name`); visibility = `workspace_id` + `merged_into_id IS NULL`.

---

## What Part 2 builds (spec §3 Pair 2 + §4)

**1. Persistence — migration `058` (two tables, header+rows; mirror 057).**
- `sar_activity_projection` (aggregate/job header + cache row): `id, workspace_id, requested_by,
  membership_hash TEXT idx, channel_hash TEXT idx, channel_spec JSONB, status, requested_at, started_at,
  completed_at, error_message, version`. Partial index `(membership_hash, channel_hash, completed_at DESC)
  WHERE status='ready'`. **Core-independent** (no core_hash — reused across cores).
- `sar_activity_value` (result projection, **SPARSE** — only mols with a value): `projection_id FK
  CASCADE, molecule_id, scalar FLOAT, unit, qualifier, source TEXT, snapshot JSONB`; PK
  `(projection_id, molecule_id)`. `snapshot` feeds curve-expand on click (off-set).
- New aggregate `SarActivityProjection` (same state machine as `RGroupDecompositionRun`) + its repo with
  `find_cached(membership_hash, channel_hash)` + `write_values` (batched) + `fetch/count`.

**2. Activity compute — `RunActivityProjection` (mirror `RunDecomposition`).**
Stream members (by membership) → `MoleculeActivityService.enrich_molecules(batch_ids, protocol_columns,
selection_rule, …)` (reuse, no change — `application/screening/molecule_activity_service.py`) → extract
**the one scalar the channel names** via a **server-side port of FE `colorSpecScalar`** (`frontend/.../
sar-analysis/lib/sar-color-spec.ts`) → batched-insert **sparse** `sar_activity_value` rows → mark ready.
⚠️ **This is the keystone risk** — confirm the `MoleculeActivityService.enrich_molecules` signature +
the `SarColorSpec`→scalar selection (protocol_columns + aggregation + run_scopes) so the server scalar
matches what the FE used to compute. Activity must be *materialized* (it's a Python service, not a SQL
column) — that single fact is why this table exists (spec §4 callout).

**3. Start/Get/Cancel activity-projection use cases + Temporal + DI** — mirror the decomposition four
exactly. Cache on `(membership_hash, channel_hash)`. Job input = source (`collection_id | molecule_ids`)
+ channel spec; re-expand at run time. Inline threshold: pick during brainstorm (projection cost ≈
activity enrich per mol; may differ from 200 — see open items).

**4. Read endpoints (pure SQL, no compute).**
- `POST /sar/decomposition/{run_id}/heatmap {axis_y, axis_x, projection_id}` →
  `{x_values, y_values, cells:[{y, x, count, best_scalar, best_molecule_id, best_molecule_label,
  best_snapshot}]}`. One `GROUP BY rgroups->>axis_y, rgroups->>axis_x` over `assignment ⋈ activity_value`,
  `argmin(scalar)` per cell (lower-is-better). Exact at any size; payload bounded by # substituent combos.
  `best_molecule_label` + `best_snapshot` let curve-expand work off-set. **BE aggregates, FE colors.**
- **Extend `POST …/{run_id}/rows`** — accept optional `projection_id`; `LEFT JOIN sar_activity_value`;
  add `activity` to the row DTO + view; enable sort-by-activity (joined scalar).
- `POST /sar/activity-projection` (start 200/202) · `GET /sar/activity-projection/jobs/{id}` (poll) ·
  `POST /sar/activity-projection/jobs/{id}/cancel`.

**FE orchestration is explicit (carries into Unit B):** pick core → ensure run → pick channel → ensure
projection → `rows`/`heatmap` take the ready `run_id`/`projection_id`. Read endpoints never trigger compute.

## Open items to settle (light brainstorm, then plan)
- **`SarColorSpec`→scalar port** — confirm the FE `colorSpecScalar` logic + `MoleculeActivityService`
  signature; decide the server `SarColorSpec`/`channel_spec` shape (protocol_columns + aggregation +
  run_scopes) and its normalization for `channel_hash`. (Pivotal correctness item.)
- **Inline threshold** for activity projection (start at the decomposition 200; activity enrich may be
  heavier — may want lower).
- **Heatmap axis cardinality guard** (spec §8.4) — a pathological core with thousands of distinct
  substituents at a position → huge grid. Decide a cap + honest "top-K substituents" labeling.
- **Member fetch for projection** — reuse `DecompositionMemberStream` (ignore smiles) vs a leaner
  `(id, version)` fetch. Check `fetch_for_decomposition` callers before adding a sibling.

## Then Unit B (frontend — atomic swap; spec §5) — "one pass" continuation
Rewire **table and heatmap together** to the new endpoints (no interim regression — the old sync path is
already gone, so the SAR FE is currently broken against this backend until Unit B lands; that's the
expected Unit-A→B handoff state). New hooks cloned from `useScaffoldTree`/`use-job-poll`:
`useDecompositionRun`, `useActivityProjection`, `useDecompositionRows` (AG-Grid **Infinite Row Model**
datasource — Community in ag-grid 35.2 — `getRows({startRow, endRow, sortModel, filterModel})` → `/rows`),
`useHeatmapAggregation` → `/heatmap`. Extend the shared `DataGrid` with an optional `datasource` prop
(present ⇒ `rowModelType="infinite"`; additive, existing consumers untouched). **This is where the
`/rows` `filter` param's AG-Grid `filterModel`→param mapping (spec §8.3) gets designed + built.** Keep
`buildRGroupColumns`/renderers, `pickReference`/`potencyShade`/`snapshotFromActivity`, axis pickers,
curve-expand. **Delete** `buildRGroupRows`, `buildHeatmapGrid`, `useSarActivity`, and the old
inline-assignments contract of `useRGroupDecomposition`. `SarView` orchestration: core→run,
colorSpec→projection; counts banner honest by construction (`matched/total` from the server).
Key FE files in spec §9.

## Then Unit C (save + polish + docs; spec §6/§7)
- Server-side **"Save all N matched → collection"** (`POST /sar/decomposition/{run_id}/save-collection
  {name, project_id, filter?}`) — inserts matched (filter-honoring) member ids; scales to any size.
  Plus the row-checkbox save for small ad-hoc picks.
- **Perf indexes** — `rgroups->>'R1'` expression indexes + join indexes (migration).
- **Domain-model deviation note** — add `RGroupDecompositionRun` **and** `SarActivityProjection` as new
  SAR aggregates to `docs/domain-model/04-sar-analysis.md` (the call-out flagged in spec §7 — modeled as
  proper aggregates, not smuggled-in columns).
- Loading/empty/cancel states, honest-label copy pass.
- **GitHub board** — update backlog #1 + create per-unit issues (per the repo's GitHub-tracking rule).

## Known boundary (documented, out of scope)
The **core picker's** coverage suggestions still sample the scaffold tree's 100K cap; decomposition over a
*chosen* core is exact at any size. Raising the scaffold ceiling is a separate feature.

## Exemplars to mirror (all current on main)
Routes/use cases/Temporal/DI/tests for the decomposition slice (Part 1b) — every file under
`{application,infrastructure,interface}/.../sar_analysis` touched by
`docs/superpowers/plans/2026-06-15-sar-decomposition-async-endpoints.md`. The async-job test patterns:
`tests/unit/application/sar_analysis/test_start_decomposition_run.py`, `test_run_decomposition.py`,
`tests/unit/infrastructure/temporal/test_rgroup_decomposition_orchestrators.py`,
`tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`,
`test_decomposition_async_e2e.py` (the real Start→Null-orch→Run→DB end-to-end test — write the analogous
one for activity projection), `tests/api/test_sar_analysis_routes.py`.
