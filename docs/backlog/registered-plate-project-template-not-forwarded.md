# RegisterPlate use case drops project_id/template_id on the floor

**Found:** 2026-08-10, during S2 Task 3 (owner_org_id application/API wiring).

**Root cause:** `RegisterPlateCommand` (`backend/src/cellar/application/inventory/registered_plates.py`) carries `project_id` and `template_id`, and the route (`interface/routes/registered_plates.py::register_plate`) populates both from the request body. But `RegisterPlate.__call__` never forwards them into the `RegisteredPlate.register(...)` factory call — only `workspace_id`, `barcode`, `plate_label`, `format`, `plate_type`, `registered_by`, `storage_location_id`, `parent_plate_id`, `notes` are passed, even though `RegisteredPlate.register()` accepts `project_id`/`template_id` too.

**Impact:** `POST /api/v1/plates` with `project_id` or `template_id` in the body silently registers the plate with both `None`. Caller believes the plate is linked to a project/template; it isn't. No existing test (`tests/api/test_registered_plates.py`, `tests/unit/test_registered_plate.py`) asserts either field round-trips through registration, so this has gone unnoticed. (`UpdatePlate` correctly forwards `project_id`; `template_id` has no update path at all.)

**Fix direction:** add `project_id=input.project_id, template_id=input.template_id` to the `RegisteredPlate.register(...)` call in `RegisterPlate.__call__`, plus an API test asserting both round-trip. Small, isolated fix — out of scope for Task 3 (owner_org_id + `/me`), left untouched to keep that change scoped.
