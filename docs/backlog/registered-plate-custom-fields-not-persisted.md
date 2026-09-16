# RegisteredPlate.custom_fields silently dropped on save

**Found:** 2026-08-10, during plate-tracker gap analysis (exploration of inventory persistence).

**Root cause:** the domain aggregate `RegisteredPlate` accepts `custom_fields: dict | None` (`backend/src/cellar/domain/inventory/registered_plate.py`), but `RegisteredPlateModel` has no corresponding column and the repository mapper (`registered_plate_repository.py`) never reads/writes it. Saved plates lose `custom_fields`; loads always return `None`.

**Impact:** any caller setting `custom_fields` (e.g. import paths) believes it persisted; data is silently discarded. Note batches DO persist `custom_fields` (external-vault batch ids are resolved via `BatchModel.custom_fields->>'cdd_batch_id'`), so the plate-side gap is an inconsistency, not a pattern.

**Fix direction:** either add a JSONB `custom_fields` column + mapper lines + migration, or remove the field from the aggregate if genuinely unused. Decide when touching RegisteredPlate next (org-ownership work will).
