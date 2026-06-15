# SAR full-collection — Part 1b handoff (async job + endpoints)

**Purpose.** Orient a **fresh session** to implement **Part 1b** of the server-side, unbounded
R-group decomposition feature, without re-exploring. **Part 1a (the compute + persist foundation) is
DONE, reviewed, tested, and merged to main.** Part 1b is the async-job + HTTP-endpoints layer that
ties the foundation together. Start with `superpowers:brainstorming` only for the few genuinely-open
decisions below (the overall design is already settled in the spec), then `writing-plans` → implement.

**Read first (in order):**
1. `docs/superpowers/specs/2026-06-11-sar-full-collection-coverage-design.md` — the design **source of
   truth**. Especially **§4 (backend compute & endpoints)**, §3 (persistence), §6 (sequencing), §8 (open items).
2. `docs/superpowers/plans/2026-06-11-sar-decomposition-run-foundation.md` — the Part 1a plan (the
   foundation Part 1b builds on).
3. This file.

**Branch:** `design-7` (off main; the Part 1a foundation is present). Migration head: `057`.
Docker + a dev Postgres (`cellar:cellar@localhost:5432/cellar`) are up; integration tests use
testcontainers (conftest applies migrations to a fresh container — Docker required).

---

## What Part 1a already gives you (merged; do NOT rebuild)

The exact seams Part 1b calls:

- **Streaming decomposer** — `backend/src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`
  - `StreamingRGroupDecomposer().session(core_smiles: str) -> RGroupDecompositionSession`
  - `session.add(molecule_id: UUID, smiles: str) -> bool` (True = matched+added; False routes the id to
    unmatched — empty/None-parse SMILES, no core match)
  - `session.finish() -> RGroupDecompositionResult` (one-shot; raises `RuntimeError` if called twice;
    fails **closed** on RDKit contract violation). Memory is **O(matched set)**, not O(collection).
- **Domain aggregate** — `backend/src/cellar/domain/sar_analysis/rgroup_decomposition_run.py`
  - `RGroupDecompositionRun.create(*, workspace_id, requested_by, membership_hash, core_smiles, core_hash, now)`
  - `.mark_running(now)` · `.mark_ready(*, rgroup_labels, matched_count, unmatched_count, total_count, now)`
    (keyword-only) · `.mark_failed(error, now)` · `.mark_cancelled(now)`
  - State machine `pending → running → {ready|failed|cancelled}`; `pending → cancelled`. ready/failed/cancelled terminal.
- **Repository** — Protocol in `backend/src/cellar/application/sar_analysis/repositories.py`
  (`RGroupDecompositionRunRepository`); impl
  `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`
  - `save(run)` (insert-or-update) · `find_by_id(run_id, *, workspace_id)` ·
    `find_cached(*, membership_hash, core_hash) -> RGroupDecompositionRun | None` (latest READY; **returns the
    run HEADER, not a result payload — labels+counts are on it; assignment rows already persisted under its id**)
  - `write_assignments(run_id, list[RGroupAssignment])` (batched 1000) ·
    `fetch_assignments(run_id, *, workspace_id, offset, limit) -> list[RGroupAssignment]` (ORDER BY molecule_id,
    workspace-scoped via join to the run) · `count_assignments(run_id, *, workspace_id) -> int`
- **Tables** (migration `057_rgroup_decomposition_runs`): `rgroup_decomposition_runs` (header; partial cache
  index `(membership_hash, core_hash, completed_at DESC) WHERE status='ready'`) + `rgroup_assignments`
  (`run_id` FK CASCADE, `molecule_id`, `rgroups` JSONB; PK `(run_id, molecule_id)`).
- **VOs reused** — `backend/src/cellar/domain/sar_analysis/rgroup_types.py`:
  `RGroupAssignment(molecule_id: UUID, rgroups: dict[str,str])`,
  `RGroupDecompositionResult(core_smiles, rgroup_labels: list[str], assignments, unmatched_ids: list[UUID])`.

**The count bridge** the runner uses (verified exact against RDKit during Part 1a review):
`matched_count = len(result.assignments)`; `unmatched_count = len(result.unmatched_ids)`;
`total_count = matched_count + unmatched_count`.

---

## What Part 1b builds (spec §4) — mirror the scaffold-tree async-job slice exactly

1. **Hashing + canonicalization helpers (new).**
   - `compute_membership_hash(pairs: list[tuple[UUID, int]]) -> str` = SHA-256 of sorted `"id:version"`
     strings. **PURE** (application/shared or a small module). Version-aware ⇒ a merge / structure-correction
     bumps a member's `version` ⇒ new hash ⇒ cache miss ⇒ recompute (no explicit invalidation handlers).
     ⚠️ Do **not** reuse `compute_ids_hash` in `build_scaffold_network.py` — it hashes ids only; we need version.
   - `core_hash`: canonicalize the core SMILES (`Chem.MolFromSmiles` → `MolToSmiles`) in **infrastructure**
     (rdkit — the streaming-decomposer module is a fine home, or a tiny canonicalizer), then SHA-256 the
     canonical string (pure). Keep RDKit out of the application layer (import-linter enforces this).
2. **Batched collection-member iterator (new).** Stream `(molecule_id, smiles, version)` in pages (~10K)
   for a collection, so a >100K collection isn't blocked by a single capped fetch, and the hash folds
   incrementally. Mirror/extend `MoleculeFetcherForScaffoldTree` (`build_scaffold_network.py` — it fetches
   `(id, smiles, bemis_murcko_smiles)`; you need `(id, smiles, version)`). Used **twice**: to compute
   `membership_hash` and to feed the decomposer session. **Job input carries `collection_id`, NOT the
   expanded id list** (passing ~1M ids through Temporal history is the anti-pattern) — re-expand at run time.
   Ad-hoc explicit sets carry their bounded id list directly.
3. **`StartDecompositionRun` use case (new)** — mirror `start_scaffold_tree_job.py` (`sync_limit=500`):
   compute `membership_hash` + `core_hash` → `find_cached` → **hit:** return `{run_id, labels, counts}`;
   **miss + ≤ inline_threshold members:** compute inline (sync), persist a READY run + its assignment rows,
   return inline; **miss + larger:** create PENDING run, `save`, `orchestrator.schedule(run_id, collection_id
   |ids, core_smiles)`, return the job (HTTP 202).
4. **`RunDecomposition` use case (new)** — mirror `run_scaffold_tree.py`: load run → `mark_running` → save;
   `session = decomposer.session(core_smiles)`; stream member batches → `session.add(id, smiles)` each →
   `result = session.finish()` → `repo.write_assignments(run_id, result.assignments)` →
   `run.mark_ready(rgroup_labels=result.rgroup_labels, matched/unmatched/total via the bridge, now)` → save.
   On exception: `mark_failed` + reraise (Temporal retries).
5. **Temporal workflow + activity + Null orchestrator + DI (new)** — mirror
   `infrastructure/temporal/{orchestrators,workflows}/scaffold_tree.py` + the Null asyncio fallback +
   `infrastructure/di/_sar_analysis.py`. ⚠️ Activity timeout/retry are **baked at schedule time** — set
   **generous** timeouts for large streamed computes.
6. **Routes** — `interface/routes/sar_analysis.py`. **Replace** the current synchronous
   `POST /api/v1/sar/r-group-decomposition` (no backwards-compat shim). Keep the `molecule_ids XOR
   collection_id` validation.
   - `POST /sar/decomposition {collection_id|molecule_ids, core_smiles}` → `{run_id, status, rgroup_labels?,
     counts?}` (200 inline-ready / 202 job).
   - `GET /sar/decomposition/jobs/{run_id}` → poll `{id, status, rgroup_labels, matched_count,
     unmatched_count, total_count, error_message}`.
   - `POST /sar/decomposition/jobs/{run_id}/cancel`.
   - `POST /sar/decomposition/{run_id}/rows {offset, limit, sort?, filter?}` →
     `{rows:[{molecule_id, smiles, registration_number, name, rgroups, mw, clogp, tpsa}], total}`.
     JOIN `rgroup_assignments ⋈ molecules` (by molecule_id, workspace-scoped) for structure/reg#/name/physchem;
     `total = count_assignments`. **NO ACTIVITY in Part 1b** — the activity column + sort-by-activity arrive in
     **Part 2** (activity projection). Sort/filter by physchem/reg# → molecules; by an R-group → `rgroups->>'Rn'`.
     v1 can start with `offset/limit` + basic sort; this is the AG Grid **Infinite Row Model** datasource for
     Unit B (its `getRows({startRow, endRow, sortModel, filterModel})`), but Part 1b builds only the backend
     endpoint + tests.

For the `/rows` molecule join, confirm exact columns on the molecule model/reader
(`infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py` + the molecule model) —
the FE join (`buildRGroupRows`) used `structure.smiles`, `registration_number`, `name`,
`descriptors.{molecular_weight, logp→cLogP, tpsa}`.

---

## Decisions already locked (honor them)
- Job input = `collection_id`, re-expanded at run time (never the materialized id list for collections).
- `membership_hash` folds `(id, version)` — version-aware invalidation; no explicit merge/structure handlers.
- `find_cached` returns the run **header**; the start path returns `{run_id, labels, counts}`; rows come from `/rows`.
- Inline ≤ ~500 members, else async (scaffold-tree threshold; confirm the exact number for decomposition cost).
- Replace the old sync endpoint — no shim.

## Open items to settle (light brainstorm, then plan)
- Exact inline threshold (start at 500; decomposition is heavier than scaffold counting — may want lower).
- Member fetcher: extend `MoleculeFetcherForScaffoldTree` to also return `version`, or add a sibling fetcher
  returning `(id, smiles, version)`? Check existing callers before changing the shared one.
- `/rows` sort/filter scope for v1 (physchem + reg# server-side is the floor; R-group-column sort optional).
- FE is **not** in Part 1b (that's Unit B) — only the backend endpoints + tests.

## Exemplars to mirror (all explored during Part 1a — paths are current)
- Routes: `interface/routes/scaffold_tree.py`, `umap_cluster.py` (start 200/202, poll, cancel, collection expansion).
- Use cases: `application/sar_analysis/start_scaffold_tree_job.py`, `run_scaffold_tree.py`,
  `get_scaffold_tree_job.py`, `cancel_scaffold_tree_job.py`, `build_scaffold_network.py`
  (`compute_ids_hash`, `MoleculeFetcherForScaffoldTree`, COLLECTION_EXPANSION_LIMIT usage).
- Temporal: `infrastructure/temporal/orchestrators/scaffold_tree.py` (Temporal + Null), `workflows/scaffold_tree.py`.
- DI: `infrastructure/di/_sar_analysis.py`.
- Limits/expansion: `application/shared/pagination.py` (COLLECTION_EXPANSION_LIMIT=100K,
  COLLECTION_FETCH_MAX_PAGE_SIZE=10K); `application/research_organization/collection_membership.py`
  (`ListCollectionMolecules`, offset/limit).
- Tests to mirror: `tests/api/test_scaffold_tree_routes.py`,
  `tests/unit/application/sar_analysis/test_start_scaffold_tree_job.py`,
  `tests/unit/infrastructure/temporal/test_scaffold_tree_orchestrators.py`,
  `tests/integration/persistence/sar_analysis/...`.

## After Part 1b
**Part 2** — activity projection (`sar_activity_projection` + `sar_activity_value` tables; membership+channel
keyed; materialize `MoleculeActivityService` output) **+ heatmap-aggregation endpoint** (server `GROUP BY
rgroups->>axisY, rgroups->>axisX`). Then **Unit B** (FE swap to the new endpoints; AG Grid Infinite Row Model;
server-cell heatmap; delete `buildRGroupRows`/`buildHeatmapGrid`/`useSarActivity`). Then **Unit C** (server-side
"save all matched → collection", honest-label pass, perf indexes, docs incl. the domain-model deviation note).
Full sequencing + cross-cutting in spec §6–§7.
