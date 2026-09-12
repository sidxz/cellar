# The `drc:` reported-endpoint fallback only fires on unscoped columns

**Found:** 2026-09-11, whole-branch review of `feat/import-data-shape`
(`.superpowers/sdd/2026-09-11-import-data-shape/final-review.md`, finding I2).
**Status:** Open — a guard shipped; the full fix did not.

## Symptom

A `drc:<readout_definition_id>` search / SAR column that the chemist scoped (Last N runs,
Since a date, Specific runs) shows **no** value for a compound whose only data on that
readout-def is a summary-imported *reported* endpoint — even when that endpoint came from a
run inside the chosen scope. The same column with scope "all" shows it with a `reported` chip.

## Root cause

`MoleculeActivityService._enrich_molecules`
(`backend/src/cellar/application/screening/molecule_activity_service.py`) fetches curves
per column scope — `_fetch_curves_and_runs` groups the `drc:` specs by their `RunScope` and
passes each scope to `DoseResponseCurveRepository.find_all_curves_for_molecules`. The D1
reported-endpoint fallback added on this branch reaches for the raw readout layer instead:

```python
drc_fallback = await self._readout_repo.find_aggregated_by_molecules(
    workspace_id, missing_mols, [(rd_id, None) for rd_id in fallback_rd_ids], wellless_only=True
)
```

`find_aggregated_by_molecules` has **no run constraint at all** — it aggregates every
`readout_data` row in the workspace for that readout-def. Under a scoped column that is wrong
data behind a header the chemist believes is filtered, so the branch restricts the fallback to
columns whose scope `is_all()`. Correct, but it under-reports: a reported endpoint that *is*
in scope is dropped.

Same code path serves the search grid, the search export (`execute_search.py`) and the SAR
workbench (`sar_analysis/activity_enrichment.py`), so all three behave this way.

## Full fix

Thread `run_scope` into the raw-layer aggregate the way the curve repo already takes it:

1. Add `run_scope: RunScope | None = None` to
   `ReadoutDataRepository.find_aggregated_by_molecules` (domain port) and apply it in the
   SQLAlchemy implementation by joining `runs` and reusing the same scope→WHERE translation
   `find_all_curves_for_molecules` uses (last N by `run_date desc`, `since_date`,
   `explicit_run_ids`).
2. In `_enrich_molecules`, drop the `fallback_rd_ids` filter and instead group the fallback by
   scope exactly as `_fetch_curves_and_runs` does — one aggregate call per distinct scope.
3. Delete the guard comment in `_enrich_molecules` and this file; extend
   `TestEnrichMoleculesReportedEndpointFallback::test_scoped_column_does_not_fall_back`
   (`backend/tests/unit/application/screening/test_molecule_activity_service.py`) into a
   scope-respecting assertion: an endpoint on an in-scope run shows, one on an out-of-scope run
   does not.

## Why it was parked

The spec text (`docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md`, D1)
prescribes `find_aggregated_by_molecules` and never mentions scope — this is a spec gap, not a
deviation. Shipping the guard costs one list comprehension and cannot show wrong data; the
full fix changes a repository port signature plus its SQL, which belongs with the batch that
touches `find_aggregated_by_molecules` next.
