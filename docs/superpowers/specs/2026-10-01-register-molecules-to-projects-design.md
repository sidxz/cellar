# Register molecules to projects — bulk add + project at registration

**Date:** 2026-10-01 · **Status:** approved; plan at `docs/superpowers/plans/2026-10-01-register-molecules-to-projects.md`
**Context:** project chips on `/search` now return only compounds *registered to* the
project (`_project_membership_clause`, ruling 2026-10-01). The only way to register a
compound to a project today is one at a time from the compound page, so every chip in
saclab-dev reads 0. This adds (1) a bulk add endpoint and (3) a project choice at
registration. Search-results "Add to project" (option 2) was not chosen.

## Decisions (user, 2026-10-01)

- **Bulk registration scope:** one project picker per upload; every compound in the file
  is linked. No per-row project column, no file-format change.
- **Existing compounds are linked too:** deduplicated and disclosed outcomes link the
  existing compound. Merge candidates are linked through the merge (below).
- **Server-side, as each compound registers:** linking happens inside registration
  (single and bulk), not in a final workflow step or the frontend.

## 1. Bulk endpoint

`POST /api/v1/projects/{project_id}/molecules`

```json
{ "references": [{ "value": "CC-000123", "ref_type": "registration_number" }] }
```

- `ref_type` ∈ `uuid | registration_number | external_id | smiles | inchi_key | name` —
  the `MoleculeReferenceBody` shape `POST /collections/{id}/molecules` already takes.
- Response `201`:
  `{ "added_count": n, "already_present": n, "unresolved": [{ "value", "ref_type", "reason" }] }`
  — the collection add contract, same response models.
- New use case `AddMoleculesToProject` (application/research_organization): resolve via
  the existing `MoleculeResolver`, then one `MoleculeRepository.add_to_project_many(
  workspace_id, project_id, molecule_ids) -> list[uuid]` (ids newly linked) — a single
  `INSERT … SELECT … WHERE molecule.workspace_id = :ws ON CONFLICT DO NOTHING RETURNING`.
- Access via the shared project-access check (§4). Unknown project → 404.
- Audit: one `EntityAddedToProject` per *newly* linked compound (unchanged event, so the
  audit trail stays per compound).
- The existing single route `POST /projects/{id}/molecules/{molecule_id}` keeps its URL
  and contract (204; 404 when the molecule is not in the workspace) but delegates to
  `AddMoleculesToProject` with one `uuid` reference. The single-add use case is deleted.

## 2. Project at registration

### Command + linking

- `RegisterMoleculeCommand.project_ids: list[uuid.UUID] = []`.
- `RegisterMolecule` links the outcome's **surviving** compound:

  | Outcome | Compound linked | Transaction |
  |---|---|---|
  | REGISTERED (disclosed or undisclosed) | the new compound | same UoW as the registration |
  | DEDUPLICATED (InChIKey or identifier match) | the existing compound | same UoW |
  | DISCLOSED (undisclosed record gains its structure) | that record | short UoW right after the disclosure service returns (it owns its own transaction) |
  | DISCLOSED → auto-merged (`was_merged`) | `merged_into_molecule_id` | same as above |
  | MERGE_CANDIDATE (awaits confirmation) | the undisclosed source record | same as above |
  | CONFLICT | nothing — registration returns an error, nothing is registered | — |

- Linking is idempotent (`ON CONFLICT DO NOTHING`), emits `EntityAddedToProject` per new
  link, and is skipped when `project_ids` is empty — zero change for CDD import and every
  other existing caller of `RegisterMolecule`.

### Merges carry project links

- New `MoleculeProjectMergeSideEffect` (infrastructure, beside
  `molecule_tag_merge_side_effect.py`): delete source rows the target already has, then
  re-point `molecule_projects` source → target. Registered in `MergeSideEffectRegistry`
  (`infrastructure/di/_chemical_registration.py`; the Temporal worker uses the same
  registry).
- So a merge candidate confirmed anywhere (wizard results, pending-merges page, bulk
  `confirm-merges`) moves its project link to the surviving compound; a rejected merge
  leaves the newly registered record in the project. This also fixes a pre-existing loss:
  any merge today drops the source's project memberships.

### Single registration

- `RegisterMoleculeBody.project_ids: list[uuid.UUID] = []` → command. The route already
  orchestrates register + optional batch; no other change.

### Bulk registration

`project_ids` threads through the same path as `create_batch_on_duplicate`:

- `POST /api/v1/bulk-registrations` multipart: repeated `project_ids` form field
  (`list[uuid.UUID] = Form([])`).
- `StartBulkRegistrationFromFileCommand` → `StartBulkRegistrationRequest` →
  `BulkRegistrationWorkflowInput` → **the `continue_as_new` payload** (fields dropped
  there are silently lost after the restart) → `ChunkInput` → `RegisterMoleculeCommand`
  in `process_chunk`.
- Sync fallback: `BulkRegistrationService` command gets `project_ids` and passes it to
  `RegisterMolecule`.

## 3. UI (registration wizard)

- `step-input.tsx`: an optional "Projects" multi-select beside Originating Organization,
  in both the single and the bulk sections. Reuse the search page's `ProjectFilter`
  (chips + "Add" popover, active projects only).
- `SingleInput.projectIds` / `BulkInput.projectIds` (`types/registration-wizard.ts`);
  `useSubmitRegistration` sends `project_ids`; `useStartBulkRegistration` appends one
  `project_ids` form field per id.
- Summary step: "Will be added to: X, Y". Results step: "Added to X".
- Compound page Projects tab: unchanged UI (now backed by the bulk use case).
- orval regenerated for the new body/form fields (revert version-stamp churn).

## 4. Access and errors

- One application check, `ProjectAccess.check_editable(workspace_id, project_ids, auth)
  -> DomainError | None` (railway style: callers return `Failure(err)`)
  (project repo + member repo): each project exists in the workspace (404), is not
  archived (422 "Project … is archived"), and the caller is admin or holds ≥ editor
  project role (403 naming the project). Used by `AddMoleculesToProject`, by
  `RegisterMolecule` when called with `auth` and non-empty `project_ids`, and by
  `StartBulkRegistration` **before** the workflow starts — so a bad choice fails before
  anything is registered.
- Worker-side `process_chunk` calls `RegisterMolecule` without `auth` (system) and trusts
  the list validated at upload start.

## 5. Compatibility

All API changes are additive (new endpoint, optional fields). Response shapes of existing
endpoints are unchanged, so daikon (consumes cellar's API live) needs no notice.

## 6. Tests

- API: bulk endpoint with mixed `ref_type`s, unresolved values, repeats
  (`already_present`), archived project (422), non-member (403), unknown project (404);
  single route still 204 / 404.
- API: single registration with `project_ids` — new compound and deduplicated compound
  both linked; non-editable project → 403 and nothing registered.
- API/integration: bulk registration through the sync fallback links registered and
  deduplicated rows.
- Integration: `MoleculeProjectMergeSideEffect` — source links move to target, shared
  links deduped.
- Unit: workflow `continue_as_new` payload carries `project_ids`.
- FE: wizard sends `project_ids` for single and bulk.

## Out of scope

Search-results / collection "Add to project" button; per-row project column in upload
files; bulk *remove* endpoint; CDD import project assignment.
