"""Disclosure request endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.chemical_registration.confirm_disclosure import ConfirmDisclosureCommand
from chem_vault.application.chemical_registration.disclosure_service import SubmitDisclosureCommand
from chem_vault.application.chemical_registration.get_disclosure import GetDisclosureQuery
from chem_vault.application.chemical_registration.list_disclosures import ListDisclosuresQuery
from chem_vault.application.chemical_registration.list_disclosures_by_workspace import ListDisclosuresByWorkspaceQuery
from chem_vault.application.chemical_registration.reject_disclosure import RejectDisclosureCommand
from chem_vault.application.chemical_registration.resolve_disclosure_conflict import ResolveConflictCommand
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.interface.dependencies import (
    AuthDep,
    ConfirmDisclosureDep,
    DisclosureServiceDep,
    GetDisclosureDep,
    ListDisclosuresByWorkspaceDep,
    ListDisclosuresDep,
    RejectDisclosureDep,
    ResolveDisclosureConflictDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/disclosures", tags=["disclosures"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DisclosureRequestResponse(BaseModel):
    id: uuid.UUID
    bulk_disclosure_id: uuid.UUID | None = None
    molecule_id: uuid.UUID
    disclosed_smiles: str
    canonical_smiles: str | None = None
    inchi_key: str | None = None
    status: str
    resolution_type: str | None = None
    resolved_to_molecule_id: uuid.UUID | None = None
    matched_molecule_id: uuid.UUID | None = None
    disclosing_org_id: uuid.UUID | None = None
    scientist_name: str | None = None
    requested_by: uuid.UUID
    requested_at: datetime
    resolved_at: datetime | None = None
    conflict_reason: str | None = None
    notes: str | None = None
    version: int

    @classmethod
    def from_domain(cls, dr: DisclosureRequest) -> DisclosureRequestResponse:
        return cls(
            id=dr.id,
            bulk_disclosure_id=dr.bulk_disclosure_id,
            molecule_id=dr.molecule_id,
            disclosed_smiles=dr.disclosed_smiles,
            canonical_smiles=dr.canonical_smiles,
            inchi_key=dr.inchi_key,
            status=dr.status.value,
            resolution_type=dr.resolution_type.value if dr.resolution_type else None,
            resolved_to_molecule_id=dr.resolved_to_molecule_id,
            matched_molecule_id=dr.matched_molecule_id,
            disclosing_org_id=dr.disclosing_org_id,
            scientist_name=dr.scientist_name,
            requested_by=dr.requested_by,
            requested_at=dr.requested_at,
            resolved_at=dr.resolved_at,
            conflict_reason=dr.conflict_reason,
            notes=dr.notes,
            version=dr.version,
        )


class DisclosureOutcomeResponse(BaseModel):
    disclosure_request: DisclosureRequestResponse
    was_merged: bool
    merged_into_molecule_id: uuid.UUID | None = None
    needs_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class SubmitDisclosureBody(BaseModel):
    molecule_id: uuid.UUID
    disclosed_smiles: str
    disclosing_org_id: uuid.UUID | None = None
    scientist_name: str | None = None
    auto_approve: bool = True
    notes: str | None = None


class ResolveConflictBody(BaseModel):
    resolution: str  # "reject" | "accept_merge" | "accept_as_new"
    reason: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=DisclosureOutcomeResponse, status_code=201)
async def submit_disclosure(
    body: SubmitDisclosureBody,
    auth: AuthDep,
    use_case: DisclosureServiceDep,
) -> DisclosureOutcomeResponse:
    command = SubmitDisclosureCommand(
        workspace_id=auth.workspace_id,
        molecule_id=body.molecule_id,
        disclosed_smiles=body.disclosed_smiles,
        requested_by=auth.user_id,
        disclosing_org_id=body.disclosing_org_id,
        scientist_name=body.scientist_name,
        auto_approve=body.auto_approve,
        notes=body.notes,
    )
    outcome = result_to_response(await use_case(command, auth=auth))
    return DisclosureOutcomeResponse(
        disclosure_request=DisclosureRequestResponse.from_domain(
            outcome.disclosure_request
        ),
        was_merged=outcome.was_merged,
        merged_into_molecule_id=outcome.merged_into_molecule_id,
        needs_confirmation=outcome.needs_confirmation,
        matched_molecule_id=outcome.matched_molecule_id,
    )


@router.get("", response_model=list[DisclosureRequestResponse])
async def list_disclosures(
    auth: AuthDep,
    use_case: ListDisclosuresByWorkspaceDep,
    status: str | None = None,
) -> list[DisclosureRequestResponse]:
    """List all disclosure requests in workspace, optionally filtered by status."""
    query = ListDisclosuresByWorkspaceQuery(
        workspace_id=auth.workspace_id, status=status
    )
    disclosures = result_to_response(await use_case(query, auth=auth))
    return [DisclosureRequestResponse.from_domain(dr) for dr in disclosures]


@router.get("/{disclosure_id}", response_model=DisclosureRequestResponse)
async def get_disclosure(
    disclosure_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetDisclosureDep,
) -> DisclosureRequestResponse:
    query = GetDisclosureQuery(workspace_id=auth.workspace_id, disclosure_id=disclosure_id)
    dr = result_to_response(await use_case(query, auth=auth))
    return DisclosureRequestResponse.from_domain(dr)


@router.get(
    "/by-molecule/{molecule_id}",
    response_model=list[DisclosureRequestResponse],
)
async def list_disclosures_for_molecule(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListDisclosuresDep,
) -> list[DisclosureRequestResponse]:
    query = ListDisclosuresQuery(workspace_id=auth.workspace_id, molecule_id=molecule_id)
    disclosures = result_to_response(await use_case(query, auth=auth))
    return [DisclosureRequestResponse.from_domain(dr) for dr in disclosures]


@router.patch(
    "/{disclosure_id}/resolve",
    response_model=DisclosureRequestResponse,
)
async def resolve_disclosure_conflict(
    disclosure_id: uuid.UUID,
    body: ResolveConflictBody,
    auth: AuthDep,
    use_case: ResolveDisclosureConflictDep,
) -> DisclosureRequestResponse:
    """Resolve a disclosure request in CONFLICT status."""
    command = ResolveConflictCommand(
        workspace_id=auth.workspace_id,
        disclosure_id=disclosure_id,
        resolution=body.resolution,
        reason=body.reason,
        resolved_by=auth.user_id,
    )
    dr = result_to_response(await use_case(command, auth=auth))
    return DisclosureRequestResponse.from_domain(dr)


# ---------------------------------------------------------------------------
# Confirm / Reject pending disclosures
# ---------------------------------------------------------------------------


class RejectDisclosureBody(BaseModel):
    reason: str | None = None


@router.post(
    "/{disclosure_id}/confirm",
    response_model=DisclosureOutcomeResponse,
)
async def confirm_disclosure(
    disclosure_id: uuid.UUID,
    auth: AuthDep,
    use_case: ConfirmDisclosureDep,
) -> DisclosureOutcomeResponse:
    """Confirm a disclosure in PENDING_CONFIRMATION status, executing the merge."""
    command = ConfirmDisclosureCommand(
        workspace_id=auth.workspace_id,
        disclosure_id=disclosure_id,
        confirmed_by=auth.user_id,
    )
    outcome = result_to_response(await use_case(command, auth=auth))
    return DisclosureOutcomeResponse(
        disclosure_request=DisclosureRequestResponse.from_domain(
            outcome.disclosure_request
        ),
        was_merged=outcome.was_merged,
        merged_into_molecule_id=outcome.merged_into_molecule_id,
    )


@router.post(
    "/{disclosure_id}/reject",
    response_model=DisclosureRequestResponse,
)
async def reject_disclosure(
    disclosure_id: uuid.UUID,
    body: RejectDisclosureBody,
    auth: AuthDep,
    use_case: RejectDisclosureDep,
) -> DisclosureRequestResponse:
    """Reject a disclosure in PENDING_CONFIRMATION status. Source molecule stays undisclosed."""
    command = RejectDisclosureCommand(
        workspace_id=auth.workspace_id,
        disclosure_id=disclosure_id,
        reason=body.reason,
        rejected_by=auth.user_id,
    )
    dr = result_to_response(await use_case(command, auth=auth))
    return DisclosureRequestResponse.from_domain(dr)
