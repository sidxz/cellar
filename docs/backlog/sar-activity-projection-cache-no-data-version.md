# SAR activity projections serve stale values after deletes, refits and re-imports

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`).

**Root cause:** `SarActivityProjectionRepository.find_cached` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/sar_activity_projection_repository.py:69-84`) returns the latest READY projection for `(workspace_id, membership_hash, channel_hash)`, with no expiry. `channel_hash` (`application/sar_analysis/activity_channel.py:90-105`) hashes only the channel's semantic spec: column, intercept, selection rule, qualifier handling and run scopes. Nothing in the key changes when the underlying activity data changes. Any change to that data leaves the same collection and channel as a permanent cache hit on old values:
- a refit (curves are deleted and re-created),
- a readout re-import or recompute,
- a run or protocol delete.

**Fix direction:** add a data version to the key. For example, fold the max `updated_at` or a row-count or checksum of the readout and curve rows in scope into `channel_hash` at lookup time. Alternatively, invalidate projections from the curve, readout and run write paths. A delete-specific rule was deliberately not added in the force-delete change, because it would fix one trigger of three.
