"""Favorite (pin) endpoints — per-user bookmarks of any entity."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import Response

from cellar.application.personalization.add_favorite import AddFavoriteCommand
from cellar.application.personalization.list_favorites import ListFavoritesQuery
from cellar.application.personalization.remove_favorite import RemoveFavoriteCommand
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.interface.dependencies import (
    AddFavoriteDep,
    AuthDep,
    ListFavoritesDep,
    RemoveFavoriteDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


class FavoriteResponse(BaseModel):
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_domain(cls, favorite: Favorite) -> FavoriteResponse:
        return cls(
            entity_type=favorite.entity_type,
            entity_id=favorite.entity_id,
            created_at=favorite.created_at,
        )


class CreateFavoriteBody(BaseModel):
    entity_type: FavoriteEntityType
    entity_id: uuid.UUID


@router.get("", response_model=list[FavoriteResponse])
async def list_favorites(
    auth: AuthDep,
    use_case: ListFavoritesDep,
    entity_type: FavoriteEntityType,
) -> list[FavoriteResponse]:
    query = ListFavoritesQuery(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=entity_type,
    )
    favorites = result_to_response(await use_case(query, auth=auth))
    return [FavoriteResponse.from_domain(f) for f in favorites]


@router.post("", response_model=FavoriteResponse)
async def add_favorite(
    auth: AuthDep,
    use_case: AddFavoriteDep,
    body: CreateFavoriteBody,
) -> FavoriteResponse:
    command = AddFavoriteCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )
    favorite = result_to_response(await use_case(command, auth=auth))
    return FavoriteResponse.from_domain(favorite)


@router.delete("/{entity_type}/{entity_id}", status_code=204)
async def remove_favorite(
    auth: AuthDep,
    use_case: RemoveFavoriteDep,
    entity_type: FavoriteEntityType,
    entity_id: uuid.UUID,
) -> Response:
    command = RemoveFavoriteCommand(
        workspace_id=auth.workspace_id,
        user_id=auth.user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    result_to_response(await use_case(command, auth=auth))
    return Response(status_code=204)
