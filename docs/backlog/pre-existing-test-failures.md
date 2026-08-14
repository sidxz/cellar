# Pre-existing test failures on `kvt` (not tagging-related)

**Status:** open · **Found:** 2026-06-02 (during tagging Phases 1–3; re-confirmed during summary-results-import final verification) · **Origin:** predates the tagging work

> Re-confirmed 2026-06-05 during the run/protocol multi-target feature: the three `test_molecules.py` failures were empirically proven pre-existing by `git stash`-ing all target-feature changes and re-running — they fail identically on the clean tree. The two `MoleculeTestCounts` failures surfaced the `dose_response_curves.batch_id` NOT-NULL variant this run. None touch any target-link file. Left untouched to keep the targets branch scoped.

> Re-confirmed 2026-06-06 during the backend architecture-audit guard sweep (`fix/backend-arch-audit`): the three `test_molecules.py` failures fail identically with all sweep changes `git stash`-ed (re-proven on the clean tree). Variants this run: `CC-000001` vs `CV-` prefix; `dose_response_curves.batch_id` NOT-NULL on `test_tested_molecule_returns_count`; `projects.visibility` UndefinedColumn on `test_project_scoped_count`. Same model↔migration-drift family already tracked below. Left untouched to keep the audit branch scoped.

> Re-confirmed 2026-06-02 during the summary-results-import feature's final verification (Task 13). The full backend suite reported `6 failed, 3102 passed`: the three `test_molecules.py` failures and the three `test_backfill_bemis_murcko.py` failures below. None touch any summary-import file (verified by inspection + git history) — all unrelated to the summary-import feature. One variant observed this run: `test_tested_molecule_returns_count` / `test_project_scoped_count` surfaced a `dose_response_curves.batch_id` NOT-NULL violation rather than the `intercept_values` column error, but it is the same shared-testcontainer / model↔migration fragility family already tracked here.

> Re-confirmed 2026-06-17 during the logging-standardization work (`design-7`): full `tests/api` run reported `3 failed, 333 passed` — the same three `test_molecules.py` failures in section 2 (`test_register_disclosed_molecule` CV-/CC- prefix; `test_tested_molecule_returns_count` and `test_project_scoped_count` surfacing `projects.visibility` UndefinedColumn / `dose_response_curves` drift). The logging work touches no models, migrations, or SQL — unrelated.

> Re-confirmed 2026-08-10 during Task 7 (`GET /api/v1/orgs` Sentinel org-directory route + wiring): full `tests/api` run reported `3 failed, 345 passed` — the identical three `test_molecules.py` failures in section 2, same variants (`test_register_disclosed_molecule` → `'CC-000001'.startswith('CV-')` is `False`; `test_tested_molecule_returns_count` → `dose_response_curves.batch_id` NOT-NULL violation; `test_project_scoped_count` → `projects.visibility` UndefinedColumnError). Confirmed via `git blame` that the raw-SQL seed helpers/assertions in `tests/api/test_molecules.py` predate this task (introduced 2026-05-17, commit `7837b3a4`). Task 7 touches only `interface/dependencies/_core.py`, a new `interface/routes/org_directory.py`, `interface/app.py`, and `tests/api/conftest.py` router/dependency wiring — no models, migrations, or molecule/project/DRC SQL — unrelated.

> Re-confirmed 2026-08-13 during S5 Task 7 (kiosk-device admin API — `application/inventory/kiosk_devices.py`, `interface/routes/kiosk_devices.py`, DI/deps wiring, `tests/api/test_kiosk_devices.py`): full `tests/api` run reported `3 failed, 439 passed` — the identical three `test_molecules.py` failures in section 2, same test identifiers. Captured verbatim this run: `test_project_scoped_count` → `sqlalchemy.exc.ProgrammingError` wrapping `asyncpg.exceptions.UndefinedColumnError: column "visibility" of relation "projects" does not exist` (`INSERT INTO projects (id, workspace_id, name, version, created_by, visibility) ... ON CONFLICT DO NOTHING`) — the same `projects.visibility` model↔migration drift as every prior run. `test_register_disclosed_molecule` and `test_tested_molecule_returns_count` failed with the same identifiers as every prior re-confirmation (tail-truncated before their tracebacks this run; names and pass/fail counts match exactly — 439 vs the prior run's 345 reflects only the growing suite size). S5 Task 7 touches only kiosk-device application/routes/DI/dependency-wiring files, `tests/api/test_kiosk_devices.py`, and the router-registration lines in `interface/app.py` / `tests/api/conftest.py` — no models, migrations, or molecule/project/DRC code — unrelated.

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

**Empirically proven pre-existing** (2026-06-05, during the run/protocol multi-target feature): `git stash -u`-ing all target-feature changes and re-running `pnpm tsc` reproduces the identical error on the clean tree. The test file and the `Molecule` type are untouched by the target work. Note the test still **passes** under vitest (vitest transpiles without type-checking) — this is a latent type error only `tsc` surfaces. Re-confirmed 2026-06-05 during the Collection `type` feature's final verification (sole `tsc` error; none of the collection-type commits touch this file or the `Molecule` type).

**Root cause (confirmed):** commit `8f094c5e` ("refactor(tagging): regen orval, alias tag types to generated, drop legacy string-tag cruft", on the kvt tagging branch) removed the legacy `tags` field from the `Molecule` type in `features/chemical-registration/types/index.ts`, but the `molecule-card.test.tsx` fixture's `tags: []` line was not removed in the same change — model ↔ test-fixture drift.

**Recommended fix:** either drop the stray `tags: []` from the fixture, or — if molecules are meant to surface tags — add `tags` to the `Molecule` type and its DTO. Left untouched to keep the targets branch scoped.

## 4. Batch-identifier mirror tests — workspace-guard / `editor_auth` fixture mismatch

**Status:** open · **Found:** 2026-06-15 (during the CDD-import batch-identifier-mirror fix on `design-7`) · **Origin:** predates this work

**Failing (6):**
- `tests/integration/inventory/test_create_batch_fans_out_mirrors.py::test_create_batch_fans_out_mirrors_from_existing_synonyms`
- `tests/integration/inventory/test_mirror_cascade_delete.py::TestMirrorCascadeDelete::test_remove_identifier_cascades_to_mirrors`
- `tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py::TestAddIdentifierFansOutMirrors::test_add_identifier_creates_one_mirror_per_existing_batch`
- `tests/integration/chemical_registration/test_add_identifier_fans_out_mirrors.py::TestAddIdentifierFansOutMirrors::test_add_identifier_no_batches_returns_zero_mirrors`
- `tests/integration/application/chemical_registration/test_register_molecule_scaffold.py::test_register_molecule_persists_scaffold` *(added to this list 2026-08-10)*
- `tests/integration/application/chemical_registration/test_register_molecule_scaffold.py::test_register_acyclic_records_empty_scaffold` *(added to this list 2026-08-10)*

All fail with `cellar.domain.shared.errors.NotFoundError: Entity not found` raised from `application/auth.py::require_same_workspace`, *before* any mirror logic runs.

**Empirically proven pre-existing** (2026-06-15): `git stash`-ing the CDD-import mirror fix (`infrastructure/temporal/activities/registration.py`) reproduces all four identically on the clean tree, and they also fail when run in isolation (so this is a deterministic guard/fixture mismatch, not shared-testcontainer contamination). None of these tests import the activity that was changed.

**Root cause (confirmed):** commit `bae2a3e1` ("fix(security): enforce workspace tenant guard in every application use case") added `require_same_workspace(auth, input.workspace_id)` to `CreateBatch.__call__` and `AddIdentifier.__call__`. These mirror tests (added earlier in `86c37a74`) pass `auth=editor_auth`, where the `editor_auth` fixture is `FakeAuth(role="editor")` — and `FakeAuth.__init__` defaults `workspace_id` to a **fresh random uuid** (`workspace_id or uuid.uuid4()`) that never matches the `seeded_workspace_and_molecule` workspace. The guard sweep did not update these co-located tests → guard ↔ test-fixture drift. (The new CDD-import mirror tests are unaffected: the Temporal activity calls `CreateBatch` with `auth=None`, the system/worker bypass path.)

**Recommended fix (clean, root-cause):** give the test auth the seeded workspace — e.g. `FakeAuth(role="editor", workspace_id=workspace_id)` in each affected test, or an `editor_auth` fixture derived from `seeded_workspace_and_molecule`. Both the tenant guard and the mirror logic are correct; only the fixtures need to share a workspace id. Left untouched to keep this branch scoped.

> Expanded 2026-08-10 during the S1 org-identity wrap-up verification: full backend suite reported `10 failed, 3612 passed` — 8 failures already documented here (§2 ×3, §4 ×4, §5 ×1) plus two previously-undocumented failures in `tests/integration/application/chemical_registration/test_register_molecule_scaffold.py` (`test_register_molecule_persists_scaffold`, `test_register_acyclic_records_empty_scaffold`), now added to the list above (4 → 6). Empirically proven pre-existing via a fresh `git worktree` checkout of pre-S1 base commit `c111aad1`: both fail identically there (`2 failed`). Same failure mode as this section per inspection — workspace-guard `NotFoundError` from a `FakeAuth` whose random `workspace_id` never matches the seeded workspace; the scaffold tests predate the `bae2a3e1` guard sweep. The S1 work touches no chemical-registration or scaffold code (SDK pin, `AuthContext` protocol, additive `FakeAuth` org params, `OrgDirectory`, org route, FE hook) — unrelated.

## 5. `tests/unit/cascade/test_fk_coverage.py::test_every_fk_is_categorized` — SAR job FKs uncategorized

**Status:** open · **Found:** 2026-06-16 (during the R-group decomposition AsyncJob migration on `design-7`) · **Origin:** predates this work

**Failing (1):** `test_every_fk_is_categorized` reports two uncategorized inbound FKs:
- `rgroup_assignments.run_id -> rgroup_decomposition_runs`
- `sar_activity_values.projection_id -> sar_activity_projections`

**Empirically proven pre-existing** (2026-06-16): `git -C <root> stash push -- backend/src backend/tests` (verified the aggregate reverted to its `@dataclass(frozen=True)` baseline) and re-running the full `tests/unit` suite reproduces the identical failure on the clean tree (`1 failed, 2857 passed`). The migration touches neither FK definition (both live in unchanged model files) and does not touch the activity-projection job at all. The failure only surfaces in the full suite (import order populates `Base.metadata` with the SAR job tables); `test_fk_coverage.py` passes in isolation.

> Re-confirmed 2026-06-17 during the logging-standardization work (`design-7`): the full `tests/unit` suite run with **all** new logging test files excluded (`--ignore` the logging + middleware dirs, `--deselect` the get_auth test) still reproduces the identical failure (`1 failed, 2872 passed`). The logging work touches no model/FK/cascade code, confirming this is independent of it.

> Re-confirmed 2026-08-10 during the sentinel-auth-sdk 0.20.0 bump (org identity on `AuthContext`/`FakeAuth`, Task 5 of the org-identity plan): `git stash push -- backend/pyproject.toml backend/uv.lock backend/src/cellar/application/auth.py backend/tests/fakes/fake_auth.py` reproduces the identical failure on the clean tree in the full `tests/unit` suite (`1 failed, 2920 passed`, plus the new org-context test file failing as expected since it targets the not-yet-stashed-back code). The task touches only the SDK pin, the `AuthContext` protocol, and `FakeAuth` — no model/FK/cascade code — confirming this is independent of it.

> Re-confirmed 2026-08-13 during S5 Task 6 (KioskDevice persistence — migration 064, ORM, repository): `git stash push -u -- backend/src backend/alembic backend/tests` reproduces the identical two-FK failure on the clean tree when running the full `tests/unit` suite with only `-k fk_coverage` selected (collection still imports every other unit module, populating `Base.metadata`); passes in isolation either way. `KioskDeviceModel` declares no `ForeignKey` columns at all (`org_id`/`created_by` are plain `Uuid`), so it cannot contribute to `_collect_all_fks()` — confirming this run is independent of the kiosk work.

**Root cause:** the cascade system has no `rules_sar_analysis` module (the test's `_CASCADE_MODULES` registers only audit / chemical_registration / inventory / research_organization / screening_assay), and the two SAR job parent tables (`rgroup_decomposition_runs`, `sar_activity_projections`) are neither Tier-1-deletable nor listed in `IGNORED_FKS`. When the SAR compute-job features were added, their child-row FKs were never categorized.

**Recommended fix:** decide the cascade policy for SAR compute-job child rows (they are recomputable results keyed to a job; the schema already carries `ON DELETE CASCADE`). Either add a `rules_sar_analysis` Tier-2 cascade module (covering rgroup + projection, and the scaffold/umap analogues), or add the child FKs to `IGNORED_FKS` with a justifying comment. Left untouched to keep the AsyncJob-migration branch scoped.

## 6. `ruff check src/` — two pre-existing lint errors in `streaming_rgroup_decomposer.py`

**Status:** open · **Found:** 2026-06-16 (during the R-group decomposition AsyncJob migration on `design-7`) · **Origin:** predates this work

**Failing:** CI's `ruff check src/` (`.github/workflows/ci.yml`) reports two errors in `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`:
- `:109` **B905** `zip()` without an explicit `strict=` parameter
- `:112` **E501** line too long (101 > 99)

**Pre-existing:** the file is unmodified by the migration (`git diff HEAD -- …streaming_rgroup_decomposer.py` is empty); the migration's own touched modules are ruff-clean. These errors are on the committed `design-7` HEAD.

**Recommended fix:** add `strict=...` to the `zip()` at line 109 and wrap the long line at 112 — trivial. Left untouched to keep the migration branch scoped (CI's ruff gate was already red on this file independent of this work).
