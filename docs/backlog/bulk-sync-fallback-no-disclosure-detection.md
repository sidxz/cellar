# Bulk registration sync fallback skips undisclosed-match detection

**Found:** 2026-09-10 (pre-merge review of `feat/daikon-asks`). **Pre-existing**, not introduced there.

`BulkRegistrationService` (`application/chemical_registration/bulk_registration_service.py`, the
synchronous path used when Temporal is unavailable) builds `RegisterMolecule` without a
`DisclosureService`, so `classify_disclosed(..., detect_undisclosed=False)`: a row whose name
matches an existing *undisclosed* molecule is a CONFLICT there, while the Temporal activity
(`infrastructure/temporal/activities/registration.py`) and `POST /molecules` — and therefore
`POST /molecules/preview-registration`, which hard-codes `detect_undisclosed=True` — classify the
same row as DISCLOSED.

**Fix direction:** inject the same `DisclosureService` into the fallback's `RegisterMolecule` (DI
already builds one for the API path) so all three doors agree with the preview.
