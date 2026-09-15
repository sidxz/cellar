# Cascade preview cost and missing indexes on the new predicates

**Found:** 2026-09-15, final review of feat/force-delete-id-references (spec docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md).

**Root cause:** `CascadeRunner.preview` (`backend/src/cellar/infrastructure/cascade/cascade_runner.py:100-108`) calls `plan()`, which runs the full exhaustive walk (`plan()` at :211-223, `_walk` at :225-272). For every CASCADE rule it selects the id of every matching row (`_walk`:258-260), including leaves that recursion reaches twice (readout_data via its run and via its readout definition). Preview only needs that full walk for blockers and warnings; the delete tree it shows is built separately, from 5 samples per rule. Before this branch, preview was counts plus 5 samples — much cheaper. At dev scale (6k readout rows) this is fine; a large HTS protocol's full readout/curve/well set is not.

Separately, the new match predicates hit columns with no index on dev, so every one of these seq-scans on a molecule or batch preview/execute, and on the equivalent Tier-1 deletes:
- `wells.batch_id`
- `readout_data.batch_id`
- `dose_response_curves.batch_id` (only present as a non-leading column in a composite index)
- `reaction_steps.product_molecule_id`
- `reaction_steps.batch_id`
- `sample_requests.batch_id`

**Fix direction:** skip id collection in `plan()` for CASCADE leaves that don't recurse further (a table with no rules of its own, or no `recurse_into_entity`) when called from `preview()` — a count is enough for those, same as before this branch. Add a migration indexing the six columns above. The spec (D5) ruled a migration for this out of scope for the initial branch.
