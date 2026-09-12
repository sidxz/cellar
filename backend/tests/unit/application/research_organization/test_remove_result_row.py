"""Unit tests for RemoveResultRow use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.remove_result_row import (
    RemoveResultRow,
    RemoveResultRowCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRemoveResultRow:
    @pytest.mark.asyncio
    async def test_happy_path_removes_result_from_campaign(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)
        assert len(campaign.results) == 1

        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
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
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[uuid.uuid4()],  # unknown
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_ids=[uuid.uuid4()],
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.results.append(result)  # bypass guard to set up result
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo(find_in_ws=None)

        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_ids=[uuid.uuid4()],
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        campaign_repo.save.assert_not_awaited()


class TestBulkRemoveResultRows:
    @pytest.mark.asyncio
    async def test_two_ids_removed_in_one_save(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        keep = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        drop_a = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        drop_b = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        for r in (keep, drop_a, drop_b):
            campaign.add_result(r)

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[drop_a.id, drop_b.id],
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert [r.id for r in out.unwrap().results] == [keep.id]
        # One aggregate save == one optimistic-concurrency version bump.
        campaign_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_unknown_id_removes_nothing(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        first = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        second = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(first)
        campaign.add_result(second)

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[first.id, uuid.uuid4()],
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        assert len(campaign.results) == 2
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_result_ids_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = RemoveResultRow(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = RemoveResultRowCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[],
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        # Rejected before anything is loaded or written.
        campaign_repo.find_by_id_in_workspace.assert_not_awaited()
        campaign_repo.save.assert_not_awaited()
