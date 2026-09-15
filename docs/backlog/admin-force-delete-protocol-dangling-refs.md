# Admin force delete (cascade) leaves a protocol's non-FK references dangling

**Status:** open. Found 2026-09-15 while guarding the draft delete (`DeleteProtocol`).

The protocol page's admin **Force delete (cascade)…** goes through the generic
cascade tool (`application/admin/cascade_delete.py`). Its rules for protocols
(`infrastructure/cascade/rules_screening_assay.py`) and its blocker scan
(`infrastructure/cascade/inbound_refs.py`) only follow **foreign keys**, so
they handle runs, curves, readout/condition definitions and project links.

These references to `protocols.id` have **no FK** and are neither cascaded
nor reported, so a force delete leaves them pointing at nothing:

- `campaign_channel.protocol_id` (and its `readout_definition_id`): campaign
  grids and the stage funnel keep a channel whose protocol is gone.
- `campaign.seed_runs` JSONB `[{run_id, protocol_id}]`
- `compound_flags.protocol_id`
- `import_templates.default_protocol_id`

**Root cause:** the cascade registry is FK-introspection-driven by design, and
these columns were added without an FK (cross-context references).

**Fix options:**
- Reuse `ProtocolRepository.find_usages` (added for the draft delete) as a
  RESTRICT blocker in the protocol cascade preview, so force delete refuses too.
- Or add explicit non-FK cascade rules for these tables (channels deleted,
  seed-run entries pruned, flags deleted, template default nulled).

The draft delete path is already safe: `DeleteProtocol` refuses with a 409
naming these usages.
