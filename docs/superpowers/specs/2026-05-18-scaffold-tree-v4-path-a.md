# V4 Path A — Server-side scaffold-membership filtering

Date: 2026-05-18
Status: ready to implement
Parent: `2026-05-17-scaffold-tree-v4-at-scale.md`
Branch: `prot-2`

---

## 1. Goal

Make the scaffold-tree right pane on `/collections/{id}?view=tree` scale past the existing 10,000-molecule cap WITHOUT loading the full collection into the FE. When a chemist selects a scaffold node (Groups or Hierarchy mode), the right pane re-queries the server with an AND'd `collection + scaffold(s)` criterion and renders only those members.

The "show all" pane (no scaffold selected) keeps loading the full collection atomically — that bottleneck is orthogonal to Path A and stays bounded by `COLLECTION_FETCH_MAX_PAGE_SIZE = 10_000`.

## 2. What's already shipped

- `_scaffold_clause` in `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py` already supports `{type: "scaffold", mode: "exact_match", scaffold_smiles}` end-to-end (Wave 1 / B1, commit `ba6ff1ff`).
- FE `<SearchQueryBuilder>` exposes the scaffold criterion row with draw-and-preview (commits `6cdcb7d2`, `7dba77bc`, `d228a01a`).
- "Open in search" loop closer from scaffold-tree node → `/search?…` (commit `67522973`).
- `molecules.bemis_murcko_smiles` column + backfill (V2 migrations 037 + `backfill_bemis_murcko.py`).

## 3. What's new in V4 Path A

### 3.1 Migration 040 — index on `bemis_murcko_smiles`

```sql
CREATE INDEX ix_molecules_workspace_scaffold
ON molecules (workspace_id, bemis_murcko_smiles)
WHERE bemis_murcko_smiles != '';
```

- **Composite** `(workspace_id, bemis_murcko_smiles)` — every search applies workspace tenancy; one index serves both predicates.
- **Partial** `WHERE bemis_murcko_smiles != ''` — acyclic mols use a different code path (`mode: "acyclic_only"`); excluding them saves disk on a column where ~10-15% of rows are empty.
- Index name follows existing convention `ix_molecules_*`.
- No data backfill — the column is already populated.

### 3.2 New scaffold criterion mode: `exact_match_in`

Existing single-value criterion stays unchanged. New mode accepts a list:

```json
{
  "type": "scaffold",
  "mode": "exact_match_in",
  "scaffold_smiles_list": ["c1ccccc1", "c1ccncc1", "c1ccc2ccccc2c1"]
}
```

**Validation:**
- Each input is canonicalized via `MurckoScaffoldCalculator` (forgiving — accepts full SMILES that resolves to a scaffold).
- Inputs that compute to empty string (acyclic) are dropped silently (caller chooses `acyclic_only` mode for those).
- Duplicates after canonicalization are de-duped.
- Empty post-canonical list → `false_()` (matches nothing). Defensive; FE shouldn't send this.
- Cap: **500** scaffolds per query. Above that → `ValueError`. Rationale: a chemotype-rich Hierarchy subtree on real workloads rarely exceeds dozens; 500 is comfortable headroom and bounds the worst-case `IN` clause.

**BE clause:** `MoleculeModel.bemis_murcko_smiles.in_(canonical_list)`. Hits the new index via index-only scan when combined with the workspace filter (already always applied by the search composer).

### 3.3 FE rewire — scaffold-tree right pane

#### Today

`frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx`:

```ts
const fullCollection = useCollectionSearch({ collectionId });  // loads ALL members
const filteredMolIds = selectedNode
  ? collectSubtreeMolIds(selectedNode, edges)  // in-memory filter
  : null;
const visibleMols = filteredMolIds
  ? fullCollection.items.filter(m => filteredMolIds.has(m.id))
  : fullCollection.items;
```

Right pane atomically loads N mols (silently clipped at 10K), then filters in memory.

#### After Path A

```ts
const selectedScaffolds = useMemo(
  () => deriveSelectedScaffolds(selectedNode, edges, subMode),
  [selectedNode, edges, subMode]
);

const fullCollection = useCollectionSearch({
  collectionId,
  enabled: selectedScaffolds.length === 0,  // skip when filtering
});

const filteredView = useCollectionScaffoldSearch({
  collectionId,
  scaffoldSmiles: selectedScaffolds,
  enabled: selectedScaffolds.length > 0,
});

const visibleMols = selectedScaffolds.length > 0
  ? filteredView.items
  : fullCollection.items;
```

#### `deriveSelectedScaffolds(node, edges, subMode)` semantics

- `node === null` → `[]` (no filter)
- `subMode === "groups"` → `[node.smiles]` (single chemotype)
- `subMode === "hierarchy"` → `collectSubtreeScaffolds(node, edges)` — walks the Schuffenhauer DAG from `node`, returns the set of all scaffold SMILES at + below it (BFS over `(parent → child)` edges, Set-deduped, includes the node itself)

#### `useCollectionScaffoldSearch` hook (new)

Thin wrapper around the same `/api/v1/search/execute` POST that `useCollectionSearch` already uses, but with the body:

```json
{
  "query": {
    "criteria": [
      {
        "type": "group",
        "op": "AND",
        "criteria": [
          { "type": "collection", "collection_id": "..." },
          {
            "type": "scaffold",
            "mode": "exact_match_in",
            "scaffold_smiles_list": ["..."]
          }
        ]
      }
    ]
  }
}
```

Keyed in TanStack Query as `["collection-scaffold-search", collectionId, sortedScaffoldsHash]` so order-of-edge-walk doesn't fragment the cache. Same `useCollectionSearch` pagination defaults (limit 10000 — though in practice filtered results are far smaller).

### 3.4 What does NOT change in this slice

- Tree COMPUTE endpoint (`POST /scaffold-tree`) — still atomically loads the collection's scaffolds. The `BuildScaffoldNetwork` use case dedups via the stored `bemis_murcko_smiles` set; even a 100K-mol collection yields hundreds of distinct scaffolds, well within the path's existing perf envelope.
- The `/search` standalone page — already uses single-value `exact_match`; new mode is additive.
- V3 cluster map — orthogonal.
- "No scaffold selected" right pane on `/collections/{id}?view=tree` — keeps loading via the existing `useCollectionSearch` route; clipping at 10K stands.

## 4. Out of scope (defer or never)

- Pagination / virtualized infinite scroll for the "show all" pane on huge collections.
- Per-scaffold lazy fetch by molecule IDs (V4 Path B).
- Tree-compute scaling beyond 100K mols (would need streaming or pre-compute).
- Cross-collection scaffold queries (overlay multiple compound-sets).
- Pre-compute on collection-membership change.

## 5. Acceptance criteria

1. `EXPLAIN ANALYZE` of a representative `exact_match_in` query on a ≥10K-mol workspace shows an index-scan on `ix_molecules_workspace_scaffold` (not a seq-scan on `molecules`).
2. Opening a 12K-mol collection in tree view → clicking any chemotype in Groups mode → right pane shows only that chemotype's members; the displayed count matches the node's count badge exactly (no silent clipping).
3. Same collection in Hierarchy mode → clicking an inner node → right pane shows the union of its subtree's members; count matches the node's `subtree_molecule_count`.
4. Deselecting (clicking the selected node again or switching back to the empty "show all") returns to the full-collection load; the 10K cap behavior is unchanged.
5. The `/search` page's existing single-value scaffold criterion continues to work; no regression on the Wave 1 / B-series flows.
6. `EXPLAIN ANALYZE` of the existing `exact_match` criterion (single value) ALSO uses the new index.
7. All existing BE tests pass; FE typecheck clean; FE tests for `scaffold-tree-view.tsx`, `useCollectionSearch`, and `scaffold-rows.tsx` continue to pass.

## 6. Testing strategy

### 6.1 Backend (`tests/unit/...`)

- `tests/unit/infrastructure/persistence/sqlalchemy/chemical_registration/test_structure_query_scaffold.py`:
  - `_scaffold_clause` with `mode="exact_match_in"` + valid list → returns `in_()` clause over canonicalized SMILES.
  - Same + caller passes full-molecule SMILES → canonicalized to scaffold.
  - Same + duplicates after canonicalization → dedup before `IN`.
  - Same + entry that canonicalizes to empty string → silently dropped.
  - Same + empty input list → `false_()`.
  - Same + 501-element list → `ValueError`.
  - `mode="exact_match"` single value still works (regression).
- `tests/integration/infrastructure/persistence/sqlalchemy/test_scaffold_index.py`:
  - Migration 040 applies cleanly; the index exists with the expected definition.
  - Optional EXPLAIN-style test on a small seed (or document as a manual perf check).

### 6.2 Frontend (`tests/...`)

- `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts`:
  - Single leaf node → `[node.smiles]`.
  - Inner node in a Schuffenhauer DAG → BFS-walked set, Set-deduped, includes node itself.
  - Cycle-safe (DAG, not tree — multiple parents can converge).
- `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx`:
  - Posts the AND'd group body; query key includes sorted scaffold hash.
  - Disabled when `enabled === false`; switches between hooks cleanly.
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx`:
  - Groups mode: clicking a chemotype invokes the new hook with `[node.smiles]`.
  - Hierarchy mode: clicking an inner node invokes with the full subtree scaffold set.
  - Deselect → falls back to `useCollectionSearch`.

### 6.3 Smoke checklist (post-implementation, browser)

1. Open `/collections/{id}?view=tree` on a 5-mol collection → ensure no regression (Groups + Hierarchy click both work; right pane filters correctly).
2. Open a 900-mol collection (e.g. `large` from prior smoke walkthroughs) → click a chemotype → right pane filters server-side; latency feels comparable or better than the in-memory filter.
3. Open a representative 5K+ mol collection → confirm tree renders; click multiple chemotypes; latency stays well under 1 sec on warm DB.
4. Switch from Groups to Hierarchy on the same collection → click an inner node with N descendants → right pane count matches `subtree_molecule_count`.
5. Click on the currently-selected node to deselect → "show all" pane returns (still 10K-capped — that's by-design).
6. Open the `/search` page → use the existing scaffold criterion → no regression.
7. Devtools network panel: when a scaffold is selected, only ONE search request fires (and its response body carries only the filtered set, not the full collection).

## 7. Diagnostic anchors

- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py::_scaffold_clause` — only place the scaffold clause is built; `exact_match_in` branch lands here.
- `backend/alembic/versions/040_*.py` — migration adds the partial composite index.
- `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.ts` — new helper; mirrors the existing `collect-subtree-mol-ids.ts` pattern.
- `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.ts` — new hook; sibling to `use-collection-search.ts`.
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` — selection-state owner; dispatches between the two hooks.

## 8. Risks + mitigations

| Risk | Mitigation |
|---|---|
| `IN` clause with 500 SMILES is slow even with the index | Hard cap at 500; index is composite with workspace_id so each lookup is a single seek. PG handles thousand-element IN clauses fine at this row scale. |
| Hierarchy subtree scaffold count regularly exceeds 500 in real workloads | Surface a warning in the chemist UI ("subtree too large; switch to Groups mode or filter by chemotype directly"). Defer the UI; instrument first via the ValueError to know if it ever fires. |
| Cache fragmentation if scaffold list order varies between component renders | Sort the list before hashing the query key; tested. |
| Switching between full and filtered hooks causes a layout flash | Use the same skeleton component for both loading states (`<CardGridSkeleton />`). |
| Backfill missing on legacy mols (`bemis_murcko_smiles IS NULL`) | Already done in V2; partial index excludes empty-string rows but the column is NOT NULL post-V2. Verify in a one-line check during migration deploy. |

## 9. Rollout

- Single PR on top of the existing un-pushed `prot-2` work, OR sequenced after V1/V2/V3 push if the chemist wants V4 in its own slice.
- No data migration; no feature flag (the new mode is additive and inert until a caller sends `exact_match_in`).
- The FE rewire of `scaffold-tree-view.tsx` is the only behavior change for current users; it's a strict improvement (less data over the wire, less in-memory filtering).
