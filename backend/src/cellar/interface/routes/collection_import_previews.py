"""Top-level endpoint that hands off stashed unregistered rows to the bulk-register wizard.

The preview_id is opaque to the FE — at the time of handoff it doesn't know
the collection_id yet, so this lives on a sibling router instead of under
``/api/v1/collections/{collection_id}``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cellar.domain.research_organization.bulk_add_types import RowStatus
from cellar.interface.dependencies import (
    AuthDep,
    BulkAddToCollectionDep,
    CollectionRepoUoWDep,
)

router = APIRouter(prefix="/api/v1/collection-import-previews", tags=["collection-import"])


class UnregisteredRowResponse(BaseModel):
    row_index: int
    registration_number: str | None = None
    external_id: str | None = None
    inchi_key: str | None = None
    smiles: str | None = None
    name: str | None = None
    notes: str | None = None


class UnregisteredRowsResponse(BaseModel):
    rows: list[UnregisteredRowResponse]
    collection_id: uuid.UUID
    collection_name: str | None = None


@router.get(
    "/{preview_id}/unregistered-rows",
    response_model=UnregisteredRowsResponse,
)
async def get_unregistered_rows(
    preview_id: uuid.UUID,
    auth: AuthDep,
    use_case: BulkAddToCollectionDep,
    collection_repo_uow: CollectionRepoUoWDep,
) -> UnregisteredRowsResponse:
    stashed = use_case.fetch_stash(preview_id)
    if stashed is None or stashed.workspace_id != auth.workspace_id:
        raise HTTPException(status_code=404, detail="preview not found or expired")

    collection_repo, uow = collection_repo_uow
    async with uow:
        collection = await collection_repo.find_by_id_in_workspace(
            stashed.workspace_id, stashed.collection_id
        )

    # The stash now holds ALL rows (not just unregistered) so the commit
    # path can reuse cached outcomes. Filter back down to unregistered rows
    # for the bulk-register wizard handoff.
    unregistered_indices = {
        o.row_index for o in stashed.outcomes if o.status == RowStatus.UNREGISTERED
    }
    unregistered_rows = [r for r in stashed.rows if r.row_index in unregistered_indices]

    return UnregisteredRowsResponse(
        rows=[
            UnregisteredRowResponse(
                row_index=r.row_index,
                registration_number=r.registration_number,
                external_id=r.external_id,
                inchi_key=r.inchi_key,
                smiles=r.smiles,
                name=r.name,
                notes=r.notes,
            )
            for r in unregistered_rows
        ],
        collection_id=stashed.collection_id,
        collection_name=getattr(collection, "name", None),
    )
