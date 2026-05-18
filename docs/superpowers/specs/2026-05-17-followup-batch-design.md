# Follow-up batch — V1.5 quick wins + scaffold filter criterion + Sonner toast

**Date:** 2026-05-17
**Branch:** prot-2 (42 commits ahead of origin/prot-2 at spec time)
**Scope:** Waves 0, 1, 4 from the agreed 7-wave plan. Waves 2, 3, 5, 6 deferred to a follow-up conversation (see Deferred section).
**Context:** Follow-ups from the V2 scaffold-tree ship (`docs/superpowers/specs/2026-05-17-scaffold-tree-v2-design.md`) and the Collections V1+V1.5 ship.

## Why this batch

Three pieces of work that are independent of each other, all small-to-medium, all unblock chemist value without architectural shifts:

- **Wave 0** closes two long-standing UX papercuts on `/collections/{id}` (frozen-collection state ignored; name edit gated behind a dialog).
- **Wave 1** lets chemists query "compounds with scaffold X" — turns the V2 scaffold work into a queryable filter, not just a viewer.
- **Wave 4** removes the only V2 polish that smoke-test fatigue exposed: a long-running compute with no progress indicator beyond an inline caption.

Deferred waves (2, 3, 5, 6) all involve larger composition changes (`/search` view-mode toggle, inline `SearchQueryBuilder` on `/collections`, the big `ResultsGrid` lift, activity threading) and should be staged separately to keep PR review surfaces small.

---

## Wave 0 — V1.5 quick wins

### A1 — Disable Add/Remove on frozen collections

**Chemist-visible:** When `is_frozen=true` on a collection, the Add and Remove molecule buttons in `/collections/{id}` are disabled with a tooltip: "Frozen collection — unfreeze to modify."

**Surfaces touched (FE only):**
- `frontend/src/features/research-organization/components/collection-detail.tsx` — read `collection.is_frozen`, disable the Add/Remove buttons + show tooltip.
- No BE work — `is_frozen` is already on the wire (V1.5 P1).

**Acceptance:**
- Frozen collection page renders: buttons greyed out, hovering shows tooltip, click does nothing.
- Non-frozen collection page renders: buttons active and clickable (regression check).
- Vitest test on `collection-detail.tsx` covering both branches.

### A2 — Inline-edit collection name

**Chemist-visible:** Click the collection name in the page header → name becomes an inline input. Blur or Enter saves via PATCH; Escape cancels. Optimistic update; on error, revert + show toast.

**Surfaces touched (FE only):**
- `frontend/src/features/research-organization/components/collection/collection-header.tsx` — wrap the name in a click-to-edit affordance.
- New small hook: `frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.ts` — wraps the existing PATCH mutation with optimistic state + revert.
- Existing edit dialog stays as fallback for description/visibility/frozen state.

**Acceptance:**
- Click name → input appears with cursor placed in name.
- Enter → save + close + page header reflects new name.
- Escape → revert + close (no save).
- Frozen collection: name still editable (frozen blocks membership changes, not metadata — confirm via business rules in `docs/domain-model/05-research-organization.md`).
- Vitest test covering save / cancel / error revert.

**Rejected:** click-pencil-icon affordance. We learned earlier (see `feedback_explicit_ui_gestures`) that pencil icons in corners get missed; click-on-text is the convention here.

---

## Wave 1 — Scaffold filter criterion

### Intent

Chemists can add a "Scaffold" criterion to any search that matches molecules by `bemis_murcko_smiles`. Two modes:

1. **`exact_match`** — molecule's stored Bemis-Murcko SMILES equals the input (after canonicalization).
2. **`acyclic_only`** — molecule's Bemis-Murcko SMILES is the empty string (no rings; the "no scaffold" bucket from V2).

Substructure-on-scaffold is **explicitly deferred** — would need a RDKit cartridge index (GIST on `mol_from_smiles(bemis_murcko_smiles)`); chemists' primary need is "all compounds in this chemotype" which exact-match solves.

### Wire shape

```jsonc
// FE → BE criterion
{
  "type": "scaffold",
  "mode": "exact_match",                // or "acyclic_only"
  "scaffold_smiles": "c1ccc2ncccc2c1",   // required when mode == "exact_match"
  "negate": false                        // existing pattern across all criteria
}
```

### B1 — Backend clause

**Surfaces:**
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py` — new `_scaffold_clause()` + dispatch case for `"scaffold"` in `compose_criteria`.
- Canonicalization: the clause builder parses `scaffold_smiles` via `Chem.MolFromSmiles()`, then calls `MurckoScaffoldCalculator.compute(mol)` from `backend/src/cellar/infrastructure/rdkit/scaffold_calculator.py` to get the canonical scaffold SMILES. This is idempotent for valid scaffold input and normalizes full-molecule paste to its Bemis-Murcko scaffold (forgiving paste behavior). On parse failure, the clause builder raises a domain validation error (handled by the existing search route's error mapper). For `acyclic_only` mode, no canonicalization — just compare to the empty string.
- Negation handled by the existing `_apply_negate` wrapper (mirrors `_collection_clause` shape).

**Tests:**
- `backend/tests/unit/infrastructure/persistence/sqlalchemy/test_search_query_composer.py` — at least 4 cases: exact match hits, exact match misses, acyclic_only hits acyclic compounds, negation flips both modes.
- Skip API integration test in this batch unless the testcontainer is already warm (pre-existing pain point flagged in earlier handoffs).

### B2 — Frontend UI

**Surfaces:**
- `frontend/src/features/research-organization/types/index.ts` — extend `CriterionType` union with `"scaffold"` + add `ScaffoldCriterion` interface.
- `frontend/src/features/research-organization/components/criterion-rows/advanced-rows.tsx` — add `ScaffoldCriterionRow` component. Mode picker (segmented control: `Exact match | Acyclic only`); when mode == `exact_match`, text input for SMILES.
- `frontend/src/features/research-organization/components/search-query-builder.tsx` — add `case "scaffold":` to the dispatch switch; add to the criterion dropdown options list (alphabetical placement — sits between "Project" and "Selectivity").

**Tests:**
- Vitest test on `ScaffoldCriterionRow` — mode switch hides/shows the SMILES input; onChange fires the right shape.
- One snapshot of the full builder with a scaffold criterion in it (regression against the dispatch).

### B3 — Ergonomic loop closer

**Chemist-visible:** In `ScaffoldTreeView`, hovering a tree node reveals a small action icon (link icon, top-right of the node row). Clicking it opens `/search` pre-populated with one `scaffold` criterion (`exact_match` mode + the node's `scaffold_smiles`) and auto-executes.

**Mechanism:** sessionStorage handoff (NOT a new `?q=` URL-encoder). Reasoning: `/search` today only has `?saved=<id>` + `?agg=` URL state. Building a generic criterion-tree encoder for arbitrary URL `?q=` is out of proportion for this loop closer and arguably belongs to a future Wave that adds bookmarkable ad-hoc queries. Chemists who want to bookmark a scaffold query can use the existing "Save Search" affordance once they land on `/search`.

**Surfaces:**
- `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx` — add the action icon (visible only on hover/focus per the existing tile-action pattern). On click:
  1. Stash `{ criteria: [{ type: "scaffold", mode: "exact_match", scaffold_smiles }] }` to `sessionStorage` under a known key (e.g. `cellar:pending-search-query`).
  2. `router.push("/search?from=scaffold-tree")`.
- `frontend/src/features/research-organization/components/search-page.tsx` — on mount, check `sessionStorage` for the pending key. If present: hydrate the search-page reducer's `query` state from it, clear the key, auto-execute. The `?from=scaffold-tree` flag is purely advisory (tells the page to look for the handoff; absent → never reads sessionStorage).

**Acceptance:**
- Hover on a scaffold node → action icon appears.
- Click icon → opens `/search` with that scaffold pre-filled and the search auto-executed.
- Search results page shows N compounds matching the scaffold (compare against `node.molecule_count` for sanity check; counts should match modulo any active project filter).
- sessionStorage is cleared after hydration (no leak into subsequent `/search` visits).
- Vitest test on `scaffold-tree-node.tsx` for the new affordance.

---

## Wave 4 — Sonner toast for scaffold-tree async compute

### Intent

When `useScaffoldTree` enters async-polling mode (large collections > 500 mols), show progress beyond the inline "Computing scaffold tree…" caption. Spec follow-up from the V2 handoff: 3-second threshold + Cancel button.

### C1 — Toast implementation

**Surfaces:**
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` — add a `useEffect` that schedules a `setTimeout(3000)` when `isStarting || isPolling`. On fire → `toast.loading("Computing scaffold tree…", { id, duration: Infinity, action: { label: "Cancel", onClick } })`. On terminal status (`tree` set OR `error` set) → `toast.dismiss(id)` + clear timeout.
- Cancel onClick → call the existing `useCancelScaffoldTreeJob(jobId)` mutation (already wired in `frontend/src/shared/lib/api/scaffold-tree/scaffold-tree.ts`); the polling hook will pick up the `"cancelled"` status and surface it via its `error` field. Toast also fires `toast.success("Cancelled")` briefly for closure.

**Pattern reference:** `frontend/src/shared/components/export/export-job-toast.tsx` — same shape (`toast.loading` with action), used for the export pipeline shipped 2026-05-16.

**Tests:**
- Vitest test on `scaffold-tree-view.tsx` covering: (a) toast appears after 3s of polling, (b) toast dismisses on tree arrival, (c) toast dismisses on Cancel click + cancel mutation fires, (d) toast does NOT appear if computation completes before 3s.
- Mock `setTimeout` via vitest's fake timers.

**Acceptance:**
- Small collection (< 500 mols): no toast, sync return as before.
- Large collection compute taking > 3s: toast appears with spinner + Cancel; dismisses when tree renders.
- User clicks Cancel: toast dismisses + brief "Cancelled" toast + inline caption clears (hook's `error` set) + chemist returns to whatever view-mode they were in.
- Inline caption stays as backstop — toast augments it, doesn't replace it (for screens where toasts may be off).

---

## Risks + decisions

| Risk | Decision |
|---|---|
| Chemist pastes a full molecule SMILES instead of a scaffold SMILES into the scaffold criterion | BE canonicalizes via `MurckoScaffoldCalculator.compute()` — forgiving paste behavior, no error popup. |
| `bemis_murcko_smiles` has no index → exact-match scan is O(N) on the molecules table | Accept for V1 (workspace molecule counts are well under the threshold where this matters). Document the perf gate in commit message + add B-tree index post-smoke if a chemist reports lag. |
| Toast Cancel + inline caption double-source-of-truth | Single SoT = hook's `error` state. Cancel mutation triggers the polling status → `"cancelled"` → hook surfaces it via `error`. Toast dismisses on terminal status (success or error). |
| Inline-edit collection name conflicts with optimistic concurrency (`version` column) on the aggregate | Existing PATCH endpoint already handles version; mutation hook can refresh on 409 + retry once. If still fails, revert + toast error. |
| Frozen-collection name edit semantics | Per business rules, `is_frozen` blocks membership changes, not metadata. Inline name edit stays enabled on frozen collections. Confirm during smoke. |
| B3 ergonomic loop: scaffold tree → search URL encoding could clash with existing query params | Use the same `q=` URL state pattern `/search` already supports; reuse the existing encode/decode round-trip helpers — no new pattern. |

---

## Acceptance criteria (overall)

Before pushing this batch:

1. All vitest + pytest tests in scope are green.
2. `pnpm exec tsc --noEmit` clean.
3. Browser smoke:
   - **A1**: Set `is_frozen=true` on a test collection → Add/Remove buttons disabled with tooltip.
   - **A2**: Click collection name → inline-edit → Enter saves; Escape cancels.
   - **B1+B2**: Open `/search`, add a Scaffold criterion (`exact_match` + a known scaffold SMILES), search → returns the expected molecule(s). Switch to `acyclic_only` mode → returns the acyclic-compound bucket.
   - **B3**: On a collection with at least one ringed compound, open scaffold-tree view → hover a node → click the link icon → lands on `/search` with the scaffold pre-filled and N compounds shown.
   - **C1**: Open scaffold-tree view on a > 500-mol collection → wait > 3s → toast appears with spinner + Cancel → click Cancel → toast dismisses + brief "Cancelled" toast.

---

## Deferred to a follow-up conversation

These 4 waves from the agreed 7-wave plan are NOT in this spec:

- **Wave 2 — Hoist ViewModeToggle onto `/search`** (~3 commits)
- **Wave 3 — Inline `SearchQueryBuilder` on `/collections/{id}`** (~4 commits)
- **Wave 5 — Lift `/search` `ResultsGrid` into `ResultsSurface` as table mode** (~8 commits)
- **Wave 6 — Activity threading on `/collections` (lazy fetch on color-by select)** (~3 commits)

Wave 5 is the largest single piece in the entire 7-wave plan and is the only one that has hard ordering implications (Wave 6 simplifies dramatically once Wave 5 lands). Defer them all together to the next conversation so they ride on a fresh context window.
