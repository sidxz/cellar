# Scaffold Tree V2 — Design

Date: 2026-05-17
Branch: `prot-2`
Parent design: `/Users/sidx/.claude/plans/lets-look-at-our-lazy-nygaard.md` (V2 section)
Predecessor: Collections V1 + V1.5 (shipped on `prot-2`, smoke pending)

---

## Goal

Add a `scaffold-tree` view mode to `/collections/{id}` (and, by extension, `/search`) so chemists can navigate a molecule set by Bemis-Murcko scaffold hierarchy. Tree on the left, the existing card grid (filtered to the selected node's subtree) on the right. Default no color; explicit per-protocol color picker. No artificial size cap — async-with-polling for sets large enough to exceed the sync budget. Caches by sorted-mol-id hash.

Headline chemist value: "what scaffolds are in this collection, and how does activity track across the tree" — find a SAR series in three clicks.

---

## Scope

### In scope (V2 MVP)

- Migration 037 — `bemis_murcko_smiles TEXT NULL` on `molecule`.
- `MurckoScaffoldCalculator` in `infrastructure/rdkit/` wrapping `Chem.Scaffolds.MurckoScaffold.MurckoScaffoldSmiles`.
- `RegisterMolecule` computes scaffold at registration (mirrors the existing fingerprint path).
- One-shot idempotent backfill script: `backend/scripts/backfill_bemis_murcko.py`.
- `BuildScaffoldNetwork` use case in `application/sar_analysis/` — wraps RDKit `rdScaffoldNetwork.CreateScaffoldNetwork`. Pure-structural payload (no activity rollup).
- Migration 038 — `scaffold_tree_jobs` (async pipeline; mirrors `export_jobs`).
- `ScaffoldTreeJob` aggregate + repo + Temporal workflow + activity.
- Endpoint `POST /api/v1/scaffold-tree` — sync on cache-hit or ≤500 mols, async otherwise.
- Endpoint `GET /api/v1/scaffold-tree/jobs/{id}` — poll job status / fetch result.
- Postgres-as-cache via `scaffold_tree_jobs.result_json` + `ids_hash` lookup, 1 h TTL via a `completed_at` WHERE clause. (Valkey isn't wired into the Python codebase yet; pivoting to Postgres keeps V2 from expanding scope. Move to Valkey in a follow-up once another feature needs it.)
- `ScaffoldTreeView` FE component — split-pane (resizable, persisted), recursive tree, color-by-protocol dropdown, right-pane `CardGrid` reuse.
- View-mode hook extension: `"table" | "cards" | "scaffold-tree"`; URL form `?view=tree`.
- View-mode toggle: third segment with fork-down icon.
- `useScaffoldTree` FE hook — handles sync + async transparently, mirrors `useExport`'s polling shape.
- Sonner-based "Computing scaffold tree" toast for long-running async jobs (reuses `ExportJobToast` patterns).

### Deferred (V2.1 or later)

- Precompute scaffold trees on collection-membership change (Temporal event handler). Solves the "first chemist pays the cost on a 10K collection" tax. Add only if chemists complain about first-load toasts on big collections.
- `GET /api/v1/molecules/{id}/scaffold` molecule-detail endpoint. Not needed — `Molecule.bemis_murcko_smiles` ships on every existing molecule response.
- Scaffold filter row in `SearchQueryBuilder` ("compounds with scaffold X"). Cheap follow-up once the column lands.
- Scaffold chip on `MoleculeCard`. Subject to the locked V1.5 card-density rule — only land if it earns the space.
- Rollup-stat toggle (median vs mean vs hit-rate). Default median; expose toggle only if asked.
- Node-only vs subtree right-pane toggle. Default subtree (industry convention); add toggle if chemists ask.
- BE-side activity rollup in the scaffold-tree response. Today the FE computes it from `activityData`; if a future portfolio surface needs the rollup pre-baked, add then.
- Save-subtree-as-collection action (lives with V3's cluster-map lasso).

### Out of scope (separate projects)

- V3 cluster map (UMAP + Butina).
- V3 property heatmap.
- Crystallographer / 3D / crystal-form features.
- Scaffold-tree on standalone `/search` (will land as a follow-up once the V2 view-mode toggle is hoisted onto `/search` — itself a V1.5 leftover).

---

## Architecture

### Layer placement

| Layer | Module | What it does |
|---|---|---|
| Domain | `domain/sar_analysis/scaffold_tree_job.py` | `ScaffoldTreeJob` aggregate + state machine |
| Domain | `domain/chemical_registration/molecule.py` | Add `bemis_murcko_smiles: str \| None` |
| Application | `application/sar_analysis/build_scaffold_network.py` | `BuildScaffoldNetwork` use case (pure compute, cache-aware) |
| Application | `application/sar_analysis/start_scaffold_tree_job.py` | Start-or-return-cached |
| Application | `application/sar_analysis/get_scaffold_tree_job.py` | Job polling |
| Infrastructure | `infrastructure/rdkit/scaffold_calculator.py` | `MurckoScaffoldCalculator` |
| Infrastructure | `infrastructure/rdkit/scaffold_network_builder.py` | Wraps `rdScaffoldNetwork.CreateScaffoldNetwork` |
| Infrastructure | `infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py` | Repo |
| Infrastructure | `infrastructure/temporal/workflows/scaffold_tree.py` | `ScaffoldTreeWorkflow` |
| Infrastructure | `infrastructure/temporal/activities/scaffold_tree.py` | Activity invoking `BuildScaffoldNetwork` |
| Infrastructure | `infrastructure/temporal/orchestrators/scaffold_tree.py` | Real + Null orchestrator (mirror export pattern) |
| Infrastructure | `infrastructure/di/_sar_analysis.py` | Lagom registration for all of the above |
| Interface | `interface/routes/scaffold_tree.py` | `POST /api/v1/scaffold-tree` + `GET /api/v1/scaffold-tree/jobs/{id}` |

Frontend:

| Path | What it does |
|---|---|
| `features/sar-analysis/components/scaffold-tree-view.tsx` | Top-level split-pane component |
| `features/sar-analysis/components/scaffold-tree-node.tsx` | Single recursive tree-row component |
| `features/sar-analysis/components/scaffold-color-picker.tsx` | "Color by:" dropdown |
| `features/sar-analysis/hooks/use-scaffold-tree.ts` | Sync-or-poll wire hook |
| `features/sar-analysis/lib/scaffold-rollup.ts` | Pure rollup functions |
| `features/sar-analysis/lib/scaffold-tree-math.ts` | Subtree-membership helpers + tree traversal |
| `features/research-organization/lib/use-view-mode.ts` | Extend `ViewMode` union + URL serialization |
| `features/research-organization/components/results/view-mode-toggle.tsx` | Add third segment |
| `features/research-organization/components/results/results-surface.tsx` | Add third dispatch branch |

### Bounded-context dependencies

- `sar_analysis` adds a hard import on `domain.chemical_registration.Molecule` (read-only — for `id` + `smiles` + `bemis_murcko_smiles`). Same pattern that `application.research_organization.execute_search` already uses. Allowed.
- `sar_analysis` does NOT depend on `screening_assay` — activity rollup is FE-only.
- `temporal/workflows/scaffold_tree.py` follows the existing `ExportWorkflow` shape (one activity, no continue-as-new — single network compute fits in one activity invocation up to ~1 min).

---

## Data layer — migration 037

```sql
ALTER TABLE molecule
  ADD COLUMN bemis_murcko_smiles TEXT NULL;
-- No index. Add B-tree later if a "filter by scaffold" criterion lands.
```

Three states distinguished by NULL semantics:

- `NULL`: not yet computed (pre-backfill row).
- `""` (empty string): acyclic — RDKit `MurckoScaffoldSmiles` convention for no-ring compounds.
- non-empty SMILES: computed scaffold.

The empty-string case becomes the virtual "no scaffold" bucket in the tree. NULL rows are silently excluded from tree compute (so backfill-in-progress doesn't break the UX — empty bucket just looks artificially small until backfill catches up).

---

## Registration pipeline

```python
# infrastructure/rdkit/scaffold_calculator.py

class MurckoScaffoldCalculator:
    def compute(self, mol: Mol) -> str | None:
        try:
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            return scaffold  # "" for acyclic; canonical SMILES otherwise
        except Exception as exc:
            logger.warning("scaffold_compute_failed", smiles=Chem.MolToSmiles(mol), exc=str(exc))
            return None
```

`StructureProcessor.process(smiles)` invokes the calculator after sanitization and adds `bemis_murcko_smiles: str | None` to `ProcessedStructureDTO`.

`RegisterMolecule._register_disclosed` gains exactly one line:

```python
mol.bemis_murcko_smiles = processed.bemis_murcko_smiles
```

Placed adjacent to the existing `mol.morgan_fp = processed.fingerprints.morgan` assignment.

Failure mode: scaffold compute exception is non-fatal — registration succeeds with `bemis_murcko_smiles = None`. Backfill (or a follow-up registration edit) can re-attempt.

---

## Backfill script

```python
# backend/scripts/backfill_bemis_murcko.py — async, batched, idempotent
```

- Selects mols with `bemis_murcko_smiles IS NULL`.
- Batches of 500.
- For each batch: parse SMILES → compute → `UPDATE molecule SET bemis_murcko_smiles = $1 WHERE id = $2`.
- Logs per-batch progress (mol count, elapsed, success/fail counts).
- Idempotent: re-running picks up exactly the rows that remain NULL.
- Mirrors `backend/scripts/rebuild_campaign_curve_snapshots.py` shape.

---

## BuildScaffoldNetwork use case

### Inputs

```python
@dataclass(frozen=True)
class BuildScaffoldNetworkInput:
    molecule_ids: list[UUID]
```

### Output (wire shape)

```python
@dataclass(frozen=True)
class ScaffoldTreeNode:
    scaffold_smiles: str  # canonical SMILES, OR "__no_scaffold__" for acyclic bucket
    molecule_ids: list[UUID]  # mols whose Bemis-Murcko equals this scaffold exactly
    molecule_count: int  # len(molecule_ids)
    subtree_molecule_count: int  # mols in this node OR descendants

@dataclass(frozen=True)
class ScaffoldTreeEdge:
    parent_smiles: str
    child_smiles: str

@dataclass(frozen=True)
class ScaffoldTreeResult:
    nodes: list[ScaffoldTreeNode]
    edges: list[ScaffoldTreeEdge]
    stats: ScaffoldTreeStats  # node_count, elapsed_ms, cache_hit, sync_path

@dataclass(frozen=True)
class ScaffoldTreeStats:
    node_count: int
    elapsed_ms: int
    cache_hit: bool
    truncated: bool = False  # reserved; always False in V2
```

### Pipeline

1. Sort and hash `molecule_ids` → `ids_hash = sha256(",".join(sorted(str(id) for id in molecule_ids)))`.
2. Cache lookup: `SELECT result_json FROM scaffold_tree_jobs WHERE ids_hash = $1 AND status = 'ready' AND completed_at > NOW() - INTERVAL '1 hour' ORDER BY completed_at DESC LIMIT 1`. On hit → deserialize + return with `cache_hit=True`.
3. Single-query fetch: `SELECT id, smiles, bemis_murcko_smiles FROM molecule WHERE id IN (...)`. Drop rows with `smiles IS NULL` (defensive; shouldn't happen).
4. Build `rdkit_mols: list[Mol]` from SMILES. Track failures (log; exclude from network).
5. Bucket acyclic mols (`bemis_murcko_smiles == ""`) separately → single virtual node `__no_scaffold__` with `molecule_ids=[...]`.
6. For ringed mols: `network = rdScaffoldNetwork.CreateScaffoldNetwork(mols, ScaffoldNetworkParams())`.
7. Walk `network.nodes` + `network.edges`. For each node:
   - `scaffold_smiles = node` (RDKit returns canonical SMILES strings).
   - `molecule_ids` — the mols whose `bemis_murcko_smiles` equals this scaffold. Computed by indexing the input mols by their stored Bemis-Murcko scaffold (NOT by re-traversing the network — the BE-stored scaffold is the ground truth for membership; the network is the hierarchy).
   - `molecule_count = len(molecule_ids)`.
   - `subtree_molecule_count` — DFS down the edge graph, summing `molecule_count` of descendants + self.
8. Return (caller — the workflow activity or the sync route — is responsible for inserting the cache row into `scaffold_tree_jobs` with `status='ready'` + `result_json=<serialized>`).

### Membership semantics

A molecule "belongs" to its Bemis-Murcko scaffold node only. The subtree count for an ancestor node is the sum of its own members plus all descendant nodes' members. This matches chemist intuition ("compounds at or below this scaffold").

The "no scaffold" bucket is a leaf at the root; it has no parent and no children.

### Errors

- `BuildScaffoldNetworkError(SmilesParseFailed)` if all SMILES fail to parse → 502.
- `BuildScaffoldNetworkError(NetworkBuildFailed)` if RDKit raises during `CreateScaffoldNetwork` → 502 with offending mol IDs in error body. (Empirically rare; only seen with extreme charged species or sanitization-resistant structures.)
- Empty `molecule_ids` → `ScaffoldTreeResult(nodes=[], edges=[], stats=...)`. 200.

---

## Async pipeline (Temporal)

### ScaffoldTreeJob aggregate

```python
@dataclass
class ScaffoldTreeJob:
    id: UUID
    requested_by: UUID  # user_id
    workspace_id: UUID
    ids_hash: str  # cache key — sha256(sorted_ids)
    requested_at: datetime
    status: ScaffoldTreeJobStatus  # pending | running | ready | failed | cancelled
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    result: ScaffoldTreeResult | None  # populated on ready; serialized to JSONB

    def mark_running(self, now: datetime) -> ScaffoldTreeJob: ...
    def mark_ready(self, result: ScaffoldTreeResult, now: datetime) -> ScaffoldTreeJob: ...
    def mark_failed(self, error: str, now: datetime) -> ScaffoldTreeJob: ...
    def mark_cancelled(self, now: datetime) -> ScaffoldTreeJob: ...
```

State machine same as `ExportJob`: `pending → running → {ready | failed | cancelled}`.

### Migration 038

```sql
CREATE TABLE scaffold_tree_jobs (
    id UUID PRIMARY KEY,
    requested_by UUID NOT NULL,
    workspace_id UUID NOT NULL,
    ids_hash TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,  -- pending | running | ready | failed | cancelled
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    result_json JSONB,  -- populated when status = 'ready'; doubles as cache
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX scaffold_tree_jobs_workspace_status ON scaffold_tree_jobs (workspace_id, status);
CREATE INDEX scaffold_tree_jobs_requested_by_at ON scaffold_tree_jobs (requested_by, requested_at DESC);
-- The cache-lookup query (ids_hash + ready + completed_at > NOW() - 1h) is served by this partial index:
CREATE INDEX scaffold_tree_jobs_cache ON scaffold_tree_jobs (ids_hash, completed_at DESC) WHERE status = 'ready';
```

### Workflow

```python
# infrastructure/temporal/workflows/scaffold_tree.py

@workflow.defn
class ScaffoldTreeWorkflow:
    @workflow.run
    async def run(self, job_id: UUID, molecule_ids: list[UUID]) -> None:
        await workflow.execute_activity(
            "run_scaffold_tree",
            args=[job_id, molecule_ids],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
```

Activity (`infrastructure/temporal/activities/scaffold_tree.py`) calls `BuildScaffoldNetwork.execute(...)`, then marks the `ScaffoldTreeJob` as ready (or failed) via the repo.

Cancellation: workflow cancellation handler flips the job to `cancelled`.

### Orchestrator (mirrors export)

```python
# infrastructure/temporal/orchestrators/scaffold_tree.py

class ScaffoldTreeOrchestrator(Protocol):
    async def schedule(self, job_id: UUID, molecule_ids: list[UUID]) -> None: ...
    async def cancel(self, job_id: UUID) -> None: ...

class TemporalScaffoldTreeOrchestrator: ...
class NullScaffoldTreeOrchestrator:
    """In-process fire-and-forget for tests/dev (TEMPORAL_DISABLED=1)."""
```

---

## Endpoint design

### `POST /api/v1/scaffold-tree`

**Request:**
```json
{ "molecule_ids": ["uuid-1", "uuid-2", ...] }
```

**Sync-path response (200):** cache hit OR `len(molecule_ids) ≤ 500`:
```json
{
  "tree": { /* ScaffoldTreeResult */ },
  "job": null
}
```

**Async-path response (202):** cache miss AND `len(molecule_ids) > 500`:
```json
{
  "tree": null,
  "job": {
    "id": "uuid",
    "status": "pending",
    "ids_hash": "..."
  }
}
```

Threshold (500) is a heuristic. Configurable via `CELLAR_SCAFFOLD_TREE_SYNC_LIMIT` env var.

### `GET /api/v1/scaffold-tree/jobs/{job_id}`

Returns:
```json
{
  "id": "uuid",
  "status": "ready" | "running" | "pending" | "failed" | "cancelled",
  "tree": { /* ScaffoldTreeResult */ } | null,  // populated when status == ready
  "error_message": "..." | null,
  "requested_at": "...",
  "completed_at": "..."
}
```

### `POST /api/v1/scaffold-tree/jobs/{job_id}/cancel`

Cancels the workflow. Returns the job with updated status. Mirrors `POST /api/v1/exports/{id}/cancel`.

### Authorization

- Endpoint requires authenticated user (Sentinel JWT, workspace scope).
- `molecule_ids` filtered to the requesting workspace at the SQL fetch step (single `AND workspace_id = $W` predicate). Cross-workspace IDs silently dropped (don't leak existence).
- Job ownership: `GET /jobs/{id}` returns 404 if requester != job.requested_by (loose check; tighten if real cross-user scenarios emerge).

---

## DI wiring (`infrastructure/di/_sar_analysis.py`)

```python
def configure(container: Container) -> None:
    container.define(MurckoScaffoldCalculator, Singleton(MurckoScaffoldCalculator))
    container.define(ScaffoldNetworkBuilder, Singleton(ScaffoldNetworkBuilder))
    container.define(BuildScaffoldNetwork, Singleton(...))

    container.define(SQLAlchemyScaffoldTreeJobRepository, Singleton(...))
    container.define(ScaffoldTreeJobRepository, lambda c: c[SQLAlchemyScaffoldTreeJobRepository])

    if os.getenv("TEMPORAL_DISABLED") == "1":
        container.define(ScaffoldTreeOrchestrator, Singleton(NullScaffoldTreeOrchestrator))
    else:
        container.define(ScaffoldTreeOrchestrator, Singleton(TemporalScaffoldTreeOrchestrator))

    container.define(StartScaffoldTreeJob, Singleton(...))
    container.define(GetScaffoldTreeJob, Singleton(...))
```

`container.py` invokes `_sar_analysis.configure(container)` at bootstrap.

`StructureProcessor` (`_core.py`) gets one new dependency: `MurckoScaffoldCalculator`. Constructor injection.

`tests/api/conftest.py` continues to set `TEMPORAL_DISABLED=1` (already in place from the export pipeline).

---

## Frontend — `ScaffoldTreeView`

### Layout

```
┌─ ScaffoldTreeView ──────────────────────────────────────────────────────┐
│ ┌─ Tree pane (left, resizable, ~360px default) ─┬─ Selection pane ───┐ │
│ │ Color by: [— none —             ▾]            │                    │ │
│ │ ─────────────────────────────────────         │  [CardGrid with     │ │
│ │ ▾ c1ccccc1            (47 / ▒▒▒)              │   molecules         │ │
│ │   ▾ c1ccc2ccccc2c1    (12 / ▒▒░)              │   filtered to the   │ │
│ │     • c1ccc2cc(N)ccc2c1 (3 / ▓▓▓)             │   selected node's   │ │
│ │   ▸ c1ccc2nccnc2c1    (8 / ░░░)               │   subtree]          │ │
│ │ ▸ c1cnc2ccccc2c1      (15 / ▒▒░)              │                    │ │
│ │ ▸ no scaffold          (3)                    │                    │ │
│ └────────────────────────────────────────────────┴───────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Props

```ts
type ScaffoldTreeViewProps = {
  molecules: Molecule[];
  activityData: Record<string, Record<string, ActivityValue>>;
  aggregationRule: SelectionRule;
};
```

### Internal state (URL- and localStorage-backed)

- `selectedNodeSmiles: string | null` — defaults to null (root view = all mols).
- `expandedNodes: Set<string>` — defaults to first-level expanded.
- `colorByProtocolId: string | null` — defaults to null.
- `treePaneWidth: number` — defaults to 360, persisted to `localStorage.scaffoldTreePaneWidth`.

URL state for `colorByProtocolId` only (`?color=<protocol_id>`). Selection state is ephemeral (resets on navigation).

### Tree rendering

- `<ScaffoldTreeNode />` is recursive. Renders:
  - Caret toggle (expanded / collapsed / leaf).
  - 56×56 `<MoleculeThumbnail size="sm" smiles={node.scaffold_smiles} />`. Special case for `__no_scaffold__` — render a `<span>` placeholder ("no scaffold").
  - Label: `(N · subtree_N)` if subtree_N > N, else `(N)`.
  - Color band: 4px-tall horizontal bar at the right edge, colored when `colorByProtocolId` is set.
- Click node → updates `selectedNodeSmiles`.
- Click caret only toggles expanded state (doesn't select).
- Empty tree (no edges, no nodes): "No scaffold information available." (covers backfill-in-progress + all-NULL case).

### Right pane

- `<CardGrid />` with `molecules` filtered to: `selectedNodeSmiles == null ? molecules : molecules.filter(m => subtreeMolIds.has(m.id))`.
- `subtreeMolIds` computed via `scaffold-tree-math.ts::computeSubtreeMembers(node, tree)`.
- **Default (no node selected) — full molecule list in the existing `CardGrid`.** The right pane is the same `CardGrid` component the chemist sees in `cards` view, so flipping to scaffold-tree without picking a node is visually equivalent to staying on cards, with the tree showing as additional navigation on the left.

### View-mode default

- Default view-mode on `/collections/{id}` stays `cards` (unchanged from V1 + V1.5). Scaffold-tree is an opt-in toggle; chemists who don't pick it never see a different default.
- View-mode persists per-user via the existing URL `?view=` + localStorage fallback. A chemist who switches to `?view=tree` and then bookmarks the link arrives back in tree view; the global default never changes.

### Color-by-protocol picker

- Top of the tree pane.
- `<Select />` populated from `activityData` keys (protocol IDs the result set has data for) — empty if no protocols.
- Options:
  - `— none —` (default)
  - Per-protocol entry: `"{protocol.name}"`.
- On change:
  - For each node, compute `nodeMolIds(subtree)` → look up each mol's `activityData[protocol_id]` for the chosen `aggregationRule` → median pIC50 → bin into 4-stop classification (`active_high / active_mid / weak / inactive` matching `InterceptCell`'s existing color scale).
  - Nodes with no data render no color band.

### Loading / async UX

- `useScaffoldTree({molecule_ids})` returns `{tree, isLoading, isComputing, jobId, error}`.
- `isLoading = true` while waiting for HTTP response (sync path) OR while polling (async path).
- `isComputing = true && elapsed > 3s` triggers a Sonner toast: `"Computing scaffold tree — 47 s, 5,234 molecules"` (mirrors `ExportJobToast`).
- Toast has a "Cancel" action that POSTs to `/jobs/{id}/cancel` and reverts the FE to the previous view (or empty).
- On error: toast with the error message + auto-revert to `cards` view.

### Resizable divider

- `react-resizable-panels` (add to `package.json`) — clean keyboard- and touch-accessible split.
- Min tree-pane width: 240px. Max: 720px.

### Empty / oversized states

- Empty mol set: "Add molecules to see the scaffold tree."
- All scaffolds NULL (backfill in progress): "Computing scaffolds for your library — check back in a few minutes."
- Cache-hit + empty tree: "These molecules are all acyclic — no scaffolds to display."

---

## Cross-cutting

### Performance budgets

| Set size | Cache miss | Cache hit |
|---|---|---|
| ≤ 500 mols | < 3 s, sync 200 | < 100 ms |
| 500 – 2,000 mols | ~3–10 s, async 202 + poll (usually 1 poll) | < 200 ms |
| 2,000 – 10,000 mols | ~10–60 s, async + visible toast | < 500 ms |
| > 10,000 mols | ~1–5 min, async + persistent toast | < 1 s |

### Cache invalidation

- Server (Valkey): TTL 1 h. Key includes sorted mol-id hash, so any membership change naturally invalidates.
- React Query: keyed by sorted ID hash with `staleTime: 5 min`. Mutations that change collection membership (`add_to_collection`, `remove_from_collection`) call `queryClient.invalidateQueries(["scaffold-tree"])`.

### Error handling summary

| Failure | Behavior |
|---|---|
| Scaffold compute on registration | Log warning, persist NULL, registration succeeds |
| Backfill failure on a mol | Log, leave NULL, continue next batch |
| Single SMILES parse failure in `BuildScaffoldNetwork` | Log, exclude mol, build tree without it |
| All SMILES fail | 502 `SmilesParseFailed` |
| RDKit network build failure | 502 `NetworkBuildFailed` with offending IDs |
| Workflow activity failure | Activity retries 3×; on exhaustion → job `failed` |
| Workflow timeout | Job `failed` with timeout reason |
| User cancels | Job `cancelled`; FE drops to cards view |

### Testing strategy

**BE unit** (`tests/unit/`):
- `MurckoScaffoldCalculator`: 10 known mol → known scaffold pairs (benzene, ibuprofen, dibenzofuran, biaryl, fused ring, acyclic methane, multi-fragment salt, charged species, complex steroid, peptide).
- `BuildScaffoldNetwork`: hand-crafted 5-mol set with expected nodes + edges + subtree counts. Cache hit/miss. Acyclic bucket. Empty input.
- `ScaffoldTreeJob`: state machine transitions, illegal transitions.
- `StartScaffoldTreeJob`: cache-hit returns tree inline + no job; small set returns tree inline + no job; large set creates job + schedules workflow.

**BE integration** (`tests/integration/`):
- Full repo round-trip on `ScaffoldTreeJobRepository`.
- Backfill script on a 5-mol fixture DB.

**BE API** (`tests/api/`):
- `POST /scaffold-tree` sync path (5 mols).
- `POST /scaffold-tree` async path (>500 mols, NullOrchestrator inline).
- `GET /scaffold-tree/jobs/{id}` lifecycle.
- `POST /scaffold-tree/jobs/{id}/cancel`.
- Cross-workspace mol filtering.

**FE unit** (`*.test.ts`):
- `scaffold-rollup.ts`: median computation with mixed-shape `activityData`, empty/missing data, classification ranges.
- `scaffold-tree-math.ts::computeSubtreeMembers`: tree with multiple parents per node.

**FE component** (`*.test.tsx`):
- `<ScaffoldTreeView />`: renders a known tree, drill into node filters right pane, color-by picker toggles node coloring, async loading state shows skeleton + toast.
- `<ScaffoldTreeNode />`: caret toggle, click selection, color band rendering.
- `useScaffoldTree`: sync-path return, async-path poll loop (mock fetch).
- View-mode toggle: third segment renders, click switches modes, URL updates.

**Smoke** (manual, on `prot-2` dev stack):
- Open a known collection with ≥20 mols across 4+ scaffolds → switch to scaffold view → tree renders with thumbnails + counts.
- Click a leaf → right pane shows that node's mols.
- Click an inner node → right pane shows mols at this scaffold + all descendants (subtree count matches).
- Color by a protocol → tree nodes shade.
- Switch back to cards → state preserved.
- Open a >500-mol collection → "Computing…" toast → tree appears.
- Refresh → cache hit, instant.
- Add a mol to the collection → re-open → cache miss (different hash) → recompute.

### Migration choreography

1. Apply migration 037 (additive column, zero-downtime).
2. Apply migration 038 (`scaffold_tree_jobs` table, additive).
3. Deploy backend with `MurckoScaffoldCalculator` wired into `RegisterMolecule`. New mols start populating `bemis_murcko_smiles`.
4. Run `backend/scripts/backfill_bemis_murcko.py` offline (idempotent; can pause/resume).
5. Deploy frontend with the new view mode.
6. (Optional) Watch logs for scaffold-compute warnings; if a class of compounds reliably fails, file as a follow-up.

---

## Critical files

| File | New / Modified | Phase |
|---|---|---|
| `backend/alembic/versions/037_bemis_murcko_smiles.py` | NEW | BE-data |
| `backend/alembic/versions/038_scaffold_tree_jobs.py` | NEW | BE-async |
| `backend/src/cellar/domain/chemical_registration/molecule.py` | Modified (+1 field) | BE-data |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py` | Modified (+1 column) | BE-data |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py` | Modified (round-trip) | BE-data |
| `backend/src/cellar/infrastructure/rdkit/scaffold_calculator.py` | NEW | BE-data |
| `backend/src/cellar/infrastructure/rdkit/scaffold_network_builder.py` | NEW | BE-compute |
| `backend/src/cellar/infrastructure/rdkit/structure_processor.py` | Modified (+1 step) | BE-data |
| `backend/src/cellar/application/chemical_registration/register_molecule.py` | Modified (+1 line) | BE-data |
| `backend/scripts/backfill_bemis_murcko.py` | NEW | BE-data |
| `backend/src/cellar/domain/sar_analysis/__init__.py` | NEW | BE-async |
| `backend/src/cellar/domain/sar_analysis/scaffold_tree_job.py` | NEW | BE-async |
| `backend/src/cellar/domain/sar_analysis/scaffold_tree_types.py` | NEW (result dataclasses) | BE-compute |
| `backend/src/cellar/application/sar_analysis/__init__.py` | NEW | BE-compute |
| `backend/src/cellar/application/sar_analysis/build_scaffold_network.py` | NEW | BE-compute |
| `backend/src/cellar/application/sar_analysis/start_scaffold_tree_job.py` | NEW | BE-async |
| `backend/src/cellar/application/sar_analysis/get_scaffold_tree_job.py` | NEW | BE-async |
| `backend/src/cellar/application/sar_analysis/cancel_scaffold_tree_job.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/__init__.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/models.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/temporal/workflows/scaffold_tree.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/temporal/activities/scaffold_tree.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/temporal/orchestrators/scaffold_tree.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/di/_sar_analysis.py` | NEW | BE-async |
| `backend/src/cellar/infrastructure/di/container.py` | Modified (+1 import) | BE-async |
| `backend/src/cellar/interface/routes/scaffold_tree.py` | NEW | BE-API |
| `backend/src/cellar/interface/app.py` (or router registry) | Modified (+1 route) | BE-API |
| `frontend/src/features/sar-analysis/types/scaffold-tree.ts` | NEW | FE-types |
| `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts` | NEW | FE-data |
| `frontend/src/features/sar-analysis/lib/scaffold-rollup.ts` | NEW | FE-compute |
| `frontend/src/features/sar-analysis/lib/scaffold-tree-math.ts` | NEW | FE-compute |
| `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` | NEW | FE-component |
| `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx` | NEW | FE-component |
| `frontend/src/features/sar-analysis/components/scaffold-color-picker.tsx` | NEW | FE-component |
| `frontend/src/features/research-organization/lib/use-view-mode.ts` | Modified (+1 mode) | FE-wire |
| `frontend/src/features/research-organization/components/results/view-mode-toggle.tsx` | Modified (+1 segment) | FE-wire |
| `frontend/src/features/research-organization/components/results/results-surface.tsx` | Modified (+1 branch) | FE-wire |
| `frontend/package.json` | Modified (+1 dep: react-resizable-panels) | FE-component |

---

## Reused existing primitives (no new code)

- `MoleculeThumbnail` — scaffold node thumbnails.
- `CardGrid` — right-pane molecule list.
- `DataGrid` / table view — unchanged.
- `useCollectionSearch` — molecule + activity data source (already returns the full enriched payload).
- `AggregationControl` — selection rule for rollup.
- `InterceptCell` color scale — rollup color binning.
- Sonner toast infra — async job toast.
- `useExport` patterns — `useScaffoldTree` polling shape.
- Export-job database conventions — `scaffold_tree_jobs` table mirrors `export_jobs`.
- Temporal workflow / activity / orchestrator scaffolding — direct mirror of export pipeline.
- Lagom DI patterns — `_sar_analysis.py` follows `_research_organization.py` conventions.
- React Query — sync + polling lifecycles.

---

## Open implementation questions (decide during writing-plans)

1. **Scaffold normalization on registration:** RDKit `MurckoScaffoldSmiles` canonicalizes by default. Verify that the same SMILES input always produces the same scaffold output across RDKit versions (defensive: pin RDKit version in pyproject if not already).
2. **Network params:** `rdScaffoldNetwork.ScaffoldNetworkParams()` defaults vs explicit Schuffenhauer settings. Defaults are Schuffenhauer-style; explicit settings give us control. Try defaults first; tune if tree shapes look wrong on chemist smoke.
3. **Workspace scoping enforcement:** confirm `MoleculeRepository.find_by_ids(ids, workspace_id)` is the right method or if it needs to be added. (Existing similar pattern: see `find_by_ids` if it exists; otherwise add.)
4. **React Query cache lifetime:** `staleTime: 5 min` is a guess. Watch behavior on smoke; tune.
5. **Tree-pane default width:** 360px is a guess; tweak post-smoke if it crowds the right-pane on standard laptop screens (1440x900).
6. **Resizable primitive:** check `frontend/src/shared/components/ui/` for an existing shadcn `<Resizable />` install (which already wraps `react-resizable-panels`) before adding a new dep. Reuse if present.

---

## Success criteria

A chemist opens `/collections/{id}` for a 200-mol collection of cyclic compounds, switches to scaffold-tree view, sees a tree with ~20–40 scaffold nodes within 1 s, clicks a node to see ~5 mols in the right pane, picks a protocol from the color-by dropdown, sees node coloring update within 100 ms, switches back to card view with no loss of selection. End to end: < 3 seconds for the entire walk.

For a 5,000-mol collection: same walk, with a "Computing…" toast that disappears within 30 s on first load and is instant on subsequent loads (cache hit).
