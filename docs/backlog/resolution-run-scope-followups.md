# Resolution run scope (batch 3) — parked follow-ups

**Branch:** `feat/resolution-run-scope` (spec `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §5, D4 as revised; issue #76).
**Source:** whole-branch review 2026-09-11, fix-wave notes, and the consumer session's follow-up.

- **`seed_runs` only grows.** The natural inverse of add-from-runs for a chemist who added the wrong run is `DELETE /campaigns/{id}/seed-runs/{run_id}`: drop the run from scope, leave rows and cells untouched, and let the next refresh re-resolve without it. Suggested by the consumer session; not blocking.
- **Unknown run ids on add-from-runs are silently skipped** (pre-existing behaviour, now also when recording seed runs). A `NotFoundError` would be more honest.
- **Aggregate selection rules leave `contributing_run_ids` empty on refresh** (`ChannelResolver`, pre-existing). The seed-runs scope does not depend on it, but the audit trail for a mean cell is thinner than for a picked cell.
- **`seed_runs` is a required key in the published document** — additive for the consumer, but a schema-strict client must accept it.
- **Rows added by hand or from a collection into a run-seeded campaign are restricted to the seeded runs of each protocol** (D4). A compound with data only in a non-seeded run of a seeded protocol reads ND until that run is added or the readout opts out.
