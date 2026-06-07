"""Integration test: filtering campaigns by target (any / all)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import insert

from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignMeasurementModel,
    CampaignModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
    TargetModel,
    run_targets,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


async def _campaign_with_run_targets(session, ws, project_id, name, target_ids):
    """One campaign whose single result has one measurement on a run carrying
    ``target_ids`` (the run's run_targets). A target-less campaign passes an
    empty ``target_ids``.
    """
    protocol_id, run_id = uuid.uuid4(), uuid.uuid4()
    campaign_id, result_id = uuid.uuid4(), uuid.uuid4()
    channel_id = uuid.uuid4()

    session.add(
        ProtocolModel(
            id=protocol_id,
            workspace_id=ws,
            name="P",
            protocol_type="biochemical",
            created_by=uuid.uuid4(),
        )
    )
    session.add(
        RunModel(
            id=run_id,
            workspace_id=ws,
            protocol_id=protocol_id,
            run_date=date(2026, 1, 1),
            operator=uuid.uuid4(),
        )
    )
    session.add(
        CampaignModel(
            id=campaign_id,
            workspace_id=ws,
            project_id=project_id,
            name=name,
            created_by=uuid.uuid4(),
        )
    )
    await session.flush()
    # channel_id on a measurement is a real FK to campaign_channel.
    session.add(
        CampaignChannelModel(
            id=channel_id,
            campaign_id=campaign_id,
            label="ch",
            protocol_id=protocol_id,
            readout_definition_id=uuid.uuid4(),
            source_kind="readout_data",
            selection_rule="latest_approved_run",
            qualifier_handling="include_qualified",
        )
    )
    if target_ids:
        await session.execute(
            insert(run_targets).values(
                [{"run_id": run_id, "target_id": tid} for tid in target_ids]
            )
        )
    session.add(
        CampaignResultModel(id=result_id, campaign_id=campaign_id, molecule_id=uuid.uuid4())
    )
    await session.flush()
    session.add(
        CampaignMeasurementModel(
            id=uuid.uuid4(),
            result_id=result_id,
            channel_id=channel_id,
            source_run_id=run_id,
            value=1.0,
            value_qualifier="=",
            unit="uM",
            protocol_name_snapshot="P",
            protocol_version_snapshot=1,
        )
    )
    return campaign_id


async def test_filter_any_and_all(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    inha, dnae1 = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        s.add(TargetModel(id=inha, workspace_id=ws, name="InhA", target_type="protein"))
        s.add(TargetModel(id=dnae1, workspace_id=ws, name="DnaE1", target_type="protein"))
        c_both = await _campaign_with_run_targets(s, ws, project_id, "Both", [inha, dnae1])
        c_inha = await _campaign_with_run_targets(s, ws, project_id, "InhA only", [inha])
        c_none = await _campaign_with_run_targets(s, ws, project_id, "Untargeted", [])
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        any_inha = {
            c.id
            for c in await repo.find_by_project(
                ws, project_id, target_ids=[inha], target_logic="any"
            )
        }
        all_both = {
            c.id
            for c in await repo.find_by_project(
                ws, project_id, target_ids=[inha, dnae1], target_logic="all"
            )
        }

    assert any_inha == {c_both, c_inha}  # c_none excluded; counter-screen-style EXISTS
    assert all_both == {c_both}  # only the campaign covering BOTH
    assert c_none not in any_inha
