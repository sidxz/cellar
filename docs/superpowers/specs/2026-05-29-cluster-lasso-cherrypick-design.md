# Cluster-map lasso → cherry-pick basket

**Date:** 2026-05-29
**Status:** Approved design, pre-implementation
**Context:** SAR Analysis (04) cluster map · Research Organization (05) collections
**Scope:** Frontend-only. No new backend tables, no new domain entities, no inventory cross-context work.

---

## Problem

The collections **Cluster** view (`/collections/{id}?view=clusters`) renders a UMAP of Morgan
fingerprints — a 2-D map of chemical space where proximity ≈ structural similarity. It has a
diversity picker (MaxMin / Butina), a cluster-threshold slider, color-by (cluster / activity /
scaffold), and a lasso drag mode. The status bar invites "Drag on the map to lasso a region."

A chemist reported the **lasso does nothing useful**. Investigation shows the lasso is partly
wired — `onSelected` collects molecule IDs, dims non-selected points to 0.25 opacity, fills the
right-hand selection pane, and the "Save selection" button turns the *current* selection into a
new collection. But:

1. **It may not actually select at runtime** — cause unconfirmed (see "The lasso bug" below). The
   "does nothing" report has to be reproduced and diagnosed empirically, not assumed.
2. **Even when it works, the payoff is thin.** A lasso that only dims-and-maybe-saves-a-collection
   is a weak reason to draw one. There is no way to *accumulate* picks across multiple regions, no
   region-scoped diversity pick, no de-dupe of overlapping regions, no negative selection, and the
   selection evaporates on the next lasso.

## The chemist's reframe

This map exists to answer **"what do I actually buy and put on a plate?"** The example collection
`chembridge_top5000_kb` is a **vendor library** (ChemBridge top-5000, cell-permeability tagged) —
compounds not yet owned. The dominant job is **library design / cherry-picking for acquisition**,
not SAR on assay data.

So the lasso's real purpose is **a region constraint on building a cherry-pick basket**: accumulate
a diverse purchase shortlist neighborhood-by-neighborhood, with chemical context (cluster / activity
/ scaffold coloring) underneath, then commit the whole basket to a collection.

## Goals

- Lasso reliably selects the compounds under the drag (fix whatever the runtime gap is).
- A **persistent cherry-pick basket** that accumulates across multiple lassos and the global
  Diversify pick, auto-de-dupes overlaps, and shows a running count.
- **Region-scoped diverse pick:** lasso a dense neighborhood → pick N diverse from *just that
  region* → add those to the basket (deepen coverage where it matters).
- **Add-all and remove (negative selection)** on a lassoed region.
- **In-basket markers** on the map so the chemist sees their running picks across all regions.
- **Commit** the basket to a new collection via the existing create + bulk-add flow.

## Non-goals (V1)

- SDF / CSV export of the basket (already a separate "Export SDF" button on the collection page).
- Acquisition / sample-request wiring for not-yet-owned compounds.
- Server-persisted named selections (a real "Selections" entity).
- Drill-in / re-embedding a lassoed subset to reveal sub-structure (the "explore" job).
- Activity-triage "promote a hot region to a project / SAR table" (the "SAR" job).
- A new backend endpoint. Region picking reuses the existing UMAP endpoint (below).

## The chemist workflow

```
1. Open the vendor library in Cluster view.
2. (optional) Hit "Diversify" → ~50 global diverse stars → "Add all picks to basket"
      → seeds a diverse starting set spanning the whole library.
3. Lasso a chemotype neighborhood you care about:
      → "Pick N diverse here" (N stepper) → N reps highlight inside the region
      → "Add N picks"          (deepen coverage where it matters)
      → or "Add all (X)"       (small / already-curated region — take everything)
4. Lasso a region you do NOT want (e.g. a PAINS-like or off-property blob):
      → "Remove from basket"   (negative selection)
5. Basket accumulates across lassos, auto-de-dupes overlaps, running count shown.
6. "Save as collection" → existing create + bulk-add flow. Done.
```

The map **does not re-embed** during cherry-picking — re-projecting mid-pick is disorienting and
moves every point under the chemist's cursor. The existing "Diversify-scoped-to-lasso re-embed"
behavior is therefore *not* reused for cherry-picking; the map stays stable and we only pick + basket.
(The global "Diversify" button keeps its current whole-map behavior.)

## Design

### State model (in `cluster-map-view.tsx`)

| State | Lifetime | Purpose |
|-------|----------|---------|
| `lassoedIds: Set<string>` | transient (exists today) | the current lasso region |
| `regionPickIds: Set<string>` | transient (new) | the N diverse reps of the current lasso, after "Pick N diverse here" — candidates to add, not yet basketed |
| `basketIds: Set<string>` | **persisted** (new) | the accumulated cherry-pick shortlist |

`basketIds` is a `Set` so overlapping-region adds de-dupe for free. It is persisted to
`localStorage` under `cellar:cherrypick:{collectionId}` (lazy-read on mount, guarded by
`typeof window`, written on every mutation) → survives reload and navigation, per the session-only
durability decision. Encapsulated in a `useCherrypickBasket(collectionId)` hook exposing
`{ ids, add, addMany, remove, removeMany, clear, has, size }`.

### Region diverse-pick — reuse the existing endpoint

"Pick N diverse here" must run MaxMin on the lassoed subset's fingerprints, which live only on the
backend. We **reuse the existing `POST /api/v1/sar/umap-cluster`** with
`molecule_ids = [...lassoedIds]`, `picker = "maxmin"`, `n = N`, and read only the returned
`representatives` — the throwaway 2-D embedding of a small lasso region is cheap and we ignore the
coords. **Zero backend change.**

This is a *separate* on-demand invocation (new `useRegionDiversePick` hook), not the `useUmapCluster`
instance that drives the map — so picking never disturbs the map's layout or its global picks.

> Optional future optimization (NOT V1): a lightweight `POST /api/v1/sar/diverse-pick` that takes
> `molecule_ids` + `n` and returns picked ids only, skipping the embedding. Only worth it if region
> picks become slow on large lassos.

### UI surfaces

- **Region action bar** — appears only while a lasso is active. Shows `"{X} in region"` plus:
  `Pick N diverse` (with an N stepper, default = the toolbar N), `Add N picks` (enabled after a
  region pick), `Add all ({X})`, `Remove from basket`, `Clear`.
- **Basket bar** — persistent strip in the toolbar row: `Basket: {Y} compounds`, an optional
  plate-target hint (`{Y} / 96`), `Review`, `Save as collection`, `Clear basket`. The plate target
  is a small chemist nicety toward a 96-/384-well cherry-pick plate; it is display-only (does not
  cap adds).
- **Selection pane** (right pane, exists) — two stacked sections: **Current region** (cards for the
  lassoed set + the add/pick controls) and **Basket** (cards for the accumulated set + save / clear).
  When no lasso is active, only the Basket section shows.
- **Map markers** — visually distinct states, in precedence order per point:
  1. **In-basket** → a distinct overlay trace (filled marker with a dark ring / badge) — always
     visible regardless of lasso, so the running picks are legible across regions.
  2. **Region-pick candidate** (`regionPickIds`, not yet basketed) → transient highlight
     (e.g. hollow star) so the chemist can eyeball the picks before adding.
  3. **Lassoed** (not basketed) → full opacity (existing dim-the-rest logic).
  4. Otherwise → dimmed when a lasso is active, else normal.

  Global representative stars stay as the "suggestion" layer; "Add all picks to basket" promotes them.

### Commit

`Save as collection` calls the existing `onSaveCollection({ name, projectId, moleculeIds })` wired in
`results-surface.tsx` (create collection → `POST /collections/{id}/molecules` bulk-add) with
`moleculeIds = [...basketIds]`, reusing `save-selection-dialog.tsx`. Default name suggestion:
`cherrypick-{Y} from {sourceLabel}`. The vendor catalog id (the large number under the `CC-` number,
e.g. `5116962` under `CC-057186`) is shown on every basket card — free, and exactly what procurement
needs later.

## The lasso bug

The "does nothing" report must be **reproduced and diagnosed**, not patched on a guess. Candidate
hypotheses to check empirically (systematic-debugging):

- **Not scattergl for this case.** The WebGL cutoff is `points.length > 5000`; a 5000-mol collection
  (minus skipped) renders as SVG `scatter`, where `plotly_selected` is well-defined. So the earlier
  scattergl theory likely does *not* explain this collection — but it WILL bite any collection
  > 5000 points, where `pointNumber → moleculeId` mapping under `scattergl` is the known-fragile spot.
- **Event wiring** through the shared `Plot` dynamic-import wrapper — confirm `onSelected` actually
  reaches `plotly_selected`.
- **Per-point `marker.opacity` array** interacting with Plotly's selected/unselected styling.
- **Two-trace selection** (base + star) — confirm `curveNumber === 0` filtering isn't dropping
  everything.

Fix the confirmed cause at the right layer. If scattergl selection indexing is unreliable above 5000
points, prefer fixing the index mapping over silently forcing SVG (which would regress render perf on
big libraries) — but make that call from evidence.

## Edge cases

- **Lasso returns empty** (drag over white space) → no region bar action enabled; basket untouched.
- **Overlapping regions** → `Set` de-dupes; running count is truthful.
- **Basket spans compounds skipped by UMAP** → not possible; only mapped points are lassoable.
- **Collection changes / different collection** → basket is keyed by `collectionId`, so each
  collection has its own basket.
- **`Remove from basket` on a region with nothing basketed** → no-op.
- **Empty basket** → `Save as collection` and `Review` disabled.
- **localStorage unavailable / SSR** → basket falls back to in-memory only; never throws.

## Testing

- `useCherrypickBasket` — add / addMany / remove / removeMany / clear / de-dupe / localStorage
  round-trip / per-collection keying / SSR-safe (no `window`).
- `useRegionDiversePick` — calls the umap endpoint with the lassoed ids + maxmin + N, returns
  representative ids, surfaces loading / error.
- Region action bar — buttons enable/disable per lasso + region-pick state; counts correct.
- Basket bar — count, plate hint, disabled states.
- Map marker derivation — in-basket / region-candidate / lassoed / dimmed precedence.
- The lasso bug — a regression test asserting `onSelected` yields the right ids for an SVG-scatter
  selection event shape (and, if scattergl is the >5000 fix, for that shape too).

## Components touched

| File | Change |
|------|--------|
| `frontend/src/features/sar-analysis/hooks/use-cherrypick-basket.ts` | **new** — localStorage-backed basket `Set`, per collection |
| `frontend/src/features/sar-analysis/hooks/use-region-diverse-pick.ts` | **new** — on-demand MaxMin over a lassoed subset, reusing the umap endpoint |
| `frontend/src/features/sar-analysis/components/cluster-map-view.tsx` | basket + region-pick state, orchestration, marker derivation |
| `frontend/src/features/sar-analysis/components/cluster-scatter.tsx` | lasso bug fix; in-basket overlay trace; region-candidate highlight |
| `frontend/src/features/sar-analysis/components/cluster-toolbar.tsx` | basket bar (count, plate hint, Review / Save / Clear) |
| `frontend/src/features/sar-analysis/components/cluster-selection-pane.tsx` | Current-region + Basket sections; per-card vendor catalog id |
| `frontend/src/features/sar-analysis/components/region-action-bar.tsx` | **new** — region selection action bar |
| `frontend/src/features/sar-analysis/components/save-selection-dialog.tsx` | reuse as-is (basket → collection) |
| `frontend/src/features/research-organization/components/results/results-surface.tsx` | already provides `onSaveCollection`; no change expected |

## Reused infrastructure (no change)

- `POST /api/v1/sar/umap-cluster` — drives the map *and* region diverse-pick.
- `useCreateCollection` + `POST /collections/{id}/molecules` — basket → collection.
- `usePickerConfig`, `useColorMode`, cluster palette, the `Plot` wrapper.
