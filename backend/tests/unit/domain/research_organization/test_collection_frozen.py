import uuid

import pytest

from chem_vault.domain.research_organization.collection import Collection
from chem_vault.domain.shared.errors import CollectionFrozenError


def test_collection_defaults_to_not_frozen():
    coll = Collection.create(
        workspace_id=uuid.uuid4(),
        name="Test",
        created_by=uuid.uuid4(),
    )
    assert coll.is_frozen is False
    assert coll.derived_from_campaign_id is None


def test_freeze_sets_flag_and_origin():
    campaign_id = uuid.uuid4()
    coll = Collection.create(
        workspace_id=uuid.uuid4(),
        name="Hits",
        created_by=uuid.uuid4(),
    )
    coll.freeze(derived_from_campaign_id=campaign_id)
    assert coll.is_frozen is True
    assert coll.derived_from_campaign_id == campaign_id


def test_freeze_is_idempotent_with_same_origin():
    campaign_id = uuid.uuid4()
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=campaign_id)
    ts_after_first = coll.updated_at
    coll.freeze(derived_from_campaign_id=campaign_id)  # no-op
    assert coll.is_frozen is True
    assert coll.updated_at == ts_after_first


def test_freeze_rejects_different_origin_after_freeze():
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=uuid.uuid4())
    with pytest.raises(CollectionFrozenError, match="already frozen"):
        coll.freeze(derived_from_campaign_id=uuid.uuid4())


def test_update_rejects_when_frozen():
    coll = Collection.create(
        workspace_id=uuid.uuid4(), name="X", created_by=uuid.uuid4()
    )
    coll.freeze(derived_from_campaign_id=uuid.uuid4())
    with pytest.raises(CollectionFrozenError, match="frozen"):
        coll.update(name="renamed")
