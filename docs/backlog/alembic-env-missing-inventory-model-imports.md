# `alembic/env.py` metadata-import block is missing two inventory model modules

**Found:** 2026-08-13, during S5 Task 6 (KioskDevice persistence — migration 064).

**Root cause:** `backend/alembic/env.py` has an explicit "Import all SA models so Base.metadata includes their tables" block used as the target metadata for `alembic revision --autogenerate`. Two inventory model modules that own real, migrated tables are missing from it:

- `cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_models` (`PlateLoanModel`, `LoanItemModel` — migration 063)
- `cellar.infrastructure.persistence.sqlalchemy.inventory.cdd_plate_import_models` (migration referenced by `cdd_plate_import_repository.py`)

Both modules *are* correctly registered in `backend/tests/unit/cascade/test_fk_coverage.py`'s equivalent import block (which is how the gap was noticed while adding the same pattern for `kiosk_device_models` in Task 6) — so `Base.metadata` is fully populated for that test, but not for Alembic's own autogenerate target.

**Impact:** harmless today (nobody has run `alembic revision --autogenerate` since 063 landed), but live: the next autogenerate run will see `plate_loans`, `plate_loan_items`, and the cdd-plate-import table in the live DB with no matching SQLAlchemy table in `target_metadata`, and will propose `DROP TABLE` migrations for all three. If accepted without review, that's real data loss.

**Fix direction:** add the two missing `import cellar.infrastructure.persistence.sqlalchemy.inventory.plate_loan_models  # noqa: F401` / `...cdd_plate_import_models  # noqa: F401` lines to `alembic/env.py`'s inventory block, then run `alembic revision --autogenerate -m check` once against a DB at head and confirm the generated diff is empty (or only contains the known `WorkspaceIdMixin` index-declaration drift already present for other tables — see `ix_kiosk_devices_ws_org` composite-covers-workspace_id precedent set in migration 064). Task 6 deliberately did **not** fix this inline (out of scope, unrelated to the kiosk work) but did register `kiosk_device_models` correctly in both `alembic/env.py` and `test_fk_coverage.py` so the new table doesn't repeat the gap.
