"""CDD Vault import endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.cdd_import.import_cdd_protocol import ImportCddProtocolCommand
from chem_vault.application.cdd_import.list_cdd_protocols import ListCddProtocolsQuery
from chem_vault.application.cdd_import.mapper import (
    CddProtocolMappingResult,
    CddProtocolSummary,
    MappedCondition,
    MappedReadout,
    MappingWarning,
)
from chem_vault.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImportQuery
from chem_vault.interface.dependencies import (
    AuthDep,
    ImportCddProtocolDep,
    ListCddProtocolsDep,
    PreviewCddProtocolImportDep,
)
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.routes.protocols import ProtocolResponse

router = APIRouter(prefix="/api/v1/cdd-import", tags=["cdd-import"])


class CddProtocolSummaryResponse(BaseModel):
    cdd_id: int
    name: str
    readout_count: int

    @classmethod
    def from_dto(cls, s: CddProtocolSummary) -> CddProtocolSummaryResponse:
        return cls(cdd_id=s.cdd_id, name=s.name, readout_count=s.readout_count)


class MappedReadoutResponse(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    aggregation: str
    normalization: str
    precision: int | None = None
    pick_list_values: list[str] | None = None
    has_dose_response_config: bool
    display_order: int

    @classmethod
    def from_dto(cls, r: MappedReadout) -> MappedReadoutResponse:
        return cls(
            name=r.name,
            data_type=r.data_type.value,
            unit=r.unit,
            aggregation=r.aggregation.value,
            normalization=r.normalization.value,
            precision=r.precision,
            pick_list_values=r.pick_list_values,
            has_dose_response_config=r.dose_response_config is not None,
            display_order=r.display_order,
        )


class MappedConditionResponse(BaseModel):
    name: str
    data_type: str
    unit: str | None = None
    pick_list_values: list[str] | None = None

    @classmethod
    def from_dto(cls, c: MappedCondition) -> MappedConditionResponse:
        return cls(
            name=c.name,
            data_type=c.data_type.value,
            unit=c.unit,
            pick_list_values=c.pick_list_values,
        )


class MappingWarningResponse(BaseModel):
    field_name: str
    cdd_type: str
    reason: str

    @classmethod
    def from_dto(cls, w: MappingWarning) -> MappingWarningResponse:
        return cls(field_name=w.field_name, cdd_type=w.cdd_type, reason=w.reason)


class CddProtocolMappingResultResponse(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    readouts: list[MappedReadoutResponse]
    conditions: list[MappedConditionResponse]
    warnings: list[MappingWarningResponse]
    cdd_source_id: int

    @classmethod
    def from_dto(cls, m: CddProtocolMappingResult) -> CddProtocolMappingResultResponse:
        return cls(
            name=m.name,
            description=m.description,
            category=m.category,
            readouts=[MappedReadoutResponse.from_dto(r) for r in m.readouts],
            conditions=[MappedConditionResponse.from_dto(c) for c in m.conditions],
            warnings=[MappingWarningResponse.from_dto(w) for w in m.warnings],
            cdd_source_id=m.cdd_source_id,
        )


class ImportCddProtocolBody(BaseModel):
    name_override: str | None = None


@router.get("/protocols", response_model=list[CddProtocolSummaryResponse])
async def list_cdd_protocols(
    auth: AuthDep,
    use_case: ListCddProtocolsDep,
) -> list[CddProtocolSummaryResponse]:
    query = ListCddProtocolsQuery(workspace_id=auth.workspace_id)
    summaries = result_to_response(await use_case(query, auth=auth))
    return [CddProtocolSummaryResponse.from_dto(s) for s in summaries]


@router.get("/protocols/{cdd_id}/preview", response_model=CddProtocolMappingResultResponse)
async def preview_cdd_protocol(
    cdd_id: int,
    auth: AuthDep,
    use_case: PreviewCddProtocolImportDep,
) -> CddProtocolMappingResultResponse:
    query = PreviewCddProtocolImportQuery(
        workspace_id=auth.workspace_id,
        cdd_protocol_id=cdd_id,
    )
    mapping = result_to_response(await use_case(query, auth=auth))
    return CddProtocolMappingResultResponse.from_dto(mapping)


@router.post("/protocols/{cdd_id}", response_model=ProtocolResponse, status_code=201)
async def import_cdd_protocol(
    cdd_id: int,
    auth: AuthDep,
    use_case: ImportCddProtocolDep,
    body: ImportCddProtocolBody | None = None,
) -> ProtocolResponse:
    command = ImportCddProtocolCommand(
        workspace_id=auth.workspace_id,
        cdd_protocol_id=cdd_id,
        name_override=body.name_override if body else None,
    )
    protocol = result_to_response(await use_case(command, auth=auth))
    return ProtocolResponse.from_domain(protocol)
