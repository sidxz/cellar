# Long-Format Run Import — Plan

> Drafted 2026-05-05. 8 sessions. Goal: ingest one xlsx (or csv) file
> covering plate layout + per-well concentration + readout values for one
> or more plates, with preview/verify gate and reusable mapping templates.

## Reference file (canonical fixture)

`/Users/sidx/Downloads/NadD_LG-2200467564_100uM-DR_4.20.26.xlsx`

384-well plate, long format. Columns:

| Plate Name | Well | Concentration | LGCY BATCH NAME | Raw Data | Scientist |
|---|---|---|---|---|---|
| `..._Plate-1` | `A01` | (empty) | (empty) | `0.6282` | `Dan Selle` |
| `..._Plate-1` | `A02` | `100` | `LG-0021362-001` | `0.079` | `Dan Selle` |
| ... | ... | ... | ... | ... | ... |

Wells with value but no batch/concentration ⇒ controls (`BLANK` by default).

## What exists today (do not duplicate)

- `domain/screening_assay/run.py` — `Plate`, `Well`, `WellType {SAMPLE, POSITIVE_CONTROL, NEGATIVE_CONTROL, BLANK, REFERENCE}`, `ReadoutData`. Sufficient. No domain changes needed.
- `application/screening/plate_setup.py` — `ParsePlateMapFile` (CSV) + `SetUpRunPlate`. Plate-map parsing and well creation. CSV-only.
- `application/screening/import_run_readouts.py` — `ImportRunReadouts` (CSV). Wells must already exist; matches by header name.
- `application/screening/create_run.py` — creates a draft `Run` with metadata only.

## Locked decisions

1. **One file → one run, multi-plate.** Distinct `Plate Name` values ⇒ separate `Plate` rows on the same run. Same-format normal; mixed-format allowed.
2. **xlsx is a first-class format everywhere.** Refactor existing CSV importers (plate map + readout) to consume a shared tabular abstraction. xlsx works on all three importers as a side effect of S1.
3. **Preview-then-write is a hard gate.** Two endpoints:
   - `POST /preview-file` parses and returns headers, suggested mapping, sample rows, batch-resolution preview, control summary, and a short-lived `preview_id`.
   - `POST /import-file` takes `preview_id` + finalized mapping. No write endpoint accepts a raw file.
4. **Fuzzy header guessing + verify.** Synonym dictionary first; value-based fallback for unknowns. Each suggestion carries confidence (high/med/low). Wizard surfaces with green/amber/red badges; low-confidence requires explicit user accept before continuing.
5. **Templates are workspace-scoped, not protocol-scoped.** A template captures column-role map + concentration unit + control rules. It does NOT capture readout-def mapping (per-protocol). Auto-suggested when headers match.
6. **Re-import semantics.** Locked run ⇒ refuse. Unlocked + has wells ⇒ wizard requires explicit "Replace plate" choice.
7. **Sync only for MVP.** Hard cap (e.g. 50k rows / 130 plates). Temporal pipeline deferred.
8. **Run pre-created** via existing "New Run" dialog. "Import Run File" populates wells + readouts. Cleaner audit, simpler MVP.
9. **Multi-readout columns supported** in MVP (file with N value columns; one minimum).
10. **Unmatched batch ref** ⇒ skip well + surface in result. Do NOT silently treat as control.

## Synonym dictionary (S2 starting point — extend in code review)

| Role | Synonyms (lowercased, alphanumeric-only match) |
|---|---|
| `well` | well, position, address, wellid, wellposition |
| `plate_name` | plate, platename, plateid, platebarcode, barcode |
| `concentration` | conc, concentration, dose, c, concum, concuM, concnM |
| `batch_ref` | batch, batchid, batchname, lot, lotnumber, sampleid, compoundid, lgcybatchname |
| `scientist` | scientist, operator, user, performedby, analyst |
| `readout` | value, rawdata, raw, signal, absorbance, fluorescence, luminescence, ic50, percentinhibition |

Value-based fallback for unknown headers:
- Matches `^[A-Z]\d{1,2}$` (case-insensitive) on >80% of rows ⇒ likely `well`.
- Numeric, high uniqueness, no nulls ⇒ likely `readout`.
- Numeric, many repeated values, many nulls ⇒ likely `concentration`.
- Strings with same prefix across rows ⇒ likely `plate_name` or `batch_ref` (use prefix length to pick).

## Open scope (out of MVP)

- Auto-trigger curve fitting after import.
- Async/Temporal for huge files.
- Run creation directly from file (infer run_date, scientist from data).
- Smarter control inference (column 1 = neg, column 24 = pos heuristics).
- Org-wide template sharing across workspaces.

## Sessions

### S1 — Tabular file abstraction (Infrastructure)

**Goal:** xlsx + csv read into a unified record stream. Replace bytes-in-CSV-only across existing importers.

**Build:**
- `infrastructure/parsers/tabular_file.py` — `parse_tabular(file: bytes, filename: str) -> ParsedTable`. `ParsedTable` exposes `headers: list[str]` and `iter_rows() -> Iterator[dict[str, str]]`. Format detected by extension + magic bytes (xlsx zip signature, csv fallback). xlsx via `openpyxl` read-only mode.
- Refactor `ImportRunReadouts` and `ParsePlateMapFile` to accept `ParsedTable` (or a thin wrapper) rather than raw bytes.
- Interface routes that take CSV uploads gain xlsx support transparently.

**Tests:** parser unit tests — xlsx, csv with BOM, csv with `;` delimiter, mixed types, empty file, malformed xlsx.

**Acceptance:** existing plate map + readout import suites still pass; new xlsx tests pass; user can upload `.xlsx` to `/api/v1/runs/{id}/readouts/import` (existing endpoint) and it works.

### S2 — Long-format normalizer (Domain/Application)

**Goal:** pure function: parsed records + column mapping → typed long-format rows.

**Build:**
- `application/screening/long_format_normalizer.py`:
  - `ColumnMapping` dataclass (which header is which role; `readout_columns: list[(header, readout_def_id)]`).
  - `LongFormatRow` dataclass (`plate_name`, `well_pos: WellPosition`, `batch_ref?`, `concentration?`, `readouts: dict[uuid, float]`, `scientist?`, `inferred_well_type: WellType`).
  - `normalize(table, mapping, conc_unit) -> Result[list[LongFormatRow], DomainError]`.
  - `infer_mapping(table) -> SuggestedMapping` — synonym dictionary + value-based fallback, returns suggestions with confidence.
- Coordinate normalization (A01 ↔ A1) and plate-format inference (96/384/1536) per plate.
- Control inference: no batch + has value ⇒ `BLANK`.

**Tests:** unit tests for synonym matching, value-based fallback, A01↔A1, plate-format inference, control inference, NadD fixture roundtrip.

**Acceptance:** given the NadD file + a hand-built mapping, normalizer produces exact expected rows for plate 1.

### S3 — `ImportRunFile` use case (Application)

**Goal:** orchestrate parse → normalize → resolve → persist. Idempotent, transactional.

**Build:**
- `application/screening/import_run_file.py`:
  - `PreviewRunFileQuery` (returns parse handle + preview payload, stores parsed table in short-lived store).
  - `ImportRunFileCommand` (run_id, preview_id, finalized mapping, replace_existing flag).
  - Resolves batches via `BatchRepository`, readout-defs via `ProtocolRepository`.
  - Builds `Plate` + `Well` + `ReadoutData` aggregates; saves via existing repos.
  - Returns `ImportRunFileResult { rows_total, plates_created, wells_created, readouts_created, unmatched_batches: list[str], controls_inferred: int, errors: list[ImportError] }`.

**Preview store:** in-memory TTL cache (60s) keyed by `preview_id`. Don't persist parsed tables to DB.

**Tests:** integration tests with NadD fixture (DB required); replay-protection (preview_id can't be reused after consume); locked-run refusal.

**Acceptance:** end-to-end backend flow imports the NadD fixture into a run and writes 384 wells + 384 readout-data rows on the first plate.

### S4 — `RunImportTemplate` (Application + Persistence)

**Goal:** workspace-level reusable mapping templates.

**Build:**
- `domain/screening_assay/run_import_template.py` — small aggregate (`id`, `workspace_id`, `name`, `description`, `column_mapping`, `concentration_unit`, `control_rules`, `version`).
- Repository + migration.
- Use cases: `CreateRunImportTemplate`, `UpdateRunImportTemplate`, `DeleteRunImportTemplate`, `ListRunImportTemplates`.
- Header-match scoring helper used by preview to auto-suggest a template.

**Tests:** standard aggregate + repo tests; header-match scoring unit tests.

**Acceptance:** "Save as template" round-trip works; uploading a similar file later auto-suggests the template.

### S5 — REST surface (Interface)

**Goal:** thin endpoints over S3 + S4. API tests.

**Build:**
- `POST /api/v1/runs/{id}/preview-file` — multipart, returns preview JSON + `preview_id`.
- `POST /api/v1/runs/{id}/import-file` — JSON body with `preview_id` + `mapping`.
- `GET /api/v1/run-import-templates` — list workspace templates.
- `POST /api/v1/run-import-templates` — create template (typically called from wizard).
- `PUT /api/v1/run-import-templates/{id}`, `DELETE /api/v1/run-import-templates/{id}`.

**Tests:** API tests with FastAPI TestClient; multipart upload; auth/workspace scoping.

**Acceptance:** curl-driven E2E: preview → import → audit visible.

### S6 — `RunImportWizard` (Frontend)

**Goal:** modal wizard with 4 steps. Reuses dropzone + DataGrid patterns.

**Build:**
- Step 1 — **Upload**: dropzone, accepts xlsx/csv, posts to preview endpoint.
- Step 2 — **Mapping**: header table with role dropdown per column; confidence badge (green/amber/red); auto-suggested template banner with "Apply" / "Edit" buttons. Low-confidence rows force explicit confirm before "Continue" enables.
- Step 3 — **Preview**: per-plate summary (plate name, well count, samples, controls, unmatched batches), sample-row table with resolved compound names. "Replace existing wells" checkbox if run already has wells.
- Step 4 — **Confirm**: results summary + "Save mapping as template" toggle with name input.

**Tests:** component tests for each step; visual regression on mapping confidence badges.

**Acceptance:** user can drive the full flow against a running backend.

### S7 — Wire entry points (Frontend)

**Build:**
- "Import Run File" button on Protocol Detail header (next to "New Run"). Opens `RunImportWizard`. Wizard creates a run via existing flow first, then runs the import.
- "Import Plate Data" button on Run Detail when run has no wells.
- Empty-state CTA on RunsTab.
- Optionally: include in the "New Run" dialog as a tab/toggle.

**Tests:** smoke E2E.

**Acceptance:** at least two discoverable entry paths.

### S8 — Tests + integration + handoff

**Build:**
- Playwright E2E with NadD fixture.
- Manual smoke against live backend.
- Update `docs/implementation-status.md` checklist.
- Update CLAUDE.md "Current Session Notes" with what shipped.
- Close GitHub issue (if one is opened for this work).

## Repo conventions to follow

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before writing backend code.
- DDD layers (Domain → Application → Infrastructure → Interface). No shortcuts; full layers even for "simple" CRUD (per memory `feedback_ddd_discipline`).
- Railway pattern (`Result[T, DomainError]`).
- Workspace scoping on every read/write.
- No external product names in commits/docs (per memory `feedback_no_cdd_mentions`).
- Templates use proper form controls in admin UI, not JSON textareas (per memory `feedback_admin_ui_no_json`).
- No UUID inputs in UI (per memory `feedback_no_uuid_inputs`) — all selection by name/code.

## Entry point for next session

Read this doc + `application/screening/import_run_readouts.py` (CSV pattern to mirror) + `application/screening/plate_setup.py` (plate/well construction pattern). Then start S1.
