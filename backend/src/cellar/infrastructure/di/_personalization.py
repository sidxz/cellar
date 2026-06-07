"""DI registrations for the Personalization context."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.personalization.add_favorite import AddFavorite
from cellar.application.personalization.list_favorites import ListFavorites
from cellar.application.personalization.remove_favorite import RemoveFavorite
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def register_personalization(container: Container) -> None:
    def _uc(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyFavoriteRepository(uow))

        return _f

    container.define(AddFavorite, _uc(AddFavorite))
    container.define(RemoveFavorite, _uc(RemoveFavorite))
    container.define(ListFavorites, _uc(ListFavorites))
