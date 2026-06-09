"""Integration test: campaign targets read projection (union of run targets)."""

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


def _measurement_snapshot_kwargs() -> dict:
    """Columns needed to satisfy both the DB NOT-NULLs (no default) and the
    domain CampaignMeasurement invariant (a "=" qualifier needs a numeric value),
    since find_by_project reconstitutes the aggregate through the domain.
    """
    return {
        "value": 1.0,
        "value_qualifier": "=",
        "unit": "uM",
        "protocol_name_snapshot": "P",
        "protocol_version_snapshot": 1,
    }


async def _seed_campaign_with_targets(session, ws, project_id):
    """One campaign, one result, two measurements referencing two runs.
    run A -> {InhA, HepG2}; run B (via contributing_run_ids) -> {InhA}.
    Expected distinct campaign targets: {InhA, HepG2}.
    """
    protocol_id = uuid.uuid4()
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    inha, hepg2 = uuid.uuid4(), uuid.uuid4()
    campaign_id, result_id = uuid.uuid4(), uuid.uuid4()
    channel_a, channel_b = uuid.uuid4(), uuid.uuid4()

    session.add(
        ProtocolModel(
            id=protocol_id,
            workspace_id=ws,
            name="P",
            protocol_type="biochemical",
            created_by=uuid.uuid4(),
        )
    )
    for rid in (run_a, run_b):
        session.add(
            RunModel(
                id=rid,
                workspace_id=ws,
                protocol_id=protocol_id,
                run_date=date(2026, 1, 1),
                operator=uuid.uuid4(),
            )
        )
    session.add(TargetModel(id=inha, workspace_id=ws, name="InhA", target_type="protein"))
    session.add(TargetModel(id=hepg2, workspace_id=ws, name="HepG2", target_type="cell_line"))
    session.add(
        CampaignModel(
            id=campaign_id,
            workspace_id=ws,
            project_id=project_id,
            name="C",
            created_by=uuid.uuid4(),
        )
    )
    await session.flush()
    # channel_id on a measurement is a real FK to campaign_channel; two
    # channels because (result_id, channel_id) is unique per measurement.
    for cid in (channel_a, channel_b):
        session.add(
            CampaignChannelModel(
                id=cid,
                campaign_id=campaign_id,
                label="ch",
                protocol_id=protocol_id,
                readout_definition_id=uuid.uuid4(),
                source_kind="readout_data",
                selection_rule="latest_approved_run",
                qualifier_handling="include_qualified",
            )
        )
    await session.execute(
        insert(run_targets).values(
            [
                {"run_id": run_a, "target_id": inha},
                {"run_id": run_a, "target_id": hepg2},
                {"run_id": run_b, "target_id": inha},
            ]
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
            channel_id=channel_a,
            source_run_id=run_a,
            **_measurement_snapshot_kwargs(),
        )
    )
    session.add(
        CampaignMeasurementModel(
            id=uuid.uuid4(),
            result_id=result_id,
            channel_id=channel_b,
            source_run_id=None,
            contributing_run_ids=[run_b],
            **_measurement_snapshot_kwargs(),
        )
    )
    await session.commit()
    return campaign_id, {inha, hepg2}, {"InhA", "HepG2"}


async def test_project_targets_unions_and_dedups(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        campaign_id, _ids, names = await _seed_campaign_with_targets(s, ws, project_id)

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        campaigns = await repo.find_by_project(ws, project_id)
        result = await repo.project_targets(ws, campaigns)

    targets = result[campaign_id]
    assert {t.name for t in targets} == names
    assert len(targets) == 2  # InhA deduped across the two runs
    assert [t.name for t in targets] == sorted(t.name for t in targets)  # sorted by name


async def test_project_targets_empty_campaign_returns_empty(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    campaign_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(
            CampaignModel(
                id=campaign_id,
                workspace_id=ws,
                project_id=project_id,
                name="Quiet",
                created_by=uuid.uuid4(),
            )
        )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        campaigns = await repo.find_by_project(ws, project_id)
        result = await repo.project_targets(ws, campaigns)

    assert result.get(campaign_id, []) == []
