"""Unit tests for SupersedeCampaign use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.supersede_campaign import (
    SupersedeCampaign,
    SupersedeCampaignCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.research_organization.events import CampaignSuperseded
from chem_vault.domain.shared.errors import (
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
        publishes_collection=False,
        created_by=uuid.uuid4(),
    )


def _make_closed_campaign(workspace_id: uuid.UUID, *, name: str = "Old") -> Campaign:
    """Build a CLOSED campaign via direct constructor (avoids full close() setup)."""
    return Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name=name,
        description=None,
        status=CampaignStatus.CLOSED,
        publishes_collection=False,
        created_by=uuid.uuid4(),
        closed_at=None,
        closed_by=uuid.uuid4(),
        signature_id=uuid.uuid4(),
    )


def _make_superseded_campaign(workspace_id: uuid.UUID) -> Campaign:
    """Build a SUPERSEDED campaign via direct constructor."""
    return Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Already Superseded",
        description=None,
        status=CampaignStatus.SUPERSEDED,
        publishes_collection=False,
        created_by=uuid.uuid4(),
        superseded_by_campaign_id=uuid.uuid4(),
    )


def _make_use_case(
    *,
    old_campaign: Campaign | None,
    new_campaign: Campaign | None,
) -> tuple[SupersedeCampaign, AsyncMock, AsyncMock]:
    """Build a SupersedeCampaign use case with fakes; return (uc, campaign_repo, dispatcher)."""
    old_id = old_campaign.id if old_campaign is not None else uuid.uuid4()
    new_id = new_campaign.id if new_campaign is not None else uuid.uuid4()

    dispatch_map: dict[uuid.UUID, Campaign | None] = {
        old_id: old_campaign,
        new_id: new_campaign,
    }
    saved: list[Campaign] = []
    campaign_repo = make_campaign_repo(saved=saved, find_dispatch=dispatch_map)

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    uc = SupersedeCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        dispatcher=dispatcher,
    )
    return uc, campaign_repo, dispatcher


def _make_command(
    workspace_id: uuid.UUID,
    old_campaign_id: uuid.UUID,
    new_campaign_id: uuid.UUID,
) -> SupersedeCampaignCommand:
    return SupersedeCampaignCommand(
        workspace_id=workspace_id,
        old_campaign_id=old_campaign_id,
        new_campaign_id=new_campaign_id,
    )


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestSupersedeCampaign:
    # ------------------------------------------------------------------
    # 1. Happy path
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Old CLOSED campaign is marked SUPERSEDED with back-pointer to new."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        old = _make_closed_campaign(ws_id, name="Old Campaign")
        new = _make_draft_campaign(ws_id, name="New Campaign")
        # Wire: new was created with supersedes_campaign_id=old.id
        new.supersedes_campaign_id = old.id  # type: ignore[misc]

        uc, campaign_repo, dispatcher = _make_use_case(old_campaign=old, new_campaign=new)
        cmd = _make_command(ws_id, old.id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        result_campaign = out.unwrap()

        # Status + back-pointer
        assert result_campaign.status == CampaignStatus.SUPERSEDED
        assert result_campaign.superseded_by_campaign_id == new.id

        # save called exactly once with old campaign
        campaign_repo.save.assert_awaited_once()
        saved_arg = campaign_repo.save.call_args.args[0]
        assert saved_arg.id == old.id

        # Dispatcher called once
        dispatcher.dispatch_all.assert_awaited_once()

        # CampaignSuperseded event was registered on the aggregate
        events = old.collect_events()
        event_types = {type(e) for e in events}
        assert CampaignSuperseded in event_types

    # ------------------------------------------------------------------
    # 2. Old campaign not found
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_old_campaign_not_found(self) -> None:
        """Returns Failure(NotFoundError) when old campaign is missing; save NOT called."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        new = _make_draft_campaign(ws_id, name="New")
        old_id = uuid.uuid4()
        # Only new is in the map; old is absent
        dispatch_map = {new.id: new, old_id: None}
        saved: list[Campaign] = []
        campaign_repo = make_campaign_repo(saved=saved, find_dispatch=dispatch_map)

        dispatcher = AsyncMock()
        uc = SupersedeCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = _make_command(ws_id, old_id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 3. New campaign not found
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_new_campaign_not_found(self) -> None:
        """Returns Failure(NotFoundError) when new campaign is missing; save NOT called."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        old = _make_closed_campaign(ws_id, name="Old")
        new_id = uuid.uuid4()
        # Only old is in the map; new is absent
        dispatch_map = {old.id: old, new_id: None}
        saved: list[Campaign] = []
        campaign_repo = make_campaign_repo(saved=saved, find_dispatch=dispatch_map)

        dispatcher = AsyncMock()
        uc = SupersedeCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = _make_command(ws_id, old.id, new_id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 4. Old campaign is DRAFT (not CLOSED)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_old_campaign_is_draft_returns_validation_failure(self) -> None:
        """mark_superseded_by raises ValidationError when old is DRAFT; save NOT called."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        old = _make_draft_campaign(ws_id, name="Old Draft")
        new = _make_draft_campaign(ws_id, name="New")
        new.supersedes_campaign_id = old.id  # type: ignore[misc]

        uc, campaign_repo, _ = _make_use_case(old_campaign=old, new_campaign=new)
        cmd = _make_command(ws_id, old.id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 5. Old campaign already SUPERSEDED
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_old_campaign_already_superseded_returns_validation_failure(self) -> None:
        """mark_superseded_by raises ValidationError when old is SUPERSEDED; save NOT called."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        old = _make_superseded_campaign(ws_id)
        new = _make_draft_campaign(ws_id, name="New")
        new.supersedes_campaign_id = old.id  # type: ignore[misc]

        uc, campaign_repo, _ = _make_use_case(old_campaign=old, new_campaign=new)
        cmd = _make_command(ws_id, old.id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 6. New campaign's supersedes_campaign_id doesn't match old.id
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_supersedes_id_mismatch_returns_validation_failure(self) -> None:
        """Failure(ValidationError) when new.supersedes_campaign_id != old.id; save NOT called."""
        auth = fake_auth()
        ws_id = auth.workspace_id

        old = _make_closed_campaign(ws_id, name="Old")
        new = _make_draft_campaign(ws_id, name="New")
        # Wire new to point at a DIFFERENT campaign id
        wrong_id = uuid.uuid4()
        new.supersedes_campaign_id = wrong_id  # type: ignore[misc]

        uc, campaign_repo, _ = _make_use_case(old_campaign=old, new_campaign=new)
        cmd = _make_command(ws_id, old.id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        err = out.failure()
        assert isinstance(err, ValidationError)
        # Error message should reference the mismatch
        assert str(wrong_id) in str(err) or str(old.id) in str(err)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 7. Unauthorized viewer
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        """Viewer role triggers AuthorizationError before any repo calls."""
        auth = fake_auth(role="viewer")
        ws_id = auth.workspace_id

        old = _make_closed_campaign(ws_id)
        new = _make_draft_campaign(ws_id)
        new.supersedes_campaign_id = old.id  # type: ignore[misc]

        uc, campaign_repo, _ = _make_use_case(old_campaign=old, new_campaign=new)
        cmd = _make_command(ws_id, old.id, new.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
