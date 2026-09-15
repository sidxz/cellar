# SQLAlchemy models and the database disagree on three FKs

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`), by diffing `pg_constraint` in the dev DB (migration 080) against `Base.metadata`.

**Root cause:**
- **Declared in models, never created:**
  - `batches.molecule_id` → `molecules` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py:36`).
  - `disclosure_requests.resolved_to_molecule_id` → `molecules` (`chemical_registration/disclosure_models.py:54`).
  - Migration 001 creates both columns without constraints (`alembic/versions/001_001_initial_schema.py:377,645`), and no later migration adds them.
  - The admin tools read model metadata, so they treat both as real FKs, but the database enforces nothing. Dev has no orphans (61,340 batches).
- **Created, never declared:**
  - `collections.derived_from_campaign_id` → `campaign`, ON DELETE SET NULL (`alembic/versions/027_screen_campaign.py:267-274`), is not on `CollectionModel` (`research_organization/models.py:117-119`).
  - Tier-1 introspection can't see it. That's moot while campaigns can't be deleted, and see `collection-freeze-unused.md`.

**Fix direction:** one migration adding the two constraints `NOT VALID`, then `VALIDATE CONSTRAINT` after an orphan check on each deployment. Declare the third FK on the model, or drop it together with the unused freeze columns.
