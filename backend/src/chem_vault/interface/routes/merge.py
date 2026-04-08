"""Molecule merge endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.chemical_registration.get_merge_history import GetMergeHistoryQuery
from chem_vault.application.chemical_registration.merge_service import MergeCommand
from chem_vault.domain.chemical_registration.enums import MergeReason
from chem_vault.domain.chemical_registration.merge_event import MergeEvent
from chem_vault.interface.dependencies import AuthDep, GetMergeHistoryDep, MergeServiceDep
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/molecules", tags=["molecules"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MergeEventResponse(BaseModel):
    id: uuid.UUID
    source_molecule_id: uuid.UUID
    target_molecule_id: uuid.UUID
    reason: str
    merged_by: uuid.UUID
    merged_at: datetime
    snapshot: dict[str, Any]
    notes: str | None = None

    @classmethod
    def from_domain(cls, event: MergeEvent) -> MergeEventResponse:
        return cls(
            id=event.id,
            source_molecule_id=event.source_molecule_id,
            target_molecule_id=event.target_molecule_id,
            reason=event.reason.value,
            merged_by=event.merged_by,
            merged_at=event.merged_at,
            snapshot=event.snapshot,
            notes=event.notes,
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class MergeBody(BaseModel):
    target_molecule_id: uuid.UUID
    reason: MergeReason = MergeReason.MANUAL_MERGE
    notes: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{source_molecule_id}/merge",
    response_model=MergeEventResponse,
    status_code=201,
)
async def merge_molecules(
    source_molecule_id: uuid.UUID,
    body: MergeBody,
    auth: AuthDep,
    use_case: MergeServiceDep,
) -> MergeEventResponse:
    command = MergeCommand(
        workspace_id=auth.workspace_id,
        source_molecule_id=source_molecule_id,
        target_molecule_id=body.target_molecule_id,
        reason=body.reason,
        merged_by=auth.user_id,
        notes=body.notes,
    )
    merge_event = result_to_response(await use_case(command, auth=auth))
    return MergeEventResponse.from_domain(merge_event)


@router.get(
    "/{molecule_id}/merge-history",
    response_model=list[MergeEventResponse],
)
async def get_merge_history(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetMergeHistoryDep,
) -> list[MergeEventResponse]:
    """Retrieve merge history for a molecule (as source or target)."""
    query = GetMergeHistoryQuery(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
    )
    events = result_to_response(await use_case(query))
    return [MergeEventResponse.from_domain(e) for e in events]
