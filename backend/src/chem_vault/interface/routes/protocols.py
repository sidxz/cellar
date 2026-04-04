"""Protocol and Target API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.screening.create_protocol import CreateProtocol, CreateProtocolCommand
from chem_vault.application.screening.create_target import CreateTarget, CreateTargetCommand
from chem_vault.application.screening.get_protocol import GetProtocol, ListProtocols
from chem_vault.application.screening.get_target import GetTarget, ListTargets
from chem_vault.application.screening.manage_protocol import PublishProtocol, RetireProtocol, VersionProtocol
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

def _create_target(c: Annotated[Container, Depends(get_container)]) -> CreateTarget:
    return c[CreateTarget]

def _get_target(c: Annotated[Container, Depends(get_container)]) -> GetTarget:
    return c[GetTarget]

def _list_targets(c: Annotated[Container, Depends(get_container)]) -> ListTargets:
    return c[ListTargets]


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
