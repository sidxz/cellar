"""Unit tests for UpdateCampaignChannel use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.update_campaign_channel import (
    UpdateCampaignChannel,
    UpdateCampaignChannelCommand,
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


def _make_campaign_with_channel(
    workspace_id: uuid.UUID,
    *,
    selection_rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
    qc_filter: dict | None = None,
    add_measurement: bool = True,
    manual_override: bool = False,
) -> tuple[Campaign, CampaignChannel, CampaignResult]:
    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=selection_rule,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter=qc_filter,
    )
    campaign.add_channel(channel)
    mol_id = uuid.uuid4()
    result = CampaignResult(campaign_id=campaign.id, molecule_id=mol_id)
    if add_measurement:
        result.add_measurement(
            _make_measurement(result.id, channel.id, is_manual_override=manual_override)
        )
    campaign.add_result(result)
    return campaign, channel, result


def _new_measurement(channel, result_id, molecule_id) -> CampaignMeasurement:
    """Factory used by _FakeResolver to return a distinguishable fresh measurement."""
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=99.0,  # distinguishable from original 10.0
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateCampaignChannel:
    @pytest.mark.asyncio
    async def test_label_only_update_does_not_trigger_resolver(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(auth.workspace_id)
        resolver = FakeResolver(factory=_new_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            label="New Label",
            # selection_rule, qc_filter stay UNSET
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Success)
        campaign_out = result_out.unwrap()
        assert campaign_out.channels[0].label == "New Label"
        # Resolver must NOT have been called — no gating field changed
        assert resolver.calls == []
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_display_order_update_moves_the_channel(self) -> None:
        auth = fake_auth()
        campaign, channel, _result = _make_campaign_with_channel(auth.workspace_id)
        resolver = FakeResolver(factory=_new_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            display_order=3,
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Success)
        assert result_out.unwrap().channels[0].display_order == 3
        # display_order is not a gating field — no re-resolution.
        assert resolver.calls == []

    @pytest.mark.asyncio
    async def test_negative_display_order_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, channel, _result = _make_campaign_with_channel(auth.workspace_id)

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            display_order=-1,
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Failure)
        assert isinstance(result_out.failure(), ValidationError)
        assert channel.display_order == 0  # unchanged

    @pytest.mark.asyncio
    async def test_omitted_display_order_is_left_alone(self) -> None:
        auth = fake_auth()
        campaign, channel, _result = _make_campaign_with_channel(auth.workspace_id)
        channel.display_order = 7
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=dispatcher,
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            label="New Label",
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Success)
        assert result_out.unwrap().channels[0].display_order == 7

    @pytest.mark.asyncio
    async def test_selection_rule_change_reruns_non_override_measurements(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(
            auth.workspace_id,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        )
        # Original measurement value is 10.0 (from _make_measurement)
        assert result.measurements[0].value == 10.0

        resolver = FakeResolver(factory=_new_measurement)  # will return value=99.0
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,  # changed
        )
        result_out = await uc(cmd, auth=auth)

        assert isinstance(result_out, Success)
        # Resolver was called once (one result)
        assert len(resolver.calls) == 1
        # Measurement replaced — value is now 99.0 (from resolver factory)
        assert campaign.results[0].measurements[0].value == 99.0

    @pytest.mark.asyncio
    async def test_selection_rule_change_preserves_manual_override_measurements(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(
            auth.workspace_id,
            manual_override=True,  # measurement flagged as manual override
        )
        original_value = result.measurements[0].value  # 10.0

        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        )
        await uc(cmd, auth=auth)

        # Resolver must NOT have been called for the manual-override measurement
        assert resolver.calls == []
        # Original value preserved
        assert campaign.results[0].measurements[0].value == original_value

    @pytest.mark.asyncio
    async def test_qc_filter_cleared_to_none_triggers_re_resolution(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(
            auth.workspace_id,
            qc_filter={"require_approved": True},  # starts non-None
        )
        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            qc_filter=None,  # explicitly clearing it
        )
        await uc(cmd, auth=auth)

        assert len(resolver.calls) == 1
        assert campaign.channels[0].qc_filter is None

    @pytest.mark.asyncio
    async def test_campaign_not_in_draft_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, channel, _ = _make_campaign_with_channel(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            label="New Label",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_channel_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _, _ = _make_campaign_with_channel(auth.workspace_id)

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=uuid.uuid4(),  # unknown channel
            label="X",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, channel, _ = _make_campaign_with_channel(auth.workspace_id)

        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=FakeResolver(factory=_new_measurement),
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            label="X",
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)

    @pytest.mark.asyncio
    async def test_re_resolve_preserves_measurement_id(self) -> None:
        """Re-resolved measurement inherits the old measurement's id to avoid DELETE+INSERT."""
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(
            auth.workspace_id,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        )
        original_m = result.find_measurement(channel.id)
        assert original_m is not None
        original_id = original_m.id

        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,  # triggers re-resolve
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        rebuilt = result.find_measurement(channel.id)
        assert rebuilt is not None
        assert rebuilt.value == 99.0  # genuinely replaced
        assert rebuilt.id == original_id  # id preserved for UPDATE semantics

    @pytest.mark.asyncio
    async def test_gating_re_resolve_is_scoped_to_the_campaigns_source_runs(self) -> None:
        """Spec D4 — a gating PATCH re-resolves within the campaign's runs."""
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(auth.workspace_id)
        run_id = uuid.uuid4()
        campaign.record_seed_runs([SeedRun(run_id, channel.protocol_id)])

        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        )
        assert isinstance(await uc(cmd, auth=auth), Success)
        assert resolver.run_ids_seen == [[run_id]]

    @pytest.mark.asyncio
    async def test_setting_resolve_from_all_runs_re_resolves_unrestricted(self) -> None:
        """Flipping the opt-out is itself gating: every cell of the channel is
        recomputed, now sweeping every run of the protocol."""
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(auth.workspace_id)
        campaign.record_seed_runs([SeedRun(uuid.uuid4(), channel.protocol_id)])

        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            resolve_from_all_runs=True,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert channel.resolve_from_all_runs is True
        assert resolver.run_ids_seen == [None]
        assert result.find_measurement(channel.id).value == 99.0

    @pytest.mark.asyncio
    async def test_resolve_from_all_runs_unchanged_does_not_re_resolve(self) -> None:
        auth = fake_auth()
        campaign, channel, result = _make_campaign_with_channel(auth.workspace_id)
        resolver = FakeResolver(factory=_new_measurement)
        uc = UpdateCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = UpdateCampaignChannelCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            channel_id=channel.id,
            resolve_from_all_runs=False,
        )
        assert isinstance(await uc(cmd, auth=auth), Success)
        assert resolver.calls == []
