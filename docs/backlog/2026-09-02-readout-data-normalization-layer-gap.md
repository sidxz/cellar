# Per-protocol `readout_data` where-clause doesn't filter `normalization_applied`

**Found:** 2026-09-02, whole-branch review of `feat/any-protocol-activity-search`
(`.superpowers/sdd/2026-09-02-any-protocol-catalog-and-active-in-column/final-review.md`, Important 3).
**Status:** Open. Pre-existing gap, out of scope for that branch.

## Root cause

`_activity_where_clause`'s per-protocol `readout_data` branch
(`backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_activity_query.py`,
the `source == "readout_data"` arm around line 204) filters `readout_data` by `workspace_id`,
`readout_definition_id`, and `is_outlier = false` — but not `normalization_applied IS NULL`.

Per the repo comment at
`backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/readout_data_repository.py`
(~line 157, in `find_aggregated_by_molecules`): "Normalized rows (% inh / % act / % control)
carry the formula's output unit, not the raw readout's unit" — raw and computed rows share the
same `readout_definition_id`, distinguished only by `normalization_applied`. Without that filter,
a per-protocol activity search on a readout-def that has both raw and normalized
(`percent_inhibition` / `percent_activation` / etc.) rows can match a normalized row's value
against a cutoff meant for the raw layer, and vice versa.

The fix-wave for the any-protocol branch closed the identical gap in the *new*
`_readout_name_any_protocol_clause` path (it has a normalization-aware twin,
`find_aggregated_by_molecules_and_names`, that already filters correctly, so the new path had
no excuse not to match it) but left this pre-existing per-protocol path untouched, per the
"record unrelated issues, don't fix inline" rule.

## Suggested fix

Add `ReadoutDataModel.normalization_applied.is_(None)` to the `base_filters` list in the
`source == "readout_data"` branch of `_activity_where_clause`, matching
`find_aggregated_by_molecules_and_names` and the any-protocol readout clause. Small, local,
one-line change — needs an API test seeding a normalized-layer row on the same
readout-def to prove the per-protocol filter now ignores it (same shape as
`TestActivityAnyProtocol::test_readout_name_ignores_normalized_layer_rows` in
`backend/tests/api/test_search.py`).

## Notes

- Not urgent: only bites on readout-defs that carry both raw and computed-normalization rows
  and are also used in an activity search `where` clause on the raw layer.
- Cheap to fix once picked up; scoped out of the any-protocol branch only to keep that diff
  minimal per plan.
