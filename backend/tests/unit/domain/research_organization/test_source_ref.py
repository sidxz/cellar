"""Tests for SourceRef discriminated value object."""

import uuid

import pytest

from cellar.domain.research_organization.enums import CampaignDecision
from cellar.domain.research_organization.source_ref import (
    CampaignRef,
    CollectionRef,
    ManualRef,
    RunRef,
    SavedSearchRef,
    SourceRef,
)
from cellar.domain.shared.errors import ValidationError


# ---------- ManualRef ----------


def test_manual_ref_round_trip():
    src = ManualRef()
    data = src.to_dict()
    assert data["kind"] == "manual"
    back = SourceRef.from_dict(data)
    assert isinstance(back, ManualRef)


def test_manual_ref_with_description():
    src = ManualRef(description="hand-picked")
    data = src.to_dict()
    assert data["description"] == "hand-picked"
    back = SourceRef.from_dict(data)
    assert isinstance(back, ManualRef)
    assert back.description == "hand-picked"


# ---------- CollectionRef ----------


def test_collection_ref_requires_collection_id():
    with pytest.raises(ValidationError):
        CollectionRef(collection_id=None)  # type: ignore[arg-type]


def test_collection_ref_round_trip():
    cid = uuid.uuid4()
    src = CollectionRef(collection_id=cid)
    data = src.to_dict()
    assert data["kind"] == "collection"
    back = SourceRef.from_dict(data)
    assert isinstance(back, CollectionRef)
    assert back.collection_id == cid


def test_collection_ref_with_description():
    cid = uuid.uuid4()
    src = CollectionRef(collection_id=cid, description="batch-1")
    back = SourceRef.from_dict(src.to_dict())
    assert isinstance(back, CollectionRef)
    assert back.description == "batch-1"


# ---------- SavedSearchRef ----------


def test_saved_search_ref_requires_id():
    with pytest.raises(ValidationError):
        SavedSearchRef(saved_search_id=None)  # type: ignore[arg-type]


def test_saved_search_ref_round_trip():
    sid = uuid.uuid4()
    src = SavedSearchRef(saved_search_id=sid)
    back = SourceRef.from_dict(src.to_dict())
    assert isinstance(back, SavedSearchRef)
    assert back.saved_search_id == sid


# ---------- CampaignRef ----------


def test_campaign_ref_requires_campaign_id():
    with pytest.raises(ValidationError):
        CampaignRef(campaign_id=None)  # type: ignore[arg-type]


def test_campaign_ref_round_trip():
    cid = uuid.uuid4()
    src = CampaignRef(
        campaign_id=cid,
        decision_filter=[CampaignDecision.SELECTED, CampaignDecision.DEFERRED],
    )
    data = src.to_dict()
    assert data["kind"] == "campaign"
    assert data["decision_filter"] == ["selected", "deferred"]
    back = SourceRef.from_dict(data)
    assert isinstance(back, CampaignRef)
    assert back.campaign_id == cid
    assert CampaignDecision.SELECTED in back.decision_filter
    assert CampaignDecision.DEFERRED in back.decision_filter


def test_campaign_ref_defaults_to_selected_only():
    src = CampaignRef(campaign_id=uuid.uuid4())
    assert src.decision_filter == [CampaignDecision.SELECTED]


def test_campaign_ref_kind_is_campaign_not_derived_from_campaign():
    src = CampaignRef(campaign_id=uuid.uuid4())
    assert src.to_dict()["kind"] == "campaign"


# ---------- RunRef ----------


def test_run_ref_requires_run_id():
    with pytest.raises(ValidationError):
        RunRef(run_id=None)  # type: ignore[arg-type]


def test_run_ref_round_trip():
    rid = uuid.uuid4()
    src = RunRef(run_id=rid)
    data = src.to_dict()
    assert data["kind"] == "run"
    back = SourceRef.from_dict(data)
    assert isinstance(back, RunRef)
    assert back.run_id == rid


def test_run_ref_with_description():
    rid = uuid.uuid4()
    src = RunRef(run_id=rid, description="IC50 screen run 3")
    back = SourceRef.from_dict(src.to_dict())
    assert isinstance(back, RunRef)
    assert back.description == "IC50 screen run 3"


# ---------- from_dict dispatch ----------


def test_from_dict_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        SourceRef.from_dict({"kind": "nope"})


def test_from_dict_rejects_missing_kind():
    with pytest.raises(ValidationError):
        SourceRef.from_dict({})
