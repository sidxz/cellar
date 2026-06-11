# Backlog: SAR workbench frontend follow-ups

Deferred items from the SAR workbench Phase-1 frontend (Plans A + B, branch `design-6`, 2026-06-09/10). None are correctness bugs in the shipped scope; each is a scoped follow-up with its root cause.

> **PRE-PHASE-2 core-selection refinement — ✅ DONE** (2026-06-11, branch `design-6`, commits `c49bebf8` + `3444e926`). The core picker now ranks/filters candidate cores by **coverage** (exact subtree mol-id union, reusing `buildSubtreeMolIdMap`) instead of direct `molecule_count`; renders cores as structure tiles with a `covers N/total` badge (SMILES → tooltip); auto-suggests the most-specific broadly-shared core; humanizes R-group fragment cells **and** heatmap axes via a shared `fragmentDisplay` (CN/OMe/–H/…, never raw `[*:1]`, RDKit-validated dictionary + safe fallback); and shows plain-language *draw-a-core* guidance on non-congeneric sets. Design: `docs/superpowers/specs/2026-06-11-sar-core-selection-refinement-design.md`; original handoff: `…-refinement-handoff.md`. The proxy was validated against the backend RDKit (`matched ≤ coverage ≤ total`). The items below remain open follow-ups.

> **Phase-2 handoff (2026-06-11).** Item #1 below (full-collection coverage), plus **activity cliffs** and **matched molecular pairs (MMP)**, are scoped — with codebase findings + file pointers + recommended sequencing — in **`docs/superpowers/specs/2026-06-11-sar-phase2-handoff.md`**. Each is its own brainstorm → spec → plan → implement cycle for a fresh session (sizes: #1 small, cliffs moderate, MMP large/Temporal).

## 1. Full-collection coverage (most significant)

**Now:** `SarView` receives the host's paginated `molecules` (the loaded page from `collection-detail`). Decomposition, the activity fetch, the table, and the heatmap all scope to that loaded set — consistent, and honestly labelled "of N loaded compounds match this core".

**Want:** the SAR view should operate on the **full collection**, so a chemist analysing a 500-member series isn't silently seeing only the first page.

**Root cause:** the SAR view is set-agnostic (it analyses whatever `molecules` it's given); the host only loads a page. The scaffold-tree route already expands `collectionId` server-side to bypass the page cap — mirror that for the SAR view.

**Fix (one seam, benefits table + heatmap uniformly):** load the full collection membership for the SAR view (fetch all members and pass them as `molecules`), OR decompose + fetch activity by `collectionId` (the decomposition endpoint already accepts `collection_id` xor `molecule_ids`) and lazily resolve structure/physchem for off-page members. Update the "of N loaded" copy once full coverage lands.

## 2. Search-results SAR entry (deferred from Plan A)

**Now:** the `sar` view-mode attaches to **collection detail** + the scaffold-tree node "Open in SAR". Search results have no SAR entry.

**Root cause:** `search-page.tsx` renders `ResultsGrid` directly with no `ViewModeToggle`/`ResultsSurface` (only `collection-detail.tsx` hosts `ResultsSurface`).

**Fix:** migrate the search results area onto `ResultsSurface` (so it gets all view-modes incl. SAR), or add a parallel toggle + `sar` branch in `search-page.tsx`.

## 3. Extract shared SAR activity-display helpers into a lib

**Now:** `potencyShade`, `pickReference`, and `snapshotFromActivity` live in (and are exported from) `rgroup-table.tsx`; `rgroup-heatmap.tsx` imports them from that sibling **component** file (a smell). `snapshotFromActivity` also duplicates the `ActivityValue → CurveSnapshot` mapping inside `research-organization/.../dose-response-cell.tsx`.

**Fix:** extract them to `features/sar-analysis/lib/sar-activity-display.ts` (pure, with their tests), import in both `rgroup-table` and `rgroup-heatmap`; and extract a single shared `activityValueToSnapshot(av)` used by both the SAR code and `dose-response-cell.tsx` (DRY the snapshot mapping so a future `CurveSnapshot` field change touches one place).

## 4. Minor robustness / UX polish

- **`useSarActivity` `isFetching` on unmount:** if the component unmounts mid-request, the cleanup sets `cancelled` and neither `.then`/`.catch` clears `isFetching` (harmless — no state update on an unmounted component — but not clean). Use a `useRef` unmount guard, or move to `useQuery` with a stable query key.
- **`RGroupColorControl` readout hydration:** `selectedOptionId`'s `useState` initialiser derives from `readoutOptions`, which is empty on first render (the `useProtocol` query hasn't resolved). If `colorSpec` is ever persisted (URL/session) and the control re-mounts with a non-null `value`, the readout Select shows blank. Fix: a `useEffect` that syncs `selectedOptionId` from `value?.column` once `readoutOptions` loads. (Does not trigger today — `colorSpec` starts null and the control stays mounted.)
- **Heatmap same-axis:** picking the same R-position for both axes renders an advisory ("Same position on both axes — diagonal only") but still builds a diagonal-only grid. Consider a hard guard (require two distinct axes) if the diagonal view proves confusing.
- **`RGroupColorControl` `projectIds`:** currently always `undefined` (lists all workspace protocols). Could scope to the collection's project for a shorter, more relevant protocol list.
