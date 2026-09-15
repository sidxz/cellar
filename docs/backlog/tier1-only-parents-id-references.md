# Tier-1 admin hard delete: id-only references for parents force delete doesn't cover

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`). That spec adds rules for protocols, runs, molecules and what they remove. The parents below are Tier-1 only (`DELETE /api/v1/admin/{entity_type}/{id}`), API-only except for collection, vocabulary and saved search.

**Root cause:** Tier-1 RESTRICT (`backend/src/cellar/infrastructure/cascade/inbound_refs.py:45-82`) blocks only on ForeignKeys. Once the spec's Tier-1 hook exists, a rule registered on these parents will block too, but none has rules yet.

- **plate_templates:**
  - `protocols.control_layouts` (JSON, `{format: template_id}`) should block: imports fail, and only a DRAFT protocol can fix its layouts.
  - `registered_plates.template_id` should be set null; plate detail spins on "Loading..." forever.
- **projects:**
  - `campaign.project_id` (NOT NULL, no FK) should block; the campaigns vanish from project pages.
  - `registered_plates.project_id` and `synthesis_requests.project_id` should be set null.
  - `favorites.entity_id` (projects are the only favoritable type) should cascade.
  - Today a project is always blocked anyway, by its creator's `project_members` row.
- **synthesis routes and requests:**
  - `synthesis_requests.proposed_route_id` and `.parent_request_id` should be set null.
  - A molecule force delete removes finished synthesis requests, so a child request on another molecule can keep a `parent_request_id` pointing at nothing; set null (or refuse) when a rule exists for it.
- **Config referenced by name, not id:**
  - Ontology slots: protocol annotations are keyed by slot name, so orphaned annotations are hidden but still returned by the API.
  - Custom fields: molecule and batch values are keyed by name, so updates carrying the key are rejected as "Unknown custom field". Separately, `registration_forms.field_overrides[].field_definition_id` goes dead.
  - API keys: `data_sources.api_key_name` makes imports fail with "not found or inactive".
- **Tier 1 skips the normal deletes' guards.** `AdminHardDelete` deletes the row through `application/admin/_adapter.py:23-24` and bypasses:
  - `delete_vocabulary.py:51-67`: locked vocabulary and settings references.
  - `delete_registration_form.py:46`: the default form.
  - `delete_salt_entry.py:46`: the default salt.
  - `delete_external_api_key.py:50-51`: secret cleanup.

**Fix direction:** add rules for these parents in the spec's style, and classify them in `test_fk_coverage.py`'s `LEFT_ALONE` until then. For name-keyed config, either route Tier-1 deletes of config entities through their domain delete use cases (which already hold the guards), or retire Tier 1 for those types.

Not fixed in the force-delete change; out of scope per its D5.
