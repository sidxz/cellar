"""FastAPI dependency aliases for the Personalization context."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.personalization.add_favorite import AddFavorite
from cellar.application.personalization.clear_recent_searches import ClearRecentSearches
from cellar.application.personalization.list_favorites import ListFavorites
from cellar.application.personalization.list_recent_searches import ListRecentSearches
from cellar.application.personalization.record_recent_search import RecordRecentSearch
from cellar.application.personalization.remove_favorite import RemoveFavorite
from cellar.interface.dependencies._core import _get_use_case

AddFavoriteDep = Annotated[AddFavorite, Depends(_get_use_case(AddFavorite))]
RemoveFavoriteDep = Annotated[RemoveFavorite, Depends(_get_use_case(RemoveFavorite))]
ListFavoritesDep = Annotated[ListFavorites, Depends(_get_use_case(ListFavorites))]
RecordRecentSearchDep = Annotated[RecordRecentSearch, Depends(_get_use_case(RecordRecentSearch))]
ListRecentSearchesDep = Annotated[ListRecentSearches, Depends(_get_use_case(ListRecentSearches))]
ClearRecentSearchesDep = Annotated[
    ClearRecentSearches, Depends(_get_use_case(ClearRecentSearches))
]

__all__ = [
    "AddFavoriteDep",
    "ClearRecentSearchesDep",
    "ListFavoritesDep",
    "ListRecentSearchesDep",
    "RecordRecentSearchDep",
    "RemoveFavoriteDep",
]
