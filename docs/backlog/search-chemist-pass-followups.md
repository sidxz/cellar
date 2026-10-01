# Search page — follow-ups left by the 2026-10-01 chemist pass

**Found:** 2026-10-01, testing every `/search` control as a chemist (branch `fix/search-chemist-pass`).
Fixed items are in that branch's commits; these were left on purpose.

- **Project chip semantics (needs a product decision).** The chip shows "N compounds" = registered
  to the project (`molecule_projects`), but the `{type:"project"}` criterion reuses the visibility
  clause `_project_clause` = *unassigned compounds + the project's*. In saclab-dev no compound is
  registered to any project, so every chip reads "0 compounds" while the search returns all 61k.
  Options: (a) registered-only (matches the chip; dev returns 0), (b) registered **or tested in a
  protocol linked to the project** (useful immediately; chip count must change to match),
  (c) keep and relabel. Recommendation: (b).
- **Detail sheet shows a scalar for inactive curves.** `@structflo/components` `summary-card.tsx`
  prints `IC50 = 0.00077 uM` next to an "Inactive" badge (grid says ND). Fix upstream: render "ND"
  when `curve_class === "inactive"`. Inactive plots also auto-scale Y to ±5 %, making noise look like
  signal — a fixed 0–100 % range for inactive curves would read correctly.
- **Dead duplicate builder.** `SearchQueryBuilder` + most of `components/criterion-rows/` are
  exported but mounted nowhere (only `ScaffoldCriterionRow` is used). It still carries the old
  two-step selectivity picker. Delete or bring in line before reusing.
- **At-bound DR intercepts in filters.** Readout values honour `<`/`>` qualifiers now; a DR primary
  intercept that is `at_bound` (reported "> max dose") still compares its extrapolated fitted value.
- **Keyword list: say which ids were not found.** 4 pasted, 3 matched — the chemist isn't told
  which one missed (MoleculeResolver already returns the unresolved list).
- **Default sort.** With a potency filter, results come back in id order; sorting by the filtered
  potency (best first) is what a triage chemist expects. Client-side sort only covers the loaded page.
- **Data:** COX-2 / EGFR protocols have `dose_unit = uM` but IC50 readout `unit = nM` and
  concentrations up to 10000 — looks like nM data entered under a µM dose unit (seed/demo data).
