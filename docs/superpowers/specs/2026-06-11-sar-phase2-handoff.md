# SAR Phase-2 handoff — full-collection coverage, activity cliffs, MMP

**Purpose.** Records the codebase exploration done 2026-06-11 so a **fresh session** can
brainstorm → spec → plan → implement each sub-project without re-exploring. This is orientation +
findings + file pointers, **not** a design or implementation plan — each sub-project should still
start with `superpowers:brainstorming`.

These came out of "do backlog #1 (full-collection) + Phase 2 (activity cliffs + MMP)". Exploration
showed they are **three sub-projects of very different sizes**. Recommended order: **#1 → cliffs →
MMP**. Each gets its own spec → plan → implementation cycle.

Branch context: shipped on `design-6` (Phase-1 SAR + the core-selection refinement). Backlog:
`docs/backlog/sar-workbench-frontend-followups.md`. Domain model: `docs/domain-model/04-sar-analysis.md`.

---

## Sub-project 1 — Full-collection coverage (SMALL, frontend-mostly)

**Problem (backlog #1).** The SAR view (`SarView`) analyzes the molecule set it's handed, which was
assumed to be a paginated page. Goal: analyze the **whole collection**.

**Reality check (smaller than the backlog implies):**
- The decomposition endpoint **already accepts `collection_id`** and server-expands to
  `COLLECTION_EXPANSION_LIMIT = 100_000` — `backend/src/cellar/interface/routes/sar_analysis.py`
  (`POST /api/v1/sar/r-group-decomposition`, `molecule_ids` XOR `collection_id`). The hook
  `frontend/.../hooks/use-rgroup-decomposition.ts` already exposes `collectionId`.
- `collection-detail` loads members via `useCollectionSearch` with **`limit = 10_000`**
  (`COLLECTION_FETCH_MAX_PAGE_SIZE`, `backend/src/cellar/application/shared/pagination.py` — "large
  enough to atomically load every realistic curated collection"). So for realistic collections the
  full set is likely already in `props.molecules`. **Verify this** — `sar-view.tsx` still carries a
  stale-looking "visible page" comment.

**Gaps to close (for the fresh session to design):**
1. `SarView` passes `moleculeIds`, not `collectionId`, to decomposition + activity. Mirror the
   scaffold-tree pattern `collectionId ? { collectionId } : { moleculeIds }`
   (`hooks/use-scaffold-tree.ts`, `components/scaffold-tree-view.tsx` already do this correctly).
2. `hooks/use-sar-activity.ts` has **no `collection_id` path** — it builds a `keyword_list` of
   explicit ids against `/search/execute`. To stay consistent with a collection-expanded
   decomposition it needs collection expansion (or to be fed the full id list).
3. The table/heatmap join assignments to **molecule objects** (structure, MW/cLogP/TPSA, reg number)
   by id (`buildRGroupRows`). Members beyond the loaded set → blank rows. Either lazily resolve
   off-set molecule objects, or accept the 10K fetch cap.
4. Honest labeling: "all N members" vs "first 10,000 of N".

**Scope decision for the fresh session:** handle >10K collections properly (lazy member-object
resolution — more work) **vs.** accept the 10K fetch cap with honest labeling (YAGNI — `pagination.py`
says 10K covers every realistic curated collection).

**Key files:** `frontend/.../sar-analysis/components/sar-view.tsx` (the seam, ~L45–71),
`hooks/use-sar-activity.ts`, `hooks/use-rgroup-decomposition.ts`, `hooks/use-scaffold-tree.ts`,
`components/scaffold-tree-view.tsx`, `research-organization/components/collection-detail.tsx` +
`hooks/use-collection-search.ts`, `research-organization/components/results/results-surface.tsx`
(view-mode wiring), `backend/.../application/shared/pagination.py`,
`backend/.../interface/routes/sar_analysis.py`.

---

## Sub-project 2 — Activity cliffs (MODERATE; primitives already exist)

**Concept.** A cliff = a structurally **similar** pair (Tanimoto ≥ threshold) with a **large activity
delta** (e.g. Δp[IC50] ≥ threshold) — a local SAR discontinuity. **Not** in the domain model yet
(a new concept); **not started**.

**What already exists to build on:**
- **Fingerprints + Tanimoto, in Postgres.** `fp_morgan` (bytes) plus RDKit-cartridge `bfp` columns
  `morgan_bfp` + `fcfp_bfp` on `molecules`, GiST-indexed (migration `025`). Tanimoto via the `%`
  operator + `tanimoto_sml()` — see `_similarity_clause` in
  `backend/.../persistence/sqlalchemy/chemical_registration/_structure_query.py`. Python-side loader:
  `backend/.../infrastructure/sar_analysis/morgan_fingerprint_loader.py`. **Caveat:** pairwise
  similarity within a set is **not** exposed as an endpoint today (only single-query similarity
  search + UMAP's internal metric).
- **Activity layer.** `SarColorSpec` (protocol + readout/intercept) → `colorSpecScalar(av)` gives one
  comparable scalar per molecule (`lib/sar-color-spec.ts`, `hooks/use-sar-activity.ts`) — the same
  channel the table/heatmap color by. `potencyShade` / `pickReference` (`components/rgroup-table.tsx`)
  already encode potency visually. Like the heatmap, comparisons must stay within **one comparable
  readout**.
- **Embedding/job patterns to mirror.** UMAP cluster feature: `backend/.../interface/routes/umap_cluster.py`
  (inline ≤500 / async job-poll), `infrastructure/rdkit/umap_embedder.py` (Jaccard on Morgan),
  `frontend/.../hooks/use-umap-cluster.ts`, `components/cluster-*`.

**Likely shape (the fresh session designs this — sketch only):** a backend
`POST /api/v1/sar/activity-cliffs` (or `/pairwise-similarity`) taking `collection_id|molecule_ids` +
the activity channel + thresholds → ranked pairs `{mol_a, mol_b, tanimoto, delta, sali}`, where
**SALI = |Δactivity| / (1 − Tanimoto)**. Compute either via a cartridge self-join over the set's
`morgan_bfp` (candidate pairs above the Tanimoto threshold) or in Python from loaded fingerprints.
Frontend: a new SAR sub-view (SALI scatter: x = similarity, y = |Δactivity|; + a ranked cliff-pair
list showing both structures, the change, and the activity jump), reachable from the SAR view-mode
toggle; reuse `DoseResponseChart` for each pair's curves.

**Decisions for the fresh session:** activity source (reuse the `SarColorSpec` channel — single
comparable readout); default + chemist-tunable thresholds; compute location (cartridge self-join vs
Python); cliffs as a computed view (no persistence) vs an aggregate.

---

## Sub-project 3 — Matched molecular pairs / MMP (LARGE; full-stack, Temporal)

**Status.** Fully specified in `docs/domain-model/04-sar-analysis.md` (MatchedMolecularPair: single
SMIRKS-transformation pairs, `property_deltas` jsonb, canonical `molecule_a_id < molecule_b_id`,
async batch via Temporal, invalidated on merge / structure-correction). Slotted as **Phase 3**
(S34–36, "requires Temporal") in `docs/implementation-status.md`. **Zero code today.**

**Build-from-scratch scope:** `MatchedMolecularPair` domain aggregate; persistence (table + repo +
migration); batch fragment-and-index (RDKit MMPA is installed at `rdkit/Contrib/mmpa/` but
unintegrated — or a custom fragmenter, or `mmpdb`); a Temporal workflow triggered by
`MoleculeRegistered`/`MoleculeDisclosed` (mirror the CDD-import continue-as-new pattern in
`backend/scripts/` + `infrastructure/temporal/`); invalidation handlers on merge/structure-correction;
API (by molecule, by transformation, by Δproperty); frontend (pair/transform table with activity
delta, optionally a transformation network). Genuinely multi-session.

**Decisions for the fresh session:** confirm Temporal as the async path (domain model says so);
property-delta source (physchem descriptors + the Screening activity layer); RDKit Contrib mmpa vs
`mmpdb` vs custom fragmenter.

---

## Cross-cutting note (affects cliffs + MMP)

The domain model specifies a `MolecularFingerprint` **aggregate** with its own lifecycle; the
implementation stores fingerprints as **columns on `molecules`** (`fp_morgan`, `morgan_bfp`,
`fcfp_bfp`) with cartridge triggers — no separate entity/repo. A fresh session touching this should
decide early: remodel to the aggregate, or document the deviation.

---

## Recommended sequencing

1. **Full-collection coverage** — small; makes every downstream SAR analysis honest about the set.
2. **Activity cliffs** — moderate; high chemist value; reuses existing fingerprint similarity +
   activity layer.
3. **MMP** — large, Temporal-dependent; its own multi-session project (Phase-3-slotted).

Each: start with `superpowers:brainstorming`, read this handoff + the cited files, then spec → plan →
implement.
