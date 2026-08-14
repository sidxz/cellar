# S6 legacy plate-tracker migration — deferred minor findings

**Context:** S6 (`backend/scripts/migrate_legacy_plate_tracker.py` + tests) shipped 2026-08-14 via subagent-driven development. Per-task reviews + a whole-branch opus review found **zero Critical and zero data-integrity defects**; all Important findings were fixed in-flight. These Minors were consciously deferred (reviewers agreed: defer / backlog). None block the migration.

Plan: `docs/superpowers/plans/2026-08-14-s6-legacy-plate-tracker-migration.md`. Issue: sidxz/cellar#71.

## Deferred (safe to leave; fix opportunistically when touching the file)

1. **`read_legacy` (pymysql I/O) has no automated test.** Inherently needs a live MySQL fixture; the runbook's *mandatory* dry-run (step 4, against a restored `sacnet_prod.sql`) is the real validation gate for the reader. Acceptable for a one-shot script.
2. **`apply_plate_ownership` accepts an unused `uow` param** (dead; call site passes `uow=uow`). 10-second cleanup.
3. **`_set_plate_status` fail-loud on an unreachable transition.** If a matched Cellar plate is already `DEPLETED`/`DISPOSED` while legacy says `Active`/`AVAIL`, `transition_status` raises and (uncaught) rolls back the whole atomic run — inconsistent with the unknown-role/status path, which is skipped-and-reported. Data-safe (atomic rollback; error names `plate.id`). **Confirm against the real dry-run**; if any such drifted plate exists, either pre-fix those rows or route this to a third report CSV (matching the unmapped pattern). Also: `_set_plate_status`'s `status == target` no-op guard is unreachable via its sole caller (harmless).
4. **Ownership `stats` dict + unmapped-role skip path untested.** `classified`/`skipped_unmapped`/`inactive_tagged` counters are operator-info, unasserted; `if plate is None: continue` bumps no counter (near-impossible right after a same-transaction match). Low ROI.
5. **`mypy.ini` lacks a `[mypy-pymysql.*]` ignore-missing-imports stanza** that sibling deps (`asyncpg`/`rdkit`/`temporalio`/`lagom`) have. Zero impact today — mypy is not wired into CI/Makefile/pre-commit anywhere. Two lines when convenient.
6. **`plan_group_tree` hand-rolls a topological sort** instead of stdlib `graphlib.TopologicalSorter`. Works, tested, and matches two pre-existing hand-rolled Kahn's implementations in the repo (`synthesis_route.py`, `readout_calculation_engine.py`) — swapping is a lateral move, not a fix. Repo-wide consolidation candidate.
7. **`assign_plates_to_groups` doesn't self-assert the plate-org == group-org invariant.** Per `RegisteredPlate.assign_to_group`'s own docstring the invariant is a use-case concern; it holds by construction in this single-org migration (Task 4 normalizes every plate to the internal org; the tree uses one `owner_org_id`). No aggregate check exists to violate.
8. **user-map CSV parsing crashes with a bare `ValueError`** on a malformed row instead of naming the offending line/email. The CSV is short and operator-maintained; a stack trace is survivable. Cheap to improve if touching the file.

## Non-issues (recorded so they're not re-raised)

- **Name-based group dedup merging same-named sibling sets** was raised as a theoretical risk. It cannot occur here: legacy `APPS_PLATE_TRACKER_SET.set_name` is `UNIQUE`, so no two sets share a name. (Still worth eyeballing `groups_created` vs. the legacy set count during the dry-run.)
- **`scripts/` ruff findings** (E501 noqa, dense style) are outside CI's lint scope (`ci.yml` lints `src/` only) and were accepted deliberately.
