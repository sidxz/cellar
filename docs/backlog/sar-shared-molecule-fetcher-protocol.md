# Backlog: extract shared molecule-SMILES fetcher port (SAR)

- **Area:** SAR analysis — backend, application layer
- **Priority:** Low (benign; no correctness impact)
- **Raised:** 2026-06-09, code review of the SAR workbench backend R-group decomposition (Task 3).

## Issue

`DecomposeRGroups` (`backend/src/cellar/application/sar_analysis/decompose_rgroups.py`) imports the
`MoleculeFetcherForScaffoldTree` Protocol from
`backend/src/cellar/application/sar_analysis/build_scaffold_network.py` — a lateral
use-case → use-case import. That Protocol is named/located for the scaffold-tree feature but is now
shared by two use cases (scaffold-network build + R-group decomposition).

## Root cause

The `(id, smiles, bemis_murcko_smiles)` fetch port was introduced feature-specifically for the
scaffold tree. Reusing it for R-group decomposition (sanctioned by the plan) revealed it is really a
*shared* application port that should live in a shared module rather than inside a sibling use-case
file.

## Suggested fix (~3 files, mechanical)

Move the Protocol to a shared location — e.g. `application/sar_analysis/repositories.py` (alongside
`ScaffoldTreeJobRepository`) — and optionally rename to a neutral `MoleculeSmilesFetcher`. Update the
two importers (`build_scaffold_network.py`, `decompose_rgroups.py`). DI already injects the same
concrete `SQLAlchemyMoleculeRepository` for both, so no DI/wiring change is needed.

## Why deferred

Benign: both use cases legitimately need the identical lean fetch, and there is no behavioral
coupling. Refactoring a pre-existing, tested file (`build_scaffold_network.py`) was out of scope for
the R-group decomposition task; the lateral import currently exists in exactly one file
(`decompose_rgroups.py`).
