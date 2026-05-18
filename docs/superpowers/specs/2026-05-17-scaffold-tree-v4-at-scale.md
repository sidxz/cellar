# V4 — Scaffold tree at scale (deferred)

Date opened: 2026-05-17
Status: **deferred — trigger on first user hitting the cap**
Parent: `2026-05-17-scaffold-tree-v2-design.md` (shipped V2 on `prot-2`)

---

## Why this exists

V2 ships with a hard ceiling: **collections up to 10,000 molecules** load atomically into the scaffold tree's right pane. The number comes from `COLLECTION_FETCH_MAX_PAGE_SIZE` introduced in commit `300f4fc5` — the search endpoint's generic 200-row cap relaxes to 10K for single-criterion `{type:"collection"}` queries so the chemist can see every member without pagination.

10K is comfortably above every real curated collection we've seen so far (typical: 5–500 mols; large: 900–5000). But sooner or later someone will:

- Drag a 50K-mol screening library into a collection and expect the tree to work, OR
- Hit the cap silently and complain that "the tree counts don't match my card grid".

This doc captures the two future-proofing paths so when that day comes we're not scrambling.

## Hard trigger

Don't build this preemptively. Build when:

- A chemist files a report that their collection's scaffold-tree counts don't match what they expect, OR
- We see a deployed collection cross 8K mols (close enough to the ceiling to warrant action), OR
- Telemetry shows `useCollectionSearch` hitting the limit on a real collection.

Until any of those, the 10K ceiling is fine — chemistry workflows live well under it.

---

## Path A — Server-side scaffold-membership filtering

**Idea:** instead of loading every mol into the FE and filtering locally, fetch only the mols matching the selected scaffold from the BE on demand. Filter happens server-side using the `bemis_murcko_smiles` column directly.

**Wire shape:**

```
GET /api/v1/collections/{id}/molecules?scaffold={smiles}
```

Or add a search criterion:

```
{ "type": "scaffold", "scaffold_smiles": "c1ccccc1" }
```

Returns enriched molecules whose Bemis-Murcko equals the requested scaffold. The BE query is a single index hit (B-tree on `bemis_murcko_smiles`).

**Pros:**
- Constant-time response regardless of collection size
- No FE-side filtering at all — pagination only matters for "all mols, no scaffold selected" mode
- Lets chemists work productively on 50K+ libraries

**Cons:**
- Needs a new BE index on `bemis_murcko_smiles` (B-tree). Modest disk cost.
- One round-trip per scaffold click (mitigated by React Query caching)
- "Show all mols" (no scaffold selected) still needs pagination — separate UX question

**Effort:** ~1 day BE + ~half-day FE. Largest piece is the index migration + a focused `find_by_scaffold(scaffold, collection_id, workspace_id)` repo method.

## Path B — Per-scaffold lazy fetch on click

**Idea:** keep the existing tree compute but fetch the selected scaffold's mols by ID on click. The tree wire shape already has the full `molecule_ids` array per node — the FE just calls a "fetch by IDs" endpoint with that list.

**Wire shape:**

```
POST /api/v1/molecules/by-ids
body: { molecule_ids: [...] }
```

Returns enriched molecules for the specified IDs. No pagination needed (chemist asked for a bounded set).

**Pros:**
- Minimal BE work — just one new endpoint
- Reuses existing scaffold-tree wire data (mol IDs are already on each node)
- Cards-pane "show all" mode degrades gracefully — paginated default, "load more" on demand

**Cons:**
- For very large scaffolds (1000+ mols of one chemotype) the fetch is still big
- Need to update CardGrid to handle "scaffold members loading" vs "all mols" vs "selected scaffold" states explicitly
- Doesn't fix the "all mols" pane for huge collections

**Effort:** ~half-day BE + ~1 day FE (state-machine refactor of CardGrid).

## Recommended sequencing when triggered

1. **Path A first** — solves the most-common chemist click ("show me this scaffold's members") cleanly and indexes scale up. Single migration + endpoint.
2. **Path B if needed** — only if "show all mols" mode on a huge collection becomes a real complaint. By then we might want to pivot to virtualized infinite scroll instead.

## Out of scope here

- Cluster map / heatmap (V3 — separate spec).
- Saving a scaffold subtree as a new collection — already in the V3 / lasso area.
- Scaffold filter row in `SearchQueryBuilder` — that's Path A's wire shape; lands together if we go that route.

## Sanity check before building

The whole reason this is deferred: **the chemistry workflow rarely needs 10K+ in one collection.** Real-world hit-lists are 5-500 mols; library-design subsets are 500-5000. The 10K ceiling exists as defense-in-depth, not because anyone has shown they need it.

When the cap actually bites: don't reach for the heavier Path A. Re-check first that the user isn't using "collection" as a substitute for "saved search" (a 50K-mol scope is more search-flavored than collection-flavored). The right answer might be to push them toward the search UX instead.
