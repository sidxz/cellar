# Stage gates (batch 2) — parked follow-ups

**Branch:** `feat/stage-gates` (spec `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §4, issue #75).
**Source:** whole-branch review 2026-09-11 (`Minor` findings parked with rulings) and implementer notes.

- **Bulk promote can force `not_in_stage` rows into a stage.** Identical to the per-result override semantics the hit-stages spec chose (an override pulls a compound into the stage and its children's population). The stage lens pre-selects the population, so the visible set normally excludes them. Revisit only if chemists trip on it.
- **No-op re-mirror still writes.** Mirroring a protocol whose channels and stage already exist reuses the stage and rewrites identical criteria, bumping the aggregate version. Harmless; a "nothing changed" short-circuit is a few lines if audit noise matters.
- **422 vs 423 on a non-draft campaign between the two bulk routes.** `PUT …/stages/{id}/overrides` returns 423 (`DataLockedError`); `POST …/results/bulk-remove` returns whatever `remove_result_by_molecule`'s draft guard raises (pre-existing on the per-row DELETE too). Align when a client needs one status.
- **Reuse-path parent select wording.** On the add-from-runs and mirror dialogs, choosing a parent while the name reuses an existing stage re-parents that stage; the advisory says "criteria will be replaced" but not "parent will change". Extend the advisory text.
- **`stage_created` is False on reuse** and the outcome carries no `stage_id`; a client that wants "reused" vs "nothing happened" needs the id. Add when a consumer asks.
- **Reuse replaces criteria wholesale**, so hand-edits to a stage are lost on re-import under the same name (as specified). A UI confirmation on the reuse path would soften it.
- **`useCampaignSummary` has no production consumer yet** (built for the campaign header once ask 8 lands).
- **No test harness for the add-from-runs dialog**, so its parent select is covered only by the shared `stage-name-notice` helper and the mirror path.
- **Reorder chevrons are disabled on single-readout protocol rows** (nothing to swap with); cross-protocol moves are not offered.
- See also `campaign-channel-reorder-atomic.md` and `campaign-list-hydrates-results.md` (written by the fix wave).
