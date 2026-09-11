# Remove campaign result decisions — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Lean plan by user ruling: files, interfaces, tests. No per-task reviews; one whole-branch review at the end.

**Goal:** Delete `CampaignResult.decision` / `decision_reason` end to end; keep `notes` with its own edit path; add-from-campaign filters by stage instead of decision.

**Architecture:** Domain → application → infrastructure → interface on the backend (one task, sequential inside), then orval regen, then the frontend (one task). No data migration: columns are dropped.

**Spec:** `docs/superpowers/specs/2026-09-11-remove-campaign-decisions-spec.md`

## Global constraints

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before backend code.
- Backend tests: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest …` for `tests/api` and `tests/integration` (testcontainers); unit tests need no Docker.
- Frontend checks: `cd frontend && pnpm vitest run src/features/screen-campaign && pnpm exec biome check src/features/screen-campaign && pnpm exec tsc --noEmit -p .`
- Commit with explicit pathspecs. No `Claude-Session` trailer; keep `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never hand-write a TS interface mirroring a backend DTO; regen orval (`pnpm generate:api`, backend on :8000) and revert version-stamp-only churn.

---

### Task 1: Backend — remove decisions, add notes-only edit, stage-filtered add-from-campaign

**Delete**
- `backend/src/cellar/application/research_organization/bulk_set_result_decisions.py`
- `backend/tests/unit/application/research_organization/test_bulk_set_result_decisions.py`

**Rename** `set_result_decision.py` → `set_result_notes.py` (+ test file `test_set_result_decision.py` → `test_set_result_notes.py`).

**Modify**
- `backend/src/cellar/domain/research_organization/enums.py` — delete `CampaignDecision` and its `__all__` entry.
- `backend/src/cellar/domain/research_organization/campaign_result.py` — drop `decision`, `decision_reason`, `set_decision`; fix module docstring (no collection at close).
- `backend/src/cellar/domain/research_organization/source_ref.py` — `CampaignRef.decision_filter` → `stage_id: uuid.UUID | None = None`; `to_dict` emits `"stage_id": str(self.stage_id) if self.stage_id else None`; `from_dict` reads `stage_id` (ignore legacy `decision_filter`); update the `source_group_key` docstring line that cites `decision_filter`.
- `backend/src/cellar/application/research_organization/add_results_from_campaign.py` — command field `stage_id: uuid.UUID | None = None`. When set: it must be one of `source.stages` ids, else `Failure(ValidationError("Stage … does not belong to source campaign"))`; then `outcomes = evaluate_stages(source)` (from `cellar.domain.research_organization.stage_evaluation`) and keep `r` where `outcomes[r.id][stage_id].outcome == StageOutcome.HIT`. When `None`: every source result. `CampaignRef(campaign_id=…, stage_id=input.stage_id, description=…)`.
- `backend/src/cellar/application/research_organization/add_results_from_runs.py` — remove `default_decision` (command field, docstring, `CampaignResult(...)` kwarg).
- `backend/src/cellar/application/research_organization/set_result_notes.py` — `SetResultNotesCommand(workspace_id, campaign_id, result_id, notes: str | None)`; class `SetResultNotes`; drop the `_Unset` sentinel (notes is now the only field and always supplied); draft-only guard stays (`"Cannot edit notes: campaign is …"`).
- `backend/src/cellar/application/research_organization/get_published_campaign.py` — drop `decision` / `decision_reason` from `_serialize_result`; update the comment that cites `CampaignRef.decision_filter`.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py` — drop the two columns on `CampaignResultModel`.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py` — drop the two fields in `_result_to_domain`, `_result_to_model`, `_result_update_model`; drop the `CampaignDecision` import.
- `backend/src/cellar/infrastructure/di/_research_organization.py` and `backend/src/cellar/interface/dependencies/_research_organization.py` — replace `SetResultDecision` wiring with `SetResultNotes` (`SetResultNotesDep`); remove `BulkSetResultDecisions` wiring and `__all__` entries.
- `backend/src/cellar/interface/routes/_campaign_dtos.py` — `AddFromCampaignRequest.decision_filter` → `stage_id: uuid.UUID | None = None`; drop `AddFromRunsRequest.default_decision`; `SetResultDecisionRequest` → `SetResultNotesRequest(notes: str | None = None, extra="forbid")`; delete `BulkSetResultDecisionsRequest` and `BulkSetResultDecisionsResponse`; drop `decision` / `decision_reason` from `CampaignResultResponse` and `from_domain`.
- `backend/src/cellar/interface/routes/campaigns.py` — `stage_id=body.stage_id` into the command; drop `default_decision`; drop the `CampaignDecision` import.
- `backend/src/cellar/interface/routes/campaigns_results.py` — delete the bulk route and its imports/comment; `PATCH /{campaign_id}/results/{result_id}` becomes `set_result_notes(body: SetResultNotesRequest, uc: SetResultNotesDep)` building `SetResultNotesCommand(..., notes=body.notes)`; module docstring.
- `backend/alembic/versions/076_campaign_drop_decision.py` — new. `revision = "076_campaign_drop_decision"`, `down_revision = "075_campaign_drop_hit_columns"`. `upgrade`: `op.drop_column("campaign_result", "decision")`, `op.drop_column("campaign_result", "decision_reason")`. `downgrade`: re-add `decision` `sa.String(32), nullable=False, server_default="deferred"` and `decision_reason` `sa.Text(), nullable=True`. Docstring in the style of 075 (data not restored on downgrade).
- `backend/tests/api/fixtures/daikon_contract.schema.json` — remove `decision` from the results `required` list and delete the `decision` / `decision_reason` properties.

**Tests (update / add)**
- `tests/unit/domain/research_organization/test_campaign_result.py` — delete the three decision tests; add `test_notes_default_none`.
- `tests/unit/domain/research_organization/test_source_ref.py` — round-trip `CampaignRef(campaign_id, stage_id=sid)` → `to_dict()["stage_id"] == str(sid)` → `from_dict` restores it; `stage_id=None` emits `None`; `from_dict({"kind": "campaign", "campaign_id": …, "decision_filter": ["selected"]})` yields `stage_id is None`.
- `tests/unit/application/research_organization/test_add_results_from_campaign.py` — rebuild the source-campaign helper with one channel, one stage (`StageCriterion` on that channel, e.g. `gte 50`), and results whose measurements make one hit and one miss; assert `stage_id=None` adds both, `stage_id=<stage>` adds only the hit, a foreign stage id returns `ValidationError`, and `added_from.to_dict()["stage_id"]` is recorded. Look at `tests/unit/domain/research_organization/test_stage_evaluation.py` (or the closest existing test) for how measurements + criteria are built.
- `tests/unit/application/research_organization/test_set_result_notes.py` — sets notes, clears with `None`, 404 on unknown result, rejects on closed campaign.
- `tests/unit/application/research_organization/test_get_published_campaign.py`, `test_close_campaign.py`, `tests/integration/application/research_organization/test_close_campaign.py`, `tests/api/test_campaigns_api.py`, `tests/api/test_campaign_published_contract.py` — remove decision setup/assertions; API test for `PATCH …/results/{id}` now sends `{"notes": "Watch hERG"}` and asserts `notes`; add a `{"notes": null}` clear case; delete bulk-decision tests.
- `tests/unit/application/research_organization/test_preview_run_import.py` and `tests/unit/domain/screening_assay/test_run.py` mention "decision" only in prose about run hit criteria — leave them.

**Interfaces produced (frontend relies on these):**
- `PATCH /api/v1/campaigns/{campaign_id}/results/{result_id}` body `SetResultNotesRequest {notes: string | null}` → `CampaignResponse`.
- `POST /api/v1/campaigns/{campaign_id}/add-from-campaign` body `AddFromCampaignRequest {source_campaign_id, stage_id?: uuid | null, description?}`.
- `AddFromRunsRequest` no longer has `default_decision`.
- `CampaignResultResponse` has `notes` but no `decision` / `decision_reason`.
- Bulk-decision route gone.

**Verify:** `uv run pytest tests/unit -q`, then `DOCKER_HOST=… uv run pytest tests/api/test_campaigns_api.py tests/api/test_campaign_published_contract.py tests/integration/application/research_organization -q`, `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` (whatever `make lint` runs). Apply the migration on the dev DB: `uv run alembic upgrade head`.

**Commit:** `refactor(campaigns)!: remove per-result decisions; notes-only edit; add-from-campaign filters by stage` with a `BREAKING CHANGE:` footer naming the published-payload change.

---

### Task 2: Frontend — drop decisions, Notes column, stage picker in add-from-campaign

Pre-step (done by the orchestrator, not the implementer): `cd frontend && pnpm generate:api` against the dev backend, revert version-stamp-only churn, keep the real DTO diffs, and delete the dangling `model/index.ts` barrel lines for `bulkSetResultDecisions*`, `setResultDecisionRequest*`.

**Delete**
- `src/features/screen-campaign/components/popovers/decision-popover.tsx`
- `src/features/screen-campaign/components/grid/decision-chip-cell.tsx`

**Create**
- `src/features/screen-campaign/components/popovers/notes-popover.tsx` — `NotesPopover({campaignId, result, onClose})`: one `Textarea`, Save / Cancel, explicit save (no autosave), calls the regenerated `useSetResultNotesApiV1CampaignsCampaignIdResultsResultIdPatch` with `{notes: trimmed || null}`, invalidates `campaignKeys.detail(campaignId)`, `showError` on failure. Model it on the old decision popover's dirty/cancel handling.
- `src/features/screen-campaign/components/grid/notes-cell.tsx` — `NotesCell({campaignId, result, readOnly})`: clamped 3-line notes text with `title` for the full text; in draft it is a button that opens `NotesPopover` in a `Popover`; empty state shows a muted "Add note" affordance in draft and nothing when read-only.

**Modify**
- `src/features/screen-campaign/types/index.ts` — drop `CampaignDecision`, `CAMPAIGN_DECISION_LABELS`, and the `SetResultDecisionRequest` re-export; alias the new `SetResultNotesRequest` if a feature type is wanted.
- `src/features/screen-campaign/components/campaign-filter-bar.tsx` (+ `.test.ts`) — remove `decisions` from `CampaignFilters`, the decision chips, `CampaignDecisionFilter`, `DECISION_*` styles, `byDecision` tally; `closedCampaignFilters()` returns `emptyFilters()` (delete it and its callers' use if nothing else differs); `filtersActive` no longer checks decisions. Tests updated accordingly.
- `src/features/screen-campaign/components/grid/results-grid.tsx` — column 5 becomes `headerName: "Notes", colId: "notes", pinned: "right", width: 220`, renderer `<NotesCell …/>`; header docblock line.
- `src/features/screen-campaign/components/close-campaign-dialog.tsx` — delete the decision breakdown block and `decisionCounts`.
- `src/features/screen-campaign/components/preview-as-published-dialog.tsx` — drop `decision` from the hand-rolled shape and the badge column.
- `src/features/screen-campaign/components/add-from-runs-dialog.tsx` — remove `defaultDecision` state, the "Default decision on new rows" control, `default_decision` in the payload, and the `ConfigureStepProps` fields.
- `src/features/screen-campaign/components/add-from-campaign-dialog.tsx` — replace the decision checkboxes with a stage `Select`: "All compounds" (value `""` → `stage_id: null`) plus one item per stage of the chosen source campaign, loaded with `useCampaign(sourceCampaignId, {enabled: !!sourceCampaignId})` (check its real signature in `hooks/use-campaigns.ts`). Reset the stage when the source changes. Payload `{source_campaign_id, stage_id: stageId || null, description}`.
- `src/features/screen-campaign/components/sections/stages-section.test.tsx` and `lib/stage-outcomes.test.ts` fixtures — drop `decision: "deferred"` from result fixtures.
- Any other compile error from the regen (grep `decision` under `src/features/screen-campaign`).

**Tests**
- `campaign-filter-bar.test.ts` — no decision cases; Overridden + stage-outcome cases stay green.
- New `notes-cell.test.tsx` — read-only renders the text and no button; draft renders a button; empty draft shows "Add note".
- Existing section tests pass.

**Verify:** `pnpm vitest run src/features/screen-campaign`, `pnpm exec biome check src/features/screen-campaign`, `pnpm exec tsc --noEmit -p .`. Then in the browser on the Test-3 campaign: filter bar shows only stage/Overridden chips, Notes column edits and persists, Add from campaign offers a stage picker.

**Commit:** `refactor(screen-campaign): drop decision UI; notes column; stage picker for add-from-campaign`.
