"""Unit tests for UpdateCampaignMetadata use case."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.update_campaign_metadata import (
    UNSET,
    UpdateCampaignMetadata,
    UpdateCampaignMetadataCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.compound_source import ExplicitListSource
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DataLockedError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_draft_campaign(
    workspace_id: uuid.UUID,
    *,
    name: str = "Alpha Screen",
    description: str | None = "initial description",
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> Campaign:
    """Build a minimal Campaign with the given status, bypassing domain events."""
    c = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name=name,
        description=description,
        status=status,
        compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        publishes_collection=False,
        created_by=uuid.uuid4(),
    )
    c.clear_events()
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateCampaignMetadata:
    @pytest.mark.asyncio
    async def test_rename_and_change_description(self) -> None:
        """Happy path: rename + change description both applied."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        saved: list[Campaign] = []
        repo = make_campaign_repo(saved=saved, find_in_ws=campaign)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="Beta Screen",
            description="updated description",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        c = result.unwrap()
        assert c.name == "Beta Screen"
        assert c.description == "updated description"
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rename_only_description_left_unchanged(self) -> None:
        """UNSET description means description is not touched."""
        auth = fake_auth()
        campaign = _make_draft_campaign(
            auth.workspace_id, description="keep this"
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        # description defaults to UNSET — only name is passed
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="New Name",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        c = result.unwrap()
        assert c.name == "New Name"
        assert c.description == "keep this"

    @pytest.mark.asyncio
    async def test_clear_description_explicit_none(self) -> None:
        """Passing description=None explicitly clears the description."""
        auth = fake_auth()
        campaign = _make_draft_campaign(
            auth.workspace_id, description="some text"
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            description=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        c = result.unwrap()
        assert c.description is None

    @pytest.mark.asyncio
    async def test_empty_name_returns_validation_error(self) -> None:
        """A blank / whitespace-only name must return Failure(ValidationError)."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        dispatcher = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="   ",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_closed_campaign_returns_data_locked_error(self) -> None:
        """A non-DRAFT campaign must return Failure(DataLockedError)."""
        auth = fake_auth()
        campaign = _make_draft_campaign(
            auth.workspace_id, status=CampaignStatus.CLOSED
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        dispatcher = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="Attempt",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, DataLockedError)
        assert "CLOSED" in str(err) or "closed" in str(err).lower()
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_error(self) -> None:
        """Missing campaign must return Failure(NotFoundError)."""
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)
        dispatcher = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            name="Ghost",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_error(self) -> None:
        """A viewer must be rejected before any repo access."""
        auth = fake_auth(role="viewer")
        repo = make_campaign_repo()
        dispatcher = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            name="Blocked",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_changes_still_saves(self) -> None:
        """Providing the same name + UNSET description still saves (idempotent call)."""
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id, name="Alpha Screen")
        repo = make_campaign_repo(find_in_ws=campaign)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = UpdateCampaignMetadata(
            uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher
        )
        # Name matches the existing value — no change tracked
        cmd = UpdateCampaignMetadataCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            name="Alpha Screen",
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        # Save still called (we always save to stay consistent with other use cases)
        repo.save.assert_awaited_once()
