"""Unit tests for ReopenCampaign use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.reopen_campaign import (
    ReopenCampaign,
    ReopenCampaignCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.enums import CampaignStatus
from cellar.domain.research_organization.events import CampaignReopened
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
# Builder helpers
# ---------------------------------------------------------------------------


def _make_draft_campaign(workspace_id: uuid.UUID, *, name: str = "Test") -> Campaign:
    """Build a DRAFT campaign."""
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name=name,
        description=None,
        created_by=uuid.uuid4(),
    )


def _make_closed_campaign(workspace_id: uuid.UUID, *, name: str = "Closed") -> Campaign:
    """Build a CLOSED campaign via direct constructor (avoids full close() setup)."""
    return Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name=name,
        description=None,
        status=CampaignStatus.CLOSED,
        created_by=uuid.uuid4(),
        closed_at=None,
        closed_by=uuid.uuid4(),
        close_note="first pass",
    )


def _make_superseded_campaign(workspace_id: uuid.UUID) -> Campaign:
    """Build a SUPERSEDED campaign via direct constructor."""
    return Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Already Superseded",
        description=None,
        status=CampaignStatus.SUPERSEDED,
        created_by=uuid.uuid4(),
        superseded_by_campaign_id=uuid.uuid4(),
    )


def _make_use_case(campaign: Campaign | None) -> tuple[ReopenCampaign, AsyncMock, AsyncMock]:
    """Build a ReopenCampaign use case with fakes; return (uc, campaign_repo, dispatcher)."""
    saved: list[Campaign] = []
    campaign_repo = make_campaign_repo(saved=saved, find_in_ws=campaign)

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    uc = ReopenCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        dispatcher=dispatcher,
    )
    return uc, campaign_repo, dispatcher


def _make_command(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    reason: str = "late confirmation result",
) -> ReopenCampaignCommand:
    return ReopenCampaignCommand(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        user_id=user_id or uuid.uuid4(),
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestReopenCampaign:
    # ------------------------------------------------------------------
    # 1. Happy path — CLOSED campaign reopens to DRAFT
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        auth = fake_auth()
        campaign = _make_closed_campaign(auth.workspace_id)

        uc, campaign_repo, dispatcher = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id, reason="late confirmation result")
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        reopened = out.unwrap()
        assert reopened.status == CampaignStatus.DRAFT
        assert reopened.closed_at is None
        assert reopened.closed_by is None
        assert reopened.close_note is None

        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

        events = campaign.collect_events()
        event_types = {type(e) for e in events}
        assert CampaignReopened in event_types

    # ------------------------------------------------------------------
    # 2. Campaign not found
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_campaign_not_found(self) -> None:
        auth = fake_auth()
        uc, campaign_repo, _ = _make_use_case(None)
        cmd = _make_command(auth.workspace_id, uuid.uuid4())
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 3. Campaign is DRAFT (not CLOSED) → 422 ValidationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)

        uc, campaign_repo, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 4. Campaign is SUPERSEDED → refused
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_superseded_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_superseded_campaign(auth.workspace_id)

        uc, campaign_repo, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 5. Empty reason → ValidationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_empty_reason_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_closed_campaign(auth.workspace_id)

        uc, campaign_repo, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id, reason="   ")
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 6. Unauthorized viewer
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_closed_campaign(auth.workspace_id)

        uc, campaign_repo, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        campaign_repo.save.assert_not_awaited()
