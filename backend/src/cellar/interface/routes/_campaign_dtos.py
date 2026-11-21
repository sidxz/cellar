"""Shared Pydantic DTOs + serialization helpers for the Campaign routes.

Split out of ``campaigns.py`` so the lifecycle module + the per-group route
modules (channels, results, publishing) can import the same request/response
shapes without circular imports.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cellar.application.research_organization.campaign_collection_coverage import (
    LibraryCoverage,
)
from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
)
from cellar.application.research_organization.set_cell_qc_verdicts import QcVerdictCounts
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult, ResultNote
from cellar.domain.research_organization.campaign_result_filters import CampaignResultFilters
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    SelectionRule,
    StageOutcome,
)
from cellar.domain.research_organization.measurement_facts import (
    ColumnDescription,
    Concentration,
    parse_concentration,
)
from cellar.domain.research_organization.source_ref import (
    ManualRef,
    SeedRun,
    source_group_key,
)
from cellar.domain.research_organization.stage_evaluation import (
    StageCheck,
    StageOutcomes,
    StageResultOutcome,
    evaluate_stages,
    tally_stage_counts,
)
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from cellar.domain.shared.target_ref import TargetRef
from cellar.interface.routes._collection_coverage import CollectionCoverageResponse
from cellar.interface.routes._target_refs import TargetRefResponse

# ---------------------------------------------------------------------------
# DTOs — requests
# ---------------------------------------------------------------------------


class ConcentrationDTO(BaseModel):
    """A molar or mass/volume concentration, e.g. ``{"value": 10, "unit": "µM"}``."""

    value: float
    unit: str

    @model_validator(mode="after")
    def _is_a_concentration(self) -> ConcentrationDTO:
        if self.to_domain() is None:
            raise ValueError(f"{self.value} {self.unit!r} is not a concentration")
        return self

    def to_domain(self) -> Concentration | None:
        return parse_concentration({"value": self.value, "unit": self.unit})

    @classmethod
    def from_domain(cls, c: Concentration) -> ConcentrationDTO:
        # Already a parsed concentration: the request-side check would be a re-parse.
        return cls.model_construct(value=c.value, unit=c.unit)


class InterceptKeyDTO(BaseModel):
    kind: str  # "ec" | "ic"
    level: float  # (0, 100)

    def to_domain(self) -> InterceptKey:
        return InterceptKey(kind=self.kind, level=self.level)

    @classmethod
    def from_domain(cls, ik: InterceptKey) -> InterceptKeyDTO:
        return cls(kind=ik.kind, level=ik.level)


class HitCriterionDTO(BaseModel):
    readout_name: str
    operator: str
    # gt/lt/gte/lte → float; in → list[str]; between → list[float] (length 2).
    value: float | list[float] | list[str]
    #: Targets a specific dose-response intercept (e.g. EC90). ``None`` means
    #: "use the channel cell value as-is" — preserves legacy criteria, which
    #: for a DR channel equals the curve's primary fitted value.
    intercept_key: InterceptKeyDTO | None = None

    def to_domain(self) -> HitCriterion:
        return HitCriterion(
            readout_name=self.readout_name,
            operator=self.operator,
            value=self.value,
            intercept_key=self.intercept_key.to_domain() if self.intercept_key else None,
        )

    @classmethod
    def from_domain(cls, hc: HitCriterion) -> HitCriterionDTO:
        return cls(
            readout_name=hc.readout_name,
            operator=hc.operator,
            value=hc.value,
            intercept_key=(
                InterceptKeyDTO.from_domain(hc.intercept_key) if hc.intercept_key else None
            ),
        )


class CreateCampaignRequest(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID
    supersedes_campaign_id: uuid.UUID | None = None
    # Sent by the app that will manage the campaign (with its X-Service-Token).
    managed_url: str | None = None
    managed_label: str | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class AddFromCollectionRequest(BaseModel):
    collection_id: uuid.UUID
    description: str | None = None


class AddFromCampaignRequest(BaseModel):
    source_campaign_id: uuid.UUID
    #: Pull only the source campaign's hits at this stage. ``None`` = every result.
    stage_id: uuid.UUID | None = None
    description: str | None = None


class ChannelImportConfigDTO(BaseModel):
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    label: str
    source_kind: str
    selection_rule: str
    hit_threshold: HitCriterionDTO | None = None
    use_for_filter: bool = True
    allowed_curve_classes: list[str] | None = None
    #: Normalization layer for ``readout_data`` source: None=raw,
    #: "percent_inhibition"=computed, etc. Ignored for dose-response curves.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept (legacy behavior). Top-level field — not
    #: nested under hit_threshold — so display-only channels (no threshold)
    #: keep their intercept identity on the wire.
    intercept_key: InterceptKeyDTO | None = None

    def to_domain(self) -> ChannelImportConfig:
        return ChannelImportConfig(
            protocol_id=self.protocol_id,
            readout_definition_id=self.readout_definition_id,
            label=self.label,
            source_kind=ChannelSourceKind(self.source_kind),
            selection_rule=SelectionRule(self.selection_rule),
            hit_threshold=self.hit_threshold.to_domain() if self.hit_threshold else None,
            use_for_filter=self.use_for_filter,
            allowed_curve_classes=self.allowed_curve_classes,
            normalization_applied=self.normalization_applied,
            intercept_key=self.intercept_key.to_domain() if self.intercept_key else None,
        )


class PreviewRunImportRequest(BaseModel):
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfigDTO]
    filter_mode: str = "all"  # "any" | "all"
    #: The stage the runs join; its columns compute over all of its runs. Omitted =
    #: campaign runs, feeding campaign columns only.
    stage_id: uuid.UUID | None = None
    #: When no ``stage_id``: creates — or reuses, by case-insensitive name — this
    #: stage and puts the runs and columns on it. Configs with thresholds
    #: (use_for_filter + hit_threshold) replace its criteria; none leave them alone.
    #: A preview of a new stage resolves its columns from the request's runs only.
    stage_name: str | None = None
    #: Parent for the stage ``stage_name`` creates. Omitted on reuse leaves
    #: the existing stage's parent alone.
    parent_stage_id: uuid.UUID | None = None


class AddFromRunsRequest(PreviewRunImportRequest):
    scope: str = "hits_only"  # "hits_only" | "all"
    description: str | None = None


class ChannelQcFilter(BaseModel):
    """A column's run filter. Unknown keys (the retired ``min_z_prime``) are a 422."""

    model_config = ConfigDict(extra="forbid")

    require_approved: bool = False

    def to_domain(self) -> dict[str, bool] | None:
        return {"require_approved": True} if self.require_approved else None


class AddChannelRequest(BaseModel):
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: ChannelQcFilter | None = None
    display_order: int = 0
    #: Normalization layer for ``readout_data`` source. Ignored for dose-response.
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept. Set-on-create; ``UpdateChannelRequest``
    #: does not accept this field (a chemist wanting a different intercept
    #: creates a new channel).
    intercept_key: InterceptKeyDTO | None = None
    #: Opt out of the campaign's run scope — resolve protocol-wide even when
    #: the campaign was seeded from runs (spec D4).
    resolve_from_all_runs: bool = False
    #: The stage that owns the column; omitted = a campaign-wide column.
    stage_id: uuid.UUID | None = None


class UpdateChannelRequest(BaseModel):
    """Partial update — omitted fields are not changed; null clears the value.

    The UC uses an UNSET sentinel to distinguish "omit" from None. We map
    Pydantic's model_fields_set to thread the sentinel through correctly.
    """

    label: str | None = None
    selection_rule: str | None = None
    qc_filter: ChannelQcFilter | None = None
    #: Column position in the campaign grid. Reorder = PATCH each moved
    #: channel with its new index.
    display_order: int | None = None
    #: Opt out of the campaign's run scope. Omitted = unchanged; flipping it
    #: re-resolves every cell of the channel.
    resolve_from_all_runs: bool | None = None
    #: The one concentration the column reads; null clears it. Omitted =
    #: unchanged; a change re-resolves every cell of the channel.
    test_concentration: ConcentrationDTO | None = None

    model_config = {"extra": "forbid"}


class StageCriterionDTO(BaseModel):
    channel_id: uuid.UUID
    operator: str  # lt, lte, gt, gte, between
    value: float | list[float]

    def to_domain(self) -> StageCriterion:
        return StageCriterion(channel_id=self.channel_id, operator=self.operator, value=self.value)

    @classmethod
    def from_domain(cls, c: StageCriterion) -> StageCriterionDTO:
        return cls(channel_id=c.channel_id, operator=c.operator, value=c.value)


class AddStageRequest(BaseModel):
    name: str
    parent_stage_id: uuid.UUID | None = None
    kind: Literal["criteria", "manual"] = "criteria"
    criteria: list[StageCriterionDTO] = []


class UpdateStageRequest(BaseModel):
    """Partial update — omitted fields are not changed; null clears parent_stage_id.

    The UC uses the domain-owned UNSET sentinel to distinguish "omit" from
    None. We map Pydantic's model_fields_set to thread the sentinel through
    correctly, exactly as ``UpdateChannelRequest`` does.
    """

    name: str | None = None
    parent_stage_id: uuid.UUID | None = None
    criteria: list[StageCriterionDTO] | None = None
    display_order: int | None = None
    kind: Literal["criteria", "manual"] | None = None

    model_config = {"extra": "forbid"}


class SetStageOverrideRequest(BaseModel):
    outcome: Literal["hit", "miss"]
    reason: str


class BulkStageOverrideRequest(BaseModel):
    """Force (or, with ``outcome: null``, clear) one stage's verdict for N results.

    ``outcome`` is a required key so a body can never silently mean "clear".
    """

    result_ids: list[uuid.UUID]
    outcome: Literal["hit", "miss"] | None
    reason: str | None = None

    model_config = {"extra": "forbid"}


class SetResultNotesRequest(BaseModel):
    """Save (or, with ``null``, clear) the note on one result row, on any campaign status.

    Both keys are required: an omitted key is a 422, so an empty body can never
    clear a note and a body without ``expected_notes`` can never overwrite one
    blind. ``expected_notes`` is the note as the editor opened it; when someone
    has changed it since, the save is a 409 ``StaleEditError`` carrying
    ``current``. Saving the same text as now changes nothing.
    """

    notes: str | None
    expected_notes: str | None

    model_config = {"extra": "forbid"}


class ResultNoteResponse(BaseModel):
    """One row's note with who last saved it and when (null when unknown)."""

    notes: str | None
    notes_edited_by: uuid.UUID | None
    notes_edited_at: datetime | None

    @classmethod
    def from_domain(cls, n: ResultNote) -> ResultNoteResponse:
        return cls(notes=n.notes, notes_edited_by=n.edited_by, notes_edited_at=n.edited_at)


class NoteVersionResponse(BaseModel):
    """One version of a row's note: its text (null = removed), who and when (null when the
    note predates tracking)."""

    notes: str | None
    edited_by: uuid.UUID | None
    edited_at: datetime | None


class ResultNoteHistoryResponse(BaseModel):
    """Every version of a row's note, newest first; ``versions[0]`` is the current note."""

    versions: list[NoteVersionResponse]

    @classmethod
    def from_domain(cls, versions: list[ResultNote]) -> ResultNoteHistoryResponse:
        return cls(
            versions=[
                NoteVersionResponse(notes=v.notes, edited_by=v.edited_by, edited_at=v.edited_at)
                for v in versions
            ]
        )


class OverrideCellRequest(BaseModel):
    value: float | None = None
    value_qualifier: str
    unit: str
    reason: str | None = None  # B8 — required when value differs from auto-resolved


class AddResultRowRequest(BaseModel):
    molecule_id: uuid.UUID


class BulkRemoveResultsRequest(BaseModel):
    result_ids: list[uuid.UUID]

    model_config = {"extra": "forbid"}


class QcWhereRequest(BaseModel):
    """The rows ``POST /results/search`` returns for this stage/outcome/filters."""

    model_config = ConfigDict(extra="forbid")

    stage_id: uuid.UUID | None = None
    outcome: list[StageOutcome] = Field(default_factory=list)
    filters: CampaignResultFilters = Field(default_factory=CampaignResultFilters)


class QcTargetRequest(BaseModel):
    """Columns times rows, the rows named exactly one way: the ``result_ids`` key (a list,
    or ``null`` for every row) or a non-null ``where``."""

    # A misspelt ``result_ids`` must not silently widen to every row.
    model_config = ConfigDict(extra="forbid")

    channel_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    result_ids: list[uuid.UUID] | None = None
    where: QcWhereRequest | None = None

    @model_validator(mode="after")
    def _rows_named_one_way(self) -> QcTargetRequest:
        # Presence, not value: an omitted result_ids is not "every row".
        if ("result_ids" in self.model_fields_set) == (self.where is not None):
            raise ValueError(
                "a target names its rows by result_ids (null = every row) or where, exactly one"
            )
        return self


class SetQcVerdictsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["verified", "failed", "not_tested"]
    targets: list[QcTargetRequest] = Field(min_length=1, max_length=100)
    #: Verified/Failed only: also replace the other verdict.
    overwrite: bool = False
    #: Omitted: a cell already holding the verdict keeps its note and who/when. Named
    #: (``null``/blank = no note), with ``overwrite``, it re-stamps such a cell.
    note: str | None = Field(default=None, max_length=2000)


class CloseCampaignRequest(BaseModel):
    note: str | None = None


class ReopenCampaignRequest(BaseModel):
    reason: str


class SetCampaignManagementRequest(BaseModel):
    """Sent by the managing app: where the campaign lives there, and what to call that app."""

    managed_url: str
    managed_label: str

    model_config = {"extra": "forbid"}


class ReleaseCampaignRequest(BaseModel):
    reason: str

    model_config = {"extra": "forbid"}


class MirrorProtocolRequest(BaseModel):
    protocol_id: uuid.UUID
    #: The stage the columns go on; its criteria are never touched.
    stage_id: uuid.UUID | None = None
    #: When no ``stage_id``: creates — or reuses, by case-insensitive name — this
    #: stage and puts the columns on it. The protocol's recommended criteria
    #: replace its criteria only when some map onto the columns.
    stage_name: str | None = None
    #: Parent for the stage ``stage_name`` creates. Omitted on reuse leaves
    #: the existing stage's parent alone.
    parent_stage_id: uuid.UUID | None = None


class MirrorProtocolOutcomeResponse(BaseModel):
    """Counts the bulk-create produced + the up-to-date campaign."""

    channels_created: int
    channels_skipped: int
    stage_created: bool
    campaign: CampaignResponse


class SupersedeRequest(BaseModel):
    new_campaign_id: uuid.UUID


# ---------------------------------------------------------------------------
# DTOs — responses
# ---------------------------------------------------------------------------


class CampaignMeasurementResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    value: float | None = None
    value_qualifier: str
    unit: str
    is_manual_override: bool
    source_run_id: uuid.UUID | None = None
    source_curve_id: uuid.UUID | None = None
    source_readout_id: uuid.UUID | None = None
    protocol_name_snapshot: str
    protocol_version_snapshot: int
    run_date_snapshot: str | None = None
    # Migration 029 — snapshot + audit fields (B6 + B8). Nullable for backwards
    # compat — existing closed campaigns serialize these as null.
    override_reason: str | None = None
    test_concentration_value: float | None = None
    test_concentration_unit: str | None = None
    replicate_count: int | None = None
    qc_verdict: Literal["not_tested", "verified", "failed"]
    qc_verdict_by: uuid.UUID | None = None
    qc_verdict_at: datetime | None = None
    qc_verdict_note: str | None = None
    holds_result: bool
    contributing_run_ids: list[uuid.UUID] | None = None
    # Migration 031 — frozen copy of the upstream dose-response curve.
    # Populated for source_kind=dose_response_curve cells; ReadoutData
    # cells serialize this as null.
    curve_snapshot: dict[str, Any] | None = None
    #: The batches the readings behind the value came from.
    batch_ids: list[uuid.UUID] | None = None
    #: ``measured`` (wells or a fitted curve), ``reported`` (a well-less reading)
    #: or ``mixed``; null when no reading is behind the cell.
    basis: Literal["measured", "reported", "mixed"] | None = None
    #: True for a dose-response value.
    concentration_series: bool = False
    #: Why an untested cell resolved nothing: ``several_concentrations`` or
    #: ``no_runs_at_stage``; null otherwise.
    unresolved_reason: Literal["several_concentrations", "no_runs_at_stage"] | None = None
    #: Single-concentration columns: every known concentration this compound had
    #: in the column's runs, resolved or not. Null for dose-response columns.
    concentrations_found: list[ConcentrationDTO] | None = None

    @classmethod
    def from_domain(cls, m: CampaignMeasurement) -> CampaignMeasurementResponse:
        return cls(
            id=m.id,
            channel_id=m.channel_id,
            value=m.value,
            value_qualifier=m.value_qualifier.value,
            unit=m.unit,
            is_manual_override=m.is_manual_override,
            source_run_id=m.source_run_id,
            source_curve_id=m.source_curve_id,
            source_readout_id=m.source_readout_id,
            protocol_name_snapshot=m.protocol_name_snapshot,
            protocol_version_snapshot=m.protocol_version_snapshot,
            run_date_snapshot=m.run_date_snapshot.isoformat()
            if m.run_date_snapshot is not None
            else None,
            override_reason=m.override_reason,
            test_concentration_value=m.test_concentration_value,
            test_concentration_unit=m.test_concentration_unit,
            replicate_count=m.replicate_count,
            qc_verdict=m.qc_verdict.value if m.qc_verdict else "not_tested",
            qc_verdict_by=m.qc_verdict_by,
            qc_verdict_at=m.qc_verdict_at,
            qc_verdict_note=m.qc_verdict_note,
            holds_result=m.holds_result,
            contributing_run_ids=m.contributing_run_ids,
            curve_snapshot=m.curve_snapshot,
            batch_ids=m.batch_ids,
            basis=m.basis.value if m.basis is not None else None,
            concentration_series=m.concentration_series,
            unresolved_reason=m.unresolved_reason.value if m.unresolved_reason else None,
            concentrations_found=[ConcentrationDTO.from_domain(c) for c in m.concentrations_found]
            if m.concentrations_found is not None
            else None,
        )


class StageCheckResponse(BaseModel):
    channel_id: uuid.UUID
    verdict: str  # pass | fail | untested

    @classmethod
    def from_domain(cls, c: StageCheck) -> StageCheckResponse:
        return cls(channel_id=c.channel_id, verdict=c.verdict.value)


class StageOutcomeResponse(BaseModel):
    stage_id: uuid.UUID
    outcome: str  # hit | miss | untested | not_in_stage | pending
    overridden: bool
    override_reason: str | None = None
    #: Who forced the verdict by hand, and when. Both null unless
    #: ``overridden`` — enough for a client to say "kept by hand by X on
    #: 12 Sep" without fetching the override separately.
    overridden_by: uuid.UUID | None = None
    overridden_at: datetime | None = None
    checks: list[StageCheckResponse]

    @classmethod
    def from_domain(cls, o: StageResultOutcome) -> StageOutcomeResponse:
        return cls(
            stage_id=o.stage_id,
            outcome=o.outcome.value,
            overridden=o.overridden,
            override_reason=o.override_reason,
            overridden_by=o.overridden_by,
            overridden_at=o.overridden_at,
            checks=[StageCheckResponse.from_domain(c) for c in o.checks],
        )


class CampaignResultResponse(BaseModel):
    id: uuid.UUID
    molecule_id: uuid.UUID
    representative_batch_id: uuid.UUID | None = None
    notes: str | None = None
    #: Who last saved ``notes`` and when; null for a note that predates tracking.
    notes_edited_by: uuid.UUID | None = None
    notes_edited_at: datetime | None = None
    #: How many versions ``GET …/notes/history`` lists for this row (0 = never noted).
    notes_version_count: int = 0
    measurements: list[CampaignMeasurementResponse]
    stage_outcomes: list[StageOutcomeResponse]

    @classmethod
    def from_domain(
        cls,
        r: CampaignResult,
        outcomes: dict[uuid.UUID, StageResultOutcome] | None = None,
    ) -> CampaignResultResponse:
        return cls(
            id=r.id,
            molecule_id=r.molecule_id,
            representative_batch_id=r.representative_batch_id,
            notes=r.notes,
            notes_edited_by=r.notes_edited_by,
            notes_edited_at=r.notes_edited_at,
            notes_version_count=r.notes_version_count,
            measurements=[CampaignMeasurementResponse.from_domain(m) for m in r.measurements],
            stage_outcomes=[
                StageOutcomeResponse.from_domain(o) for o in (outcomes or {}).values()
            ],
        )


class ConcentrationCountResponse(BaseModel):
    """One concentration a column's compounds were measured at; null value and unit
    for "not recorded"."""

    value: float | None = None
    unit: str | None = None
    count: int


class ReplicatesResponse(BaseModel):
    min: int | None = None
    max: int | None = None
    not_recorded: int


class ColumnDescriptionResponse(BaseModel):
    """What a column holds (spec §6.6), computed on read from its values.

    ``label`` is the whole sentence; ``short_label`` is the same sentence without
    its stage and readout parts, for a header already under both.
    """

    stage_name: str | None = None
    readout_label: str
    design: Literal[
        "single_concentration",
        "single_concentration_mixed",
        "concentration_series",
        "reported",
        "not_recorded",
    ]
    concentrations: list[ConcentrationCountResponse]
    replicates: ReplicatesResponse
    run_count: int
    rule: str
    basis: list[Literal["measured", "reported", "mixed"]]
    #: The column's runs hold more than one concentration and it names none.
    needs_concentration: bool
    label: str
    short_label: str
    #: Runs the column's scope holds; None for a column reading all protocol runs.
    scope_run_count: int | None = None
    #: Cells with a numeric value across the whole column (after its rule and any
    #: typed override); ND, excluded and unresolved cells don't count. 0 = nothing
    #: to show — the column is empty or every cell is ND.
    value_count: int

    @classmethod
    def from_domain(cls, d: ColumnDescription) -> ColumnDescriptionResponse:
        return cls.model_validate(asdict(d))


class CampaignChannelResponse(BaseModel):
    id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: dict[str, Any] | None = None
    display_order: int
    normalization_applied: str | None = None
    #: Identifies which intercept of a DR curve this channel surfaces.
    #: ``None`` = primary intercept (legacy single-intercept channels).
    intercept_key: InterceptKeyDTO | None = None
    resolve_from_all_runs: bool = False
    #: The stage that owns the column; null for a campaign-wide column.
    stage_id: uuid.UUID | None = None
    #: The one concentration the column reads, when it names one.
    test_concentration: ConcentrationDTO | None = None
    #: Computed on the reads (summary, full campaign, list); null on the
    #: responses of writes — read the campaign back for it.
    description: ColumnDescriptionResponse | None = None

    @classmethod
    def from_domain(
        cls, ch: CampaignChannel, description: ColumnDescription | None = None
    ) -> CampaignChannelResponse:
        return cls(
            id=ch.id,
            label=ch.label,
            protocol_id=ch.protocol_id,
            readout_definition_id=ch.readout_definition_id,
            source_kind=ch.source_kind.value,
            selection_rule=ch.selection_rule.value,
            qualifier_handling=ch.qualifier_handling.value,
            qc_filter=ch.qc_filter,
            display_order=ch.display_order,
            normalization_applied=ch.normalization_applied,
            intercept_key=InterceptKeyDTO.from_domain(ch.intercept_key)
            if ch.intercept_key is not None
            else None,
            resolve_from_all_runs=ch.resolve_from_all_runs,
            stage_id=ch.stage_id,
            test_concentration=ConcentrationDTO.from_domain(ch.test_concentration)
            if ch.test_concentration is not None
            else None,
            description=ColumnDescriptionResponse.from_domain(description)
            if description is not None
            else None,
        )


class StageCountsResponse(BaseModel):
    """Funnel counts for one stage — ``tally_stage_counts`` buckets, verbatim.

    ``population = hit + miss + untested + pending``; ``overridden`` counts
    rows whose outcome came from a manual override (it overlaps the others).
    """

    population: int
    hit: int
    miss: int
    untested: int
    pending: int
    not_in_stage: int
    overridden: int


class CollectionStageCountsResponse(BaseModel):
    """One campaign stage's funnel, counted over a single library's rows."""

    stage_id: uuid.UUID
    counts: StageCountsResponse


class CampaignCollectionCoverageResponse(CollectionCoverageResponse):
    """Campaign library coverage, optionally with its per-stage funnel.

    Extends the shared run/protocol coverage shape rather than widening it:
    those two payloads must not grow a campaign-only field. ``stages`` is
    null unless the caller asked for it (``?include=stages``) and ``[]`` for
    a campaign with no stages.
    """

    stages: list[CollectionStageCountsResponse] | None = None

    @classmethod
    def from_library(cls, lib: LibraryCoverage) -> CampaignCollectionCoverageResponse:
        c = lib.coverage
        return cls(
            id=c.ref.id,
            name=c.ref.name,
            type=c.ref.type,
            covered=c.covered,
            total=c.total,
            fraction=c.fraction,
            # tally_stage_counts keys its dict in ``campaign.stages`` order,
            # which is the order the summary lists them — the contract daikon
            # reads against. Preserved by dict insertion order, not re-sorted.
            stages=None
            if lib.stage_counts is None
            else [
                CollectionStageCountsResponse(
                    stage_id=stage_id, counts=StageCountsResponse(**counts)
                )
                for stage_id, counts in lib.stage_counts.items()
            ],
        )


class CampaignStageResponse(BaseModel):
    id: uuid.UUID
    name: str
    parent_stage_id: uuid.UUID | None = None
    display_order: int
    kind: Literal["criteria", "manual"]
    criteria: list[StageCriterionDTO]
    #: Read-time funnel counts (never stored) — lets a list/summary surface
    #: render the funnel without shipping every result row.
    counts: StageCountsResponse

    @classmethod
    def from_domain(cls, s: CampaignStage, counts: dict[str, int]) -> CampaignStageResponse:
        return cls(
            id=s.id,
            name=s.name,
            parent_stage_id=s.parent_stage_id,
            display_order=s.display_order,
            kind=s.kind.value,
            criteria=[StageCriterionDTO.from_domain(c) for c in s.criteria],
            counts=StageCountsResponse(**counts),
        )


def _derive_compound_sources(
    results: list[CampaignResult],
    scientist_by_run_id: dict[uuid.UUID, str] | None = None,
) -> list[dict[str, Any]]:
    """Derive compound_sources summary from per-result added_from attribution.

    Groups results by their source ref. Results with added_from=None are
    treated as ManualRef. Returns a list of {kind, ref, description, count}.

    When ``scientist_by_run_id`` is supplied, run-kind entries are decorated
    with the bench scientist name from the run's "Scientist" readout. The
    map is computed once per response in the GET handler (cheap one-shot
    query) rather than stored on the campaign aggregate, so it works
    retroactively on already-imported campaigns.
    """
    from collections import Counter

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    # Group by the source's full identity (kind + entity id + description),
    # not just (kind, description) — otherwise two distinct runs/collections
    # added without a description collapse into a single row.
    counts: Counter[tuple[Any, ...]] = Counter()
    for r in results:
        ref = r.added_from if r.added_from is not None else ManualRef()
        d = ref.to_dict()
        key = source_group_key(d)
        if key not in groups:
            groups[key] = d
        counts[key] += 1

    out: list[dict[str, Any]] = []
    for k in groups:
        entry = {**groups[k], "count": counts[k]}
        if entry.get("kind") == "run" and scientist_by_run_id is not None and entry.get("run_id"):
            try:
                rid = uuid.UUID(entry["run_id"])
            except (ValueError, TypeError):
                rid = None
            if rid is not None:
                name = scientist_by_run_id.get(rid)
                if name:
                    entry["scientist"] = name
        out.append(entry)
    return out


class SeedRunResponse(BaseModel):
    """One run the campaign was seeded from (spec D4) — the resolution scope
    for channels of that protocol."""

    run_id: uuid.UUID
    protocol_id: uuid.UUID
    #: The stages the run feeds; empty for a campaign run (campaign columns only).
    stage_ids: list[uuid.UUID]

    @classmethod
    def from_domain(cls, s: SeedRun) -> SeedRunResponse:
        return cls(run_id=s.run_id, protocol_id=s.protocol_id, stage_ids=list(s.stage_ids))


class _CampaignFieldsResponse(BaseModel):
    """Everything a campaign read carries apart from the result rows.

    Shared by ``CampaignResponse`` (adds ``results``) and
    ``CampaignSummaryResponse`` (adds ``result_count``) so the two reads can
    never drift apart.
    """

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    compound_sources: list[dict[str, Any]]
    supersedes_campaign_id: uuid.UUID | None = None
    superseded_by_campaign_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    close_note: str | None = None
    #: The realm app that manages the campaign (only it changes structure), where the campaign
    #: lives there, and that app's display name; all null when ChemCellar manages it.
    managed_by: str | None = None
    managed_url: str | None = None
    managed_label: str | None = None
    source_protocols: list[dict[str, Any]]
    #: Runs the campaign was seeded from, in insertion order (spec D4).
    seed_runs: list[SeedRunResponse]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    version: int
    channels: list[CampaignChannelResponse]
    stages: list[CampaignStageResponse]
    #: Distinct targets unioned from the runs this campaign's measurements
    #: reference — a derived, read-time field (never stored), like
    #: ``compound_sources``. Defaults to ``[]`` for callers that don't project
    #: targets (e.g. mutation responses that return the refreshed campaign).
    targets: list[TargetRefResponse] = []

    @staticmethod
    def _shared(
        c: Campaign,
        scientist_by_run_id: dict[uuid.UUID, str] | None,
        targets: list[TargetRef] | None,
        descriptions: dict[uuid.UUID, ColumnDescription] | None,
    ) -> tuple[dict[str, Any], StageOutcomes]:
        """Build the shared kwargs and hand back the stage outcomes.

        Evaluates the hit-stage funnel once (pure, cheap: results x stages x
        criteria). The outcomes come back so ``CampaignResponse`` can thread
        each result's verdicts through in declared stage order —
        ``evaluate_stages`` inserts entries in parent-first recursive-evaluation
        order, which need not match ``campaign.stages`` (a child stage can be
        declared before its parent).
        """
        stage_outcomes = evaluate_stages(c)
        stage_counts = tally_stage_counts(c, stage_outcomes)
        return {
            "id": c.id,
            "workspace_id": c.workspace_id,
            "project_id": c.project_id,
            "name": c.name,
            "description": c.description,
            "status": c.status.value,
            "compound_sources": _derive_compound_sources(c.results, scientist_by_run_id),
            "supersedes_campaign_id": c.supersedes_campaign_id,
            "superseded_by_campaign_id": c.superseded_by_campaign_id,
            "closed_at": c.closed_at,
            "closed_by": c.closed_by,
            "close_note": c.close_note,
            "managed_by": c.management.managed_by if c.management else None,
            "managed_url": c.management.url if c.management else None,
            "managed_label": c.management.label if c.management else None,
            "source_protocols": c.source_protocols,
            "seed_runs": [SeedRunResponse.from_domain(s) for s in c.seed_runs],
            "created_by": c.created_by,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "version": c.version,
            # Sort here, not on the aggregate: the ORM relationship only
            # re-orders on reload, so a mutation response that returns the
            # in-memory aggregate would otherwise disagree with the next GET.
            "channels": [
                CampaignChannelResponse.from_domain(ch, (descriptions or {}).get(ch.id))
                for ch in sorted(c.channels, key=lambda x: (x.display_order, x.id))
            ],
            "stages": [CampaignStageResponse.from_domain(s, stage_counts[s.id]) for s in c.stages],
            "targets": [TargetRefResponse.from_ref(t) for t in (targets or [])],
        }, stage_outcomes


class CampaignResponse(_CampaignFieldsResponse):
    results: list[CampaignResultResponse]

    @classmethod
    def from_domain(
        cls,
        c: Campaign,
        scientist_by_run_id: dict[uuid.UUID, str] | None = None,
        targets: list[TargetRef] | None = None,
        descriptions: dict[uuid.UUID, ColumnDescription] | None = None,
    ) -> CampaignResponse:
        shared, stage_outcomes = cls._shared(c, scientist_by_run_id, targets, descriptions)
        return cls(
            **shared,
            results=[
                CampaignResultResponse.from_domain(
                    r, {s.id: stage_outcomes[r.id][s.id] for s in c.stages}
                )
                for r in c.results
            ],
        )


class CampaignSummaryResponse(_CampaignFieldsResponse):
    """A campaign without its result rows — the list + summary read.

    Stage ``counts`` carry the funnel, so a caller that only needs "how many
    compounds cleared each stage" never pays for the row payload.
    """

    result_count: int

    @classmethod
    def from_domain(
        cls,
        c: Campaign,
        scientist_by_run_id: dict[uuid.UUID, str] | None = None,
        targets: list[TargetRef] | None = None,
        descriptions: dict[uuid.UUID, ColumnDescription] | None = None,
    ) -> CampaignSummaryResponse:
        shared, _ = cls._shared(c, scientist_by_run_id, targets, descriptions)
        return cls(**shared, result_count=len(c.results))


class QcVerdictCountsResponse(BaseModel):
    """How each targeted cell fared; a cell named by two targets counts once."""

    changed: int
    unchanged: int
    #: Already carried the other verdict and ``overwrite`` was false.
    kept: int
    #: No value or tested ND to judge (or no cell at all).
    no_result: int

    @classmethod
    def from_domain(cls, counts: QcVerdictCounts) -> QcVerdictCountsResponse:
        return cls(**asdict(counts))


class AddResultsOutcomeResponse(BaseModel):
    added: int
    skipped: int
    #: True only for the add-from-runs outcome when a stage was actually
    #: created from the requested stage_name; other add-results outcomes
    #: (collection, campaign) never create a stage.
    stage_created: bool = False
    campaign: CampaignResponse

    @classmethod
    def from_outcome(cls, outcome: Any) -> AddResultsOutcomeResponse:
        return cls(
            added=outcome.added,
            skipped=outcome.skipped,
            stage_created=getattr(outcome, "stage_created", False),
            campaign=CampaignResponse.from_domain(outcome.campaign),
        )
