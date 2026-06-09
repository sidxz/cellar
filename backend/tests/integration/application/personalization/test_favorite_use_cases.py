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
from cellar.domain.personalization.favorite import Favorite
from cellar.domain.shared.errors import AuthorizationError
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


def _add(session_factory) -> AddFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return AddFavorite(uow, SQLAlchemyFavoriteRepository(uow))


def _remove(session_factory) -> RemoveFavorite:
    uow = AsyncUnitOfWork(session_factory)
    return RemoveFavorite(uow, SQLAlchemyFavoriteRepository(uow))


def _list(session_factory) -> ListFavorites:
    uow = AsyncUnitOfWork(session_factory)
    return ListFavorites(uow, SQLAlchemyFavoriteRepository(uow))


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


async def test_concurrent_add_lost_race_does_not_500(
    session_factory, workspace_id, user_id
) -> None:
    """Simulate the lost side of a concurrent AddFavorite race.

    Both racers pass the use-case find-first fast path, so each calls
    ``repo.save`` with a *fresh* aggregate carrying the same natural key. The
    second insert conflicts on ``uq_favorites_ws_user_entity`` and must no-op
    (no IntegrityError / 500) rather than raise — leaving exactly one row.
    """
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    entity = uuid.uuid4()

    # Racer A commits first.
    first = await _add(session_factory)(
        AddFavoriteCommand(
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type=FavoriteEntityType.PROJECT,
            entity_id=entity,
        ),
        auth=auth,
    )
    assert isinstance(first, Success)

    # Racer B already passed find-first before A committed: it now tries to
    # save a brand-new aggregate (distinct PK) for the same natural key. The
    # idempotent ON CONFLICT DO NOTHING insert must not raise.
    losing = Favorite.create(
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(losing)  # must NOT raise IntegrityError
        await uow.commit()

    listed = await _list(session_factory)(
        ListFavoritesQuery(
            workspace_id=workspace_id, user_id=user_id, entity_type=FavoriteEntityType.PROJECT
        ),
        auth=auth,
    )
    assert isinstance(listed, Success)
    assert len(listed.unwrap()) == 1  # exactly one row survives the race


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


async def test_add_for_another_user_is_rejected(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    cmd = AddFavoriteCommand(
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),  # someone else's id
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    with pytest.raises(AuthorizationError):
        await _add(session_factory)(cmd, auth=auth)


async def test_remove_for_another_user_is_rejected(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    cmd = RemoveFavoriteCommand(
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),  # someone else's id
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    with pytest.raises(AuthorizationError):
        await _remove(session_factory)(cmd, auth=auth)


async def test_list_for_another_user_is_rejected(session_factory, workspace_id, user_id) -> None:
    auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    query = ListFavoritesQuery(
        workspace_id=workspace_id,
        user_id=uuid.uuid4(),  # someone else's id
        entity_type=FavoriteEntityType.PROJECT,
    )
    with pytest.raises(AuthorizationError):
        await _list(session_factory)(query, auth=auth)
