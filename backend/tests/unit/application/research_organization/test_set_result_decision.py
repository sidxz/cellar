"""Unit tests for SetResultDecision use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.set_result_decision import (
    UNSET,
    SetResultDecision,
    SetResultDecisionCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import CampaignDecision, CampaignStatus
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
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSetResultDecision:
    @pytest.mark.asyncio
    async def test_selected_with_reason_updates_decision_and_reason(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)

        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.SELECTED,
            reason="Strong hit",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        campaign_out = out.unwrap()
        assert campaign_out.results[0].decision == CampaignDecision.SELECTED
        assert campaign_out.results[0].decision_reason == "Strong hit"
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deferred_without_reason_keeps_reason_none(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.DEFERRED,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap().results[0].decision == CampaignDecision.DEFERRED
        assert out.unwrap().results[0].decision_reason is None

    @pytest.mark.asyncio
    async def test_result_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=uuid.uuid4(),  # unknown
            decision=CampaignDecision.SELECTED,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            decision=CampaignDecision.SELECTED,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        # Bypass aggregate guard by mutating the list directly
        campaign.results.append(result)

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.SELECTED,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo(find_in_ws=None)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            decision=CampaignDecision.SELECTED,
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notes_set_to_string(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.SELECTED,
            notes="Watch hERG",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap().results[0].notes == "Watch hERG"

    @pytest.mark.asyncio
    async def test_notes_explicitly_cleared(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        result.notes = "old"
        campaign.add_result(result)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.SELECTED,
            notes=None,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap().results[0].notes is None

    @pytest.mark.asyncio
    async def test_notes_unset_leaves_existing_value(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        result.notes = "keep me"
        campaign.add_result(result)

        uc = SetResultDecision(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        # Omit notes — default is UNSET; use_case must not touch result.notes
        cmd = SetResultDecisionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            decision=CampaignDecision.SELECTED,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        assert out.unwrap().results[0].notes == "keep me"
