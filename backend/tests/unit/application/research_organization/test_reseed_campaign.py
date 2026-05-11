"""Unit tests for ReseedCampaign use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.reseed_campaign import (
    ReseedCampaign,
    ReseedCampaignCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.shared.errors import (
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


def _make_channel(campaign_id: uuid.UUID) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign_id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        publishes_collection=True,
        created_by=uuid.uuid4(),
    )


def _make_measurement(result_id: uuid.UUID, channel_id: uuid.UUID) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )


def _reseed_measurement_factory(channel, result_id, molecule_id) -> CampaignMeasurement:
    return _make_measurement(result_id, channel.id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReseedCampaign:
    # ------------------------------------------------------------------
    # 1. Happy path — ExplicitListSource
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_with_explicit_list_replaces_results_and_fills_measurements(
        self,
    ) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)

        # Add one channel
        channel = _make_channel(campaign.id)
        campaign.add_channel(channel)

        # Pre-seed 2 old results
        old_mol_a, old_mol_b = uuid.uuid4(), uuid.uuid4()
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=old_mol_a))
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=old_mol_b))

        new_mol_a, new_mol_b, new_mol_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        resolver = FakeResolver(factory=_reseed_measurement_factory)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=ExplicitListSource(molecule_ids=[new_mol_a, new_mol_b, new_mol_c]),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()

        # Old results replaced by 3 new ones
        assert len(campaign_out.results) == 3
        mol_ids = [r.molecule_id for r in campaign_out.results]
        assert mol_ids == [new_mol_a, new_mol_b, new_mol_c]

        # Each result carries the correct campaign_id
        assert all(r.campaign_id == campaign.id for r in campaign_out.results)

        # Default decision is DEFERRED
        assert all(r.decision == CampaignDecision.DEFERRED for r in campaign_out.results)

        # Each new result has exactly 1 measurement (one per existing channel)
        assert all(len(r.measurements) == 1 for r in campaign_out.results)

        # Resolver called once per new result (3 times total)
        assert len(resolver.calls) == 3

        # Save + dispatch called once each
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    # ------------------------------------------------------------------
    # 2. Happy path — CollectionSource
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_with_collection_source_succeeds(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        coll_id = uuid.uuid4()
        members = [uuid.uuid4(), uuid.uuid4()]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=True, molecule_ids=members)
        resolver = FakeResolver(factory=_reseed_measurement_factory)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=CollectionSource(collection_id=coll_id),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()
        assert len(campaign_out.results) == 2
        assert [r.molecule_id for r in campaign_out.results] == members

    # ------------------------------------------------------------------
    # 3. Happy path — DerivedFromCampaignSource with decision_filter
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_with_derived_from_campaign_filters_by_decision(
        self,
    ) -> None:
        auth = fake_auth()
        # The campaign being reseeded
        target_campaign = _make_draft_campaign(auth.workspace_id)

        # Origin campaign from which compounds are pulled
        origin_campaign = _make_draft_campaign(auth.workspace_id)
        sel_mol = uuid.uuid4()
        def_mol = uuid.uuid4()
        rej_mol = uuid.uuid4()

        r_sel = CampaignResult(campaign_id=origin_campaign.id, molecule_id=sel_mol)
        r_sel.set_decision(CampaignDecision.SELECTED)
        r_def = CampaignResult(campaign_id=origin_campaign.id, molecule_id=def_mol)
        r_def.set_decision(CampaignDecision.DEFERRED)
        r_rej = CampaignResult(campaign_id=origin_campaign.id, molecule_id=rej_mol)
        r_rej.set_decision(CampaignDecision.REJECTED)
        origin_campaign.add_result(r_sel)
        origin_campaign.add_result(r_def)
        origin_campaign.add_result(r_rej)

        # Dispatch by id: target_campaign id → target_campaign, origin id → origin
        campaign_repo = make_campaign_repo(
            find_dispatch={
                target_campaign.id: target_campaign,
                origin_campaign.id: origin_campaign,
            }
        )
        collection_repo = make_collection_repo()
        resolver = FakeResolver(factory=_reseed_measurement_factory)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=target_campaign.id,
            new_source=DerivedFromCampaignSource(
                campaign_id=origin_campaign.id,
                decision_filter=[CampaignDecision.SELECTED],
            ),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign_out = result.unwrap()
        assert len(campaign_out.results) == 1
        assert campaign_out.results[0].molecule_id == sel_mol

    # ------------------------------------------------------------------
    # 4. SavedSearchSource returns ValidationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_with_saved_search_source_returns_validation_error(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=make_collection_repo(),
            resolver=FakeResolver(factory=_reseed_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=SavedSearchSource(saved_search_id=uuid.uuid4()),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "not yet supported" in str(err).lower()
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 5. Empty resolved list returns ValidationError
    #    Use CollectionSource returning zero members (ExplicitListSource
    #    validates at construction and already rejects empty lists).
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_rejects_when_resolved_zero_compounds(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        # Collection found but returns zero molecule_ids
        collection_repo = make_collection_repo(in_ws=True, molecule_ids=[])

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=FakeResolver(factory=_reseed_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=CollectionSource(collection_id=uuid.uuid4()),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "zero compounds" in str(err).lower()
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 6. Campaign not found → NotFoundError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_campaign_not_found_returns_not_found_error(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        resolver = FakeResolver(factory=_reseed_measurement_factory)

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=make_collection_repo(),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            new_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()
        assert resolver.calls == []

    # ------------------------------------------------------------------
    # 7. Campaign not DRAFT → ValidationError mentioning status
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_non_draft_campaign_returns_validation_error(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        # Force status to CLOSED without calling close() (which has guards)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        resolver = FakeResolver(factory=_reseed_measurement_factory)

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=make_collection_repo(),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        msg = str(err).lower()
        assert "draft" in msg or "closed" in msg
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 8. CollectionSource collection not found → NotFoundError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_collection_not_found_returns_not_found_error(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        collection_repo = make_collection_repo(in_ws=False)

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=FakeResolver(factory=_reseed_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            new_source=CollectionSource(collection_id=uuid.uuid4()),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 9. DerivedFromCampaignSource — origin campaign not found
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_derived_campaign_origin_not_found_returns_not_found_error(
        self,
    ) -> None:
        auth = fake_auth()
        target_campaign = _make_draft_campaign(auth.workspace_id)
        missing_origin_id = uuid.uuid4()

        # target_campaign found, but origin (missing_origin_id) returns None
        campaign_repo = make_campaign_repo(
            find_dispatch={
                target_campaign.id: target_campaign,
                # missing_origin_id intentionally absent → returns None
            }
        )
        collection_repo = make_collection_repo()

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            resolver=FakeResolver(factory=_reseed_measurement_factory),
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=target_campaign.id,
            new_source=DerivedFromCampaignSource(
                campaign_id=missing_origin_id,
                decision_filter=[CampaignDecision.SELECTED],
            ),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 10. Unauthorized — viewer role → AuthorizationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_reseed_unauthorized_viewer_returns_authorization_error(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo()
        resolver = FakeResolver(factory=_reseed_measurement_factory)

        uc = ReseedCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=make_collection_repo(),
            resolver=resolver,
            dispatcher=AsyncMock(),
        )
        cmd = ReseedCampaignCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            new_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
        assert resolver.calls == []
