# Campaign Hit Stages and Soft Close — Design Spec

**Date:** 2026-09-11
**Status:** design approved in chat; spec pending user review
**Supersedes parts of:** `docs/superpowers/specs/2026-05-10-screen-campaign-design.md` (§3 lifecycle, §5 close/e-signature, §6 published surface, channel `hit_threshold`)

---

## 1. Purpose

A screen campaign today has a flat list of readouts (channels). A readout may carry one
`hit_threshold`, each cell stores a `hit_call`, and the filter bar reports "Hit / Non-hit /
ND" with any-hit semantics across cells. Two problems surfaced while triaging real data:

1. **Ambiguity.** Two protocols that both define an "IC50" readout produce two rows labelled
   "IC50" in the readouts list, and nothing in the list says which protocol each belongs to.
   The grid disambiguates by protocol group header; the list does not.
2. **No triage funnel.** Hit triage is a cascade: primary screen hits → confirmed hits →
   validated hits. Today there is one implicit "hit" notion, defined per readout, so a chemist
   cannot express "Confirmed Hits = Screening Hits AND IC50 < 10 µM" or see how many compounds
   survive each step.

Separately, Close & Sign was designed as stone: an e-signature (currently a client-side stub)
locks the campaign forever and the only way to change anything is to supersede it with a new
campaign. In practice a closed campaign needs small corrections (a late confirmation result, a
decision change), and the auto-published "Hits — <campaign>" collection is not used.

This spec adds **named hit stages** with a parent chain (the funnel), moves hit rules out of
readouts into stages, adds per-stage manual promote/demote, and replaces Close & Sign with a
plain close/reopen toggle. It also removes the auto-published collection.

---

## 2. Decisions (from the brainstorm)

| Question | Decision |
|---|---|
| Do stages own readouts? | **No.** Readouts stay one shared pool, grouped by protocol. A stage is a named set of rules over them. Any stage may reference any readout, including the same IC50 with a tighter cut in a later stage. |
| Where does "hit if" live? | **Stages only.** `CampaignChannel.hit_threshold` and `CampaignMeasurement.hit_call` are removed. Existing thresholds migrate into auto-created single-criterion stages. |
| Parent semantics | **Funnel population.** A child stage is evaluated only on its parent's hits; other compounds are `not_in_stage`. Counts read "of 12 screening hits: 7 hit, 3 miss, 2 untested". One optional parent per stage; branching allowed (two stages may share a parent). |
| Manual override | **Per-stage promote/demote with a required reason**, audited, shown as overridden. |
| Combination inside a stage | AND of all criteria. OR is out of scope. |
| Missing data | A compound with no usable value for any criterion is `untested`, not a miss. |
| Close & Sign | **Plain close / reopen toggle, no e-signature.** Close takes an optional note; reopen takes a required reason. Both are audited. Supersede stays. |
| Published collection | **Removed.** Close publishes nothing. |
| Naming | Section title "Hit stages"; entity `CampaignStage`; rule `StageCriterion`. "Readouts" keeps its name. |

---

## 3. Domain model (`cellar.domain.research_organization`)

### 3.1 `CampaignStage` — owned entity of `Campaign`

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | |
| `campaign_id` | UUID | must equal the owning campaign |
| `name` | str | trimmed, non-empty, ≤ 120 chars, unique per campaign case-insensitively |
| `parent_stage_id` | UUID \| None | must be a stage of the same campaign; not self; no cycles (walk the parent chain) |
| `display_order` | int | ≥ 0; new stages append at max+1 |
| `criteria` | list[StageCriterion] | 0..10; every `channel_id` must be a channel of the campaign |

A stage with zero criteria passes its whole population. It is allowed (a scaffold while the
chemist is still building) and the UI flags it as "no criteria yet".

New file: `domain/research_organization/campaign_stage.py` (holds `CampaignStage` and
`StageCriterion`).

### 3.2 `StageCriterion` — frozen value object

| Field | Type | Rules |
|---|---|---|
| `channel_id` | UUID | a readout of the campaign |
| `operator` | str | one of `lt`, `lte`, `gt`, `gte`, `between` |
| `value` | float \| list[float] | numeric for the four comparisons; `[low, high]` with `low <= high` for `between` |

`StageCriterion.is_met(value: float) -> bool` performs the comparison. The numeric comparison
is factored into one module-level function in `domain/shared/hit_criterion.py`
(`compare(operator, value, target) -> bool`) that both `HitCriterion` (still used by run-import
filtering and protocol recommendations) and `StageCriterion` call, so there is one comparison
implementation. The string `in` operator is not accepted on a `StageCriterion`.

Duplicate criteria on the same readout inside one stage are allowed (two bounds on one value
can also be expressed with `between`; no rule prevents either form).

### 3.3 `StageOverride` — owned by `CampaignResult`

| Field | Type | Rules |
|---|---|---|
| `result_id` | UUID | owning result |
| `stage_id` | UUID | a stage of the campaign |
| `forced_outcome` | `StageOutcome` | only `hit` or `miss` |
| `reason` | str | required, non-empty |
| `overridden_by` | UUID | user id |
| `overridden_at` | datetime | UTC |

`CampaignResult.stage_overrides: dict[uuid.UUID, StageOverride]` keyed by `stage_id`.
Methods: `set_stage_override(stage_id, forced_outcome, reason, by)`,
`clear_stage_override(stage_id)`, `remove_overrides_for_stage(stage_id)`.

### 3.4 Enums (`enums.py`)

```python
class StageOutcome(StrEnum):
    HIT = "hit"
    MISS = "miss"
    UNTESTED = "untested"
    NOT_IN_STAGE = "not_in_stage"

class CheckVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNTESTED = "untested"
```

`HitCall` is deleted (its only consumers were the cell `hit_call`, the cell override, and the
run-import carrier, which switches to a bool).

### 3.5 `Campaign` aggregate changes

New collection: `stages: list[CampaignStage]`.

| Method | Guard | Behaviour |
|---|---|---|
| `add_stage(stage)` | draft | validates ownership, name uniqueness, parent, criteria channels; appends |
| `update_stage(stage_id, *, name=UNSET, parent_stage_id=UNSET, criteria=UNSET, display_order=UNSET)` | draft | same validation; `criteria` is replaced whole (never patched per item) |
| `remove_stage(stage_id)` | draft | `ConflictError` if any other stage has it as parent; removes it and every result's override for it |
| `remove_channel(channel_id)` | draft | existing behaviour **plus** strips every criterion referencing the channel from every stage |
| `find_stage(stage_id)` | — | helper |
| `close(*, closed_by, note, source_protocols)` | draft | replaces the signature variant; requires ≥1 result and ≥1 channel as today |
| `reopen(*, reopened_by, reason)` | closed only | `ValidationError` if not closed (superseded cannot be reopened); status → draft; clears `closed_at`, `closed_by`, `close_note`; emits `CampaignReopened` |

Removed from the aggregate: `publishes_collection`, `published_collection_id`,
`signature_id`, `set_published_collection()`.
Added: `close_note: str | None`.

Events (`events.py`):

```python
class CampaignClosed(DomainEvent):      # changed
    closed_by: uuid.UUID
    note: str | None

class CampaignReopened(DomainEvent):    # new
    reopened_by: uuid.UUID
    reason: str
```

`CampaignPublishedCollectionCreated` is deleted.

### 3.6 Evaluation — `domain/research_organization/stage_evaluation.py`

Pure functions, no I/O.

```python
@dataclass(frozen=True)
class StageCheck:
    channel_id: uuid.UUID
    verdict: CheckVerdict

@dataclass(frozen=True)
class StageResultOutcome:
    stage_id: uuid.UUID
    outcome: StageOutcome
    overridden: bool
    override_reason: str | None
    checks: tuple[StageCheck, ...]

def evaluate_stages(campaign: Campaign) -> dict[uuid.UUID, dict[uuid.UUID, StageResultOutcome]]:
    """result_id -> stage_id -> outcome"""
```

Algorithm, per result, stages visited parents-first (recursive with memo; the parent links
form a forest so this terminates):

1. If the stage has a parent and the parent's **final** outcome (after override) is not `hit`
   → `not_in_stage`, `checks = ()`.
2. Otherwise evaluate each criterion against the result's measurement for that channel:
   - no measurement, or `value_qualifier in {nd, excluded}`, or `value is None` → `untested`
   - else `pass` if `criterion.is_met(value)` else `fail`
3. Combine: any `fail` → `miss`; else any `untested` → `untested`; else `hit`.
4. Apply override: if the result has an override for this stage, `outcome = forced_outcome`,
   `overridden = True`. An override applies even when step 1 produced `not_in_stage` (a forced
   hit pulls the compound into the stage and therefore into its children's population).

Censored values (`<`, `>` qualifiers) are compared by their numeric value, exactly as the
current `_compute_hit_call` does. The channel's existing `qualifier_handling` remains the knob
for excluding or clamping censored data. A `ponytail:` comment in the evaluator names this as
the known simplification.

Worked example (68 compounds):

| Stage | Parent | Criteria | Population | hit | miss | untested | not_in_stage |
|---|---|---|---|---|---|---|---|
| Screening Hits | — | `% Inhibition (EGFR) >= 50` | 68 | 12 | 56 | 0 | 0 |
| Confirmed Hits | Screening Hits | `IC50 (NadD-Sumo) < 10` | 12 | 7 | 3 | 2 | 56 |

`population = hit + miss + untested`. For a root stage the population is every result.

---

## 4. Lifecycle: soft close

Statuses stay `draft → closed → superseded`. `closed` still means read-only: the existing
`CampaignLockGuard`, the repository `is_locked`, and the DB trigger keep blocking writes to
results, measurements, and (new) stages and overrides.

| Action | From | To | Input | Notes |
|---|---|---|---|---|
| Close | draft | closed | `note: str \| None` | same re-resolve + `source_protocols` snapshot + unit repair as today; no signature, no collection |
| Reopen | closed | draft | `reason: str` (required) | clears close metadata; audited via `CampaignReopened` |
| Supersede | closed | superseded | unchanged | superseded campaigns cannot be reopened |

The header shows "Closed by <name> on <date>" and the note when present. The "Close & Sign"
button becomes "Close"; closed campaigns show "Reopen".

---

## 5. Removed concepts

| Removed | Where |
|---|---|
| `CampaignChannel.hit_threshold` | domain, DTOs (`AddChannelRequest`, `UpdateChannelRequest`, `CampaignChannelResponse`), ORM column, published JSON, channel popover, mirror-protocol threshold copy, run-import `existing.hit_threshold = cfg.hit_threshold` persistence |
| `CampaignMeasurement.hit_call` + `HitCall` enum | domain, `CampaignMeasurementResponse`, `OverrideCellRequest.hit_call`, `OverrideResultCellCommand.hit_call`, `_compute_hit_call` in `channel_resolution.py`, ORM column, published JSON, override modal hit-call select, grid `hitCall` prop |
| E-signature | `signature_id`, `signature_meaning` on command/DTO/aggregate/ORM/published JSON; `CloseSignDialog`; header signature slice |
| Auto-published collection | `publishes_collection`, `published_collection_id`, close step 9, `CampaignPublishedCollectionCreated`, `PublishedCollectionLink` card, create-dialog toggle, close-dialog toggle, published JSON `published_collection` |

`Collection.freeze()` / `is_frozen` / `derived_from_campaign_id` become unused by any use case.
They are left in place and recorded in `docs/backlog/` as a cleanup item; removing them is not
part of this change.

Run import keeps `ChannelImportConfigDTO.hit_threshold`, `use_for_filter`, `filter_mode` and
`scope` as **import-time filtering only**. Nothing about hits is persisted on channels or cells
any more.

---

## 6. Application layer

New use cases (`application/research_organization/`):

| File | Command | Behaviour |
|---|---|---|
| `add_campaign_stage.py` | `AddCampaignStageCommand(workspace_id, campaign_id, name, parent_stage_id, criteria)` | `require_editor`; load; `campaign.add_stage`; save; commit |
| `update_campaign_stage.py` | `UpdateCampaignStageCommand(..., stage_id, name=UNSET, parent_stage_id=UNSET, criteria=UNSET, display_order=UNSET)` | UNSET sentinel as in `UpdateCampaignChannel`; criteria replaced whole |
| `remove_campaign_stage.py` | `RemoveCampaignStageCommand(..., stage_id)` | `campaign.remove_stage`; `ConflictError` → 409 when children exist |
| `set_stage_override.py` | `SetStageOverrideCommand(..., result_id, stage_id, forced_outcome: StageOutcome \| None, reason: str \| None, user_id)` | `None` clears; otherwise requires reason; `hit`/`miss` only |
| `reopen_campaign.py` | `ReopenCampaignCommand(workspace_id, campaign_id, user_id, reason)` | `campaign.reopen`; save; commit; dispatch |

Changed use cases:

| File | Change |
|---|---|
| `close_campaign.py` | command becomes `(workspace_id, campaign_id, user_id, note)`; drop `collection_repo` dependency and step 9; `campaign.close(closed_by, note, source_protocols)` |
| `get_campaign.py` | `GetCampaignResult` gains `stage_outcomes` (from `evaluate_stages`) |
| `get_published_campaign.py` | serialize `stages` (with criteria and counts) and per-result `stage_outcomes`; drop `signature`, `published_collection`, channel `hit_threshold`, measurement `hit_call` |
| `add_results_from_runs.py` | stop writing `hit_threshold` onto channels and `hit_call` onto cells; carrier uses `is_hit: bool`; new optional `stage_name`: when given and at least one config has `use_for_filter and hit_threshold`, create a `CampaignStage(name=stage_name, parent=None, criteria=[one per such config, bound to the created/existing channel])`; name collision → `ValidationError` |
| `mirror_protocol_channels.py` | stop copying recommended criteria into `hit_threshold`; new optional `stage_name`: map each `recommended_hit_criteria` entry to the channel created/found for `(protocol, readout_name, intercept_key)` using the existing `_match_recommended_threshold` matching; if ≥1 maps, create the stage; outcome gains `stage_created: bool` |
| `override_result_cell.py` | drop `hit_call` |
| `channel_resolution.py` | drop `_compute_hit_call` and `hit_call=` kwargs; the comparison moves to `domain/shared/hit_criterion.compare` |
| `create_campaign.py` | drop `publishes_collection` |
| `add_campaign_channel.py`, `update_campaign_channel.py` | drop `hit_threshold` |

DI (`infrastructure/di/`) registers the five new use cases and drops `collection_repo` from
`CloseCampaign`.

---

## 7. API

New router `interface/routes/campaigns_stages.py` (mirrors `campaigns_channels.py`; editor
role for mutations, viewer for reads; all return `CampaignResponse`):

```
POST   /api/v1/campaigns/{campaign_id}/stages
       {name, parent_stage_id?, criteria: [{channel_id, operator, value}]}
PATCH  /api/v1/campaigns/{campaign_id}/stages/{stage_id}
       {name?, parent_stage_id?, criteria?, display_order?}     # omitted = unchanged; null parent clears
DELETE /api/v1/campaigns/{campaign_id}/stages/{stage_id}       # 409 when children exist
PUT    /api/v1/campaigns/{campaign_id}/results/{result_id}/stages/{stage_id}/override
       {outcome: "hit" | "miss", reason}
DELETE /api/v1/campaigns/{campaign_id}/results/{result_id}/stages/{stage_id}/override
```

Changed routes:

```
POST /api/v1/campaigns/{campaign_id}/close     {note?}          # CloseCampaignRequest loses signature_* and publishes_collection
POST /api/v1/campaigns/{campaign_id}/reopen    {reason}         # new, in campaigns.py next to close
POST /api/v1/campaigns/{campaign_id}/add-from-runs      AddFromRunsRequest.stage_name?: str
POST /api/v1/campaigns/{campaign_id}/channels/mirror-protocol   MirrorProtocolRequest.stage_name?: str
```

Response DTOs (`_campaign_dtos.py`):

```python
class StageCriterionDTO(BaseModel):
    channel_id: uuid.UUID
    operator: str
    value: float | list[float]

class CampaignStageResponse(BaseModel):
    id: uuid.UUID
    name: str
    parent_stage_id: uuid.UUID | None
    display_order: int
    criteria: list[StageCriterionDTO]

class StageCheckResponse(BaseModel):
    channel_id: uuid.UUID
    verdict: str                      # pass | fail | untested

class StageOutcomeResponse(BaseModel):
    stage_id: uuid.UUID
    outcome: str                      # hit | miss | untested | not_in_stage
    overridden: bool
    override_reason: str | None = None
    checks: list[StageCheckResponse]

class CampaignResultResponse(BaseModel):
    ...                               # unchanged fields
    stage_outcomes: list[StageOutcomeResponse]

class CampaignResponse(BaseModel):
    ...                               # minus signature_id, publishes_collection, published_collection_id
    close_note: str | None
    stages: list[CampaignStageResponse]
```

`CampaignResponse.from_domain(campaign)` calls `evaluate_stages(campaign)` itself, so the
routes that already build a `CampaignResponse` need no change. Outcomes are never persisted;
the evaluator is pure and cheap (results × stages × criteria). Funnel counts are tallied
client-side from `stage_outcomes`; they appear server-side only in the published JSON.

`PATCH .../stages/{stage_id}` distinguishes omitted from `null` through Pydantic's
`model_fields_set`, exactly as `UpdateChannelRequest` does.

Error mapping is the existing one: `ValidationError` → 400, `ConflictError` → 409,
`DataLockedError` → 423, `NotFoundError` → 404.

---

## 8. Persistence and migration 074

ORM (`infrastructure/persistence/sqlalchemy/research_organization/models.py`):

| Table | Columns | Constraints |
|---|---|---|
| `campaign_stage` | `id`, `campaign_id` FK→campaign CASCADE, `name` varchar(120), `parent_stage_id` FK→campaign_stage RESTRICT nullable, `display_order` int, `criteria` JSONB (list of `{channel_id, operator, value}`), `created_at`, `updated_at` | unique `(campaign_id, lower(name))` as a functional unique index; index on `campaign_id` |
| `campaign_stage_override` | `id`, `result_id` FK→campaign_result CASCADE, `stage_id` FK→campaign_stage CASCADE, `forced_outcome` varchar(16), `reason` text, `overridden_by` uuid, `overridden_at` timestamptz, `created_at`, `updated_at` | unique `(result_id, stage_id)` |

Relationships: `CampaignModel.stages` (cascade delete-orphan, ordered by `display_order`);
`CampaignResultModel.stage_overrides` (cascade delete-orphan). Repository `_update_model`
reconciles stages by id exactly like channels, and overrides by `(result_id, stage_id)` inside
`_result_update_model`.

Migration `074_campaign_hit_stages.py` (revises `073_molecules_inchi_key_unique`), steps in
execution order:

1. Create the two tables and indexes.
2. Data: for every `campaign_channel` with a non-null `hit_threshold` whose operator is not
   `in`, insert one `campaign_stage` with `name = label || ' hits'`, `parent_stage_id = NULL`,
   `display_order` = channel `display_order`, and `criteria` = one entry
   `{channel_id, operator, value}`. Name collisions inside a campaign get a ` (2)`, ` (3)` …
   suffix via `row_number() over (partition by campaign_id, lower(label))`. Manual `hit_call`
   overrides on cells are **not** migrated (documented in `docs/backlog/`). This step runs
   before the triggers exist so stages can be written for closed campaigns too.
3. Extend `reject_locked_campaign_write()` with two branches: `campaign_stage` (status via
   `campaign_id`) and `campaign_stage_override` (status via `campaign_result → campaign`).
   Create `BEFORE INSERT OR UPDATE OR DELETE` triggers on both tables, same shape as 027.
4. Drop columns: `campaign_channel.hit_threshold`, `campaign_measurement.hit_call`,
   `campaign.signature_id`, `campaign.publishes_collection`, `campaign.published_collection_id`.
5. Add `campaign.close_note` text nullable.

Downgrade reverses the order: drop `close_note`, recreate the dropped columns (data not
restored), drop the triggers and the trigger-function branches, drop the tables.

---

## 9. Published JSON (DAIKON contract)

`GET /campaigns/{id}/published` and `/preview-published`:

- Remove `signature`, `published_collection`, `channels[].hit_threshold`,
  `results[].measurements[].hit_call`.
- Add `close_note`.
- Add `stages[]`: `{id, name, parent_stage_id, display_order, criteria[], counts: {population,
  hit, miss, untested, not_in_stage, overridden}}`.
- Add `results[].stage_outcomes[]` with the same shape as the API response.

`backend/tests/api/test_campaign_published_contract.py` is updated to the new contract.

---

## 10. Frontend (`frontend/src/features/screen-campaign/`)

Types: regenerate orval (`pnpm generate:api`, revert version-stamp-only churn). In
`types/index.ts` drop `HitCall`, add `StageOutcome` and `CheckVerdict` string unions, re-export
the new generated DTOs.

### 10.1 Readouts section (`sections/channels-section.tsx`, `channel-popover.tsx`)

- Group rows by protocol with a small protocol sub-heading, reusing
  `useProtocolSummaries(undefined, { includeAll: true })` and `groupBy` exactly as
  `grid/results-grid.tsx` does.
- Row text becomes `label · DR/RD · selection rule` (no threshold text).
- Popover: remove hit-threshold fields; in edit mode show a locked line
  "Protocol: <name> › <readout>" under the existing "Source" line.
- Mirror-protocol popover: when the chosen protocol has recommended criteria, show a checkbox
  "Also create stage" with a name input defaulting to `<Protocol name> hits`; sends `stage_name`.

### 10.2 Hit stages section — new `sections/stages-section.tsx`

```
HIT STAGES                                               [+ Stage]
  [All 68]  [Screening Hits 12]  [Confirmed Hits 7 ↳ after Screening Hits]
  Confirmed Hits
    IC50 · NadD-Sumo        < 10 uM                          ...
    + Criterion            Parent: Screening Hits    Rename   Delete
```

- Tabs sorted by `display_order`. Every tab shows its hit count (tallied from
  `stage_outcomes`) regardless of selection; a child tab shows "↳ after <parent>" as a subline
  or tooltip.
- Selected stage state `selectedStageId: string | null` lives in `CampaignBuilderV2` and
  `CampaignView` next to `filters`, and is passed to the filter bar and grid. Default `null`
  ("All").
- The panel under the tabs lists the selected stage's criteria as rows
  (`<readout label> · <protocol> <operator> <value> <unit>`), with the parent, rename, and
  delete affordances. "+ Stage" and edit open one popover form (`stage-popover.tsx`) holding
  name, parent select (other stages, excluding descendants), and the criteria list; one
  explicit Save sends one POST or PATCH with the whole criteria list.
- Criterion editor: readout picker showing `protocol › readout (unit)` so duplicates are
  unambiguous; operator select; one value input, or two for `between`.
- Delete is refused with the backend's 409 message when children exist. Deleting the
  selected stage resets the selection to "All".
- Read-only mode (closed) renders tabs and criteria without affordances.

### 10.3 Filter bar (`campaign-filter-bar.tsx`)

- `CampaignFilters.hitStatus` becomes `stageOutcomes: Set<"hit" | "miss" | "untested" |
  "not_in_stage">`. `computeRowHitStatus` is replaced by a lookup of the row's outcome for the
  selected stage.
- When a stage is selected: chips `Hit n · Miss n · Untested n · Not in stage n`. Selecting a
  tab pre-selects `{hit, miss, untested}` so the population is shown and the rest hidden;
  the chemist can toggle any chip.
- When "All" is selected: the outcome chips are hidden; decision chips and Overridden remain.
- "Overridden" matches rows with any manually overridden cell, plus, when a stage is selected,
  rows with an override on that stage.
- `rowPassesFilters(result, filters, selectedStageId)` is the single function both the grid
  external filter and `BulkDecisionMenu` use, so "select all confirmed hits" stays: stage tab →
  Hit chip → bulk Selected.

### 10.4 Grid (`grid/results-grid.tsx`)

- `CompoundValueCell` prop `hitCall` becomes `verdict: "pass" | "fail" | "untested" | null`;
  the chip renders for `pass` / `fail` only. The verdict comes from the selected stage's
  `checks` for that channel; `null` when no stage is selected or the stage doesn't check it.
- New "Stage" column, pinned right before Decision, present only when a stage is selected:
  outcome chip (hit / miss / untested / not in stage) with an "overridden" marker. In draft it
  opens `stage-override-popover.tsx`: computed outcome, failing criteria summary, actions
  "Promote to hit" / "Demote to miss" with a required reason, and "Clear override" when one
  exists. Read-only in closed view.
- Protocol group headers stay as they are.

### 10.5 Header, close, reopen (`sections/header-strip.tsx`, `close-sign-dialog.tsx`, `campaign-view/index.tsx`, `create-campaign-dialog.tsx`)

- "Close & Sign" → "Close"; `CloseSignDialog` becomes `close-campaign-dialog.tsx`: title,
  optional note, Close button. The signature and publish-collection steps are deleted.
- Closed view: "Reopen" button opens a dialog with a required reason (same shape as the run
  unlock dialog in `screening-assay/components/run-detail.tsx`); on success the page switches
  back to the builder because `status` is `draft` again.
- Closed metadata line shows closed-by, date, and note; the signature slice is removed.
- `campaign-view/published-collection-link.tsx` and the "Published collection" card are
  deleted; the "Source protocols" card stays.
- Create dialog drops the publish toggle.
- Preview-as-published dialog drops the hit chip and adds a stages table (name, parent,
  criteria count, counts).

### 10.6 Add-from-runs dialog (`add-from-runs-dialog.tsx`)

When the chemist enters at least one filter criterion, show "Save criteria as stage" with a
name input defaulting to the protocol name plus " hits" (or "Imported hits" when runs span
protocols); sends `stage_name`.

---

## 11. Testing

Backend unit (`tests/unit/domain/research_organization/`):
- `test_campaign_stage.py`: name rules, criterion validation (operators, between bounds, no
  `in`), `is_met`.
- `test_stage_evaluation.py`: AND semantics; untested precedence over hit but not over miss;
  root population; child `not_in_stage`; override wins and feeds children; branching parents;
  parents-first regardless of `display_order`; zero-criteria stage.
- `test_campaign.py`: add/update/remove stage guards; cycle and self-parent refusal; delete
  with children → `ConflictError`; `remove_channel` strips criteria and leaves other criteria;
  `close` without signature; `reopen` from closed clears metadata and emits event; reopen from
  draft/superseded refused.
- `test_campaign_result.py`: override set/clear/remove-for-stage.
- `tests/unit/domain/shared/test_hit_criterion.py`: `compare` covers every operator.

Backend unit application (`tests/unit/application/research_organization/`): one file per new
use case; updated `test_close_campaign.py` (no collection, note stored), `test_add_campaign_channel.py`,
`test_update_campaign_channel.py`, `test_create_campaign.py`, `test_get_published_campaign.py`,
`test_refresh_campaign_from_sources.py`; `test_add_results_from_runs.py` and
`test_mirror_protocol_channels.py` gain `stage_name` cases (created, skipped when nothing
maps, name collision).

Backend integration (needs `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`):
- `test_campaign_repository.py`: stages and overrides round-trip; reconcile on update
  (rename, criteria replace, override clear).
- `test_close_campaign.py`: close → stage write blocked by trigger (`check_violation`) →
  reopen → write allowed.
- Migration 074 data step, following `tests/integration/test_migration_069_backfill.py`:
  seed two channels with thresholds (one name collision) on a closed campaign, run the
  upgrade, assert two stages with suffixed names and the columns gone.

Backend API (`tests/api/`): `test_campaigns_api.py` gains stages CRUD, override PUT/DELETE,
reopen (200 from closed, 400 from draft, 400 from superseded), close body without signature,
423 on stage write when closed; `test_campaign_published_contract.py` updated.

Frontend (vitest): `campaign-filter-bar.test.ts` for tallies and `rowPassesFilters` with stage
outcomes; `stages-section.test.tsx` for tab counts and parent subline; `channels-section.test.tsx`
for protocol grouping. Existing `use-campaigns.test.tsx` and `snapshot-adapter.test.ts` are
updated for the DTO changes. `pnpm lint` and `pnpm typecheck` gate by exit code.

---

## 12. Sequencing

Layer order per CLAUDE.md: Domain → domain tests → persistence → integration tests →
application → API → API tests → UI. Suggested sessions:

1. **Domain + persistence.** `campaign_stage.py`, `stage_evaluation.py`, enums, events,
   aggregate/result changes, `hit_criterion.compare`; ORM, repository, migration 074; unit +
   integration tests.
2. **Application + API.** Five new use cases, changed use cases, DTOs, routers, DI, published
   JSON; API tests; contract test.
3. **Frontend: readouts + stages.** orval regen, types, readouts grouping and popover cleanup,
   stages section and popover, filter bar, grid verdicts and Stage column, override popover,
   add-from-runs and mirror `stage_name`.
4. **Frontend: close/reopen + removals + docs.** Close dialog, reopen dialog, header, view
   cards, create dialog, preview dialog; `docs/domain-model/05-research-organization.md`
   Campaign section; backlog entries (Collection freeze cleanup; unmigrated hit-call
   overrides); `docs/implementation-status.md`.

Each session ends green (backend `uv run pytest`, frontend `pnpm lint && pnpm typecheck &&
pnpm test`) and committed with explicit pathspecs.

---

## 13. Out of scope (follow-ups)

- Curve-quality criteria (R², curve class) and computed criteria (selectivity ratios).
- OR / n-of-m logic inside a stage.
- Creating a collection on demand from a stage's hits or from the Selected set.
- Stage templates shared across campaigns or projects.
- Removing `Collection.freeze` / `is_frozen` / `derived_from_campaign_id` and the
  `is_frozen` fields on the collections API.
- A real reopen/close history view (the audit trail already records both events).
