# cdd_plate_sync.cdd_statistics exists in DB but not in ORM

**Found:** 2026-08-10, during plate-tracker gap analysis.

**Root cause:** migration 013 creates a `cdd_statistics JSONB` column on `cdd_plate_sync`, but `CddPlateSyncModel` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/cdd_plate_import_models.py`) declares no such attribute. The column is dead: never written, never read.

**Impact:** harmless at runtime, but schema/ORM drift — anyone diffing model vs DB (or autogenerating a migration) will trip on it, and the per-plate QC stats the import could have captured are being thrown away.

**Fix direction:** either map the column and populate it during plate import (the external vault export does include plate QC stats), or drop the column in a follow-up migration. Decide when the plate import is next touched.
