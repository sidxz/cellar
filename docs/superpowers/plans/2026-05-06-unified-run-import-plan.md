# Unified Run Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make `Import Run File` the single import path on every Run tab. Re-imports are non-destructive (per-cell skip-and-report); a separate `Reset Run Data` button is the destructive escape hatch. Every successfully POSTed file is persisted as a Run attachment.

**Architecture:** Backend extends `_StoredPreview` to keep raw bytes; `PreviewRunFile` and `ImportRunFile` gain a conflict scan that compares each `(plate, well)` and `(well, readout_def)` against existing run state and produces `will_create / will_skip / will_fail` reports. `ImportRunFile` calls `UploadAttachment` after the write commit. New `ResetRunData` use case wipes plates/wells/readouts/curves but keeps run + attachments.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Pydantic v2 / Lagom DI / dry-python returns. Frontend Next.js 16 / React 19 / shadcn/ui / TanStack Query.

**Spec:** `docs/superpowers/specs/2026-05-06-unified-run-import-design.md`

---

## Backend

### Task 1: Extend `_StoredPreview` with raw bytes

**Files:**
- Modify: `backend/src/cellar/application/screening/import_run_file.py` (around line 87-95)

- [ ] Add `raw_bytes: bytes`, `filename: str`, `content_type: str` to `_StoredPreview`. Update `PreviewRunFile._execute` to populate them from the upload (filename comes through; content_type can be inferred from extension or defaulted to `application/octet-stream`).

### Task 2: Add conflict types + helpers

**Files:**
- Modify: `backend/src/cellar/application/screening/import_run_file.py`

- [ ] Add `WellConflict`, `ReadoutConflict`, `CreatePlan`, `SkipPlan` dataclasses near the existing DTOs.
- [ ] Add `_scan_conflicts(normalized: NormalizedTable, existing_plates: list[Plate], existing_readouts: dict[(well_id, rd_id)] -> ReadoutData, templates_by_format) -> tuple[CreatePlan, SkipPlan, list[str]]`. Pure function. Returns the writes to perform and the conflicts to report.

### Task 3: Update `PreviewRunFileResult` with conflict counters

**Files:**
- Modify: `backend/src/cellar/application/screening/import_run_file.py`

- [ ] Extend `PreviewRunFileResult` with `will_create_plates: int`, `will_create_wells: int`, `will_create_readouts: int`, `will_skip_wells: tuple[WellConflict, ...]`, `will_skip_readouts: tuple[ReadoutConflict, ...]`.
- [ ] In `PreviewRunFile._execute`, after normalize, also load existing plates/wells/readouts and run `_scan_conflicts`. Populate the counters.

### Task 4: Refactor `ImportRunFile` to skip-and-report

**Files:**
- Modify: `backend/src/cellar/application/screening/import_run_file.py`

- [ ] Drop the `run.wells` rejection block (current lines ~388–399). Drop `replace_existing` from `ImportRunFileCommand`.
- [ ] Load existing plates+readouts; run `_scan_conflicts`; build new plates/wells/readouts only from `CreatePlan`. Reuse existing plate id when plate name already exists; create new wells; write only readouts not already present.
- [ ] Extend `ImportRunFileResult` with `conflicts_well_metadata`, `conflicts_readout`, `attachment_id`. Populate from the scan + post-attach.

### Task 5: Attach raw file on import success

**Files:**
- Modify: `backend/src/cellar/application/screening/import_run_file.py`
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (DI binding for `ImportRunFile`)

- [ ] Inject `UploadAttachment` use case into `ImportRunFile`. After `_uow.commit()` and calc engine, call it with the cached `(raw_bytes, filename, content_type)` and `attachable_type=RUN`. Failures become a non-fatal warning on result.

### Task 6: Add `ResetRunData` use case

**Files:**
- Create: `backend/src/cellar/application/screening/reset_run_data.py`
- Modify: `backend/src/cellar/domain/screening_assay/events.py` (add `RunDataReset` event)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (bind it)
- Modify: `backend/src/cellar/interface/dependencies.py` (add `ResetRunDataDep`)
- Modify: `backend/src/cellar/interface/routes/runs.py` (add `POST /runs/{run_id}/reset-data`)

- [ ] Pattern after `DeleteRun`: only DRAFT/IN_PROGRESS, not locked. Cleanup order: curves → readout_data → plates (cascade wells) → clear `run.qc_metrics` → save run. Returns counts; emits `RunDataReset` event with counts on the run aggregate.
- [ ] Plates: add `RunRepository.delete_plates_for_run(workspace_id, run_id)` if not present, OR clear `run.plates` and rely on save; check what's idiomatic.

### Task 7: Update routes — preview + import response shapes

**Files:**
- Modify: `backend/src/cellar/interface/routes/run_import.py`

- [ ] Add `WellConflictModel`, `ReadoutConflictModel`. Extend `PreviewRunFileResponse` with `will_create_plates/wells/readouts`, `will_skip_wells`, `will_skip_readouts`. Drop `replace_existing` from `ImportRunFileRequest`. Extend `ImportRunFileResponse` with conflict arrays + `attachment_id`.

### Task 8: Backend tests

**Files:**
- Modify: `backend/tests/unit/application/screening/test_import_run_file.py`
- Create: `backend/tests/unit/application/screening/test_reset_run_data.py`

- [ ] Tests for: existing run accepts new plate; overlapping plate appends new well; existing readout cell skipped with conflict; well metadata mismatch skipped; raw file attached on success; reset clears expected entities; reset preserves attachments; reset rejects locked.

### Task 9: Backend commit

- [ ] Run `cd backend && uv run pytest tests/unit/application/screening/ tests/unit/domain/screening_assay/ -x` clean.
- [ ] Commit backend changes.

## Frontend

### Task 10: Update import hook types

**Files:**
- Modify: `frontend/src/features/screening-assay/hooks/use-run-import.ts`

- [ ] Add `WellConflict`, `ReadoutConflict` types. Extend `PreviewRunFileResponse` and `ImportRunFileResponse`. Drop `replace_existing` from request.

### Task 11: Add `useResetRunData`

**Files:**
- Modify: `frontend/src/features/screening-assay/hooks/use-runs.ts`

- [ ] Mutation that POSTs to `/api/v1/runs/{id}/reset-data`. Invalidates run, plate-map, readout-data, dose-response queries.

### Task 12: Wizard preview shows conflicts

**Files:**
- Modify: `frontend/src/features/screening-assay/components/run-import-wizard.tsx`

- [ ] PreviewStep renders `will_create / will_skip / will_fail` summary cards. Skip section is collapsible with up to 10 sample conflicts per reason. Import button stays enabled when `will_create.total === 0`; label changes to "Attach file" with a soft warning.

### Task 13: `RunDataPanel` — one button on every tab

**Files:**
- Modify: `frontend/src/features/screening-assay/components/run-data-panel.tsx`

- [ ] Replace the conditional `Import CSV` / `Import Readouts` / `Import Run File` cluster with a single `Import Run File` button that's always visible (disabled only if locked). Same on Plate Map empty state. Drop the unused dialog state.

### Task 14: Reset Run Data dialog + button

**Files:**
- Create: `frontend/src/features/screening-assay/components/reset-run-data-dialog.tsx`
- Modify: `frontend/src/features/screening-assay/components/run-detail.tsx`

- [ ] AlertDialog with damage report. Button on Run header actions, visible when (`!is_locked && status in [draft, in_progress] && plate_count > 0`). Sits next to Delete.

### Task 15: Delete legacy components + endpoints

**Files:**
- Delete: `frontend/src/features/screening-assay/components/bulk-readout-import-dialog.tsx`
- Delete: `frontend/src/features/screening-assay/components/simplified-import-dialog.tsx`

- [ ] Verify no other imports via grep before delete. Delete unused hooks too.

### Task 16: Frontend type-check + commit

- [ ] `cd frontend && pnpm tsc --noEmit` clean.
- [ ] Commit frontend changes.
