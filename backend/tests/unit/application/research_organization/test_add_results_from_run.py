"""Unit tests for AddResultsFromRun use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.add_results_from_collection import (
    AddResultsOutcome,
)
from chem_vault.application.research_organization.add_results_from_run import (
    AddResultsFromRun,
    AddResultsFromRunCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.research_organization.source_ref import RunRef
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeResolver,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
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


def _make_run_repo(*, found: bool = True) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(
        return_value=AsyncMock() if found else None
    )
    return repo


def _make_row(molecule_id: uuid.UUID, batch_id: uuid.UUID | None) -> MagicMock:
    """Build a fake SA row object with molecule_id and batch_id attributes."""
    row = MagicMock()
    row.molecule_id = molecule_id
    row.batch_id = batch_id
    return row


class TestAddResultsFromRun:
    @pytest.mark.asyncio
    async def test_happy_path_adds_molecules_from_run(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)

        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()
        mol_c = uuid.uuid4()
        batch_a = uuid.uuid4()
        batch_b = uuid.uuid4()

        rows = [
            _make_row(mol_a, batch_a),
            _make_row(mol_b, batch_b),
            _make_row(mol_c, None),
        ]

        uow = FakeUnitOfWork()
        # The session.execute result must support .all() returning rows.
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        uow.session._execute_result = mock_result

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        run_id = uuid.uuid4()
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=run_id,
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 3
        assert outcome.skipped == 0

        # All new results carry RunRef with the correct run_id
        for r in outcome.campaign.results:
            assert isinstance(r.added_from, RunRef)
            assert r.added_from.run_id == run_id

    @pytest.mark.asyncio
    async def test_representative_batch_id_populated_for_single_batch(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)

        mol_a = uuid.uuid4()
        batch_a = uuid.uuid4()
        rows = [_make_row(mol_a, batch_a)]

        uow = FakeUnitOfWork()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        uow.session._execute_result = mock_result

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        r = result.unwrap().campaign.results[0]
        assert r.representative_batch_id == batch_a

    @pytest.mark.asyncio
    async def test_null_batch_id_when_no_batch_in_run(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        rows = [_make_row(uuid.uuid4(), None)]

        uow = FakeUnitOfWork()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        uow.session._execute_result = mock_result

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        assert result.unwrap().campaign.results[0].representative_batch_id is None

    @pytest.mark.asyncio
    async def test_idempotent_reskip_existing(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        mol_a = uuid.uuid4()
        mol_b = uuid.uuid4()
        # Pre-seed mol_a
        campaign.results.append(CampaignResult(campaign_id=campaign.id, molecule_id=mol_a))

        rows = [_make_row(mol_a, uuid.uuid4()), _make_row(mol_b, uuid.uuid4())]
        uow = FakeUnitOfWork()
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        uow.session._execute_result = mock_result

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.added == 1
        assert outcome.skipped == 1

    @pytest.mark.asyncio
    async def test_run_not_found_returns_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        uow = FakeUnitOfWork()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=False)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_failure(self) -> None:
        auth = fake_auth()
        uow = FakeUnitOfWork()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_closed_campaign_rejects_add(self) -> None:
        auth = fake_auth()
        campaign = _make_campaign(auth)
        ch = CampaignChannel(
            campaign_id=campaign.id, label="x",
            protocol_id=uuid.uuid4(), readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )
        campaign.add_channel(ch)
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4()))
        campaign.close(closed_by=auth.user_id, signature_id=uuid.uuid4(), source_protocols=[])

        uow = FakeUnitOfWork()
        mock_result = MagicMock()
        mock_result.all.return_value = [_make_row(uuid.uuid4(), None)]
        uow.session._execute_result = mock_result

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unauthorized_returns_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign = _make_campaign(auth)
        uow = FakeUnitOfWork()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        run_repo = _make_run_repo(found=True)
        resolver = FakeResolver(_fake_measurement)
        dispatcher = AsyncMock()

        uc = AddResultsFromRun(
            uow=uow,
            campaign_repo=campaign_repo,
            run_repo=run_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = AddResultsFromRunCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_id=uuid.uuid4(),
        )
        result = await uc(cmd, auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), AuthorizationError)
