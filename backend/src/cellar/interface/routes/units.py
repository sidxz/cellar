"""Unit suggestions for readout and condition units."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.screening.list_units import ListUnitsQuery
from cellar.interface.dependencies import AuthDep, ListUnitsDep
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/units", tags=["units"])


class UnitSuggestionResponse(BaseModel):
    unit: str
    group: str


@router.get("", response_model=list[UnitSuggestionResponse])
async def list_units(auth: AuthDep, use_case: ListUnitsDep) -> list[UnitSuggestionResponse]:
    units = result_to_response(
        await use_case(ListUnitsQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return [UnitSuggestionResponse(unit=u.unit, group=u.group) for u in units]
