# Scaffold-tree cache lookup ignores workspace

**Found:** 2026-09-15, while analysing admin force delete (`docs/superpowers/specs/2026-09-15-force-delete-id-references-design.md`).

**Root cause:** `ScaffoldTreeJobRepository.find_cached` (`backend/src/cellar/infrastructure/persistence/sqlalchemy/sar_analysis/scaffold_tree_job_repository.py:68-90`) matches on `ids_hash` and READY status only. `StartScaffoldTreeJob.execute` (`application/sar_analysis/start_scaffold_tree_job.py:68-84`) checks that cache before anything else. `POST /scaffold-tree` accepts an explicit `molecule_ids` list with no workspace check (`interface/routes/scaffold_tree.py`, the `else` branch of the `molecule_ids`/`collection_id` split). Only the `collection_id` branch is workspace-scoped. A caller who supplies another workspace's molecule ids gets that workspace's cached tree back.

**Exploitability:** it needs the other workspace's molecule UUIDs, which aren't guessable. That makes this defense in depth, not an open read. Unverified: whether the cache-miss compute path loads molecules workspace-scoped.

**Fix direction:** add `workspace_id` to `find_cached`, as the UMAP and SAR projection caches already do, and validate explicit `molecule_ids` against the caller's workspace in the route or use case.
