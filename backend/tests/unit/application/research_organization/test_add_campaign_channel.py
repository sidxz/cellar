"""Unit tests for AddCampaignChannel use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_campaign_channel import (
    AddCampaignChannel,
    AddCampaignChannelCommand,
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
from cellar.domain.research_organization.source_ref import SeedRun
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft_campaign(workspace_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> Campaign:
    c = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=user_id or uuid.uuid4(),
    )
    # Seed one result so we can assert measurements are added
    mol_id = uuid.uuid4()
    c.add_result(CampaignResult(campaign_id=c.id, molecule_id=mol_id))
    return c


def _fake_measurement(channel: CampaignChannel, result_id: uuid.UUID, molecule_id: uuid.UUID) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Test Protocol",
        protocol_version_snapshot=1,
    )


def _base_command(workspace_id: uuid.UUID, campaign_id: uuid.UUID, **overrides) -> AddCampaignChannelCommand:
    defaults = dict(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        label="IC50 (uM)",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        qc_filter=None,
        display_order=0,
    )
    defaults.update(overrides)
    return AddCampaignChannelCommand(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddCampaignChannel:
    @pytest.mark.asyncio
    async def test_happy_path_appends_channel_and_measurements(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        resolver = FakeResolver(factory=_fake_measurement)

        cmd = _base_command(auth.workspace_id, campaign.id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=dispatcher,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()
        assert len(campaign_out.channels) == 1
        ch = campaign_out.channels[0]
        assert ch.label == "IC50 (uM)"
        # One resolver call per result
        assert len(resolver.calls) == len(campaign_out.results) == 1
        # Measurement added to the result
        assert len(campaign_out.results[0].measurements) == 1
        assert campaign_out.results[0].measurements[0].channel_id == ch.id
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            resolver=FakeResolver(factory=_fake_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, uuid.uuid4())
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_in_draft_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        # Close it manually to force non-DRAFT status
        campaign.status = CampaignStatus.CLOSED

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_fake_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id)
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_draft_campaign(auth.workspace_id)

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_fake_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id)
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)

    @pytest.mark.asyncio
    async def test_resolution_is_scoped_to_the_campaigns_source_runs(self) -> None:
        """Spec D4 — a run-seeded campaign resolves a new channel against its
        own runs, and only its own runs."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        run_id, protocol_id = uuid.uuid4(), uuid.uuid4()
        campaign.record_seed_runs([SeedRun(run_id, protocol_id)])
        resolver = FakeResolver(factory=_fake_measurement)

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id, protocol_id=protocol_id)
        assert isinstance(await uc(cmd, auth=auth), Success)
        assert resolver.run_ids_seen == [[run_id]]

    @pytest.mark.asyncio
    async def test_channel_on_an_unseeded_protocol_resolves_unrestricted(self) -> None:
        """A counter-screen on a protocol the campaign was never seeded from
        has no seed runs to scope to, so it resolves protocol-wide."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign.record_seed_runs([SeedRun(uuid.uuid4(), uuid.uuid4())])
        resolver = FakeResolver(factory=_fake_measurement)

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id, protocol_id=uuid.uuid4())
        assert isinstance(await uc(cmd, auth=auth), Success)
        assert resolver.run_ids_seen == [None]

    @pytest.mark.asyncio
    async def test_opt_out_channel_resolves_unrestricted(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        protocol_id = uuid.uuid4()
        campaign.record_seed_runs([SeedRun(uuid.uuid4(), protocol_id)])
        resolver = FakeResolver(factory=_fake_measurement)

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(
            auth.workspace_id, campaign.id, protocol_id=protocol_id, resolve_from_all_runs=True
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap().channels[0].resolve_from_all_runs is True
        assert resolver.run_ids_seen == [None]
