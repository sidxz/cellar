# Older screens print the raw dose unit value instead of its label

**Found:** 2026-11-12, in the whole-branch review of the instrument file import (`feat/instrument-curves`).

**Root cause:** the protocol's dose unit reaches the frontend as its stored value (for example `uM`). `DOSE_UNIT_LABELS` in `frontend/src/features/screening-assay/types/index.ts` maps each value to its display label (for example `µM`), but several older screens print the value as it came:

- plate-map tooltips: `frontend/src/features/screening-assay/components/plate-map-viewer.tsx` (the well tooltip's "Dose" line)
- heat map: `frontend/src/features/screening-assay/components/plate-value-heatmap.tsx` (well tooltip) and `run-heatmap-panel.tsx` (the "Concentration (...)" header)
- the run import wizard: `frontend/src/features/screening-assay/components/run-import-wizard.tsx` (the protocol dose unit note)
- the search grid: `frontend/src/features/research-organization/components/search/results-grid.tsx` (curve and intercept column headers)

The instrument import wizard and the Curves table already go through `DOSE_UNIT_LABELS`.

**Fix direction:** print `DOSE_UNIT_LABELS[unit] ?? unit` in each of those places (or one small shared helper, if more than these call sites appear).

**Status:** recorded, not fixed.
