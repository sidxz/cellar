# Campaign result rows reorder after any per-row edit

**Found:** 2026-09-11, smoke-testing the notes-only PATCH on the screen-campaign grid
(`docs/superpowers/specs/2026-09-11-remove-campaign-decisions-spec.md`).

**Symptom:** save a note (or previously a decision, or a cell override) on a row, the campaign
refetches, and the grid's row order changes — the edited row jumps elsewhere in the list.

**Root cause:** `CampaignModel.results` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`)
is a `selectin` relationship with no `order_by`, so rows come back in Postgres heap order. An
`UPDATE` rewrites the tuple, which moves it in heap order, so the edited row's position changes
on the next load. `channels` and `stages` on the same model do set `order_by=display_order`;
`results` has no display order column at all.

**Fix:** give the relationship a stable order. Cheapest correct option is
`order_by="CampaignResultModel.id"` (deterministic, no migration); a chemist-meaningful option is
adding a `created_at`/`added_at` column to `campaign_result` and ordering by it (migration).
The frontend grid keys rows by `result.id` and applies no client sort, so fixing the backend order
is sufficient.

**Scope note:** pre-existing; not touched by the decision-removal branch.
