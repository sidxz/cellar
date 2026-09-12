# Sorting by a `drc:` column ranks fitted curves only — reported endpoints sort as missing

**Found:** 2026-09-11, while implementing the reported-endpoint fallback for `drc:` columns
(`.superpowers/sdd/2026-09-11-import-data-shape/`, Task 4).
**Status:** Open. Pre-existing gap, deliberately out of scope for that task.

## Symptom

A `drc:<readout_definition_id>` column now shows a value for a compound that has no fitted
curve but does have a summary-imported *reported* endpoint on the raw readout layer
(`MoleculeActivityService._enrich_molecules`, the DR branch). Clicking the column header to
sort drops every one of those compounds to the bottom (nulls-last) regardless of how potent
the reported value is — the grid says `3.4 nM` and the sort treats the cell as empty.

## Root cause

Sort-by-DR-column is served by a different query from the cell values. `_apply_drc_sort`
(`backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_reader.py`,
~line 525) builds its ranking subquery over `dose_response_curve` alone:

```python
best_value_sq = (
    select(
        DoseResponseCurveModel.molecule_id.label("molecule_id"),
        func.min(DoseResponseCurveModel.fitted_value).label("best_value"),
    )
    .where(
        DoseResponseCurveModel.workspace_id == workspace_id,
        DoseResponseCurveModel.readout_definition_id == readout_definition_id,
    )
    .group_by(DoseResponseCurveModel.molecule_id)
    .subquery("drc_best")
)
```

A compound with no row in `dose_response_curve` for that readout-def produces no row in
`drc_best`, so the outer join yields `best_value IS NULL` and the `nulls_last()` ordering
parks it at the end. The raw-layer `readout_data` rows the cell renderer now falls back to
are invisible to this subquery.

## Suggested fix

Union the raw readout layer into the ranking subquery, so a molecule contributes a candidate
from whichever layer it has (curve rows preferred, endpoint rows as the fallback — mirroring
the value path's "a curve always wins" rule):

- select `molecule_id, fitted_value` from `dose_response_curve` for the readout-def, and
- select `molecule_id, value_numeric` from `readout_data` for the same readout-def with
  `normalization_applied IS NULL`, `is_outlier = false`, `value_numeric IS NOT NULL`,
  `molecule_id IS NOT NULL` (same candidate predicate as
  `channel_resolution_query._readout_stmt`),
- `UNION ALL` the two, then `min(...)` grouped by `molecule_id`.

If "a curve always wins" matters for ordering too (it does for the displayed value), rank the
two layers per molecule instead of a flat `min` — e.g. `min()` over the curve layer with the
endpoint layer's `min()` used only via `COALESCE` when the curve layer has no row.

Needs an integration test in
`backend/tests/integration/persistence/chemical_registration/` covering: curve-only molecule,
endpoint-only molecule, and a molecule with both (curve value must win the ordering).
