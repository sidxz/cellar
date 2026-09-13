# `POST /api/v1/molecules/depict` raises TypeError on every call

**Found:** 2026-09-12, while adding `POST /api/v1/sar/mcs` (the MCS ask names depict as the
consumer of `core_smiles`, so the new API test called it).

**Symptom:** every request returns 500.

```
TypeError: DepictMoleculesQuery.__init__() got an unexpected keyword argument 'workspace_id'
  src/cellar/interface/routes/molecules.py:734
```

**Root cause:** the route builds `DepictMoleculesQuery(workspace_id=auth.workspace_id, ...)`, but
`DepictMoleculesQuery` (`application/chemical_registration/depict_molecules.py:30-33`) declares only
`smiles_list` / `width` / `height`, and the shared `Query` base carries no `workspace_id` either.
The kwarg has never been accepted — depiction is pure RDKit rendering of supplied SMILES and reads
nothing workspace-scoped, so the field was presumably dropped from the query without the route
following.

**Impact:** the endpoint is dead for every caller. In-app that includes
`frontend/src/shared/lib/export/structure-image.ts`, which embeds structure images in Excel exports,
and the generated client in `shared/lib/api/molecules/molecules.ts`. Nothing raised it before now,
which suggests the FE paths either fall back silently or are themselves unexercised — worth checking
while fixing.

**Fix:** one line, either direction — drop `workspace_id=` from the route call, or add
`workspace_id: uuid.UUID | None = None` to the query. Prefer dropping it: the use case genuinely has
no tenant-scoped read, and adding an unused field invites the opposite confusion later. Add an API
test; there is none today, which is why a 500 sat here unnoticed.

**Blocked by this:** `tests/api/test_mcs_routes.py::test_the_core_is_depictable` is marked `xfail`
pointing here. It asserts the MCS `core_smiles` renders — the integration the MCS ask asked for —
and will pass as soon as the route is fixed.
