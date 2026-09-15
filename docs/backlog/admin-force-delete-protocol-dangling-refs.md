# Handoff: admin force delete leaves references without an FK dangling

**Status:** implemented on `feat/force-delete-id-references` (2026-09-15). Design:
`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`; plan:
`docs/superpowers/plans/2026-09-15-force-delete-id-references.md`. The handoff below is kept for context.

## Context

- **Force delete:** the admin **Force delete (cascade)…** action on protocol, run and molecule pages
  (`TIER2_ENTITY_TYPES`). It goes through the generic cascade tool:
  - **Application:** `backend/src/cellar/application/admin/`, covering `cascade_preview.py`,
    `cascade_delete.py`, `admin_hard_delete.py`, `admin_delete_registry.py`, `tier2_entities.py` and
    `cascade_service.py`.
  - **Infrastructure:** `backend/src/cellar/infrastructure/cascade/`, covering
    `rules_<context>.py` (one per bounded context), `registry.py`, `cascade_runner.py`, `inbound_refs.py`
    (the FK-introspection blocker scan) and `label_fields.py`.
  - **Routes:** `backend/src/cellar/interface/routes/admin_delete.py`.
  - **Tests:** `backend/tests/integration/cascade/`.
- **Rules follow FKs only, by design.** A `CascadeRule` is (child_table, fk_column, parent_table,
  action), with action one of cascade, set_null, block or warn. The rule files record that columns
  without an FK were deliberately left out. For example, `rules_chemical_registration.py` notes that
  `compound_flags.molecule_id` and `bulk_registration_items.molecule_id` are plain UUIDs with no FK
  constraint, so their rules were removed.
- **Result:** force-deleting an entity leaves every reference without an FK pointing at nothing.

## What is verified (for protocols only)

These references to `protocols.id` have no FK. I checked them against the live DB with `pg_constraint`
and `information_schema`:

- `campaign_channel.protocol_id` (also `readout_definition_id`)
- `campaign.seed_runs` JSONB `[{run_id, protocol_id}]`
- `campaign.source_protocols` JSONB (a snapshot written when a campaign closes)
- `compound_flags.protocol_id`
- `import_templates.default_protocol_id`

`ProtocolRepository.find_usages`
(`infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py`, PR #91) already names
the blocking ones for the draft delete. It may be reusable.

## Not yet verified: this is the analysis to do

- The same gap for **runs** and **molecules**, and any other entity the cascade tool can delete. Likely
  suspects:
  - campaign `seed_runs` run ids
  - campaign results and measurements (`source_run_id`, `source_curve_id`, `source_readout_id`,
    `molecule_id`)
  - compound flags
  - bulk-registration items
  - collection members
  - SAR caches
  - saved-search JSON
- Whether the runner can act on a column that has no FK, or whether `registry.py` or the tests assume
  every rule is a real FK.
- For each reference, what a chemist and the audit trail need: block, cascade or set null.
  - **Campaigns:** closed or published campaigns are frozen results (21 CFR Part 11 alignment, and the
    audit trail is append-only). Daikon reads published campaigns live.
  - **JSONB references** (`seed_runs`, `source_protocols`, saved searches) can't be expressed as a
    column rule.

## Related

- **Draft delete:** `DeleteProtocol` (`application/screening/manage_protocol.py`, PR #91) is already
  safe. It returns 409 and names the usages.
- **Race:** a deliberate, marked shortcut in the draft delete (`ponytail:` comment, no row lock). It is
  out of scope here.

## Working notes for the session

- **Testing:**
  - Tests using testcontainers need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`.
  - The local dev stack runs on `:8000`/`:3000` (the backend reloads on file changes).
  - The dev DB container is `chem-vault2-postgres-1`.
- **Git:**
  - Commit with explicit pathspecs. The working tree has unrelated user changes
    (`frontend/next-env.d.ts`, `frontend/AGENTS.md`).
  - Committer identity is panda-sas.
  - Keep `Co-Authored-By`, and never add a `Claude-Session` trailer.
- **Daikon:** daikon consumes cellar's API live. Tell the daikon session (`daikon-gen3`) before merging
  anything that changes a response shape.
