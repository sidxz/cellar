import uuid

import pytest

from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    CompoundSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import ValidationError


def test_explicit_list_round_trip():
    ids = [uuid.uuid4(), uuid.uuid4()]
    src = ExplicitListSource(molecule_ids=ids)
    data = src.to_dict()
    assert data["kind"] == "explicit_list"
    back = CompoundSource.from_dict(data)
    assert isinstance(back, ExplicitListSource)
    assert back.molecule_ids == ids


def test_collection_source_requires_collection_id():
    with pytest.raises(ValidationError):
        CollectionSource(collection_id=None)  # type: ignore[arg-type]


def test_collection_source_round_trip():
    cid = uuid.uuid4()
    src = CollectionSource(collection_id=cid)
    data = src.to_dict()
    assert data["kind"] == "collection"
    back = CompoundSource.from_dict(data)
    assert isinstance(back, CollectionSource)
    assert back.collection_id == cid


def test_saved_search_source_round_trip():
    sid = uuid.uuid4()
    src = SavedSearchSource(saved_search_id=sid)
    back = CompoundSource.from_dict(src.to_dict())
    assert isinstance(back, SavedSearchSource)
    assert back.saved_search_id == sid


def test_saved_search_source_requires_id():
    with pytest.raises(ValidationError):
        SavedSearchSource(saved_search_id=None)  # type: ignore[arg-type]


def test_derived_from_campaign_filters_decisions():
    cid = uuid.uuid4()
    src = DerivedFromCampaignSource(
        campaign_id=cid, decision_filter=[CampaignDecision.SELECTED]
    )
    data = src.to_dict()
    assert data["decision_filter"] == ["selected"]
    back = CompoundSource.from_dict(data)
    assert isinstance(back, DerivedFromCampaignSource)
    assert back.campaign_id == cid
    assert back.decision_filter == [CampaignDecision.SELECTED]


def test_derived_from_campaign_defaults_to_selected_only():
    src = DerivedFromCampaignSource(campaign_id=uuid.uuid4())
    assert src.decision_filter == [CampaignDecision.SELECTED]


def test_derived_from_campaign_requires_campaign_id():
    with pytest.raises(ValidationError):
        DerivedFromCampaignSource(campaign_id=None)  # type: ignore[arg-type]


def test_explicit_list_rejects_empty():
    with pytest.raises(ValidationError):
        ExplicitListSource(molecule_ids=[])


def test_from_dict_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        CompoundSource.from_dict({"kind": "nope"})


def test_from_dict_rejects_missing_kind():
    with pytest.raises(ValidationError):
        CompoundSource.from_dict({})
