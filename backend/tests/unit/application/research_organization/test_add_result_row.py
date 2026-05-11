"""Unit tests for AddResultRow use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.add_result_row import (
    AddResultRow,
    AddResultRowCommand,
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


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
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


def _make_campaign_repo(campaign: Campaign | None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=campaign)
    repo.save = AsyncMock()
    return repo


class _FakeResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []

    async def resolve(self, *, workspace_id, channel, result_id, molecule_id):
        self.calls.append((channel.id, result_id, molecule_id))
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
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        channel = _make_channel(campaign.id)
        campaign.add_channel(channel)

        resolver = _FakeResolver()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = _make_campaign_repo(campaign)

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
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        ch1 = _make_channel(campaign.id)
        ch2 = _make_channel(campaign.id)
        campaign.add_channel(ch1)
        campaign.add_channel(ch2)

        resolver = _FakeResolver()
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
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
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        # No channels added
        resolver = _FakeResolver()
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=_make_campaign_repo(campaign),
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
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        mol_id = uuid.uuid4()
        existing = CampaignResult(campaign_id=campaign.id, molecule_id=mol_id)
        campaign.add_result(existing)

        campaign_repo = _make_campaign_repo(campaign)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=_FakeResolver(),
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
        auth = _fake_auth()
        campaign_repo = _make_campaign_repo(None)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=_FakeResolver(),
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
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = _make_campaign_repo(campaign)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=_FakeResolver(),
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
        auth = _fake_auth(role="viewer")
        campaign_repo = _make_campaign_repo(None)
        uc = AddResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            resolver=_FakeResolver(),
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
