# V3 — UMAP Cluster Map + Diversify Picker (Design)

**Status:** Draft, awaiting user review.
**Branch target:** `prot-2` (or successor after V2 ships).
**Predecessor:** `2026-05-17-scaffold-tree-v2-design.md` — V3 mirrors its infrastructure pattern (jobs table + Temporal workflow + Postgres-as-cache + split-pane FE view-mode).
**Deferral:** Heatmap view (`HeatmapView` from the V2 handoff) is **out of scope**. If chemists ask, it gets its own spec.

---

## 1. Goal

Give chemists a chemical-space map of any collection or search result with two terminal actions:

- **Lasso a region** → "save as new collection".
- **Diversify N** → algorithmic representative selection (MaxMin or Butina) → "save N representatives as new collection".

Both flows can compose: lasso first, then Diversify within the lassoed region.

---

## 2. User-visible surface

### 2.1 Entry points

New view-mode `?view=clusters` slotted into the existing toolbar segmented control on:

- `/collections/{id}` — compound-set is the collection's members (`useCollectionSearch`).
- `/search` — compound-set is the current search-criteria results.

The toggle becomes a 4-segment control: `List | Grid | Scaffold | Cluster`. Disabled with tooltip "Need ≥ 10 compounds for a meaningful map" if N < 10 in the compound-set.

### 2.2 Layout

**Split-pane**, mirroring scaffold-tree V2:

- **Left pane (~70%):** Plotly scatter (UMAP coords). Hover = tooltip with struct thumb + ID + name; click = full compound detail in a side sheet.
- **Right pane (~30%):** `CardGrid` of currently-selected compounds (defaults to all in the compound-set when no selection is active).

Resizable divider, min 20% / max 50% left, matching V2's settings.

### 2.3 Toolbar

Left-to-right:

```
[Color by ▼]  [Picker: MaxMin ▼]  [N: 50 ↕]  [Diversify]  [Save selection (12)]
```

When `Picker=Butina`, `N` field swaps to `Threshold: 0.4` (slider 0.2–0.8 Tanimoto distance).

**Color by** dropdown items:
- `Cluster` — categorical palette per cluster ID.
- `Activity` — sub-dropdown picks a protocol; encoding reuses the search-grid's 4-bin pIC50 classification (red → amber → orange → emerald). Inactive → solid grey. ND / no curve → hollow ring (no fill, dotted outline). Tooltip on hover names the bin.
- `Scaffold` — Bemis-Murcko bucket id → scaffold palette (reuses V2's coloring).
- `None` — uniform muted grey.

### 2.4 Selection markers

- **Lasso polygon** outline drawn while lasso is active; lassoed points get a thin yellow outline; non-lassoed points fade to 0.35 opacity.
- **Diversify picks** render as **star markers** (white-outlined) overlaid on the colored fill. Stars persist alongside any color-by choice.

### 2.5 Save-as-collection flow

`[Save selection]` button → **modal preview**:

- Header: "Save N compounds as a new collection".
- Body: scrollable grid of compound cards (struct + ID + name); name input pre-filled (e.g. "Diversify-50 from <source-collection-name>"); project picker (default: source collection's project, or "Workspace" on `/search`).
- Buttons: `[Save & open]` (primary) / `[Cancel]`.

On confirm:
1. `POST /api/v1/collections` with the molecule list + name + project_id.
2. Toast: "Collection created".
3. Redirect to `/collections/{new-id}?view=clusters` (the new collection inherits the cluster-map view-mode for immediate continuation).

### 2.6 URL state

- `?view=clusters` (locked).
- `?picker=maxmin&n=50` OR `?picker=butina&t=0.4`.
- `?color=cluster|activity|scaffold|none`.
- If `color=activity`, also `&color-protocol=<uuid>`.
- Lasso polygon is NOT in URL (ephemeral, cleared on refresh).

---

## 3. Defaults

| Knob | Default | Rationale |
|---|---|---|
| Picker | MaxMin | Industry standard for diverse subset selection (RDKit MaxMinPicker docs); no tuning. |
| N (MaxMin) | 50 | Common diverse-subset size in medchem reports. |
| Threshold (Butina) | 0.4 Tanimoto distance (≈ 0.6 similarity) | RDKit Butina chemistry convention for ECFP4-like fingerprints. |
| UMAP `n_neighbors` | 15 | Industry default; balanced local-vs-global. |
| UMAP `min_dist` | 0.1 | Compact clusters; readable scatter. |
| UMAP metric | `jaccard` | Equivalent to Tanimoto on binary FPs; built into umap-learn. |
| Color by | Activity if DR columns present (auto-protocol = pinned protocol if search criteria pin one, else first available); Cluster otherwise. | Matches chemist context. |

None of UMAP n_neighbors/min_dist/metric is chemist-tunable in V3. Add if asked.

---

## 4. Backend architecture

Mirrors `scaffold-tree V2` exactly. All new code lives in the existing `sar_analysis` bounded context.

### 4.1 Domain (`backend/src/cellar/domain/sar_analysis/`)

- `umap_job.py` — `UmapJob` aggregate with state machine (`pending → running → ready | failed | cancelled`), version column for optimistic concurrency.
- `umap_types.py` — `UmapPoint`, `ClusterAssignment`, `RepresentativePick`, `UmapResult` dataclasses (pure Python).

### 4.2 Application (`backend/src/cellar/application/sar_analysis/`)

- `repositories.py` (extend) — `UmapJobRepository` protocol with `find_cached(ids_hash, picker, picker_param_hash, ttl_seconds)`.
- `compute_umap_cluster.py` — pure runner: takes fingerprints + picker config, returns `UmapResult`. Composed of:
  - `umap_embed(fps)` → 2D coords.
  - `butina_cluster(fps, threshold)` → cluster ids (always run, used for `color=cluster` even when picker=maxmin).
  - `maxmin_pick(fps, n)` OR `butina_pick(fps, clusters)` → representative indices.
- `start_umap_cluster_job.py` — sync/async dispatch. ≤ 500 mols → run inline + persist as `READY` job (next call hits cache); > 500 → schedule Temporal workflow + return `PENDING` job.
- `get_umap_cluster_job.py` / `cancel_umap_cluster_job.py` — polling + cancellation.
- `run_umap_cluster.py` — the function the Temporal activity calls.

### 4.3 Infrastructure

- `infrastructure/rdkit/umap_embedder.py` — wraps `umap-learn` with our metric/param defaults. New dependency: `umap-learn` (`uv add umap-learn` — pulls `numba` + `pynndescent`).
- `infrastructure/rdkit/butina_clusterer.py` — wraps `rdkit.ML.Cluster.Butina.ClusterData` + medoid picker.
- `infrastructure/rdkit/maxmin_picker.py` — wraps `rdkit.SimDivFilters.MaxMinPicker.LazyBitVectorPick`.
- `infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_repository.py` — Postgres impl with `find_cached`.
- `infrastructure/temporal/workflows/umap_cluster.py` + `activities/umap_cluster.py` + `orchestrators/umap_cluster.py` — mirrors scaffold-tree's orchestrator triad.
- `infrastructure/di/_sar_analysis.py` (extend) — register the new use cases + repo + orchestrator.

### 4.4 Interface (`backend/src/cellar/interface/routes/umap_cluster.py`)

- `POST /api/v1/sar/umap-cluster` — body `{collection_id?: UUID, molecule_ids?: UUID[], picker: "maxmin" | "butina", n?: int, threshold?: float}`. Validation: exactly one of `collection_id` / `molecule_ids`; `n` required iff `picker=maxmin`; `threshold` required iff `picker=butina`. Responses: `200 {result, job: null}` cache-hit-or-sync, `202 {result: null, job: {...}}` async.
- `GET /api/v1/sar/umap-cluster/jobs/{id}` — polling.
- `POST /api/v1/sar/umap-cluster/jobs/{id}/cancel` — cancellation.

### 4.5 Migration `039_umap_jobs.py`

```sql
CREATE TABLE umap_jobs (
  id UUID PRIMARY KEY,
  workspace_id UUID NOT NULL,
  ids_hash TEXT NOT NULL,
  picker TEXT NOT NULL CHECK (picker IN ('maxmin', 'butina')),
  picker_params JSONB NOT NULL,
  picker_param_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','running','ready','failed','cancelled')),
  result_json JSONB,
  error TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX umap_jobs_cache
  ON umap_jobs (ids_hash, picker, picker_param_hash, completed_at DESC)
  WHERE status = 'ready';

CREATE INDEX umap_jobs_workspace ON umap_jobs (workspace_id, requested_at DESC);
```

### 4.6 Caching

- Cache key: `(ids_hash, picker, picker_param_hash)`.
- TTL: 1 hour from `completed_at`.
- Cache lookup: `WHERE status='ready' AND completed_at > now() - interval '1 hour' ORDER BY completed_at DESC LIMIT 1`.
- The sync path persists every successful run as `READY` — so the next identical call is a cache hit.

**Deferred:** a two-layer cache that re-uses UMAP coords across different picker configs is V3.1. For V3 ship, whole-result caching is sufficient.

### 4.7 Dispatch thresholds

- **N ≤ 500 mols:** sync UMAP + Butina + picker, return inline.
- **N > 500 mols:** dispatch Temporal workflow, return 202 with job id. FE polls.
- Activity timeout: 30 min start-to-close, 3 retries (mirrors `ExportWorkflow`).
- `TEMPORAL_DISABLED=1` → `NullUmapClusterOrchestrator` runs inline (test env).

### 4.8 Validation + edge cases

- Compound-set size < 10 → 400 with `{detail: "Need at least 10 molecules for UMAP."}`.
- Compound-set size > 50,000 → 400 with `{detail: "Cluster map capped at 50k molecules; refine the filter."}`. (Performance bound; revisit when chemists actually hit it.)
- Molecules without Morgan fingerprints (corrupted structures) → skip with a warning, log count in `result.warnings`.
- Duplicate molecule_ids in body → dedupe silently.

---

## 5. Frontend architecture

All new code under `frontend/src/features/sar-analysis/`.

### 5.1 Files

| File | Purpose |
|---|---|
| `types/index.ts` (extend) | `UmapPoint`, `ClusterAssignment`, `RepresentativePick`, `UmapResult`, `UmapJob` |
| `hooks/use-umap-cluster.ts` | Sync + async poll (mirrors `useScaffoldTree`) |
| `lib/use-picker-config.ts` | URL state `?picker=maxmin&n=50` / `?picker=butina&t=0.4` |
| `lib/use-color-mode.ts` | URL state `?color=...&color-protocol=...` |
| `lib/cluster-palette.ts` | Categorical palette + activity gradient + scaffold palette adapter |
| `lib/lasso-math.ts` | Point-in-polygon helper |
| `components/cluster-map-view.tsx` | Top-level split-pane composition |
| `components/cluster-scatter.tsx` | `react-plotly.js` wrapper, lasso event handler, custom modebar (`lasso2d` + `pan2d` only) |
| `components/cluster-toolbar.tsx` | All toolbar controls (color, picker, N/threshold, Diversify, Save) |
| `components/color-mode-picker.tsx` | Color-by dropdown + protocol sub-picker |
| `components/cluster-selection-pane.tsx` | Right pane (CardGrid variant aware of current selection) |
| `components/save-selection-dialog.tsx` | Modal preview before save |

### 5.2 ResultsSurface wiring

Add `view === "clusters"` branch to `ResultsSurface` alongside the existing `tree | cards | table` branches. Passes `collectionId` (when available) the same way V2 does.

### 5.3 View-mode toggle extension

`useViewMode` enum gains `"clusters"`. `view-mode-toggle.tsx` adds a `Cluster` segment (Lucide `ScatterChart` icon + "Cluster" label, label hides on narrow screens).

### 5.4 Local state

- `lassoPolygon: Point[] | null` — set on Plotly's `onSelected`.
- `selectedIds: Set<UUID>` — derived. Logic:
  - No lasso, no diversify → empty.
  - Lasso only → IDs in polygon.
  - Diversify only → picks from `umapResult.representatives`.
  - Lasso + diversify (composed flow) → diversify request's `molecule_ids` body was scoped to lassoed subset; `selectedIds = picks`.
- `previewOpen: boolean` — controls save-dialog visibility.

### 5.5 Server-side diversify-on-subset

When a lasso is active and the chemist clicks `Diversify`, the request body's `molecule_ids` is scoped to the lassoed subset. Cache key includes that subset's `ids_hash`, so refining N on the same lasso re-hits cache.

### 5.6 Plotly integration

- Library: `react-plotly.js` (already in deps — see `dose-response-figure.tsx`).
- Trace: `Scattergl` mode `markers` (WebGL for 5K+ points smoothness).
- Modebar: pruned to `lasso2d` + `pan2d` only.
- Hover template: thumbnail + id + name; depiction comes from existing `/api/v1/molecules/{id}/depiction` endpoint, image already cached per mol.
- Representatives: a second `Scattergl` trace overlaid, marker `symbol="star"`, larger size, white outline.

### 5.7 Loading state

"Computing cluster map…" caption with a thin progress indicator; identical visual to scaffold-tree's loading. After 3s, Sonner toast offering `[Cancel]` (which calls the cancel endpoint).

---

## 6. Testing strategy

### 6.1 Backend (`tests/unit/...`)

- Domain: `UmapJob` state machine transitions + invalid transition rejection.
- Application:
  - `compute_umap_cluster` — golden tests on known small molecule sets (e.g. 20 quinazolines from fixture); assert deterministic embedding (fix `random_state=42`).
  - `maxmin_pick` — assert N picks returned, no duplicates, includes first compound (MaxMin convention).
  - `butina_pick` — assert one medoid per cluster, cluster count varies with threshold.
  - `start_umap_cluster_job` — sync path persists READY job; async path returns PENDING + dispatches; cache-hit path skips dispatch.
- Infrastructure: repo `find_cached` honors TTL + picker_param_hash; partial index used.

### 6.2 API integration (`tests/api/`)

- `POST /api/v1/sar/umap-cluster` happy paths (sync small; async large via TEMPORAL_DISABLED=1 + NullOrchestrator).
- Validation errors: <10 mols, >50K mols, missing N when picker=maxmin, etc.
- Cancel endpoint idempotency on terminal states.

### 6.3 Frontend (`tests/...`)

- `useUmapCluster` — sync return + async polling state transitions (mock `startFn` / `pollFn`).
- `usePickerConfig` / `useColorMode` — URL ↔ state round-trip.
- `lasso-math.pointInPolygon` — unit cases (inside, outside, on boundary, concave polygon).
- `ClusterScatter` — renders Plotly with expected trace shape (mock `react-plotly.js`).
- `ClusterToolbar` — toggling picker swaps N ↔ threshold input; Diversify button disabled while no compound-set; Save button shows live count.
- `SaveSelectionDialog` — submit calls collection-create with the right payload.

### 6.4 Smoke checklist (post-implementation)

1. Open a 50-mol collection → switch to `Cluster` view → scatter renders within ~2s; tooltips show thumbnails.
2. Same collection → click `Diversify` (N=10) → 10 stars appear; right pane filters to 10.
3. Save 10 as new collection → redirected to new collection → new collection has those 10.
4. Open a 5K-mol collection → switch to `Cluster` → "Computing…" caption ~20s on cold cache; <500ms on second open.
5. Lasso a region of ~200 points → counter updates → `N=20` → `Diversify` → 20 stars within polygon.
6. Save the 20 → modal preview shows them → save → new collection.
7. Switch color-by from `Cluster` to `Activity (Mtb_WCA)` → scatter recolors with gradient; star overlay persists.
8. Deep-link `?view=clusters&picker=butina&t=0.3&color=scaffold` → page loads in that exact state.
9. Try opening a 5-mol collection → `Cluster` segment is disabled with tooltip.

---

## 7. Diagnostic anchors (for the implementer)

- `frontend/src/features/sar-analysis/components/cluster-map-view.tsx::ClusterMapView` — split-pane composition + selection state owner.
- `frontend/src/features/sar-analysis/hooks/use-umap-cluster.ts::useUmapCluster` — single SoT for sync vs async path.
- `backend/src/cellar/application/sar_analysis/start_umap_cluster_job.py::StartUmapClusterJob` — dispatch + cache-write.
- `backend/src/cellar/application/sar_analysis/compute_umap_cluster.py::ComputeUmapCluster` — pure runner consumed by both sync path and Temporal activity.
- `backend/src/cellar/infrastructure/rdkit/umap_embedder.py::UmapEmbedder` — only place UMAP params are pinned.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/umap_job_repository.py::find_cached` — partial-index-served cache lookup.

---

## 8. Out of scope (V3.1+)

- Heatmap view (compound × protocol grid).
- UMAP parameter knobs (n_neighbors, min_dist, metric).
- FCFP fingerprint switch.
- Two-layer cache (UMAP coords reused across picker configs).
- k-medoids picker on UMAP coords.
- Cross-collection cluster maps (multiple compound-sets overlaid).
- Pre-compute on collection-membership change.

---

## 9. Acceptance criteria

- All 9 smoke-checklist items pass.
- New BE unit tests + API tests green, no regression in existing 2611+ test suite.
- New FE tests green, `pnpm exec tsc --noEmit` clean.
- Cluster view-mode is disabled for collections with < 10 compounds.
- Cold-cache compute time for a 5K-compound collection: < 30s end-to-end.
- Warm-cache response: < 500ms.
- URL state round-trips cleanly.
