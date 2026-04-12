"""External vault import endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.vault_import.import_external_protocol import ImportExternalProtocolCommand
from chem_vault.application.vault_import.list_external_protocols import ListExternalProtocolsQuery
from chem_vault.application.vault_import.mapper import (
    ExternalProtocolMappingResult,
    ExternalProtocolSummary,
    MappedCondition,
    MappedReadout,
    MappingWarning,
)
from chem_vault.application.vault_import.preview_external_protocol_import import PreviewExternalProtocolImportQuery
from chem_vault.interface.dependencies import (
    AuthDep,
    ImportExternalProtocolDep,
    ListExternalProtocolsDep,
    PreviewExternalProtocolImportDep,
)
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.routes.protocols import ProtocolResponse

router = APIRouter(prefix="/api/v1/vault-import", tags=["vault-import"])


class ExternalProtocolSummaryResponse(BaseModel):
    external_id: int
    name: str
    readout_count: int

    @classmethod
    def from_dto(cls, s: ExternalProtocolSummary) -> ExternalProtocolSummaryResponse:
        return cls(external_id=s.external_id, name=s.name, readout_count=s.readout_count)


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
    source_type: str
    reason: str

    @classmethod
    def from_dto(cls, w: MappingWarning) -> MappingWarningResponse:
        return cls(field_name=w.field_name, source_type=w.source_type, reason=w.reason)


class ExternalProtocolMappingResultResponse(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    readouts: list[MappedReadoutResponse]
    conditions: list[MappedConditionResponse]
    warnings: list[MappingWarningResponse]
    external_source_id: int

    @classmethod
    def from_dto(cls, m: ExternalProtocolMappingResult) -> ExternalProtocolMappingResultResponse:
        return cls(
            name=m.name,
            description=m.description,
            category=m.category,
            readouts=[MappedReadoutResponse.from_dto(r) for r in m.readouts],
            conditions=[MappedConditionResponse.from_dto(c) for c in m.conditions],
            warnings=[MappingWarningResponse.from_dto(w) for w in m.warnings],
            external_source_id=m.external_source_id,
        )


class ImportExternalProtocolBody(BaseModel):
    name_override: str | None = None


@router.get("/protocols", response_model=list[ExternalProtocolSummaryResponse])
async def list_external_protocols(
    auth: AuthDep,
    use_case: ListExternalProtocolsDep,
) -> list[ExternalProtocolSummaryResponse]:
    query = ListExternalProtocolsQuery(workspace_id=auth.workspace_id)
    summaries = result_to_response(await use_case(query, auth=auth))
    return [ExternalProtocolSummaryResponse.from_dto(s) for s in summaries]


@router.get("/protocols/{external_id}/preview", response_model=ExternalProtocolMappingResultResponse)
async def preview_external_protocol(
    external_id: int,
    auth: AuthDep,
    use_case: PreviewExternalProtocolImportDep,
) -> ExternalProtocolMappingResultResponse:
    query = PreviewExternalProtocolImportQuery(
        workspace_id=auth.workspace_id,
        external_protocol_id=external_id,
    )
    mapping = result_to_response(await use_case(query, auth=auth))
    return ExternalProtocolMappingResultResponse.from_dto(mapping)


@router.post("/protocols/{external_id}", response_model=ProtocolResponse, status_code=201)
async def import_external_protocol(
    external_id: int,
    auth: AuthDep,
    use_case: ImportExternalProtocolDep,
    body: ImportExternalProtocolBody | None = None,
) -> ProtocolResponse:
    command = ImportExternalProtocolCommand(
        workspace_id=auth.workspace_id,
        external_protocol_id=external_id,
        name_override=body.name_override if body else None,
    )
    protocol = result_to_response(await use_case(command, auth=auth))
    return ProtocolResponse.from_domain(protocol)
