# Hit-stage follow-ups — design

**Date:** 2026-09-11
**Status:** approved in chat 2026-09-11 (user: "looks good, go ahead"); ask 8 deferred to its own spec
**Builds on:** `2026-09-11-campaign-hit-stages-and-soft-close-spec.md`, `2026-09-11-remove-campaign-decisions-spec.md`
**Source of the asks:** `~/workspace/daikon-gen3/docs/superpowers/handoffs/2026-09-11-chemcellar-asks-hit-stages-followups.md` (nine asks + hygiene), verified against HEAD `3e3ed6b7` on 2026-09-11.

---

## 0. Verification — what the code contradicts

Every claim in the handoff was opened. These are the corrections that change the design; everything else held.

| Ask | Handoff says | Code says |
|---|---|---|
| 1 | Resolver branches on the readout definition's kind | Branches on the channel's persisted `source_kind` (`channel_resolution_query.py:102`). `add_campaign_channel` accepts `source_kind` from the body unvalidated, so a `readout_data` channel can point at a dose-response definition. Fallback therefore lives on the `DOSE_RESPONSE_CURVE` channel branch. |
| 1 | — | `resolve_intercept` (`run_aggregation.py:121`) returns ND for any candidate without `intercept_values` when the channel has an `intercept_key`. A readout row on a DR channel would resolve ND today even if it were a candidate. One guard fixes it. |
| 1 | — | `molecule_activity_service.py` already has `ActivityValue.source = "readout" \| "curve"` and a batched raw-layer query (`find_aggregated_by_molecules`). The compound-page fallback is one extra call; the marker exists. |
| 2 | 422 "carrying the readout name" | `plan_summary_rows` raises nothing; cell errors are data and the import returns 201 with an `errors` array. A mapping-level refusal is new behaviour on this path (parse failure and row cap are the only 422s today). |
| 2 | `latest_approved_run` breaks ties by run date | `run_date` is the sort key; there is no tie-break. Same-run rows resolve by unordered DB row order. Nothing filters on `run_approved` despite the name. |
| 5 | Menu deleted in `af4f3d9c` | Deleted in `58874366` (`af4f3d9c` is the merge). Recover with `git show 58874366^:frontend/src/features/screen-campaign/components/bulk-decision-menu.tsx`. |
| 7 | Five paths resolve unrestricted | Nine: refresh, close, add-channel, mirror, `add_result_row`, `recompute_channel`, `update_campaign_channel`, `add_results_from_campaign`, `add_results_from_collection`. `ChannelResolver.resolve` has no run parameter at all. |
| 7 | Campaign "knows its source runs" via `compound_sources` | `compound_sources` is a read-time projection over per-row `CampaignResult.added_from` (`_campaign_dtos.py:449`, duplicated in `get_published_campaign.py:264`). The run set must be derived from rows. |
| 7 | — | Reopen keeps every frozen cell, snapshot and override; it only flips status and clears close metadata. The "reopen → refresh pulls newer runs" hazard is real. |
| 8 | Eager loading is a repo loader chain | `lazy="selectin"` on the models, so the **list** endpoint hydrates every result and measurement too. |
| 9 | Duplicate name fails "before any cell is written" | True for add-from-runs; mirror resolves every measurement first and checks the name last. |

Also confirmed: no import path reads `is_calculated`; `ImportPlateData` (inventory) writes well-less rows through `BulkCreateReadoutData`; the CDD plate import writes no readout rows.

---

## 1. Decisions (defaults unless the owner overrides)

| # | Question | Decision |
|---|---|---|
| D1 | Fitted vs reported when both exist | **Fitted wins, decided post-QC.** Candidates of both kinds pass the channel's `qc_filter` (readout rows carry `run_approved` and z′ too). If any curve survives QC — regardless of curve class; an inactive curve is a measurement and resolves ND as today — only curves are candidates. If no curve survives, the QC-passing endpoint rows go through the selection rule. (Requester's note 2026-09-11: pre-QC would resolve ND for a compound whose only curves are filtered out while a reported endpoint exists.) |
| D2 | Bulk override route shape | **One `PUT`** with `outcome: "hit" \| "miss" \| null` (null clears). Not the PUT + DELETE pair. Mirrors `SetStageOverrideCommand.forced_outcome`. |
| D3 | `GET /campaigns` payload | Switches to `CampaignSummaryResponse` (no results). Contract change for any list consumer; the requester asked for it. |
| D4 | Run scope for resolution (ask 7) | Union of `RunRef.run_id` over all rows' `added_from`. Empty set → unrestricted (today's behaviour). Per-channel opt-out `resolve_from_all_runs`. Rows added manually or from a collection in a run-seeded campaign are restricted too. |
| D5 | Ask 8 (paginated results) | **Deferred to its own spec.** It changes the aggregate's persistence model (stop eager-loading results; per-page evaluation or persisted outcomes, which the hit-stages spec ruled out). The stable-order fix from the backlog lands now. |
| D6 | Reopen role | Stays editor, symmetric with close. |
| D7 | Manual stage overrides | Promote (→ hit) and demote (→ miss) both allowed on a manual stage; `pending` is the untouched base. No override special-casing. |
| D8 | Published document provenance | `measurements[].source` gains `curve_id` and `readout_id` (nullable), mirroring the API DTO. "Reported" = readout_id set on a DR channel. No new vocabulary. |

---

## 2. Batches

Three branches, each with one whole-branch review at the end (no per-task reviews). Order matters: batch 1's shape rule must precede batch 1's fallback rule; batch 3 touches every resolver call site so it goes last.

| Batch | Branch | Asks | Migration |
|---|---|---|---|
| 1 | `feat/import-data-shape` | 2 → 3 → 1 | none |
| 2 | `feat/stage-gates` | 4 → 5 (+ bulk remove) → 9 → 6 (+ hygiene) | 077 `campaign_stage.kind` |
| 3 | `feat/resolution-run-scope` | 7 | 078 `campaign_channel.resolve_from_all_runs` |
| — | own spec later | 8 | — |

---

## 3. Batch 1 — import data shape

### 3.1 Ask 2 — refuse direct entry on a calculated readout

**Backend**
- `application/screening/preview_summary_file.py:148-153` — build `readout_by_name` from definitions where `not d.is_calculated`, so the preview never suggests one.
- `application/screening/import_summary_file.py::_execute` and `preview_summary_import.py::_execute` — after `defs_by_id`, every readout id in the mapping whose definition `is_calculated` → `Failure(ValidationError("Readout '<name>' is calculated; its values are computed from other readouts and cannot be imported"))` → 422. Mapping-level, before planning.
- Plate mapper — the same check where the column→readout mapping is validated (`import_plan.py` plan builder; `import_run_readouts.py` for the grid path).
- `bulk_create_readout_data.py::_resolve_readout_definition_id` — per-item error `Item {idx}: readout '<name>' is calculated; values cannot be entered directly`.

**Frontend** — filter `!rd.is_calculated` in `use-summary-import-wizard.ts:91-99`, `use-run-import-wizard.ts:106`, `grid-import-dialog.tsx:47,109`.

**Unchanged** — cross-protocol formulas resolved on read; engine cleanup stays computed-rows-only.

### 3.2 Ask 3 — one run, one shape

Shape is derived, never stored: a run is **welled** when `run.wells` is non-empty, **well-less** when it has raw rows with `well_id IS NULL AND is_computed IS FALSE`, else empty. Computed rows are excluded because the engine writes calculated readouts well-less on welled runs by design.

- `ReadoutDataRepository.has_wellless_rows(workspace_id, run_id) -> bool` (one `EXISTS`).
- `application/screening/run_shape.py` — two guards returning `ConflictError` (409): `refuse_if_welled(run)` and `refuse_if_wellless(readout_repo, ws, run_id)`. Messages name the run's shape.
- Summary import + summary dry-run → `refuse_if_welled`.
- `preview-file`, `repreview-file`, `import-file`, `import-readouts`, `plate-setup` → `refuse_if_wellless` after loading the run.
- `POST /readout-data/bulk` — per item: run has wells and `well_id` is None → error; run has no wells and `well_id` is set → error. `ImportPlateData` (inventory) auto-creates a well-less run and passes no `well_id`, so it stays valid.

### 3.3 Ask 1 — fitted first, reported second, provenance

**Query** (`channel_resolution_query.py`) — the port gains `fetch_endpoint_candidates(workspace_id, channel, molecule_id)` (today's private `_fetch_readout_candidates`, made public; raw layer, `normalization_applied` is None on DR channels already) and a runs-scoped twin. `fetch_candidates` / `fetch_candidates_for_runs` are unchanged: curves for a DR channel, readout rows otherwise.

**Resolver** (`channel_resolution.py::ChannelResolver.resolve`) — after the QC filter, if no candidate remains and the channel is `DOSE_RESPONSE_CURVE`, fetch the endpoint candidates, apply the same QC filter, and continue with those (D1). `add_results_from_runs` applies the same post-QC fallback per molecule on its runs-scoped path so both entry points agree.

**Aggregation** (`run_aggregation.py::resolve_intercept`) — first line: a candidate with `curve_id is None` resolves to `(run.value, EQ)`; there is no intercept to look up. Behaviour-preserving for readout channels (identical result to today's `intercept_key is None` path). The resolver already carries the row's own qualifier (`>32` stays `>32`). `BEST_R_SQUARED` on readout rows degenerates to first-row (r² is −inf for all); acceptable, it is a curve rule.

**Provenance**
- API: nothing new — `CampaignMeasurementResponse` already exposes `source_curve_id` / `source_readout_id`.
- Grid `CompoundValueCell`: a small "reported" marker with tooltip when the channel is DR and `source_readout_id` is set without `source_curve_id`.
- Published JSON `_serialize_measurement`: `source` gains `curve_id`, `readout_id` (D8). Contract fixture updated.

**Compound page and search** (`molecule_activity_service.py:406-416`) — for each `drc:` spec, molecules with no curves are looked up once via `find_aggregated_by_molecules(ws, missing, [(rd_id, None)])` and emitted as `ActivityValue(source="readout", …)`. Export's search rows go through the same service. Sort-by-`drc:` (`molecule_reader.py:410`, curves only) stays as is → backlog note.

**Unchanged** — channel identity and reuse key; the fitter and the four-point rule; numeric readouts.

**Tests** — integration `test_channel_resolution_query.py` (fallback; fitted wins pre-QC; runs-scoped twin); unit `test_channel_resolver.py` (readout candidate on a DR channel with an intercept key resolves to the value and keeps `>`); unit for `molecule_activity_service`; summary/plate/bulk guards (unit with fakes + one integration each); FE cell test for the marker.

---

## 4. Batch 2 — stage gates and reads

### 4.1 Ask 4 — manual stage kind

**Domain**
- `enums.py`: `StageKind(StrEnum) = CRITERIA | MANUAL`; `StageOutcome.PENDING = "pending"`.
- `CampaignStage.kind: StageKind = CRITERIA`; invariant: a `MANUAL` stage has no criteria (`ValidationError` otherwise). `Campaign.update_stage(kind=UNSET)` applies the same invariant.
- `stage_evaluation.py::_evaluate_stage`: in population and `stage.kind is MANUAL` → `checks = ()`, `base_outcome = PENDING`. Overrides apply unchanged; children's population is still "parent final outcome is hit".
- `tally_stage_counts`: add `pending`; population = hit + miss + untested + pending.
- `stage_name` paths (ask 9) create `CRITERIA` stages; reusing a `MANUAL` stage by name is a `ValidationError`.

**Persistence** — migration 077: `campaign_stage.kind varchar(16) NOT NULL DEFAULT 'criteria'`; ORM column; repository maps it.

**API** — `kind` on `CreateStageRequest`, `UpdateStageRequest`, `CampaignStageResponse`; `StageOutcomeResponse.outcome` may be `pending`. Published JSON: `stages[].kind`, `counts.pending`; contract fixture updated (cross-app: the consumer must accept `pending`).

**Frontend** — `StageKind` union in `types/index.ts`; `stage-popover.tsx` gets a Criteria / Manual toggle and hides the criteria editor for manual; `stages-section.tsx` tile already reads "hit of population" (→ "18 of 63"); `stage-outcomes.ts` tallies `pending`; `campaign-filter-bar.tsx` gains a Pending chip and `selectStage` pre-selects it with the population; `stage-outcome-cell.tsx` chip for pending; `stage-override-popover.tsx` leads with "Promote" on a manual stage; `preview-as-published-dialog.tsx` shows kind.

### 4.2 Ask 5 — bulk overrides (+ bulk row removal)

- `SetStageOverrideCommand.result_ids: list[uuid.UUID]` replaces `result_id`. The per-result routes pass a one-element list. Unknown id → `NotFoundError` for the whole call; empty list → `ValidationError`; one transaction, one version bump.
- New route `PUT /api/v1/campaigns/{id}/stages/{stage_id}/overrides` body `{result_ids, outcome: "hit" | "miss" | null, reason?}` → `CampaignResponse` (D2). Existing per-result PUT/DELETE stay.
- `RemoveResultRow` → `result_ids: list`; new route `POST /api/v1/campaigns/{id}/results/bulk-remove` body `{result_ids}` (POST because DELETE bodies are dropped by some proxies). Per-result DELETE stays.
- Frontend: stage-lens toolbar in the builder (draft, stage selected): **Promote all visible · Demote all visible · Clear overrides** over the `rowPassesFilters` rows, confirm dialog with count and required reason — the shape of the deleted `bulk-decision-menu.tsx`. Grid row multi-select + "Remove selected" for bulk removal.

### 4.3 Ask 9 — `parent_stage_id` and reuse on the `stage_name` paths

- `parent_stage_id: uuid | None` on `AddFromRunsRequest`, `MirrorProtocolRequest`, and both commands.
- Both use cases: find an existing stage by case-insensitive name → `campaign.update_stage(id, criteria=…, parent_stage_id=… if given else UNSET)`; else `add_stage(…, parent_stage_id=…)`. Mirror moves the stage step before the resolve loop.

### 4.4 Ask 6 — counts on the draft read, summary read, list

- `CampaignStageResponse.counts: StageCountsResponse {population, hit, miss, untested, pending, not_in_stage, overridden}` from `tally_stage_counts` in `CampaignResponse.from_domain` (the evaluator already runs there). The published document reuses the same shape.
- `CampaignSummaryResponse`: every `CampaignResponse` field except `results`, plus `result_count`. `channels`, `stages` (with counts), `compound_sources`, `source_protocols`, `targets` included.
- `GET /api/v1/campaigns/{id}/summary` → `CampaignSummaryResponse` (viewer). Reuses `GetCampaign`; only the payload shrinks. The repository still hydrates results through `lazy="selectin"` — recorded in backlog with the fix (count subquery + `noload`) rather than done here.
- `GET /api/v1/campaigns` → `PaginatedResponse[CampaignSummaryResponse]` (D3) and gains `status` (repo `find_by_project` / `find_by_workspace` get `status: CampaignStatus | None`).
- Frontend: `campaign-list.tsx` reads `result_count`; a status filter on the list; `stages-section.tsx` tiles read `stage.counts` (the filter-bar chips stay client-side because they count the filtered rows).
- Hygiene in the same batch: `get_published_campaign.py` uses `require_workspace_role(auth, "viewer")`; `UpdateChannelRequest.display_order` + command + up/down arrows in the readouts section; `CampaignModel.results` gets `order_by="CampaignResultModel.id"` (backlog stable-order fix); reopen stays editor (D6).

---

## 5. Batch 3 — resolution honours the campaign's runs (ask 7)

- `Campaign.source_run_ids() -> set[uuid.UUID]` — `RunRef.run_id` over every result's `added_from`. Docstring notes the transitional state: a campaign seeded only from another campaign, a collection or by hand has no `RunRef`s and resolves protocol-wide until its first add-from-runs, after which it narrows to those runs.
- `CampaignChannel.resolve_from_all_runs: bool = False`; migration 078; ORM; `AddChannelRequest`, `UpdateChannelRequest`, `CampaignChannelResponse`; channel popover checkbox "Resolve from all runs of the protocol" with helper text "Off: only the runs this campaign was seeded from".
- `ChannelResolutionQuery.fetch_candidates(..., run_ids: list[uuid.UUID] | None = None)` → `run_id IN (...)` in both branches and the ask-1 fallback.
- `ChannelResolver.resolve(..., run_ids=None)` passes through. Module helper `resolution_run_ids(campaign, channel)`: `None` when the channel opts out or the campaign has no run sources; otherwise the sorted set (D4).
- All nine call sites pass `run_ids=resolution_run_ids(campaign, channel)`. `add_results_from_runs` is already run-scoped and is unchanged.
- Tests: resolver forwards `run_ids`; query filters; one unit case per use case (foreign-run candidate excluded; opt-out includes it); integration reopen → refresh keeps the old run's value when a newer run exists.

---

## 6. Ask 8 — deferred, and why

Server-side `stage_id` / `outcome` filters need every row evaluated (outcomes are not persisted, and the hit-stages spec chose that), so a page cannot be selected in SQL without either persisting outcomes or loading all rows and slicing. A real fix stops the aggregate from eager-loading results (`lazy="selectin"` → explicit loaders), adds a results-page repository method, and moves the grid to the infinite row model with every filter and the ask-5 bulk gesture re-expressed server-side. That is a persistence-model spec of its own. What lands now: stable order (§4.4) and the summary read (§4.4), which answers the header and tile needs the ask cites.

---

## 7. Cross-app contract changes (for the requester)

- Published JSON: `stages[].kind`, `counts.pending`, `stage_outcomes[].outcome` may be `pending`, `measurements[].source.curve_id` / `readout_id`.
- `GET /campaigns` returns summaries (no `results`; `result_count` instead).
- New: `GET /campaigns/{id}/summary`, `PUT /campaigns/{id}/stages/{stage_id}/overrides`, `POST /campaigns/{id}/results/bulk-remove`, `status` on the list, `parent_stage_id` on add-from-runs and mirror-protocol, `kind` on stages, `resolve_from_all_runs` on channels.
- New 409s on summary/plate imports onto a run of the other shape; new 422 on mapping a calculated readout; per-item errors on bulk.

## 8. Process

- One plan document per batch via `superpowers:writing-plans`, executed with subagent-driven development, focused tests per task, one whole-branch review per batch.
- One GitHub issue per batch on `sidxz/cellar`, linked to the project board.
- Explicit-pathspec commits; `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; no session trailer.
- Backend `tests/api` and `tests/integration` need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`. Orval regen per batch with version-stamp churn reverted.
