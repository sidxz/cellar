# tests/api/test_molecules.py — 3 tests rotted against schema/prefix changes

**Found:** 2026-08-26, while verifying the Duar 1.3.0 / dependency upgrade (the API suite is not in CI, so nothing caught it).

**Failing:**
- `TestRegisterMolecule::test_register_disclosed_molecule` — asserts `registration_number.startswith("CV-")`; the default prefix is now `CC-` (`workspace_settings.py: _DEFAULT_PREFIX`).
- `TestMoleculeTestCounts::test_tested_molecule_returns_count` — `_seed_protocol_run_curve` inserts a `dose_response_curves` row without `batch_id`, which is now NOT NULL.
- `TestMoleculeTestCounts::test_project_scoped_count` — raw `INSERT INTO projects (…, visibility)`; the `visibility` column no longer exists.

**Root cause:** the test seeds rows with hand-written SQL instead of the domain factories/repositories, so every schema change silently breaks it. Unrelated to dependencies — fails identically on the pre-upgrade lockfile.

**Fix direction:** update the prefix expectation to `CC-`, seed the curve through a real batch (or the `BulkCreateReadoutData` path), and drop `visibility` from the project insert. Better: replace the raw SQL seeding with the existing fixtures used elsewhere in `tests/api/`. Consider adding `tests/api/` to CI once green — it is the only suite exercising FastAPI/Starlette/Pydantic together.
