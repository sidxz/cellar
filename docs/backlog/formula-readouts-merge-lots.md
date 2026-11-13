# Calculated (formula) readouts merge two lots of one compound in a run

**Found:** 2026-11-13, while checking whether ΔTm could be a calculated readout.
**Status:** Open. Pre-existing.

## Root cause

`ReadoutCalculationEngine._execute` (`backend/src/cellar/application/screening/readout_calculation_engine.py`)
builds formula bindings per molecule (step 5, `aggregated_values[molecule_id]`) and writes each
calculated row with a "representative" batch: the batch of the first raw row it saw for that
molecule (around lines 332-350). When one run holds two batches of the same compound (lot
comparison is routine for the thermal shift lab, whose old stock degrades), their raw values are
averaged or first-picked together, and the calculated value is attributed to one batch only.
`ReplicateAggregator` has the same molecule-level grouping
(`backend/src/cellar/domain/screening_assay/replicate_aggregator.py`).

## Suggested fix

Group step 5 and the formula evaluation by `(molecule_id, batch_id)` instead of `molecule_id`,
and write each calculated row with its own batch. Check the consumers that assume one calculated
row per molecule per run (campaign channel resolution reads per-row, so it should be unaffected).
Unit test: one run, one molecule, two batches with different raw values; expect two calculated
rows, one per batch, each with its own value.
