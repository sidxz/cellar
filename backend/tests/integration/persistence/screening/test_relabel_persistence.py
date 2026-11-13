"""Integration tests: relabelling a run's positions persists, and its readout rows can follow."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import text

from cellar.domain.screening_assay.enums import WellType
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.run import PositionEdit
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignMeasurementModel,
    CampaignModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import _insert_readout_def
from tests.integration.persistence.screening.test_measured_curve_lifecycle import (
    _repos,
    _run_with_curves,
)

pytestmark = pytest.mark.integration

# readout_data.batch_id / molecule_id carry no foreign key, so invented ids stand in
# for batches and molecules here.


async def _protocol_id(session, run_id: uuid.UUID) -> uuid.UUID:  # type: ignore[no-untyped-def]
    return (
        await session.execute(text("SELECT protocol_id FROM runs WHERE id = :id"), {"id": run_id})
    ).scalar_one()


async def _with_readouts(session_factory, workspace_id, well_ids: list[uuid.UUID]):  # type: ignore[no-untyped-def]
    """A run with curves plus one raw readout row per given well id (repeats allowed)."""
    run_id, wells = await _run_with_curves(session_factory, workspace_id)
    b1, m1 = uuid.uuid4(), uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        rd_id = uuid.uuid4()
        await _insert_readout_def(uow, rd_id, await _protocol_id(uow.session, run_id))
        rows = [
            ReadoutData(
                workspace_id=workspace_id,
                run_id=run_id,
                well_id=wells[i],
                molecule_id=m1,
                batch_id=b1,
                readout_definition_id=rd_id,
                value=QualifiedValue(value=50.0),
            )
            for i in well_ids
        ]
        await _repos(uow)["readout_data_repo"].save_bulk(rows)
        await uow.commit()
    return run_id, wells, rows, (b1, m1)


async def _batch_and_molecule(session_factory, run_id: uuid.UUID) -> list[tuple]:  # type: ignore[no-untyped-def]
    async with session_factory() as s:
        result = await s.execute(
            text(
                "SELECT well_id, batch_id, molecule_id FROM readout_data "
                "WHERE run_id = :run ORDER BY well_id"
            ),
            {"run": run_id},
        )
        return [tuple(r) for r in result.all()]


async def test_repoint_well_moves_only_that_wells_rows(session_factory, workspace_id):
    run_id, wells, _, (b1, m1) = await _with_readouts(session_factory, workspace_id, [0, 0, 1])
    b2, m2 = uuid.uuid4(), uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = _repos(uow)["readout_data_repo"]
        assert (
            await repo.repoint_well(workspace_id, run_id, wells[0], batch_id=b2, molecule_id=m2)
            == 2
        )
        await uow.commit()

    rows = await _batch_and_molecule(session_factory, run_id)
    assert sorted((b, m) for w, b, m in rows if w == wells[0]) == [(b2, m2), (b2, m2)]
    assert [(b, m) for w, b, m in rows if w == wells[1]] == [(b1, m1)]


async def test_repoint_well_to_none_and_other_workspace(session_factory, workspace_id):
    run_id, wells, _, _ = await _with_readouts(session_factory, workspace_id, [0, 0])
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = _repos(uow)["readout_data_repo"]
        assert (
            await repo.repoint_well(
                uuid.uuid4(), run_id, wells[0], batch_id=None, molecule_id=None
            )
            == 0
        )
        assert (
            await repo.repoint_well(
                workspace_id, run_id, wells[0], batch_id=None, molecule_id=None
            )
            == 2
        )
        await uow.commit()

    rows = await _batch_and_molecule(session_factory, run_id)
    assert [(b, m) for _, b, m in rows] == [(None, None), (None, None)]


async def test_run_save_persists_relabelled_wells_and_keeps_curves(session_factory, workspace_id):
    run_id, wells = await _run_with_curves(session_factory, workspace_id)
    well_id = wells[1]
    new_batch = uuid.uuid4()
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        run_repo = _repos(uow)["run_repo"]
        run = await run_repo.find_by_id_in_workspace(workspace_id, run_id)
        assert run is not None
        well = next(w for w in run.wells if w.id == well_id)
        edited_values = replace(
            well.values,
            label="buffer only",
            note="bubble",
            well_type=WellType.REFERENCE,
            batch_id=new_batch,
            dose=12.5,
        )
        run.relabel_positions([PositionEdit(well_id, well.values, edited_values)])
        await run_repo.save(run)
        await uow.commit()

    async with uow:
        reloaded = await _repos(uow)["run_repo"].find_by_id_in_workspace(workspace_id, run_id)
        assert reloaded is not None
        reloaded_well = next(w for w in reloaded.wells if w.id == well_id)
        assert reloaded_well.values == edited_values and reloaded_well.id == well_id
        curve_repo = SQLAlchemyMeasuredCurveRepository(uow)
        assert len(await curve_repo.find_by_run(workspace_id, run_id)) == 6


async def test_find_names_using_readouts(session_factory, workspace_id):
    run_id, _, rows, _ = await _with_readouts(session_factory, workspace_id, [0, 1])
    used, unused = rows[0].id, rows[1].id
    campaign_id, result_id, channel_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        protocol_id = await _protocol_id(s, run_id)
        s.add(
            CampaignModel(
                id=campaign_id,
                workspace_id=workspace_id,
                project_id=uuid.uuid4(),
                name="Campaign A",
                created_by=uuid.uuid4(),
            )
        )
        await s.flush()
        s.add(
            CampaignChannelModel(
                id=channel_id,
                campaign_id=campaign_id,
                label="ch",
                protocol_id=protocol_id,
                readout_definition_id=rows[0].readout_definition_id,
                source_kind="readout_data",
                selection_rule="latest_approved_run",
                qualifier_handling="include_qualified",
            )
        )
        s.add(CampaignResultModel(id=result_id, campaign_id=campaign_id, molecule_id=uuid.uuid4()))
        await s.flush()
        s.add(
            CampaignMeasurementModel(
                id=uuid.uuid4(),
                result_id=result_id,
                channel_id=channel_id,
                source_run_id=run_id,
                source_readout_id=used,
                value=50.0,
                value_qualifier="=",
                unit="uM",
                protocol_name_snapshot="P",
                protocol_version_snapshot=1,
            )
        )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        campaign_repo = SQLAlchemyCampaignRepository(uow)
        assert await campaign_repo.find_names_using_readouts(workspace_id, [used, unused]) == {
            used: "Campaign A"
        }
        assert await campaign_repo.find_names_using_readouts(uuid.uuid4(), [used]) == {}
        assert await campaign_repo.find_names_using_readouts(workspace_id, []) == {}
