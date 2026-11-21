"""A campaign managed by another app: only that app changes its structure."""

import uuid

import pytest

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_management import (
    CampaignManagedElsewhereError,
    CampaignManagement,
    ensure_writable_by,
)
from cellar.domain.research_organization.events import CampaignManagementSet, CampaignReleased
from cellar.domain.shared.errors import ConflictError, DataLockedError, ValidationError

DAIKON = CampaignManagement(
    managed_by="daikon", url="http://localhost:3002/screens/S1?round=R1", label="Daikon"
)


def _campaign() -> Campaign:
    return Campaign(
        workspace_id=uuid.uuid4(), project_id=uuid.uuid4(), name="Round 1", created_by=uuid.uuid4()
    )


def _managed() -> Campaign:
    c = _campaign()
    c.set_management(DAIKON, user_id=uuid.uuid4())
    c.clear_events()
    return c


def test_unmanaged_campaign_is_writable_by_anyone():
    ensure_writable_by(None, None)
    ensure_writable_by(None, "daikon")
    _campaign().ensure_writable_by(None)


def test_managing_app_may_write():
    ensure_writable_by(DAIKON, "daikon")
    _managed().ensure_writable_by("daikon")


@pytest.mark.parametrize("acting", [None, "other-app"])
def test_others_are_refused_with_the_label_and_url(acting):
    with pytest.raises(CampaignManagedElsewhereError) as caught:
        _managed().ensure_writable_by(acting)
    error = caught.value
    assert isinstance(error, DataLockedError)
    assert "managed in Daikon" in error.message
    assert error.body_extras() == {
        "managed_by": "daikon",
        "managed_label": "Daikon",
        "managed_url": DAIKON.url,
    }


@pytest.mark.parametrize(
    ("url", "label", "managed_by"),
    [
        ("ftp://x.org/a", "Daikon", "daikon"),
        ("javascript:alert(1)", "Daikon", "daikon"),
        ("http:///nohost", "Daikon", "daikon"),
        ("https://d.org/s", "", "daikon"),
        ("https://d.org/s", "Daikon", " "),
        ("https://d.org/s", "x" * 101, "daikon"),
    ],
)
def test_management_validates_url_label_and_app(url, label, managed_by):
    with pytest.raises(ValidationError):
        CampaignManagement(managed_by=managed_by, url=url, label=label)


def test_set_management_registers_event():
    c = _campaign()
    who = uuid.uuid4()
    c.set_management(DAIKON, user_id=who)
    assert c.management == DAIKON
    [event] = [e for e in c.collect_events() if isinstance(e, CampaignManagementSet)]
    assert (event.managed_by, event.url, event.label, event.set_by) == (
        "daikon",
        DAIKON.url,
        "Daikon",
        who,
    )


def test_set_management_again_by_the_same_app_updates_it():
    c = _managed()
    moved = CampaignManagement(managed_by="daikon", url="https://d.org/screens/S2", label="Daikon")
    c.set_management(moved, user_id=uuid.uuid4())
    assert c.management == moved


def test_set_management_by_another_app_conflicts():
    c = _managed()
    other = CampaignManagement(managed_by="other-app", url="https://o.org/x", label="Other")
    with pytest.raises(ConflictError):
        c.set_management(other, user_id=uuid.uuid4())
    assert c.management == DAIKON


def test_release_needs_a_reason_and_a_managed_campaign():
    with pytest.raises(ValidationError):
        _managed().release_management(reason="  ", user_id=uuid.uuid4())
    with pytest.raises(ConflictError):
        _campaign().release_management(reason="round abandoned", user_id=uuid.uuid4())


def test_release_clears_and_registers_event():
    c = _managed()
    who = uuid.uuid4()
    c.release_management(reason=" round abandoned ", user_id=who)
    assert c.management is None
    c.ensure_writable_by(None)
    [event] = [e for e in c.collect_events() if isinstance(e, CampaignReleased)]
    assert (event.previous_managed_by, event.previous_label, event.reason, event.released_by) == (
        "daikon",
        "Daikon",
        "round abandoned",
        who,
    )
