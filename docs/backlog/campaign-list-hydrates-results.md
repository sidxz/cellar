# Campaign list and summary reads hydrate every result and measurement

**Found:** 2026-09-11, spec §4.4 of `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` (recorded during the `feat/stage-gates` review).

**Root cause:** `CampaignModel.results` is `lazy="selectin"` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`), and `CampaignResultModel.measurements` likewise. Every campaign load therefore pulls the full result and measurement rows, including the two reads that deliberately do *not* ship them:

- `GET /api/v1/campaigns?project_id=…` (list) — returns `CampaignSummaryResponse`, which drops `results` and emits `result_count`.
- `GET /api/v1/campaigns/{id}/summary` — same projection for one campaign.

So the wire payload shrank but the database work did not: a project with 30 campaigns × 500 results still loads 15k result rows plus their measurements to emit 30 integers. The funnel counts the summary *does* need (`evaluate_stages` + `tally_stage_counts`) are computed from those same hydrated results, so the fix is not simply "don't load them".

**Impact:** no regression versus the old behaviour (the list route previously serialized the results as well, so this is strictly cheaper), but the list route's cost still scales with total result count rather than campaign count. It is the first thing to bite when a project accumulates large campaigns.

**Fix direction:** in `find_by_project` / `find_by_workspace` (`infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py`), add `noload(CampaignModel.results)` to the statement and source `result_count` from a correlated `count()` subquery. That requires a second projection path for the funnel counts, since `tally_stage_counts` needs per-result outcomes — either a SQL-side tally, or accept that `/summary` (one campaign) keeps hydrating while the list (N campaigns) does not. Do the list route first; it is where the N multiplies.
