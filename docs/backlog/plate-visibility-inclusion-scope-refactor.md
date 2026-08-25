# Plate visibility: replace the exclusion set with an inclusion scope (deleted-org residual, Duar on the read path)

**Found:** 2026-08-25, S7 whole-branch review of the plate tracker revamp (branch `feat/plate-tracker-revamp`,
spec `docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md` §3).

**Design as shipped:** `PlateVisibilityService.excluded_org_ids()` = "every org in the Duar directory except
mine" (empty for admins/system). Every read/write call site keeps its S2-era `excluded: set[UUID]` plumbing
(~24 sites, three repository query signatures: `exclude_owner_org_ids` on plates/tag-browse/read models).

**Why it is not fully fail-closed:**
1. A plate whose `owner_org_id` is absent from the directory is *not* excluded, i.e. visible to everyone.
   S7 fixed the **disabled**-org case (`OrgDirectory(include_disabled=True)` for the visibility instance —
   review finding C1); an org **deleted** from Duar is a documented residual.
2. Duar is now on the plate read path: after the 5-minute cache expires, a Duar outage turns every non-admin
   plate/group/loan/tag-browse/molecule→plates/import read into a 503 (`ServiceUnavailableError`, finding I2).
   No stale-serve on purpose (a stale list could also hide a newly created org).
3. `list_orgs()` (an HTTP call on a cold cache) runs *inside* `async with self._uow` at every call site,
   holding a DB session across network I/O (finding M1). Harmless at current scale.
4. Two `OrgDirectory` instances exist (route singleton in `interface/dependencies/_core.py` for `/api/v1/orgs`,
   container port in `infrastructure/di/_core.py` for visibility), each with its own 5-min cache (M2).

**Fix direction (an S-sized session, not a patch):** invert the predicate. `PlateVisibilityService` returns a
`VisibilityScope` = `all` (admin/system) | `own(org_id, borrowed_plate_ids)`; repositories take
`visible_owner_org_id: UUID | None` and emit `owner_org_id IS NULL OR owner_org_id = :mine OR id IN :borrowed`;
`can_view`/`can_view_owner` compare against the caller's org instead of a set. This removes Duar from the read
path entirely (1–3 disappear), makes deleted/disabled/unknown orgs fail-closed by construction, and lets the
route singleton be the only directory instance. Sweep: the ~24 construction/call sites listed in
`docs/superpowers/plans/2026-08-25-s7-strict-visibility-audit-actor.md` Task 2, plus
`registered_plate_repository.py::search`, `tag_browse_repository.py`, the molecule→plates read model,
`plate_loans.py::_loan_visible`, and the group/insights 403 gates. Keep the API tests from S7 as the
regression net — they assert hidden==404 for a non-admin foreign caller and visibility for admins.
