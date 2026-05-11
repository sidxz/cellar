"""Unit tests for CreateCampaign use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.create_campaign import (
    CreateCampaign,
    CreateCampaignCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.compound_source import (
    CollectionSource,
    DerivedFromCampaignSource,
    ExplicitListSource,
    SavedSearchSource,
)
from chem_vault.domain.research_organization.enums import CampaignDecision
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from chem_vault.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    def __init__(self) -> None:
        self._tracked: list = []

    def track(self, aggregate) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for agg in self._tracked:
            events.extend(agg.collect_events())
            agg.clear_events()
        return events

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def _fake_auth(*, role: str = "editor", is_admin: bool = False):
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = role
    auth.is_admin = is_admin
    # role hierarchy: viewer < editor < admin
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    current = rank.get(role, 0)
    auth.has_role = lambda min_role: current >= rank.get(min_role, 0)
    return auth


def _make_campaign_repo(saved: list[Campaign] | None = None, *, find_in_ws=None) -> AsyncMock:
    repo = AsyncMock()
    captured: list[Campaign] = saved if saved is not None else []

    async def _save(agg: Campaign) -> None:
        captured.append(agg)

    repo.save = AsyncMock(side_effect=_save)
    repo.find_by_id_in_workspace = AsyncMock(return_value=find_in_ws)
    repo.saved = captured  # type: ignore[attr-defined]
    return repo


def _make_collection_repo(
    *, in_ws: bool = True, molecule_ids: list[uuid.UUID] | None = None
) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(
        return_value=object() if in_ws else None
    )
    repo.get_molecule_ids = AsyncMock(return_value=molecule_ids or [])
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateCampaign:
    @pytest.mark.asyncio
    async def test_create_campaign_with_explicit_list_seeds_results(self) -> None:
        auth = _fake_auth()
        mol_a, mol_b, mol_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        campaign_repo = _make_campaign_repo()
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Initial Screen",
            description="kick-off",
            compound_source=ExplicitListSource(
                molecule_ids=[mol_a, mol_b, mol_a, mol_c]  # dupe to test dedupe
            ),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign = result.unwrap()
        assert isinstance(campaign, Campaign)
        assert campaign.name == "Initial Screen"
        # Dedupe applied, order preserved
        mol_ids = [r.molecule_id for r in campaign.results]
        assert mol_ids == [mol_a, mol_b, mol_c]
        # All seeded results carry the campaign id
        assert all(r.campaign_id == campaign.id for r in campaign.results)
        # Default decision is DEFERRED
        assert all(r.decision == CampaignDecision.DEFERRED for r in campaign.results)
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_campaign_with_collection_source_resolves_membership(
        self,
    ) -> None:
        auth = _fake_auth()
        coll_id = uuid.uuid4()
        members = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        campaign_repo = _make_campaign_repo()
        collection_repo = _make_collection_repo(in_ws=True, molecule_ids=members)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="From collection",
            description=None,
            compound_source=CollectionSource(collection_id=coll_id),
            publishes_collection=False,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        campaign = result.unwrap()
        assert [r.molecule_id for r in campaign.results] == members
        collection_repo.find_by_id_in_workspace.assert_awaited_once_with(
            auth.workspace_id, coll_id
        )
        collection_repo.get_molecule_ids.assert_awaited_once()
        # workspace_id and collection_id flow into get_molecule_ids
        call_kwargs = collection_repo.get_molecule_ids.await_args
        assert call_kwargs.args[0] == auth.workspace_id
        assert call_kwargs.args[1] == coll_id

    @pytest.mark.asyncio
    async def test_create_campaign_with_collection_source_not_found_returns_failure(
        self,
    ) -> None:
        auth = _fake_auth()
        campaign_repo = _make_campaign_repo()
        collection_repo = _make_collection_repo(in_ws=False)
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="missing",
            description=None,
            compound_source=CollectionSource(collection_id=uuid.uuid4()),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_campaign_with_derived_from_campaign_filters_selected_only(
        self,
    ) -> None:
        auth = _fake_auth()
        # Build an origin campaign with three results in three decisions
        origin = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="origin",
            description=None,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=False,
            created_by=auth.user_id,
        )
        sel_mol = uuid.uuid4()
        def_mol = uuid.uuid4()
        rej_mol = uuid.uuid4()
        r_sel = CampaignResult(campaign_id=origin.id, molecule_id=sel_mol)
        r_sel.set_decision(CampaignDecision.SELECTED)
        r_def = CampaignResult(campaign_id=origin.id, molecule_id=def_mol)
        r_def.set_decision(CampaignDecision.DEFERRED)
        r_rej = CampaignResult(campaign_id=origin.id, molecule_id=rej_mol)
        r_rej.set_decision(CampaignDecision.REJECTED)
        origin.add_result(r_sel)
        origin.add_result(r_def)
        origin.add_result(r_rej)

        campaign_repo = _make_campaign_repo(find_in_ws=origin)
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="follow-up",
            description="derived",
            compound_source=DerivedFromCampaignSource(
                campaign_id=origin.id,
                decision_filter=[CampaignDecision.SELECTED],
            ),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        new = result.unwrap()
        assert [r.molecule_id for r in new.results] == [sel_mol]
        campaign_repo.find_by_id_in_workspace.assert_awaited_once_with(
            auth.workspace_id, origin.id
        )

    @pytest.mark.asyncio
    async def test_create_campaign_derived_from_campaign_not_found(self) -> None:
        auth = _fake_auth()
        campaign_repo = _make_campaign_repo(find_in_ws=None)
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="follow-up",
            description=None,
            compound_source=DerivedFromCampaignSource(
                campaign_id=uuid.uuid4(),
                decision_filter=[CampaignDecision.SELECTED],
            ),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_campaign_rejects_when_resolved_zero_compounds(self) -> None:
        auth = _fake_auth()
        # Origin campaign has no selected results — the derived seed will be empty
        origin = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="origin",
            description=None,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=False,
            created_by=auth.user_id,
        )
        # Add only a deferred result — the SELECTED filter resolves to []
        only_def = CampaignResult(campaign_id=origin.id, molecule_id=uuid.uuid4())
        only_def.set_decision(CampaignDecision.DEFERRED)
        origin.add_result(only_def)

        campaign_repo = _make_campaign_repo(find_in_ws=origin)
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="empty",
            description=None,
            compound_source=DerivedFromCampaignSource(
                campaign_id=origin.id,
                decision_filter=[CampaignDecision.SELECTED],
            ),
            publishes_collection=False,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "zero" in str(err).lower()
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_campaign_saved_search_source_returns_validation_error_for_now(
        self,
    ) -> None:
        auth = _fake_auth()
        campaign_repo = _make_campaign_repo()
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="ss-campaign",
            description=None,
            compound_source=SavedSearchSource(saved_search_id=uuid.uuid4()),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "saved_search" in str(err).lower()
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_campaign_rejects_when_unauthorized(self) -> None:
        auth = _fake_auth(role="viewer")
        campaign_repo = _make_campaign_repo()
        collection_repo = _make_collection_repo()
        dispatcher = AsyncMock()

        uc = CreateCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            collection_repo=collection_repo,
            dispatcher=dispatcher,
        )
        cmd = CreateCampaignCommand(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="blocked",
            description=None,
            compound_source=ExplicitListSource(molecule_ids=[uuid.uuid4()]),
            publishes_collection=True,
            created_by=auth.user_id,
            supersedes_campaign_id=None,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
