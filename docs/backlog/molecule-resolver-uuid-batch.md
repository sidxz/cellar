# MoleculeResolver resolves UUID refs one-query-per-ref (N+1)

**Found:** 2026-06-16, final review of SAR Unit C item 1 (save-all-matched → collection).
**Status:** open — folded into **SAR Unit C item 2 (perf)**.

## Root cause
`cellar.application.shared.molecule_resolver.MoleculeResolver.resolve()` loops over
refs and calls `_resolve_one` per ref; `_resolve_uuid` issues one
`molecule_repo.find_by_id_in_workspace(workspace_id, mol_id)` per ref — each
reconstructing a **full `Molecule` aggregate** (all-or-nothing `ChemicalStructure`
+ `ComputedDescriptors`). So resolving N uuid refs = N sequential DB round-trips +
N aggregate reconstructions.

## Impact
Every bulk-add path that funnels through the resolver: `BulkAddToCollection`,
`AddMoleculesToCollection`, and now `SaveDecompositionCollection` (SAR save-all).
The save-all path is the **first to feed the resolver the entire matched library**
(thousands of refs) — prior callers fed bounded selections/baskets (tens), so the
N+1 never bit. For a whole-collection save this is thousands of sequential queries,
directly undercutting SAR's "correct over the full collection of any size" premise.
Correctness is fine (tenant-safe, deduped); this is latency only.

## Planned fix (Unit C item 2 perf slice)
Batch UUID resolution in `resolve()`: partition refs by `ref_type`, resolve all
UUID refs in a **single** `molecule_repo.find_by_ids(workspace_id, uuid_list)`, then
map back preserving the existing per-ref semantics (`not_found`, `tombstone`/
`is_tombstone`, order, dedup). Non-UUID ref types keep the current per-ref path.

Fix at the **resolver** (root) rather than bypassing it in `SaveDecompositionCollection`
(e.g. calling `CollectionRepository.add_molecules` directly with the already-resolved
ids): the resolver-level fix keeps `AddMoleculesToCollection`'s domain event
(`CollectionMembersChanged`, audit/21 CFR Part 11) and already-present accounting
intact, and speeds up **every** bulk-add caller, not just save-all.

## Verify
- All resolver-caller test suites stay green (bulk-add preview/commit, collection
  membership, SAR save-collection API).
- Add a resolver unit test: a mix of uuid + non-uuid refs resolves with one
  `find_by_ids` for the uuid batch; not-found + tombstone uuids still surface as
  `UnresolvedMolecule`.
- Timing/`EXPLAIN` sanity on a few-thousand-ref save.
