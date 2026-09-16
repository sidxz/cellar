# RegisterPlate / UpdatePlate / DerivePlate don't validate storage_location_id

**Found:** 2026-08-25, S8 final review (I2), while fixing the same gap on `PlateGroup`.

`backend/src/cellar/application/inventory/registered_plates.py` — `RegisterPlate` (:196), `UpdatePlate` (:331), `DerivePlate` (:488) all pass a client-supplied `storage_location_id` straight to `PlateGroup`/`RegisteredPlate.create`/`.update` without checking it exists in `auth.workspace_id`. A nonexistent id raises an unhandled `IntegrityError` at commit (500, no handler exists for it anywhere in `src/cellar`); a real id from another workspace is silently accepted.

**Fix direction (same as the `PlateGroup` fix landed alongside this note):** inject `StorageLocationRepository` into all three use cases; when `storage_location_id` is provided and not `None`/`UNSET`, `find_by_id_in_workspace` it and return `Failure(NotFoundError("StorageLocation", str(id)))` when missing. Mirrors the existing `MoveSample` pattern in `manage_sample.py`.

Not fixed in this wave — plates were explicitly out of scope for the S8 metadata fix.
