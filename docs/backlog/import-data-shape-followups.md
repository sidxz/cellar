# Import data shape (batch 1) — parked follow-ups

**Branch:** `feat/import-data-shape` (spec `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §3, issue #74).
**Source:** whole-branch review 2026-09-11 (`Minor` findings parked with rulings) and implementer notes.

- **Single-row readout create returns 422, bulk and imports return 409 for the same shape rule.** `application/screening/create_readout_data.py` treats "well_id required iff the run has wells" as a payload validation (422), matching bulk's per-item errors; the summary/plate paths refuse a whole import with `ConflictError` (409). Ruling: payload-level errors stay 422. Revisit only if a client needs one status for both.
- **Resolver issues one extra SELECT per dose-response cell with no QC-surviving curve** (`channel_resolution.py::ChannelResolver.resolve`, the D1 fallback). Close/refresh-time only; the runs-scoped add-from-runs path stays batched. Fold into the ask 8 persistence work if campaigns grow past a few thousand rows.
- **Compound activity summary hydrates every raw readout row for the molecule** to discover curve-less dose-response protocols (`molecule_activity_service.py::_get_activity_summary`, ponytail-marked). Fix = a repository query returning (protocol_id, readout_definition_id) pairs for well-less rows.
- **Compound activity readouts table cannot name the readout definition per row**, so two reported endpoints on one protocol look identical. Needs `readout_definition_name` on `ActivityValueResponse` (DTO change + orval regen). Candidate for batch 2.
- **`wellless_only` is a per-call opt-in** on `fetch_endpoint_candidates{,_for_runs}` and `find_aggregated_by_molecules`. A future third fallback caller must pass it; consider a dedicated `fetch_reported_endpoints` wrapper if one appears.
- **`drc:` sort still ranks curves only** — see `drc-sort-curves-only.md`. **`drc:` fallback fires only on unscoped columns** — see `drc-fallback-run-scope.md`.
- **Runs that already held both shapes before this branch** keep their data and now refuse further imports of either kind (dev data only; no backfill was in scope).
