"""Unit tests for RemoveResultRow use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.remove_result_row import (
    RemoveResultRow,
    RemoveResultRowCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import ExplicitListSource
from chem_vault.domain.research_organization.enums import CampaignStatus
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


def _make_campaign_repo(campaign: Campaign | None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=campaign)
    repo.save = AsyncMock()
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRemoveResultRow:
    @pytest.mark.asyncio
    async def test_happy_path_removes_result_from_campaign(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)
        assert len(campaign.results) == 1

        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = _make_campaign_repo(campaign)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        campaign_out = out.unwrap()
        assert len(campaign_out.results) == 0
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_result_not_found_returns_not_found_failure_and_no_save(
        self,
    ) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = _make_campaign_repo(campaign)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=uuid.uuid4(),  # unknown
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = _fake_auth()
        campaign_repo = _make_campaign_repo(None)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_draft_campaign_returns_validation_failure(self) -> None:
        auth = _fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.results.append(result)  # bypass guard to set up result
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = _make_campaign_repo(campaign)
        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = _fake_auth(role="viewer")
        campaign_repo = _make_campaign_repo(None)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
