"""Unit tests for ``upsert_stage_by_name`` — the get-or-create shared by the
``stage_name`` import paths (add-from-runs, mirror-protocol)."""

from __future__ import annotations

import uuid

import pytest

from cellar.application.research_organization.stage_upsert import upsert_stage_by_name
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_stage import (
    CampaignStage,
    StageCriterion,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    StageKind,
)
from cellar.domain.shared.errors import ValidationError


def _campaign_with_channel() -> tuple[Campaign, CampaignChannel]:
    campaign = Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        display_order=0,
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
    )
    campaign.add_channel(channel)
    return campaign, channel


def _criterion(channel: CampaignChannel, *, value: float) -> StageCriterion:
    return StageCriterion(channel_id=channel.id, operator="lt", value=value)


def test_creates_stage_when_name_is_new() -> None:
    campaign, channel = _campaign_with_channel()

    stage, created = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=None,
    )

    assert created is True
    assert campaign.stages == [stage]
    assert stage.name == "Primary Hits"
    assert stage.display_order == 0
    assert stage.parent_stage_id is None
    assert stage.kind == StageKind.CRITERIA
    assert [c.value for c in stage.criteria] == [10.0]


def test_new_stage_appends_after_existing_ones() -> None:
    campaign, channel = _campaign_with_channel()
    campaign.add_stage(
        CampaignStage(campaign_id=campaign.id, name="Triage", display_order=3)
    )

    stage, created = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=None,
    )

    assert created is True
    assert stage.display_order == 4


def test_reuse_replaces_criteria_and_keeps_id() -> None:
    campaign, channel = _campaign_with_channel()
    first, _ = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=None,
    )
    original_id = first.id

    stage, created = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=1.0)],
        parent_stage_id=None,
    )

    assert created is False
    assert stage.id == original_id
    assert len(campaign.stages) == 1
    assert [c.value for c in campaign.stages[0].criteria] == [1.0]


def test_name_match_is_case_insensitive() -> None:
    campaign, channel = _campaign_with_channel()
    first, _ = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=None,
    )

    stage, created = upsert_stage_by_name(
        campaign,
        name="  PRIMARY hits  ",
        criteria=[_criterion(channel, value=2.0)],
        parent_stage_id=None,
    )

    assert created is False
    assert stage.id == first.id
    assert len(campaign.stages) == 1
    # The stored name is not rewritten by the re-import.
    assert campaign.stages[0].name == "Primary Hits"


def test_reuse_with_parent_sets_it() -> None:
    campaign, channel = _campaign_with_channel()
    parent = CampaignStage(campaign_id=campaign.id, name="Triage", display_order=0)
    campaign.add_stage(parent)
    upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=None,
    )

    stage, created = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=parent.id,
    )

    assert created is False
    assert stage.parent_stage_id == parent.id


def test_reuse_without_parent_keeps_existing_parent() -> None:
    campaign, channel = _campaign_with_channel()
    parent = CampaignStage(campaign_id=campaign.id, name="Triage", display_order=0)
    campaign.add_stage(parent)
    upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=parent.id,
    )

    stage, _ = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=5.0)],
        parent_stage_id=None,
    )

    assert stage.parent_stage_id == parent.id


def test_create_with_parent_sets_it() -> None:
    campaign, channel = _campaign_with_channel()
    parent = CampaignStage(campaign_id=campaign.id, name="Triage", display_order=0)
    campaign.add_stage(parent)

    stage, created = upsert_stage_by_name(
        campaign,
        name="Primary Hits",
        criteria=[_criterion(channel, value=10.0)],
        parent_stage_id=parent.id,
    )

    assert created is True
    assert stage.parent_stage_id == parent.id


def test_unknown_parent_raises_validation_error() -> None:
    campaign, channel = _campaign_with_channel()

    with pytest.raises(ValidationError):
        upsert_stage_by_name(
            campaign,
            name="Primary Hits",
            criteria=[_criterion(channel, value=10.0)],
            parent_stage_id=uuid.uuid4(),
        )

    assert campaign.stages == []


def test_manual_stage_of_that_name_raises_validation_error() -> None:
    campaign, channel = _campaign_with_channel()
    campaign.add_stage(
        CampaignStage(
            campaign_id=campaign.id,
            name="Primary Hits",
            display_order=0,
            kind=StageKind.MANUAL,
        )
    )

    with pytest.raises(ValidationError):
        upsert_stage_by_name(
            campaign,
            name="primary hits",
            criteria=[_criterion(channel, value=10.0)],
            parent_stage_id=None,
        )

    # Untouched: still manual, still criteria-free.
    assert len(campaign.stages) == 1
    assert campaign.stages[0].kind == StageKind.MANUAL
    assert campaign.stages[0].criteria == []
