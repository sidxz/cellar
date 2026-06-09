"""Enums for the Personalization bounded context."""

from __future__ import annotations

from enum import StrEnum


class FavoriteEntityType(StrEnum):
    """Kinds of entity a user can favorite.

    Open by extension — add a value as each module adopts favorites
    (``molecule``, ``protocol``, ``collection``, ``campaign`` …). Stored as
    the string value in the ``favorites.entity_type`` column.
    """

    PROJECT = "project"
