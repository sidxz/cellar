# Unified Run Import — Design

**Date:** 2026-05-06
**Branch:** `fe2`
**Status:** Approved by user; awaiting implementation plan.

## Problem

Run-level import on the Run Detail page currently has three buttons:

1. `Import CSV` → `BulkReadoutImportDialog` (legacy bulk readout import).
2. `Import Readouts` → `SimplifiedImportDialog` (legacy, only when `hasPlateMap`).
3. `Import Run File` → `RunImportWizard` (the long-format unified flow,
   only shown when `!hasPlateMap`).

Three problems:

- The chemist sees three import buttons with overlapping semantics. The
  long-format wizard already accepts every shape the legacy paths handle,
  so the legacy buttons are dead weight that adds confusion.
- `Import Run File` is **hidden** as soon as a run has any plate map data.
  Re-importing requires deleting the run and starting over.
- The backend `ImportRunFile` use case rejects re-imports
  (`"Run already has wells — pass replace_existing to overwrite"`) and even
  with `replace_existing=true` returns `"not yet supported in MVP"`.
- The raw uploaded file is parsed into a `ParsedTable`, cached in TTL
  memory for 60s, then **discarded**. A bench chemist who comes back two
  weeks later to defend their dose-response curve has no way to retrieve
  the source `.xlsx` — there is no audit artifact of what was uploaded.

## Goals

1. **One import button.** `Import Run File` is the only way to bring run
   data into the system. The two legacy buttons (and their dialogs, hooks,
   and routes if unshared) are deleted.
2. **Always available.** The button is visible on Readout Data, Plate Map,
   and Dose-Response tabs whenever the run is not locked, regardless of
   whether plates/wells already exist.
3. **Additive imports without silent overwrite.** A second file can land
   new plates, new wells on existing plates, and new readout values on
   existing wells, but never overwrite values the chemist has already
   committed. Conflicts are reported, not silently resolved.
4. **Raw file persisted as a run attachment** on every successful import,
   so the Files tab is the audit log of what was uploaded for this run.
5. **Explicit destructive escape hatch** (`Reset Run Data`) for the case
   where the first import was wrong end-to-end and the chemist needs to
   start over. Separate from the import path; never silent.

## Non-Goals

- Async / Temporal pipeline — sync only, 50K row cap (matches existing
  `_MAX_ROWS`).
- Auto-merging conflicting values via "newest wins" or similar policies.
- Cell-level edit-in-place from the wizard. Manual one-off edits remain
  the job of `Add Data`.
- Versioning the run on import. Reset is destructive; no soft-delete or
  restore.

## Conflict Semantic

The conflict unit is granular: per `(plate_name, well_position,
readout_definition_id)` for readouts, per `(plate_name, well_position)`
for well metadata. The same skip-and-report rule applies uniformly to
both layers.

| File row maps to                                                  | Action                                            |
|-------------------------------------------------------------------|---------------------------------------------------|
| New plate name                                                    | Create plate + wells + readouts                   |
| Existing plate, new well position                                 | Create well + its readouts                        |
| Existing well, file metadata matches, readout cell empty          | Write readout cell                                |
| Existing well, file metadata matches, readout cell populated      | Skip cell, report `readout_conflict`              |
| Existing well, file metadata differs (well_type / batch / dose)   | Skip whole row (well + readouts), report `well_metadata_conflict` |
| Existing plate, file declares different `plate_format`            | Hard fail; surface in `validation_errors`         |

**"File metadata matches"** means:

- For `well_type`: derived from the protocol's control layout for that
  plate format and the well position. The control layout is canonical;
  the file's batch/dose values cannot reclassify a well that the layout
  has already painted as POS / NEG / BLANK. This rule is identical to
  the rule in the existing first-time import path.
- For `batch_ref`: identical normalized batch reference, OR both empty.
- For `concentration`: identical numeric value (with the protocol's
  `dose_unit`), OR both unset.

Plate-format mismatches abort the entire import at the preview phase. The
chemist resolves by renaming the plate in the source file, by changing
the protocol's plate-format expectations, or by `Reset Run Data`.

Post-import, the calc engine and dose-response fitter re-run unconditionally
when `readouts_created > 0`. The existing wiring covers this; no change.

## Preview Report (Step 3)

Today the preview shows: total rows, plates, blanks, unmatched batches,
validation errors. The wizard adds three count groups:

- **`will_create`** — new plates / new wells / new readout cells the
  import will land.
- **`will_skip`** — readouts skipped because the cell is already
  populated, plus wells skipped because of well-metadata mismatch.
  Breakdown by reason and a sample of the conflicting rows.
- **`will_fail`** — hard errors (plate-format mismatch, missing control
  layout for required normalization). The Import button is disabled when
  this list is non-empty.

If `will_create.total == 0 && will_fail.empty`, surface a soft warning:
*"This file is fully redundant with existing data — nothing will change.
Use Reset Run Data if you want to replace."*

## Raw File Persistence

The backend `_StoredPreview` cache today holds `ParsedTable + workspace_id
+ run_id + expires_at`. We extend it to also hold the raw `bytes`,
`filename`, and `content_type`. On `ImportRunFile` success — including
partial application where some cells skipped — the use case calls the
existing attachment service to persist the bytes as a `Run` attachment
with metadata: `imported_at`, `imported_by`, `import_result_summary`
(plates created, wells created, readouts created, skipped counts).

Filename collisions: attach as-is. The attachment store keys by
attachment id; the Files tab can show duplicates. Two imports of the
same filename are treated as two separate audit artifacts, not deduped.

**Why on commit, not on preview.** A chemist who hits Cancel on Step 3
should not end up with stray attachments. Atomic attach-with-import
keeps the file linked to the data it produced.

**Why even on full-skip imports.** The Files tab represents *what was
uploaded for this run*, not *what changed it*. A re-uploaded redundant
file is still a thing the chemist did and should be able to find later.

**Reset Run Data does not delete attachments.** Files are an audit
artifact independent of the parsed state. Manual deletion via the Files
tab if the chemist truly wants them gone.

## UI Surface Changes

### `RunDataPanel`

- Delete `Import CSV` and `Import Readouts` buttons + their state hooks
  (`bulkImportOpen`, `importReadoutsOpen`).
- Render `Import Run File` on each relevant tab's action row
  unconditionally, disabled only when `run.is_locked`. The button text
  is identical across tabs; the wizard does not need tab-aware behavior.
- `Add Data` (manual single-readout) stays — different need.

### Run header (`RunDetailPage`)

- New `Reset Run Data` button, destructive style. Visible only when
  `!run.is_locked && (plates.length > 0 || readouts.length > 0)`. Opens
  a confirm dialog with damage report:

  > *"This will delete:*
  > - *N plates*
  > - *M wells*
  > - *K readouts*
  > - *J dose-response curves*
  > - *L QC metric snapshots*
  >
  > *The run, its metadata, and attached files will be kept.*
  >
  > *This cannot be undone.*"

  Default: simple confirm checkbox is enough since attachments are
  preserved. Friction can be increased (e.g., typing the run name) if
  accidental resets become a real complaint after rollout.

### `RunImportWizard`

- Step 3 (Preview) renders the new `will_create / will_skip / will_fail`
  panels. The skip panel is collapsible with a per-conflict-reason
  breakdown and a sample of up to 10 conflicting (plate, well, readout)
  triples per reason.
- Import button disabled only when `will_fail` is non-empty. When
  `will_create.total == 0`, the button stays enabled and its label
  changes to "Attach file" with the soft warning rendered above it.
  Clicking submits the import as usual; the backend writes nothing and
  attaches the file. Single code path; chemist's intent ("get this
  file into the audit trail") is honored without a special UI branch.
- The raw file attaches on every successful POST to `/import-file`,
  including the no-op case above. The attachment lives or dies with
  the use case's success Result, not with the count of cells written.

### Dropped legacy code

- `frontend/src/features/screening-assay/components/bulk-readout-import-dialog.tsx`
- `frontend/src/features/screening-assay/components/simplified-import-dialog.tsx`
- Their hooks under `frontend/src/features/screening-assay/hooks/`
- Their backend endpoints if not consumed elsewhere — verify via grep
  before deletion. The `ImportRunReadouts` use case might still serve
  manual ad-hoc CSV→readouts paths used in tests; check before removing.

## Backend Changes

### `ImportRunFile` use case

1. Drop the `run.wells` rejection block (lines ~388–399 of
   `import_run_file.py`).
2. Drop the `replace_existing` flag from `ImportRunFileCommand` and
   delete the request body field on the route. Replace mode lives in
   `ResetRunData` now.
3. After loading the run, eager-load existing plates + wells + readouts
   into a per-run map keyed by `(plate_name, well_position)` and a
   secondary map keyed by `(well_id, readout_definition_id)`. Use the
   existing readers; do not invent a new repository method without
   reusing what's there.
4. For each `LongFormatRow`:
   - If plate name is new → create plate + well + readouts as today.
   - If plate name exists → resolve `Plate` by name. Validate
     `plate_format` matches the existing plate's format; if not, accumulate
     a hard error (this surfaces in preview already).
   - If well at `(plate, row, column)` exists → run the well-metadata
     comparison. On mismatch, accumulate a `well_metadata_conflict`
     entry, skip the row.
   - If well exists and metadata matches → for each readout column in
     the row, check `(well_id, readout_definition_id)` against the
     existing-readouts map. Existing → accumulate `readout_conflict`;
     missing → write the readout.
5. `ImportRunFileResult` gains:
   ```python
   conflicts_well_metadata: list[WellConflict]
   conflicts_readout: list[ReadoutConflict]
   ```
   Each conflict carries `plate_name`, `well_position`, and the reason
   in human-readable form (`"existing dose 10.0 µM, file dose 1.0 µM"`).
   Counts are also kept on the result for the wizard's summary cards.
6. After the run save and `_uow.commit()`, before dispatching events,
   invoke the attachment service to persist the cached raw bytes. The
   attachment service runs in its own UoW; failures do not roll back the
   import (file persistence is best-effort, surfaced as a non-fatal
   warning on the result similar to the existing `compute_warning`).

### `_StoredPreview`

```python
@dataclass(frozen=True)
class _StoredPreview:
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    table: ParsedTable
    raw_bytes: bytes          # NEW
    filename: str             # NEW
    content_type: str         # NEW
    expires_at: float
```

`PreviewRunFile` populates the new fields from the multipart upload.
TTL eviction in `InMemoryPreviewStore` already covers cleanup; no change.

### `PreviewRunFile` use case

The preview phase also runs the conflict scan now (it has the run +
existing wells available; the wizard needs `will_create / will_skip /
will_fail` to render Step 3). Returns a `PreviewRunFileResult` extended
with the same conflict counters and samples.

The conflict scan is deterministic and read-only; running it twice
(preview, then again at import time as a safety net) is fine. The
preview result drives the UI; the import-time scan is the source of
truth that drives the actual write.

### `ResetRunData` use case (new)

```
ResetRunDataCommand
  workspace_id: UUID
  run_id: UUID

ResetRunDataResult
  plates_deleted: int
  wells_deleted: int
  readouts_deleted: int
  curves_deleted: int
  qc_metrics_cleared: bool
```

Auth: `require_editor`. Rejects `is_locked` runs and any run whose
status is not `draft` or `in_progress` (terminal states have audit
trails — once approved/rejected, no reset).

Cleanup order, all within one UoW:
1. `dose_response_curves` for the run
2. `readout_data` for the run
3. `wells` (FK ON DELETE CASCADE from `plates`)
4. `plates` for the run
5. Clear `run.qc_metrics` (set to `{}` and bump version)

Attachments are NOT deleted. Run row is NOT deleted. Run metadata
(name, status, plate_format, protocol_id, operator, notes) is preserved.

Emits `RunDataResetEvent` with counts for audit.

### Routes

- `POST /api/v1/runs/{run_id}/preview-file` (multipart) — extends
  response with conflict counters.
- `POST /api/v1/runs/{run_id}/import-file` (JSON) — drops
  `replace_existing` from request body; extends response with conflict
  arrays + samples.
- `POST /api/v1/runs/{run_id}/reset-data` — new endpoint for
  `ResetRunData`. Returns 200 with the result. Editor + workspace
  scoped.

## Frontend Changes

### Hooks

- New `useResetRunData(runId)` mutation that POSTs to the reset-data
  endpoint. Invalidates the run query, plate-map query, readout-data
  query, dose-response query.
- Extend `usePreviewRunFile` and `useImportRunFile` types to include the
  new conflict shapes.

### Components

- New `ResetRunDataDialog`, modeled after the existing `DeleteRunDialog`
  pattern. Shows damage report, single confirm.
- New `ResetRunDataButton` rendered in the Run header actions.
- Update `RunImportWizard.PreviewStep` to render the `will_create /
  will_skip / will_fail` panels with collapsible breakdowns.
- Delete `bulk-readout-import-dialog.tsx`, `simplified-import-dialog.tsx`,
  and any state in `RunDataPanel` referring to them.

### `RunDataPanel`

```tsx
// Replaces the conditional block at lines 247-283 of run-data-panel.tsx
<div className="mb-4 flex gap-2">
  <Button
    size="sm"
    onClick={() => setAddReadoutOpen(true)}
    disabled={run.is_locked}
  >
    <Plus className="mr-2 h-4 w-4" /> Add Data
  </Button>
  <Button
    size="sm"
    variant="outline"
    onClick={() => setRunImportWizardOpen(true)}
    disabled={run.is_locked}
  >
    <Upload className="mr-2 h-4 w-4" /> Import Run File
  </Button>
</div>
```

The Plate Map tab keeps the same single button on its empty-state and
populated-state action rows.

## Test Plan

### Backend unit tests

Add to `tests/unit/application/screening/test_import_run_file.py`:

- `test_import_into_run_with_existing_plates_appends_new_plate`
- `test_import_overlapping_plate_appends_new_wells`
- `test_import_existing_well_writes_only_empty_readout_cells`
- `test_import_existing_readout_cell_skips_with_conflict_report`
- `test_import_well_metadata_mismatch_skips_row_with_conflict_report`
- `test_import_plate_format_mismatch_aborts_at_preview`
- `test_import_attaches_raw_file_on_success`
- `test_import_attaches_raw_file_even_on_full_skip` (if we ship that)
- `test_import_does_not_attach_on_validation_failure`

### Backend reset tests

`tests/unit/application/screening/test_reset_run_data.py`:

- `test_reset_clears_plates_wells_readouts_curves_qc`
- `test_reset_preserves_run_metadata_and_attachments`
- `test_reset_rejects_locked_run`
- `test_reset_rejects_terminal_status_run`
- `test_reset_emits_event`

### Frontend

`pnpm tsc --noEmit` clean; smoke test in browser per the manual recipe.

### Manual smoke

End-to-end on the existing `NadD` flow:

1. `Reset Run Data` on the existing run → confirm wells/plates/readouts gone, run still there, attached files still listed.
2. Import the original `.xlsx` → success, file appears in Files tab.
3. Import the same file again → preview shows 100% redundant; soft
   warning; file still attaches if user proceeds (or import button is
   disabled — final call deferred).
4. Import a separate file with one new plate that shares wells with an
   existing plate, but adds a new readout column (e.g., `OD600`) →
   preview shows N readouts to write, 0 conflicts; import succeeds; both
   files are in Files tab.
5. Import a file that overlaps with already-populated `raw AU` cells →
   preview shows N skip; import button still enabled; import writes 0
   readouts; both files in Files tab.
6. Import a file with mismatched dose for an existing well → preview
   shows row-level skip with `well_metadata_conflict`; chemist sees
   exactly which (plate, well) is the problem.

## Migration

No DB migration. Existing runs work as-is — the only behavior change is
that future imports go through the new conflict-aware path.

## Open Implementation Choices

- **Attachment metadata schema.** Whether `import_result_summary` lives
  in the `Attachment.metadata` JSON column or a dedicated relation.
  Default: JSON metadata; we have no reporting use case yet that needs
  joins.
