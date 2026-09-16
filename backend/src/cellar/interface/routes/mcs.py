"""POST /api/v1/sar/mcs — the maximum common substructure of a molecule set.

Takes the same input shape as ``/sar/scaffold-tree`` and ``/sar/umap-cluster``
(exactly one of ``molecule_ids`` or ``collection_id``, expanded server-side)
and returns the same ``{result, job}`` envelope.

Unlike those two it always answers inline, so ``job`` is always ``null``:
``FindMCS`` runs in milliseconds on realistic sets and carries its own timeout
for the rest, so there is no wait to poll. See ``ComputeMcs`` for the
measurements and for what would change if that stopped being true.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, model_validator

from cellar.application.research_organization.collection_membership import (
    ListCollectionMoleculesQuery,
)
from cellar.application.sar_analysis.compute_mcs import (
    MAX_SET_SIZE,
    MIN_SET_SIZE,
    ComputeMcsInput,
)
from cellar.domain.sar_analysis.mcs_types import McsResult
from cellar.interface.dependencies import AuthDep
from cellar.interface.dependencies._research_organization import ListCollectionMoleculesDep
from cellar.interface.dependencies._sar_analysis import ComputeMcsDep
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import COLLECTION_EXPANSION_LIMIT

router = APIRouter(prefix="/api/v1/sar", tags=["sar-analysis"])


class ComputeMcsBody(BaseModel):
    """Exactly one of ``collection_id`` or ``molecule_ids`` must be supplied."""

    collection_id: UUID | None = None
    molecule_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _check_exactly_one_source(self) -> ComputeMcsBody:
        if (self.collection_id is not None) == bool(self.molecule_ids):
            raise ValueError("Provide exactly one of collection_id or molecule_ids.")
        return self


class McsResultDto(BaseModel):
    #: RDKit's SMARTS for the common substructure — exact, for substructure search.
    smarts: str
    #: The same substructure as plain SMILES, for depiction and for R-group
    #: decomposition's ``core_smiles``. Null when none could be produced.
    core_smiles: str | None
    num_atoms: int
    num_bonds: int
    #: True when the search hit its time limit and returned its best-so-far.
    #: A partial answer must never be read as the maximum common substructure.
    timed_out: bool
    #: Molecules the answer was computed over, after de-duplication and after
    #: skipping any member without a usable structure.
    molecule_count: int


class ComputeMcsResponse(BaseModel):
    result: McsResultDto | None
    #: Always null. Present so this endpoint's envelope matches its two
    #: siblings, which do schedule jobs.
    job: None = None


def _to_dto(r: McsResult) -> McsResultDto:
    return McsResultDto(
        smarts=r.smarts,
        core_smiles=r.core_smiles,
        num_atoms=r.num_atoms,
        num_bonds=r.num_bonds,
        timed_out=r.timed_out,
        molecule_count=r.molecule_count,
    )


@router.post("/mcs", status_code=status.HTTP_200_OK)
async def compute_mcs(
    body: ComputeMcsBody,
    auth: AuthDep,
    uc: ComputeMcsDep,
    list_collection_members: ListCollectionMoleculesDep,
) -> ComputeMcsResponse:
    """Compute the maximum common substructure of a supplied set of molecules."""
    if body.collection_id is not None:
        molecule_ids = result_to_response(
            await list_collection_members(
                ListCollectionMoleculesQuery(
                    workspace_id=auth.workspace_id,
                    collection_id=body.collection_id,
                    offset=0,
                    limit=COLLECTION_EXPANSION_LIMIT,
                ),
                auth=auth,
            )
        )
    else:
        molecule_ids = list(dict.fromkeys(body.molecule_ids or []))

    if len(molecule_ids) < MIN_SET_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Need at least {MIN_SET_SIZE} molecules for an MCS.",
        )
    if len(molecule_ids) > MAX_SET_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MCS capped at {MAX_SET_SIZE} molecules; refine the selection.",
        )

    result = await uc.execute(
        ComputeMcsInput(molecule_ids=molecule_ids, workspace_id=auth.workspace_id), auth=auth
    )
    return ComputeMcsResponse(result=_to_dto(result))
