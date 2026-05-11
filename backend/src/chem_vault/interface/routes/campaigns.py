"""Campaign lifecycle endpoints — create, manage, close, publish."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chem_vault.application.research_organization.add_campaign_channel import (
    AddCampaignChannelCommand,
)
from chem_vault.application.research_organization.add_result_row import (
    AddResultRowCommand,
)
from chem_vault.application.research_organization.add_results_from_campaign import (
    AddResultsFromCampaignCommand,
)
from chem_vault.application.research_organization.add_results_from_collection import (
    AddResultsFromCollectionCommand,
)
from chem_vault.application.research_organization.add_results_from_runs import (
    AddResultsFromRunsCommand,
)
from chem_vault.application.research_organization.preview_run_import import (
    ChannelImportConfig,
    PreviewRunImportQuery,
)
from chem_vault.application.research_organization.close_campaign import (
    CloseCampaignCommand,
)
from chem_vault.application.research_organization.create_campaign import (
    CreateCampaignCommand,
)
from chem_vault.application.research_organization.get_published_campaign import (
    GetPublishedCampaignQuery,
)
from chem_vault.application.research_organization.override_result_cell import (
    OverrideResultCellCommand,
)
from chem_vault.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSourcesCommand,
)
from chem_vault.application.research_organization.remove_campaign_channel import (
    RemoveCampaignChannelCommand,
)
from chem_vault.application.research_organization.remove_result_row import (
    RemoveResultRowCommand,
)
from chem_vault.application.research_organization.set_result_decision import (
    UNSET as DECISION_UNSET,
    SetResultDecisionCommand,
)
from chem_vault.application.research_organization.supersede_campaign import (
    SupersedeCampaignCommand,
)
from chem_vault.application.research_organization.update_campaign_channel import (
    UNSET,
    UpdateCampaignChannelCommand,
)
from chem_vault.application.research_organization.update_campaign_metadata import (
    UNSET as METADATA_UNSET,
    UpdateCampaignMetadataCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.research_organization.source_ref import ManualRef, SourceRef
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from chem_vault.interface.dependencies import (
    AddCampaignChannelDep,
    AddResultRowDep,
    AddResultsFromCampaignDep,
    AddResultsFromCollectionDep,
    AddResultsFromRunsDep,
    CloseCampaignDep,
    PreviewRunImportDep,
    CreateCampaignDep,
    GetPublishedCampaignDep,
    OverrideResultCellDep,
    RefreshFromSourcesDep,
    RemoveCampaignChannelDep,
    RemoveResultRowDep,
    SetResultDecisionDep,
    SupersedeCampaignDep,
    UpdateCampaignChannelDep,
    UpdateCampaignMetadataDep,
    AuthDep,
    UoWDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


# ---------------------------------------------------------------------------
# DTOs — requests
# ---------------------------------------------------------------------------


class HitCriterionDTO(BaseModel):
    readout_name: str
    operator: str
    # gt/lt/gte/lte → float; in → list[str]; between → list[float] (length 2).
    value: float | list[float] | list[str]

    def to_domain(self) -> HitCriterion:
        return HitCriterion(
            readout_name=self.readout_name,
            operator=self.operator,
            value=self.value,
        )

    @classmethod
    def from_domain(cls, hc: HitCriterion) -> HitCriterionDTO:
        return cls(
            readout_name=hc.readout_name,
            operator=hc.operator,
            value=hc.value,
        )


class CreateCampaignRequest(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID
    publishes_collection: bool = True
    supersedes_campaign_id: uuid.UUID | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class AddFromCollectionRequest(BaseModel):
    collection_id: uuid.UUID
    description: str | None = None


class AddFromCampaignRequest(BaseModel):
    source_campaign_id: uuid.UUID
    decision_filter: list[str] = ["selected"]
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
        )


class PreviewRunImportRequest(BaseModel):
    run_ids: list[uuid.UUID]
    channel_configs: list[ChannelImportConfigDTO]
    filter_mode: str = "all"  # "any" | "all"


class AddFromRunsRequest(PreviewRunImportRequest):
    scope: str = "hits_only"  # "hits_only" | "all"
    default_decision: str = "selected"
    description: str | None = None
    refresh_existing_cells: bool = False


class AddChannelRequest(BaseModel):
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None
    display_order: int = 0


class UpdateChannelRequest(BaseModel):
    """Partial update — omitted fields are not changed; null clears the value.

    The UC uses an UNSET sentinel to distinguish "omit" from None. We map
    Pydantic's model_fields_set to thread the sentinel through correctly.
    """

    label: str | None = None
    selection_rule: str | None = None
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None

    model_config = {"extra": "forbid"}


class SetResultDecisionRequest(BaseModel):
    decision: str
    reason: str | None = None
    notes: str | None = None

    model_config = {"extra": "forbid"}


class OverrideCellRequest(BaseModel):
    value: float | None = None
    value_qualifier: str
    unit: str
    hit_call: str | None = None
    reason: str | None = None  # B8 — required when value differs from auto-resolved


class AddResultRowRequest(BaseModel):
    molecule_id: uuid.UUID


class CloseCampaignRequest(BaseModel):
    signature_id: uuid.UUID
    signature_meaning: str | None = None


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
    hit_call: str | None = None
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
    qc_pass: bool | None = None
    contributing_run_ids: list[uuid.UUID] | None = None

    @classmethod
    def from_domain(cls, m: CampaignMeasurement) -> CampaignMeasurementResponse:
        return cls(
            id=m.id,
            channel_id=m.channel_id,
            value=m.value,
            value_qualifier=m.value_qualifier.value,
            unit=m.unit,
            hit_call=m.hit_call.value if m.hit_call is not None else None,
            is_manual_override=m.is_manual_override,
            source_run_id=m.source_run_id,
            source_curve_id=m.source_curve_id,
            source_readout_id=m.source_readout_id,
            protocol_name_snapshot=m.protocol_name_snapshot,
            protocol_version_snapshot=m.protocol_version_snapshot,
            run_date_snapshot=m.run_date_snapshot.isoformat() if m.run_date_snapshot is not None else None,
            override_reason=m.override_reason,
            test_concentration_value=m.test_concentration_value,
            test_concentration_unit=m.test_concentration_unit,
            replicate_count=m.replicate_count,
            qc_pass=m.qc_pass,
            contributing_run_ids=m.contributing_run_ids,
        )


class CampaignResultResponse(BaseModel):
    id: uuid.UUID
    molecule_id: uuid.UUID
    representative_batch_id: uuid.UUID | None = None
    decision: str
    decision_reason: str | None = None
    notes: str | None = None
    measurements: list[CampaignMeasurementResponse]

    @classmethod
    def from_domain(cls, r: CampaignResult) -> CampaignResultResponse:
        return cls(
            id=r.id,
            molecule_id=r.molecule_id,
            representative_batch_id=r.representative_batch_id,
            decision=r.decision.value,
            decision_reason=r.decision_reason,
            notes=r.notes,
            measurements=[CampaignMeasurementResponse.from_domain(m) for m in r.measurements],
        )


class CampaignChannelResponse(BaseModel):
    id: uuid.UUID
    label: str
    protocol_id: uuid.UUID
    readout_definition_id: uuid.UUID
    source_kind: str
    selection_rule: str
    qualifier_handling: str
    qc_filter: dict[str, Any] | None = None
    hit_threshold: HitCriterionDTO | None = None
    display_order: int

    @classmethod
    def from_domain(cls, ch: CampaignChannel) -> CampaignChannelResponse:
        return cls(
            id=ch.id,
            label=ch.label,
            protocol_id=ch.protocol_id,
            readout_definition_id=ch.readout_definition_id,
            source_kind=ch.source_kind.value,
            selection_rule=ch.selection_rule.value,
            qualifier_handling=ch.qualifier_handling.value,
            qc_filter=ch.qc_filter,
            hit_threshold=HitCriterionDTO.from_domain(ch.hit_threshold) if ch.hit_threshold is not None else None,
            display_order=ch.display_order,
        )


def _derive_compound_sources(results: list[CampaignResult]) -> list[dict[str, Any]]:
    """Derive compound_sources summary from per-result added_from attribution.

    Groups results by their source ref. Results with added_from=None are
    treated as ManualRef. Returns a list of {kind, ref, description, count}.
    """
    from collections import Counter

    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for r in results:
        ref = r.added_from if r.added_from is not None else ManualRef()
        d = ref.to_dict()
        key = (d.get("kind", "manual"), d.get("description"))
        if key not in groups:
            groups[key] = d
    # Count
    counts: Counter[tuple[str, str | None]] = Counter()
    for r in results:
        ref = r.added_from if r.added_from is not None else ManualRef()
        d = ref.to_dict()
        key = (d.get("kind", "manual"), d.get("description"))
        counts[key] += 1

    return [
        {**groups[k], "count": counts[k]}
        for k in groups
    ]


class CampaignResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    compound_sources: list[dict[str, Any]]
    publishes_collection: bool
    supersedes_campaign_id: uuid.UUID | None = None
    superseded_by_campaign_id: uuid.UUID | None = None
    published_collection_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    signature_id: uuid.UUID | None = None
    source_protocols: list[dict[str, Any]]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    version: int
    channels: list[CampaignChannelResponse]
    results: list[CampaignResultResponse]

    @classmethod
    def from_domain(cls, c: Campaign) -> CampaignResponse:
        return cls(
            id=c.id,
            workspace_id=c.workspace_id,
            project_id=c.project_id,
            name=c.name,
            description=c.description,
            status=c.status.value,
            compound_sources=_derive_compound_sources(c.results),
            publishes_collection=c.publishes_collection,
            supersedes_campaign_id=c.supersedes_campaign_id,
            superseded_by_campaign_id=c.superseded_by_campaign_id,
            published_collection_id=c.published_collection_id,
            closed_at=c.closed_at,
            closed_by=c.closed_by,
            signature_id=c.signature_id,
            source_protocols=c.source_protocols,
            created_by=c.created_by,
            created_at=c.created_at,
            updated_at=c.updated_at,
            version=c.version,
            channels=[CampaignChannelResponse.from_domain(ch) for ch in c.channels],
            results=[CampaignResultResponse.from_domain(r) for r in c.results],
        )


class AddResultsOutcomeResponse(BaseModel):
    added: int
    skipped: int
    campaign: CampaignResponse

    @classmethod
    def from_outcome(cls, outcome: Any) -> AddResultsOutcomeResponse:
        return cls(
            added=outcome.added,
            skipped=outcome.skipped,
            campaign=CampaignResponse.from_domain(outcome.campaign),
        )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CreateCampaignRequest,
    auth: AuthDep,
    uc: CreateCampaignDep,
) -> CampaignResponse:
    """Create an empty draft Campaign. Compounds are added via add-from-* endpoints."""
    cmd = CreateCampaignCommand(
        workspace_id=auth.workspace_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        publishes_collection=body.publishes_collection,
        created_by=auth.user_id,
        supersedes_campaign_id=body.supersedes_campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    auth: AuthDep,
    uow: UoWDep,
    project_id: uuid.UUID | None = Query(default=None),
) -> list[CampaignResponse]:
    """List campaigns in the workspace, optionally filtered by project."""
    repo = SQLAlchemyCampaignRepository(uow)
    async with uow:
        if project_id is not None:
            campaigns = await repo.find_by_project(auth.workspace_id, project_id)
        else:
            campaigns = await repo.find_by_workspace(auth.workspace_id)
    return [CampaignResponse.from_domain(c) for c in campaigns]


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uow: UoWDep,
) -> CampaignResponse:
    """Get a campaign by id (full draft view including channels + results)."""
    from chem_vault.domain.shared.errors import NotFoundError

    repo = SQLAlchemyCampaignRepository(uow)
    async with uow:
        campaign = await repo.find_by_id_in_workspace(auth.workspace_id, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign", str(campaign_id))
    return CampaignResponse.from_domain(campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: UpdateCampaignRequest,
    auth: AuthDep,
    uc: UpdateCampaignMetadataDep,
) -> CampaignResponse:
    """Update campaign name/description."""
    provided = body.model_fields_set
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "campaign_id": campaign_id,
    }
    if "name" in provided:
        cmd_kwargs["name"] = body.name
    if "description" in provided:
        cmd_kwargs["description"] = body.description
    cmd = UpdateCampaignMetadataCommand(**cmd_kwargs)
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/add-from-collection", response_model=AddResultsOutcomeResponse)
async def add_results_from_collection(
    campaign_id: uuid.UUID,
    body: AddFromCollectionRequest,
    auth: AuthDep,
    uc: AddResultsFromCollectionDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from a Collection to a DRAFT campaign (idempotent)."""
    cmd = AddResultsFromCollectionCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        collection_id=body.collection_id,
        description=body.description,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/add-from-campaign", response_model=AddResultsOutcomeResponse)
async def add_results_from_campaign(
    campaign_id: uuid.UUID,
    body: AddFromCampaignRequest,
    auth: AuthDep,
    uc: AddResultsFromCampaignDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from another Campaign's filtered result set (idempotent)."""
    cmd = AddResultsFromCampaignCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        source_campaign_id=body.source_campaign_id,
        decision_filter=[CampaignDecision(d) for d in body.decision_filter],
        description=body.description,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/preview-run-import")
async def preview_run_import(
    campaign_id: uuid.UUID,
    body: PreviewRunImportRequest,
    auth: AuthDep,
    uc: PreviewRunImportDep,
) -> dict[str, Any]:
    """Compute the would-be-added cells for the multi-run import dialog (B6).

    Read-only. Returns ``{summary, channels, rows}`` — see spec §3.2.
    """
    q = PreviewRunImportQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[c.to_domain() for c in body.channel_configs],
        filter_mode=body.filter_mode,
    )
    return result_to_response(await uc(q, auth=auth))


@router.post("/{campaign_id}/add-from-runs", response_model=AddResultsOutcomeResponse)
async def add_results_from_runs(
    campaign_id: uuid.UUID,
    body: AddFromRunsRequest,
    auth: AuthDep,
    uc: AddResultsFromRunsDep,
) -> AddResultsOutcomeResponse:
    """Add compound results from one or more protocol Runs (B6).

    Creates campaign channels for each unique (protocol_id, readout_definition_id),
    reusing existing ones. Filters molecules by hit-criteria when scope=hits_only.
    Snapshots concentration/replicate/QC per cell.
    """
    cmd = AddResultsFromRunsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        run_ids=body.run_ids,
        channel_configs=[c.to_domain() for c in body.channel_configs],
        filter_mode=body.filter_mode,
        scope=body.scope,
        default_decision=CampaignDecision(body.default_decision),
        description=body.description,
        refresh_existing_cells=body.refresh_existing_cells,
    )
    outcome = result_to_response(await uc(cmd, auth=auth))
    return AddResultsOutcomeResponse.from_outcome(outcome)


@router.post("/{campaign_id}/channels", response_model=CampaignResponse, status_code=200)
async def add_campaign_channel(
    campaign_id: uuid.UUID,
    body: AddChannelRequest,
    auth: AuthDep,
    uc: AddCampaignChannelDep,
) -> CampaignResponse:
    """Add a channel to a draft Campaign."""
    cmd = AddCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        label=body.label,
        protocol_id=body.protocol_id,
        readout_definition_id=body.readout_definition_id,
        source_kind=ChannelSourceKind(body.source_kind),
        selection_rule=SelectionRule(body.selection_rule),
        qualifier_handling=QualifierHandling(body.qualifier_handling),
        qc_filter=body.qc_filter,
        hit_threshold=body.hit_threshold.to_domain() if body.hit_threshold is not None else None,
        display_order=body.display_order,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.patch("/{campaign_id}/channels/{channel_id}", response_model=CampaignResponse)
async def update_campaign_channel(
    campaign_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: UpdateChannelRequest,
    auth: AuthDep,
    uc: UpdateCampaignChannelDep,
) -> CampaignResponse:
    """Update a campaign channel.

    Semantics: omitted fields are left unchanged (UNSET); null-valued fields
    are cleared where applicable (qc_filter, hit_threshold).
    """
    provided = body.model_fields_set

    # Map omit → UNSET, present → actual value (including None)
    label: str | object = body.label if "label" in provided else UNSET
    selection_rule: SelectionRule | object = SelectionRule(body.selection_rule) if "selection_rule" in provided and body.selection_rule is not None else UNSET
    qc_filter: dict | None | object = body.qc_filter if "qc_filter" in provided else UNSET
    hit_threshold: HitCriterion | None | object = (
        body.hit_threshold.to_domain() if (body.hit_threshold is not None) else None
    ) if "hit_threshold" in provided else UNSET

    cmd = UpdateCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        channel_id=channel_id,
        label=label,
        selection_rule=selection_rule,
        qc_filter=qc_filter,
        hit_threshold=hit_threshold,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete("/{campaign_id}/channels/{channel_id}", response_model=CampaignResponse)
async def remove_campaign_channel(
    campaign_id: uuid.UUID,
    channel_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveCampaignChannelDep,
) -> CampaignResponse:
    """Remove a channel and its measurements from a draft Campaign."""
    cmd = RemoveCampaignChannelCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        channel_id=channel_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.patch("/{campaign_id}/results/{result_id}", response_model=CampaignResponse)
async def set_result_decision(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    body: SetResultDecisionRequest,
    auth: AuthDep,
    uc: SetResultDecisionDep,
) -> CampaignResponse:
    """Set a screener's per-compound decision (SELECTED / DEFERRED / REJECTED)."""
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "campaign_id": campaign_id,
        "result_id": result_id,
        "decision": CampaignDecision(body.decision),
        "reason": body.reason,
    }
    if "notes" in body.model_fields_set:
        cmd_kwargs["notes"] = body.notes
    cmd = SetResultDecisionCommand(**cmd_kwargs)
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.patch(
    "/{campaign_id}/results/{result_id}/cells/{channel_id}",
    response_model=CampaignResponse,
)
async def override_result_cell(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: OverrideCellRequest,
    auth: AuthDep,
    uc: OverrideResultCellDep,
) -> CampaignResponse:
    """Manually override a single (result, channel) measurement cell."""
    cmd = OverrideResultCellCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        channel_id=channel_id,
        value=body.value,
        value_qualifier=ValueQualifier(body.value_qualifier),
        unit=body.unit,
        hit_call=HitCall(body.hit_call) if body.hit_call is not None else None,
        reason=body.reason,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/results", response_model=CampaignResponse)
async def add_result_row(
    campaign_id: uuid.UUID,
    body: AddResultRowRequest,
    auth: AuthDep,
    uc: AddResultRowDep,
) -> CampaignResponse:
    """Add a new compound result row (manual attribution) to a DRAFT campaign."""
    cmd = AddResultRowCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        molecule_id=body.molecule_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.delete("/{campaign_id}/results/{result_id}", response_model=CampaignResponse)
async def remove_result_row(
    campaign_id: uuid.UUID,
    result_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveResultRowDep,
) -> CampaignResponse:
    """Remove a compound result row and its measurements from a DRAFT campaign."""
    cmd = RemoveResultRowCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/refresh", response_model=CampaignResponse)
async def refresh_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: RefreshFromSourcesDep,
) -> CampaignResponse:
    """Re-resolve all non-override measurements in a DRAFT campaign."""
    cmd = RefreshFromSourcesCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/close", response_model=CampaignResponse)
async def close_campaign(
    campaign_id: uuid.UUID,
    body: CloseCampaignRequest,
    auth: AuthDep,
    uc: CloseCampaignDep,
) -> CampaignResponse:
    """Lock a DRAFT campaign and optionally publish a frozen Collection."""
    cmd = CloseCampaignCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        user_id=auth.user_id,
        signature_id=body.signature_id,
        signature_meaning=body.signature_meaning,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.post("/{campaign_id}/supersede", response_model=CampaignResponse)
async def supersede_campaign(
    campaign_id: uuid.UUID,
    body: SupersedeRequest,
    auth: AuthDep,
    uc: SupersedeCampaignDep,
) -> CampaignResponse:
    """Mark a closed campaign as superseded by a newer one.

    ``campaign_id`` is the OLD (closed) campaign to supersede.
    ``body.new_campaign_id`` is the NEW campaign that replaces it.
    Returns the old campaign (now SUPERSEDED).
    """
    cmd = SupersedeCampaignCommand(
        workspace_id=auth.workspace_id,
        old_campaign_id=campaign_id,
        new_campaign_id=body.new_campaign_id,
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


@router.get("/{campaign_id}/published")
async def get_published_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPublishedCampaignDep,
    cursor: str | None = Query(default=None),
    page_size: int | None = Query(default=None),
) -> dict[str, Any]:
    """Return the DAIKON contract document for a closed/superseded campaign."""
    query = GetPublishedCampaignQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        cursor=cursor,
        page_size=page_size,
    )
    return result_to_response(await uc(query, auth=auth))


@router.get("/{campaign_id}/preview-published")
async def preview_published_campaign(
    campaign_id: uuid.UUID,
    auth: AuthDep,
    uc: GetPublishedCampaignDep,
    cursor: str | None = Query(default=None),
    page_size: int | None = Query(default=None),
) -> dict[str, Any]:
    """Render any campaign (incl. DRAFT) through the DAIKON serializer.

    Lifts the closed/superseded status guard so the screener can preview
    what the published artifact will look like before closing.
    """
    query = GetPublishedCampaignQuery(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        cursor=cursor,
        page_size=page_size,
        bypass_status_check=True,
    )
    return result_to_response(await uc(query, auth=auth))
