# Pre-existing test failures on `kvt` (not tagging-related)

**Status:** open · **Found:** 2026-06-02 (during tagging Phases 1–3; re-confirmed during summary-results-import final verification) · **Origin:** predates the tagging work

> Re-confirmed 2026-06-05 during the run/protocol multi-target feature: the three `test_molecules.py` failures were empirically proven pre-existing by `git stash`-ing all target-feature changes and re-running — they fail identically on the clean tree. The two `MoleculeTestCounts` failures surfaced the `dose_response_curves.batch_id` NOT-NULL variant this run. None touch any target-link file. Left untouched to keep the targets branch scoped.

> Re-confirmed 2026-06-02 during the summary-results-import feature's final verification (Task 13). The full backend suite reported `6 failed, 3102 passed`: the three `test_molecules.py` failures and the three `test_backfill_bemis_murcko.py` failures below. None touch any summary-import file (verified by inspection + git history) — all unrelated to the summary-import feature. One variant observed this run: `test_tested_molecule_returns_count` / `test_project_scoped_count` surfaced a `dose_response_curves.batch_id` NOT-NULL violation rather than the `intercept_values` column error, but it is the same shared-testcontainer / model↔migration fragility family already tracked here.

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

## 3. Frontend `tsc` — stale `tags` fixture in `molecule-card.test.tsx` (pre-existing)

**Failing:** `frontend` `pnpm tsc --noEmit` → `molecule-card.test.tsx(40,3): error TS2353: Object literal may only specify known properties, and 'tags' does not exist in type 'Molecule'.`

**Empirically proven pre-existing** (2026-06-05, during the run/protocol multi-target feature): `git stash -u`-ing all target-feature changes and re-running `pnpm tsc` reproduces the identical error on the clean tree. The test file and the `Molecule` type are untouched by the target work. Note the test still **passes** under vitest (vitest transpiles without type-checking) — this is a latent type error only `tsc` surfaces.

**Root cause:** the test builds a `Molecule` object literal with a `tags: []` property, but the `Molecule` type (`features/research-organization/types`) has no `tags` field — model ↔ test-fixture drift (likely the type once had `tags`, or the fixture was copied from a tagged entity).

**Recommended fix:** either drop the stray `tags: []` from the fixture, or — if molecules are meant to surface tags — add `tags` to the `Molecule` type and its DTO. Left untouched to keep the targets branch scoped.
