# SAR Unit C · Item 2 — Perf (evidence-first) — design

**Created:** 2026-06-16 · **Branch:** `design-7` · **Slice of:** `docs/superpowers/specs/2026-06-15-sar-unit-c-handoff.md` (item 2).
**Related:** `docs/backlog/molecule-resolver-uuid-batch.md` (the N+1 this slice fixes).

## Problem
The handoff's item 2 proposed indexes on the `/rows` scoped-join and activity-join.
Exploration shows both are **already covered by composite PKs**: `rgroup_assignments`
PK `(run_id, molecule_id)` and `sar_activity_values` PK `(projection_id, molecule_id)`
(and `molecules.id` PK for the molecule join). So the real perf gap is the **N+1 in
`MoleculeResolver`** that the SAR save-all path is the first to stress at full-library
scale (final review of item 1 confirmed: one `find_by_id_in_workspace` per ref).

## Decisions (approved 2026-06-16)
- **Evidence-first.** Deliverables: (A) the resolver UUID-batch fix; (B) an EXPLAIN
  verification of the `/rows` hot path. Add a migration **only** if EXPLAIN demands —
  expected outcome: none. No speculative GIN/index (avoids write-cost for no proven gain).

## Part A — `MoleculeResolver` UUID batch
`cellar/application/shared/molecule_resolver.py`.

**Today:** `resolve(workspace_id, refs)` loops `for ref in refs: await _resolve_one(...)`;
`_resolve_uuid` does one `molecule_repo.find_by_id_in_workspace` per UUID ref (each
reconstructing a full `Molecule` aggregate).

**Rework `resolve`** (keep `_resolve_one` / the non-UUID `_resolve_*` helpers as-is):
1. First pass over `refs` in order: classify each. For UUID-type refs, parse
   `uuid.UUID(ref.value)`; invalid string → record an `invalid` outcome inline (no DB
   hit). Collect the set of valid parsed UUIDs.
2. One bulk fetch: `mols = await molecule_repo.find_by_ids(workspace_id, valid_uuids)`
   → build `by_id = {m.id: m}`. (`find_by_ids` is workspace-scoped and **returns
   tombstoned rows** — verified — so the tombstone reason is preservable.)
3. Second pass over `refs` in original order, building `(resolved, unresolved)`:
   - UUID ref, invalid string → `UnresolvedMolecule(ref, "invalid")`.
   - UUID ref, `by_id.get(id) is None` → `UnresolvedMolecule(ref, "not_found")`.
   - UUID ref, `mol.is_tombstone` → `UnresolvedMolecule(ref, "tombstone")`.
   - UUID ref, else → `ResolvedMolecule(...)` constructed **identically** to today's
     `_resolve_uuid` success branch.
   - Non-UUID ref → `await _resolve_one(workspace_id, ref)` (unchanged per-ref path).

**Invariants preserved (must not regress — shared infra):** output order == input ref
order; duplicate refs → duplicate outputs (no dedup, as today); `invalid` / `not_found`
/ `tombstone` reason codes unchanged; non-UUID resolution byte-identical. Net DB cost
for a save-all of N matched ids: **one** `find_by_ids` instead of N `find_by_id`.

**Tests:**
- New unit test `tests/unit/application/shared/test_molecule_resolver_batch.py` (or
  extend the existing resolver test if present): a mix of uuid + non-uuid refs resolves
  with **exactly one** `find_by_ids` call for the uuid batch (fake repo counts calls);
  invalid-string / not-found / tombstone uuids surface as `UnresolvedMolecule` with the
  right reason; output order matches input; a duplicate uuid yields two resolved outputs.
- Regression: re-run **every** resolver-caller suite green — bulk-add preview/commit,
  collection membership, SAR save-collection API, plus any `MoleculeResolver` unit tests.

## Part B — EXPLAIN verification (evidence; likely no migration)
Confirm the `/rows` query already rides the PKs; produce durable evidence.
- Build the actual statement from `SQLAlchemyDecompositionRowReader.fetch_rows`
  (scoped join + activity outerjoin + a representative filter + sort), seed a small
  representative run + assignments + activity in the dev DB, and run
  `EXPLAIN (ANALYZE, BUFFERS)`.
- Because a tiny seed may let the planner pick a seq scan legitimately, also run with
  `SET LOCAL enable_seqscan = off` to prove the PK indexes are **usable** for the join
  shape (Index Scan / Index Only Scan on `rgroup_assignments`, `sar_activity_values`,
  `molecules`).
- Capture the plan output + a one-paragraph conclusion in a committed perf note
  (`docs/backlog/sar-rows-explain-evidence.md`).
- **Migration `059` only if** the evidence shows a genuine bottleneck the PKs don't
  cover (e.g. the run-scoped `rgroups` filter dominating on very large single runs).
  Expected outcome: **no migration**. If one IS warranted, scope it then (GIN on
  `rgroups` + rewrite `_apply_filter`'s `->>'Rn' = v` to containment `@>`).

## Files
- Modify: `backend/src/cellar/application/shared/molecule_resolver.py`
- Create: `backend/tests/unit/application/shared/test_molecule_resolver_batch.py` (or extend existing)
- Create: `docs/backlog/sar-rows-explain-evidence.md` (the EXPLAIN evidence + conclusion)
- Conditional: `backend/alembic/versions/059_*.py` + `_apply_filter` rewrite — only if EXPLAIN demands.

## Out of scope
GIN/containment rewrite unless EXPLAIN demands it; any FE change; the broader bulk-add
ergonomics. The resolver fix is deliberately at the shared layer so every bulk-add
caller benefits, not just SAR save-all.
