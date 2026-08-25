# Pre-existing test and lint failures on `main` (observed 2026-08-24)

Found while executing the targets-from-prot-cellar plan (branch
`feat/targets-from-prot-cellar`). None are caused by that work; each was
confirmed against the pre-branch commit `3c3d1234`. Not fixed inline — recorded
here so they get scheduled rather than re-diagnosed by every future branch.

## Backend

| Test | Symptom | Root cause | Notes |
|---|---|---|---|
| `tests/unit/application/export/renderers/test_pdf_renderer.py::test_pdf_renders_a_small_report` | `OSError: cannot load library 'libgobject-2.0-0'` | WeasyPrint needs system GObject/Pango libs that are not installed on this Mac | Environmental. Either `brew install pango` + document it in the dev setup, or skip the test when the libs are missing. |
| `tests/unit/cascade/test_fk_coverage.py::test_every_fk_is_categorized` | Fails only inside the full `tests/unit` run; passes standalone | Order-dependent: flags `rgroup_assignments` / `sar_activity_values` FKs, both SAR tables, presumably registered by an import that another test triggers first | Test-isolation bug in the cascade registry / model-import ordering, not a real categorisation gap. |
| 3 tests in `tests/api/test_molecules.py` | `UndefinedColumnError: column "visibility" of relation "projects" does not exist` | The `projects` ORM model has a `visibility` column that no Alembic migration adds (head 065 at time of writing) — autogenerate drift, same family as `docs/backlog/alembic-env-missing-inventory-model-imports.md` | Found 2026-08-25 during S7 (plate tracker revamp), confirmed pre-existing via `git stash`. Fix = one migration adding the column with the model's default; verify with `uv run alembic check` afterwards. |
| 9 tests under `tests/api` + `tests/integration` in `chemical_registration` / `inventory` | `NotFoundError: Entity not found` raised from `require_same_workspace` | Fixtures build an auth context whose `workspace_id` no longer matches the entity's (likely drift after the Duar 1.0.0 migration `0a53a7d4`) | Run `uv run pytest tests/api tests/integration -q` on `main` for the exact list. |

## Frontend

`pnpm lint` (biome) exits 1 on `main`: ~12 error-level findings in files
untouched by recent work — `src/app/login/page.tsx` (`noSvgWithoutTitle`,
`useButtonType`), `src/features/audit/hooks/use-audit.ts`
(`noNonNullAssertion`), `audit-timeline.tsx`, `activity-tab.tsx`,
`compound-search-bar.tsx`, `merge-impact-row.tsx` (`noArrayIndexKey`,
`noLabelWithoutControl`, `useKeyWithClickEvents`). Because the gate is
repo-wide, every branch's `pnpm lint` is red regardless of its own changes.

Fix options: clean the ~12 sites in one sweep (most are one-line a11y/key
fixes), or downgrade the offending rules to `warn` in `biome.json` until then.

## Repo hygiene

`ruff check --fix` / `ruff format` over `backend/src` + `backend/tests` rewrites
~170 files (import ordering, blank lines). ruff is not part of `make test`, so
the tree has drifted from its own config. Either run one formatting commit or
add ruff to the CI gate — otherwise anyone who runs the formatter repo-wide
gets a 170-file diff they must revert (happened twice on this branch).
