# Run hit criteria: a `between` rule passes every row

**Found:** 2026-11-13, design check for thermal shift analysis.
**Status:** Open. Pre-existing.

## Root cause

`applyHitFilter` in `frontend/src/features/screening-assay/components/run-dr-results-transforms.ts`
(around line 110) handles `gt`, `lt`, `gte`, `lte` and falls to `default: return true`. The
backend accepts `between` on a run hit criterion (`backend/src/cellar/domain/shared/hit_criterion.py`),
so a run saved with `IC50 between [1, 10]` shows every compound as a hit on the Dose-Response tab.

## Suggested fix

Add the `between` case (inclusive both ends, value `[low, high]`) and make the default case
return `false` so an unknown operator never passes silently. Unit test in
`run-dr-results-transforms` covering `between` inside, outside and on the edges.
