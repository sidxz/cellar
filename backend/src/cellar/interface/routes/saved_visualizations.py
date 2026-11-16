"""Saved visualizations: named workbench views (what they show, how they look; never data)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from cellar.application.auth import AuthContext
from cellar.application.research_organization.saved_visualizations import (
    CreateSavedVisualizationCommand,
    DeleteSavedVisualizationCommand,
    GetSavedVisualizationQuery,
    ListedView,
    ListSavedVisualizationsQuery,
    UpdateSavedVisualizationCommand,
)
from cellar.application.shared.sentinel import UNSET
from cellar.application.visualization.get_dataset import DatasetLevel
from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.saved_visualization import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    SavedVisualization,
)
from cellar.interface.dependencies import (
    AuthDep,
    CreateSavedVisualizationDep,
    DeleteSavedVisualizationDep,
    GetSavedVisualizationDep,
    ListSavedVisualizationsDep,
    UpdateSavedVisualizationDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.routes.visualization import DatasetRequest

router = APIRouter(prefix="/api/v1/saved-visualizations", tags=["saved-visualizations"])


class _SavedVisualizationFields(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    level: DatasetLevel
    visibility: SearchVisibility
    project_id: uuid.UUID | None = None
    created_by: uuid.UUID
    can_edit: bool
    version: int
    updated_at: datetime | None = None

    @staticmethod
    def fields_of(view: SavedVisualization, auth: AuthContext) -> dict[str, Any]:
        return {
            "id": view.id,
            "name": view.name,
            "description": view.description,
            "level": cast(DatasetLevel, view.level),
            "visibility": view.visibility,
            "project_id": view.project_id,
            "created_by": view.created_by,
            "can_edit": view.can_be_edited_by(auth.user_id, is_admin=auth.is_admin),
            "version": view.version,
            "updated_at": view.updated_at,
        }


class ProtocolRefResponse(BaseModel):
    id: uuid.UUID
    name: str


class SavedVisualizationSummaryResponse(_SavedVisualizationFields):
    # The protocols the view reads that still exist: its own first, then the compared ones.
    protocols: list[ProtocolRefResponse]

    @classmethod
    def from_listed(
        cls, listed: ListedView, auth: AuthContext
    ) -> SavedVisualizationSummaryResponse:
        return cls(
            **cls.fields_of(listed.view, auth),
            protocols=[ProtocolRefResponse(id=p.id, name=p.name) for p in listed.protocols],
        )


class SavedVisualizationResponse(_SavedVisualizationFields):
    # The dataset request to load: the saved one less what no longer exists; null when its
    # run or protocol is gone.
    dataset: DatasetRequest | None
    config: dict[str, Any]
    # One plain-language line per thing left out.
    unresolved: list[str] = []

    @classmethod
    def opened(
        cls,
        view: SavedVisualization,
        source: dict[str, Any] | None,
        unresolved: list[str],
        auth: AuthContext,
    ) -> SavedVisualizationResponse:
        dataset = (
            None
            if source is None
            else DatasetRequest.model_validate({"source": source, "level": view.level})
        )
        return cls(
            **cls.fields_of(view, auth), dataset=dataset, config=view.config, unresolved=unresolved
        )


def _source(dataset: DatasetRequest) -> dict[str, Any]:
    return dataset.source.model_dump(mode="json")


class CreateSavedVisualizationBody(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    visibility: SearchVisibility = SearchVisibility.PRIVATE
    project_id: uuid.UUID | None = None
    dataset: DatasetRequest
    config: dict[str, Any]


class UpdateSavedVisualizationBody(BaseModel):
    """Only the fields sent change; ``expected_version`` is the version the edit was made
    from."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    visibility: SearchVisibility | None = None
    project_id: uuid.UUID | None = None
    dataset: DatasetRequest | None = None
    config: dict[str, Any] | None = None


@router.get("", response_model=list[SavedVisualizationSummaryResponse])
async def list_saved_visualizations(
    auth: AuthDep, uc: ListSavedVisualizationsDep, protocol_id: uuid.UUID | None = None
) -> list[SavedVisualizationSummaryResponse]:
    """Views the caller can see, by name; only those reading ``protocol_id`` when given."""
    query = ListSavedVisualizationsQuery(workspace_id=auth.workspace_id, protocol_id=protocol_id)
    views = result_to_response(await uc(query, auth=auth))
    return [SavedVisualizationSummaryResponse.from_listed(v, auth) for v in views]


@router.get("/{view_id}", response_model=SavedVisualizationResponse)
async def get_saved_visualization(
    view_id: uuid.UUID, auth: AuthDep, uc: GetSavedVisualizationDep
) -> SavedVisualizationResponse:
    """A view, with its source resolved against current runs and protocols."""
    query = GetSavedVisualizationQuery(workspace_id=auth.workspace_id, view_id=view_id)
    opened = result_to_response(await uc(query, auth=auth))
    return SavedVisualizationResponse.opened(opened.view, opened.source, opened.unresolved, auth)


@router.post("", response_model=SavedVisualizationResponse, status_code=201)
async def create_saved_visualization(
    body: CreateSavedVisualizationBody, auth: AuthDep, uc: CreateSavedVisualizationDep
) -> SavedVisualizationResponse:
    command = CreateSavedVisualizationCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        description=body.description,
        source=_source(body.dataset),
        level=body.dataset.level,
        config=body.config,
        visibility=body.visibility,
        project_id=body.project_id,
        created_by=auth.user_id,
    )
    view = result_to_response(await uc(command, auth=auth))
    return SavedVisualizationResponse.opened(view, view.source, [], auth)


@router.patch("/{view_id}", response_model=SavedVisualizationResponse)
async def update_saved_visualization(
    view_id: uuid.UUID,
    body: UpdateSavedVisualizationBody,
    auth: AuthDep,
    uc: UpdateSavedVisualizationDep,
) -> SavedVisualizationResponse:
    sent = body.model_fields_set
    command = UpdateSavedVisualizationCommand(
        workspace_id=auth.workspace_id,
        view_id=view_id,
        expected_version=body.expected_version,
        name=body.name,
        description=body.description if "description" in sent else UNSET,
        source=_source(body.dataset) if body.dataset is not None else None,
        level=body.dataset.level if body.dataset is not None else None,
        config=body.config,
        visibility=body.visibility,
        project_id=body.project_id if "project_id" in sent else UNSET,
    )
    opened = result_to_response(await uc(command, auth=auth))
    return SavedVisualizationResponse.opened(opened.view, opened.source, opened.unresolved, auth)


@router.delete("/{view_id}", status_code=204)
async def delete_saved_visualization(
    view_id: uuid.UUID, auth: AuthDep, uc: DeleteSavedVisualizationDep
) -> Response:
    command = DeleteSavedVisualizationCommand(workspace_id=auth.workspace_id, view_id=view_id)
    result_to_response(await uc(command, auth=auth))
    return Response(status_code=204)
