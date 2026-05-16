# Search: sync the per-criterion `run_scope` filter with the toolbar "Show" aggregation — design

> **For agentic workers:** This is a design doc. The implementation plan will live at a `…-plan.md` sibling once the design is approved. Use `superpowers:writing-plans` to turn this into the task-by-task plan.

## Goal

Resolve the visible disconnect between the per-criterion **runs** filter (in the search form) and the toolbar **Show:** dropdown (above the results grid) so that the two controls behave as one composed thing from a chemist's perspective. The fix is purely UX — the backend already composes the two correctly; the FE just doesn't communicate it.

## Background

The 2026-05-15 multi-run aggregation work introduced two filters on the search results grid:

1. **`run_scope`** (per-criterion, on each activity criterion in the search form): determines *which* runs are eligible. Wire shape: `any | latest | all | specific{run_ids[]} | date_range | past_n_days`.
2. **`aggregation` / "Show:"** (global, in the results toolbar): determines *how* to collapse the eligible runs of one `(compound, intercept)` cell into one number. Wire shape: `LATEST_APPROVED_RUN | GEOMETRIC_MEAN | MEAN_ACROSS_RUNS | BEST_R_SQUARED`.

A chemist using the system reported two intuitive expectations the UI doesn't reinforce:

- When `run_scope` narrows to one specific run, the toolbar dropdown should disappear — there is no choice to make.
- When the chemist picks several specific runs and chooses "Latest," they expect the latest *among the selected runs*, not the latest run overall.

The second behavior is already what runs at the backend (the SQL filters by `run_scope` before `apply_selection_rule` sees the candidate list). The first is purely a missing FE affordance.

## What's already correct (do not change)

- **Backend composition order.** `MoleculeActivityService._fetch_curves_and_runs` (`backend/src/cellar/application/screening/molecule_activity_service.py:383`) groups DR specs by their per-column `RunScope` and calls `find_all_curves_for_molecules(..., run_scope=scope)`. Only the scoped curve list is then handed to `apply_selection_rule`. "Latest" therefore already means "latest among in-scope" without any code change.
- **Per-cell decoration.** `InterceptCell` (`frontend/src/features/research-organization/components/search/intercept-cell.tsx`) reads `runCount = av.run_count ?? 1` and gates the subscript ₙ, fold-range chip, disagreement glyph, and Popover drill-in on `runCount >= 2`. Cells with a single in-scope run already render plain, regardless of toolbar mode.
- **Chart overlay.** `DoseResponseCell` (`frontend/src/features/research-organization/components/search/dose-response-cell.tsx`) forwards `additional_curves` + `aggregate` marker only when the backend writes them (gmean / mean modes). Latest / Best R² cells draw the rep curve alone. Single-run cells draw their one curve.
- **URL state.** `?agg=...` round-trips unchanged; saved searches persist `query.aggregation` and reload it correctly.
- **Multi-criterion scope merge** (`_collect_run_scopes` LAST-wins): pre-existing smell flagged in CLAUDE.md session notes; **explicitly out of scope** for this design.

## Core observation

The only axis that drives toolbar relevance is **per-cell in-scope cardinality**:

| In-scope runs for the cell | Toolbar effect | Cell decoration today |
|---|---|---|
| 0 | irrelevant — empty cell | — |
| 1 | **all four options identical** — toolbar is dead UI | plain value, no decoration, no drill-in |
| ≥2 | toolbar drives the answer | subscript ₙ, optional fold-range chip / ⚠, drill-in Popover |

Per-criterion scope mode → per-cell cardinality bound:

| `run_scope.mode` | Max per-cell cardinality |
|---|---|
| `any` / `all` / unset | unbounded |
| `past_n_days` / `date_range` | unbounded |
| `specific` with **N≥2 IDs** | bounded by N (but still potentially multi-run) |
| `specific` with **exactly 1 ID** | ≤ 1 |
| `latest` (= `last_n(1)`) | ≤ 1 |

The bottom two rows are the only modes where the toolbar is **provably** useless across every cell in the result set. They are the trigger condition for hiding the dropdown.

## Decisions Locked

| # | Decision | Rationale |
|---|---|---|
| D1 | When **every** activity criterion's `run_scope` is single-run (mode `latest`, or `specific` with exactly one `run_id`), replace the toolbar dropdown with a static muted label. | The dropdown has no effect on any cell in this state; rendering it as a live control is dishonest. |
| D2 | Static label text: **"Single run per compound"**. | Chemist-natural; describes what's happening at the unit a chemist cares about (compound → value), no jargon. |
| D3 | Trigger prefix when dropdown is shown: **"Summarize:"** (was "Show:"). | Chemists already use "summarize" for collapsing replicate values; verb-first; reads cleanly with all four option labels (`Summarize: Latest run`, `Summarize: Geometric mean`, …). |
| D4 | Tooltip on the dropdown trigger (always present when shown): "Each cell with multiple in-scope runs is reduced to one value using this rule. Cells with one in-scope run ignore it." | Removes the residual ambiguity that the rule applies *within* the scope window, not globally. |
| D5 | Tooltip on the static label when hidden: "You've narrowed each criterion to one run, so there's nothing to summarize. Loosen the runs filter to enable summarization." | Explains the affordance change rather than leaving the chemist guessing. |
| D6 | Trigger condition is **per-query, not per-cell.** Even when scope is `specific` with N ≥ 2 IDs, the dropdown stays live — because individual compounds may have 2+ of the N runs and the dropdown matters for them. | A search-wide control needs a search-wide trigger; per-cell relevance is already communicated by the absence of decoration on single-run cells. |
| D7 | `past_n_days` / `date_range` do **not** trigger the hide. | These are range filters; cells can have 0, 1, or many in-scope runs. Hiding would be premature. |
| D8 | No backend change. | Composition order is already correct; per-cell `run_count` is already on the wire. |
| D9 | No change to cell rendering, chart, URL state, or saved-search semantics. | These are already aligned with the chemist's intuition; only the toolbar widget needs work. |
| D10 | URL `?agg=...` stays in the URL even when the toolbar is hidden. | Loosening scope later re-exposes the dropdown with the persisted value. No silent state loss. |

## Files Touched

### Modified

| Path | Change |
|---|---|
| `frontend/src/features/research-organization/components/search/aggregation-control.tsx` | Add `disabled?: boolean` + `disabledReason?: string` props. When `disabled === true`, render the static label (no Select). Otherwise render today's dropdown but with the new trigger prefix and a tooltip on the trigger. |
| `frontend/src/features/research-organization/components/search/results-toolbar.tsx` | `ResultsToolbarActions` takes a new `scopeForcesSingleRun: boolean` prop and forwards it to `<AggregationControl />` as `disabled`. |
| `frontend/src/features/research-organization/components/search-page.tsx` | Compute `scopeForcesSingleRun = computeScopeForcesSingleRun(currentQuery?.criteria ?? [])` and pass it to `<ResultsToolbarActions />`. |
| `frontend/src/features/research-organization/lib/use-aggregation-mode.ts` | Add and export a pure helper `computeScopeForcesSingleRun(criteria: AnyCriterion[]): boolean` (criteria walker; `true` iff at least one activity criterion exists AND every one of them has `run_scope.mode === "latest"` OR (`run_scope.mode === "specific"` && `run_ids.length + (run_id ? 1 : 0) === 1`)). Returns `false` for empty criteria lists (no activity column = no relevant scope). |

### New tests

| Path | Coverage |
|---|---|
| `frontend/src/features/research-organization/lib/use-aggregation-mode.test.ts` | Existing file — append cases for `computeScopeForcesSingleRun`: no criteria → false; single activity criterion with `mode=latest` → true; single criterion with `mode=specific, run_ids=[x]` → true; criterion with `mode=specific, run_ids=[x, y]` → false; criterion with `mode=past_n_days` → false; two criteria, one `specific 1` + one `any` → false (the `any` still allows multi-run); two criteria both `specific 1` → true; legacy single-id shape (`run_id="x"`, `run_ids` absent) → treated as 1. |
| `frontend/src/features/research-organization/components/search/aggregation-control.test.tsx` | Existing file — add cases: with `disabled=true` renders the static label and **does not** render a Select; with `disabled=false` renders today's Select with the new "Summarize:" prefix; the static label's tooltip carries D5's text; the dropdown trigger's tooltip carries D4's text. |

### Not touched

- Any backend file.
- `InterceptCell`, `RunHistoryTooltip`, `DoseResponseCell`, `DoseResponseFigure`, `results-grid.tsx` — already render correctly given the wire shape.
- `useAggregationMode` URL behavior — unchanged.
- Saved-search load/save paths — unchanged.

## Wire-shape additions

**None.** This is a FE-only change.

## Acceptance criteria

A chemist running the dev stack against a protocol with at least one compound that has 3+ approved runs can verify:

1. **Default state.** Open `/search`, build a query with one activity criterion (`runs` = `Any run`). Toolbar shows `Summarize: [Latest run]`. Hovering the trigger shows D4's tooltip. Cells with multi-run compounds carry subscript ₙ and a drill-in Popover; single-run compound cells render plain.
2. **Narrow to one specific run.** Change the criterion's `runs` filter to `Specific run` and pick one run. Re-run. Toolbar widget becomes the static label `Single run per compound`. Hovering it shows D5's tooltip. URL `?agg=...` is preserved if it was set. All cells render plain (no subscript, no drill-in).
3. **Narrow to `latest`.** Change the criterion's `runs` filter to `Latest run`. Toolbar collapses to the static label as in (2).
4. **Narrow to multiple specific runs.** Change the criterion's `runs` filter to `Specific run` and pick 3 runs. Toolbar stays as the live dropdown. Switching it to `Geometric mean` recomputes cells across the 3 in-scope runs only (latest-of-selected, gmean-of-selected, etc.). The DR chart on multi-run cells switches between the rep-curve view (Latest / Best fit) and the aggregate overlay view (Geometric / Arithmetic mean) appropriately.
5. **Two criteria, one narrow one open.** Add a second activity criterion on a different protocol with `runs = Any run`. With the first criterion still narrowed to `Specific run` (1 ID), toolbar stays live (the second criterion's cells can still be multi-run). The narrowed criterion's cells render plain; the open criterion's cells carry decoration as appropriate.
6. **Saved-search round-trip.** Save a search in state (2) with `?agg=geometric_mean` in the URL. Reload it. Toolbar comes back as the static label; URL is restored. Loosen the criterion back to `Any run` and re-search — toolbar reappears showing `Geometric mean` selected.

## Risks and caveats

- **Per-cell vs per-search trigger.** D6 chooses a per-search trigger (only hide when *every* criterion is single-run). The alternative — hide per-cell — would require dropping the toolbar entirely on the page and instead surfacing the rule per-column, which is a much bigger change. We accept the small dishonesty that the dropdown is *live* but *useless* for some cells inside a result set with mixed scopes; that case is already mitigated by the cell-level absence of decoration.
- **Date-range scopes** (`past_n_days`, `date_range`) intentionally do not trigger the hide. A range can yield one run for one compound and many for another; the toolbar must stay live.
- **Translatability.** "Summarize" and "Single run per compound" are English-natural; if the product later localizes, both strings need translator notes describing the intent ("collapse multiple replicate values into one" and "the runs filter has narrowed each compound to one measurement").
- **Multi-criterion scope merge** (`_collect_run_scopes` LAST-wins, pre-existing): unchanged here. A follow-up design should make scope per-column rather than per-search.
