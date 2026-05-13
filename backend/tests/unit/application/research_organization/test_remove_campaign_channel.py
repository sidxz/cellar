"""Unit tests for RemoveCampaignChannel use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.remove_campaign_channel import (
    RemoveCampaignChannel,
    RemoveCampaignChannelCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
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


def _make_campaign_with_channel_and_result(
    workspace_id: uuid.UUID,
) -> tuple[Campaign, CampaignChannel, CampaignResult]:
    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Campaign",
        description=None,
        publishes_collection=True,
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

    result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    measurement = CampaignMeasurement(
        result_id=result.id,
        channel_id=channel.id,
        value=5.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )
    result.add_measurement(measurement)
    campaign.add_result(result)
    return campaign, channel, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRemoveCampaignChannel:
    @pytest.mark.asyncio
    async def test_happy_path_channel_and_measurements_removed(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel_and_result(
            auth.workspace_id
        )
        assert len(campaign.channels) == 1
        assert len(result.measurements) == 1

        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = RemoveCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=dispatcher,
        )
        cmd = RemoveCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Success)
        campaign_out = result_out.unwrap()
        # Channel gone
        assert len(campaign_out.channels) == 0
        # Measurements for the channel gone from the result
        assert not any(
            m.channel_id == channel.id
            for r in campaign_out.results
            for m in r.measurements
        )
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        uc = RemoveCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            dispatcher=AsyncMock(),
        )
        cmd = RemoveCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_channel_not_found_on_campaign_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _, _ = _make_campaign_with_channel_and_result(auth.workspace_id)

        uc = RemoveCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = RemoveCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=uuid.uuid4(),  # unknown channel
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)
        assert "CampaignChannel" in str(err)

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, channel, _ = _make_campaign_with_channel_and_result(
            auth.workspace_id
        )

        uc = RemoveCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = RemoveCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
