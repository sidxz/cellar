# Stage gates and reads (batch 2) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Lean plan by user ruling: files, interfaces, tests. No per-task reviews; one whole-branch review at the end.

**Goal:** Make hit stages usable for triage: a manual (hand-picked) stage kind with a `pending` outcome, bulk overrides and bulk row removal, `parent_stage_id` and get-or-create on the `stage_name` paths, stage counts on the draft read, a results-free summary read that the list and project page use, plus four hygiene items.

**Architecture:** Domain first (enum, entity invariant, evaluator, tally), then persistence (migration 077), application (commands), interface (DTOs, routes), then orval regen and the frontend. Backend tasks 1-4 are sequential on one branch; frontend tasks 5-6 follow the regen.

**Spec:** `docs/superpowers/specs/2026-09-11-hit-stages-followups-design.md` §4 (D2, D3, D6, D7). Issue sidxz/cellar#75. Branch `feat/stage-gates` from `main` (after PR #77).

## Global constraints

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before backend code.
- Backend tests: `cd backend && uv run pytest tests/unit/... -q`; `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/... tests/api/... -q`. Lint: `cd backend && uv run ruff check src && uv run ruff format src` (src only, matches CI).
- Frontend checks: `cd frontend && pnpm vitest run src/features/screen-campaign src/features/research-organization && pnpm exec biome check src/features && pnpm exec tsc --noEmit -p .` — verify by exit code.
- Use cases return `Failure(DomainError)`, never raise: `ValidationError` → 422, `ConflictError` → 409, `NotFoundError` → 404, `DataLockedError` → 423.
- Migration numbering: `077_campaign_stage_kind` revises `076_campaign_drop_decision`. Apply it to the dev DB after writing it (`cd backend && uv run alembic upgrade head`) so the reloading dev backend on :8000 keeps serving.
- Orval: backend DTOs change in this batch. After the backend tasks, `cd frontend && pnpm generate:api` (backend on :8000, `--reload`), then revert version-stamp-only churn (`git checkout -- <files whose only diff is the OpenAPI version line>`) and keep real DTO diffs. Never hand-write a TS type mirroring a backend DTO; alias generated ones.
- Commit with explicit pathspecs (`git commit -m … -- <paths>`); the working tree carries unrelated user edits (`frontend/next-env.d.ts`, `frontend/AGENTS.md`). No `Claude-Session` trailer; keep `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Tool shell is fish; BSD sed has no `\b` — `perl -pi -e` for identifier renames.
- Cross-app: the published document and the list endpoint are consumed by another app. Changes here are additive except `GET /campaigns` switching to summaries (D3, agreed with the consumer).

Paths relative to `backend/src/cellar/` unless prefixed `backend/tests/`, `backend/alembic/`, or `frontend/`.

---

### Task 1: Manual stage kind and the `pending` outcome (ask 4, backend)

**Modify — domain**
- `domain/research_organization/enums.py` — add `class StageKind(StrEnum): CRITERIA = "criteria"; MANUAL = "manual"` next to `StageOutcome` (:56-62); add `PENDING = "pending"` to `StageOutcome`; export both in `__all__` if the module keeps one.
- `domain/research_organization/campaign_stage.py::CampaignStage` (:119-139) — add `kind: StageKind = StageKind.CRITERIA` after `parent_stage_id`; in `__post_init__`: `if self.kind == StageKind.MANUAL and self.criteria: raise ValidationError("A manual stage has no criteria; clear them or use a criteria stage")`. Docstring: a manual stage's population evaluates to `pending` until promoted.
- `domain/research_organization/campaign.py::update_stage` (:254) — add `kind: StageKind | object = UNSET`; when set, assign and re-run the manual-no-criteria invariant against the (possibly also updated) criteria; switching to manual with non-empty criteria is a `ValidationError` (the UI sends `criteria: []` with the switch).
- `domain/research_organization/stage_evaluation.py::_evaluate_stage` (:116-121) — in the `in_stage` branch: `if stage.kind == StageKind.MANUAL: checks, base_outcome = (), StageOutcome.PENDING` else the existing `_combine`. Overrides (:123-127) unchanged: a promote makes it `hit`, a demote `miss`.
- `tally_stage_counts` (:151-179) — add `"pending": 0` to every bucket; the existing `bucket[outcome.outcome.value] += 1` already counts it and `population` already includes it.

**Modify — persistence**
- `infrastructure/persistence/sqlalchemy/research_organization/models.py::CampaignStageModel` (:367-392) — `kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="criteria")`.
- `campaign_repository.py::_stage_to_domain` (:225) / `_stage_to_model` (:236) — map `kind` (`StageKind(model.kind)` / `stage.kind.value`); also the reconcile branch in `_update_model` that copies stage fields onto an existing model (find where `name`/`criteria` are copied for an existing stage and add `kind`).
- `backend/alembic/versions/077_campaign_stage_kind.py` — new, docstring in the style of 076. `revision = "077_campaign_stage_kind"`, `down_revision = "076_campaign_drop_decision"`. `upgrade`: `op.add_column("campaign_stage", sa.Column("kind", sa.String(16), nullable=False, server_default="criteria"))`. `downgrade`: drop it. Run `uv run alembic upgrade head` against the dev DB.

**Modify — application and interface**
- `application/research_organization/add_campaign_stage.py::AddCampaignStageCommand` — `kind: StageKind = StageKind.CRITERIA`, passed into `CampaignStage(...)`.
- `application/research_organization/update_campaign_stage.py::UpdateCampaignStageCommand` — `kind: StageKind | object = UNSET`, threaded to `campaign.update_stage`.
- `interface/routes/_campaign_dtos.py` — `AddStageRequest.kind: Literal["criteria", "manual"] = "criteria"`; `UpdateStageRequest.kind: Literal["criteria", "manual"] | None = None` (omitted = unchanged, via `model_fields_set` like the other fields); `CampaignStageResponse.kind: str` from `s.kind.value`; `StageOutcomeResponse.outcome` docstring/Literal (if it is a Literal) gains `"pending"`.
- `interface/routes/campaigns_stages.py` — thread `kind` into both commands (`StageKind(body.kind)`).
- `application/research_organization/get_published_campaign.py::_serialize_stage` (:352) — add `"kind": stage.kind.value`.
- `backend/tests/api/fixtures/daikon_contract.schema.json` — `stages[]` gains required `kind` (`enum: ["criteria","manual"]`), `counts` gains `pending` (integer), and the stage-outcome `outcome` enum gains `"pending"`. Keep `additionalProperties` as it is.

**Tests**
- `backend/tests/unit/domain/research_organization/test_campaign_stage.py` — manual with criteria → `ValidationError`; manual without → ok; default kind is criteria.
- `backend/tests/unit/domain/research_organization/test_campaign.py` — `update_stage(kind=MANUAL)` with existing criteria → `ValidationError`; `update_stage(kind=MANUAL, criteria=[])` → ok.
- `backend/tests/unit/domain/research_organization/test_stage_evaluation.py` — manual root stage: every result `pending`, `checks == ()`; promote → `hit` and the child stage's population includes it; demote → `miss`; `tally_stage_counts` reports `pending` and `population == hit + miss + untested + pending`.
- `backend/tests/unit/application/research_organization/test_add_campaign_stage.py`, `test_update_campaign_stage.py` — kind threads through.
- `backend/tests/unit/infrastructure/persistence/test_migration_074_stage_backfill.py` — leave; add `backend/tests/integration/research_organization/test_campaign_repository.py` case: a manual stage round-trips `kind`.
- `backend/tests/api/test_campaigns_api.py` — `POST …/stages` with `kind: "manual"` returns it; `PATCH` to manual with criteria → 422; `GET` outcomes show `pending`. `backend/tests/api/test_campaign_published_contract.py` — passes with the fixture change.
- `backend/tests/unit/interface/routes/test_campaign_dtos.py` — kind on the response.

**Interfaces produced**
- `StageKind`, `StageOutcome.PENDING`; `CampaignStage.kind`; `AddCampaignStageCommand.kind`; `UpdateCampaignStageCommand.kind`; `AddStageRequest.kind`, `UpdateStageRequest.kind`, `CampaignStageResponse.kind`; published `stages[].kind`, `counts.pending`.

**Commit:** `feat(campaigns): manual stage kind with a pending outcome`

---

### Task 2: Bulk stage overrides and bulk row removal (ask 5 + hygiene, backend)

**Modify**
- `application/research_organization/set_stage_override.py` — `SetStageOverrideCommand.result_id` becomes `result_ids: list[uuid.UUID]`. Handler: empty list → `Failure(ValidationError("result_ids must not be empty"))`; after the draft check and `find_stage`, resolve every id up front (`{r.id: r for r in campaign.results}`); any missing → `Failure(NotFoundError("CampaignResult", <first missing id>))` before mutating; then apply `clear_stage_override` / `set_stage_override` to each; one `save`, one `commit`. `reason` required when `forced_outcome` is not None (the domain `StageOverride` already enforces non-empty; keep that path).
- `interface/routes/_campaign_dtos.py` — `class BulkStageOverrideRequest(BaseModel): result_ids: list[uuid.UUID]; outcome: Literal["hit", "miss"] | None; reason: str | None = None; model_config = {"extra": "forbid"}`. `class BulkRemoveResultsRequest(BaseModel): result_ids: list[uuid.UUID]`.
- `interface/routes/campaigns_stages.py` — new `PUT /{campaign_id}/stages/{stage_id}/overrides` (editor) building `SetStageOverrideCommand(result_ids=body.result_ids, forced_outcome=StageOutcome(body.outcome) if body.outcome else None, reason=body.reason, …)` → `CampaignResponse`. The two existing per-result routes (:122-170) pass `result_ids=[result_id]`.
- `application/research_organization/remove_result_row.py` — `RemoveResultRowCommand.result_id` becomes `result_ids: list[uuid.UUID]`; resolve all first (missing → `NotFoundError`), then `campaign.remove_result_by_molecule(r.molecule_id)` for each; one save/commit. Keep the class name.
- `interface/routes/campaigns_results.py` — the per-row `DELETE` (:107-121) passes `[result_id]`; new `POST /{campaign_id}/results/bulk-remove` (editor) with `BulkRemoveResultsRequest` → `CampaignResponse`. Module docstring updated.

**Tests**
- `backend/tests/unit/application/research_organization/test_set_stage_override.py` — adapt to lists; add: three ids promoted in one call with one reason, all three overridden and `campaign.version` bumped once (save called once); one unknown id → `NotFoundError` and nothing changed; empty list → `ValidationError`; `forced_outcome=None` clears all listed.
- `backend/tests/unit/application/research_organization/test_remove_result_row.py` (extend or create) — two ids removed in one call; unknown id → `NotFoundError`, nothing removed.
- `backend/tests/api/test_campaigns_api.py` — `PUT …/stages/{sid}/overrides` promotes two results (outcomes `hit`, `overridden: true`); `outcome: null` clears; `POST …/results/bulk-remove` removes two rows; per-result routes still work.

**Interfaces produced**
- `PUT /api/v1/campaigns/{id}/stages/{stage_id}/overrides` body `{result_ids, outcome: "hit"|"miss"|null, reason?}` → `CampaignResponse`.
- `POST /api/v1/campaigns/{id}/results/bulk-remove` body `{result_ids}` → `CampaignResponse`.

**Commit:** `feat(campaigns): bulk stage overrides and bulk row removal`

---

### Task 3: `parent_stage_id` and get-or-create on the `stage_name` paths (ask 9, backend)

**Modify**
- `interface/routes/_campaign_dtos.py` — `AddFromRunsRequest.parent_stage_id: uuid.UUID | None = None` (:152-159); `MirrorProtocolRequest.parent_stage_id: uuid.UUID | None = None` (:265-270).
- `application/research_organization/add_results_from_runs.py::AddResultsFromRunsCommand` (:76-89) and `mirror_protocol_channels.py::MirrorProtocolChannelsCommand` (:70-78) — `parent_stage_id: uuid.UUID | None = None`. Routes in `interface/routes/campaigns.py` (`add_results_from_runs`, :229) and `campaigns_channels.py` (mirror) thread it.
- Both use cases: replace the `campaign.add_stage(CampaignStage(...))` block with a shared helper in `application/research_organization/stage_upsert.py`:
  ```python
  def upsert_stage_by_name(campaign: Campaign, *, name: str, criteria: list[StageCriterion], parent_stage_id: uuid.UUID | None) -> tuple[CampaignStage, bool]:
      """Reuse the stage with this name (case-insensitive) and replace its criteria,
      else append a new criteria stage. Returns (stage, created). A manual stage of
      that name is a ValidationError — its membership is hand-picked, not rule-driven."""
  ```
  Reuse path: `campaign.update_stage(existing.id, criteria=criteria, parent_stage_id=parent_stage_id if parent_stage_id is not None else UNSET)`; create path: `CampaignStage(campaign_id=…, name=name, display_order=max+1, criteria=criteria, parent_stage_id=parent_stage_id)`; `add_stage`. Both use cases keep returning `stage_created` (False on reuse).
- `mirror_protocol_channels.py` — move the stage block (:310-342) to run right after the channels are created/found and BEFORE the per-result resolve loop (:297-304), so a parent validation failure costs no resolver work. Read the loop to see which variables the stage block needs (`channel_targets`) and keep them available.

**Tests**
- `backend/tests/unit/application/research_organization/test_stage_upsert.py` (new): create; reuse replaces criteria and keeps id; reuse with a parent sets it; manual stage → `ValidationError`; name match is case-insensitive.
- `test_add_results_from_runs.py` and `test_mirror_protocol_channels.py` — existing "name collision" cases become "reuse" cases (`stage_created is False`, criteria replaced); one case each with `parent_stage_id` set on a new stage; mirror: a bad parent id fails before any measurement is resolved (assert the fake resolver was not called).
- `backend/tests/api/test_campaigns_api.py` — `add-from-runs` twice with the same `stage_name` succeeds and leaves one stage.

**Commit:** `feat(campaigns): parent_stage_id and get-or-create on the stage_name paths`

---

### Task 4: Stage counts, summary read, list summaries, hygiene (ask 6, backend)

**Modify — counts and summary**
- `interface/routes/_campaign_dtos.py`:
  - `class StageCountsResponse(BaseModel): population: int; hit: int; miss: int; untested: int; pending: int; not_in_stage: int; overridden: int`.
  - `CampaignStageResponse.counts: StageCountsResponse`; `from_domain(cls, s, counts: dict[str, int])`.
  - `CampaignResponse.from_domain` (:523-562) — after `stage_outcomes = evaluate_stages(c)` (:534) call `stage_counts = tally_stage_counts(c, stage_outcomes)` and build stages with `CampaignStageResponse.from_domain(s, stage_counts[s.id])`. Every other place that builds `CampaignStageResponse` (grep) gets the same.
  - `class CampaignSummaryResponse(BaseModel)` — every `CampaignResponse` field except `results`, plus `result_count: int`; `from_domain(cls, c, scientist_by_run_id=None, *, targets)` mirrors `CampaignResponse.from_domain` (reuse its helpers; `compound_sources` via `_derive_compound_sources`; stages with counts).
- `interface/routes/campaigns.py` — new `GET /{campaign_id}/summary` → `CampaignSummaryResponse` using the existing `GetCampaignDep` (viewer); `list_campaigns` (:104-135) returns `PaginatedResponse[CampaignSummaryResponse]` and gains `status: Literal["draft","closed","superseded"] | None = Query(default=None)`.
- `application/research_organization/list_campaigns.py::ListCampaignsQuery` — `status: CampaignStatus | None = None`, forwarded to the repo.
- `domain/research_organization/repository.py::find_by_project` / `find_by_workspace` (:194-217) and the SQLAlchemy impl (`campaign_repository.py:437-515`) — keyword `status: CampaignStatus | None = None` → `stmt.where(CampaignModel.status == status.value)`.
- `get_published_campaign.py:111-113` — replace `require_editor(auth)` with `require_workspace_role(auth, "viewer")` (import from `cellar.application.auth`); drop the TODO.
- `_campaign_dtos.py::UpdateChannelRequest` (:180-191) — `display_order: int | None = None`; `application/research_organization/update_campaign_channel.py::UpdateCampaignChannelCommand` — `display_order: int | object = UNSET`; thread through the route in `campaigns_channels.py` (model_fields_set pattern) and the aggregate's channel update path (find how `label` is applied to the channel in the use case / `Campaign` and apply `display_order` the same way; validate `>= 0` via the entity).
- `models.py::CampaignModel.results` (:200-204) — `order_by="CampaignResultModel.id"` (backlog `campaign-results-unstable-order.md`; delete that backlog file in this commit with `git rm`).

**Tests**
- `backend/tests/unit/interface/routes/test_campaign_dtos.py` — `counts` present on each stage with the seven keys; `CampaignSummaryResponse` has no `results` and `result_count == len(results)`.
- `backend/tests/unit/application/research_organization/test_list_campaigns.py` (extend or create) — `status` forwarded to the repo fake.
- `backend/tests/integration/research_organization/test_campaign_repository.py` — `find_by_project(status=CLOSED)` filters; results come back ordered by id after an update to one row.
- `backend/tests/unit/application/research_organization/test_get_published_campaign.py` — a viewer-role auth passes; no role fails.
- `backend/tests/unit/application/research_organization/test_update_campaign_channel.py` — `display_order` updates; negative → `ValidationError`.
- `backend/tests/api/test_campaigns_api.py` — `GET …/summary` shape (no `results`, has `result_count`, stages carry `counts`); `GET /campaigns?status=closed`; list items have no `results`; `PATCH …/channels/{id}` with `display_order`.

**Interfaces produced**
- `CampaignStageResponse.counts`, `CampaignSummaryResponse`, `GET /api/v1/campaigns/{id}/summary`, `GET /api/v1/campaigns?status=`, list items are `CampaignSummaryResponse`, `UpdateChannelRequest.display_order`.

**Commit:** `feat(campaigns): stage counts on the draft read, summary endpoint, list summaries with status filter; viewer gate, channel reorder, stable result order`

---

### Task 5: Orval regen, manual stages, bulk gestures (frontend)

**Regen** — `cd frontend && pnpm generate:api`; revert version-stamp-only churn; keep the new/changed models (`StageCountsResponse`, `CampaignSummaryResponse`, `BulkStageOverrideRequest`, `BulkRemoveResultsRequest`, `kind` fields, `parent_stage_id` on the two requests, `display_order` on `UpdateChannelRequest`, list response type) and the new generated hooks under `frontend/src/shared/lib/api/campaigns/`. Commit the regen separately: `chore(frontend): regen API types for stage gates`.

**Modify — types and lib**
- `frontend/src/features/screen-campaign/types/index.ts:43` — `StageOutcome` adds `"pending"`; add `export type StageKind = "criteria" | "manual"`; re-export the new generated DTOs.
- `lib/stage-outcomes.ts::tallyStage` — `pending` in `StageTally`, counted, included in `population`.

**Modify — stage form and tiles**
- `components/stage-popover.tsx` — form gains `kind` (default `"criteria"`, or the existing stage's); a two-option segmented control "Criteria / Manual" above the criteria list; when `manual`, the criteria field array is hidden and submitted as `[]`, with the helper text "Hand-picked: compounds start pending; promote the ones to take forward." Both POST and PATCH send `kind`.
- `components/sections/stages-section.tsx` — tiles read `stage.counts` (server) instead of `tallyStage`; a manual tile shows "18 of 63" the same way (`hit` of `population`) with a small "manual" eyebrow; the criteria panel for a manual stage shows the helper text instead of "No criteria yet".
- `components/campaign-filter-bar.tsx` — `OUTCOME_ORDER` and the label/colour maps gain `pending` (neutral blue, label "Pending"); chip visible whenever the selected stage's `counts.pending > 0` or the stage is manual.
- `components/campaign-builder.tsx::selectStage` (:121-130) and the same lens in `campaign-view/index.tsx:55` — pre-select `["hit","miss","untested","pending"]`.
- `components/grid/stage-outcome-cell.tsx` — chip class and label for `pending`.
- `components/popovers/stage-override-popover.tsx` — on a manual stage the primary action reads "Promote"; "Demote" secondary; copy otherwise unchanged.
- `components/preview-as-published-dialog.tsx` — `PublishedStageShape` gains `kind`, counts gain `pending`; the stages table shows kind.

**Add — bulk gestures**
- `components/stage-bulk-menu.tsx` (new; model on `git show 58874366^:frontend/src/features/screen-campaign/components/bulk-decision-menu.tsx`): rendered in the builder toolbar only when draft and a stage is selected; computes `visibleIds` with `rowPassesFilters(r, filters, selectedStageId)`; three actions — Promote all visible, Demote all visible, Clear overrides — each opens an `AlertDialog` with the count and, for promote/demote, a required reason textarea; calls the generated `PUT …/stages/{stage_id}/overrides` hook; invalidates `campaignKeys.detail`.
- Grid bulk remove: in `grid/results-grid.tsx` enable AG Grid multi-row selection in draft (`rowSelection="multiple"`), and a "Remove selected (n)" button in the same toolbar calling the generated `POST …/results/bulk-remove` hook after an `AlertDialog` confirm.

**Tests**
- `lib/stage-outcomes.test.ts` — pending tallied into population.
- `components/campaign-filter-bar.test.ts` — a pending row passes when the chip is on; excluded when off.
- `components/sections/stages-section.test.tsx` — tiles render from `counts`; manual tile shows the eyebrow.
- `components/stage-bulk-menu.test.tsx` (new) — visible ids follow the filter; confirm sends `{result_ids, outcome, reason}`; clear sends `outcome: null`.

**Commit:** `feat(screen-campaign): manual stages, pending outcome, bulk promote/demote and bulk remove`

---

### Task 6: Summary-driven list, parent select on the stage_name dialogs, channel reorder (frontend)

**Modify**
- `hooks/use-campaigns.ts::useCampaigns` (:34) — the list now returns `CampaignSummaryResponse`; type it from the generated list response; add an optional `status` param passed as a query arg; add `useCampaignSummary(campaignId)` over the new `GET …/summary` hook with key `campaignKeys.summary(id)`.
- `components/campaign-list.tsx` — `c.channels.length` stays; `c.results?.length` → `c.result_count`; a status filter (segmented: All / Draft / Closed / Superseded) above the table driving the `status` param. Update `frontend/src/features/research-organization/components/project-detail.tsx:119` and `app/(dashboard)/projects/[id]/campaigns/page.tsx` only if their props change.
- `components/add-from-runs-dialog.tsx` — under "Save criteria as stage", a parent select (other stages of the campaign; same options shape as `stage-popover.tsx`'s parent select, excluding none) sending `parent_stage_id`. `components/channel-popover.tsx` mirror-protocol "Also create stage": same parent select.
- `components/sections/channels-section.tsx` — up/down arrow buttons per readout row (draft only) that PATCH `display_order` via the generated update-channel hook, swapping with the neighbour; disabled at the ends.
- Any component that reads `campaign.results` from the list payload (grep `useCampaigns(` consumers, e.g. `add-from-campaign-dialog.tsx`) switches to `result_count` or fetches the full campaign when it actually needs rows.

**Tests**
- `hooks/use-campaigns.test.tsx` — `status` forwarded; summary hook keyed.
- `components/campaign-list.test.tsx` (create if absent) — renders `result_count`; status filter changes the query.
- `components/add-from-campaign-dialog.test.tsx` — still passes after the list type change.

**Commit:** `feat(screen-campaign): summary-driven campaign list with status filter, stage parent on import dialogs, readout reorder`

---

### Task 7: Whole-branch verification and hand-off

- Backend: `cd backend && uv run pytest tests/unit -q`; `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration tests/api -q`; `uv run ruff check src`. Pre-existing failures per `docs/backlog/pre-existing-test-failures.md` and `test-molecules-api-drift.md`.
- Frontend: `cd frontend && pnpm vitest run && pnpm exec biome check src && pnpm exec tsc --noEmit -p .`.
- Dev DB is at migration 077 (`uv run alembic current`).
- One whole-branch review, one fix wave, one scoped re-review; push; PR against `main` referencing #75 with the D2/D3 contract notes; merge per the owner's instruction; report commit hashes to the consumer session.
