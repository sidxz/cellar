"""Tests for the Favorite aggregate."""

import uuid

from cellar.domain.personalization.enums import FavoriteEntityType
from cellar.domain.personalization.favorite import Favorite


def test_create_sets_fields() -> None:
    ws, user, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fav = Favorite.create(
        workspace_id=ws,
        user_id=user,
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=entity,
    )
    assert fav.workspace_id == ws
    assert fav.user_id == user
    assert fav.entity_type is FavoriteEntityType.PROJECT
    assert fav.entity_id == entity
    assert fav.version == 1
    assert fav.id is not None


def test_create_emits_no_events() -> None:
    fav = Favorite.create(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    assert fav.collect_events() == []



def test_equality_is_by_identity() -> None:
    shared_id = uuid.uuid4()
    kwargs = dict(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entity_type=FavoriteEntityType.PROJECT,
        entity_id=uuid.uuid4(),
    )
    a = Favorite(id=shared_id, **kwargs)
    b = Favorite(id=shared_id, **kwargs)
    assert a == b
