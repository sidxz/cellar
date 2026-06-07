"""Integration tests for SQLAlchemyFavoriteRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)

pytestmark = pytest.mark.integration


def _fav(ws: uuid.UUID, user: uuid.UUID, entity: uuid.UUID) -> Favorite:
    return Favorite.create(
        workspace_id=ws,
        user_id=user,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )


async def test_save_and_find_by_entity(uow) -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user, entity))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        found = await repo.find_by_entity(ws, user, FavoriteEntityType.PROJECT, entity)

    assert found is not None
    assert found.entity_id == entity


async def test_list_for_user_scopes_to_user_and_type(uow) -> None:
    ws, user_a, user_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    e1, e2, e3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user_a, e1))
        await repo.save(_fav(ws, user_a, e2))
        await repo.save(_fav(ws, user_b, e3))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        a_favs = await repo.list_for_user(ws, user_a, FavoriteEntityType.PROJECT)

    assert {f.entity_id for f in a_favs} == {e1, e2}


async def test_remove_deletes_the_row(uow) -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user, entity))
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.remove(ws, user, FavoriteEntityType.PROJECT, entity)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        found = await repo.find_by_entity(ws, user, FavoriteEntityType.PROJECT, entity)

    assert found is None


async def test_duplicate_natural_key_rejected_by_db(uow) -> None:
    """The unique index is the DB backstop for use-case idempotency."""
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with uow:
        repo = SQLAlchemyFavoriteRepository(uow)
        await repo.save(_fav(ws, user, entity))
        await uow.commit()

    with pytest.raises(IntegrityError):
        async with uow:
            repo = SQLAlchemyFavoriteRepository(uow)
            await repo.save(_fav(ws, user, entity))
            await uow.commit()
