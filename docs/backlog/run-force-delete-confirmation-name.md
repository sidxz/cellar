# Run force delete asks for a confirmation name many runs don't have

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`).

**Root cause:** the typed confirmation name for Tier-2 deletes is the table's label column. For runs that is `notes`, which is nullable free text (`backend/src/cellar/infrastructure/cascade/label_fields.py:13`). `CascadeDelete` fetches it (`infrastructure/cascade/cascade_service_impl.py:82-99`) and compares it with the typed name (`application/admin/cascade_delete.py:64-73`). The run page passes `entityLabel={query.data.notes ?? runId}` (`frontend/src/features/screening-assay/components/run-detail.tsx:665`).
- **NULL notes:** the dialog asks the admin to type the run's UUID, then the backend returns 404 because the label is missing. (Dev: 4 of 24 runs.)
- **Empty notes:** `"" ?? runId` stays `""`, and `typed_name` needs at least one character, so it can never match. (Dev: 7 of 24.)
- **Long notes** must be typed verbatim.

**Fix direction:** give runs a confirmation name a person can read and type, computed once server-side for both the dialog label and the check. The UI already titles runs `Run <run_date>` (`run-detail.tsx:198`); protocol name plus run date would be distinct enough. Never a UUID.
