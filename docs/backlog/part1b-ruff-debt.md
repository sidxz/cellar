# Part 1b ruff debt (pre-existing on `design-7`, blocks CI's `src/` lint gate)

**Created:** 2026-06-15
**Context:** Surfaced while finishing the SAR Part 2 (activity projection + heatmap)
slice on branch `design-7`. CI (`.github/workflows/ci.yml`) runs `uv run ruff check
src/` + `uv run ruff format --check src/`. All **Part 2** `src/` files were brought
to pass both gates. These two **Part 1b** (decomposition) files still fail them —
they were committed earlier on this branch (commits `1cf1a3c1`, `d708f56d`) without
a ruff pass, predate the Part 2 session, and are unrelated to Part 2. Left untouched
to keep the Part 2 work scoped; recorded here so the branch's lint gate can be made
green in a single focused cleanup.

> Note: the Part 2 handoff stated "Part 1a+1b are on main", but `git branch --contains
> 1cf1a3c1` shows these commits are on `design-7` only — Part 1a/1b have **not** been
> merged to `main`. So this debt is design-7-local, not inherited from `main`.

## Failing items (`cd backend`)

`ruff check src/`:
- `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py:109` — **B905** `zip()`
  without an explicit `strict=` parameter.
- `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py:112` — **E501** line too
  long (101 > 99).

`ruff format --check src/` would reformat:
- `src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py`
- `src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py`

## Root cause

Part 1b landed these files without `ruff check`/`ruff format` being run on them (the
project's pre-commit does not enforce ruff; only CI does, and Part 1b's branch CI was
evidently not gating on it — or was red). Same class of debt the
`frontend-biome-burndown` backlog tracks for the FE.

## Fix (one focused commit, ~2 min)

```bash
cd backend
# B905: add strict= to the zip() at streaming_rgroup_decomposer.py:109 (choose
#   strict=True/False per the call's intent — verify the two iterables are
#   meant to be equal length before picking True).
# E501: wrap the long line at :112.
uv run ruff check --fix src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py
uv run ruff format src/cellar/infrastructure/rdkit/streaming_rgroup_decomposer.py \
                   src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/rgroup_decomposition_run_repository.py
uv run ruff check src/ && uv run ruff format --check src/   # expect clean
```

The B905 `strict=` choice is the only non-mechanical decision — inspect the `zip()` at
`streaming_rgroup_decomposer.py:109` to confirm whether the paired iterables are
guaranteed equal-length (`strict=True`) or intentionally truncating (`strict=False`).
