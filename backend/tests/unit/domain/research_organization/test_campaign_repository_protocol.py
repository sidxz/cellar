import inspect

from cellar.domain.research_organization.repository import CampaignRepository


def test_campaign_repository_protocol_exposes_expected_methods():
    members = dict(inspect.getmembers(CampaignRepository))
    expected = {
        "find_by_id_in_workspace",
        "save",
        "delete",
        "find_by_project",
        "find_by_workspace",
        "is_locked",
    }
    for name in expected:
        assert name in members, f"CampaignRepository should expose {name}"


def test_campaign_repository_protocol_does_not_expose_unscoped_find_by_id():
    """Cross-tenant footgun: unscoped find_by_id must not appear on the Protocol."""
    members = dict(inspect.getmembers(CampaignRepository))
    assert "find_by_id" not in members
