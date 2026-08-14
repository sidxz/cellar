# Plate Groups Hierarchy tab overflows viewport by ~68px regardless of legend (pre-existing, `12rem` offset miscalibrated)

**Found:** 2026-08-13, during S5 Task 13 fix-round re-verification of the tree-legend-height defect
(`plate-group-tree.tsx`, sidxz/cellar#71).

**Root cause:** `PlateGroupTreeView`'s tree/legend wrapper sizes itself with a static
`h-[calc(100vh-12rem)]`. At a 1600×900 viewport, `12rem` (192px) undercounts the actual page chrome
above it (top nav + `PageHeader` + `Tabs`/`TabsList` + tab-content margin — measured live at
~260px), so the wrapper's own fixed height already exceeds the space left in the viewport by
~68px, **independent of whether the legend row renders**.

Confirmed with a same-session A/B (git-stash the legend fix, re-measure, pop): the legend fix
recovered exactly 24px (92px → 68px overflow, matching legend height 16px + `gap-2` 8px) — but
68px of overflow was present **both before and after** that fix, proving it's a distinct,
pre-existing contributor the legend fix correctly did not touch. Measured via the same
`document.documentElement.scrollHeight` vs `window.innerHeight` technique as
`debug_legend_height.mjs`.

**Impact:** cosmetic only — nothing is clipped or broken (no `overflow-hidden` ancestor found), the
page just needs ~68px of extra scroll to reach the tree box's bottom edge at short (~900px-tall)
viewports. Same class of issue as the legend defect already fixed, just a larger, older,
unrelated contributor.

**Fix direction:** recalibrate the `12rem` constant against the actual rendered chrome height
(~260px, not 192px) in `frontend/src/features/inventory/components/plate-group-tree.tsx`'s outer
wrapper (e.g. `~16.25rem`), or better, let the parent page
(`plate-group-dashboard.tsx`) give the tree a flex-based `min-h-0 flex-1` slot so it fills
whatever space is actually left instead of guessing a fixed viewport offset. Verify by re-running
a `debug_legend_height.mjs`-style measurement at 1600×900 and confirming `overflowPx <= 0`.
