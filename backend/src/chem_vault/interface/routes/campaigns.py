"""Campaign lifecycle endpoints — create, manage, close, publish."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from chem_vault.application.research_organization.add_campaign_channel import (
    AddCampaignChannelCommand,
)
from chem_vault.application.research_organization.add_result_row import (
    AddResultRowCommand,
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
from chem_vault.application.research_organization.reseed_campaign import (
    ReseedCampaignCommand,
)
from chem_vault.application.research_organization.set_result_decision import (
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
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    CompoundSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from chem_vault.interface.dependencies import (
    AddCampaignChannelDep,
    AddResultRowDep,
    CloseCampaignDep,
    CreateCampaignDep,
    GetPublishedCampaignDep,
    OverrideResultCellDep,
    RefreshFromSourcesDep,
    RemoveCampaignChannelDep,
    RemoveResultRowDep,
    ReseedCampaignDep,
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
    value: float | list[str]

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


# Discriminated compound-source request models
class ExplicitListSourceDTO(BaseModel):
    kind: Literal["explicit_list"] = "explicit_list"
    molecule_ids: list[uuid.UUID]

    def to_domain(self) -> ExplicitListSource:
        return ExplicitListSource(molecule_ids=self.molecule_ids)


class CollectionSourceDTO(BaseModel):
    kind: Literal["collection"] = "collection"
    collection_id: uuid.UUID

    def to_domain(self) -> CollectionSource:
        return CollectionSource(collection_id=self.collection_id)


class SavedSearchSourceDTO(BaseModel):
    kind: Literal["saved_search"] = "saved_search"
    saved_search_id: uuid.UUID

    def to_domain(self) -> SavedSearchSource:
        return SavedSearchSource(saved_search_id=self.saved_search_id)


class DerivedFromCampaignSourceDTO(BaseModel):
    kind: Literal["derived_from_campaign"] = "derived_from_campaign"
    campaign_id: uuid.UUID
    decision_filter: list[str] = ["selected"]

    def to_domain(self) -> DerivedFromCampaignSource:
        return DerivedFromCampaignSource(
            campaign_id=self.campaign_id,
            decision_filter=[CampaignDecision(d) for d in self.decision_filter],
        )


# Union type for source parsing — Pydantic v2 discriminated union
from typing import Union
from pydantic import Field

CompoundSourceRequest = Annotated[
    Union[
        ExplicitListSourceDTO,
        CollectionSourceDTO,
        SavedSearchSourceDTO,
        DerivedFromCampaignSourceDTO,
    ],
    Field(discriminator="kind"),
]


def _source_dto_to_domain(src: Any) -> CompoundSource:
    """Coerce any source DTO to a domain CompoundSource."""
    return src.to_domain()


def _source_to_dict(src: CompoundSource) -> dict[str, Any]:
    """Serialize a domain CompoundSource to a JSON-compatible dict."""
    return src.to_dict()


class CreateCampaignRequest(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID
    compound_source: CompoundSourceRequest
    publishes_collection: bool = True
    supersedes_campaign_id: uuid.UUID | None = None


class UpdateCampaignRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class ReseedRequest(BaseModel):
    new_source: CompoundSourceRequest


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


class OverrideCellRequest(BaseModel):
    value: float | None = None
    value_qualifier: str
    unit: str
    hit_call: str | None = None


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


class CampaignResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    compound_source: dict[str, Any]
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
            compound_source=c.compound_source.to_dict(),
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


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CreateCampaignRequest,
    auth: AuthDep,
    uc: CreateCampaignDep,
) -> CampaignResponse:
    """Create a draft Campaign and seed its results from compound_source."""
    cmd = CreateCampaignCommand(
        workspace_id=auth.workspace_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        compound_source=_source_dto_to_domain(body.compound_source),
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
    """Update campaign name/description (source mutation is done via reseed)."""
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


@router.post("/{campaign_id}/reseed", response_model=CampaignResponse)
async def reseed_campaign(
    campaign_id: uuid.UUID,
    body: ReseedRequest,
    auth: AuthDep,
    uc: ReseedCampaignDep,
) -> CampaignResponse:
    """Replace the compound list of a DRAFT campaign and re-resolve measurements."""
    cmd = ReseedCampaignCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        new_source=_source_dto_to_domain(body.new_source),
    )
    campaign = result_to_response(await uc(cmd, auth=auth))
    return CampaignResponse.from_domain(campaign)


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
    cmd = SetResultDecisionCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign_id,
        result_id=result_id,
        decision=CampaignDecision(body.decision),
        reason=body.reason,
    )
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
    """Add a new compound result row to a DRAFT campaign."""
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
