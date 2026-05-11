"""Unit tests for OverrideResultCell use case."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.override_result_cell import (
    OverrideResultCell,
    OverrideResultCellCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    HitCall,
    ValueQualifier,
)
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


def _make_measurement(
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    value: float = 5.0,
    value_qualifier: ValueQualifier = ValueQualifier.EQ,
    unit: str = "uM",
    protocol_name: str = "Proto A",
    protocol_version: int = 2,
    source_run_id: uuid.UUID | None = None,
    source_curve_id: uuid.UUID | None = None,
    source_readout_id: uuid.UUID | None = None,
    run_date: date | None = None,
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=value,
        value_qualifier=value_qualifier,
        unit=unit,
        protocol_name_snapshot=protocol_name,
        protocol_version_snapshot=protocol_version,
        source_run_id=source_run_id,
        source_curve_id=source_curve_id,
        source_readout_id=source_readout_id,
        run_date_snapshot=run_date,
    )


def _make_campaign_with_measurement(
    workspace_id: uuid.UUID,
) -> tuple[Campaign, CampaignResult, CampaignMeasurement, uuid.UUID]:
    """Return (campaign, result, measurement, channel_id)."""
    campaign = _make_draft_campaign(workspace_id)
    channel_id = uuid.uuid4()
    result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    run_id = uuid.uuid4()
    curve_id = uuid.uuid4()
    readout_id = uuid.uuid4()
    m = _make_measurement(
        result.id,
        channel_id,
        source_run_id=run_id,
        source_curve_id=curve_id,
        source_readout_id=readout_id,
        run_date=date(2025, 1, 15),
    )
    result.add_measurement(m)
    campaign.add_result(result)
    return campaign, result, m, channel_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOverrideResultCell:
    @pytest.mark.asyncio
    async def test_happy_path_numeric_eq_value(self) -> None:
        auth = fake_auth()
        campaign, result, existing_m, channel_id = _make_campaign_with_measurement(
            auth.workspace_id
        )
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)

        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=dispatcher,
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=channel_id,
            value=1.5,
            value_qualifier=ValueQualifier.EQ,
            unit="nM",
            hit_call=HitCall.HIT,
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        updated = out.unwrap()
        new_m = updated.results[0].find_measurement(channel_id)
        assert new_m is not None
        # New value applied
        assert new_m.value == 1.5
        assert new_m.value_qualifier == ValueQualifier.EQ
        assert new_m.unit == "nM"
        assert new_m.hit_call == HitCall.HIT
        # Override flag set
        assert new_m.is_manual_override is True
        # Source FKs carried forward
        assert new_m.source_run_id == existing_m.source_run_id
        assert new_m.source_curve_id == existing_m.source_curve_id
        assert new_m.source_readout_id == existing_m.source_readout_id
        assert new_m.run_date_snapshot == existing_m.run_date_snapshot
        # Protocol snapshot carried forward
        assert new_m.protocol_name_snapshot == existing_m.protocol_name_snapshot
        assert new_m.protocol_version_snapshot == existing_m.protocol_version_snapshot
        # Measurement id is stable (same as original)
        assert new_m.id == existing_m.id
        campaign_repo.save.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_override_to_nd_stores_none_value_with_override_flag(self) -> None:
        auth = fake_auth()
        campaign, result, _, channel_id = _make_campaign_with_measurement(
            auth.workspace_id
        )
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=channel_id,
            value=None,
            value_qualifier=ValueQualifier.ND,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        new_m = out.unwrap().results[0].find_measurement(channel_id)
        assert new_m is not None
        assert new_m.value is None
        assert new_m.value_qualifier == ValueQualifier.ND
        assert new_m.is_manual_override is True

    @pytest.mark.asyncio
    async def test_eq_with_none_value_returns_validation_failure(self) -> None:
        """EQ qualifier requires a numeric value — __post_init__ must reject this."""
        auth = fake_auth()
        campaign, result, _, channel_id = _make_campaign_with_measurement(
            auth.workspace_id
        )
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=channel_id,
            value=None,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_unit_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, result, _, channel_id = _make_campaign_with_measurement(
            auth.workspace_id
        )
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=channel_id,
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="",  # empty — rejected by __post_init__
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_result_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=uuid.uuid4(),  # unknown
            channel_id=uuid.uuid4(),
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_measurement_not_on_result_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign, result, _, _channel_id = _make_campaign_with_measurement(
            auth.workspace_id
        )
        different_channel_id = uuid.uuid4()
        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=different_channel_id,  # no measurement for this channel
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        err = out.failure()
        assert isinstance(err, NotFoundError)
        assert "CampaignMeasurement" in str(err)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_non_draft_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _make_draft_campaign(auth.workspace_id)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.results.append(result)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        campaign_repo = make_campaign_repo(find_in_ws=campaign)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            result_id=result.id,
            channel_id=uuid.uuid4(),
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign_repo = make_campaign_repo(find_in_ws=None)
        uc = OverrideResultCell(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            dispatcher=AsyncMock(),
        )
        cmd = OverrideResultCellCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            result_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            value=1.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
        )
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), AuthorizationError)
        campaign_repo.save.assert_not_awaited()
