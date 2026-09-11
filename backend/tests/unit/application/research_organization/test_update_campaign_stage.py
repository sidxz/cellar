"""Unit tests for UpdateCampaignStage use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.update_campaign_stage import (
    UpdateCampaignStage,
    UpdateCampaignStageCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
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


def _make_draft_campaign_with_stage(
    workspace_id: uuid.UUID,
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> tuple[Campaign, CampaignChannel, CampaignStage]:
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
    stage = CampaignStage(
        campaign_id=campaign.id,
        name="Primary Hit",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel.id, operator="lt", value=10.0)],
    )
    campaign.add_stage(stage)
    campaign.status = status
    campaign.clear_events()
    return campaign, channel, stage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateCampaignStage:
    @pytest.mark.asyncio
    async def test_rename_and_replace_criteria(self) -> None:
        auth = fake_auth()
        campaign, channel, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        new_criteria = [StageCriterion(channel_id=channel.id, operator="lte", value=5.0)]
        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=stage.id,
            name="Renamed Stage",
            criteria=new_criteria,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        updated = result.unwrap().find_stage(stage.id)
        assert updated is not None
        assert updated.name == "Renamed Stage"
        assert len(updated.criteria) == 1
        assert updated.criteria[0].operator == "lte"
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_omitted_fields_left_unchanged(self) -> None:
        auth = fake_auth()
        campaign, _channel, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        original_criteria = stage.criteria
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        # Only display_order supplied — name/parent/criteria default to UNSET
        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=stage.id,
            display_order=3,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        updated = result.unwrap().find_stage(stage.id)
        assert updated is not None
        assert updated.display_order == 3
        assert updated.name == "Primary Hit"
        assert updated.criteria == original_criteria

    @pytest.mark.asyncio
    async def test_null_parent_clears_existing_parent(self) -> None:
        auth = fake_auth()
        campaign, _channel, parent_stage = _make_draft_campaign_with_stage(auth.workspace_id)
        child = CampaignStage(
            campaign_id=campaign.id,
            name="Child Stage",
            display_order=1,
            parent_stage_id=parent_stage.id,
        )
        campaign.add_stage(child)
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=child.id,
            parent_stage_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        updated = result.unwrap().find_stage(child.id)
        assert updated is not None
        assert updated.parent_stage_id is None

    @pytest.mark.asyncio
    async def test_empty_name_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, _channel, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=stage.id,
            name="   ",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_stage_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _channel, _stage = _make_draft_campaign_with_stage(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=uuid.uuid4(),
            name="Whatever",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)
        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            stage_id=uuid.uuid4(),
            name="Ghost",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_returns_data_locked_error(self) -> None:
        auth = fake_auth()
        campaign, _channel, stage = _make_draft_campaign_with_stage(
            auth.workspace_id, status=CampaignStatus.CLOSED
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=stage.id,
            name="Attempt",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), DataLockedError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_error(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, _channel, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = UpdateCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = UpdateCampaignStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            stage_id=stage.id,
            name="Blocked",
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        repo.save.assert_not_awaited()
