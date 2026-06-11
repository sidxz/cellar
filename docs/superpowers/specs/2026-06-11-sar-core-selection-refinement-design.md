# SAR Core Picker — Chemist-Readiness Refinement (design)

Design for the pre-Phase-2 core-selection refinement called out in
`2026-06-11-sar-core-selection-refinement-handoff.md`. Brainstormed + approved 2026-06-11.

## Problem

Running the shipped Phase-1 SAR workbench on a **diverse, non-congeneric** collection exposed that
the core picker degrades badly off a clean analog series:

1. Offers unusable cores (count-0 generic parents + a long tail of count-1 singleton leaves).
2. Ranks/auto-suggests by direct Bemis-Murcko `molecule_count` (exact-Murcko membership) instead of
   **coverage** (molecules that *contain* the scaffold) — so generic frameworks show as `0` and get
   buried, and the lone specific leaf shared by 3 molecules is crowned "dominant" → a 3-row table.
3. Renders cores as raw SMILES (long mono string dominates each chip).
4. R-group cells expose attachment SMARTS (`N#C[*:1]`, `[H][*:1]`).
5. No graceful "this isn't a congeneric series" handling — dumps a wall of singletons.

## Decisions (brainstorming)

- **Auto-suggested default core:** the most **specific** scaffold that still covers a **strong
  majority** (≥50% of the set); fall back to highest-coverage if none clears the bar.
- **Coverage floor:** **≥3 compounds** (absolute). Hide cores covering 0–2; if nothing reaches 3 →
  show the "no shared scaffold" guidance.
- **Presentation:** flat, coverage-ranked **structure chips** (capped, with "show all"). No
  generic↔specific navigator (handoff optional #5 stays a follow-up).
- **R-group cells:** **human chemical labels** for common substituents (curated dictionary) +
  structure thumbnail, with a **cleaned-SMILES fallback so unknown fragments are never mislabeled**.
  Hydrogen shown as "–H / unsubstituted".
- **Coverage metric:** **exact, deduplicated** subtree-union count computed in the FE (reuse
  `buildSubtreeMolIdMap` from `lib/scaffold-tree-math.ts`), not the backend `subtree_molecule_count`
  scalar (which can double-count on DAG diamonds and exceed the set size).

## Approach (frontend-only)

Two new pure, unit-tested libs in `features/sar-analysis/lib/`, then thin the three components.

- `lib/sar-core-candidates.ts` — `buildCoreCandidates(tree, {floor=3})` →
  `{ candidates: {scaffoldSmiles, coverage, directCount}[], total }` (coverage from
  `buildSubtreeMolIdMap`, NO_SCAFFOLD excluded, ranked coverage DESC then specificity DESC then
  SMILES); `pickDefaultCore(candidates, total)` — among `coverage ≥ max(floor, ceil(total/2))` pick
  least-coverage (most specific) tie-broken by specificity; else top candidate; else `null`.
- `lib/sar-fragment-label.ts` — `fragmentDisplay(smiles)` →
  `{ label, isHydrogen, thumbnailSmiles }`. Collapse the dummy atom-map, look up a curated
  `SUBSTITUENT_NAMES` dictionary keyed on the (already-canonical) backend fragment SMILES, fall back
  to cleaned SMILES (never an invented name), special-case hydrogen.
- `components/rgroup-core-picker.tsx` — coverage ranking + `pickDefaultCore` auto-suggest;
  structure-led chips with a coverage badge (SMILES → tooltip); show-all cap; empty-state guidance
  steering to the existing Ketcher "Draw core". Keep the post-decomposition "N of M match" line.
- `components/rgroup-table.tsx` + `components/rgroup-heatmap.tsx` — render fragment cells / axis
  headers via the shared `fragmentDisplay`.

## Testing

TDD on both libs (analog series → real shared core; diverse → empty/guidance; two-series →
sub-series core; dedup coverage ≤ total; floor; known/unknown/H labels). Update the three component
tests for the new behavior. `pnpm test` green, `pnpm lint` exit 0.

## Out of scope / follow-ups

Generic↔specific navigator; full-collection scope; extracting shared activity-display helpers. A
backend "substructure-coverage" count only if the FE coverage proxy proves materially off vs actual
RGD match counts during verification.
