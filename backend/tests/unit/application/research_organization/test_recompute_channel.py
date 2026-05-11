"""Unit tests for RecomputeChannel use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.recompute_channel import (
    RecomputeChannel,
    RecomputeChannelCommand,
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


def _build_campaign_two_channels_three_results(
    workspace_id: uuid.UUID,
    override_indices: set[tuple[int, int]] | None = None,
) -> tuple[Campaign, CampaignChannel, CampaignChannel, list[CampaignResult]]:
    """Build a DRAFT campaign with 2 channels and 3 results.

    ``override_indices`` is a set of (result_index, channel_index) whose
    measurements should be marked as manual overrides.
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

    ch_a = _make_channel(campaign.id, display_order=0)
    ch_b = _make_channel(campaign.id, display_order=1)
    campaign.add_channel(ch_a)
    campaign.add_channel(ch_b)
    channels = [ch_a, ch_b]

    results: list[CampaignResult] = []
    for ri in range(3):
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        for ci, ch in enumerate(channels):
            is_override = (ri, ci) in override_indices
            m = _make_measurement(result.id, ch.id, is_manual_override=is_override)
            result.add_measurement(m)
        campaign.add_result(result)
        results.append(result)

    return campaign, ch_a, ch_b, results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecomputeChannel:
    @pytest.mark.asyncio
    async def test_happy_path_only_target_channel_re_resolved(self) -> None:
        """RecomputeChannel re-resolves only channel A × 3 results; channel B untouched."""
        auth = fake_auth()
        campaign, ch_a, ch_b, results = _build_campaign_two_channels_three_results(
            auth.workspace_id
        )

        resolver = FakeResolver(factory=_new_measurement)  # returns value=99.0
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=ch_a.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        # Resolver called exactly 3 times — one per result, only for channel A
        assert len(resolver.calls) == 3
        assert all(call[0] == ch_a.id for call in resolver.calls)

        # Channel A measurements replaced with 99.0
        for result in results:
            m_a = result.find_measurement(ch_a.id)
            assert m_a is not None
            assert m_a.value == 99.0

        # Channel B measurements still at 10.0
        for result in results:
            m_b = result.find_measurement(ch_b.id)
            assert m_b is not None
            assert m_b.value == 10.0

        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_override_preservation_for_targeted_channel(self) -> None:
        """Manual override on the targeted channel is preserved; others are re-resolved."""
        auth = fake_auth()
        # result=1, channel=0 (ch_a) is a manual override
        override_indices = {(1, 0)}
        campaign, ch_a, ch_b, results = _build_campaign_two_channels_three_results(
            auth.workspace_id, override_indices=override_indices
        )

        resolver = FakeResolver(factory=_new_measurement)
        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=ch_a.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        # Resolver called 2 times (3 results − 1 override)
        assert len(resolver.calls) == 2
        assert all(call[0] == ch_a.id for call in resolver.calls)

        # Override measurement for result[1] is unchanged
        m_override = results[1].find_measurement(ch_a.id)
        assert m_override is not None
        assert m_override.value == 10.0
        assert m_override.is_manual_override is True

        # Other ch_a measurements are re-resolved to 99.0
        for ri in [0, 2]:
            m = results[ri].find_measurement(ch_a.id)
            assert m is not None
            assert m.value == 99.0

    @pytest.mark.asyncio
    async def test_channel_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, ch_a, ch_b, _ = _build_campaign_two_channels_three_results(
            auth.workspace_id
        )
        resolver = FakeResolver(factory=_new_measurement)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=uuid.uuid4(),  # unknown channel
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        err = out.failure()
        assert isinstance(err, NotFoundError)
        assert "CampaignChannel" in str(err)
        campaign_repo.save.assert_not_awaited()
        assert resolver.calls == []

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        resolver = FakeResolver(factory=_new_measurement)

        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()
        assert resolver.calls == []

    @pytest.mark.asyncio
    async def test_campaign_not_draft_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, ch_a, _, _ = _build_campaign_two_channels_three_results(
            auth.workspace_id
        )
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        resolver = FakeResolver(factory=_new_measurement)
        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=ch_a.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        uc = RecomputeChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = RecomputeChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)
