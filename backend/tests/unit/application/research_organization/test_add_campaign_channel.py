"""Unit tests for AddCampaignChannel use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.add_campaign_channel import (
    AddCampaignChannel,
    AddCampaignChannelCommand,
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
from chem_vault.domain.screening_assay.hit_criterion import HitCriterion
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from chem_vault.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    def __init__(self) -> None:
        self._tracked: list = []

    def track(self, aggregate) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for agg in self._tracked:
            events.extend(agg.collect_events())
            agg.clear_events()
        return events

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def _fake_auth(*, role: str = "editor", is_admin: bool = False):
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = role
    auth.is_admin = is_admin
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    current = rank.get(role, 0)
    auth.has_role = lambda min_role: current >= rank.get(min_role, 0)
    return auth


def _make_draft_campaign(workspace_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> Campaign:
    c = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        publishes_collection=True,
        created_by=user_id or uuid.uuid4(),
    )
    # Seed one result so we can assert measurements are added
    mol_id = uuid.uuid4()
    c.add_result(CampaignResult(campaign_id=c.id, molecule_id=mol_id))
    return c


def _make_campaign_repo(campaign: Campaign | None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=campaign)
    repo.save = AsyncMock()
    return repo


def _make_protocol_repo(
    *,
    protocol=None,
) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    return repo


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


class _FakeResolver:
    def __init__(self, factory=None):
        self._factory = factory or _fake_measurement
        self.calls: list = []

    async def resolve(self, *, workspace_id, channel, result_id, molecule_id):
        self.calls.append((channel.id, result_id, molecule_id))
        return self._factory(channel, result_id, molecule_id)


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
        hit_threshold=HitCriterion(readout_name="IC50", operator="lt", value=10.0),
        display_order=0,
    )
    defaults.update(overrides)
    return AddCampaignChannelCommand(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddCampaignChannel:
    @pytest.mark.asyncio
    async def test_happy_path_explicit_hit_threshold_appends_channel_and_measurements(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        resolver = _FakeResolver()

        cmd = _base_command(auth.workspace_id, campaign.id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=_make_protocol_repo(),
            resolver=resolver,
            dispatcher=dispatcher,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()
        assert len(campaign_out.channels) == 1
        ch = campaign_out.channels[0]
        assert ch.label == "IC50 (uM)"
        assert ch.hit_threshold == cmd.hit_threshold
        # One resolver call per result
        assert len(resolver.calls) == len(campaign_out.results) == 1
        # Measurement added to the result
        assert len(campaign_out.results[0].measurements) == 1
        assert campaign_out.results[0].measurements[0].channel_id == ch.id
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_carry_forward_hit_threshold_uses_matching_criterion(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)

        protocol_id = uuid.uuid4()
        rdid = uuid.uuid4()

        # Build a minimal fake protocol with readout_definitions + recommended_hit_criteria
        protocol = AsyncMock()
        rd = AsyncMock()
        rd.id = rdid
        rd.name = "IC50"
        protocol.readout_definitions = [rd]
        criterion = HitCriterion(readout_name="IC50", operator="lt", value=5.0)
        protocol.recommended_hit_criteria = [criterion]

        protocol_repo = _make_protocol_repo(protocol=protocol)
        resolver = _FakeResolver()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        cmd = _base_command(
            auth.workspace_id,
            campaign.id,
            protocol_id=protocol_id,
            readout_definition_id=rdid,
            hit_threshold=None,  # trigger carry-forward
        )

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=protocol_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        ch = result.unwrap().channels[0]
        assert ch.hit_threshold == criterion

    @pytest.mark.asyncio
    async def test_carry_forward_miss_leaves_hit_threshold_none(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)

        rdid = uuid.uuid4()
        protocol = AsyncMock()
        rd = AsyncMock()
        rd.id = rdid
        rd.name = "IC50"
        protocol.readout_definitions = [rd]
        # Criterion for a different readout name — no match
        protocol.recommended_hit_criteria = [
            HitCriterion(readout_name="EC50", operator="lt", value=10.0)
        ]

        cmd = _base_command(
            auth.workspace_id,
            campaign.id,
            readout_definition_id=rdid,
            hit_threshold=None,
        )

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=_make_protocol_repo(protocol=protocol),
            resolver=_FakeResolver(),
            dispatcher=AsyncMock(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap().channels[0].hit_threshold is None

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = _fake_auth()
        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(None),
            protocol_repo=_make_protocol_repo(),
            resolver=_FakeResolver(),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, uuid.uuid4())
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_protocol_not_found_during_carry_forward_returns_not_found(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=_make_protocol_repo(protocol=None),  # protocol missing
            resolver=_FakeResolver(),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id, hit_threshold=None)
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_in_draft_returns_validation_failure(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        # Close it manually to force non-DRAFT status
        campaign.status = CampaignStatus.CLOSED

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=_make_protocol_repo(),
            resolver=_FakeResolver(),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id)
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = _fake_auth(role="viewer")
        campaign = _make_draft_campaign(auth.workspace_id)

        uc = AddCampaignChannel(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
            protocol_repo=_make_protocol_repo(),
            resolver=_FakeResolver(),
            dispatcher=AsyncMock(),
        )
        cmd = _base_command(auth.workspace_id, campaign.id)
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
