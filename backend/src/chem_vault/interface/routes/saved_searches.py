"""SavedSearch CRUD endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.research_organization.create_saved_search import CreateSavedSearchCommand
from chem_vault.application.research_organization.delete_saved_search import DeleteSavedSearchCommand
from chem_vault.application.research_organization.get_saved_search import (
    GetSavedSearchQuery,
    ListSavedSearchesQuery,
)
from chem_vault.application.research_organization.update_saved_search import UpdateSavedSearchCommand
from chem_vault.domain.research_organization.saved_search import SavedSearch, SearchVisibility
from chem_vault.interface.dependencies import (
    AuthDep,
    CreateSavedSearchDep,
    DeleteSavedSearchDep,
    GetSavedSearchDep,
    ListSavedSearchesDep,
    UpdateSavedSearchDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/saved-searches", tags=["saved-searches"])


class SavedSearchResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    project_id: uuid.UUID | None = None
    query: dict[str, Any]
    columns: dict[str, Any] | None = None
    visibility: SearchVisibility
    created_by: uuid.UUID
    version: int

    @classmethod
    def from_domain(cls, search: SavedSearch) -> SavedSearchResponse:
        return cls(
            id=search.id,
            workspace_id=search.workspace_id,
            name=search.name,
            project_id=search.project_id,
            query=search.query,
            columns=search.columns,
            visibility=search.visibility,
            created_by=search.created_by,
            version=search.version,
        )


class CreateSavedSearchBody(BaseModel):
    name: str
    query: dict[str, Any]
    columns: dict[str, Any] | None = None
    visibility: str = "private"
    project_id: uuid.UUID | None = None


class UpdateSavedSearchBody(BaseModel):
    name: str | None = None
    query: dict[str, Any] | None = None
    columns: dict[str, Any] | None = None
    visibility: str | None = None
    project_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


@router.get("", response_model=list[SavedSearchResponse])
async def list_saved_searches(
    auth: AuthDep,
    use_case: ListSavedSearchesDep,
    project_id: uuid.UUID | None = None,
    mine: bool = False,
) -> list[SavedSearchResponse]:
    query = ListSavedSearchesQuery(
        workspace_id=auth.workspace_id,
        project_id=project_id,
        created_by=auth.user_id if mine else None,
    )
    searches = result_to_response(await use_case(query))
    return [SavedSearchResponse.from_domain(s) for s in searches]


@router.get("/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    search_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetSavedSearchDep,
) -> SavedSearchResponse:
    query = GetSavedSearchQuery(
        workspace_id=auth.workspace_id, saved_search_id=search_id
    )
    search = result_to_response(await use_case(query))
    return SavedSearchResponse.from_domain(search)


@router.post("", response_model=SavedSearchResponse, status_code=201)
async def create_saved_search(
    body: CreateSavedSearchBody,
    auth: AuthDep,
    use_case: CreateSavedSearchDep,
) -> SavedSearchResponse:
    command = CreateSavedSearchCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        query=body.query,
        columns=body.columns,
        visibility=body.visibility,
        project_id=body.project_id,
        created_by=auth.user_id,
    )
    search = result_to_response(await use_case(command, auth=auth))
    return SavedSearchResponse.from_domain(search)


@router.patch("/{search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    search_id: uuid.UUID,
    body: UpdateSavedSearchBody,
    auth: AuthDep,
    use_case: UpdateSavedSearchDep,
) -> SavedSearchResponse:
    provided = body.model_fields_set
    command = UpdateSavedSearchCommand(
        workspace_id=auth.workspace_id,
        saved_search_id=search_id,
        name=body.name if "name" in provided else None,
        query=body.query if "query" in provided else None,
        columns=body.columns if "columns" in provided else ...,
        visibility=body.visibility if "visibility" in provided else None,
        project_id=body.project_id if "project_id" in provided else ...,
    )
    search = result_to_response(await use_case(command, auth=auth))
    return SavedSearchResponse.from_domain(search)


@router.delete("/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteSavedSearchDep,
) -> None:
    command = DeleteSavedSearchCommand(
        workspace_id=auth.workspace_id, saved_search_id=search_id
    )
    result_to_response(await use_case(command, auth=auth))
