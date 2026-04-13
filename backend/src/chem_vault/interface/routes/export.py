"""Molecule export endpoints (SDF)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from chem_vault.application.chemical_registration.export_sdf import (
    ExportSDFQuery,
    MAX_SDF_EXPORT,
)
from chem_vault.interface.dependencies import AuthDep, ExportMoleculesSDFDep
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/molecules/export", tags=["export"])


class ExportSDFBody(BaseModel):
    molecule_ids: list[uuid.UUID]

    @field_validator("molecule_ids")
    @classmethod
    def check_limit(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) > MAX_SDF_EXPORT:
            msg = f"Maximum {MAX_SDF_EXPORT} molecules per export."
            raise ValueError(msg)
        return v


@router.post("/sdf")
async def export_sdf(
    body: ExportSDFBody,
    auth: AuthDep,
    use_case: ExportMoleculesSDFDep,
) -> Response:
    command = ExportSDFQuery(
        workspace_id=auth.workspace_id,
        molecule_ids=body.molecule_ids,
    )
    sdf_content = result_to_response(await use_case(command, auth=auth))
    return Response(
        content=sdf_content,
        media_type="chemical/x-sdf",
        headers={
            "Content-Disposition": 'attachment; filename="export.sdf"',
        },
    )
