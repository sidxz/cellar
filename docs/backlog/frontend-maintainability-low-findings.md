# Frontend maintainability — deferred low-severity findings

**Created:** 2026-06-06
**STATUS: RESOLVED 2026-06-06** — all 22 items below were fixed on branch
`fe-review-1` (wave-4 commits `5ec5cebb..6ebdaa50`). Intentional skips,
each judged at fix time: three message-only empty states stayed as plain
text (forcing icon+title would regress them); JSDoc `/api/v1` route
references keep the literal; generated orval files untouched. Kept for
the historical record of what was found and why.

**Context:** A 6-dimension multi-agent review of `frontend/src` (duplication,
data-layer duplication, hand-rolled-vs-native, escape hatches, hardcoded
values, convention drift) produced 46 adversarially-verified findings.
The 9 high + 15 medium items were fixed on branch `fe-review-1`
(2026-06-06). The 22 low-severity items below were initially deferred,
then fixed the same day in a follow-up wave.

## Duplication

1. **Four divergent StepIndicator implementations** across import/registration
   wizards (`run-import-wizard.tsx:228`, `summary-import-wizard.tsx:176`,
   `inventory/import-wizard.tsx:73`, `registration-wizard.tsx:32`).
   → shared `WizardStepIndicator({ steps, current })` in `src/shared/components/`;
   also fixes the Mapping/Map label drift.
2. **'Structure' AG Grid column def duplicated** in
   `run-dr-results-columns.tsx:86` and `detail-tabs/activity-tab-columns.tsx:93`.
   → `structureColumn()` factory in a screening grid-columns module.
3. **List-loading Skeleton block copy-pasted ×8** (workspace-config admin
   components et al.). → `<SkeletonList rows={3} />` next to `empty-state.tsx`.
4. **Identical Set-toggle selection handler ×3** (`cluster-selection-pane.tsx:18`,
   `collection-detail.tsx:81`, `scaffold-tree-view.tsx:166`).
   → `useSelectionSet<string>()` in `src/shared/hooks/`.
5. **Local `formatBytes` duplicates shared `formatFileSize`**
   (`export-job-toast.tsx:65` vs `format-number.ts:42`). → delete local copy.
6. **Hand-rolled empty states bypass shared `EmptyState`/`ErrorState`**
   (`card-grid.tsx:118`, `shipment-detail.tsx:175`, `plate-detail.tsx:372`,
   `add-molecules-dialog.tsx:219`, `dose-response-chart.tsx:705`).
   (The medium-severity adoption pass covered list/grid surfaces; these
   stragglers remain.)
7. **Duplicate local `PaginatedResponse<T>`** in `inventory/types/index.ts:207`
   shadows `shared/types/pagination.ts`. → re-export/import the shared one.
8. **Link/unlink target mutation hooks duplicated** between
   `use-protocol-targets.ts:42` and `use-run-targets.ts:26`.
   → `createTargetLinkHooks({ entity, labels, invalidateKeys })` factory.

## Hand-rolled vs native

9. **`<a href>` for internal nav** (full page reload):
   `workspace-settings-form.tsx:266`, `step-results.tsx:326` (the latter is
   inside `<Button asChild>` — swap inner `<a>` for `next/link`'s `<Link>`).
10. **`protocol-section.tsx:78` reimplements `formatRelativeDate`** with a
    divergent threshold table. → use shared helper; add an option if the
    year-omitting fallback is genuinely needed.
11. **Inline grouping loop** in `screen-campaign/.../results-grid.tsx:302`
    reimplements `groupBy` from `@/shared/lib/group-by`.

## Escape hatches

12. **Editable form-row lists keyed by array index** → input/focus
    misreconciliation on add/remove (`intercepts-editor.tsx:101`,
    `hit-criteria-dialog.tsx:195`, `edit-qc-metrics-dialog.tsx:162`,
    `custom-field-builder.tsx:49`, `protocol-form-admin.tsx:247,376`).
    → stable client ids; RHF-based forms should use `useFieldArray`'s
    `field.id`. Overlaps the `noArrayIndexKey` burndown
    (see frontend-biome-warning-burndown.md) but these six are *editable*
    rows, i.e. the genuinely buggy subset.

## Hardcoded values

13. **`.slice(0, 8)` UUID-shortening ×14 sites / 7 files** with one divergent
    copy. → `shortId()` helper with a single `SHORT_ID_LEN` + ellipsis policy.
14. **`/api/v1` prefix hardcoded in every hook's URL string.**
    → `export const API_V1 = "/api/v1"` in a shared endpoints module
    (note: must not collide with orval's generated
    `src/shared/lib/api/endpoints.ts`); optionally per-feature endpoint maps.
15. **Inline `staleTime` values restated per hook** (incl. a redundant 60_000
    override matching the query-provider default).
    → `STALE_TIME` tier object in `timing.ts`/`query-defaults.ts`.
16. **Picker search limits hardcoded (20/25) + debounce spread (200/250/300).**
    → `PICKER_RESULT_LIMIT`, `SEARCH_DEBOUNCE_MS` shared defaults; reconcile
    the debounce spread unless a surface documents why it differs.

## Conventions

17. **Conditional classNames via template literals instead of `cn()`**
    (curve-class-badge, readout-definition-viewer-dialog, run-detail:729,
    search-query-builder:171, research-org results-grid:219, …). Mechanical.
18. **Three files import `toast` directly from sonner**, bypassing
    `shared/lib/toast` (collection-import-wizard/index.tsx:140,
    scaffold-tree-view.tsx:355, mirror-summary-toast.tsx:29). The wrapper
    lacks `showLoading`/`dismissToast` — extend it, then migrate.
19. **`tagging` uses `types.ts`** while every other feature uses `types/`;
    `formulation` is a bare stub dir. → normalize layout.
20. **Per-feature `index.ts` barrels inconsistently populated/used**
    (some empty, deep imports dominate). → pick one stance (populate +
    lint-enforce, or drop empty barrels) and apply uniformly.
21. **Zustand store location/naming inconsistent**
    (`shared/lib/stores/preferences-store.ts` vs
    `shared/components/layout/breadcrumb-context.tsx` — a store with no JSX).
    → `*-store.ts` naming, one documented location policy.
22. **`style={{ textTransform: "uppercase" }}`** in
    `workspace-settings-form.tsx:212`. → `className="uppercase"`.

## Source

Full machine-readable findings (incl. the fixed high/medium set, verifier
notes, per-finding file:line evidence): generated 2026-06-06 by the
`fe-maintainability-review` workflow; archived copy at
`/tmp/fe-review-findings.json` (re-derivable by re-running the review).
