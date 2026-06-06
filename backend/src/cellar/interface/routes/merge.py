"""Molecule merge endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.chemical_registration.get_merge_history import GetMergeHistoryQuery
from cellar.application.chemical_registration.get_merge_impact import (
    GetMergeImpactQuery,
    MergeImpact,
    MergeImpactCategory,
    MoleculeSummary,
)
from cellar.application.chemical_registration.merge_service import MergeCommand
from cellar.domain.chemical_registration.enums import MergeReason
from cellar.domain.chemical_registration.merge_event import MergeEvent
from cellar.interface.dependencies import (
    AuthDep,
    GetMergeHistoryDep,
    GetMergeImpactDep,
    MergeServiceDep,
)
from cellar.interface.error_handlers import result_to_response

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
    events = result_to_response(await use_case(query, auth=auth))
    return [MergeEventResponse.from_domain(e) for e in events]


# ---------------------------------------------------------------------------
# Merge impact preview
# ---------------------------------------------------------------------------


class MoleculeSummaryResponse(BaseModel):
    id: uuid.UUID
    registration_number: str
    name: str
    structure_status: str

    @classmethod
    def from_domain(cls, s: MoleculeSummary) -> MoleculeSummaryResponse:
        return cls(
            id=s.id,
            registration_number=s.registration_number,
            name=s.name,
            structure_status=s.structure_status,
        )


class MergeImpactCategoryResponse(BaseModel):
    name: str
    label: str
    count: int
    items: list[dict[str, Any]] = []
    is_blocker: bool = False

    @classmethod
    def from_domain(cls, c: MergeImpactCategory) -> MergeImpactCategoryResponse:
        return cls(
            name=c.name,
            label=c.label,
            count=c.count,
            items=c.items,
            is_blocker=c.is_blocker,
        )


class MergeImpactResponse(BaseModel):
    source: MoleculeSummaryResponse
    target: MoleculeSummaryResponse
    categories: list[MergeImpactCategoryResponse]
    blockers: list[str]

    @classmethod
    def from_domain(cls, impact: MergeImpact) -> MergeImpactResponse:
        return cls(
            source=MoleculeSummaryResponse.from_domain(impact.source),
            target=MoleculeSummaryResponse.from_domain(impact.target),
            categories=[MergeImpactCategoryResponse.from_domain(c) for c in impact.categories],
            blockers=impact.blockers,
        )


@router.get(
    "/{source_molecule_id}/merge-impact/{target_molecule_id}",
    response_model=MergeImpactResponse,
)
async def get_merge_impact(
    source_molecule_id: uuid.UUID,
    target_molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetMergeImpactDep,
) -> MergeImpactResponse:
    """Preview what data would be affected by merging source into target."""
    query = GetMergeImpactQuery(
        workspace_id=auth.workspace_id,
        source_molecule_id=source_molecule_id,
        target_molecule_id=target_molecule_id,
    )
    impact = result_to_response(await use_case(query, auth=auth))
    return MergeImpactResponse.from_domain(impact)
