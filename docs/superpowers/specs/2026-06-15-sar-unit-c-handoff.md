# SAR Unit C — handoff (fresh session)

**Created:** 2026-06-15 · **Branch:** `design-7` · **Prev:** Unit B ✅ done (16 commits, top `5b5bebcc`).

Unit B rewired the SAR workbench (table **+** heatmap) onto the Unit-A server endpoints and deleted the client-side compute, so SAR is correct over the **full collection** of any size. This doc is the self-contained handoff for **Unit C** (the polish + remaining server work). Each item is independently shippable; do them as separate brainstorm→plan→implement slices, or batch the small ones.

---

## Start here (environment)

```bash
cd backend && uv run alembic heads      # expect 058_sar_activity_projections
# backend must run on :8000 for orval regen; it auto-reloads on code change
curl -sf localhost:8000/openapi.json >/dev/null && echo up || echo "START BACKEND on :8000"
cd ../frontend && pnpm -v && node -v     # pnpm 11, node 25
```

- **BE gates:** `cd backend && uv run pytest <paths> -q && uv run lint-imports && uv run ruff check src/ && uv run ruff format --check src/`
- **FE gates:** `cd frontend && pnpm exec vitest run <paths> && pnpm exec tsc --noEmit && pnpm exec biome check <paths>`
- Commit convention: explicit pathspec (`git commit -m … -- <paths>`); FE from `frontend/`, BE from `backend/`; trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Pre-existing debt (NOT yours — don't fix inline, they gate `*/`-wide checks)
- `docs/backlog/part1b-ruff-debt.md` — 2 `ruff check` errors + 2 `ruff format` files in `streaming_rgroup_decomposer.py` / `rgroup_decomposition_run_repository.py`. Could be cleared in one focused commit if you want the BE `src/` gate green.
- `docs/backlog/frontend-biome-warning-burndown.md` — ~59 FE biome **warnings** (a11y, noExplicitAny, useExhaustiveDependencies, …). Warnings don't gate; errors do.
- `docs/backlog/pre-existing-test-failures.md` — don't run the *full* suites blind; scope tests to what you touch.

## Gotchas that bit Unit B (save yourself the rediscovery)
- **biome format = error severity; lint rules = warn.** After writing ANY file (impl **and test**), run `pnpm exec biome check --write <impl> <test>` then `biome check` to verify exit 0. Unit B shipped one format error because a *test* file was checked-but-not-formatted. Verify by **exit code**, never piped output (a `| tail` masks the real `$?`).
- **orval generated fn names:** mostly `<operationId>ApiV1Sar…`, but the activity-projection poll is `getActivityProjectionApiV1SarActivityProjectionJobsProjectionIdGet` (not `…JobsIdGet`). Re-grep `src/shared/lib/api/sar-analysis/sar-analysis.ts` after any regen.
- **orval boundary casts:** the FE hooks use a loose hand-rolled channel/body type and cast at the generated-fn call (`x as unknown as Parameters<typeof fn>[0]`, return `as unknown as <Response>`). Per-task vitest does NOT catch arg-type mismatches — run `pnpm exec tsc --noEmit` after hook/component work.
- **Node 25 + jsdom:** `vitest.setup.ts` polyfills `localStorage` (Node 25's built-in shadows jsdom's). Radix Select in jsdom needs `scrollIntoView`/`hasPointerCapture` polyfills (see any `*color-control*`/`*core-picker*` test).
- **docs/ is gitignored** — only force-added files are tracked. This handoff + the plan/specs were `git add -f`'d. `git ls-files` before assuming a doc is tracked.

---

## Unit-B landmarks (what to build on)

**Backend**
- `backend/src/cellar/interface/routes/sar_analysis.py` — `/decomposition` (async start, 200/202), `/decomposition/jobs/{run_id}` (poll), `/decomposition/{run_id}/rows` (server page+sort+**filter**, returns `activity`/`activity_snapshot` per row + `activity_reference`), `/decomposition/{run_id}/heatmap`, `/activity-projection` (+ jobs/{id} + cancel).
- `…/application/sar_analysis/decomposition_rows.py` — `FetchDecompositionRows` use case; `DecompositionRowReader` Protocol (`fetch_rows`/`count_rows`/`activity_reference`, all take `filter`).
- `…/infrastructure/persistence/sqlalchemy/sar_analysis/decomposition_row_reader.py` — `_apply_filter` (lenient col/op resolver), `_activity_join`, `_scoped_join`. **Reuse `_scoped_join` + `_apply_filter` for the save-collection id query (item 1).**
- `…/sar_analysis/rgroup_decomposition_run_repository.py` (run aggregate + assignments), `…/sar_activity_projection_repository.py` (projection + `ActivityScalar` values).

**Frontend**
- Hooks (`features/sar-analysis/hooks/`): `use-decomposition-run`, `use-activity-projection` (+ `channelFromColorSpec`), `use-heatmap-aggregation`, `use-decomposition-rows` (returns the AG-Grid `IDatasource` + captured `activityReference`). All job-poll hooks clone `use-scaffold-tree.ts` + `shared/hooks/use-job-poll.ts`.
- `lib/ag-filter-model.ts` — `agFilterModelToParam` + `colIdToBackendKey` (the AG-Grid↔`/rows` contract; **the filter you'll reuse for "save all N filtered"**).
- `components/`: `rgroup-table.tsx` (infinite datasource; exports kept helpers `pickReference`/`potencyShade`/`snapshotFromActivity`/`buildActivityColumns`), `rgroup-heatmap.tsx` (server cells), `sar-view.tsx` (orchestrator, **prefers `collectionId`**, save dialog takes `{id,label}[]`).
- `shared/components/data-grid/data-grid.tsx` — additive `datasource` prop → Infinite Row Model.

---

## Unit-C work items (recommended order)

### 1. ✅ DONE (2026-06-16) — Server-side "Save all N matched → collection"  *(small–moderate; highest user value)*
**Done:** commits `bb0af382`→`577281c5` on `design-7` (reader `fetch_matched_ids` → `SaveDecompositionCollection` use case reusing `CreateCollection`+`AddMoleculesToCollection` → `POST /sar/decomposition/{run_id}/save-collection` route+DI → orval regen → FE `useDecompositionRows` filterParam/total + `useSaveDecompositionCollection` hook + `SaveSelectionDialog` count/preview refactor + `RGroupTable` opt-in toolbar action + `SarView` discriminated save-intent). Filter-aware single button (no filter → "Save all N matched"; filter → "Save N filtered"). Spec+plan: `docs/superpowers/{specs,plans}/2026-06-15-sar-unit-c-item1-save-collection*.md`. Tests: reader integration + use-case unit + API + FE hook/dialog/helper/orchestration. Render-flow still deferred to E2E (item 6). Follow-up: the membership-add re-resolves ids through `MoleculeResolver` (one query/ref — N+1); root-cause fix (batch uuid resolution) folded into item 2, tracked in `docs/backlog/molecule-resolver-uuid-batch.md`.
**Now (original):** the table's "Save as collection" only saves the **selected/loaded** rows (`SarView` → `SaveSelectionDialog` → create-collection + bulk-add by id). Over a full collection the chemist can't save *all* matches (or all matches under the current filter) without scrolling every page.
**Build:** `POST /sar/decomposition/{run_id}/save-collection` body `{ name, project_id, filter? }` → resolves **all** matched `molecule_id`s for the run (apply the same `filter` contract via `_apply_filter` + `_scoped_join`; add a reader `fetch_matched_ids(run_id, *, workspace_id, filter)` returning ids only), creates the collection, bulk-adds. Validate workspace + (if given) projection ownership like the rows route does. Return `{ collection_id }`.
**FE:** add a "Save all N matched" action in the table toolbar (next to the per-selection save) that passes the live `filterModel` (mapped via `agFilterModelToParam`) to the new endpoint; reuse `SaveSelectionDialog` for name/project. Keep the per-selection path too. Regenerate orval; hand-write the hook calling `customInstance` (FE convention). TDD: reader id-query test + API test + a hook test.

### 2. Perf indexes  *(small; do before real-collection load testing)*
The `/rows` filter/sort hits `rgroups->>'Rn'` and the activity LEFT JOIN every page. Add a migration:
- Activity join: index on `sar_activity_values (projection_id, molecule_id)` (confirm exact table/cols from `sar_activity_projection_models.py`).
- Scoped join: `rgroup_assignments (run_id, molecule_id)` (confirm from `rgroup_decomposition_models.py`).
- R-group filter/sort: a **GIN** index on the `rgroups` jsonb (labels are dynamic, so per-key expression indexes don't scale). If you keep `->>'Rn' = v` equality, consider rewriting those clauses to containment (`rgroups @> '{"Rn":"v"}'`) so the GIN index is used — decide in the slice. `alembic revision` → `059_…`; verify `EXPLAIN` on a seeded set.

### 3. Functional-state + honest-label polish  *(small)*
Loading / empty / **cancel** states + copy across `sar-view`/`rgroup-table`/`rgroup-heatmap`: wire the projection/run **cancel** endpoints (`…/jobs/{id}/cancel`) to a cancel affordance; distinguish "no core picked" vs "decomposing" vs "0 matched" vs "failed"; the counts banner is already honest ("M matched of N"). Heatmap already shows the "top 30 of N" truncation note.

### 4. Domain-model deviation note  *(tiny; docs only)*
`docs/domain-model/04-sar-analysis.md` does **not** mention `RGroupDecompositionRun` or `SarActivityProjection` (added as async-job/read-model aggregates in Part 1b/2). Add a short section documenting them (job lifecycle: pending→running→ready/failed/cancelled; membership/channel hashes for cache identity; relationship to the existing fingerprint/Markush aggregates).

### 5. Extract shared SAR activity-display helpers  *(small; followups item #3)*
`rgroup-heatmap.tsx` imports `pickReference`/`potencyShade`/`snapshotFromActivity` from the sibling **component** `rgroup-table.tsx` (a smell). Extract to `features/sar-analysis/lib/sar-activity-display.ts` (pure + tests), import in both; also DRY `snapshotFromActivity` against the duplicate mapping in `research-organization/.../dose-response-cell.tsx`.

### 6. Playwright E2E harness + SAR smoke  *(large; foundational)*
The repo has **no active E2E harness** — `tests/e2e/*.spec.ts.TODO` are stubs (no auth fixture, no seeding). Building it is its own project: auth fixture, seed a collection whose members share a core **and** carry activity, then a smoke: open SAR → core auto-suggests/draw → "Decomposing…" resolves → table shows server rows + footer count → pick activity → "Computing activity…" resolves → activity column appears → sort + number-filter (rows update) → switch to Heatmap → cells render → click a cell → curve dialog. If activity seeding is hard, ship the decomposition+sort+filter smoke first and note the rest.

### 7. GitHub board update  *(tiny)*
Update the SAR items on the project board (https://github.com/users/sidxz/projects/4) to reflect Unit A+B done, Unit C scoped.

---

## Test coverage shape (so you don't re-test what's covered)
BE: reader integration (`tests/integration/persistence/sar_analysis/test_decomposition_row_reader.py`) + API (`tests/api/test_sar_activity_projection_routes.py`, `test_sar_analysis_routes.py`). FE: hook tests per hook, component **pure-helper** tests (`rgroup-table`/`rgroup-heatmap`), a `sar-view` orchestration smoke, `ag-filter-model`, `data-grid.infinite`. Full component **render-flow** is intentionally deferred to the E2E (item 6). Reference: `docs/backlog/sar-workbench-frontend-followups.md` (Unit-B note + deferrals) and the Unit-B plan/spec (`docs/superpowers/{plans,specs}/2026-06-15-sar-unit-b-frontend-swap*.md`).
