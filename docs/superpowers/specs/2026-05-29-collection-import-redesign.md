# 2026-05-29 — Collection Import Redesign

Today's collection import is a 3-tab dialog
(`features/research-organization/components/add-molecules-dialog.tsx:347`)
with a fixed 2-column CSV (`identifier,type`), no header detection, no
mapping, no preview classification, no template reuse. SMILES paths only
ever call `find_by_inchi_key` — unregistered molecules are **silently
rejected** with a one-word "not_found" reason.

Chemists routinely receive partner CSVs / vendor catalogs / SDFs with
hundreds of compounds where some fraction aren't in Cellar yet. Today
that means: manually identify the unknowns, leave the page, register
them via the bulk-register wizard, come back, re-upload the original
CSV. Broken.

This spec redesigns collection import along the protocol-import wizard
pattern (`run-import-wizard.tsx:75`), with the **registration handoff
kept as a separate concern** because Cellar registration has fields
(org, source, disclosure scientist, eventual GxP attribution) that
don't belong in a collection-import preview.

## Goals

1. Header auto-detection + manual column mapping, matching the run-file
   wizard's UX.
2. Per-row preview with explicit status classification (resolved /
   already_member / ambiguous / unregistered / error) and counts.
3. Save-and-reuse mapping templates, workspace-scoped, mirroring
   `RunImportTemplate`.
4. Resolved rows committable independently of unregistered rows
   (chemist can add the 140 they have now and come back for the 60).
5. Unregistered rows hand off cleanly to the existing bulk-register
   wizard with structures pre-filled, then return to the collection
   import to add the newly-registered molecules in one click.

## Non-goals

- Auto-registration inside the collection import wizard. Registration
  needs fields (org, scientist, source) that don't belong here.
- Per-row override of the "register or skip" decision — V1 is a clean
  handoff to the register wizard; per-row UX lives there if it ever
  exists.
- SDF support — V1 is CSV/XLSX. The shared `chemical_file_parser` can
  read SDF but the wizard's preview shape is tabular.
- Batch/inventory fields in the same CSV — collections are about
  molecules, not batches.
- Bulk-remove via CSV (asymmetric to import — defer until requested).
- A "pending membership" state on collections (the auto-resolve flow).
  Pending lists are new domain state and would leak unfinished-import
  concepts across the product.

## Pieces

### 1 — `BulkAddToCollection` use case (BE)

New use case at
`backend/src/cellar/application/research_organization/bulk_add_to_collection.py`.

```
BulkAddToCollectionCommand:
  collection_id: UUID
  rows: list[BulkAddRow]            # parsed + mapped
  dry_run: bool                     # preview vs commit
  source_label: str | None          # "CSV import 2026-05-29"

BulkAddRow:
  row_index: int
  registration_number: str | None
  external_id: str | None
  inchi_key: str | None
  smiles: str | None
  name: str | None
  notes: str | None                 # optional column; audit only

BulkAddToCollectionResult:
  outcomes: list[RowOutcome]
  resolved_count: int
  already_present_count: int
  unregistered_count: int
  ambiguous_count: int
  error_count: int
  preview_id: UUID | None           # set when dry_run + unregistered>0;
                                    # stashes unmatched rows for handoff

RowOutcome:
  row_index: int
  status: Literal["resolved", "already_present", "ambiguous",
                  "unregistered", "error"]
  molecule_id: UUID | None          # set when resolved or already_present
  molecule_name: str | None         # for display
  candidates: list[UUID] | None     # set when ambiguous
  message: str | None               # diagnostic (e.g. "no usable identifier")
```

Pure find-and-add — no `RegisterMolecule` call. Wraps the existing
`MoleculeResolver` (`application/shared/molecule_resolver.py:45`) for
the lookup path and `collection_repo.add_molecules` for the membership
write. Commit path adds only `resolved` rows; everything else is
skipped (chemist sees the outcomes and decides what to do).

When `dry_run=True` AND `unregistered_count > 0`, the use case stashes
the unmatched rows (those with `status="unregistered"`) under a fresh
`preview_id` with a 30-minute TTL. This `preview_id` is what the
register-wizard handoff consumes (see Piece 5).

### 2 — Two endpoints

Mirror the bulk-batch-identifier endpoint pair shipped earlier this
month:

- `POST /api/v1/collections/{collection_id}/molecules/preview-bulk` —
  dry_run=True. Returns outcomes + counts + `preview_id` if any
  unregistered.
- `POST /api/v1/collections/{collection_id}/molecules/bulk` —
  dry_run=False. Adds resolved rows; returns outcomes + counts.

Same request shape (`BulkAddToCollectionRequest`), same response shape.
Workspace scoping via the standard auth middleware (resolver already
honors `workspace_id`).

### 3 — Mapping templates (BE)

New aggregate `CollectionImportTemplate` at
`backend/src/cellar/domain/research_organization/collection_import_template.py`,
1:1 with `RunImportTemplate`:

```
CollectionImportTemplate:
  id: UUID
  workspace_id: UUID
  name: str
  description: str | None
  column_mapping: dict       # JSONB: {registration_number, external_id,
                             # inchi_key, smiles, name, notes}
  created_by: UUID
  created_at, updated_at
```

Migration adds `collection_import_templates` table — schema mirrors
`run_import_templates` (33-2 / 33-3). CRUD routes at
`/api/v1/collection-import-templates` (GET list / POST create / PUT
update / DELETE) — copy the shape of `routes/run_import.py:522–584`.

Auto-pick by header overlap (≥70%, same threshold as run-file wizard).

### 4 — Header auto-detection

Extend the run-file synonym dictionary pattern
(`long_format_normalizer.py:183–264`) for collection-import column
roles:

| Role | Synonyms (case-insensitive, normalized) |
|---|---|
| `registration_number` | reg, reg_no, reg_number, registration, compound_id, cellar_id, cc_number |
| `external_id` | external_id, vendor_id, vendor_lot, cas, cas_number, chembl_id, pubchem_id, supplier_code, catalog_no, sku |
| `inchi_key` | inchi_key, inchikey, inchi |
| `smiles` | smiles, canonical_smiles, structure, mol_smiles |
| `name` | name, compound_name, molecule_name, common_name, title |
| `notes` | notes, note, comment, comments, description, remark |

Detection is synonym-only for V1 (no value-shape heuristics) — the
roles are unambiguous enough that synonym matching gives high
confidence, and the chemist can override in the mapping step.

Lives at
`backend/src/cellar/application/research_organization/collection_import_mapping.py`.
Returns `HeaderSuggestion[]` shaped identically to the run-file
suggestion type for FE reuse.

### 5 — Handoff to the bulk-register wizard

When the preview shows `unregistered_count > 0`, the response carries
`preview_id`. The FE preview surface renders:

> ⚠ N rows reference molecules not yet registered. They won't be added
> by this import.
> &nbsp;&nbsp; [Register them →]   [Skip and commit X resolved rows]

The **Register them** button routes to
`/compounds/bulk-register?from_collection_import=<preview_id>&return_to_collection=<collection_id>`.

Server side: a new endpoint
`GET /api/v1/collection-import-previews/{preview_id}/unregistered-rows`
returns the stashed rows as a structure list:

```
UnregisteredRowsResponse:
  rows: list[{
    name: str | None,
    smiles: str | None,
    external_ids: list[{type: str, value: str}],
    notes: str | None
  }]
  collection_id: UUID | None
  collection_name: str | None
```

The bulk-register wizard
(`features/chemical-registration/components/registration-wizard/`)
gains:

- A startup branch: if `from_collection_import` is present in the URL,
  fetch the stashed rows and pre-fill the wizard's input step as if
  the chemist had uploaded a CSV with those rows. The existing
  `step-input.tsx` / `step-preview.tsx` / `step-processing.tsx` flow
  takes over from there — chemist fills in org/scientist/source on
  the existing screens, no schema change to the register wizard.
- A success-step branch: if `return_to_collection` is present, render
  an additional CTA on `step-summary.tsx`:
  > ✓ X molecules registered.
  > &nbsp;&nbsp; [Add to "{collection_name}" →]
- Clicking the CTA POSTs the new molecule IDs to
  `POST /api/v1/collections/{id}/molecules` (the existing single-add
  endpoint, accepting UUIDs) and routes to the collection page.

Rows whose registration failed (merge candidates, errors) are NOT
added. The success-step counts and the audit trail tell the chemist
what landed.

### 6 — Frontend wizard

New route `/collections/{id}/import` with a 4-step wizard at
`frontend/src/features/research-organization/components/collection-import-wizard/`:

1. **Upload step** — drag-drop CSV/XLSX. Template download button
   generates `collection-import-template.csv` with the 6 columns + 3
   example rows (one by reg number, one by SMILES, one by external_id).
2. **Mapping step** — table of {CSV header → role select}. Apply-template
   dropdown loads saved templates; auto-picks the best match (≥70%
   overlap) on initial load. Per-column manual override. Re-preview
   on changes. "Save mapping as template" inline checkbox + name input,
   shown on this step.
3. **Preview step** — colored count badges (emerald `resolved` /
   muted `already_present` / amber `ambiguous` / amber `unregistered` /
   red `error`); per-row table with status badge + diagnostic. The
   ambiguous section uses an inline picker (reuse the run-import
   `DisambiguatePanel:684` pattern). The unregistered section has
   the handoff CTA from Piece 5. The commit button reads
   "Add X resolved rows" — enabled when `resolved_count > 0`,
   independent of unregistered/ambiguous counts.
4. **Confirm step** — success card "X molecules added · Y already
   present · Z skipped". If unregistered rows existed at commit time,
   secondary line: "N rows not added (unregistered). [Register them now]".

The wizard is entry-pointed from a "Bulk import" button on the
collection detail page header (next to the existing per-molecule "Add
Molecules" dialog — the dialog stays for small ad-hoc adds).

FE hooks at `features/research-organization/hooks/`:
- `usePreviewCollectionImport`
- `useCommitCollectionImport`
- `useCollectionImportTemplates` (list / create / update / delete)
- `useUnregisteredRowsForHandoff` (consumed by the register wizard's
  startup branch)

CSV parsing reuses the existing papaparse pattern from
`features/inventory/lib/parse-bulk-identifier-csv.ts:1`. New module at
`features/research-organization/lib/parse-collection-import-csv.ts`.

### 7 — What stays

- The existing `AddMoleculesDialog` for ad-hoc <20-molecule additions
  (Search + Paste tabs) is unchanged. The CSV tab gets a deprecation
  note + link to the new wizard, then can be removed in a follow-up.
- The existing `POST /api/v1/collections/{id}/molecules` single-add
  endpoint stays — the bulk path is additive.
- `MoleculeResolver` is unchanged.

## Wire-shape additions

- New `BulkAddRow` / `RowOutcome` / `BulkAddToCollectionResult` types
  in `domain/research_organization/`.
- New `CollectionImportTemplate` aggregate + repository protocol.
- Frontend `CollectionImportPreview` / `CollectionImportRowOutcome`
  types added via orval regen.

## Migration

Single migration: `collection_import_templates` table. Shape mirrors
`run_import_templates` (id, workspace_id, name, description,
column_mapping JSONB, created_by, created_at, updated_at). Unique
constraint on `(workspace_id, name)`. Foreign keys to `workspaces` +
`users`.

No data migration; no backfill.

## Smoke acceptance

1. Upload a CSV with 200 rows: 140 by `registration_number` (existing),
   30 by `smiles` (10 existing, 20 new structures), 30 by `name` (5
   existing, 25 unknown). Preview shows: 155 resolved, 0 already
   present, 20 unregistered, 25 error.
2. Mapping step auto-detects `Reg. No.` → registration_number,
   `Structure (SMILES)` → smiles, `Vendor Code` → external_id, etc.
3. Save the mapping as template "Partner ACME quarterly." Upload same
   shape next month → template auto-picks → no manual mapping needed.
4. Hit "Add 155 resolved rows" → success card + 155 added. Refresh the
   collection page → 155 new members.
5. Click "Register them" → routes to bulk-register wizard with 20 rows
   pre-filled. Chemist fills in org + scientist + source → registers.
6. Success step shows "✓ 20 molecules registered. [Add to ACME Q3
   Collection]" → click → 20 newly-registered molecules added to the
   collection in one round-trip.
7. Upload a CSV with no `name`, no `smiles`, no identifier columns
   (just notes). Preview shows N error rows with "no usable
   identifier" diagnostic; commit button disabled.
8. Upload a CSV with an ambiguous name ("aspirin" → 2 hits in the
   workspace). Preview shows 1 row in `ambiguous`; inline picker
   resolves it; commit proceeds.

## Out-of-band notes

The handoff `preview_id` lives in the same in-memory or DB-backed
short-TTL store the run-file imports already use. If the chemist takes
>30 minutes between "Register them" and the actual registration commit,
they'll need to re-upload the original CSV (acceptable — registration
flows are session-bounded anyway).

A future follow-up could add a "pending unregistered" banner on the
collection detail page listing rows the chemist staged but hasn't
registered yet, as a soft reminder. Not in V1 — solving with chemist
discipline first.
