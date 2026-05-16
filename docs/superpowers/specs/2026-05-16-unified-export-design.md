# Unified Export — Always-Async, Per-Format Renderers, Search as First Consumer

**Date:** 2026-05-16
**Status:** Approved (design)
**Scope:** Cross-cutting — `search` is the first consumer; the shared module is built to serve every future "export this filtered list" surface (runs, batches, activity, ELN entries, etc.)

---

## Problem

The chemist on `/search` clicks **Export → Excel** expecting the 5,432-row result set. They get the 200 rows the AG Grid happened to have loaded. The same is true on every grid in the app — today's `ExportToolbar` is FE-only and walks `forEachNodeAfterFilterAndSort`, which only sees rows already in `rowData[]`.

Other gaps:

- **Excel** ships as `exceljs` strings — numbers lose their numeric type, no formulas survive, no embedded sparklines despite `excelEnhancer` being a defined extension point with zero consumers.
- **CSV** is AG Grid's built-in `exportDataAsCsv` over the visible cells, so a chemist re-importing the file sees `"value · unit · ₃ · ⚠"` in cells — display strings, not data.
- **SDF** routes through `POST /api/v1/molecules/export/sdf` which takes a list of UUIDs (10,000-cap), no activity data on the MOL data tags. The FE has to materialize every result row's id before asking, which it can't do today.
- **PDF** does not exist anywhere.
- **No async story.** A 50,000-mol substructure × 5-protocol export blocks a FastAPI worker for minutes and dies if the browser tab closes.
- **No DRY abstraction.** Every grid that wires `<DataGrid exportFilename>` inherits the FE-only model; SDF gets bolted on per-feature via `extraExportItems`.

## Goals

1. **Export every result the query produces, not just the loaded page** — across every format.
2. **One shared backend module + one shared frontend hook** — set up `/search` as the template so every other module (runs grid, batches grid, activity tabs, ELN) gets the same wire shape, the same job UX, and the same audit trail later.
3. **Four formats with honest semantics:**
   - **CSV** — strictly tabular, machine-friendly (raw numbers, qualifier in a sibling column, ND when inactive).
   - **SDF** — strictly chemistry-payload (MOL block + identity tags + per-activity data tags).
   - **XLSX** — true numeric cells (Excel formulas work) + embedded sparkline PNGs per DR cell + freeze panes + CurveClass in a sibling cell so sort works.
   - **PDF** — presentation-tight, closer to what the UI shows: page header with query summary + aggregation chip, per-protocol column groups, SVG sparklines, footer with timestamp / workspace / page N of M.
4. **Async by default**, surviving browser tab close, with a tray of recent exports.

---

## Decisions locked before tasks

These were brainstormed and accepted in the prior turn. They are inputs to the plan, not open questions.

| # | Decision | Rationale |
|---|---|---|
| D1 | **Always-async via Temporal**, no sync route. Tiny exports still *feel* sync because the first 500 ms poll already returns `ready`. | One codepath, one FE hook, one audit trail. Temporal is already running for bulk_reg / CDD imports. |
| D2 | **WeasyPrint + Jinja** for PDF. Pure-Python, no browser binary in the worker. | Avoids the Chrome-in-container surface; "looks like the UI" is approximated by templating, not pixel-copied. |
| D3 | **XLSX embeds PNG sparklines up to 5,000 rows; numeric-only above.** Renderer emits a one-line header note when the cap trips. | 5,000 PNG-embedded rows is ~15–30 MB; above that Excel chokes. Honest fallback beats a 300 MB file. |
| D4 | **Initial scope = `/search` only.** Build the shared module against one consumer; port runs / batches / activity in follow-ups. | Lower risk, faster ship. The abstraction earns its keep only after a second consumer; we accept one rework round. |
| D5 | **Persisted `ExportJob` aggregate** (status, format, query_snapshot, file_key, row_count, requested_by, requested_at, completed_at, expires_at). | Audit trail for regulated data, "my recent exports" tray, re-download after browser close. Matches the 21 CFR Part 11 stance already in CLAUDE.md. |
| D6 | **fsspec** for file storage, same client as attachments (`./data/attachments` today; S3/MinIO swap is a config flip). Files keyed `exports/{workspace_id}/{job_id}.{ext}`. | Reuses the existing storage layer; no new infra. |
| D7 | **Job TTL = 7 days.** A nightly purge activity drops expired files + flips job status to `expired`. | Bounds storage. Re-download window matches what chemists typically need; long-term retention is the source-of-truth's job (the saved-search, the protocol). |
| D8 | **Re-runs the query**, doesn't snapshot it. The job stores the query payload; the workflow walks pages at execution time using the same `ExecuteSearch` use case. | Honest to the data at export time. If a chemist edits a saved search between request and execution, the user sees the new query in the audit trail. |
| D9 | **Streaming inside the worker** — renderer writes batch-by-batch to a tempfile, then fsspec uploads the finished file. Never holds the whole result set in memory. | Bounded memory regardless of row count. |
| D10 | **One toast UX**, no inline blocking dialog. Toast shows progress; auto-triggers `<a download>` when ready; gives a re-download link until it disappears. | Matches the always-async model; lets chemists kick off multiple exports without page lock. |

---

## Architecture

### Backend layout (new)

```
backend/src/cellar/
  domain/export/
    __init__.py
    enums.py                   # ExportFormat (CSV|SDF|XLSX|PDF), ExportStatus
    export_job.py              # ExportJob aggregate
    repository.py              # ExportJobRepository protocol
    
  application/export/
    __init__.py
    start_export.py            # use case: validate → persist job(pending) → dispatch
    get_export_status.py       # use case: poll endpoint payload
    cancel_export.py
    list_exports.py            # "my recent exports" tray
    purge_expired_exports.py   # scheduled cleanup
    
    row_streams/
      base.py                  # RowStream protocol — async iterator of ExportRow + ColumnSpec[]
      search_results.py        # SearchResultsRowStream
    
    renderers/
      base.py                  # ExportRenderer protocol — write(row_stream, out_path, opts)
      csv_renderer.py
      sdf_renderer.py
      excel_renderer.py
      pdf_renderer.py
    
    orchestration/
      export_orchestrator.py   # Protocol: start(job_id, payload) → workflow_id

  infrastructure/
    persistence/sqlalchemy/export/
      export_job_model.py
      export_job_repository.py
    temporal/
      workflows/export.py
      activities/export.py
      orchestrators/export.py

  interface/routes/export.py     # (extend the existing file)
    POST   /api/v1/exports                 → {job_id}
    GET    /api/v1/exports/{id}            → {status, progress, row_count, error?, download_url?}
    GET    /api/v1/exports/{id}/download   → Response with file bytes (or 302 to signed URL)
    POST   /api/v1/exports/{id}/cancel
    GET    /api/v1/exports                 → list (paginated, my-workspace)

  alembic/versions/036_export_jobs.py
```

### Frontend layout (new + modified)

```
frontend/src/shared/components/export/
  export-toolbar.tsx           # NEW — replaces today's data-grid/export-toolbar.tsx
  export-job-toast.tsx         # NEW — Sonner toast with progress + cancel + re-download
  use-export.ts                # NEW — POST /exports → poll → trigger download
  types.ts                     # ExportRequest, ExportJob, ExportFormat
  
frontend/src/shared/components/data-grid/data-grid.tsx
  - Accepts a `buildExportRequest(format) => ExportRequest` prop in place of today's
    `exportFilename` + `excelEnhancer` + `extraExportItems`. The data-grid
    no longer renders the FE-side ExportToolbar; consumers wire the new
    shared one if they want export.
  - Old `excelEnhancer` typedef stays as a deprecated re-export with a
    comment pointing at the new approach (one cleanup commit after porting).
    
frontend/src/features/research-organization/components/search-page.tsx
  - Calls the new ExportToolbar with a buildRequest that bundles the
    current query, protocol_columns, aggregation, reportConfig — same
    shape the search execute already takes, plus the format and any
    format-specific options.
```

### Wire shape

```ts
// FE → BE
POST /api/v1/exports
{
  source: "search",                            // discriminator for row_stream selection
  format: "xlsx" | "csv" | "sdf" | "pdf",
  filename_hint: "cellar-search-2026-05-16",   // BE picks the extension
  options: {                                   // per-format knobs
    image_size: "small" | "medium" | "large",  // XLSX/PDF: sparkline size
    include_sparklines: true,                  // XLSX/PDF: chemist override
  },
  payload: {
    // SearchResultsRowStream interprets this shape exactly like ExecuteSearch:
    query: { … } | null,
    saved_search_id: uuid | null,
    protocol_columns: ["drc:<rd_id>", "rd:<proto>:<rd>:percent_inhibition", …],
    aggregation: "latest_approved_run" | "geometric_mean" | "mean" | "best_r_squared",
    project_ids: [uuid, …] | null,
    sort_by: "registration_number" | …,
    sort_dir: "asc" | "desc",
  },
}
→ 202 { job_id: uuid }

GET /api/v1/exports/{id}
→ 200 {
  id: uuid,
  status: "pending" | "running" | "ready" | "failed" | "cancelled" | "expired",
  format: "xlsx",
  row_count: int | null,                       // null while still counting
  progress: float | null,                      // 0.0–1.0; null until counting finishes
  error: string | null,
  download_url: string | null,                 // populated when status=ready
  byte_size: int | null,
  requested_at: iso8601,
  completed_at: iso8601 | null,
  expires_at: iso8601 | null,
}
```

### Async flow

```
1. POST /api/v1/exports
   ↓ application.export.start_export
     - validate payload (workspace match, format known, aggregation enum)
     - persist ExportJob(status=pending, query_snapshot=payload)
     - dispatch ExportWorkflow(job_id) via TemporalExportOrchestrator
     - return { job_id }

2. FE: useExport() shows Sonner toast "Exporting (queued)..." with spinner + Cancel
   - polls GET /api/v1/exports/{id} every 500 ms for the first 3 s, then 2 s

3. ExportWorkflow (Temporal):
   a. activity: mark_running                                           → status=running
   b. activity: count_rows(query)                                      → job.row_count
   c. activity loop: for batch in row_stream(query, batch_size=500):
        renderer.write_batch(batch, tempfile)
        update job.progress = rows_done / row_count
      (continue_as_new every 50 batches for huge jobs)
   d. activity: finalize(tempfile)
        - fsspec.upload(key=exports/{ws}/{job_id}.{ext})
        - mark_ready(byte_size, content_type, expires_at=now+7d)

4. GET /api/v1/exports/{id} → {status: "ready", download_url: "/api/v1/exports/{id}/download"}
   FE auto-creates <a href download> and triggers click; toast switches to
   "Exported (5.4 MB) — Re-download" and lingers ~30 s.

5. (Nightly) PurgeExpiredExports activity scans jobs where expires_at < now
   and status == "ready"; fsspec.delete + flip status to "expired".
```

**Cancel:** `POST /api/v1/exports/{id}/cancel` sets job to `cancel_requested`; the workflow's loop checks each iteration. fsspec is told to delete the partial tempfile. Cancellation is best-effort — a job between activities will finish that activity first.

### Sync-feeling path

There is no sync route. For tiny jobs the workflow simply completes inside the first poll window:

- 50-row CSV: count + render finishes in <200 ms; first poll at 500 ms returns `ready`.
- Chemist sees the toast flip to "done" before they look away.

This keeps the codepath count to one and makes the audit trail uniform.

---

## Per-format contracts

### CSV (`csv_renderer.py`)

Stdlib `csv.writer`, write-only stream. **One column per data field, no display strings.**

Columns (search source):
```
registration_number, name, smiles, inchi_key, molecular_formula,
molecular_weight, logp, hbd, hba, tpsa,
<for each protocol column>:
  "<Protocol>::<Readout>::<Intercept>::value",         # e.g. "Mtb_WCA::EC50::value"
  "<Protocol>::<Readout>::<Intercept>::qualifier",     # "=", ">", "<", or "ND"
  "<Protocol>::<Readout>::<Intercept>::unit",          # "µM"
  "<Protocol>::<Readout>::<Intercept>::run_count",     # n (1 if no multi-run aggregation)
  "<Protocol>::<Readout>::<Intercept>::curve_class",   # "active" | "inactive" | …
```

Inactive curves emit `qualifier=ND`, `value=` (empty). At-bound curves emit `qualifier=>`, `value=<max_dose>`. This matches the wire-level `_resolve_intercept` BE helper exactly (`channel_resolution.py`).

### SDF (`sdf_renderer.py`)

RDKit `SDWriter` over an open file handle. Reuses the existing `ExportMoleculesSDF.smiles_to_mol_block` path. **Per-activity data tags** added beside identity tags:

```
> <Registration_Number>
CV-00982

> <Name>
…

> <Molecular_Weight>
421.50

> <Mtb_WCA::EC50::value>
1.23

> <Mtb_WCA::EC50::qualifier>
=

> <Mtb_WCA::EC50::unit>
µM

> <Mtb_WCA::EC50::curve_class>
active

> <Mtb_WCA::EC90::value>


> <Mtb_WCA::EC90::qualifier>
ND
```

Undisclosed molecules without SMILES skipped (today's behavior). The existing 10K cap is removed — async pagination makes it unnecessary.

### XLSX (`excel_renderer.py`)

`openpyxl` in `write_only` mode (constant-memory). Two sheets:

- **`Data`** — the export rows.
  - Header row: bold, frozen.
  - First column (`registration_number`) pinned-frozen.
  - Numeric values stored as Excel numbers (`cell.value = 1.23`, not `"1.23"`), unit in a separate column so formulas work.
  - DR intercept cells: numeric, with **sibling columns** for `qualifier` and `curve_class` (so sort + filter behave). Inactive cells empty; qualifier column carries `ND`.
  - **Sparkline column per readout-def** (one column per DR readout, NOT one per intercept — same as the grid). For row count ≤ 5,000: matplotlib renders a 240×120 PNG from `curve_snapshot` and inserts it via `openpyxl.drawing.image.Image`. Above 5,000: column is omitted with a single-line note appended to a `Notes` sheet.
- **`Notes`** — query summary, aggregation mode, row count, generated_at, omissions ("Sparklines omitted: row count 12,847 exceeds 5,000 cap").

Matplotlib rendering uses the snapshot shape already shipped in commits `5e182dbc` / `e16285a1` / `3498a293` — there's a single `_build_curve_snapshot` shared module the renderer imports.

### PDF (`pdf_renderer.py`)

WeasyPrint with a Jinja2 template (`backend/src/cellar/application/export/renderers/pdf_template/`):

```
pdf_template/
  search_report.html.j2     # landscape, A4
  search_report.css         # print-targeted CSS, page sizes, header/footer
  partials/
    cell_dr.html.j2         # DR cell — value + unit + class chip + SVG sparkline
    cell_scalar.html.j2     # plain readout
    header.html.j2          # query summary + aggregation chip + project chips
    footer.html.j2          # workspace · timestamp · "Page X of Y"
```

Sparklines: matplotlib SVG backend renders one SVG per DR cell from `curve_snapshot`, inlined directly into the HTML. WeasyPrint embeds SVGs natively.

Page break strategy: `page-break-inside: avoid` on each `<tr>`, so molecules don't split across pages. Header repeats per page via `position: running(header)` + `@top-center`.

PDFs are inherently lossy at huge row counts. Renderer warns above 1,000 rows ("PDF best for ≤ 1,000 rows — XLSX is recommended for 5,432-row exports") but proceeds. Above 5,000: refuses with a 422 from the start_export use case.

---

## Domain model: `ExportJob`

```python
# domain/export/export_job.py

@dataclass
class ExportJob:
    id: UUID
    workspace_id: UUID
    requested_by: UUID
    source: str                           # "search" | (future) "runs", "batches", …
    format: ExportFormat                  # CSV | SDF | XLSX | PDF
    query_snapshot: dict                  # full payload from the POST
    status: ExportStatus                  # PENDING | RUNNING | READY | FAILED | CANCELLED | EXPIRED
    row_count: int | None
    progress: float | None                # 0.0–1.0
    file_key: str | None                  # fsspec key once finalized
    byte_size: int | None
    content_type: str | None
    filename: str | None                  # what we send in Content-Disposition
    error_message: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None           # null until READY
    version: int                          # optimistic concurrency

    def mark_running(self) -> None: …
    def set_row_count(self, n: int) -> None: …
    def report_progress(self, p: float) -> None: …
    def mark_ready(self, file_key: str, byte_size: int,
                   content_type: str, expires_at: datetime) -> None: …
    def mark_failed(self, error: str) -> None: …
    def request_cancel(self) -> None: …
    def mark_cancelled(self) -> None: …
    def mark_expired(self) -> None: …
```

`query_snapshot` is the full wire payload (without auth context). It's the audit-trail evidence of what was asked. The workflow re-runs it; if the saved-search has changed since, the audit trail still shows the snapshot used.

### Migration `036_export_jobs.py`

```
export_jobs (
  id UUID PK,
  workspace_id UUID NOT NULL,
  requested_by UUID NOT NULL,
  source TEXT NOT NULL,
  format TEXT NOT NULL,
  query_snapshot JSONB NOT NULL,
  status TEXT NOT NULL,
  row_count INTEGER,
  progress REAL,
  file_key TEXT,
  byte_size BIGINT,
  content_type TEXT,
  filename TEXT,
  error_message TEXT,
  requested_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  version INTEGER NOT NULL DEFAULT 0
)
INDEX (workspace_id, requested_at DESC)
INDEX (status, expires_at)            -- for the purge sweep
```

---

## Row-stream protocol

```python
# application/export/row_streams/base.py

@dataclass(frozen=True)
class ColumnSpec:
    key: str                # stable identifier — e.g. "molecular_weight" or "drc:<rd_id>:ec:50:value"
    header: str             # human-readable header — "MW" / "Mtb_WCA::EC50"
    kind: Literal["text", "number", "smiles", "image_curve", "qualifier"]
    unit: str | None = None
    group: str | None = None  # e.g. protocol name — used by XLSX for header banding, PDF for column groups

@dataclass(frozen=True)
class ExportRow:
    cells: dict[str, Any]   # key → value matching ColumnSpec.kind
    raw: dict[str, Any]     # full enriched-molecule payload — renderers reach into for sparkline data

class RowStream(Protocol):
    columns: list[ColumnSpec]
    async def total_count(self) -> int: ...
    async def iter_rows(self, batch_size: int) -> AsyncIterator[list[ExportRow]]: ...
```

`SearchResultsRowStream` builds its `ColumnSpec[]` from the protocol_columns list + the search molecule descriptors block. Yields enriched molecules in batches by calling `ExecuteSearch` with a fresh cursor each loop. The same `protocol_columns` token shapes the column count, so a row's cell-dict keys line up with `ColumnSpec.key`.

---

## Failure modes

| Failure | Behavior |
|---|---|
| Workflow worker crashes mid-batch | Temporal retries the activity (idempotent via tempfile path keyed on job_id + batch_index). Job status stays `running`. |
| Worker keeps crashing | After 3 retries activity fails → workflow catches → `mark_failed(error)`. FE toast shows error and a "View details" link to the (future) exports tray. |
| User closes browser | Workflow keeps running. Job lands in `ready` with a download URL — chemist can re-download from the (future) exports tray. |
| FE poll fails (network hiccup) | `useExport` retries with exponential backoff; toast says "Reconnecting…". |
| File expired (re-download attempted after 7 d) | Download endpoint returns 410 Gone with `"Export expired — re-export the same query"`. |
| Cancel mid-stream | Workflow's loop checks `is_cancel_requested` between batches; deletes tempfile; marks `cancelled`. |
| Storage full | `fsspec.upload` raises → workflow catches → `mark_failed`. |

---

## Out of scope (deferred)

- **Recent-exports tray UI** — the `GET /api/v1/exports` endpoint ships; the tray is a follow-up.
- **Porting runs / batches / activity / collection / ELN grids** — each becomes its own follow-up issue once the shared module proves out on search.
- **S3 / MinIO** — fsspec already abstracts it; the swap is a config flip done when storage volume warrants.
- **Email-on-complete** — a chemist who closes the tab today loses the toast; the recent-exports tray (above) is enough until email/notification UX exists.
- **Per-format permissions** — every viewer can export every format today. Locking down (e.g. SDF restricted) is a future workspace-config item.
- **Sentry-style metric on export duration** — falls out of the existing structlog observability stack later; not needed for v1.

---

## Open questions surfaced during design

None — all four decision forks were resolved (D1–D4). One follow-up worth noting:

- **PDF page layout taste** is the highest-risk item. Recommend a brief side-loop with one chemist on a real 100-row export PDF before declaring the renderer done. The renderer's contract is stable; the Jinja template will iterate.

---

## Diagnostic anchors (for the implementer)

- `frontend/src/shared/components/data-grid/export-toolbar.tsx` — today's FE-only model. The replacement lives at `frontend/src/shared/components/export/export-toolbar.tsx` and the data-grid stops rendering it.
- `frontend/src/features/research-organization/components/search-page.tsx::handleExportSdf` — old codepath. Removed when the new toolbar lands; the new toolbar consumes the same `currentQuery` + `protocolColumns` + `aggregationMode` already in scope.
- `backend/src/cellar/application/research_organization/execute_search.py` — `ExecuteSearch` is invoked from inside `SearchResultsRowStream.iter_rows`. No change to the use case itself; the row stream just sets `limit=500` and walks `next_cursor`.
- `backend/src/cellar/application/screening/curve_snapshot.py` — already-shared snapshot builder. Both XLSX and PDF renderers read snapshots through this module's shape.
- `backend/src/cellar/infrastructure/temporal/orchestrators/bulk_registration.py` — template for `TemporalExportOrchestrator`. Same `start` / `get_progress` shape; same NullExportOrchestrator stub for Temporal-down deployments (returns `WorkflowOrchestratorUnavailable`, which `start_export` translates to a 503).
- `backend/src/cellar/infrastructure/storage/fsspec_client.py` — reused as-is. New key prefix `exports/{workspace_id}/`.
- `backend/src/cellar/interface/routes/export.py` — extended in place (rather than a new file), so the existing `POST /api/v1/molecules/export/sdf` route can be deprecated in favor of the unified `POST /api/v1/exports` once the FE migration lands. Keep the legacy route returning a 410 + pointer for one release.
