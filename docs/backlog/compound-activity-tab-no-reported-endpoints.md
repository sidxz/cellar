# Compound Activity tab never shows reported endpoints — the readouts table is fed by a field the backend never sets

**Found:** 2026-09-11, implementing Task 4 of
`.superpowers/sdd/2026-09-11-import-data-shape/` (reported-endpoint fallback + markers).
**Status:** Open. The task's brief scoped the compound page as a FE-only chip; the real gap is
in the backend read model, out of that task's scope.

## Symptom

Task 4 gave the *search* grid the reported-endpoint fallback (a `drc:` cell resolves from the
raw readout layer when no curve exists). The compound detail page's Activity tab does **not**
get it: a compound whose only data on a protocol is a summary-imported reported IC50 shows
nothing at all for that protocol — the protocol card isn't even rendered.

## Root cause

Two things, both in the `get_activity_summary` read path (a different query from
`enrich_molecules`, which is what Task 4 changed):

1. `MoleculeActivityService._get_activity_summary`
   (`backend/src/cellar/application/screening/molecule_activity_service.py`, ~line 118) derives
   `proto_ids` **only** from `self._curve_repo.find_by_molecule(...)`. A protocol with reported
   endpoints but no fitted curve produces no `ProtocolActivitySummary` at all.
2. It constructs every `ProtocolActivitySummary` with `best_curves=` and `intercepts=` only —
   `readouts=` is never passed, so `ProtocolActivitySummary.readouts` is always its
   `default_factory=list` empty list. (The only `readouts=` in the file is on the unrelated
   `_build_any_activity` call in `_enrich_molecules`.)

The frontend is already built for the data: `activity-tab.tsx` renders a readouts table
(Value / Unit / Source / Points) in the `curves.length === 0 && readouts.length > 0` branch,
and Task 4 put the `ReportedEndpointBadge` in its Source column. That branch is unreachable
today. Note it is also `else`-chained after the curve table, so even once `readouts` is
populated a protocol with *both* a curve and a reported endpoint on a different readout-def
would still hide the endpoint.

## Suggested fix

1. In `_get_activity_summary`, fetch aggregated raw-layer readouts for the molecule
   (`ReadoutDataRepository.find_aggregated_by_molecules` or the by-names variant) and pass them
   as `readouts=` on each `ProtocolActivitySummary`; widen `proto_ids` to the union of
   curve-bearing and readout-bearing protocols so an endpoint-only protocol gets a card.
2. In `activity-tab.tsx`, render the readouts table *in addition to* the curve table rather
   than as an `else` branch, so a protocol with both shows both.
3. API test in `backend/tests/api/` for a molecule whose only datum on a protocol is a
   reported endpoint: the protocol appears with a readout row carrying `source="readout"`.
