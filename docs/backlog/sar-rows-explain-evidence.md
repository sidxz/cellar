# SAR /rows EXPLAIN evidence (Unit C item 2)

**Date:** 2026-06-16 · **Probe:** `tests/integration/persistence/sar_analysis/test_decomposition_rows_explain.py`

## Finding
The `/rows` query's three joins ride composite PKs — `rgroup_assignments (run_id,
molecule_id)`, `sar_activity_values (projection_id, molecule_id)`, `molecules (id)`.
With `enable_seqscan=off`, the planner uses index scans on all three (no seq scan on
the SAR tables), confirming the indexes are usable for the join/filter/sort shape.

For `molecules`, the planner selected `uq_mol_ws_regnum` (the workspace-scoped unique
index on `registration_number`) rather than the plain PK, because it is more selective
for the `workspace_id` filter + `ORDER BY registration_number` shape. This is
correct: the PK is reachable and the planner picked a narrower index.

## Decision
**No new index added.** The handoff's proposed scoped-join / activity-join indexes are
already the composite PKs. The run-scoped `rgroups` filter operates on one run's rows
(PK-prefixed), so a speculative GIN on `rgroups` is not justified by evidence; revisit
only if a real workload shows the in-run jsonb filter dominating.

## Captured plan (enable_seqscan=off)

```
Limit  (cost=37.26..37.26 rows=1 width=455)
  ->  Sort  (cost=37.26..37.26 rows=1 width=455)
        Sort Key: m.registration_number, rga.molecule_id
        ->  Nested Loop Left Join  (cost=4.60..37.25 rows=1 width=455)
              Join Filter: (sav.molecule_id = rga.molecule_id)
              ->  Nested Loop  (cost=0.44..27.72 rows=1 width=415)
                    ->  Nested Loop  (cost=0.29..19.54 rows=1 width=431)
                          ->  Index Scan using uq_mol_ws_regnum on molecules m  (cost=0.14..8.16 rows=1 width=383)
                                Index Cond: (workspace_id = '3ee6619f-1351-4bc2-98dd-f096351b72bb'::uuid)
                                Filter: ((merged_into_id IS NULL) AND (molecular_weight > '0'::double precision))
                          ->  Index Scan using rgroup_assignments_pkey on rgroup_assignments rga  (cost=0.15..8.17 rows=1 width=64)
                                Index Cond: ((run_id = 'd178850c-fe46-40c2-b765-7a2b0e61d5c4'::uuid) AND (molecule_id = m.id))
                    ->  Index Scan using rgroup_runs_workspace_status on rgroup_decomposition_runs r  (cost=0.15..8.17 rows=1 width=16)
                          Index Cond: (workspace_id = '3ee6619f-1351-4bc2-98dd-f096351b72bb'::uuid)
                          Filter: (id = 'd178850c-fe46-40c2-b765-7a2b0e61d5c4'::uuid)
              ->  Bitmap Heap Scan on sar_activity_values sav  (cost=4.16..9.50 rows=2 width=56)
                    Recheck Cond: (projection_id = '38ea11af-885e-4302-9db4-7eb5076d8fbf'::uuid)
                    ->  Bitmap Index Scan on sar_activity_values_pkey  (cost=0.00..4.16 rows=2 width=0)
                          Index Cond: (projection_id = '38ea11af-885e-4302-9db4-7eb5076d8fbf'::uuid)
```
