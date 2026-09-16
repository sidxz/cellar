import inspect

from cellar.domain.research_organization.repository import CampaignRepository



def test_campaign_repository_protocol_does_not_expose_unscoped_find_by_id():
    """Cross-tenant footgun: unscoped find_by_id must not appear on the Protocol."""
    members = dict(inspect.getmembers(CampaignRepository))
    assert "find_by_id" not in members
