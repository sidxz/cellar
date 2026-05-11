"""Unit tests for RefreshFromSources use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSources,
    RefreshFromSourcesCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import ExplicitListSource
from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.shared.errors import (
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


def _make_channel(campaign_id: uuid.UUID, *, display_order: int = 0) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign_id,
        label=f"Channel-{display_order}",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=display_order,
    )


def _make_measurement(
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    value: float = 10.0,
    is_manual_override: bool = False,
) -> CampaignMeasurement:
    m = CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=value,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )
    if is_manual_override:
        m.mark_manual_override()
    return m


def _new_measurement(channel, result_id, molecule_id) -> CampaignMeasurement:
    """Factory used by FakeResolver to return a distinguishable fresh measurement."""
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=99.0,  # distinguishable from original 10.0
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )


def _build_pre_populated_campaign(
    workspace_id: uuid.UUID,
    n_channels: int = 1,
    n_results: int = 1,
    override_indices: set[tuple[int, int]] | None = None,
) -> tuple[Campaign, list[CampaignChannel], list[CampaignResult]]:
    """Build a DRAFT campaign with channels and results.

    Each result gets a CampaignMeasurement per channel (value=10.0).
    ``override_indices`` is a set of (result_index, channel_index) pairs whose
    measurements should have ``is_manual_override=True``.
    """
    if override_indices is None:
        override_indices = set()

    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )

    channels: list[CampaignChannel] = []
    for ci in range(n_channels):
        ch = _make_channel(campaign.id, display_order=ci)
        campaign.add_channel(ch)
        channels.append(ch)

    results: list[CampaignResult] = []
    for ri in range(n_results):
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        for ci, ch in enumerate(channels):
            is_override = (ri, ci) in override_indices
            m = _make_measurement(result.id, ch.id, is_manual_override=is_override)
            result.add_measurement(m)
        campaign.add_result(result)
        results.append(result)

    return campaign, channels, results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefreshFromSources:
    @pytest.mark.asyncio
    async def test_happy_path_multi_channel_multi_result_skips_overrides(self) -> None:
        """Re-resolves non-override cells; leaves override cells byte-for-byte intact."""
        auth = fake_auth()
        # (result=0,channel=1) and (result=2,channel=0) are overrides
        override_indices = {(0, 1), (2, 0)}
        campaign, channels, results = _build_pre_populated_campaign(
            auth.workspace_id,
            n_channels=2,
            n_results=3,
            override_indices=override_indices,
        )

        # Capture identities and values of override measurements before refresh
        override_measurements_before = {}
        for ri, ci in override_indices:
            m = results[ri].find_measurement(channels[ci].id)
            assert m is not None
            override_measurements_before[(ri, ci)] = (id(m), m.value, m.is_manual_override)

        resolver = FakeResolver(factory=_new_measurement)  # returns value=99.0
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        # Total cells = 3 results × 2 channels = 6; 2 are overrides → resolver called 4 times
        assert len(resolver.calls) == 4

        # All non-override cells now have value=99.0
        for ri, result in enumerate(results):
            for ci, ch in enumerate(channels):
                m = result.find_measurement(ch.id)
                assert m is not None
                if (ri, ci) in override_indices:
                    assert m.value == 10.0
                    assert m.is_manual_override is True
                else:
                    assert m.value == 99.0

        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_cells_are_manual_overrides_resolver_not_called(self) -> None:
        """When every cell is an override, resolver is skipped but campaign is still saved."""
        auth = fake_auth()
        n_channels, n_results = 2, 2
        override_indices = {(ri, ci) for ri in range(n_results) for ci in range(n_channels)}
        campaign, channels, results = _build_pre_populated_campaign(
            auth.workspace_id,
            n_channels=n_channels,
            n_results=n_results,
            override_indices=override_indices,
        )

        resolver = FakeResolver(factory=_new_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert resolver.calls == []
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_measurement_is_filled(self) -> None:
        """A (result, channel) cell with no measurement gets resolved and added."""
        auth = fake_auth()
        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="C",
            description=None,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=True,
            created_by=uuid.uuid4(),
        )
        ch = _make_channel(campaign.id)
        campaign.add_channel(ch)

        # Result with NO measurement for this channel
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)
        assert result.find_measurement(ch.id) is None

        resolver = FakeResolver(factory=_new_measurement)
        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert len(resolver.calls) == 1
        m = campaign.results[0].find_measurement(ch.id)
        assert m is not None
        assert m.value == 99.0

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        resolver = FakeResolver(factory=_new_measurement)
        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()
        assert resolver.calls == []

    @pytest.mark.asyncio
    async def test_campaign_not_draft_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, _, _ = _build_pre_populated_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        resolver = FakeResolver(factory=_new_measurement)
        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)

    @pytest.mark.asyncio
    async def test_zero_channels_no_resolver_calls_campaign_still_saved(self) -> None:
        """Campaign with no channels: resolver never called, campaign saved and dispatched."""
        auth = fake_auth()
        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Empty",
            description=None,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=True,
            created_by=uuid.uuid4(),
        )
        # Add a result but no channels
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)

        resolver = FakeResolver(factory=_new_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RefreshFromSources(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = RefreshFromSourcesCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert resolver.calls == []
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()
