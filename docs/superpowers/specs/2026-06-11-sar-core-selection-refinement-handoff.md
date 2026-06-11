# SAR Workbench — Pre-Phase-2 Core-Selection Refinement (HANDOFF)

- **Date:** 2026-06-11
- **Branch:** design-6 (Phase-1 SAR workbench complete + green; 37 commits)
- **Status:** HANDOFF for a fresh session — brainstorm → spec → plan → build. This documents a UX gap found by running the shipped Phase-1 UI on a real (diverse) collection. Do it BEFORE Phase 2 (activity cliffs + MMP), since a chemist-usable core picker is a prerequisite for that layer.
- **Workflow for the fresh session:** start with `superpowers:brainstorming` (this doc is the problem statement, not a finalized spec), then `writing-plans`, then subagent-driven build — same rhythm as Phase 1. Read `docs/superpowers/specs/2026-06-09-sar-workbench-rgroup-design.md` (the Phase-1 design) and the plans (`docs/superpowers/plans/2026-06-09-sar-workbench-*.md`, `2026-06-10-...`) first.

## What shipped in Phase 1 (works, tested, green)
The `sar` view-mode on collection detail: core picker → R-group decomposition table (structure + R1…Rn + physchem) + activity coloring + 2-axis heatmap + save-as-collection; "Open in SAR" from a scaffold node. Backend `POST /api/v1/sar/r-group-decomposition` (RDKit RGroupDecompose). All the *plumbing* is correct and reviewed.

## The gap (observed running it on a diverse 30-molecule collection)
The **core-selection experience** is not chemist-ready for non-congeneric collections:

1. **0-member and singleton cores are offered.** The candidate list shows every ringed scaffold-network node ranked by direct member count: `3, 3, 2, 1, 1, …, 0, 0, 0`. Count-0 nodes (generic ring-removed *parents*) and the long tail of count-1 leaves are not usable cores.
2. **Wrong ranking metric.** The picker ranks/auto-suggests by each node's **direct Bemis-Murcko `molecule_count`** (molecules whose *exact* Murcko scaffold == the node). For an R-group core the relevant number is **coverage** — how many molecules *contain* the scaffold as a substructure. The backend already computes a proxy: `subtree_molecule_count` (descendants in the Schuffenhauer network = molecules that contain the more-generic ancestor). Generic frameworks therefore show as "0" and get buried, while the one specific leaf shared by 3 molecules is crowned "dominant" → a 3-row table.
3. **Cores rendered as raw SMILES**, not structures — each chip is dominated by a long SMILES string with a tiny thumbnail.
4. **R-group cells expose attachment-point SMARTS** (`N#C[*:1]`, `[H][*:1]`) instead of a clean rendered fragment / human label.
5. **No graceful handling of "this isn't a congeneric series."** On a diverse set the UI dumps a wall of singletons instead of guiding the chemist.

Root cause framing: this is a **plan under-spec** (Task A4 said "rank by `molecule_count`, preselect the dominant"), not an implementation bug. For a true analog series the current UI behaves reasonably; it must degrade well for diverse inputs.

## Proposed refinement scope (prioritize 1–4; 5 optional)
1. **Coverage-based core candidates (the core fix).** Rank, display, and filter candidate cores by **coverage** (molecules that contain the scaffold), using `subtree_molecule_count` as the proxy (so generic frameworks surface with their real coverage, not "0"). Filter out candidates below a small threshold (e.g. coverage < 3). Auto-suggest a sensible default that balances coverage and specificity — not the lone specific leaf. **Never show a 0-coverage core.** (Validate the `subtree_molecule_count` proxy against actual RGD substructure-match counts; if it's materially off, consider a small backend "candidate cores with substructure coverage" computation — but start FE-only with the proxy.)
2. **Render cores as structures.** Lead with a clear scaffold thumbnail; show coverage as a badge; demote the SMILES to a tooltip/secondary line. No giant SMILES as the primary label.
3. **Clean R-group fragment cells.** Render the substituent cleanly and strip/handle the `[*:1]` attachment notation (don't show raw SMARTS as the primary text; optionally derive a human label, e.g. "–C≡N", "–C(=O)NH₂", "–H").
4. **Graceful non-congeneric handling.** When no scaffold reaches the coverage threshold, say so plainly ("This set doesn't share a common scaffold — draw/pick a core, or SAR works best on a focused analog series") and steer to **Edit/draw core**, rather than listing singletons.
5. **(Optional) Core-level navigator.** A compact scaffold-hierarchy picker (generic ↔ specific) reusing the existing scaffold tree, so the chemist chooses the grouping level deliberately.

## Affected files (pointers for the fresh session)
- `frontend/src/features/sar-analysis/components/rgroup-core-picker.tsx` — the candidate-core ranking/filtering/display + auto-suggest (uses `molecule_count`; switch to coverage; render structures; add the no-good-core guidance). **Primary file.**
- `frontend/src/features/sar-analysis/hooks/use-scaffold-tree.ts` + `types/scaffold-tree.ts` — `ScaffoldTreeNode { scaffold_smiles, molecule_ids, molecule_count, subtree_molecule_count }`. Coverage proxy is `subtree_molecule_count`.
- `backend/src/cellar/application/sar_analysis/build_scaffold_network.py` — computes `molecule_count` (direct) + `subtree_molecule_count` (rollup). If a true substructure-coverage count is needed, this/or a new use case is where it'd live.
- `frontend/src/features/sar-analysis/components/rgroup-table.tsx` — the R-group column `cellRenderer` (renders `StructureThumbnail` + the raw fragment SMILES text → clean it). Same fragment rendering reused by `rgroup-heatmap.tsx` axis headers.
- Decomposition itself (`infrastructure/rdkit/rgroup_decomposer.py`, `decompose_rgroups.py`) is correct — no change expected there.

## Test data note
The example "My Collection 1" is a **diverse** 30-molecule set, which is the hard case. Also test with a **true congeneric analog series** (a collection where most molecules share one scaffold) to validate the good-case behavior — the refinement should make BOTH read well: a clean dominant core + rich R-group table for a series, and clear guidance for a diverse set.

## Out of scope (still later)
- Full-collection coverage (vs the loaded page), search-results SAR entry, shared activity-display lib, minor robustness — see `docs/backlog/sar-workbench-frontend-followups.md`.
- Phase 2: activity cliffs + matched-molecular-pairs (build on the activity layer; do AFTER this refinement).
