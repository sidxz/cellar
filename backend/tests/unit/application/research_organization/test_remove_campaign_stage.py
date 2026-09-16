"""Unit tests for RemoveCampaignStage use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.remove_campaign_stage import (
    RemoveCampaignStage,
    RemoveCampaignStageCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DataLockedError,
    NotFoundError,
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
    with_child: bool = False,
) -> tuple[Campaign, CampaignStage]:
    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Campaign",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    stage = CampaignStage(campaign_id=campaign.id, name="Primary Hit", display_order=0)
    campaign.add_stage(stage)
    if with_child:
        child = CampaignStage(
            campaign_id=campaign.id,
            name="Child Stage",
            display_order=1,
            parent_stage_id=stage.id,
        )
        campaign.add_stage(child)
    campaign.status = status
    campaign.clear_events()
    return campaign, stage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRemoveCampaignStage:
    @pytest.mark.asyncio
    async def test_happy_path_removes_stage(self) -> None:
        auth = fake_auth()
        campaign, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, stage_id=stage.id
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        assert len(result.unwrap().stages) == 0
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_conflict_when_child_stages_exist(self) -> None:
        auth = fake_auth()
        campaign, stage = _make_draft_campaign_with_stage(auth.workspace_id, with_child=True)
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, stage_id=stage.id
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.save.assert_not_awaited()
        assert len(campaign.stages) == 2  # nothing removed

    @pytest.mark.asyncio
    async def test_unknown_stage_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _stage = _make_draft_campaign_with_stage(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, stage_id=uuid.uuid4()
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)
        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=uuid.uuid4(), stage_id=uuid.uuid4()
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_returns_data_locked_error(self) -> None:
        auth = fake_auth()
        campaign, stage = _make_draft_campaign_with_stage(
            auth.workspace_id, status=CampaignStatus.CLOSED
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, stage_id=stage.id
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), DataLockedError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_error(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, stage = _make_draft_campaign_with_stage(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveCampaignStage(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = RemoveCampaignStageCommand(
            workspace_id=auth.workspace_id, campaign_id=campaign.id, stage_id=stage.id
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        repo.save.assert_not_awaited()
