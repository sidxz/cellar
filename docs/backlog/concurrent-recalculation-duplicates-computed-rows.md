# Concurrent recalculations of one run can duplicate computed rows

**Found:** 2026-11-13, whole-branch review of `feat/thermal-shift-analysis`.
**Status:** Open. Pre-existing; made more frequent by melting-step review, which recalculates the run on every accept, reject, correct or add.

## Root cause

`ReadoutCalculationEngine._execute`
(`backend/src/cellar/application/screening/readout_calculation_engine.py`) deletes the run's
computed rows (`delete_computed_for_run`) and inserts the new set in the same transaction, but
nothing serializes two recalculations of the same run. Two transactions that start together both
delete the (same, old) rows and each insert a full new set; after both commit the run holds two
copies of every computed row (Tm, ΔTm, normalized layers, formula values). Campaign channels then
see duplicate candidates and means are unaffected but counts and "latest" picks are not.

## Suggested fix

Lock the run row at the start of `_execute` (`SELECT … FROM runs WHERE id = :id FOR UPDATE`, via
a repository method such as `RunRepository.lock_for_update(workspace_id, run_id)`), so a second
recalculation waits for the first and then replaces its rows. Integration test: run two
`compute_for_run` calls concurrently on one run and assert one set of computed rows.
