"""Unit tests for AddCampaignStage use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_campaign_stage import (
    AddCampaignStage,
    AddCampaignStageCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_stage import StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    DataLockedError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft_campaign_with_channel(
    workspace_id: uuid.UUID,
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> tuple[Campaign, CampaignChannel]:
    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Campaign",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(channel)
    campaign.status = status
    campaign.clear_events()
    return campaign, channel


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddCampaignStage:
    @pytest.mark.asyncio
    async def test_happy_path_appends_stage_with_criteria(self) -> None:
        auth = fake_auth()
        campaign, channel = _make_draft_campaign_with_channel(auth.workspace_id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        cmd = AddCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="Primary Hit",
            criteria=[StageCriterion(channel_id=channel.id, operator="lt", value=10.0)],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()
        assert len(campaign_out.stages) == 1
        stage = campaign_out.stages[0]
        assert stage.name == "Primary Hit"
        assert stage.display_order == 0
        assert stage.parent_stage_id is None
        assert len(stage.criteria) == 1
        assert stage.criteria[0].channel_id == channel.id
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_stage_gets_next_display_order(self) -> None:
        auth = fake_auth()
        campaign, _channel = _make_draft_campaign_with_channel(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        first = await uc(
            AddCampaignStageCommand(
                workspace_id=auth.workspace_id, campaign_id=campaign.id, name="First"
            ),
            auth=auth,
        )
        assert isinstance(first, Success)

        second = await uc(
            AddCampaignStageCommand(
                workspace_id=auth.workspace_id, campaign_id=campaign.id, name="Second"
            ),
            auth=auth,
        )
        assert isinstance(second, Success)
        campaign_out = second.unwrap()
        orders = sorted(s.display_order for s in campaign_out.stages)
        assert orders == [0, 1]

    @pytest.mark.asyncio
    async def test_unknown_channel_in_criteria_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, _channel = _make_draft_campaign_with_channel(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = AddCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="Bad Stage",
            criteria=[StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=10.0)],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)
        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = AddCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=uuid.uuid4(), name="Ghost"
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_returns_data_locked_error(self) -> None:
        auth = fake_auth()
        campaign, _channel = _make_draft_campaign_with_channel(
            auth.workspace_id, status=CampaignStatus.CLOSED
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = AddCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, name="Attempt"
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), DataLockedError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_error(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, _channel = _make_draft_campaign_with_channel(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = AddCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, name="Blocked"
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        repo.save.assert_not_awaited()
