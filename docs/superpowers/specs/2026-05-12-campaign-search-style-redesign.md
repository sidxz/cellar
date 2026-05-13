# Screen-Campaign Search-Style Redesign — Design Spec

**Status:** Brainstorming approved 2026-05-12. Implementation plan via `writing-plans` next.
**Date:** 2026-05-12
**Branch:** `fe2`
**Bounded context:** `research_organization` (BC #05) — Campaign aggregate (FE only)
**Builds on:**
- `docs/superpowers/specs/2026-05-10-screen-campaign-design.md` (original lifecycle/contract)
- `docs/superpowers/specs/2026-05-11-screen-campaign-b-gaps-design.md` (B1/B5/B6/B7/B8 already shipped)

---

## 1. Purpose & framing

A `Campaign` is the screener's **final report** — the immutable artifact published to DAIKON. The lifecycle, persistence, and contract are done. The B-gap session ironed out audit defensibility (override reason, ND qualifier handling, multi-run import, thumbnails, chip filter). What's still wrong is the **shell**: a chemist looking at NadD-3 today sees a three-pane layout (compound list / pivot grid / decision panel) that fights for attention, hides the dose-response curve behind a row click, and surfaces sources as opaque badges (`NadD-Sumo-Col 31`).

The user's words: *"campaign is a snapshot of search results"*. The Search page is what the team already likes — single-column flow, uppercase section headers, `+Add` chip pills, an AG-Grid where each protocol becomes a column-group with `IC50 + IC50 Plot` rendered inline (Plotly). The redesign brings the Campaign UI under the same visual grammar.

### 1.1. Goals

- **G1.** Campaign page reads like a frozen Search page — same section headers, same grid layout, same DR-cell rendering, same "Customize Report" sheet.
- **G2.** Dose-response curve is inline in the grid, not hidden behind a row click.
- **G3.** Decision/override editing happens *in the row* (popover from chip, hover-edit on cell); the right-pane gets recovered as plain workspace.
- **G4.** Sources are readable rows (`Run · NadD-Sumo dose-response · 2026-05-07 · 31 compounds`), not UUID-derived badges. Add-compounds becomes a set of `+Add` pills in the SOURCES section — discoverable, mirrors Search's `+Add` pattern, no dropdown.
- **G5.** Closed/superseded campaigns use the same layout (controls disabled) — one mental model regardless of status.

### 1.2. Non-goals

- No backend redesign of the Campaign aggregate, channel resolver, or close flow. Contract is stable.
- No change to the close-and-sign flow (stub e-sig stays as-is until Sentinel re-auth lands).
- No change to the DAIKON published-JSON contract.
- No new Add-Compounds dialogs. We re-trigger the four existing ones (`AddFromCollection`, `AddFromCampaign`, `AddFromRuns`, Manual) via new entry points.
- No support yet for the `saved_search` source kind (still backlogged behind SavedSearch wiring).
- Workspace-wide campaigns list (B12 backlog item) is unchanged; this spec only touches per-campaign and per-project pages.

### 1.3. In-scope changes (summary)

| Layer | Change |
|---|---|
| FE: layout | `CampaignBuilder` → single-column flow (`Header → SOURCES → CHANNELS → Filter chips → Toolbar → Grid`). Closed view shares this layout, controls disabled. |
| FE: grid | `ResultsGrid` adopts the Search-style column architecture: pinned-left Molecule, optional property columns (toggleable), one column-group per channel with `Value + Plot` cells, pinned-right Decision (editable). |
| FE: DR inline | New batch DRC endpoint feeds `DoseResponseCell` rendering per row. Curves are pre-fetched, not lazily-fetched. |
| FE: decisions | Click on Decision chip → `DecisionPopover` (radio + reason + notes). Row-start chevron → `RowDetailDrawer` (full notes/rationale/audit fields). The standalone right-pane `DecisionPanel` is deleted. |
| FE: sources | New `SourcesSection` block — uppercase header, one readable row per source (with description), per-kind `+Add` pills (Run / Collection / Campaign / Manual). The existing dialogs are reused unchanged. |
| FE: channels | `ChannelStrip` → `ChannelsSection` — uppercase header, one detail row per channel (label, readout, hit threshold, selection rule), `+Add Channel` pill. Existing add/edit popover is reused. |
| FE: customize | Reuse the Search `ReportCustomizer` sheet. Campaign-specific knobs: show/hide property columns, show/hide Decision Reason / Notes / Override-status columns. |
| FE: deletions | `CompoundListPane` (~331 lines), `SourcesSummaryCard` (~132 lines), `DecisionPanel` (~289 lines) — removed. Their behavior is folded into the new layout. |
| FE: project scoping | Every entity picker (`+Add Collection`, `+Add Campaign`, `+Add Run` → protocol picker) wired to the campaign's `project_id`. Backend support already exists; this is pure FE prop-drilling. See §3.5. |
| BE: one new endpoint | `POST /api/v1/dose-response/curves:batch` returning DRC details for a list of curve IDs. Required to feed inline DR plots. |

---

## 2. Architecture overview

### 2.1. New FE file tree

```
frontend/src/features/screen-campaign/
  components/
    campaign-builder.tsx              REWRITE — single-column shell, dispatches to view-mode for closed
    campaign-view/index.tsx           REWRITE — share layout with builder, disable controls
    sections/
      header-strip.tsx                NEW    — name, status, channel/compound counts, primary actions
      sources-section.tsx             NEW    — uppercase header, source rows, +Add pills
      channels-section.tsx            NEW    — uppercase header, channel rows, +Add Channel pill
      campaign-toolbar.tsx            NEW    — Refresh / Preview / Customize Report / Export / Close & Sign
    grid/
      results-grid.tsx                REWRITE — Search-style column architecture, DR inline cell
      dose-response-cell.tsx          NEW    — campaign-specific wrapper that composes ActivityValue
      decision-chip-cell.tsx          NEW    — pinned-right cell; click opens DecisionPopover
      measurement-cell.tsx            NEW    — value + qualifier + hit chip + override badge + hover edit
    popovers/
      decision-popover.tsx            NEW    — radio + reason + notes (replaces DecisionPanel)
      row-detail-drawer.tsx           NEW    — chevron-expand drawer: full notes, rationale, audit fields
    add/
      add-compounds-pills.tsx         NEW    — the +Add chip set in SOURCES (wires existing dialogs)
    channel-popover.tsx               KEPT — already exists inside ChannelStrip; extracted as a component
    override-modal.tsx                KEPT — B8, unchanged
    create-campaign-dialog.tsx        KEPT
    add-from-collection-dialog.tsx    KEPT
    add-from-campaign-dialog.tsx      KEPT
    add-from-runs-dialog.tsx          KEPT
    close-sign-dialog.tsx             KEPT
    preview-as-published-dialog.tsx   KEPT
    supersede-dialog.tsx              KEPT
    campaign-list.tsx                 KEPT (per-project list page)
    campaign-status-chip.tsx          KEPT
    campaign-filter-bar.tsx           MINOR — re-style to Search section heading
  lib/
    hooks.ts                          PATCH — add `useCampaignCurves(campaign)` (batch fetch DRCs by id)
    api.ts                            PATCH — wrap new `POST /api/v1/dose-response/curves:batch`
    measurement-to-activity.ts        NEW    — pure mapper: CampaignMeasurement + DRC → ActivityValue
    report-config.ts                  NEW    — Zustand store; campaign-scoped report config (mirrors search)
  types/
    index.ts                          PATCH — re-export new ActivityValue mapper input types
  components/
    [DELETED] compound-list-pane.tsx       (~331 lines)
    [DELETED] sources-summary-card.tsx     (~132 lines)
    [DELETED] decision-panel.tsx           (~289 lines)
    [DELETED] channel-strip.tsx            (~620 lines) — replaced by channels-section.tsx + channel-popover.tsx
```

### 2.2. New BE endpoint

```
POST /api/v1/dose-response/curves:batch
Body: { curve_ids: [UUID, ...] }
Response: { curves: [ { id, run_id, molecule_id, curve_params: {...}, raw_data: [{x,y}, ...] }, ... ] }
```

- Auth: `require_viewer` (anyone who can read the campaign can read the curves it cites).
- Workspace-scoped (the existing curve repo already filters by workspace).
- Limit: 500 curve IDs per request. (A typical campaign has 1 channel × 30-100 compounds = 30-100 curves; this is comfortable headroom.)
- Lives in `interface/routes/dose_response_curves.py` (new file). Uses the existing `DoseResponseCurveRepository.find_by_ids` (add the method if it doesn't already exist; see §6.2).

No new application layer use case — this is a read query reusing the existing repo. A thin route is fine here (consistent with similar batch-fetch routes elsewhere in the project; see `MoleculeRepository.find_by_ids` usage in the FE today).

---

## 3. Layout — final composition

### 3.1. Overall structure

```
┌─ HeaderStrip ────────────────────────────────────────────────────────────────────┐
│  NadD-3   [Draft]   1 channel   31 compounds        [Refresh] [Preview] [Close & Sign] │
│  (description, muted, second line if present)                                        │
├─ SourcesSection ─────────────────────────────────────────────────────────────────┤
│  SOURCES                              [+ Run]  [+ Collection]  [+ Campaign]  [+ Manual] │
│  ⊕ Run · NadD-Sumo dose response · Run 2026-05-07 · 31 compounds              [×]    │
│  (one row per distinct compound_source entry; "×" removes that source's compounds)   │
├─ ChannelsSection ────────────────────────────────────────────────────────────────┤
│  CHANNELS                                                       [+ Channel]          │
│  ⊕ IC50  [DR]   hit if ≤ 100 μM   ·  latest approved run                      [⋯]   │
├─ FilterChipBar (B5, restyled) ──────────────────────────────────────────────────┤
│  Decision: Selected 1 · Deferred 30 · Rejected 0   |   Hit: Hit 24 · Non-hit 7      │
│                                                            Overridden 0  · Reset    │
├─ CampaignToolbar ────────────────────────────────────────────────────────────────┤
│  31 results               [Export ▾]   [Customize Report]   (compact, right-aligned) │
├─ ResultsGrid ────────────────────────────────────────────────────────────────────┤
│  ┌▾┬───┬─────────────┬──────┬─────────────────────────────────┬──────────────┐    │
│  │ │ ☐ │ Molecule    │ MW…  │ IC50            IC50 Plot       │ Decision     │    │
│  ├─┼───┼─────────────┼──────┼─────────────────────────────────┼──────────────┤    │
│  │▸│ ☐ │ ╱╲ CV-00777 │ 550.7│ 53.4 μM  hit    ▁▂▆█▇            │ [deferred ▾] │    │
│  │▸│ ☐ │ ╱╲ CV-00782 │ 401.3│  2.24 μM miss   ▁▁▁▃█            │ [selected ▾] │    │
│  │▸│ ☐ │ ╱╲ CV-00786 │ 612.1│ 240 μM   hit    ▁▁▃▆█  [OVR]    │ [deferred ▾] │    │
│  └─┴───┴─────────────┴──────┴─────────────────────────────────┴──────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

The `▸` glyph is the row-detail expand chevron — click expands `RowDetailDrawer` (full reason, full notes, override history, B6/B7/B8 audit fields, contributing-run IDs). The `OVR` chip in a measurement cell signals manual override; hover surfaces a pencil icon that opens the existing `OverrideModal`.

### 3.2. Visual primitives (reused from Search)

- **Section heading:** `text-sm font-semibold uppercase tracking-wide text-muted-foreground`
- **`+Add` pill:** `inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary` (hover → `bg-primary/20`)
- **Result count pill:** muted plain text, right-aligned in the toolbar
- **AG-Grid theme:** existing `chemVaultTheme` from `/shared/components/data-grid/ag-grid-theme.ts` — no changes
- **Status chip:** `<CampaignStatusChip>` — kept as-is
- **Decision chip cell:** keep the existing chip styling (selected = green, deferred = yellow, rejected = red); add a small caret `▾` to signal it's clickable; entire chip is a button trigger
- **Hit chip:** existing `HitCallChip` styling — kept

### 3.3. Decision popover (new — replaces DecisionPanel)

```
┌─ Decision ───────────────────┐
│ ( ) Selected                 │
│ (•) Deferred                 │
│ ( ) Rejected                 │
│                              │
│ Reason (optional)            │
│ ┌──────────────────────────┐ │
│ │                          │ │
│ └──────────────────────────┘ │
│ Notes                        │
│ ┌──────────────────────────┐ │
│ │                          │ │
│ └──────────────────────────┘ │
│              [Cancel] [Save] │
└──────────────────────────────┘
```

- Width: ~360px. Anchored to the decision chip with `align="end"`.
- **Save semantics** (single, consistent rule): typing fires a 300ms debounce that PATCHes silently. The explicit **Save** button does the same PATCH immediately (skips debounce) and closes the popover. **Cancel** discards local edits and closes. Closing the popover by clicking outside *commits* any dirty state — no data loss. (Same pattern as today's `DecisionPanel`.)
- Backend: `PATCH /api/v1/campaigns/{id}/results/{result_id}` with `{ decision, decision_reason, notes }`. The notes field is already wired through the command + use case + route + response (verified: `SetResultDecisionCommand.notes` with `UNSET` semantics, `SetResultDecisionRequest.notes`, `CampaignResultResponse.notes`, and three unit tests for set/clear/leave-unchanged). No backend change required for decisions.

### 3.4. Row-detail expansion (new)

Click the row chevron (`▸`) → the row expands *inline* (AG-Grid `getRowHeight` callback returns ~200px for expanded rows, ~48px otherwise). The expanded area uses a full-row cell renderer that spans all columns and shows:

- **Decision rationale** — full text of `decision_reason`, read-only here (edit happens in popover).
- **Notes** — full text of `notes`, read-only here.
- **Per-channel audit** — for each measurement, a compact table: value, qualifier, hit_call, source run snapshot, B6/B7/B8 audit fields (override_reason, test_concentration, replicate_count, qc_pass, contributing_run_ids).
- **Override history** — when `is_manual_override`, show original value + override value + reason + who-overrode (when name resolution lands).

State: `Set<resultId>` of expanded rows held in component state (not persisted). Keyboard: `Enter` on a focused row toggles expand; `Esc` collapses.

Implementation note: AG-Grid Community supports `getRowHeight(params)` + a `fullWidthCellRenderer` for the expanded portion. No Master/Detail (Enterprise) required.

### 3.5. Project-scoped pickers (mandatory)

Every entity picker in the Campaign UI **must** scope its listing to the campaign's `project_id`. This matches the Search UI convention (`useProtocolSummaries([projectId])`) and prevents chemists from accidentally picking resources that belong to a different project. Current state and required wiring:

| Picker | Where | Current state | Fix |
|---|---|---|---|
| Protocol picker (`+Add Channel`) | `ChannelStrip` / `channels-section.tsx` | Already project-scoped via `useProtocolSummaries([projectId])` | No change |
| Collection picker (`+Add Collection`) | `AddFromCollectionDialog` | Uses `useCollections()` — workspace-wide | Pass `projectId` → `useCollections([projectId])` |
| Campaign picker (`+Add Campaign`) | `AddFromCampaignDialog` | No project filter today | Swap to `useCampaignsByProject(projectId)` (already exists). Filter to `status ∈ {closed, draft}` of the *same* project. |
| Protocol picker (`+Add Run` step 1) | `AddFromRunsDialog` | Uses `useListProtocolsApiV1ProtocolsGet()` — workspace-wide | Swap to `useProtocolSummaries([projectId])` |
| Run picker (`+Add Run` step 1, after protocol picked) | `AddFromRunsDialog` | Implicitly scoped by selected protocol | No change (runs inherit scope from protocol) |
| Compound picker (`+Add Manual`) | manual add dialog | Workspace-wide compound search | **No change** — adding an existing-elsewhere compound to a project-specific campaign is a legitimate cross-project transfer (e.g., a hit found in NadD that screens well in another project). Keep it workspace-wide but display the compound's source project as a chip in the dialog when known. |

Backend already supports project filtering on all three list routes:
- `GET /api/v1/protocols/list-summaries?project_ids=…` — confirmed at `interface/routes/protocols.py:446`
- `GET /api/v1/collections?project_ids=…` — confirmed at `interface/routes/collections.py:124`
- `GET /api/v1/campaigns?project_id=…` — confirmed via `useCampaignsByProject`

So this is **FE-only wiring**. No new endpoints needed.

The `projectId` reaches every picker via prop drilling from `CampaignBuilder` / `CampaignView` (both already receive it). Add a `projectId: string` prop to `AddFromCollectionDialog`, `AddFromCampaignDialog`, `AddFromRunsDialog`, and the new `SourcesSection` that hosts the `+Add` pills. Each dialog passes the prop to its picker hook.

### 3.6. Customize-Report sheet (reused)

We reuse Search's `ReportCustomizer` shape (`Sheet`, right-side, 420px wide). Campaign-scoped knobs:

| Knob | Default | Effect |
|---|---|---|
| Properties (MW / LogP / HBD / HBA / TPSA) | off | Show as columns between Molecule and the first channel |
| Image size (small / medium / large) | small | Drives row height + thumbnail size |
| Show Decision Reason column | off | Adds a column between channels and Decision; chemist can scan reasons without expanding |
| Show Notes column | off | Adds a column after Decision Reason |
| Show Override-status column | off | Adds a column flagged when any cell is overridden |
| Plot scale | per_molecule | Same options as Search (per_molecule / min_max / protocol) |

State is per-campaign and persisted to `localStorage` keyed by `campaign:${campaignId}:report-config` — chemists tweak the view per campaign without affecting Search defaults.

---

## 4. Data flow

### 4.1. Page load

1. `useCampaign(campaignId)` — fetches `CampaignResponse` (channels + results with measurements).
2. `useMoleculesByIds(result.map(r => r.molecule_id))` — fetches structures.
3. **NEW** `useCampaignCurves(campaign)`:
   - Collects every `measurement.source_curve_id` that's non-null and whose channel `source_kind === "dose_response_curve"`.
   - Calls `POST /api/v1/dose-response/curves:batch` with the deduplicated list.
   - Returns `Map<curveId, DoseResponseCurve>`.
4. Grid rendering composes `ActivityValue` per cell via `measurementToActivity(measurement, curveMap)`.

If a cell's `source_kind === "readout_data"` (scalar, not DR), the cell shows only the value/qualifier/hit-chip — no plot. If a DR cell's `source_curve_id` is null (e.g., manual override of a DR channel), the cell shows the override value + `OVR` badge and no plot.

### 4.2. Decision change

1. Chemist clicks decision chip → `DecisionPopover` opens with current values pre-filled.
2. Form local state debounced at 300ms; on debounce or explicit Save, fire `PATCH /api/v1/campaigns/{id}/results/{result_id}` with `{ decision, decision_reason, notes }`.
3. On success, optimistic-update the campaign query cache.
4. Filter chip bar tallies recompute automatically (it's derived state, no separate query).

### 4.3. Override

Unchanged — `OverrideResultCell` use case + modal flow already shipped (B8). The trigger moves from "click the cell" to "click the pencil icon that appears on hover".

### 4.4. Add compounds

Each `+Add` pill (Run / Collection / Campaign / Manual) opens its existing dialog. No flow change — only the trigger UI changes. Hooks into the same mutations as today.

### 4.5. Close & Sign

Unchanged. Triggered from the header strip.

---

## 5. Closed / superseded campaigns

Same layout, all mutation controls disabled:

- HeaderStrip: hide Refresh, Preview-as-published, Close & Sign. Show Supersede (existing flow). Show signature info (closed_at, closed_by, signature_id).
- SourcesSection: rows are read-only (no `×` remove), `+Add` pills hidden.
- ChannelsSection: rows read-only, `+Add Channel` hidden.
- FilterChipBar: unchanged (read-only filtering is still useful).
- Toolbar: keep Export + Customize Report; hide Refresh. Add "Download Published JSON".
- Grid: pinned-right Decision becomes a read-only chip (no popover trigger). Measurement cells: no hover-edit. Row-detail drawer remains useful.

The DRC inline cells render identically; closed campaigns cite the same `source_curve_id`s.

---

## 6. Backend changes (minimal)

### 6.1. New route — batch DRC fetch

File: `backend/src/cellar/interface/routes/dose_response_curves.py` (new)

```python
@router.post("/curves:batch", response_model=BatchCurvesResponse, status_code=200)
async def get_curves_batch(
    request: BatchCurvesRequest,
    auth: AuthContext = Depends(require_viewer),
    repo: DoseResponseCurveRepository = Depends(...),
) -> BatchCurvesResponse:
    if len(request.curve_ids) > 500:
        raise HTTPException(400, "max 500 curve ids per request")
    curves = await repo.find_by_ids(request.curve_ids, workspace_id=auth.workspace_id)
    return BatchCurvesResponse(curves=[_serialize(c) for c in curves])
```

The serializer reuses the existing curve DTO shape used by `GET /api/v1/protocols/{protocol_id}/compounds/{molecule_id}/dose-response`.

### 6.2. Repo method

`DoseResponseCurveRepository.find_by_ids(ids: list[UUID], workspace_id: UUID) -> list[DoseResponseCurve]` — add if missing. SQL: `SELECT ... WHERE id = ANY(:ids) AND workspace_id = :workspace_id`. No additional indexing needed (PK is already indexed).

### 6.3. Nothing else changes

All other backend code is untouched. The CampaignResponse already exposes everything the new UI needs (per the earlier audit). The new `+Add` pills wire to existing endpoints (`add-from-runs`, `add-from-collection`, `add-from-campaign`, `results` for manual).

---

## 7. Migration order

A phased rollout keeps each PR reviewable:

1. **BE batch DRC endpoint** (1 PR). Add `POST /api/v1/dose-response/curves:batch`, `find_by_ids` repo method, integration test. Re-run orval on the FE. (Decision-notes wiring is already done — see §6.)
2. **FE: new sections, no grid changes yet** (1 PR). Build `HeaderStrip`, `SourcesSection`, `ChannelsSection`, `CampaignToolbar` as new files. Wire them into the existing `CampaignBuilder` *alongside* the existing 3-pane layout under a `?v2=1` query param (no feature-flag infra needed; this is dev-only and removed in Phase 4). The current builder layout stays default.
3. **FE: new grid + DR cell + popover/drawer** (1 PR). New `results-grid.tsx`, `measurement-cell.tsx`, `decision-chip-cell.tsx`, `dose-response-cell.tsx`, `decision-popover.tsx`, `row-detail-drawer.tsx`. Still hidden behind the `?v2` switch.
4. **FE: switch default, delete the old shell** (1 PR). `CampaignBuilder` and `CampaignView` use the new layout unconditionally. Delete `CompoundListPane`, `SourcesSummaryCard`, `DecisionPanel`, `ChannelStrip`. Update tests. Update CLAUDE.md "Current Session Notes".
5. **FE: customize-report sheet + property columns + project-scoped pickers** (1 PR). Add the report-customizer wired to a campaign-scoped Zustand store. Wire optional property columns + Decision-Reason / Notes / Override-status toggles. Fix the project-scoping wiring in the three add-dialogs per §3.5 in the same PR (small, related, easy to review together).
6. **Playwright smoke** (1 PR). Land the `screen-campaign.spec.ts` (currently a `.TODO` stub) covering: create campaign → add from runs → set decisions inline → close & sign. Hooks into the existing test infra.

Each PR is independently revertable. Phase 1 and Phase 6 are mandatory bookends; Phases 2-5 carry the user-visible work.

---

## 8. Open follow-ups (carried over)

These pre-existed before the redesign and must be respected by it (not new work):

1. **Stub e-signature** — `signature_id` is caller-supplied today. Redesign doesn't fix this; flagged for a future Sentinel re-auth integration.
2. **`closed_by.name` / `signature.signed_at` resolution** — `GetPublishedCampaign` still has TODOs for Sentinel user-name lookup and audit signature-row lookup. Redesign reads what's available; missing fields render as muted placeholders.
3. **`SavedSearchSource`** — still rejected at the backend; redesign hides the SavedSearch source kind from the SOURCES `+Add` pill set (matches the disabled state in the current `CompoundListPane` dropdown).
4. **`GetPublishedCampaign` viewer guard** — still uses `require_editor`. Out of scope here.
5. **B6 selection-rule DRY** — `_apply_selection_rule` lives in `preview_run_import.py`; extract to a shared helper. Out of scope (a backlog-T-item from the prior session).
6. **Latent unique-constraint pattern fix** in `RefreshFromSources`, `RecomputeChannel`, `UpdateCampaignChannel`. Mentioned in CLAUDE.md handoff; not triggered by the redesign but should be picked up in a follow-up backend session.

---

## 9. Test plan

### 9.1. Backend
- `POST /api/v1/dose-response/curves:batch` — unit on repo `find_by_ids`, API test for happy path, workspace isolation, 400 on >500 ids, empty list returns empty array.

### 9.2. Frontend
- `pnpm tsc --noEmit` must pass after each FE PR.
- New components have minimal RTL unit tests where logic is non-trivial (`measurementToActivity` is pure → test it; `DecisionPopover` debounce + autosave; `RowDetailDrawer` audit-field rendering).
- Manual browser smoke checklist:
  1. Create a draft campaign, add channel via `+Add Channel`, add compounds via `+Add Run`.
  2. Verify DR plots render inline for each row; verify scalar (non-DR) cells show `—` for plot.
  3. Click decision chip → set Selected with reason and notes → confirm chip re-colors and tally updates.
  4. Click row chevron → drawer expands, shows audit fields, override history.
  5. Hover over a cell → pencil appears → click → override modal → set value + reason → confirm `OVR` badge appears + plot disappears (override).
  6. Open Customize Report → toggle MW + LogP + Decision Reason column → confirm columns appear.
  7. Click `Filter chips` (Selected / Deferred / Hit / Non-hit / Overridden) → grid filters live.
  8. Close & Sign → confirm transition to closed view → confirm all mutation controls disabled but DR plots / filter still work.
  9. Open Preview-as-published → JSON matches the closed campaign's published shape.

### 9.3. Playwright
The end-to-end spec lands in Phase 6. Covers the happy-path workflow (steps 1-3 above) headlessly.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Pre-fetching DRCs balloons payload for large campaigns | 500-id cap on batch endpoint; deduplicate before fetch (most channels share curves across many results). Typical case: 1 channel × 100 compounds = 100 curves × ~10 dose points = ~10KB per curve = ~1MB total. Acceptable. If a campaign approaches the cap, chunk the request and merge in `useCampaignCurves`. |
| Decision popover loses focus on autosave | Match the current `DecisionPanel` pattern — autosave does not unmount the form, so focus is retained. Tested in B8 already. |
| Row-detail expansion + AG-Grid interaction (expand changes row height) | Standard Community-edition pattern: `getRowHeight(params)` returns variable height per row based on an `expandedIds` set; `fullWidthCellRenderer` paints the expanded content. The search grid uses fixed row heights, so this is new ground in this repo — first-of-its-kind use of AG-Grid `getRowHeight`. Risk that a row's height change can cause grid jank when many rows toggle in quick succession; mitigation: `api.resetRowHeights()` after each toggle, and disable expand-all bulk actions. |
| Customize-Report state pollution across campaigns | Scope the Zustand store by `campaignId`; persist to `localStorage` with campaign-keyed bucket. |
| Closed campaigns still cite curves the user is allowed to read | Confirmed: workspace-scoped repo + same auth model. Closed campaigns can't grow new curves, so the batch fetch returns a stable set. |

---

## 11. Out-of-scope but considered

- **Unified Add-Compounds wizard** — instead of four separate dialogs, one wizard with Source-Kind → Source-Picker → Channel-Config → Preview-Commit steps. *Decision: not now.* Each existing dialog is well-tuned to its kind (AddFromRuns has channel config that none of the others need; AddFromCampaign has a decision filter; AddFromCollection is a flat picker). A wizard would force the lowest common denominator. The `+Add` pill discoverability fix is enough.
- **Bulk decision setter** (B3 backlog) — set decision on a multi-row selection. Plays well with the redesign but is its own UX; deferred.
- **Bulk remove** (B4) — same shape as bulk decision.
- **CSV export** (B9) — Search has CSV export via the export-toolbar; the redesign's toolbar exposes Export, so this can be wired with minimal work *if* the campaign-export backend route exists. Out of scope for this spec but trivially additive in a follow-up.
- **Per-row audit history view** (B13) — covered partially by the row-detail drawer's "Override history" block. A separate audit-log view (cross-row, time-ordered) is its own feature.
- **Workspace-wide campaigns list** (B12) — separate page; this spec only redesigns per-campaign and per-project views.

---

## 12. Hand-off

After spec approval:
1. Invoke `superpowers:writing-plans` to generate a per-phase implementation plan.
2. Plan defines tasks for each PR in §7. Each task identifies the files touched, the test deltas, and the verification command.
3. Execution mode: subagent-driven (one implementer + spec reviewer + quality reviewer per task), matching the Phase-5 pattern.
4. Branch stays `fe2`; merge to `main` after the full Playwright smoke completes in Phase 6.
