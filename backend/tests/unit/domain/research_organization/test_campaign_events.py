import uuid

from chem_vault.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignPublishedCollectionCreated,
    CampaignSuperseded,
)


def test_campaign_created_event_has_required_fields():
    e = CampaignCreated(
        aggregate_id=uuid.uuid4(),
        aggregate_type="Campaign",
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="EGFR Round 2",
    )
    assert e.aggregate_type == "Campaign"
    assert e.name == "EGFR Round 2"
    assert e.event_id is not None
    assert e.occurred_at is not None


def test_campaign_closed_event():
    e = CampaignClosed(
        aggregate_id=uuid.uuid4(),
        aggregate_type="Campaign",
        workspace_id=uuid.uuid4(),
        closed_by=uuid.uuid4(),
        signature_id=uuid.uuid4(),
    )
    assert e.signature_id is not None


def test_campaign_superseded_event():
    new_id = uuid.uuid4()
    e = CampaignSuperseded(
        aggregate_id=uuid.uuid4(),
        aggregate_type="Campaign",
        workspace_id=uuid.uuid4(),
        superseded_by_campaign_id=new_id,
    )
    assert e.superseded_by_campaign_id == new_id


def test_campaign_published_collection_created_event():
    coll_id = uuid.uuid4()
    e = CampaignPublishedCollectionCreated(
        aggregate_id=uuid.uuid4(),
        aggregate_type="Campaign",
        workspace_id=uuid.uuid4(),
        collection_id=coll_id,
    )
    assert e.collection_id == coll_id
