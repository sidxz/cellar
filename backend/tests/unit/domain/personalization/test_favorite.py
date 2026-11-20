"""Tests for the Favorite aggregate."""

import uuid

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite


def test_create_emits_no_events() -> None:
    fav = Favorite.create(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    assert fav.collect_events() == []
