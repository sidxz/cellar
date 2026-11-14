"""DI registrations for the Personalization context."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.personalization.add_favorite import AddFavorite
from cellar.application.personalization.clear_recent_searches import ClearRecentSearches
from cellar.application.personalization.list_favorites import ListFavorites
from cellar.application.personalization.list_recent_searches import ListRecentSearches
from cellar.application.personalization.record_recent_search import RecordRecentSearch
from cellar.application.personalization.remove_favorite import RemoveFavorite
from cellar.infrastructure.persistence.sqlalchemy.personalization.favorite_repository import (
    SQLAlchemyFavoriteRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.personalization.recent_search_repository import (
    SQLAlchemyRecentSearchRepository,
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

    # Recent searches: plain-CRUD repo on its own sessions, no UoW.
    def _recent(uc_cls: type):
        return lambda c: uc_cls(SQLAlchemyRecentSearchRepository(c[async_sessionmaker]))

    container.define(RecordRecentSearch, _recent(RecordRecentSearch))
    container.define(ListRecentSearches, _recent(ListRecentSearches))
    container.define(ClearRecentSearches, _recent(ClearRecentSearches))
