"""SAR analysis HTTP routes — R-group decomposition (Phase 1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from cellar.application.research_organization.collection_membership import (
    ListCollectionMoleculesQuery,
)
from cellar.application.sar_analysis.decompose_rgroups import DecomposeRGroupsInput
from cellar.domain.sar_analysis.rgroup_types import RGroupDecompositionResult
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._research_organization import (
    ListCollectionMoleculesDep,
)
from cellar.interface.dependencies._sar_analysis import DecomposeRGroupsDep
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import COLLECTION_EXPANSION_LIMIT

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])


class RGroupDecompositionRequest(BaseModel):
    molecule_ids: list[UUID] | None = None
    collection_id: UUID | None = None
    core_smiles: str


class RGroupAssignmentView(BaseModel):
    molecule_id: UUID
    rgroups: dict[str, str]


class RGroupDecompositionResponse(BaseModel):
    core_smiles: str
    rgroup_labels: list[str]
    assignments: list[RGroupAssignmentView]
    unmatched_ids: list[UUID]


def _serialize(result: RGroupDecompositionResult) -> RGroupDecompositionResponse:
    return RGroupDecompositionResponse(
        core_smiles=result.core_smiles,
        rgroup_labels=result.rgroup_labels,
        assignments=[
            RGroupAssignmentView(molecule_id=a.molecule_id, rgroups=a.rgroups)
            for a in result.assignments
        ],
        unmatched_ids=result.unmatched_ids,
    )


@router.post("/r-group-decomposition", status_code=status.HTTP_200_OK)
async def decompose_rgroups(
    payload: RGroupDecompositionRequest,
    auth: AuthDep,
    uc: DecomposeRGroupsDep,
    list_collection_members: ListCollectionMoleculesDep,
) -> RGroupDecompositionResponse:
    if (payload.molecule_ids is None) == (payload.collection_id is None):
        raise HTTPException(
            status_code=400,
            detail="exactly one of molecule_ids or collection_id must be set",
        )
    if not payload.core_smiles.strip():
        raise HTTPException(status_code=400, detail="core_smiles must not be empty")

    if payload.collection_id is not None:
        molecule_ids = result_to_response(
            await list_collection_members(
                ListCollectionMoleculesQuery(
                    workspace_id=auth.workspace_id,
                    collection_id=payload.collection_id,
                    offset=0,
                    limit=COLLECTION_EXPANSION_LIMIT,
                ),
                auth=auth,
            )
        )
    else:
        molecule_ids = list(payload.molecule_ids or [])

    result = await uc.execute(
        DecomposeRGroupsInput(
            molecule_ids=molecule_ids,
            workspace_id=auth.workspace_id,
            core_smiles=payload.core_smiles,
        )
    )
    return _serialize(result)
