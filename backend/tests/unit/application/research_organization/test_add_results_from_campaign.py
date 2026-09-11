"""Unit tests for AddResultsFromCampaign use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_results_from_campaign import (
    AddResultsFromCampaign,
    AddResultsFromCampaignCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import (
    CampaignStage,
    StageCriterion,
)
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import CampaignRef
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeResolver,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


def _make_channel(campaign: Campaign) -> CampaignChannel:
    ch = CampaignChannel(
        campaign_id=campaign.id,
        label="Potency",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(ch)
    return ch


def _make_campaign(auth) -> Campaign:
    return Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="Target Campaign",
        description=None,
        created_by=auth.user_id,
    )


def _make_source_campaign(auth, values: list[float]) -> tuple[Campaign, CampaignStage]:
    """Source campaign with one channel and one stage (``>= 50`` on it).

    One CampaignResult per entry in ``values``, each carrying a measurement
    on that channel — so a value of 60 is a hit at the stage and 10 a miss.
    """
    source = Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="Source Campaign",
        description=None,
        created_by=auth.user_id,
    )
    channel = _make_channel(source)
    stage = CampaignStage(
        campaign_id=source.id,
        name="Confirmed",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel.id, operator="gte", value=50.0)],
    )
    source.add_stage(stage)
    for v in values:
        r = CampaignResult(campaign_id=source.id, molecule_id=uuid.uuid4())
        source.add_result(r)
        r.add_measurement(
            CampaignMeasurement(
                result_id=r.id,
                channel_id=channel.id,
                value=v,
                value_qualifier=ValueQualifier.EQ,
                unit="nM",
                protocol_name_snapshot="proto",
                protocol_version_snapshot=1,
            )
        )
    return source, stage


def _fake_measurement(channel, result_id, molecule_id) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="-",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )


def _make_uc(campaign_repo) -> AddResultsFromCampaign:
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    return AddResultsFromCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        resolver=FakeResolver(_fake_measurement),
        dispatcher=dispatcher,
    )


class TestAddResultsFromCampaign:
    @pytest.mark.asyncio
    async def test_no_stage_filter_adds_every_source_result(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source, _stage = _make_source_campaign(auth, [60.0, 10.0])
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 2
        assert outcome.skipped == 0
        for r in outcome.campaign.results:
            assert isinstance(r.added_from, CampaignRef)
            assert r.added_from.campaign_id == source.id
            assert r.added_from.stage_id is None

    @pytest.mark.asyncio
    async def test_stage_filter_adds_only_hits_at_that_stage(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source, stage = _make_source_campaign(auth, [60.0, 10.0])
        hit_molecule_id = source.results[0].molecule_id
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            stage_id=stage.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 1
        assert [r.molecule_id for r in outcome.campaign.results] == [hit_molecule_id]
        added_from = outcome.campaign.results[0].added_from
        assert isinstance(added_from, CampaignRef)
        assert added_from.to_dict()["stage_id"] == str(stage.id)

    @pytest.mark.asyncio
    async def test_stage_from_another_campaign_is_rejected(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source, _stage = _make_source_campaign(auth, [60.0, 10.0])
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            stage_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        assert "does not belong to source campaign" in str(result.failure())

    @pytest.mark.asyncio
    async def test_accepts_any_source_status_including_draft(self) -> None:
        """AddResultsFromCampaign works with source campaigns in DRAFT status."""
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source, _stage = _make_source_campaign(auth, [60.0, 10.0, 70.0])
        assert source.status == CampaignStatus.DRAFT
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap().added == 3

    @pytest.mark.asyncio
    async def test_idempotent_reskip_existing(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source, _stage = _make_source_campaign(auth, [60.0, 70.0, 80.0])
        # Pre-seed 2 of 3 molecules into the target campaign
        for r in source.results[:2]:
            campaign.results.append(
                CampaignResult(campaign_id=campaign.id, molecule_id=r.molecule_id)
            )
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 1
        assert outcome.skipped == 2

    @pytest.mark.asyncio
    async def test_source_campaign_not_found(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_target_campaign_rejects_add(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        _make_channel(campaign)
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4()))
        campaign.close(closed_by=auth.user_id, note=None, source_protocols=[])

        source, _stage = _make_source_campaign(auth, [60.0])
        uc = _make_uc(make_campaign_repo(find_dispatch={campaign.id: campaign, source.id: source}))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_returns_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_campaign(auth)
        uc = _make_uc(make_campaign_repo(find_in_ws=campaign))
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=uuid.uuid4(),
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
