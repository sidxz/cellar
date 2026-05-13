"""Unit tests for AddResultsFromCollection use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_results_from_collection import (
    AddResultsFromCollection,
    AddResultsFromCollectionCommand,
    AddResultsOutcome,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.source_ref import CollectionRef
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    FakeResolver,
    fake_auth,
    make_campaign_repo,
    make_collection_repo,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)


def _make_campaign(auth) -> Campaign:
    return Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        publishes_collection=True,
        created_by=auth.user_id,
    )


def _make_channel(campaign: Campaign) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )


def _fake_measurement(channel, result_id, molecule_id) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=None,
        value_qualifier=ValueQualifier.ND,
        unit="-",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )


class TestAddResultsFromCollection:
    @pytest.mark.asyncio
    async def test_happy_path_adds_all_molecules(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        mols = [uuid.uuid4() for _ in range(5)]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=True, molecule_ids=mols)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        coll_id = uuid.uuid4()
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            collection_id=coll_id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert isinstance(outcome, AddResultsOutcome)
        assert outcome.added == 5
        assert outcome.skipped == 0
        assert len(outcome.campaign.results) == 5
        # All results attributed to CollectionRef
        for r in outcome.campaign.results:
            assert isinstance(r.added_from, CollectionRef)
            assert r.added_from.collection_id == coll_id

    @pytest.mark.asyncio
    async def test_idempotent_reskip_existing(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()
        mol_c = uuid.uuid4()
        # Pre-seed mol_a and mol_b
        campaign.results.append(CampaignResult(campaign_id=campaign.id, molecule_id=mol_a))
        campaign.results.append(CampaignResult(campaign_id=campaign.id, molecule_id=mol_b))

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=True, molecule_ids=[mol_a, mol_b, mol_c])
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            collection_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 1
        assert outcome.skipped == 2
        assert len(outcome.campaign.results) == 3

    @pytest.mark.asyncio
    async def test_collection_not_found_returns_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=False)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            collection_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        collection_repo = make_collection_repo(in_ws=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            collection_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_rejects_add(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        ch = _make_channel(campaign)
        campaign.add_channel(ch)
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4()))
        campaign.close(closed_by=auth.user_id, signature_id=uuid.uuid4(), source_protocols=[])

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=True, molecule_ids=[uuid.uuid4()])
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            collection_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_returns_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_campaign(auth)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromCollection(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromCollectionCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            collection_id=uuid.uuid4(),
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
