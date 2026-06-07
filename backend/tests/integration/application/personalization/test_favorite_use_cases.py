"""Integration tests for Favorite use cases (Railway Result)."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Success
from tests.fakes.fake_auth import FakeAuth

from cellar.application.personalization.add_favorite import AddFavorite, AddFavoriteCommand
from cellar.application.personalization.list_favorites import ListFavorites, ListFavoritesQuery
from cellar.application.personalization.remove_favorite import (
    RemoveFavorite,
    RemoveFavoriteCommand,
)
from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


def _add(session_factory) -> AddFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return AddFavorite(uow, SQLAlchemyFavoriteRepository(uow), _NoOpDispatcher())


def _remove(session_factory) -> RemoveFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return RemoveFavorite(uow, SQLAlchemyFavoriteRepository(uow), _NoOpDispatcher())


def _list(session_factory) -> ListFavorites:
    uow = AsyncUnitOfWork(session_factory)
    return ListFavorites(uow, SQLAlchemyFavoriteRepository(uow))


class _NoOpDispatcher:
    async def dispatch_all(self, events) -> None:
        return None


async def test_add_is_idempotent(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    entity = uuid.uuid4()
    cmd = AddFavoriteCommand(
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )
    first = await _add(session_factory)(cmd, auth=auth)
    second = await _add(session_factory)(cmd, auth=auth)
    assert isinstance(first, Success)
    assert isinstance(second, Success)

    listed = await _list(session_factory)(
        ListFavoritesQuery(
            workspace_id=workspace_id, user_id=user_id, entity_type=FavoriteEntityType.PROJECT
        ),
        auth=auth,
    )
    assert isinstance(listed, Success)
    assert len(listed.unwrap()) == 1  # not duplicated


async def test_remove_absent_is_noop(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    cmd = RemoveFavoriteCommand(
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    result = await _remove(session_factory)(cmd, auth=auth)
    assert isinstance(result, Success)
