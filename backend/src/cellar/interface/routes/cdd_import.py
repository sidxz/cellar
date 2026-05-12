"""CDD Vault import endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.cdd_import.import_cdd_protocol import ImportCddProtocolCommand
from cellar.application.cdd_import.list_cdd_protocols import ListCddProtocolsQuery
from cellar.application.cdd_import.mapper import (
    CddProtocolMappingResult,
    CddProtocolSummary,
    MappedCondition,
    MappedReadout,
    MappingWarning,
)
from cellar.application.cdd_import.preview_cdd_protocol_import import PreviewCddProtocolImportQuery
from cellar.application.screening._dose_response_config_serde import (
    serialize_dose_response_config,
)
from cellar.interface.dependencies import (
    AuthDep,
    ImportCddProtocolDep,
    ListCddProtocolsDep,
    PreviewCddProtocolImportDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.protocols import ProtocolResponse

router = APIRouter(prefix="/api/v1/cdd-import", tags=["cdd-import"])


class CddProtocolSummaryResponse(BaseModel):
    external_id: int
    name: str
    readout_count: int

    @classmethod
    def from_dto(cls, s: CddProtocolSummary) -> CddProtocolSummaryResponse:
        return cls(external_id=s.external_id, name=s.name, readout_count=s.readout_count)


class MappedReadoutResponse(BaseModel):
    name: str
    description: str | None = None
    data_type: str
    unit: str | None = None
    aggregation: str
    normalizations: list[str] = []
    precision: int | None = None
    pick_list_values: list[str] | None = None
    has_dose_response_config: bool
    # Same shape as ReadoutDefinitionResponse.dose_response_config so the
    # import wizard can preview intercepts, range constraints, and curve
    # type before the user clicks Import. None for non-dose-response readouts.
    dose_response_config: dict | None = None
    display_order: int

    @classmethod
    def from_dto(cls, r: MappedReadout) -> MappedReadoutResponse:
        return cls(
            name=r.name,
            description=r.description,
            data_type=r.data_type.value,
            unit=r.unit,
            aggregation=r.aggregation.value,
            normalizations=sorted(n.value for n in r.normalizations),
            precision=r.precision,
            pick_list_values=r.pick_list_values,
            has_dose_response_config=r.dose_response_config is not None,
            dose_response_config=(
                serialize_dose_response_config(r.dose_response_config)
                if r.dose_response_config is not None
                else None
            ),
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
    source_type: str
    reason: str

    @classmethod
    def from_dto(cls, w: MappingWarning) -> MappingWarningResponse:
        return cls(field_name=w.field_name, source_type=w.source_type, reason=w.reason)


class CddProtocolMappingResultResponse(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    readouts: list[MappedReadoutResponse]
    conditions: list[MappedConditionResponse]
    warnings: list[MappingWarningResponse]
    external_source_id: int

    @classmethod
    def from_dto(cls, m: CddProtocolMappingResult) -> CddProtocolMappingResultResponse:
        return cls(
            name=m.name,
            description=m.description,
            category=m.category,
            readouts=[MappedReadoutResponse.from_dto(r) for r in m.readouts],
            conditions=[MappedConditionResponse.from_dto(c) for c in m.conditions],
            warnings=[MappingWarningResponse.from_dto(w) for w in m.warnings],
            external_source_id=m.external_source_id,
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


@router.get("/protocols/{external_id}/preview", response_model=CddProtocolMappingResultResponse)
async def preview_cdd_protocol(
    external_id: int,
    auth: AuthDep,
    use_case: PreviewCddProtocolImportDep,
) -> CddProtocolMappingResultResponse:
    query = PreviewCddProtocolImportQuery(
        workspace_id=auth.workspace_id,
        external_protocol_id=external_id,
    )
    mapping = result_to_response(await use_case(query, auth=auth))
    return CddProtocolMappingResultResponse.from_dto(mapping)


@router.post("/protocols/{external_id}", response_model=ProtocolResponse, status_code=201)
async def import_cdd_protocol(
    external_id: int,
    auth: AuthDep,
    use_case: ImportCddProtocolDep,
    body: ImportCddProtocolBody | None = None,
) -> ProtocolResponse:
    command = ImportCddProtocolCommand(
        workspace_id=auth.workspace_id,
        external_protocol_id=external_id,
        name_override=body.name_override if body else None,
    )
    protocol = result_to_response(await use_case(command, auth=auth))
    return ProtocolResponse.from_domain(protocol)
