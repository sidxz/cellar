"""Unit tests for CreateCampaign use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.create_campaign import (
    CreateCampaign,
    CreateCampaignCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.shared.errors import AuthorizationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


class TestCreateCampaign:
    @pytest.mark.asyncio
    async def test_create_campaign_creates_empty_draft(self) -> None:
        """CreateCampaign creates an empty campaign — no compound source required."""
        auth = fake_auth()

        campaign_repo = make_campaign_repo()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="EGFR Round 2",
            description="kick-off",
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign = result.unwrap()
        assert isinstance(campaign, Campaign)
        assert campaign.name == "EGFR Round 2"
        assert campaign.results == []
        assert campaign.channels == []
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_campaign_rejects_when_unauthorized(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo()
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="blocked",
            description=None,
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
