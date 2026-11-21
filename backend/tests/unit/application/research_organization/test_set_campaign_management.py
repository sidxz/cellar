"""Marking a campaign as managed by the calling app, and an admin releasing it."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.release_campaign import (
    ReleaseCampaign,
    ReleaseCampaignCommand,
)
from cellar.application.research_organization.set_campaign_management import (
    SetCampaignManagement,
    SetCampaignManagementCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_management import CampaignManagement
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

URL = "http://localhost:3002/screens/S1?round=R1"


def _campaign(workspace_id: uuid.UUID, *, managed_by: str | None = None) -> Campaign:
    c = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Round 1",
        description=None,
        created_by=uuid.uuid4(),
    )
    if managed_by is not None:
        c.set_management(
            CampaignManagement(managed_by=managed_by, url=URL, label=managed_by.title()),
            user_id=None,
        )
    c.clear_events()
    return c


def _set_uc(campaign: Campaign | None) -> tuple[SetCampaignManagement, list[Campaign]]:
    saved: list[Campaign] = []
    uc = SetCampaignManagement(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        dispatcher=AsyncMock(),
    )
    return uc, saved


def _release_uc(campaign: Campaign | None) -> tuple[ReleaseCampaign, list[Campaign]]:
    saved: list[Campaign] = []
    uc = ReleaseCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        dispatcher=AsyncMock(),
    )
    return uc, saved


def _mark(ws: uuid.UUID, campaign_id: uuid.UUID, acting: str | None, url: str = URL):
    return SetCampaignManagementCommand(
        workspace_id=ws,
        campaign_id=campaign_id,
        managed_url=url,
        managed_label="Daikon",
        acting_service=acting,
    )


class TestSetCampaignManagement:
    async def test_marks_the_campaign_as_managed_by_the_caller(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id)
        uc, saved = _set_uc(campaign)
        out = await uc(_mark(auth.workspace_id, campaign.id, "daikon"), auth=auth)
        assert isinstance(out, Success)
        assert saved[0].management == CampaignManagement(
            managed_by="daikon", url=URL, label="Daikon"
        )

    async def test_without_a_verified_app_is_refused(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id)
        uc, saved = _set_uc(campaign)
        with pytest.raises(AuthorizationError):
            await uc(_mark(auth.workspace_id, campaign.id, None), auth=auth)
        assert saved == []

    async def test_unknown_campaign_is_not_found(self) -> None:
        auth = fake_auth()
        uc, _ = _set_uc(None)
        out = await uc(_mark(auth.workspace_id, uuid.uuid4(), "daikon"), auth=auth)
        assert isinstance(out, Failure) and isinstance(out.failure(), NotFoundError)

    async def test_managed_by_another_app_conflicts(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id, managed_by="other-app")
        uc, saved = _set_uc(campaign)
        out = await uc(_mark(auth.workspace_id, campaign.id, "daikon"), auth=auth)
        assert isinstance(out, Failure) and isinstance(out.failure(), ConflictError)
        assert saved == []

    async def test_a_bad_address_is_refused(self) -> None:
        auth = fake_auth()
        campaign = _campaign(auth.workspace_id)
        uc, _ = _set_uc(campaign)
        out = await uc(
            _mark(auth.workspace_id, campaign.id, "daikon", url="javascript:alert(1)"),
            auth=auth,
        )
        assert isinstance(out, Failure) and isinstance(out.failure(), ValidationError)

    async def test_a_viewer_is_refused(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _campaign(auth.workspace_id)
        uc, _ = _set_uc(campaign)
        with pytest.raises(AuthorizationError):
            await uc(_mark(auth.workspace_id, campaign.id, "daikon"), auth=auth)


class TestReleaseCampaign:
    def _cmd(self, ws: uuid.UUID, campaign_id: uuid.UUID, reason: str = "round abandoned"):
        return ReleaseCampaignCommand(
            workspace_id=ws, campaign_id=campaign_id, user_id=uuid.uuid4(), reason=reason
        )

    async def test_an_admin_releases_a_managed_campaign(self) -> None:
        auth = fake_auth(role="admin", is_admin=True)
        campaign = _campaign(auth.workspace_id, managed_by="daikon")
        uc, saved = _release_uc(campaign)
        out = await uc(self._cmd(auth.workspace_id, campaign.id), auth=auth)
        assert isinstance(out, Success)
        assert saved[0].management is None

    async def test_an_editor_may_not_release(self) -> None:
        auth = fake_auth(role="editor")
        campaign = _campaign(auth.workspace_id, managed_by="daikon")
        uc, saved = _release_uc(campaign)
        with pytest.raises(AuthorizationError):
            await uc(self._cmd(auth.workspace_id, campaign.id), auth=auth)
        assert saved == []

    async def test_unknown_campaign_is_not_found(self) -> None:
        auth = fake_auth(role="admin", is_admin=True)
        uc, _ = _release_uc(None)
        out = await uc(self._cmd(auth.workspace_id, uuid.uuid4()), auth=auth)
        assert isinstance(out, Failure) and isinstance(out.failure(), NotFoundError)

    async def test_an_unmanaged_campaign_conflicts(self) -> None:
        auth = fake_auth(role="admin", is_admin=True)
        campaign = _campaign(auth.workspace_id)
        uc, _ = _release_uc(campaign)
        out = await uc(self._cmd(auth.workspace_id, campaign.id), auth=auth)
        assert isinstance(out, Failure) and isinstance(out.failure(), ConflictError)

    async def test_a_reason_is_required(self) -> None:
        auth = fake_auth(role="admin", is_admin=True)
        campaign = _campaign(auth.workspace_id, managed_by="daikon")
        uc, _ = _release_uc(campaign)
        out = await uc(self._cmd(auth.workspace_id, campaign.id, reason=" "), auth=auth)
        assert isinstance(out, Failure) and isinstance(out.failure(), ValidationError)
