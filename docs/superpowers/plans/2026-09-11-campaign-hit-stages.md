# Campaign Hit Stages + Soft Close — Implementation Plan (lean)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Named hit stages with a parent-chain funnel and per-stage overrides replace per-readout thresholds and per-cell hit calls; Close & Sign becomes a plain close/reopen toggle; the auto-published collection is removed.

**Architecture:** `CampaignStage` (criteria over shared readouts, optional parent) is a new owned entity of the Campaign aggregate; `StageOverride` is owned by `CampaignResult`. A pure domain evaluator computes per-result outcomes on read; nothing is persisted for outcomes. Two migrations: 074 (additive: tables, triggers, backfill, `close_note`) and 075 (drop the five retired columns) so the intermediate tasks stay green.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / Pydantic v2 / pytest (asyncio auto) — Next.js 16 / React 19 / TanStack Query / AG Grid / vitest / orval.

**Spec:** `docs/superpowers/specs/2026-09-11-campaign-hit-stages-and-soft-close-spec.md` (read it first; every task argues from it).

**Lean format:** this plan gives files, exact names and signatures, test names, and the template to copy. Implementers write the code. No per-task review; one whole-branch review at the end (user ruling).

## Global constraints

- Branch: `feat/campaign-hit-stages`. Commit after every task with explicit pathspecs: `git commit -m "..." -- <paths>` (the working tree carries unrelated user changes: `frontend/next-env.d.ts`, `frontend/AGENTS.md` — never sweep them in). Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never add a `Claude-Session:` trailer.
- Backend commands run from `backend/`: `uv run pytest tests/unit -q`; integration + API: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration tests/api -q` (Docker Desktop must be running). `uv run lint-imports` must stay green (layer rules in `docs/backend-code-guidelines.md`).
- Frontend commands run from `frontend/`: `pnpm lint` (biome, gate by exit code), `pnpm exec tsc --noEmit`, `pnpm test`.
- Backend rules: read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before writing. Railway pattern (`returns.result`), `require_editor` / `require_same_workspace` guards, UoW + repo + dispatcher constructor injection, `Failure(NotFoundError|ValidationError|ConflictError)` never raised across the boundary.
- Error mapping (existing): `ValidationError`→422, `ConflictError`→409, `NotFoundError`→404, `DataLockedError`→423.
- Templates to copy: use case `application/research_organization/add_campaign_channel.py`, `update_campaign_channel.py` (UNSET sentinel), `remove_campaign_channel.py`; router `interface/routes/campaigns_channels.py`; DI `infrastructure/di/_research_organization.py` (`_add_channel` factory + `container.define`); deps `interface/dependencies/_research_organization.py` (`AddCampaignChannelDep = Annotated[...]`); unit-test helpers `tests/unit/application/research_organization/_helpers.py` (`FakeUnitOfWork`, `fake_auth`, `make_campaign_repo`, `FakeResolver`); API helpers in `tests/api/test_campaigns_api.py` (`_create_project`, `_create_empty_campaign`, `_register_molecule`); integration helpers in `tests/integration/application/research_organization/test_close_campaign.py`.
- Frontend rules: generated types only (`frontend/src/shared/lib/api/model`), hand-written hooks or the generated react-query hooks in `shared/lib/api/campaigns/campaigns.ts`; no hand-rolled DTO interfaces. Explicit Save gestures, no autosave. No UUIDs shown to users.

---

## Phase 1 — Domain

### Task 1: Stage value objects and shared comparison

**Files**
- Modify: `backend/src/cellar/domain/shared/hit_criterion.py`
- Modify: `backend/src/cellar/domain/research_organization/enums.py`
- Create: `backend/src/cellar/domain/research_organization/campaign_stage.py`
- Test: `backend/tests/unit/domain/shared/test_hit_criterion.py` (add `TestCompare`), create `backend/tests/unit/domain/research_organization/test_campaign_stage.py`

**Interfaces (produces)**
```python
# hit_criterion.py
def compare(operator: str, value: float, target: float | list[float]) -> bool  # lt/lte/gt/gte/between; ValidationError otherwise
class HitCriterion:  def is_met(self, value: float) -> bool | None   # None for the "in" operator

# enums.py (add only; HitCall is removed in Task 6)
class StageOutcome(StrEnum): HIT="hit"; MISS="miss"; UNTESTED="untested"; NOT_IN_STAGE="not_in_stage"
class CheckVerdict(StrEnum): PASS="pass"; FAIL="fail"; UNTESTED="untested"

# campaign_stage.py
MAX_STAGE_NAME_LEN = 120; MAX_STAGE_CRITERIA = 10
UNSET  # singleton sentinel (same shape as update_campaign_channel._Unset) — domain-owned, reused by Task 9
@dataclass(frozen=True) class StageCriterion(channel_id: uuid.UUID, operator: str, value: float | list[float])
    # __post_init__: operator in {lt,lte,gt,gte,between}; numeric (not bool) or [low, high] with low <= high
    def is_met(self, value: float) -> bool; def to_dict(self) -> dict; @classmethod from_dict(cls, d: dict)
def normalize_stage_name(name: str) -> str   # strip; ValidationError if empty or > 120
@dataclass class CampaignStage(campaign_id, name, display_order, id=uuid4, parent_stage_id=None, criteria: list[StageCriterion]=[])
    # __post_init__: name normalized; display_order >= 0; len(criteria) <= 10
@dataclass(frozen=True) class StageOverride(result_id, stage_id, forced_outcome: StageOutcome, reason: str, overridden_by: uuid.UUID, overridden_at: datetime)
    # forced_outcome must be HIT or MISS; reason stripped non-empty
```

**Tests**
- `TestCompare`: one case per operator incl. boundary equality for lte/gte/between; `in` → `is_met` returns None; unsupported operator raises.
- `test_campaign_stage.py`: criterion operator validation, between bounds, bool rejected, `is_met`, `to_dict/from_dict` round-trip; stage name trimmed / empty / too long; negative display_order; > 10 criteria; override forced_outcome must be hit/miss; empty reason rejected.

- [ ] Write tests → run (fail) → implement → run (pass) → `uv run lint-imports` → commit.

### Task 2: Aggregate — stages and overrides

**Files**
- Modify: `backend/src/cellar/domain/research_organization/campaign_result.py`, `campaign.py`
- Test: `backend/tests/unit/domain/research_organization/test_campaign_result.py`, `test_campaign.py`

**Interfaces (produces)**
```python
# CampaignResult
stage_overrides: dict[uuid.UUID, StageOverride]   # keyed by stage_id (dataclass field, default {})
def set_stage_override(self, *, stage_id, forced_outcome: StageOutcome, reason: str, overridden_by: uuid.UUID) -> StageOverride
def clear_stage_override(self, stage_id) -> bool

# Campaign (constructor gains stages: list[CampaignStage] | None = None)
stages: list[CampaignStage]
def find_stage(self, stage_id) -> CampaignStage | None
def add_stage(self, stage: CampaignStage) -> None                      # draft guard; campaign_id match; duplicate id; unique name (case-insensitive); parent valid (exists, != self, no cycle); criteria channels exist
def update_stage(self, stage_id, *, name=UNSET, parent_stage_id=UNSET, criteria=UNSET, display_order=UNSET) -> CampaignStage   # NotFoundError if missing; same validation; criteria replaced whole
def remove_stage(self, stage_id) -> None                                 # NotFoundError if missing; ConflictError if another stage has it as parent; clears every result's override for it
def remove_channel(self, channel_id) -> None                             # existing behaviour + strip criteria referencing the channel from every stage
```
Guard messages follow `_ensure_draft("add stage")` style. Cycle check walks `parent_stage_id` upward from the proposed parent until None; hitting `stage_id` → `ValidationError("stage parent would create a cycle")`.

**Tests** (`test_campaign.py`): add appends; duplicate name case-insensitive rejected; unknown channel in criteria rejected; parent must exist; self-parent rejected; cycle A→B→A rejected; update replaces criteria whole and re-validates name; remove with child → ConflictError; remove clears overrides on results; remove_channel strips criteria and leaves the others; all guards refuse when not draft. (`test_campaign_result.py`): set/replace/clear override.

- [ ] Tests → implement → pass → commit.

### Task 3: Evaluator

**Files**
- Create: `backend/src/cellar/domain/research_organization/stage_evaluation.py`
- Test: create `backend/tests/unit/domain/research_organization/test_stage_evaluation.py`

**Interfaces (produces)**
```python
@dataclass(frozen=True) class StageCheck(channel_id: uuid.UUID, verdict: CheckVerdict)
@dataclass(frozen=True) class StageResultOutcome(stage_id, outcome: StageOutcome, overridden: bool, override_reason: str | None, checks: tuple[StageCheck, ...])
StageOutcomes = dict[uuid.UUID, dict[uuid.UUID, StageResultOutcome]]     # result_id -> stage_id -> outcome
def evaluate_stages(campaign: Campaign) -> StageOutcomes
def tally_stage_counts(campaign: Campaign, outcomes: StageOutcomes) -> dict[uuid.UUID, dict[str, int]]   # stage_id -> {population, hit, miss, untested, not_in_stage, overridden}; population = hit+miss+untested
```
Algorithm exactly as spec §3.6: parents first (recursive with memo, memo per result); `not_in_stage` when parent final outcome != hit; per criterion: missing measurement / value None / qualifier nd|excluded → untested, else pass/fail via `is_met`; combine any fail→miss, else any untested→untested, else hit; override replaces outcome (also when not_in_stage) and marks `overridden`. Add the `# ponytail:` comment about censored values compared as-is.

**Tests**: AND semantics; untested beats hit but not miss; root population is all results; child not_in_stage when parent miss/untested; child evaluated on parent hit; override forces hit and feeds child population; override on not_in_stage row; branching (two children of one parent); parent listed after child in `campaign.stages` still evaluated first; zero-criteria stage = hit for whole population; `tally_stage_counts` numbers on the spec's worked example (68 → 12 → 7/3/2/56).

- [ ] Tests → implement → pass → commit.

---

## Phase 2 — Persistence and lifecycle

### Task 4: ORM + repository + migration 074 (additive)

**Files**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`, `campaign_repository.py`
- Create: `backend/alembic/versions/074_campaign_hit_stages.py`
- Test: create `backend/tests/unit/infrastructure/persistence/test_migration_074_stage_backfill.py`; extend `backend/tests/integration/research_organization/test_campaign_repository.py`

**Interfaces (produces)**
```python
# models.py
class CampaignStageModel(Base, EntityModelMixin): __tablename__="campaign_stage"; campaign_id FK campaign CASCADE (index); name String(120); parent_stage_id FK campaign_stage.id ondelete RESTRICT nullable; display_order Integer server_default "0"; criteria JSONB not null server_default '[]'
    __table_args__ = (Index("uq_campaign_stage_name", "campaign_id", text("lower(name)"), unique=True),)
class CampaignStageOverrideModel(Base, EntityModelMixin): __tablename__="campaign_stage_override"; result_id FK campaign_result CASCADE; stage_id FK campaign_stage CASCADE; forced_outcome String(16); reason Text; overridden_by Uuid; overridden_at DateTime(tz)
    __table_args__ = (Index("uq_campaign_stage_override_result_stage", "result_id", "stage_id", unique=True),)
CampaignModel.stages = relationship(cascade="all, delete-orphan", lazy="selectin", order_by display_order)
CampaignModel.close_note: Mapped[str | None] = mapped_column(Text, nullable=True)
CampaignResultModel.stage_overrides = relationship(cascade="all, delete-orphan", lazy="selectin")

# campaign_repository.py — mirror the channel/measurement mapping trio
_stage_to_domain / _stage_to_model / _stage_update_model ; _override_to_domain / _override_to_model
_to_domain passes stages=..., close_note=...; _update_model reconciles stages by id; _result_update_model reconciles overrides by stage_id (update existing, append new, remove missing)

# 074_campaign_hit_stages.py (revision "074_campaign_hit_stages", down_revision "073_molecules_inchi_key_unique")
def build_stage_rows(channel_rows: list[dict]) -> list[dict]
    # input rows: {id, campaign_id, label, display_order, hit_threshold(dict|None)}; output rows for campaign_stage:
    # {id: uuid4, campaign_id, name: label + " hits" (collisions within a campaign, case-insensitive, get " (2)", " (3)"...), parent_stage_id: None, display_order, criteria: [{"channel_id": str(id), "operator", "value"}]}
    # skip rows whose threshold is None or whose operator == "in"
upgrade(): create tables + indexes → SELECT channel rows, build_stage_rows, INSERT (before triggers exist) → CREATE OR REPLACE the trigger function with two new branches (campaign_stage via campaign_id; campaign_stage_override via campaign_result join) + triggers on both tables (copy 027's shape) → add campaign.close_note
downgrade(): drop close_note, triggers, restore the 027 function body, drop tables
```
Note: the domain `Campaign.__init__` gains `close_note: str | None = None` here (attribute only; behaviour in Task 5).

**Tests**: unit `build_stage_rows` (suffixing, `in` skipped, between value array kept, None threshold skipped, ordering). Integration: stages + overrides round-trip; rename + criteria replacement + override removal reconcile on save; `close_note` round-trips. Run `uv run alembic upgrade head` against the dev DB (`make migrate` or equivalent) and confirm `SELECT name, criteria FROM campaign_stage` shows one stage per old threshold. Schema guard test (`tests/unit/infrastructure/persistence/test_schema_guard.py`) must still pass.

- [ ] Tests → implement → pass → commit.

### Task 5: Soft close — no signature, no published collection, reopen

**Files**
- Modify: `domain/research_organization/campaign.py`, `events.py`; `application/research_organization/close_campaign.py`, `create_campaign.py`, `get_published_campaign.py`; create `application/research_organization/reopen_campaign.py`; `interface/routes/_campaign_dtos.py`, `campaigns.py`; `infrastructure/di/_research_organization.py`; `interface/dependencies/_research_organization.py`; `campaign_repository.py` (stop mapping the three retired fields; map `close_note`)
- Tests: `tests/unit/domain/research_organization/test_campaign.py`; `tests/unit/application/research_organization/test_close_campaign.py`, `test_create_campaign.py`, `test_get_published_campaign.py`; create `test_reopen_campaign.py`; `tests/integration/application/research_organization/test_close_campaign.py`; `tests/api/test_campaigns_api.py`; `tests/api/test_campaign_published_contract.py` + `tests/api/fixtures/daikon_contract.schema.json`

**Interfaces (produces)**
```python
# Campaign: remove publishes_collection, signature_id, published_collection_id, set_published_collection(); create() loses publishes_collection
def close(self, *, closed_by: uuid.UUID, note: str | None, source_protocols: list[dict]) -> None   # sets close_note
def reopen(self, *, reopened_by: uuid.UUID, reason: str) -> None   # ValidationError unless CLOSED (superseded refused); reason required; status→DRAFT; clears closed_at/closed_by/close_note; registers CampaignReopened
# events: CampaignClosed(closed_by, note: str | None); CampaignReopened(reopened_by, reason: str); delete CampaignPublishedCollectionCreated
# CloseCampaignCommand(workspace_id, campaign_id, user_id, note: str | None = None); CloseCampaign.__init__ drops collection_repo; step 9 deleted
# ReopenCampaignCommand(workspace_id, campaign_id, user_id, reason); class ReopenCampaign(uow, campaign_repo, dispatcher) -> Result[Campaign, DomainError]
# CreateCampaignCommand / CreateCampaignRequest lose publishes_collection
# GetPublishedCampaign.__init__ drops collection_repo; doc drops "signature" and "published_collection", campaign dict gains "close_note"
# DTOs: CloseCampaignRequest(note: str | None = None); ReopenCampaignRequest(reason: str); CampaignResponse drops publishes_collection/published_collection_id/signature_id, gains close_note
# Route: POST /api/v1/campaigns/{campaign_id}/reopen  (function name reopen_campaign) -> CampaignResponse; ReopenCampaignDep
```

**Tests**: domain close stores note; reopen from closed clears metadata + event; reopen from draft and from superseded refused; unit close (no collection repo, note persisted); reopen UC (404, 422 on draft, happy path); create without the flag; published doc keys (no signature, no published_collection, has close_note); integration close test asserts no collection row is created and `close_note` persisted; API: close with `{}` and with `{"note": "..."}`, reopen 200 then 422 on second call, `test_patch_after_close_423` still green; contract test: schema fixture `required` list and definitions updated. Grep gate: `grep -rn "signature_id\|publishes_collection\|published_collection" backend/src` → only the ORM columns in `models.py` (dropped in Task 8) and `collections` routes/models (untouched).

- [ ] Tests → implement → pass → commit.

### Task 6: Remove per-cell hit call

**Files**
- Modify: `domain/research_organization/campaign_measurement.py`, `enums.py` (delete `HitCall`); `application/research_organization/channel_resolution.py` (delete `_compute_hit_call`, `hit_call=` kwargs), `add_results_from_runs.py` (`_CellData.is_hit: bool | None`; `_build_measurement` drops hit_call; `mol_is_hit` uses `is_hit`), `preview_run_import.py` (`met = cfg.hit_threshold.is_met(picked.value)`; keep the transient preview key `"hit_call": "hit"/"miss"/None`), `override_result_cell.py` (drop `hit_call`); `interface/routes/campaigns_results.py`, `_campaign_dtos.py` (`OverrideCellRequest`, `CampaignMeasurementResponse`); `campaign_repository.py`; `get_published_campaign.py`; `tests/api/fixtures/daikon_contract.schema.json`
- Tests: `test_campaign_measurement.py`, `test_channel_resolver.py` (rewrite the three hit-call tests to assert `m.value` for the resolved intercept instead), `test_override_result_cell.py`, `test_close_campaign.py` (imports), `test_get_published_campaign.py`, `test_add_results_from_runs.py`, `test_preview_run_import.py` (unchanged behaviour), API tests that send `hit_call`.

Grep gate: `grep -rn "hit_call\|HitCall" backend/src backend/tests` → only `preview_run_import.py`, its test, and the FE-facing preview DTO.

- [ ] Update tests → implement → pass → commit.

### Task 7: Remove per-readout hit threshold

**Files**
- Modify: `domain/research_organization/campaign_channel.py`; `application/research_organization/add_campaign_channel.py` (drop `hit_threshold`, the carry-forward block and the `protocol_repo` dependency), `update_campaign_channel.py`, `mirror_protocol_channels.py` (stop passing `hit_threshold`; keep `_match_recommended_threshold` for Task 12), `add_results_from_runs.py` (stop persisting on reuse/create; `ChannelImportConfig.hit_threshold` stays as import filter); `_campaign_dtos.py` (`AddChannelRequest`, `UpdateChannelRequest`, `CampaignChannelResponse`), `campaigns_channels.py`; `campaign_repository.py`; `get_published_campaign.py`; DI factory `_add_channel` (no protocol_repo); schema fixture
- Tests: `test_campaign_channel.py`, `test_add_campaign_channel.py`, `test_update_campaign_channel.py`, `test_mirror_protocol_channels.py`, `test_add_results_from_runs.py`, `test_campaign_dtos.py`, API tests.

Grep gate: `grep -rn "hit_threshold" backend/src` → only `preview_run_import.py`/`add_results_from_runs.py` import-config usage and the ORM column (dropped in Task 8).

- [ ] Update tests → implement → pass → commit.

### Task 8: Migration 075 — drop retired columns

**Files**
- Create: `backend/alembic/versions/075_campaign_drop_hit_columns.py` (revises 074): drop `campaign_channel.hit_threshold`, `campaign_measurement.hit_call`, `campaign.signature_id`, `campaign.publishes_collection`, `campaign.published_collection_id`; downgrade re-adds them nullable (data not restored, `publishes_collection` server_default true)
- Modify: `models.py` (remove the five columns)
- Tests: schema guard unit test; full `tests/integration` + `tests/api` green; `uv run alembic upgrade head` on the dev DB.

- [ ] Implement → run all backend tests → commit.

---

## Phase 3 — Application and API for stages

### Task 9: Stage use cases, routes, DTOs

**Files**
- Create: `application/research_organization/add_campaign_stage.py`, `update_campaign_stage.py`, `remove_campaign_stage.py`; `interface/routes/campaigns_stages.py`
- Modify: `_campaign_dtos.py`, `infrastructure/di/_research_organization.py`, `interface/dependencies/_research_organization.py`, `interface/app.py` (include router)
- Tests: create `tests/unit/application/research_organization/test_add_campaign_stage.py`, `test_update_campaign_stage.py`, `test_remove_campaign_stage.py`; extend `tests/api/test_campaigns_api.py`

**Interfaces (produces)**
```python
AddCampaignStageCommand(workspace_id, campaign_id, name: str, parent_stage_id: uuid.UUID | None, criteria: list[StageCriterion])
UpdateCampaignStageCommand(workspace_id, campaign_id, stage_id, name=UNSET, parent_stage_id=UNSET, criteria=UNSET, display_order=UNSET)   # UNSET from domain campaign_stage
RemoveCampaignStageCommand(workspace_id, campaign_id, stage_id)
# each use case: (uow, campaign_repo, dispatcher) -> Result[Campaign, DomainError]; NotFound/Validation/Conflict from the aggregate become Failure(...)
# DTOs
class StageCriterionDTO(BaseModel): channel_id: uuid.UUID; operator: str; value: float | list[float]; to_domain(); from_domain()
class CampaignStageResponse(BaseModel): id; name; parent_stage_id: uuid.UUID | None; display_order: int; criteria: list[StageCriterionDTO]; from_domain()
class AddStageRequest(BaseModel): name: str; parent_stage_id: uuid.UUID | None = None; criteria: list[StageCriterionDTO] = []
class UpdateStageRequest(BaseModel): name: str | None = None; parent_stage_id: uuid.UUID | None = None; criteria: list[StageCriterionDTO] | None = None; display_order: int | None = None; model_config = {"extra": "forbid"}   # omitted vs null via model_fields_set, as UpdateChannelRequest
CampaignResponse.stages: list[CampaignStageResponse]
# Routes (router prefix /api/v1/campaigns, tag "campaigns"); function names fix the orval hook names:
POST   /{campaign_id}/stages                  add_campaign_stage
PATCH  /{campaign_id}/stages/{stage_id}       update_campaign_stage
DELETE /{campaign_id}/stages/{stage_id}       remove_campaign_stage
# Deps: AddCampaignStageDep, UpdateCampaignStageDep, RemoveCampaignStageDep
```

**Tests**: unit per use case (auth, 404 campaign, draft guard via aggregate, happy path saves + commits, conflict on delete with child → `Failure(ConflictError)`); API: create stage 200 with criteria echoing back; PATCH rename + null parent clears; DELETE 409 with child then 200 after re-parent; unknown channel in criteria 422; stage write on closed campaign 423 (DB trigger / lock guard).

- [ ] Tests → implement → pass → commit.

### Task 10: Stage overrides and outcomes on the API

**Files**
- Create: `application/research_organization/set_stage_override.py`
- Modify: `_campaign_dtos.py`, `campaigns_stages.py`, DI, deps
- Tests: create `tests/unit/application/research_organization/test_set_stage_override.py`; extend `tests/unit/interface/routes/test_campaign_dtos.py`, `tests/api/test_campaigns_api.py`

**Interfaces (produces)**
```python
SetStageOverrideCommand(workspace_id, campaign_id, result_id, stage_id, user_id, forced_outcome: StageOutcome | None, reason: str | None)   # None clears; else HIT/MISS with non-empty reason
class SetStageOverride(uow, campaign_repo, dispatcher) -> Result[Campaign, DomainError]   # draft guard (ValidationError like OverrideResultCell); 404 result/stage
# DTOs
class StageCheckResponse(BaseModel): channel_id: uuid.UUID; verdict: str
class StageOutcomeResponse(BaseModel): stage_id: uuid.UUID; outcome: str; overridden: bool; override_reason: str | None = None; checks: list[StageCheckResponse]
class SetStageOverrideRequest(BaseModel): outcome: str  # "hit" | "miss"; reason: str
CampaignResultResponse.stage_outcomes: list[StageOutcomeResponse]; from_domain(r, outcomes: dict[uuid.UUID, StageResultOutcome] | None = None)
CampaignResponse.from_domain(c, ...) computes evaluate_stages(c) once and threads per-result outcomes
# Routes
PUT    /{campaign_id}/results/{result_id}/stages/{stage_id}/override   set_stage_override
DELETE /{campaign_id}/results/{result_id}/stages/{stage_id}/override   clear_stage_override
```

**Tests**: unit (set, replace, clear, invalid outcome 422, empty reason 422, closed campaign refused); DTO unit: `CampaignResponse.from_domain` on a campaign with two stages yields `stage_outcomes` with checks; API: PUT then GET shows `overridden: true`, DELETE clears; funnel scenario through the API (stage A on channel X, stage B parent A on channel Y; three results with values → outcomes hit / miss / not_in_stage).

- [ ] Tests → implement → pass → commit.

### Task 11: Published JSON

**Files**
- Modify: `application/research_organization/get_published_campaign.py`; `tests/api/fixtures/daikon_contract.schema.json`
- Tests: `tests/unit/application/research_organization/test_get_published_campaign.py`, `tests/api/test_campaign_published_contract.py`

**Interfaces**: doc gains `"stages": [{id, name, parent_stage_id, display_order, criteria: [...], counts: {population, hit, miss, untested, not_in_stage, overridden}}]` (from `tally_stage_counts`) and `results[].stage_outcomes[]` in the same shape as `StageOutcomeResponse`. Add `_serialize_stage(stage, counts)` and `_serialize_stage_outcome(o)`.

**Tests**: unit doc contains stages with counts and per-result outcomes; contract schema validates the new keys; required lists updated.

- [ ] Tests → implement → pass → commit.

### Task 12: `stage_name` on run import and mirror protocol

**Files**
- Modify: `add_results_from_runs.py` (`AddResultsFromRunsCommand.stage_name: str | None = None`; after channels resolve, if `stage_name` and ≥1 config with `use_for_filter and hit_threshold`, build `StageCriterion(channel_id=<resolved channel>.id, operator=cfg.hit_threshold.operator, value=cfg.hit_threshold.value)` per such config and `campaign.add_stage(CampaignStage(name=stage_name, display_order=max+1))`; name collision → `Failure(ValidationError)`), `mirror_protocol_channels.py` (`MirrorProtocolChannelsCommand.stage_name: str | None`; map `protocol.recommended_hit_criteria` to channels via `_match_recommended_threshold` per (rd.name, intercept_key) over created + existing channels; create the stage when ≥1 maps; outcome `stage_created: bool`), `_campaign_dtos.py` (`AddFromRunsRequest.stage_name`, `MirrorProtocolRequest.stage_name`, `MirrorProtocolOutcomeResponse.stage_created`), routes `campaigns.py`, `campaigns_channels.py`
- Tests: `test_add_results_from_runs.py` (stage created with N criteria; none when no filter criteria; collision 422), `test_mirror_protocol_channels.py` (stage from recommendations; `stage_created False` when nothing maps), API smoke for both request fields.

- [ ] Tests → implement → pass → commit. Run the full backend suite; `uv run lint-imports`.

---

## Phase 4 — Frontend

Backend must be running on :8000 (`make dev-be` from repo root) for orval regen.

### Task 13: Types, readouts grouping, popover cleanup, mirror stage checkbox

**Files**
- Run `pnpm generate:api`; revert files whose only change is the OpenAPI version stamp (see memory note); delete dangling `model/index.ts` exports for removed schemas (`campaignChannelResponseHitThreshold`, `campaignMeasurementResponseHitCall`, `campaignResponseSignatureId`, `campaignResponsePublishedCollectionId`, `closeCampaignRequestPublishesCollection`, …).
- Modify: `features/screen-campaign/types/index.ts` (drop `HitCall`; add `export type StageOutcome = "hit" | "miss" | "untested" | "not_in_stage"; export type CheckVerdict = "pass" | "fail" | "untested";` re-export `CampaignStageResponse`, `StageCriterionDTO`, `StageOutcomeResponse`, `AddStageRequest`, `UpdateStageRequest`, `SetStageOverrideRequest`, `ReopenCampaignRequest`)
- Modify: `components/sections/channels-section.tsx` — group rows by `protocol_id` (reuse `useProtocolSummaries(undefined, { includeAll: true })` + `groupBy` from `@/shared/lib/group-by` exactly as `grid/results-grid.tsx:208-216`), protocol sub-heading per group, row text `label · DR/RD · selection rule`; remove `formatThreshold`/`parseHitThreshold` usage; mirror popover gains "Also create stage" checkbox + name input (default `<Protocol name> hits`) sending `stage_name`; toast mentions the stage when `stage_created`.
- Modify: `components/channel-popover.tsx` — delete the hit-threshold schema fields, defaults, effects, submit block and the "Hit threshold" UI block; keep `intercept_key` computation (channel identity) by moving the intercept picker out of the threshold block into its own "Intercept" field shown for multi-intercept DR readouts in create mode; edit mode shows a locked line `Protocol: <name> › <readout name>` under "Source".
- Tests: create `components/sections/channels-section.test.tsx` (renders two protocol groups; row shows no threshold text), typecheck + lint.

- [ ] Implement → `pnpm exec tsc --noEmit && pnpm lint && pnpm test` → commit (pathspecs: the feature files + `src/shared/lib/api/**` regenerated files).

### Task 14: Hit stages section

**Files**
- Create: `components/sections/stages-section.tsx`, `components/stage-popover.tsx`
- Modify: `components/campaign-builder.tsx`, `components/campaign-view/index.tsx` (state `selectedStageId: string | null`, default null; pass to `StagesSection`, `CampaignFilterBar`, `ResultsGridV2`), `hooks/use-campaigns.ts` (optional: `useStageCounts` helper) 

**Interfaces (produces)**
```ts
// stages-section.tsx
export function StagesSection(props: { campaign: CampaignResponse; selectedStageId: string | null; onSelectStage: (id: string | null) => void; readOnly: boolean })
// lib/stage-outcomes.ts (pure, tested)
export function outcomeFor(result: CampaignResultResponse, stageId: string): StageOutcomeResponse | undefined
export function tallyStage(results: CampaignResultResponse[], stageId: string): { population: number; hit: number; miss: number; untested: number; not_in_stage: number; overridden: number }
// stage-popover.tsx — one form (name, parent select excluding self + descendants, criteria list editor with readout picker labelled "<protocol> › <readout> (unit)", operator, value / low+high), one Save → POST or PATCH with the whole criteria list; delete with AlertDialog; 409 message surfaced via toast
```
Tabs: `[All N] [Stage name count]…` sorted by `display_order`; child tabs show "↳ after <parent>" subline; "+ Stage" pill. Panel under tabs lists the selected stage's criteria rows and affordances (readOnly hides them). Selecting a tab calls `onSelectStage` and the parent resets `filters.stageOutcomes` to `{hit, miss, untested}`. Deleting the selected stage resets to null. Generated hooks: `useAddCampaignStageApiV1CampaignsCampaignIdStagesPost`, `useUpdateCampaignStageApiV1CampaignsCampaignIdStagesStageIdPatch`, `useRemoveCampaignStageApiV1CampaignsCampaignIdStagesStageIdDelete`.
- Tests: `lib/stage-outcomes.test.ts` (tally on a fixture with three results); `stages-section.test.tsx` (tab counts, parent subline, click selects).

- [ ] Implement → checks → commit.

### Task 15: Filter bar, grid verdicts, Stage column, override popover

**Files**
- Modify: `components/campaign-filter-bar.tsx` (`CampaignFilters.hitStatus` → `stageOutcomes: Set<StageOutcome>`; `rowPassesFilters(result, filters, selectedStageId)`; `computeRowHitStatus` deleted; chips Hit/Miss/Untested/Not in stage shown only when a stage is selected; Overridden = cell override OR override on the selected stage; `emptyFilters()`/`closedCampaignFilters()` updated), `components/bulk-decision-menu.tsx` (pass `selectedStageId`), `components/grid/results-grid.tsx` (`CompoundValueCell.hitCall` → `verdict: CheckVerdict | null` from the selected stage's `checks`; new pinned-right "Stage" column before Decision rendered only when `selectedStageId` is set: outcome chip + overridden marker, opens `StageOverridePopover` in draft), create `components/popovers/stage-override-popover.tsx` (computed outcome, failing criteria, "Promote to hit" / "Demote to miss" with required reason, "Clear override"; hooks `useSetStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverridePut`, `useClearStageOverrideApiV1CampaignsCampaignIdResultsResultIdStagesStageIdOverrideDelete`), `components/override-modal.tsx` (remove the hit-call select and its state)
- Tests: create `components/campaign-filter-bar.test.ts` (rowPassesFilters with stage outcomes; tally; Overridden semantics); update `hooks/use-campaigns.test.tsx` / `lib/snapshot-adapter.test.ts` fixtures if they reference removed fields.

- [ ] Implement → checks → commit.

### Task 16: Close, reopen, header, removals, preview, run-import stage name

**Files**
- Rename `components/close-sign-dialog.tsx` → `components/close-campaign-dialog.tsx` (`CloseCampaignDialog`: summary card, optional note textarea, "Close campaign" button; `useCloseCampaignApiV1CampaignsCampaignIdClosePost` with `{ note }`)
- Create: `components/campaign-view/reopen-dialog.tsx` (required reason, `useReopenCampaignApiV1CampaignsCampaignIdReopenPost`, invalidates `campaignKeys.detail`; copy the shape of the unlock dialog in `features/screening-assay/components/run-detail.tsx:633-658`)
- Modify: `components/sections/header-strip.tsx` ("Close" button; `onReopen` prop + "Reopen" button in closed mode; drop `signatureId` prop and the "Signed" span; show `campaign.close_note` in the closed line), `components/campaign-builder.tsx` (dialog rename), `components/campaign-view/index.tsx` (reopen dialog; delete the Published collection card; drop signature), delete `components/campaign-view/published-collection-link.tsx`, `components/create-campaign-dialog.tsx` (drop the publish checkbox + schema field), `components/preview-as-published-dialog.tsx` (drop `hit_call` chip and `published_collection`; add a "Stages" table: name, after, criteria count, hit / miss / untested), `components/add-from-runs-dialog.tsx` ("Save criteria as stage" checkbox + name input in `ConfigureStep`, shown when any config has a threshold; default `<protocol name> hits`; sends `stage_name`)
- Tests: typecheck + lint + existing suites; smoke in the browser against the dev stack: create stage, chain a second, override one compound, close, reopen.

- [ ] Implement → checks → commit.

### Task 17: Docs

- Modify: `docs/domain-model/05-research-organization.md` (Campaign section: stages, overrides, lifecycle, removed fields), `docs/implementation-status.md`, the spec (note the 074/075 split and the `build_stage_rows` unit test instead of a DB migration test); create `docs/backlog/collection-freeze-unused.md` and `docs/backlog/campaign-hit-call-overrides-not-migrated.md`. Only force-added docs are tracked: `git add -f` the changed doc files explicitly.

- [ ] Commit. Then the single whole-branch review.
