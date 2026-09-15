# Reopening and re-closing a campaign silently rewrites its frozen cells

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`). This is a compliance question for the owner, not a crash.

**Root cause:**
- `Campaign.reopen` (`backend/src/cellar/domain/research_organization/campaign.py:400-418`) only flips a closed campaign back to draft, clears the close metadata and records the reason.
- `CloseCampaign` (`application/research_organization/close_campaign.py:98-123`) re-resolves every cell that isn't a manual override from live data, the same loop as refresh, then rebuilds `source_protocols`.

Reopen followed by re-close therefore replaces the values the campaign was closed with by whatever the live data says now. That includes refits, re-imports, and sources that have since gone, which become untested ND cells. The events record only the reopen and the close. Unverified: whether per-cell before and after values reach the audit trail.

**Also:** close nulls `contributing_run_ids`, `replicate_count` and `qc_pass`. The resolver builds `CampaignMeasurement` without them (`application/research_organization/channel_resolution.py:338-351`). Dev: 0 of 88 closed cells carry them, against 1,885 of 5,769 draft cells.

**Fix direction (owner decision):**
- Either re-close keeps frozen cells and re-resolving stays an explicit refresh,
- or re-close writes per-cell before and after values into the audit operation.

Separately, the resolver should carry the three fields, or they should be dropped if nothing reads them.
