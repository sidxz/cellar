# Non-admin deletes leave the same id-only references dangling

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`). The force-delete fix covers only the admin cascade tool; these user-facing delete paths have the same gap.

**Root cause:** each delete checks only what its own aggregate owns. References from other aggregates carry no FK, so nothing refuses and nothing cleans up:

- **`DeleteRun`** (`backend/src/cellar/application/screening/delete_run.py:66-80`) deletes draft or in-progress runs with their curves and readouts, and checks no campaigns. A draft run can already be a campaign seed run (`campaign.seed_runs`) or a measurement source (`campaign_measurement.source_run_id`).
- **`DeletePlateTemplate`** (`application/screening/plate_templates.py:150-182`) refuses only via `count_references` (`infrastructure/persistence/sqlalchemy/screening_assay/plate_template_repository.py:42-70`). That counts `plates.template_id` and `registered_plates.template_id`, which are never written (see `registered-plate-project-template-not-forwarded.md`). It misses `protocols.control_layouts` (`{format: template_id}`, copied into every new protocol version). After the delete, control-normalized imports fail with "no Control Layout configured", and only a DRAFT protocol can fix its layouts.
- **Draft synthesis route delete** leaves `synthesis_requests.proposed_route_id` pointing at nothing ("Unknown route").
- **Draft synthesis request delete** leaves children's `parent_request_id` dangling (a "View parent request" link to a not-found page).
- **`SynthesisRoute.remove_step`** leaves the removed step's id in other steps' `reaction_steps.preceding_step_ids`, so the route then fails validation with a 422.
- **Registered plate delete** refuses only on child plates, and leaves `plate_comments.target_id` rows unreachable and `cdd_plate_sync.plate_id` stale.

**Fix direction:** once the force-delete spec lands, its rules are the single list of "who references X". Each delete use case can ask the same question through a port backed by that registry: refuse on block rules, apply the cascade and set-null rules. The fix lives in one place instead of a guard per use case. `DeleteRun` first, since campaigns are frozen records.

Not fixed in the force-delete change; out of scope per its D5.
