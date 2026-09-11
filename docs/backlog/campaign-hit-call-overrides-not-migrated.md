# Migration 074 doesn't carry manual per-cell `hit_call` overrides into stage overrides

**Found:** 2026-09-11, implementing migration 074 for the Campaign Hit Stages + Soft Close feature
(`docs/superpowers/specs/2026-09-11-campaign-hit-stages-and-soft-close-spec.md` §8).

**Root cause:** migration 074's backfill (`build_stage_rows`, in
`backend/alembic/versions/074_campaign_hit_stages.py`) creates one `campaign_stage` (with one
`StageCriterion`) per `campaign_channel.hit_threshold` that has a non-`in` operator —
reconstructing the *channel-level rule* the old hit-call system was built on. It never reads
`campaign_measurement.hit_call` or `.is_manual_override`, so it cannot carry forward a **manual
per-cell hit-call override**: `OverrideResultCell`
(`backend/src/cellar/application/research_organization/override_result_cell.py`) lets a chemist
replace one (result, channel) cell with `is_manual_override=True` and an explicit `hit_call` that
may deliberately disagree with what a plain threshold comparison on the cell's `value` would
produce — e.g. flipping one borderline compound from MISS to HIT after a second look, without
touching the channel's threshold or the cell's numeric value. Once the migrated stage's criterion
is evaluated by the new evaluator (`evaluate_stages`,
`backend/src/cellar/domain/research_organization/stage_evaluation.py`), the computed outcome for
that cell comes purely from re-comparing `value` against the criterion — the old, manually-recorded
divergence is silently dropped unless a chemist notices and re-applies it by hand as a
`StageOverride`.

**Impact:** affects only **closed campaigns that have at least one manually-overridden cell with a
`hit_call` set**, and only in local/dev workspaces — this is pre-production data; no production
workspace exists yet. Cells where the manual `hit_call` happened to match what re-comparing `value`
against the migrated criterion produces lose nothing (the new evaluator reaches the same verdict).
Real divergences are limited to the — likely rare — cases where a chemist explicitly forced a
hit/miss call that disagreed with the numeric value, plus any cell with a manually-entered `value`
that has no threshold-comparable basis at all.

**How to reconstruct, if ever needed:** before migration `075` (drops
`campaign_channel.hit_threshold` and `campaign_measurement.hit_call` — see the spec's
"Implementation notes") has run against a given database: for each closed campaign, join
`campaign_measurement` (`hit_call`, `is_manual_override`, `value`) to its channel's
`hit_threshold` and to the `campaign_stage` / criterion migration 074 created from that same
threshold. Rows where the stored `hit_call` disagrees with re-evaluating the criterion against
`value` are the genuine manual overrides; for each, insert a `campaign_stage_override` row with
`forced_outcome` = the stored `hit_call`, `reason` noting it was migrated from a pre-stages
hit-call override (carry forward `campaign_measurement.override_reason` when present), and
`overridden_by` / `overridden_at` best-effort from the audit trail, else a system/migration
identity and the migration's run time. **Once migration `075` has run, the source columns are
gone** — reconstruction after that point needs a database backup or WAL snapshot taken before
`075`, not a live query. Given today's data is dev/local only, this has not been treated as work to
do before `075` ships; recorded here so it isn't forgotten if a real closed campaign with hit-call
overrides ever needs re-triage after the cutover.
