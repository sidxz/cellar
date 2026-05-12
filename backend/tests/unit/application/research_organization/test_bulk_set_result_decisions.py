"""Unit tests for BulkSetResultDecisions use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.bulk_set_result_decisions import (
    BulkSetResultDecisions,
    BulkSetResultDecisionsCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


def _draft_campaign_with_results(workspace_id: uuid.UUID, n: int) -> tuple[Campaign, list[CampaignResult]]:
    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Bulk decision test",
        description=None,
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )
    results = []
    for _ in range(n):
        r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(r)
        results.append(r)
    return campaign, results


class TestBulkSetResultDecisions:
    @pytest.mark.asyncio
    async def test_applies_decision_to_all_listed_results(self) -> None:
        auth = fake_auth()
        campaign, results = _draft_campaign_with_results(auth.workspace_id, 3)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = BulkSetResultDecisions(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        out = await uc(
            BulkSetResultDecisionsCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[r.id for r in results],
                decision=CampaignDecision.SELECTED,
                reason="Bulk accept hits",
            ),
            auth=auth,
        )

        assert isinstance(out, Success)
        outcome = out.unwrap()
        assert outcome.updated_count == 3
        assert outcome.missing_ids == []
        for r in outcome.campaign.results:
            assert r.decision == CampaignDecision.SELECTED
            assert r.decision_reason == "Bulk accept hits"
        repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_op_when_all_results_already_at_target(self) -> None:
        """All-rows-already-at-target → no aggregate save, no event dispatch."""
        auth = fake_auth()
        campaign, results = _draft_campaign_with_results(auth.workspace_id, 2)
        for r in results:
            r.set_decision(CampaignDecision.REJECTED, reason=None)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = BulkSetResultDecisions(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=dispatcher)
        out = await uc(
            BulkSetResultDecisionsCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[r.id for r in results],
                decision=CampaignDecision.REJECTED,
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().updated_count == 0
        repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_match_reports_missing_ids(self) -> None:
        auth = fake_auth()
        campaign, results = _draft_campaign_with_results(auth.workspace_id, 2)
        stray = uuid.uuid4()
        repo = make_campaign_repo(find_in_ws=campaign)

        uc = BulkSetResultDecisions(uow=FakeUnitOfWork(), campaign_repo=repo, dispatcher=AsyncMock())
        out = await uc(
            BulkSetResultDecisionsCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[results[0].id, stray, results[1].id],
                decision=CampaignDecision.SELECTED,
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        outcome = out.unwrap()
        assert outcome.updated_count == 2
        assert outcome.missing_ids == [stray]

    @pytest.mark.asyncio
    async def test_empty_result_ids_rejected(self) -> None:
        auth = fake_auth()
        campaign, _ = _draft_campaign_with_results(auth.workspace_id, 1)
        uc = BulkSetResultDecisions(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        out = await uc(
            BulkSetResultDecisionsCommand(
                workspace_id=auth.workspace_id,
                campaign_id=campaign.id,
                result_ids=[],
                decision=CampaignDecision.SELECTED,
            ),
            auth=auth,
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_missing_campaign_returns_not_found(self) -> None:
        auth = fake_auth()
        uc = BulkSetResultDecisions(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            dispatcher=AsyncMock(),
        )
        out = await uc(
            BulkSetResultDecisionsCommand(
                workspace_id=auth.workspace_id,
                campaign_id=uuid.uuid4(),
                result_ids=[uuid.uuid4()],
                decision=CampaignDecision.SELECTED,
            ),
            auth=auth,
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
