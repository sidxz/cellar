"""Unit tests for AddResultRow use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_result_row import (
    AddResultRow,
    AddResultRowCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import ManualRef
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    FakeResolver,
    fake_auth,
    make_campaign_repo,
)


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )


def _make_channel(campaign_id: uuid.UUID) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign_id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )


def _add_result_measurement_factory(channel, result_id, molecule_id) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=10.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddResultRow:
    @pytest.mark.asyncio
    async def test_happy_path_one_channel_adds_result_with_one_measurement(
        self,
    ) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        channel = _make_channel(campaign.id)
        campaign.add_channel(channel)

        resolver = FakeResolver(factory=_add_result_measurement_factory)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        new_mol_id = uuid.uuid4()
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=new_mol_id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        campaign_out = out.unwrap()
        assert len(campaign_out.results) == 1
        assert campaign_out.results[0].molecule_id == new_mol_id
        assert len(campaign_out.results[0].measurements) == 1
        assert len(resolver.calls) == 1
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_happy_path_two_channels_calls_resolver_twice(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        ch1 = _make_channel(campaign.id)
        ch2 = _make_channel(campaign.id)
        campaign.add_channel(ch1)
        campaign.add_channel(ch2)

        resolver = FakeResolver(factory=_add_result_measurement_factory)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert len(out.unwrap().results[0].measurements) == 2
        assert len(resolver.calls) == 2

    @pytest.mark.asyncio
    async def test_happy_path_no_channels_adds_result_with_empty_measurements(
        self,
    ) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        # No channels added
        resolver = FakeResolver(factory=_add_result_measurement_factory)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        result = out.unwrap().results[0]
        assert result.measurements == []
        assert resolver.calls == []

    @pytest.mark.asyncio
    async def test_duplicate_molecule_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        mol_id = uuid.uuid4()
        existing = CampaignResult(campaign_id=campaign.id, molecule_id=mol_id)
        campaign.add_result(existing)

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=FakeResolver(factory=_add_result_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=mol_id,  # already present
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=FakeResolver(factory=_add_result_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            molecule_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=FakeResolver(factory=_add_result_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo(find_in_ws=None)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=FakeResolver(factory=_add_result_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            molecule_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()


    @pytest.mark.asyncio
    async def test_added_row_has_manual_ref_attribution(self) -> None:
        """AddResultRow attributes new results as ManualRef."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        mol_id = uuid.uuid4()

        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=FakeResolver(factory=_add_result_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            molecule_id=mol_id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        result = out.unwrap().results[0]
        assert isinstance(result.added_from, ManualRef)
