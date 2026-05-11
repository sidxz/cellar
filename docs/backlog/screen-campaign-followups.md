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

## High priority (do first)

### H1. SavedSearch wiring into AddResultsFromSavedSearch
- **What:** Backend `AddResultsFromSavedSearch` use case currently throws `NotImplementedError`. The "From a saved search" dropdown item in the campaign builder's Add-compounds menu is disabled with a "coming soon" tooltip.
- **Where:** `backend/src/chem_vault/application/research_organization/add_results_from_saved_search.py`; `frontend/src/features/screen-campaign/components/compound-list-pane.tsx` (dropdown item); needs a new `<AddFromSavedSearchDialog>`.
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
- **Where:** `backend/src/chem_vault/interface/app.py` startup hook.
- **Work:** Compare `alembic current` vs `alembic heads` at FastAPI startup; log a structured warning when behind. ~30 minutes.

### M6. Real e-signature integration (replace `crypto.randomUUID()` stub)
- **What:** CloseCampaign currently takes a caller-supplied `signature_id`. FE generates a random UUID in `close-sign-dialog.tsx`. Real flow: Sentinel re-auth challenge → mints an `ElectronicSignature` → use case records its id. Whole chain is stubbed.
- **Where:** Multiple. `close-sign-dialog.tsx` (FE re-auth integration), new application-layer SignatureService (or wire AuditRecordingService to capture signatures), `CloseCampaignRequest` DTO probably loses `signature_id` (moves to a SignatureService dep), Sentinel integration for the re-auth challenge.
- **Work:** ~1 day. Coupled to broader audit/Sentinel work.

---

## Low priority (engineering / nice-to-have)

### L1. Sentinel-resolved `closed_by.name` in published JSON
- **What:** Currently emits `{"id": uuid, "name": null}` for closed_by. Need Sentinel user-resolver hook.
- **Where:** `backend/src/chem_vault/application/research_organization/get_published_campaign.py`. TODO comment exists.

### L2. Audit `signature.signed_at` in published JSON
- **What:** Currently emits `{"id": uuid, "signed_at": null}`. Need an audit signature lookup query.
- **Where:** Same file as L1. Audit-compliance bounded context has `ElectronicSignature` model already.

### L3. `BatchRepository.find_by_ids` bulk endpoint
- **What:** GetPublishedCampaign currently loops `find_by_id` for batches per result. Add a bulk method.
- **Where:** `backend/src/chem_vault/domain/inventory/repository.py` + SA impl.

### L4. `require_viewer` auth guard
- **What:** GetPublishedCampaign currently uses `require_editor`. A lower-privilege `require_viewer` guard should exist for read-only endpoints.
- **Where:** `backend/src/chem_vault/application/auth.py`. Wire it into `GetPublishedCampaign`.

### L5. `update_campaign_channel.py` — push label validation into the entity
- **What:** Partial in-memory mutation on label validation failure. Benign in current code path (campaign discarded on Failure) but cleaner to add a `set_label()` method on `CampaignChannel` that validates first.
- **Where:** `backend/src/chem_vault/domain/research_organization/campaign_channel.py`.

### L6. RecomputeChannel API route
- **What:** `RecomputeChannel` use case is wired in DI but no API endpoint exposes it. Reachable via `UpdateCampaignChannel` re-resolve in practice, but a dedicated `POST /campaigns/{id}/channels/{channel_id}/recompute` endpoint would be cleaner.
- **Where:** `backend/src/chem_vault/interface/routes/campaigns.py`.

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

## Quick reference — key recent commits on `fe2`

- `082d47fb..cef359e4` — backend refactor (per-result attribution, 6 commits)
- `bd33686b..40b5c6fd` — FE refactor (5 commits)
- `ac2b8e13`, `40fa5dc4` — enum-alignment fixes
- `679f22a9` — compound-list pane registration_number display
- `62ec6689` — notes field persistence
- `4931b721` — close-campaign measurement-id preservation test
- `80e9ebed` — measurement-id preservation in re-resolve loops (RefreshFromSources/RecomputeChannel/UpdateCampaignChannel)
