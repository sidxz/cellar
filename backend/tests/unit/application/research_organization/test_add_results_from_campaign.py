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
from cellar.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    CampaignDecision,
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


def _make_campaign(auth) -> Campaign:
    return Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="Target Campaign",
        description=None,
        publishes_collection=True,
        created_by=auth.user_id,
    )


def _make_source_campaign(auth, decisions: list[CampaignDecision]) -> Campaign:
    source = Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="Source Campaign",
        description=None,
        publishes_collection=False,
        created_by=auth.user_id,
    )
    for d in decisions:
        r = CampaignResult(campaign_id=source.id, molecule_id=uuid.uuid4())
        r.set_decision(d)
        source.results.append(r)
    return source


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


class TestAddResultsFromCampaign:
    @pytest.mark.asyncio
    async def test_happy_path_adds_filtered_molecules(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        # Source has 3 selected + 1 deferred + 1 rejected
        source = _make_source_campaign(
            auth,
            [
                CampaignDecision.SELECTED,
                CampaignDecision.SELECTED,
                CampaignDecision.SELECTED,
                CampaignDecision.DEFERRED,
                CampaignDecision.REJECTED,
            ],
        )
        campaign_repo = make_campaign_repo(
            find_dispatch={campaign.id: campaign, source.id: source}
        )
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            decision_filter=[CampaignDecision.SELECTED],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 3
        assert outcome.skipped == 0
        # All results attributed with CampaignRef pointing to source
        for r in outcome.campaign.results:
            assert isinstance(r.added_from, CampaignRef)
            assert r.added_from.campaign_id == source.id

    @pytest.mark.asyncio
    async def test_accepts_any_source_status_including_draft(self) -> None:
        """AddResultsFromCampaign works with source campaigns in DRAFT status."""
        auth = fake_auth()
        campaign = _make_campaign(auth)
        # Source is a DRAFT campaign (status not checked)
        source = _make_source_campaign(auth, [CampaignDecision.DEFERRED] * 3)
        assert source.status == CampaignStatus.DRAFT

        campaign_repo = make_campaign_repo(
            find_dispatch={campaign.id: campaign, source.id: source}
        )
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            decision_filter=[CampaignDecision.DEFERRED],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap().added == 3

    @pytest.mark.asyncio
    async def test_idempotent_reskip_existing(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        source = _make_source_campaign(
            auth,
            [CampaignDecision.SELECTED, CampaignDecision.SELECTED, CampaignDecision.SELECTED],
        )
        # Pre-seed 2 of 3 molecules into the target campaign
        pre_a = source.results[0].molecule_id
        pre_b = source.results[1].molecule_id
        campaign.results.append(CampaignResult(campaign_id=campaign.id, molecule_id=pre_a))
        campaign.results.append(CampaignResult(campaign_id=campaign.id, molecule_id=pre_b))

        campaign_repo = make_campaign_repo(
            find_dispatch={campaign.id: campaign, source.id: source}
        )
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            decision_filter=[CampaignDecision.SELECTED],
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
        campaign_repo = make_campaign_repo(
            find_dispatch={campaign.id: campaign}  # source not in map → None
        )
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=uuid.uuid4(),
            decision_filter=[CampaignDecision.SELECTED],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_target_campaign_rejects_add(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        ch = CampaignChannel(
            campaign_id=campaign.id, label="x",
            protocol_id=uuid.uuid4(), readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )
        campaign.add_channel(ch)
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4()))
        campaign.close(closed_by=auth.user_id, signature_id=uuid.uuid4(), source_protocols=[])

        source = _make_source_campaign(auth, [CampaignDecision.SELECTED])
        campaign_repo = make_campaign_repo(
            find_dispatch={campaign.id: campaign, source.id: source}
        )
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=source.id,
            decision_filter=[CampaignDecision.SELECTED],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_returns_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_campaign(auth)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            source_campaign_id=uuid.uuid4(),
            decision_filter=[CampaignDecision.SELECTED],
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
