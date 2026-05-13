# Screen Campaign — pending follow-ups

**Branch:** `fe2`
**Status as of 2026-05-11 EOD:** Phases 1–10 + per-result-attribution refactor shipped. Build green, 2058 unit tests + 180 API tests + integration tests pass. The list below is everything still owed.

**Reference docs:**
- Spec: `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`
- Plan: `docs/superpowers/plans/2026-05-10-screen-campaign.md`
- Most recent handoff: CLAUDE.md "Current Session Notes" block

**Pick up in a fresh session by:**
1. Reading this file + the CLAUDE.md handoff.
2. Choosing items by priority below — they're independent unless noted.

---

## 2026-05-11 PM — Deeper gap analysis vs. stated intent

A second pass against the stated intent ("snapshot for DAIKON publication; screener freedom till close & sign-off") surfaced gaps not in the original H/M/L list. **Use this section as the current priority view;** the older H/M/L list below remains for reference.

### A — Blockers to "publishing final results for DAIKON"

- **A1. Real e-signature** (= M6). `crypto.randomUUID()` stub in `close-sign-dialog.tsx:79`. Without a real re-auth → signature, the "signed off" artifact has no provenance — 21 CFR Part 11 non-compliant.
- **A2. `closed_by.name` + `signature.signed_at` resolution** (= L1+L2). Published JSON emits `null` for both today. These are *exactly* the audit fields DAIKON consumers need.
- **A3. DAIKON transport / discovery** *(NEW)*. No webhook, no `/campaigns?status=closed` index, no explicit "publish" action. Pull-based DAIKON has nothing to discover; push-based has nowhere to push. Decide and build.
- **A4. PATCH-after-close 423 test** (= H3). Currently asserts 404 against a fake UUID. Immutability proof missing.
- **A5. `AddResultsFromSavedSearch`** (= H1). Backend file doesn't exist; FE dropdown disabled. User framed campaigns as "snapshot of a saved search" — natural seed path is missing.

### B — Screener UX (the "UI is crude" complaint) ← **next-session focus**

- **B1. Structure thumbnails in grid** (= M3). Chemists work by sight, not by reg-id.
- **B2. Dose-response curve preview** *(NEW)*. Cells from `dose_response_curve` channels should open the curve inline (or in a popover). Reuse existing curve renderer.
- **B3. Bulk decision** *(NEW)*. Multi-select rows → set decision + reason. New endpoint + UI.
- **B4. Bulk remove rows** (= M2).
- **B5. Decision-count chip filter row** *(NEW)*. Chips at top of grid: `Selected (12) / Deferred (88) / Rejected (4)`; click to filter the grid.
- **B6. Run import bridge + multi-run + hit-criteria preview** *(EXPANDED from H2)*. New requirements this session:
  - Picker supports **one OR many runs** (multi-select).
  - Default filter = each run's protocol `hit_criterion` (presented, editable per channel/readout).
  - Override hit-criteria, then **preview** which compounds would be added (and which would be hit-flagged) before committing.
  - DRY: reuse existing `HitCriterion.evaluate` + dose-response fit machinery. No new hit-calling logic.
- **B7. Override-cell ND/excluded gating** (= M4). Backend requires non-empty unit for ND today.
- **B8. Override reason field** *(NEW)*. `OverrideCellRequest` carries no rationale — audit-relevant.
- **B9. CSV/Excel export of draft grid** *(NEW)*. AG Grid Community supports it; wire it.
- **B10. Refresh-from-sources staleness signal** *(NEW)*. Badge/banner when a source Run was unlocked + re-fitted after the last refresh.
- **B11. Sources summary card on drafts** (= L8). Card reads `compound_sources` which is server-derived only on published view.
- **B12. Workspace-wide campaign list** (= M1). Per-project entry only today.
- **B13. Per-row decision audit history** *(NEW)*. Audit context records it; UI never surfaces it.

### C — Snapshot-integrity verifications (correctness, unproven)

- **C1. Molecule-merge behavior on closed campaign** *(NEW)*. Spec says draft rewires, closed doesn't. No integration test proving it.
- **C2. Admin cascade-delete of Run vs `source_run_id`** *(NEW)*. If a Run is hard-deleted, does the FK cascade into `campaign_measurement` and corrupt the snapshot? Verify FK ON DELETE.
- **C3. Latent unique-constraint fix verification**. Memory says commit `80e9ebed` applied measurement-id preservation to `RefreshFromSources` / `RecomputeChannel` / `UpdateCampaignChannel`. Confirm in code; add real-DB integration tests.
- **C4. `source_protocols` snapshot on supersede target** *(NEW)*. Verify the new campaign's snapshot is computed independently at close, not shared with the superseded one.

### D — Plumbing / type safety
- D1-D7 captured below (orval-zod, Playwright, browser smoke, viewer guard, RecomputeChannel route, Alembic drift, find_by_ids).

### E — Conceptual gaps the spec didn't address
- **E1. Operational meaning of "published"** — closed=published-automatically or separate publish action?
- **E2. Compare campaign vs supersede target** *(NEW)* — "what changed between v1 and v2"; supersede is a graveyard without it.
- **E3. Channel-set templates** *(NEW)* — "the standard kinase panel"; spec §11 lists post-v1.
- **E4. Replicate drill-in per cell** *(NEW)* — `mean_across_runs` collapses to one cell; no UI to see contributors.
- **E5. ELN linkage from closed campaign** *(NEW)* — spec §11 mentions; not built.

### Next-session plan
1. Address B gaps, ordered as: B6 (multi-run + preview) → B1 + B5 (thumbnails + hit chips) → B7 + B8 (override polish + reason) → B2 (curve preview) → B3 + B4 (bulk ops) → B9/B10/B11/B12/B13.
2. Code-reuse rule: scan existing curve-fit + hit-call machinery first; no reinvention.

---

## High priority (do first)

### H1. SavedSearch wiring into AddResultsFromSavedSearch
- **What:** Backend `AddResultsFromSavedSearch` use case currently throws `NotImplementedError`. The "From a saved search" dropdown item in the campaign builder's Add-compounds menu is disabled with a "coming soon" tooltip.
- **Where:** `backend/src/cellar/application/research_organization/add_results_from_saved_search.py`; `frontend/src/features/screen-campaign/components/compound-list-pane.tsx` (dropdown item); needs a new `<AddFromSavedSearchDialog>`.
- **Work:** Wire the existing `ExecuteSavedSearch` use case into the seeder. Build the dialog (SavedSearchPicker → submit → toast). About half a day.

### H2. Run import → "also add to campaign" UX
- **What:** Today the path is: import run data via wizard → manually add compounds to a campaign. The cleaner UX is a checkbox in the run-import wizard ("Also add these compounds to campaign…") OR an "Add to campaign…" action on the run detail page. Backend `AddResultsFromRun` already works.
- **Where:**
  - Backend: confirm a clean entry point for "give me unique molecule_ids + per-molecule batch_ids for run X." If not present, add a small query to `RunRepository`.
  - FE: `frontend/src/features/screening-assay/components/run-import-wizard.tsx` (the existing wizard at `/assays/runs/[id]` → Import Run File → Readout Data tab) OR a new "Add to campaign" button on `run-detail.tsx`. Also enable the disabled "From a protocol run" item in the campaign builder's Add-compounds dropdown with a Run picker.
- **Work:** Backend query if missing + FE Run picker dialog + wiring into the existing wizard. About a day.

### H3. PATCH-after-close 423 API test (currently degraded to 404)
- **What:** Plan §6.1 required a real 423 test for "mutate a closed campaign." The current `test_patch_after_close_423` actually asserts 404 against a non-existent UUID because constructing a CLOSED campaign in the API test env needs real Protocol/Run/ReadoutData fixtures.
- **Where:** `backend/tests/api/test_campaigns_api.py::test_patch_after_close_423`.
- **Work:** Build a "closed campaign" API fixture (probably reuse the pattern from `test_campaign_published_contract.py` which already constructs one via direct domain calls). Then update the test to PATCH against the real closed campaign and assert 423. About 2 hours.

### H4. Orval Zod plugin — eliminate the FE/BE enum-drift class of bugs
- **What:** Hand-written Zod schemas in `channel-strip.tsx` / `results-grid.tsx` drifted from the backend `enums.py` three separate times today (`source_kind`, `selection_rule`, `qualifier_handling`, `value_qualifier`, `hit_call`). Each cost a round of 422/500 errors. The fix is to generate Zod from the OpenAPI spec so the FE schemas can't disagree with the backend.
- **Where:** `frontend/orval.config.ts` — add a `--zod` output target (or a second client config). Generated schemas land at `frontend/src/shared/lib/api/model/<Type>.zod.ts` or similar; FE forms import from there instead of hand-writing `z.enum(...)`.
- **Work:** Set up the orval-zod plugin + migrate the 4–6 forms currently hand-writing schemas. About half a day.

### H5. Verify saved notes display after reload
- **What:** Earlier this session we fixed the silent-data-loss bug — `notes` now persists from the decision panel via PATCH. Need to verify in a browser smoke test that saved notes also display correctly after page reload (orval-generated `CampaignResultResponse` includes a `notes` field; the decision panel reads `result.notes` on hydration — should already work but never browser-verified).
- **Where:** `frontend/src/features/screen-campaign/components/decision-panel.tsx:46-53`.
- **Work:** Manual smoke test, ~5 minutes. Add a Playwright assertion (see H6).

---

## Medium priority (good polish targets)

### M1. Workspace-wide "All campaigns" entry in sidebar
- **What:** Campaigns are only reachable per-project today. Add a sidebar entry under "Discovery" linking to a workspace-wide list.
- **Where:** Backend list endpoint currently requires `project_id`; relax it to optional. Frontend: new sidebar item + a `/campaigns` route + workspace-wide hook (extend `useCampaignsByProject` to skip projectId).
- **Work:** ~2 hours.

### M2. Bulk delete compounds from grid
- **What:** Curated-workspace model implies the user wants to bulk-select rows and remove. Currently per-row delete only.
- **Where:** `frontend/src/features/screen-campaign/components/results-grid.tsx` (AG Grid row selection); needs a backend `RemoveResultRows(result_ids: list)` use case + endpoint for efficiency (or just fire N DELETEs from the FE).
- **Work:** ~3–4 hours including the bulk endpoint.

### M3. AG Grid molecule column — add structure thumbnail
- **What:** Plan §8.4 said "structure thumbnail + reg id." Currently shows reg id only (after today's fix). RDKit.js depiction on hover or inline.
- **Where:** `frontend/src/features/screen-campaign/components/results-grid.tsx:308-336`. Look at the existing structure-rendering hook (likely `useMoleculeDepict` or similar in `features/chemical-registration`).
- **Work:** ~2 hours.

### M4. Override-cell modal UX — value/unit gating for ND/excluded
- **What:** When the user picks `value_qualifier=nd` or `excluded`, the value/unit inputs should disable (backend forces value to null for those qualifiers). Currently the modal still requires a non-empty `unit` — backend rejects empty unit even for ND.
- **Where:** `frontend/src/features/screen-campaign/components/results-grid.tsx` override-cell modal.
- **Work:** Two paths — FE-only: disable inputs + auto-fill unit from existing measurement. Better: relax `CampaignMeasurement.__post_init__` to allow empty unit when value_qualifier ∈ {nd, excluded}. ~1–2 hours.

### M5. Alembic-on-startup migration drift warning
- **What:** The "null value in column compound_source" 500 today happened because the dev DB was at revision 027 but code expected 028. Surface this as a startup warning so it doesn't manifest as a confusing NotNull violation.
- **Where:** `backend/src/cellar/interface/app.py` startup hook.
- **Work:** Compare `alembic current` vs `alembic heads` at FastAPI startup; log a structured warning when behind. ~30 minutes.

### M6. Real e-signature integration (replace `crypto.randomUUID()` stub)
- **What:** CloseCampaign currently takes a caller-supplied `signature_id`. FE generates a random UUID in `close-sign-dialog.tsx`. Real flow: Sentinel re-auth challenge → mints an `ElectronicSignature` → use case records its id. Whole chain is stubbed.
- **Where:** Multiple. `close-sign-dialog.tsx` (FE re-auth integration), new application-layer SignatureService (or wire AuditRecordingService to capture signatures), `CloseCampaignRequest` DTO probably loses `signature_id` (moves to a SignatureService dep), Sentinel integration for the re-auth challenge.
- **Work:** ~1 day. Coupled to broader audit/Sentinel work.

---

## Low priority (engineering / nice-to-have)

### L1. Sentinel-resolved `closed_by.name` in published JSON
- **What:** Currently emits `{"id": uuid, "name": null}` for closed_by. Need Sentinel user-resolver hook.
- **Where:** `backend/src/cellar/application/research_organization/get_published_campaign.py`. TODO comment exists.

### L2. Audit `signature.signed_at` in published JSON
- **What:** Currently emits `{"id": uuid, "signed_at": null}`. Need an audit signature lookup query.
- **Where:** Same file as L1. Audit-compliance bounded context has `ElectronicSignature` model already.

### L3. `BatchRepository.find_by_ids` bulk endpoint
- **What:** GetPublishedCampaign currently loops `find_by_id` for batches per result. Add a bulk method.
- **Where:** `backend/src/cellar/domain/inventory/repository.py` + SA impl.

### L4. `require_viewer` auth guard
- **What:** GetPublishedCampaign currently uses `require_editor`. A lower-privilege `require_viewer` guard should exist for read-only endpoints.
- **Where:** `backend/src/cellar/application/auth.py`. Wire it into `GetPublishedCampaign`.

### L5. `update_campaign_channel.py` — push label validation into the entity
- **What:** Partial in-memory mutation on label validation failure. Benign in current code path (campaign discarded on Failure) but cleaner to add a `set_label()` method on `CampaignChannel` that validates first.
- **Where:** `backend/src/cellar/domain/research_organization/campaign_channel.py`.

### L6. RecomputeChannel API route
- **What:** `RecomputeChannel` use case is wired in DI but no API endpoint exposes it. Reachable via `UpdateCampaignChannel` re-resolve in practice, but a dedicated `POST /campaigns/{id}/channels/{channel_id}/recompute` endpoint would be cleaner.
- **Where:** `backend/src/cellar/interface/routes/campaigns.py`.

### L7. Per-result provenance log (vs single `added_from`)
- **What:** Currently each result has ONE `added_from` (first-add wins). If multi-source-per-row history matters later, add an append-only `CampaignResultProvenance` log on top — additive, no data migration.
- **Where:** New domain entity + persistence + summary serialization. Defer until there's a real need.

### L8. Sources summary card on drafts
- **What:** Today the `<SourcesSummaryCard>` reads `campaign.compound_sources` which is only populated on published view (server-derived at close). For draft campaigns, the card needs to compute the summary client-side from `result.added_from`. But `CampaignResultResponse` doesn't currently serialize `added_from` — so either expose it in the response DTO or expose a server-side `compound_sources_draft` field.
- **Where:** Backend `CampaignResponse` DTO. ~1 hour.

---

## Verification / process

### V1. Playwright E2E happy path
- **What:** `frontend/tests/e2e/screen-campaign.spec.ts.TODO` is a stub. Configure `@playwright/test`, write the test, run in CI.
- **Path:**
  ```
  pnpm add -D @playwright/test
  pnpm exec playwright install
  # write playwright.config.ts with baseURL, testDir, etc.
  # write the test: create draft → add channel → set decision → close → supersede
  ```
- **Work:** ~half a day including stable selectors and seeded data.

### V2. Browser smoke pass on the FE
- **What:** I shipped 17 FE commits without ever rendering them in a browser (per the CLAUDE.md rule, we owe this). Run `pnpm dev`, log in, click through:
  - Projects → pick a project → Campaigns tab.
  - Create campaign (3-field dialog) → land in builder.
  - Add compounds: manual / from collection / from another campaign.
  - Add a channel (channel-strip dropdown — verify all enum dropdowns are correct).
  - Set a decision in the decision panel; refresh page; verify decision + reason + notes persist.
  - Override a cell — verify all qualifier options work.
  - Close & sign → verify redirect to closed view.
  - Try the supersede flow.
- **Work:** ~30 minutes if no bugs, more if issues surface.

### V3. Backend lint pass
- **What:** Run `ruff check backend/` + `mypy backend/` (or whatever's in the Makefile). Tests pass but lint/type discipline isn't checked.
- **Work:** ~1 hour if there are violations to fix.

---

## Out of scope (do not do)

- Reseed-style "wipe and replace from new source" — explicitly removed by the per-result-attribution refactor. If a user wants to start over they delete the campaign.
- A campaign-level `compound_source` field — explicitly removed. Use per-result `added_from` instead.
- Saved-search add-from for v1.5 — H1 covers this; deferring further is fine.
- Multi-channel batch deletion (similar to bulk row delete) — single delete is fine; batch is M2's compound version.

---

## ChannelPopoverForm follow-ups (2026-05-12, found during Task 2.5 extraction)

Both are pre-existing in the original `ChannelForm` (before extraction in `fb8f5b72`). Tracked for a separate fix session, not a redesign blocker.

- **`between` range silent-drop.** `channel-popover.tsx:187-200` — when user enters `low > high`, the form silently saves without the threshold. No validation error shown. Fix: add a `superRefine` to the schema that emits `path: ["hit_value_high"]` when `Number(low) > Number(high)`.
- **`"in"` operator silent clearing on edit.** `channel-popover.tsx:68-79` + `channels-section.tsx:112` — `parseHitThreshold` returns `null` for `string[]` operand values, so opening the edit popover for a channel created with `operator: "in"` (e.g. from `recommended_hit_criteria`) silently clears the existing threshold on save and hides it in the section display. Fix: detect `operator === "in"` in the edit form and render as read-only; in `formatThreshold`, handle the `"in"` case explicitly.

---

## Quick reference — key recent commits on `fe2`

- `082d47fb..cef359e4` — backend refactor (per-result attribution, 6 commits)
- `bd33686b..40b5c6fd` — FE refactor (5 commits)
- `ac2b8e13`, `40fa5dc4` — enum-alignment fixes
- `679f22a9` — compound-list pane registration_number display
- `62ec6689` — notes field persistence
- `4931b721` — close-campaign measurement-id preservation test
- `80e9ebed` — measurement-id preservation in re-resolve loops (RefreshFromSources/RecomputeChannel/UpdateCampaignChannel)
