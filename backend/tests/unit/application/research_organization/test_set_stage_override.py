"""Unit tests for SetStageOverride use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.set_stage_override import (
    SetStageOverride,
    SetStageOverrideCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import CampaignStatus, StageOutcome
from cellar.domain.shared.errors import (
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
# Helpers
# ---------------------------------------------------------------------------


def _make_draft_campaign_with_stage_and_results(
    workspace_id: uuid.UUID,
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
    result_count: int = 1,
) -> tuple[Campaign, CampaignStage, list[CampaignResult]]:
    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Campaign",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    stage = CampaignStage(campaign_id=campaign.id, name="Primary Hit", display_order=0)
    campaign.add_stage(stage)
    results = []
    for _ in range(result_count):
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(result)
        results.append(result)
    campaign.status = status
    campaign.clear_events()
    return campaign, stage, results


def _make_draft_campaign_with_stage_and_result(
    workspace_id: uuid.UUID,
    *,
    status: CampaignStatus = CampaignStatus.DRAFT,
) -> tuple[Campaign, CampaignStage, CampaignResult]:
    campaign, stage, results = _make_draft_campaign_with_stage_and_results(
        workspace_id, status=status
    )
    return campaign, stage, results[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSetStageOverride:
    @pytest.mark.asyncio
    async def test_set_override_records_hit_with_reason(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Confirmed by re-assay",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Success)
        campaign_out = outcome.unwrap()
        override = campaign_out.results[0].stage_overrides[stage.id]
        assert override.forced_outcome == StageOutcome.HIT
        assert override.reason == "Confirmed by re-assay"
        assert override.overridden_by == auth.user_id
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_second_override_replaces_first(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        first = await uc(
            SetStageOverrideCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[result.id],
                stage_id=stage.id,
                user_id=auth.user_id,
                forced_outcome=StageOutcome.HIT,
                reason="First call",
            ),
            auth=auth,
        )
        assert isinstance(first, Success)

        second = await uc(
            SetStageOverrideCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[result.id],
                stage_id=stage.id,
                user_id=auth.user_id,
                forced_outcome=StageOutcome.MISS,
                reason="Retracted after review",
            ),
            auth=auth,
        )
        assert isinstance(second, Success)
        override = second.unwrap().results[0].stage_overrides[stage.id]
        assert override.forced_outcome == StageOutcome.MISS
        assert override.reason == "Retracted after review"

    @pytest.mark.asyncio
    async def test_clear_removes_existing_override(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        result.set_stage_override(
            stage_id=stage.id,
            forced_outcome=StageOutcome.HIT,
            reason="Pre-existing",
            overridden_by=auth.user_id,
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Success)
        assert stage.id not in outcome.unwrap().results[0].stage_overrides
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_when_nothing_overridden_is_a_noop_success(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Success)
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_outcome_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.UNTESTED,
            reason="Not a real verdict",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), ValidationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_reason_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="   ",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), ValidationError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        repo = make_campaign_repo(find_in_ws=None)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_ids=[uuid.uuid4()],
            stage_id=uuid.uuid4(),
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unknown_result_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, stage, _result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[uuid.uuid4()],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_unknown_stage_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, _stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=uuid.uuid4(),
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_returns_data_locked_error(self) -> None:
        auth = fake_auth()
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(
            auth.workspace_id, status=CampaignStatus.CLOSED
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Too late",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), DataLockedError)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_error(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, stage, result = _make_draft_campaign_with_stage_and_result(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[result.id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Blocked",
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
        repo.save.assert_not_awaited()


class TestBulkStageOverride:
    @pytest.mark.asyncio
    async def test_three_results_overridden_in_one_save(self) -> None:
        auth = fake_auth()
        campaign, stage, results = _make_draft_campaign_with_stage_and_results(
            auth.workspace_id, result_count=3
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[r.id for r in results],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Batch promote after re-assay",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Success)
        for result in outcome.unwrap().results:
            override = result.stage_overrides[stage.id]
            assert override.forced_outcome == StageOutcome.HIT
            assert override.reason == "Batch promote after re-assay"
        # One aggregate save == one optimistic-concurrency version bump.
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_forced_outcome_none_clears_every_listed_result(self) -> None:
        auth = fake_auth()
        campaign, stage, results = _make_draft_campaign_with_stage_and_results(
            auth.workspace_id, result_count=3
        )
        for result in results:
            result.set_stage_override(
                stage_id=stage.id,
                forced_outcome=StageOutcome.HIT,
                reason="Pre-existing",
                overridden_by=auth.user_id,
            )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[r.id for r in results],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=None,
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Success)
        assert all(not r.stage_overrides for r in outcome.unwrap().results)
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_unknown_id_fails_and_leaves_every_result_untouched(self) -> None:
        auth = fake_auth()
        campaign, stage, results = _make_draft_campaign_with_stage_and_results(
            auth.workspace_id, result_count=3
        )
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[results[0].id, uuid.uuid4(), results[2].id],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Batch promote",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), NotFoundError)
        assert all(not r.stage_overrides for r in campaign.results)
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_result_ids_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, stage, _results = _make_draft_campaign_with_stage_and_results(auth.workspace_id)
        repo = make_campaign_repo(find_in_ws=campaign)
        uc = SetStageOverride(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())

        cmd = SetStageOverrideCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_ids=[],
            stage_id=stage.id,
            user_id=auth.user_id,
            forced_outcome=StageOutcome.HIT,
            reason="Nothing selected",
        )
        outcome = await uc(cmd, auth=auth)

        assert isinstance(outcome, Failure)
        assert isinstance(outcome.failure(), ValidationError)
        repo.save.assert_not_awaited()
