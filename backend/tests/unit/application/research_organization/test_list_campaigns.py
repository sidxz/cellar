"""Unit tests for the ListCampaigns query — filter forwarding to the repo."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.research_organization.list_campaigns import (
    ListCampaigns,
    ListCampaignsQuery,
)
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.shared.errors import AuthorizationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
)


def _make_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_project = AsyncMock(return_value=[])
    repo.find_by_workspace = AsyncMock(return_value=[])
    repo.project_targets = AsyncMock(return_value={})
    return repo


class TestListCampaignsStatusFilter:
    @pytest.mark.asyncio
    async def test_status_forwarded_to_find_by_workspace(self) -> None:
        auth = fake_auth(role="viewer")
        repo = _make_repo()
        uc = ListCampaigns(uow=FakeUnitOfWork(), campaign_repo=repo)

        out = await uc(
            ListCampaignsQuery(workspace_id=auth.workspace_id, status=CampaignStatus.CLOSED),
            auth=auth,
        )

        assert isinstance(out, Success)
        assert repo.find_by_workspace.await_args.kwargs["status"] is CampaignStatus.CLOSED
        repo.find_by_project.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_forwarded_to_find_by_project(self) -> None:
        auth = fake_auth()
        repo = _make_repo()
        project_id = uuid.uuid4()
        uc = ListCampaigns(uow=FakeUnitOfWork(), campaign_repo=repo)

        await uc(
            ListCampaignsQuery(
                workspace_id=auth.workspace_id,
                project_id=project_id,
                status=CampaignStatus.DRAFT,
            ),
            auth=auth,
        )

        assert repo.find_by_project.await_args.kwargs["status"] is CampaignStatus.DRAFT

    @pytest.mark.asyncio
    async def test_status_defaults_to_none(self) -> None:
        auth = fake_auth()
        repo = _make_repo()
        uc = ListCampaigns(uow=FakeUnitOfWork(), campaign_repo=repo)

        await uc(ListCampaignsQuery(workspace_id=auth.workspace_id), auth=auth)

        assert repo.find_by_workspace.await_args.kwargs["status"] is None

    @pytest.mark.asyncio
    async def test_no_workspace_role_is_rejected(self) -> None:
        auth = fake_auth(role="viewer")
        auth.has_role = lambda _minimum_role: False
        uc = ListCampaigns(uow=FakeUnitOfWork(), campaign_repo=_make_repo())

        with pytest.raises(AuthorizationError):
            await uc(ListCampaignsQuery(workspace_id=auth.workspace_id), auth=auth)
