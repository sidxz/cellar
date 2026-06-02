# Pre-existing test failures on `kvt` (not tagging-related)

**Status:** open · **Found:** 2026-06-02 (during tagging Phases 1–3) · **Origin:** predates the tagging work

These failures were **empirically proven pre-existing** — they already fail in the full suite at commit `5554e342` (the `kvt` HEAD before any tagging work began). They are unrelated to the tagging feature and were deliberately left untouched so the tagging branch stays scoped. Recording them here so they're tracked.

## 1. `tests/integration/test_backfill_bemis_murcko.py` — global NULL-count fragility

**Failing:** `test_backfill_populates_null_rows`, `test_backfill_idempotent` (`assert N == 1`, N grows with the number of other molecule-inserting tests in the session).

**Root cause:** `scripts/backfill_bemis_murcko.py::backfill_batch` selects `MoleculeModel.bemis_murcko_smiles.is_(None)` **globally** — the `workspace_id` filter is only applied when a `workspace_id` arg is passed, and these tests call `backfill_batch(session, batch_size=10)` with **no** workspace, then assert a global `processed` count. Because the integration suite shares one session-scoped testcontainer and many tests COMMIT molecules with NULL `bemis_murcko_smiles` (registration, repository, campaign, and the tagging suites), the global count is contaminated → the assertion fails. Passes in isolation; fails in the full suite.

**Recommended fix (clean, root-cause):** scope the test to its own workspace — call `backfill_batch(uow.session, batch_size=10, workspace_id=ws_id)` and assert on counts within `ws_id`. This fixes the contamination for **all** contaminators at once (cleaning up individual tests' rows would not, since many suites contribute).

## 2. `tests/api/test_molecules.py` — three failures (schema drift / config)

All three predate tagging and reference fields/columns the tagging work never touched.

- **`test_register_disclosed_molecule`** — expects registration prefix `CV-` but gets `CC-`. Likely a workspace registration-number-prefix config/branding default mismatch (the test or the default needs aligning).
- **`test_tested_molecule_returns_count`** — `asyncpg.exceptions.UndefinedColumnError: column "intercept_values" of relation "dose_response_curves" does not exist`. The ORM/query references `dose_response_curves.intercept_values` but no migration creates it → **model ↔ migration drift**.
- **`test_project_scoped_count`** — `UndefinedColumnError: column "visibility" of relation "projects" does not exist`. A query references `projects.visibility` but no migration creates it → **model ↔ migration drift**.

**Recommended fix:** reconcile the ORM models with the Alembic migrations — either add the missing migrations (`dose_response_curves.intercept_values`, `projects.visibility`) or remove the stale column references; align the registration-prefix expectation with the configured default. Investigate the intended schema before choosing (these likely stem from incomplete earlier branch work).
