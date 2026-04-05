"""Protocol and Target API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.screening.create_protocol import CreateProtocol, CreateProtocolCommand
from chem_vault.application.screening.create_target import CreateTarget, CreateTargetCommand
from chem_vault.application.screening.delete_target import DeleteTarget, DeleteTargetCommand
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.manage_protocol import (
    DeleteProtocol,
    PublishProtocol,
    RetireProtocol,
    UpdateProtocol,
    UpdateProtocolCommand,
    VersionProtocol,
)
from chem_vault.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    AddReadoutDefinitionCommand,
    RemoveReadoutDefinition,
    RemoveReadoutDefinitionCommand,
)
from chem_vault.application.screening.update_target import UpdateTarget, UpdateTargetCommand
from chem_vault.interface.dependencies import AuthDep, get_container
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
    readout_definitions: list[ReadoutDefinitionResponse]
    condition_definitions: list[ConditionDefinitionResponse]

    @classmethod
    def from_domain(cls, p) -> ProtocolResponse:  # type: ignore[no-untyped-def]
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
        )


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
    readout_definitions: list[dict]
    condition_definitions: list[dict] | None = None


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
# Dependency resolvers
# ---------------------------------------------------------------------------


def _create_protocol(c: Annotated[Container, Depends(get_container)]) -> CreateProtocol:
    return c[CreateProtocol]

def _get_protocol(c: Annotated[Container, Depends(get_container)]) -> GetProtocol:
    return c[GetProtocol]

def _list_protocols(c: Annotated[Container, Depends(get_container)]) -> ListProtocols:
    return c[ListProtocols]

def _publish_protocol(c: Annotated[Container, Depends(get_container)]) -> PublishProtocol:
    return c[PublishProtocol]

def _retire_protocol(c: Annotated[Container, Depends(get_container)]) -> RetireProtocol:
    return c[RetireProtocol]

def _version_protocol(c: Annotated[Container, Depends(get_container)]) -> VersionProtocol:
    return c[VersionProtocol]

def _update_protocol(c: Annotated[Container, Depends(get_container)]) -> UpdateProtocol:
    return c[UpdateProtocol]

def _delete_protocol(c: Annotated[Container, Depends(get_container)]) -> DeleteProtocol:
    return c[DeleteProtocol]

def _add_readout_definition(c: Annotated[Container, Depends(get_container)]) -> AddReadoutDefinition:
    return c[AddReadoutDefinition]

def _remove_readout_definition(c: Annotated[Container, Depends(get_container)]) -> RemoveReadoutDefinition:
    return c[RemoveReadoutDefinition]

def _create_target(c: Annotated[Container, Depends(get_container)]) -> CreateTarget:
    return c[CreateTarget]

def _get_target(c: Annotated[Container, Depends(get_container)]) -> GetTarget:
    return c[GetTarget]

def _list_targets(c: Annotated[Container, Depends(get_container)]) -> ListTargets:
    return c[ListTargets]

def _get_update_target(c: Annotated[Container, Depends(get_container)]) -> UpdateTarget:
    return c[UpdateTarget]

def _get_delete_target(c: Annotated[Container, Depends(get_container)]) -> DeleteTarget:
    return c[DeleteTarget]


# ---------------------------------------------------------------------------
# Protocol routes
# ---------------------------------------------------------------------------


@router.post("/protocols", response_model=ProtocolResponse, status_code=201, tags=["protocols"])
async def create_protocol(
    auth: AuthDep,
    body: CreateProtocolRequest,
    uc: Annotated[CreateProtocol, Depends(_create_protocol)],
) -> ProtocolResponse:
    cmd = CreateProtocolCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        protocol_type=body.protocol_type,
        target_id=body.target_id,
        category=body.category,
        readout_definitions=body.readout_definitions,
        condition_definitions=body.condition_definitions or [],
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.get("/protocols", response_model=list[ProtocolResponse], tags=["protocols"])
async def list_protocols(
    auth: AuthDep,
    uc: Annotated[ListProtocols, Depends(_list_protocols)],
) -> list[ProtocolResponse]:
    result = await uc(auth=auth)
    protocols = result_to_response(result)
    return [ProtocolResponse.from_domain(p) for p in protocols]


@router.get("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def get_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[GetProtocol, Depends(_get_protocol)],
) -> ProtocolResponse:
    result = await uc(protocol_id, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/publish", response_model=ProtocolResponse, tags=["protocols"])
async def publish_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[PublishProtocol, Depends(_publish_protocol)],
) -> ProtocolResponse:
    result = await uc(protocol_id, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/retire", response_model=ProtocolResponse, tags=["protocols"])
async def retire_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    body: RetireRequest,
    uc: Annotated[RetireProtocol, Depends(_retire_protocol)],
) -> ProtocolResponse:
    result = await uc(protocol_id, reason=body.reason, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.post("/protocols/{protocol_id}/version", response_model=ProtocolResponse, status_code=201, tags=["protocols"])
async def version_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[VersionProtocol, Depends(_version_protocol)],
) -> ProtocolResponse:
    result = await uc(protocol_id, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


class UpdateProtocolRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    target_id: uuid.UUID | None = None
    category: str | None = None


@router.patch("/protocols/{protocol_id}", response_model=ProtocolResponse, tags=["protocols"])
async def update_protocol(
    protocol_id: uuid.UUID,
    body: UpdateProtocolRequest,
    auth: AuthDep,
    uc: Annotated[UpdateProtocol, Depends(_update_protocol)],
) -> ProtocolResponse:
    """Update a DRAFT protocol's metadata."""
    from chem_vault.application.shared.sentinel import UNSET
    cmd = UpdateProtocolCommand(
        workspace_id=auth.workspace_id,
        protocol_id=protocol_id,
        name=body.name,
        description=body.description if "description" in body.model_fields_set else UNSET,
        target_id=body.target_id if "target_id" in body.model_fields_set else UNSET,
        category=body.category if "category" in body.model_fields_set else UNSET,
    )
    result = await uc(cmd, auth=auth)
    return ProtocolResponse.from_domain(result_to_response(result))


@router.delete("/protocols/{protocol_id}", status_code=204, tags=["protocols"])
async def delete_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[DeleteProtocol, Depends(_delete_protocol)],
) -> None:
    """Delete a DRAFT protocol. Only drafts can be deleted."""
    result_to_response(await uc(protocol_id, auth=auth))


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
    uc: Annotated[AddReadoutDefinition, Depends(_add_readout_definition)],
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
    )
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
    uc: Annotated[RemoveReadoutDefinition, Depends(_remove_readout_definition)],
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
# Target routes
# ---------------------------------------------------------------------------


@router.post("/targets", response_model=TargetResponse, status_code=201, tags=["targets"])
async def create_target(
    auth: AuthDep,
    body: CreateTargetRequest,
    uc: Annotated[CreateTarget, Depends(_create_target)],
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
    uc: Annotated[ListTargets, Depends(_list_targets)],
) -> list[TargetResponse]:
    result = await uc(auth=auth)
    targets = result_to_response(result)
    return [TargetResponse.from_domain(t) for t in targets]


@router.get("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def get_target(
    target_id: uuid.UUID,
    auth: AuthDep,
    uc: Annotated[GetTarget, Depends(_get_target)],
) -> TargetResponse:
    result = await uc(target_id, auth=auth)
    return TargetResponse.from_domain(result_to_response(result))


@router.patch("/targets/{target_id}", response_model=TargetResponse, tags=["targets"])
async def update_target(
    target_id: uuid.UUID,
    body: UpdateTargetRequest,
    auth: AuthDep,
    uc: Annotated[UpdateTarget, Depends(_get_update_target)],
) -> TargetResponse:
    from chem_vault.application.shared.sentinel import UNSET

    cmd = UpdateTargetCommand(
        workspace_id=auth.workspace_id,
        target_id=target_id,
        name=body.name,
        target_type=body.target_type,
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
    uc: Annotated[DeleteTarget, Depends(_get_delete_target)],
) -> None:
    cmd = DeleteTargetCommand(workspace_id=auth.workspace_id, target_id=target_id)
    result_to_response(await uc(cmd, auth=auth))
