# `alembic/env.py` metadata-import block was incomplete → autogenerate proposed dropping real tables

**Found:** 2026-08-13 (S5 Task 6, KioskDevice). **Resolved (table-drop class):** 2026-08-14, S6-first.

## Root cause

`backend/alembic/env.py` explicitly imports every SA model module so `Base.metadata`
(the `--autogenerate` target) includes their tables. The block was missing modules that
own real, migrated tables. Any missing module → its live table has no match in
`target_metadata` → autogenerate proposes `DROP TABLE` for it. Accepted without review =
real data loss.

The original report named 2 inventory tables. The real defect was broader: the import
block was simply incomplete. Running autogenerate at head surfaced **five** missing
modules (eight tables), not two:

- `inventory.plate_loan_models` — `plate_loans`, `plate_loan_items` (migration 063)
- `inventory.cdd_plate_import_models` — `cdd_plate_imports`
- `export.export_job_model` — `export_jobs`
- `personalization.models` — `favorites`
- `sar_analysis.sar_activity_projection_models` — `sar_activity_projections`, `sar_activity_values`

## Fix applied

Added all five `import … # noqa: F401` lines to `alembic/env.py`. Verified against a DB at
head (064): `alembic revision --autogenerate` now emits **zero `op.drop_table`**.

## Residual: autogenerate is still NOT clean (pre-existing, separate issue)

Even with every table modeled, autogenerate at 064 still emits drift it **cannot** produce
from ORM metadata, because SQLAlchemy can't model raw-SQL DDL. Snapshot (2026-08-14):

| op | n | what |
|----|---|------|
| `drop_index` | 40 | raw-SQL indexes: pg_trgm, RDKit bfp, partial-unique (`uq_loan_items_active_plate`, `uq_plate_groups_ws_org_parent_name`, `uq_readout_data_wellless`), async-job cache indexes |
| `create_index` | 40 | `ix_<table>_workspace_id` — `WorkspaceIdMixin` declares a single-col index the migrations instead cover with composites (the `ix_kiosk_devices_ws_org` precedent, migration 064) |
| `alter_column` | 28 | mostly `created_at`/`updated_at` NOT-NULL (`TimestampMixin` server_default vs. DB) |
| `drop_column` | 4 | `molecules.morgan_bfp`/`fcfp_bfp` (RDKit bfp type), `cdd_plate_sync.cdd_statistics` (see `cdd-plate-sync-orm-column-drift.md`) |
| `create_foreign_key` | 3 | model-declared FKs the DB column lacks a constraint for |

None are table drops, but `drop_index`/`drop_column` would still destroy real objects.

**Rule for every migration author (incl. S6): never blindly apply autogenerate output —
hand-write migrations, or diff and prune.** Autogenerate is a hint, not a source of truth,
while this drift stands.

**Upgrade path (not scheduled):** add an `include_object` / `include_name` hook to
`env.py` that excludes objects SQLAlchemy can't own (functional/partial/GIN indexes, bfp
columns), and reconcile the `WorkspaceIdMixin` single-col-vs-composite and `TimestampMixin`
nullability drift with real migrations. That makes autogenerate trustworthy again. Larger
task, its own session.

## Note on `test_fk_coverage.py`

Its model-import block has the **same** three gaps (`export`, `personalization`,
`sar_activity_projection`), so those tables' FK cascades go unchecked by that test — a
latent, separate coverage gap, not addressed here.
