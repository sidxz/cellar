# SAR Workbench — Phase 1: R-group Decomposition Table + Heatmap

- **Date:** 2026-06-09
- **Branch:** design-6
- **Context:** 04 SAR Analysis (frontend `features/sar-analysis`, backend `sar_analysis`)
- **Status:** Design — awaiting review before implementation plan
- **Phase:** 1 of a phased SAR workbench (this doc covers Phase 1 only)

---

## 1. Summary

Add an **SAR workbench** to Cellar whose first deliverable is **R-group decomposition** of a compound series rendered as both a **sortable table** and a **2D heatmap (SAR map)**. The chemist picks a set of compounds, chooses a common core (auto-suggested from the existing scaffold tree), and sees each analog broken into its R-groups beside its activity and physchem — sortable as a table, or laid out as a colored R1×R2 grid where empty cells are unmade analogs.

This is the single most-used SAR capability in professional tools (the peer-reviewed "SAR Maps" pattern; present in DataWarrior, Dotmatics Vortex, CCG MOEsaic, CDD SuperSAR). It is also the lowest-risk first build because it reuses four existing subsystems and adds essentially one new chemistry operation plus a view.

## 2. Background & motivation

Cellar today has strong compound search, a Bemis-Murcko **scaffold tree**, **chemical-space clustering** (UMAP/Butina/MaxMin), Morgan/FCFP **fingerprints**, **dose-response/IC50** data with multi-run aggregation, and **collections** — but no surface that places **structure next to activity across a congeneric series**. That structure↔activity surface is the heart of the medicinal-chemistry lead-optimization loop and is currently absent (no R-group decomposition, no matched-pairs, no activity-cliff code exists in the repo).

Research basis (deep-research, 2026-06-09, 24 sources / 25 verified claims): the canonical SAR capabilities are (1) R-group SAR table/heatmap, (2) matched molecular pairs, (3) activity cliffs. (1) is the highest day-to-day value and the standard first build; (2)/(3) build on it. Key cited pitfalls are incorporated as guardrails (§14).

## 3. Goals (Phase 1)

- Decompose a chosen set of compounds against a chosen core into core + R1…Rn.
- Present the result as a **Table view** and a **Heatmap view** (a sub-toggle on one shared decomposition).
- Color by **one** chosen activity (protocol → readout/intercept → aggregation mode), with Δ-vs-reference shading.
- Surface **synthesis gaps** (empty heatmap cells) and let chemists act on selections (save as collection, export).
- Maximize reuse: scaffold tree (core suggestions), dose-response + `run_aggregation` (activity), collections (the set + save-as-collection), `DoseResponseFigure` (row→curve), structure renderer, view-mode toggle.

## 4. Non-goals (explicitly deferred)

- **Activity cliffs & matched molecular pairs (MMP)** — Phase 2.
- **Free-Wilson modeling, de-novo activity-cliff prediction, fragment-driven (core-less) SAR** — later/niche.
- **Simultaneous multi-core decomposition** (several series at once) — v1 decomposes against one core; non-matching compounds are shown separately, not decomposed.
- **Small-multiples heatmap** (a grid of heatmaps faceted on a 3rd R-group) — later; v1 collapses extra positions with a "+N" badge.
- **Standalone "SAR" navigation destination / landing page** — v1 is a view-mode opened on an existing set only.
- **Persisting SAR "sessions"** (saved core + config as a first-class entity) — later; v1 state lives in URL params like the other view modes.

## 5. Users & the questions answered

Primary user: medicinal chemist in lead optimization (also useful to screeners triaging a series). The workbench answers:
- "Which substituent wins at each position, and is the effect additive?" → table + heatmap.
- "What analogs haven't we made yet?" → empty heatmap cells.
- "How does this analog's curve actually look?" → row → dose-response.

## 6. Placement & entry points

The workbench is a **new view-mode** on a compound set, consistent with the existing `Table · Cards · Scaffold tree · Clusters` toggle.

- Add `"sar"` to `ViewMode` in `frontend/src/features/research-organization/lib/use-view-mode.ts` (and its URL mapping; suggested URL token `sar`).
- Surface the new mode in `features/research-organization/components/results/view-mode-toggle.tsx` and wherever the toggle is consumed: **collection detail** (`collection-detail.tsx`) and **search results** (`results-grid.tsx` host).
- Add **"Open in SAR"** from a scaffold-tree node (`features/sar-analysis/components/scaffold-tree-node.tsx`), which opens the SAR view on that node's members with the node's scaffold pre-selected as the core (skips core-picking).
- Gate like the cluster mode (which disables under 10 molecules): enable the SAR view-mode based on **set size** (a small minimum, mirroring the cluster gate; final threshold a build detail). This is a pre-core check; the matched-vs-unmatched count against the chosen core is shown afterward (§8).

## 7. End-to-end flow

1. **Open SAR on a set** — view-mode toggle on a collection/search result, or "Open in SAR" from a scaffold node.
2. **Pick the core** — auto-suggested from the scaffold tree; override via Edit/Draw (§8).
3. **Decompose** — backend runs RDKit R-group decomposition against the core (§9).
4. **Explore** — Table or Heatmap, colored by a chosen activity (§10–§12); act on selections (§13).

## 8. Core selection

**Auto-suggest from the scaffold tree + manual override** (chosen approach).

- Group the set's molecules by their stored `bemis_murcko_smiles` (already computed at registration) / scaffold-tree node membership; rank candidate cores by member count; **pre-select the dominant scaffold** as the core.
- Show **unmatched compounds separately** with a count ("18 of 24 match; 6 shown separately"). Never silently drop compounds. Unmatched can be left out or re-cored in a later pass (multi-core is a non-goal for v1).
- **Override:** "Edit in Ketcher" (adjust/generalize the suggested core, fix attachment points) and "Draw different core" (start from scratch). Reuses `shared/components/chemistry/ketcher-editor.tsx` / `structure-editor-dialog.tsx`.
- The selected core is passed to decomposition as SMILES/SMARTS. Implementation must validate behavior when the core is a bare Murcko ring skeleton (no explicit attachment points) — RDKit assigns R-groups at open positions; confirm parameters during build (§9, open question).

## 9. R-group decomposition (chemistry + backend)

Net-new, following the existing `infrastructure/rdkit` conventions (stateless singleton, no RDKit types in domain signatures, return plain VOs, defensive error handling, workspace-scoped queries).

- **Domain VO** — `backend/src/cellar/domain/sar_analysis/rgroup_decomposition.py`: a frozen result type, e.g. per-molecule `{ molecule_id, matched: bool, rgroups: dict[label, smiles] }` plus the set of R-group labels discovered (R1…Rn) and the core used.
- **Infrastructure** — `backend/src/cellar/infrastructure/rdkit/rgroup_decomposer.py`: thin wrapper over `rdkit.Chem.rdRGroupDecomposition.RGroupDecompose` (with `RGroupDecompositionParameters` for matching strategy / symmetrization). Input: core mol + list of mols; output: R-group assignments as SMILES. Each R-group SMILES is depicted via the existing `depiction.py` for thumbnails (FE may render via RDKit.js instead — decide in build).
- **Application** — `backend/src/cellar/application/sar_analysis/decompose_rgroups.py`: fetch the set's `(id, smiles)` via the existing lean fetch pattern (`fetch_for_scaffold_tree`-style), run the decomposer, return matched + unmatched. Railway/`Result` per project conventions.
- **Interface** — extend `interface/routes/scaffold_tree.py` or add `interface/routes/sar_analysis.py`: `POST /api/v1/sar/r-group-decomposition` with `{ molecule_ids | collection_id | search query ref, core_smiles }` → decomposition payload. Workspace guard + auth per `backend-code-guidelines.md`.
- **Scale:** synchronous for typical series sizes; the existing scaffold-tree async **job pattern** is the fallback if large sets need it (not built in v1).
- **orval:** regenerate types for the new endpoint into `frontend/src/shared/lib/api/model/`; hand-write the hook (`features/sar-analysis/hooks/use-rgroup-decomposition.ts`) per the project's hook convention.

## 10. Activity columns & guardrails

Reuse the search activity path — **do not reinvent**.

- Activity values come from `application/screening/molecule_activity_service.py::enrich_molecules` + `application/screening/run_aggregation.py` (the same engine search and campaigns use), via `POST /search/execute` or a lean equivalent.
- **Color-by control:** protocol → readout/intercept (e.g. IC50/EC50) → **aggregation mode** (latest / mean / geomean / best R²), reusing `lib/use-aggregation-mode.ts`.
- **GUARDRAIL — one readout at a time:** the heatmap color and Δ comparisons are computed within a **single comparable readout definition**. Never mix incompatible measurements (e.g. IC50 vs Ki) — the control selects exactly one readout; aggregation is scoped to that readout before any comparison.
- **Selectivity** column = ratio of two chosen intercepts (target vs counter-screen). v1 may compute the ratio in the frontend from the two `ActivityValue`s; a backend selectivity column is a possible later enhancement (open question).
- **Δ vs reference:** default reference = most-potent compound in the matched set; user can re-pick. Shading is relative to the reference within the chosen readout.

## 11. Table view

- One row per matched compound. Columns: selection checkbox, `#`, structure thumbnail, **R1…Rn** (each rendered as a small substituent structure + SMILES label), then **IC50** (chosen readout), **selectivity**, **LogP**, **MW** (physchem from existing descriptors). Column set is a sensible default; full column customization is out of scope for v1.
- Sort on any column. Activity cells shaded green→red relative to the reference (★).
- **Row click → dose-response curve** via the existing `DoseResponseFigure` renderer (no new chart code).
- **Selection → actions** (§13).
- Unmatched compounds accessible via a separate "N not matching this core" affordance (list, with option to exclude or revisit).

## 12. Heatmap view

- **Axis pickers:** choose any two R-positions as Y and X. Cells colored by the chosen activity (same control as the table).
- **Empty cells = synthesis gaps** (analogs not yet made) — rendered distinctly (hatched, "make?"). These are a feature, not an error.
- **3+ varying R-groups (chosen handling):** pick any 2 axes; when other positions vary, multiple compounds collapse into one cell — show the **best value + a "+N" badge**; click to expand the cell's compounds. The Table view always holds the full per-compound detail.
- Legend (potent→weak) and the active readout/aggregation are always visible.
- Click a populated cell → the compound(s) there (and their curves via the shared renderer).

## 13. Actions

- **Save selection as collection** — reuse the cluster view's existing "save selection as collection" plumbing (`clusterProjects` / save dialog used by `collection-detail.tsx`).
- **Export** — the matched table to CSV (and SDF where structures apply), reusing existing export utilities.
- (Later) acting on empty heatmap cells as explicit "analogs to make" — not in v1.

## 14. Pitfalls & guardrails (from research)

- **Correct core is mandatory** (garbage-in-garbage-out). Mitigated by seeding from the scaffold tree + explicit Edit/Draw override + visible matched/unmatched counts.
- **One comparable readout only** for any color/Δ comparison (§10). This is exactly where multi-run aggregation can mislead, so aggregation is scoped to a single readout definition.
- **Never silently drop compounds** — unmatched are always surfaced with a count.
- **Empty heatmap cells are gaps, not failures** — labeled as synthesis opportunities.
- (Phase-1 N/A but noted for Phase 2) activity cliffs must be **detection over measured data, not prediction**, with a tunable fold-change threshold (default ×100) and MMP-based pairing preferred over raw fingerprint thresholds.

## 15. Architecture & reuse map

**Reuse (no new code, just wiring):** scaffold tree + `bemis_murcko_smiles` (core suggestions); `enrich_molecules` + `run_aggregation` (activity); `use-aggregation-mode` (mode); `DoseResponseFigure` (curves); structure renderer / Ketcher (cores, thumbnails); cluster view's save-as-collection; view-mode toggle; export utilities.

**Net-new backend:** `domain/sar_analysis/rgroup_decomposition.py`; `infrastructure/rdkit/rgroup_decomposer.py`; `application/sar_analysis/decompose_rgroups.py`; route in `interface/routes/sar_analysis.py` (or extend scaffold_tree route); DI wiring in `infrastructure/di/_sar_analysis.py`.

**Net-new frontend:** `features/sar-analysis/components/` — `sar-view.tsx` (shell + sub-toggle), `core-picker.tsx`, `rgroup-table.tsx`, `rgroup-heatmap.tsx`; `hooks/use-rgroup-decomposition.ts`; integration into `lib/use-view-mode.ts` + `components/results/view-mode-toggle.tsx`.

**Layer order (per CLAUDE.md):** Domain → domain tests → persistence (none new beyond reuse) → integration tests → application → API → API tests → UI → E2E. **Mandatory reads before coding:** `docs/backend-code-guidelines.md`, `docs/patterns-and-conventions.md`.

## 16. Testing

- **Domain/unit:** decomposition VO; the RDKit decomposer wrapper against known cores/series (incl. unmatched handling, symmetric positions, core without explicit attachment points).
- **Application/integration:** `decompose_rgroups` over a seeded workspace set; activity reuse path returns expected values under each aggregation mode; single-readout guardrail enforced.
- **API:** endpoint contract, workspace scoping, auth guard, unmatched payload.
- **UI:** core-picker (auto-suggest + override + unmatched count), table (sort, Δ shading, row→curve), heatmap (axis pick, gaps, +N collapse/expand), color-by control.
- **E2E:** collection → SAR view → pick core → table/heatmap → save selection as collection.

## 17. Open questions / decisions to settle during implementation

1. **RGD parameters** for cores supplied as bare Murcko ring skeletons (no explicit attachment points) — confirm `RGroupDecompositionParameters` give chemically sensible R-group assignment; may need to derive a core with exit vectors.
2. **Selectivity ratio** computed frontend (from two `ActivityValue`s) vs a new backend selectivity column — start FE, revisit if needed.
3. **R-group thumbnail rendering** — backend depiction vs frontend RDKit.js; prefer FE RDKit.js for interactivity if performant.
4. **Sync vs async** decomposition for very large sets — sync for v1; adopt the scaffold-tree job pattern only if needed.
5. **Minimum-members gate** for enabling the SAR view-mode (mirror the cluster ≥10 pattern or lower).
