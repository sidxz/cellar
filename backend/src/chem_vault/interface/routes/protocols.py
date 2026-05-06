"""Protocol and Target API routes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from chem_vault.application.screening.condition_grouping_service import ConditionGroupingService
from chem_vault.application.screening.create_protocol import CreateProtocol, CreateProtocolCommand
from chem_vault.application.screening.create_target import CreateTarget, CreateTargetCommand
from chem_vault.application.screening.delete_target import DeleteTarget, DeleteTargetCommand
from chem_vault.application.screening.get_protocol import GetProtocol, GetProtocolQuery, ListProtocols, ListProtocolsQuery
from chem_vault.application.screening.get_target import GetTarget, GetTargetQuery, ListTargets, ListTargetsQuery
from chem_vault.application.screening.manage_protocol import (
    AddProtocolToProject,
    AddProtocolToProjectCommand,
    DeleteProtocol,
    DeleteProtocolCommand,
    ListProtocolsByProject,
    ListProtocolsByProjectQuery,
    PublishProtocol,
    PublishProtocolCommand,
    RemoveProtocolFromProject,
    RemoveProtocolFromProjectCommand,
    RetireProtocol,
    RetireProtocolCommand,
    UpdateProtocol,
    UpdateProtocolCommand,
    VersionProtocol,
    VersionProtocolCommand,
)
from chem_vault.application.screening.manage_condition_definitions import (
    AddConditionDefinition,
    AddConditionDefinitionCommand,
    RemoveConditionDefinition,
    RemoveConditionDefinitionCommand,
    UpdateConditionDefinition,
    UpdateConditionDefinitionCommand,
)
from chem_vault.application.screening.manage_control_layouts import (
    RemoveControlLayout,
    RemoveControlLayoutCommand,
    SetControlLayout,
    SetControlLayoutCommand,
)
from chem_vault.application.screening.manage_ontology_annotations import (
    RemoveOntologyAnnotation,
    RemoveOntologyAnnotationCommand,
    SetOntologyAnnotation,
    SetOntologyAnnotationCommand,
)
from chem_vault.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    AddReadoutDefinitionCommand,
    RemoveReadoutDefinition,
    RemoveReadoutDefinitionCommand,
    UpdateReadoutDefinition,
    UpdateReadoutDefinitionCommand,
    _UNSET as _RD_UNSET,
)
from chem_vault.application.screening.update_target import UpdateTarget, UpdateTargetCommand
from chem_vault.interface.dependencies import (
    AddConditionDefinitionDep,
    UpdateConditionDefinitionDep,
    AddProtocolToProjectDep,
    AddReadoutDefinitionDep,
    UpdateReadoutDefinitionDep,
    AuthDep,
    ConditionGroupingServiceDep,
    CreateProtocolDep,
    CreateTargetDep,
    DeleteProtocolDep,
    DeleteTargetDep,
    GetProtocolDep,
    GetTargetDep,
    ListProtocolsByProjectDep,
    ListProtocolsDep,
    ListTargetsDep,
    PublishProtocolDep,
    RemoveConditionDefinitionDep,
    RemoveControlLayoutDep,
    RemoveOntologyAnnotationDep,
    RemoveProtocolFromProjectDep,
    RemoveReadoutDefinitionDep,
    RetireProtocolDep,
    SetControlLayoutDep,
    SetOntologyAnnotationDep,
    UpdateProtocolDep,
    UpdateTargetDep,
    VersionProtocolDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ReadoutDefinitionResponse(BaseModel):
    id: uuid.UUID
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str
    precision: int | None = None
    normalization: str
    is_calculated: bool
    calculation_formula: str | None = None
    display_order: int
    pick_list_values: list[str] | None = None
    dose_response_config: dict | None = None


class ConditionDefinitionResponse(BaseModel):
    id: uuid.UUID
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


class ProtocolResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    protocol_type: str
    target_id: uuid.UUID | None = None
    category: str | None = None
    protocol_version: int
    parent_protocol_id: uuid.UUID | None = None
    status: str
    created_by: uuid.UUID
    # Canonical dose unit for all wells + IC50 fits of runs of this protocol.
    dose_unit: str
    readout_definitions: list[ReadoutDefinitionResponse]
    condition_definitions: list[ConditionDefinitionResponse]
    control_layouts: dict[str, str] | None = None
    ontology_annotations: dict[str, list[dict]] | None = None
    project_ids: list[uuid.UUID] = []
    recommended_hit_criteria: list[dict] | None = None

    @classmethod
    def from_domain(  # type: ignore[no-untyped-def]
        cls,
        p,
        *,
        project_ids: list[uuid.UUID] | None = None,
    ) -> ProtocolResponse:
        # Serialize ontology_annotations
        onto_annots = None
        if p.ontology_annotations:
            onto_annots = {
                slot: [
                    {"term_id": t.term_id, "label": t.label, "ontology_source": t.ontology_source, "uri": t.uri}
                    for t in terms
                ]
                for slot, terms in p.ontology_annotations.items()
            }

        return cls(
            id=p.id,
            workspace_id=p.workspace_id,
            name=p.name,
            description=p.description,
            protocol_type=p.protocol_type.value,
            target_id=p.target_id,
            category=p.category,
            protocol_version=p.protocol_version,
            parent_protocol_id=p.parent_protocol_id,
            status=p.status.value,
            created_by=p.created_by,
            dose_unit=p.dose_unit.value,
            readout_definitions=[
                ReadoutDefinitionResponse(
                    id=rd.id,
                    name=rd.name,
                    data_type=rd.data_type.value,
                    unit=rd.unit,
                    aggregation=rd.aggregation.value,
                    precision=rd.precision,
                    normalization=rd.normalization.value,
                    is_calculated=rd.is_calculated,
                    calculation_formula=rd.calculation_formula,
                    display_order=rd.display_order,
                    pick_list_values=rd.pick_list_values,
                    dose_response_config=(
                        {
                            "curve_type": rd.dose_response_config.curve_type.value,
                            "x_readout_name": rd.dose_response_config.x_readout_name,
                            "y_readout_name": rd.dose_response_config.y_readout_name,
                            "hill_slope_constraint": rd.dose_response_config.hill_slope_constraint.value,
                            "activity_threshold": rd.dose_response_config.activity_threshold,
                            "normalization_scope": rd.dose_response_config.normalization_scope.value,
                            "top_constraint": rd.dose_response_config.top_constraint,
                            "bottom_constraint": rd.dose_response_config.bottom_constraint,
                        }
                        if rd.dose_response_config is not None
                        else None
                    ),
                )
                for rd in p.readout_definitions
            ],
            condition_definitions=[
                ConditionDefinitionResponse(
                    id=cd.id,
                    name=cd.name,
                    data_type=cd.data_type.value,
                    unit=cd.unit,
                    pick_list_values=cd.pick_list_values,
                )
                for cd in p.condition_definitions
            ],
            control_layouts=(
                {k: str(v) for k, v in p.control_layouts.items()}
                if p.control_layouts
                else None
            ),
            ontology_annotations=onto_annots,
            project_ids=project_ids or [],
            recommended_hit_criteria=(
                [c.to_dict() for c in p.recommended_hit_criteria]
                if p.recommended_hit_criteria
                else None
            ),
        )


class ConditionGroupReadoutResponse(BaseModel):
    readout_definition_id: uuid.UUID
    name: str
    value: float
    unit: str | None = None
    aggregation: str
    count: int


class ConditionGroupResponse(BaseModel):
    condition_value: str
    run_count: int
    aggregated_readouts: list[ConditionGroupReadoutResponse]


class ConditionGroupsResponse(BaseModel):
    condition_name: str
    groups: list[ConditionGroupResponse]


class TargetResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    target_type: str
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None

    @classmethod
    def from_domain(cls, t) -> TargetResponse:  # type: ignore[no-untyped-def]
        return cls(
            id=t.id,
            workspace_id=t.workspace_id,
            name=t.name,
            target_type=t.target_type.value,
            organism=t.organism,
            gene_name=t.gene_name,
            uniprot_id=t.uniprot_id,
            ncbi_gene_id=t.ncbi_gene_id,
            description=t.description,
            target_class=t.target_class,
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateProtocolRequest(BaseModel):
    name: str
    description: str | None = None
    protocol_type: str
    target_id: uuid.UUID | None = None
    category: str | None = None
    dose_unit: str = "uM"
    readout_definitions: list[dict[str, Any]]
    condition_definitions: list[dict[str, Any]] | None = None


class RetireRequest(BaseModel):
    reason: str | None = None


class AddReadoutDefinitionRequest(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str = "none"
    precision: int | None = None
    normalization: str = "none"
    is_calculated: bool = False
    calculation_formula: str | None = None
    display_order: int = 0
    pick_list_values: list[str] | None = None
    dose_response_config: dict | None = None


class UpdateReadoutDefinitionRequest(BaseModel):
    """Partial-update payload. Only fields present in the JSON are applied."""

    name: str | None = None
    data_type: str | None = None
    unit: str | None = None
    aggregation: str | None = None
    precision: int | None = None
    normalization: str | None = None
    is_calculated: bool | None = None
    calculation_formula: str | None = None
    display_order: int | None = None
    pick_list_values: list[str] | None = None
    dose_response_config: dict | None = None


class CreateTargetRequest(BaseModel):
    name: str
    target_type: str
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None
    sequence: str | None = None


class UpdateTargetRequest(BaseModel):
    name: str | None = None
    target_type: str | None = None
    organism: str | None = None
    gene_name: str | None = None
    uniprot_id: str | None = None
    ncbi_gene_id: str | None = None
    description: str | None = None
    target_class: str | None = None
    sequence: str | None = None


# ---------------------------------------------------------------------------
# Protocol routes
# ---------------------------------------------------------------------------


@router.post("/protocols", response_model=ProtocolResponse, status_code=201, tags=["protocols"])
async def create_protocol(
    auth: AuthDep,
    body: CreateProtocolRequest,
    uc: CreateProtocolDep,
) -> ProtocolResponse:
    cmd = CreateProtocolCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        protocol_type=body.protocol_type,
        target_id=body.target_id,
        category=body.category,
        dose_unit=body.dose_unit,
        readout_definitions=body.readout_definitions,
        condition_definitions=body.condition_definitions or [],
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.get("/protocols", response_model=list[ProtocolResponse], tags=["protocols"])
async def list_protocols(
    auth: AuthDep,
    uc: ListProtocolsDep,
    uc_by_project: ListProtocolsByProjectDep,
    project_id: uuid.UUID | None = Query(default=None),
) -> list[ProtocolResponse]:
    if project_id is not None:
        result = await uc_by_project(
            ListProtocolsByProjectQuery(workspace_id=auth.workspace_id, project_id=project_id),
            auth=auth,
        )
        protocols = result_to_response(result)
        return [ProtocolResponse.from_domain(p) for p in protocols]
    result = await uc(ListProtocolsQuery(workspace_id=auth.workspace_id), auth=auth)
    protocols = result_to_response(result)
    return [ProtocolResponse.from_domain(p) for p in protocols]


@router.get("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def get_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: GetProtocolDep,
) -> ProtocolResponse:
    result = await uc(
        GetProtocolQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id),
        auth=auth,
    )
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/publish", response_model=ProtocolResponse, tags=["protocols"])
async def publish_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: PublishProtocolDep,
) -> ProtocolResponse:
    result = await uc(PublishProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id), auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/retire", response_model=ProtocolResponse, tags=["protocols"])
async def retire_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    body: RetireRequest,
    uc: RetireProtocolDep,
) -> ProtocolResponse:
    result = await uc(RetireProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id, reason=body.reason), auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/version", response_model=ProtocolResponse, status_code=201, tags=["protocols"])
async def version_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: VersionProtocolDep,
) -> ProtocolResponse:
    result = await uc(VersionProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id), auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


class UpdateProtocolRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    target_id: uuid.UUID | None = None
    category: str | None = None
    recommended_hit_criteria: list[dict] | None = None


@router.patch("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def update_protocol(
    protocol_id: uuid.UUID,
    body: UpdateProtocolRequest,
    auth: AuthDep,
    uc: UpdateProtocolDep,
) -> ProtocolResponse:
    """Update a DRAFT protocol's metadata."""
    from chem_vault.application.shared.sentinel import UNSET
    cmd = UpdateProtocolCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name if "name" in body.model_fields_set else UNSET,
        description=body.description if "description" in body.model_fields_set else UNSET,
        target_id=body.target_id if "target_id" in body.model_fields_set else UNSET,
        category=body.category if "category" in body.model_fields_set else UNSET,
        recommended_hit_criteria=body.recommended_hit_criteria if "recommended_hit_criteria" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete("/protocols/{protocol_id}", status_code=204, tags=["protocols"])
async def delete_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteProtocolDep,
) -> None:
    """Delete a DRAFT protocol. Only drafts can be deleted."""
    result_to_response(await uc(
        DeleteProtocolCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id),
        auth=auth,
    ))


# ---------------------------------------------------------------------------
# Readout definition routes
# ---------------------------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/readout-definitions",
    response_model=ProtocolResponse,
    status_code=201,
    tags=["protocols"],
)
async def add_readout_definition(
    protocol_id: uuid.UUID,
    body: AddReadoutDefinitionRequest,
    auth: AuthDep,
    uc: AddReadoutDefinitionDep,
) -> ProtocolResponse:
    """Add a readout definition to a DRAFT protocol."""
    cmd = AddReadoutDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        data_type=body.data_type,
        unit=body.unit,
        aggregation=body.aggregation,
        precision=body.precision,
        normalization=body.normalization,
        is_calculated=body.is_calculated,
        calculation_formula=body.calculation_formula,
        display_order=body.display_order,
        pick_list_values=body.pick_list_values,
        dose_response_config=body.dose_response_config,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.put(
    "/protocols/{protocol_id}/readout-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def update_readout_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    body: UpdateReadoutDefinitionRequest,
    auth: AuthDep,
    uc: UpdateReadoutDefinitionDep,
) -> ProtocolResponse:
    """Edit a readout definition on a DRAFT protocol. Partial-update semantics."""
    sent = body.model_fields_set
    cmd_kwargs: dict = {}
    # Mandatory IDs
    cmd_kwargs["workspace_id"] = auth.workspace_id
    cmd_kwargs["protocol_id"] = protocol_id
    cmd_kwargs["definition_id"] = definition_id
    # Only forward keys explicitly present in the request body. Otherwise
    # the use case keeps its sentinel default ("leave unchanged").
    for key in (
        "name", "data_type", "aggregation", "normalization",
        "is_calculated", "display_order",
    ):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)
    for key in (
        "unit", "precision", "calculation_formula",
        "pick_list_values", "dose_response_config",
    ):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)

    cmd = UpdateReadoutDefinitionCommand(**cmd_kwargs)
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete(
    "/protocols/{protocol_id}/readout-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_readout_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveReadoutDefinitionDep,
) -> ProtocolResponse:
    """Remove a readout definition from a DRAFT protocol."""
    cmd = RemoveReadoutDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        definition_id=definition_id,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


# ---------------------------------------------------------------------------
# Condition definition routes
# ---------------------------------------------------------------------------


class AddConditionDefinitionRequest(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None


@router.post(
    "/protocols/{protocol_id}/condition-definitions",
    response_model=ProtocolResponse,
    status_code=201,
    tags=["protocols"],
)
async def add_condition_definition(
    protocol_id: uuid.UUID,
    body: AddConditionDefinitionRequest,
    auth: AuthDep,
    uc: AddConditionDefinitionDep,
) -> ProtocolResponse:
    """Add a condition definition to a DRAFT protocol."""
    cmd = AddConditionDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        data_type=body.data_type,
        unit=body.unit,
        pick_list_values=body.pick_list_values,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


class UpdateConditionDefinitionRequest(BaseModel):
    """Partial-update payload."""

    name: str | None = None
    data_type: str | None = None
    unit: str | None = None
    pick_list_values: list[str] | None = None


@router.put(
    "/protocols/{protocol_id}/condition-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def update_condition_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    body: UpdateConditionDefinitionRequest,
    auth: AuthDep,
    uc: UpdateConditionDefinitionDep,
) -> ProtocolResponse:
    """Edit a condition definition on a DRAFT protocol. Partial-update semantics."""
    sent = body.model_fields_set
    cmd_kwargs: dict = {
        "workspace_id": auth.workspace_id,
        "protocol_id": protocol_id,
        "definition_id": definition_id,
    }
    for key in ("name", "data_type", "unit", "pick_list_values"):
        if key in sent:
            cmd_kwargs[key] = getattr(body, key)

    cmd = UpdateConditionDefinitionCommand(**cmd_kwargs)
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete(
    "/protocols/{protocol_id}/condition-definitions/{definition_id}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_condition_definition(
    protocol_id: uuid.UUID,
    definition_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveConditionDefinitionDep,
) -> ProtocolResponse:
    """Remove a condition definition from a DRAFT protocol."""
    cmd = RemoveConditionDefinitionCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        definition_id=definition_id,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


# ---------------------------------------------------------------------------
# Control layout routes
# ---------------------------------------------------------------------------


class SetControlLayoutRequest(BaseModel):
    plate_format: str
    template_id: uuid.UUID


@router.put(
    "/protocols/{protocol_id}/control-layouts",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def set_control_layout(
    protocol_id: uuid.UUID,
    body: SetControlLayoutRequest,
    auth: AuthDep,
    uc: SetControlLayoutDep,
) -> ProtocolResponse:
    """Set a default control layout (plate template) for a plate format on a DRAFT protocol."""
    cmd = SetControlLayoutCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        plate_format=body.plate_format,
        template_id=body.template_id,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete(
    "/protocols/{protocol_id}/control-layouts/{plate_format}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_control_layout(
    protocol_id: uuid.UUID,
    plate_format: str,
    auth: AuthDep,
    uc: RemoveControlLayoutDep,
) -> ProtocolResponse:
    """Remove the default control layout for a plate format from a DRAFT protocol."""
    cmd = RemoveControlLayoutCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        plate_format=plate_format,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


# ---------------------------------------------------------------------------
# Ontology annotation routes
# ---------------------------------------------------------------------------


class SetOntologyAnnotationRequest(BaseModel):
    slot: str
    terms: list[dict]


@router.put(
    "/protocols/{protocol_id}/ontology-annotations",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def set_ontology_annotation(
    protocol_id: uuid.UUID,
    body: SetOntologyAnnotationRequest,
    auth: AuthDep,
    uc: SetOntologyAnnotationDep,
) -> ProtocolResponse:
    """Set ontology terms for a slot on a DRAFT protocol."""
    cmd = SetOntologyAnnotationCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        slot=body.slot,
        terms=body.terms,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete(
    "/protocols/{protocol_id}/ontology-annotations/{slot}",
    response_model=ProtocolResponse,
    tags=["protocols"],
)
async def remove_ontology_annotation(
    protocol_id: uuid.UUID,
    slot: str,
    auth: AuthDep,
    uc: RemoveOntologyAnnotationDep,
) -> ProtocolResponse:
    """Remove all ontology terms for a slot from a DRAFT protocol."""
    cmd = RemoveOntologyAnnotationCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        slot=slot,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


# ---------------------------------------------------------------------------
# Protocol–Project association routes
# ---------------------------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/projects/{project_id}",
    status_code=204,
    tags=["protocols"],
)
async def add_protocol_to_project(
    protocol_id: uuid.UUID,
    project_id: uuid.UUID,
    auth: AuthDep,
    uc: AddProtocolToProjectDep,
) -> Response:
    """Link a protocol to a project (idempotent)."""
    result = await uc(
        AddProtocolToProjectCommand(
            workspace_id=auth.workspace_id, protocol_id=protocol_id, project_id=project_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


@router.delete(
    "/protocols/{protocol_id}/projects/{project_id}",
    status_code=204,
    tags=["protocols"],
)
async def remove_protocol_from_project(
    protocol_id: uuid.UUID,
    project_id: uuid.UUID,
    auth: AuthDep,
    uc: RemoveProtocolFromProjectDep,
) -> Response:
    """Unlink a protocol from a project."""
    result = await uc(
        RemoveProtocolFromProjectCommand(
            workspace_id=auth.workspace_id, protocol_id=protocol_id, project_id=project_id,
        ),
        auth=auth,
    )
    result_to_response(result)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Condition grouping routes
# ---------------------------------------------------------------------------


@router.get(
    "/protocols/{protocol_id}/condition-groups",
    response_model=ConditionGroupsResponse,
    tags=["protocols"],
)
async def get_condition_groups(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    condition_name: Annotated[str, Query(...)],
    svc: ConditionGroupingServiceDep,
) -> ConditionGroupsResponse:
    """Aggregate readout data grouped by a condition value."""
    result = await svc.group_by_condition(auth.workspace_id, protocol_id, condition_name)
    groups = result_to_response(result)
    return ConditionGroupsResponse(
        condition_name=condition_name,
        groups=[
            ConditionGroupResponse(
                condition_value=g.condition_value,
                run_count=g.run_count,
                aggregated_readouts=[
                    ConditionGroupReadoutResponse(
                        readout_definition_id=ar.readout_definition_id,
                        name=ar.name,
                        value=ar.value,
                        unit=ar.unit,
                        aggregation=ar.aggregation,
                        count=ar.count,
                    )
                    for ar in g.aggregated_readouts
                ],
            )
            for g in groups
        ],
    )


# ---------------------------------------------------------------------------
# Target routes
# ---------------------------------------------------------------------------


@router.post("/targets", response_model=TargetResponse, status_code=201, tags=["targets"])
async def create_target(
    auth: AuthDep,
    body: CreateTargetRequest,
    uc: CreateTargetDep,
) -> TargetResponse:
    cmd = CreateTargetCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        target_type=body.target_type,
        organism=body.organism,
        gene_name=body.gene_name,
        uniprot_id=body.uniprot_id,
        ncbi_gene_id=body.ncbi_gene_id,
        description=body.description,
        target_class=body.target_class,
        sequence=body.sequence,
    )
    result = await uc(cmd, auth=auth)
    return TargetResponse.from_domain(result_to_response(result))


@router.get("/targets", response_model=list[TargetResponse], tags=["targets"])
async def list_targets(
    auth: AuthDep,
    uc: ListTargetsDep,
) -> list[TargetResponse]:
    result = await uc(ListTargetsQuery(workspace_id=auth.workspace_id), auth=auth)
    targets = result_to_response(result)
    return [TargetResponse.from_domain(t) for t in targets]


@router.get("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def get_target(
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: GetTargetDep,
) -> TargetResponse:
    result = await uc(
        GetTargetQuery(workspace_id=auth.workspace_id, target_id=target_id),
        auth=auth,
    )
    return TargetResponse.from_domain(result_to_response(result))


@router.patch("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def update_target(
    target_id: uuid.UUID,
    body: UpdateTargetRequest,
    auth: AuthDep,
    uc: UpdateTargetDep,
) -> TargetResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateTargetCommand(
        workspace_id=auth.workspace_id,
        target_id=target_id,
        name=body.name if "name" in body.model_fields_set else UNSET,
        target_type=body.target_type if "target_type" in body.model_fields_set else UNSET,
        organism=body.organism if "organism" in body.model_fields_set else UNSET,
        gene_name=body.gene_name if "gene_name" in body.model_fields_set else UNSET,
        uniprot_id=body.uniprot_id if "uniprot_id" in body.model_fields_set else UNSET,
        ncbi_gene_id=body.ncbi_gene_id if "ncbi_gene_id" in body.model_fields_set else UNSET,
        description=body.description if "description" in body.model_fields_set else UNSET,
        target_class=body.target_class if "target_class" in body.model_fields_set else UNSET,
        sequence=body.sequence if "sequence" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return TargetResponse.from_domain(result_to_response(result))


@router.delete("/targets/{target_id}", status_code=204, tags=["targets"])
async def delete_target(
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: DeleteTargetDep,
) -> None:
    cmd = DeleteTargetCommand(workspace_id=auth.workspace_id, target_id=target_id)
    result_to_response(await uc(cmd, auth=auth))
