"""Integration tests for SQLAlchemyCampaignRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_management import CampaignManagement
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    MeasurementBasis,
    QcVerdict,
    QualifierHandling,
    SelectionRule,
    StageKind,
    StageOutcome,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.measurement_facts import Concentration
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.shared.errors import ConcurrencyConflictError
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _build_campaign(
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    *,
    add_channel: bool = True,
    add_result: bool = True,
    add_measurement: bool = True,
    stage_name: str | None = None,
) -> Campaign:
    """``stage_name`` makes the column a stage column with an ``IC50 < 5`` criterion."""
    workspace_id = workspace_id or uuid.uuid4()
    project_id = project_id or uuid.uuid4()
    c = Campaign.create(
        workspace_id=workspace_id,
        project_id=project_id,
        name="Test Campaign",
        description="x",
        created_by=uuid.uuid4(),
    )
    c.collect_events()  # discard CampaignCreated for test cleanliness
    stage = None
    if stage_name is not None:
        stage = CampaignStage(campaign_id=c.id, name=stage_name, display_order=0)
        c.add_stage(stage)
    if add_channel:
        ch = CampaignChannel(
            campaign_id=c.id,
            label="IC50",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
            selection_rule=SelectionRule.LATEST_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
            stage_id=stage.id if stage else None,
        )
        c.add_channel(ch)
        if stage is not None:
            c.update_stage(
                stage.id,
                criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=5.0)],
            )
        if add_result:
            r = CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4())
            c.add_result(r)
            if add_measurement:
                m = CampaignMeasurement(
                    result_id=r.id,
                    channel_id=ch.id,
                    value=42.0,
                    value_qualifier=ValueQualifier.EQ,
                    unit="nM",
                    protocol_name_snapshot="EGFR",
                    protocol_version_snapshot=3,
                )
                r.add_measurement(m)
    return c


async def test_save_and_load_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        reloaded = await repo2.find_by_id(c.id)

    assert reloaded is not None
    assert reloaded.name == c.name
    assert reloaded.status == CampaignStatus.DRAFT
    assert len(reloaded.channels) == 1
    assert reloaded.channels[0].label == "IC50"
    assert len(reloaded.results) == 1
    assert len(reloaded.results[0].measurements) == 1
    assert reloaded.results[0].measurements[0].value == 42.0


async def test_find_by_id_in_workspace_returns_none_for_wrong_workspace(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        assert await repo2.find_by_id_in_workspace(uuid.uuid4(), c.id) is None
        assert await repo2.find_by_id_in_workspace(c.workspace_id, c.id) is not None


async def test_optimistic_concurrency_conflict(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    workspace_id = uuid.uuid4()
    c = _build_campaign(workspace_id=workspace_id)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    # Both UoWs load the SAME version BEFORE either commits
    uow_a = AsyncUnitOfWork(session_factory)
    uow_b = AsyncUnitOfWork(session_factory)
    await uow_a.__aenter__()
    await uow_b.__aenter__()
    repo_a = SQLAlchemyCampaignRepository(uow_a)
    repo_b = SQLAlchemyCampaignRepository(uow_b)
    a = await repo_a.find_by_id(c.id)
    b = await repo_b.find_by_id(c.id)
    assert a is not None
    assert b is not None
    assert a.version == b.version == 1

    # A saves and commits — version 1 -> 2
    a.name = "renamed-a"
    await repo_a.save(a)
    await uow_a.commit()
    await uow_a.__aexit__(None, None, None)

    # B tries to save with stale version 1 — must conflict
    b.name = "renamed-b"
    with pytest.raises(ConcurrencyConflictError):
        await repo_b.save(b)
    await uow_b.__aexit__(None, None, None)


async def test_is_locked_returns_true_for_closed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # First persist as draft (children must be inserted while parent is draft —
    # migration 027 installs a DB trigger that blocks writes to closed parents).
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    # Now close the aggregate and persist the status flip.
    async with AsyncUnitOfWork(session_factory) as uow_close:
        repo_close = SQLAlchemyCampaignRepository(uow_close)
        loaded = await repo_close.find_by_id(c.id)
        assert loaded is not None
        loaded.close(
            closed_by=uuid.uuid4(),
            note=None,
            source_protocols=[{"id": "p1", "name": "X", "version": 1}],
        )
        loaded.collect_events()  # discard CampaignClosed
        await repo_close.save(loaded)
        await uow_close.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        locked = await repo2.is_locked(c.workspace_id, c.id)
    assert locked is True


async def test_is_locked_false_for_draft(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        locked = await repo2.is_locked(c.workspace_id, c.id)
    assert locked is False


async def test_find_by_project(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    a = _build_campaign(workspace_id=workspace_id, project_id=project_id)
    b = _build_campaign(workspace_id=workspace_id, project_id=project_id)
    c_other = _build_campaign(workspace_id=workspace_id)  # different project
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(a)
        await repo.save(b)
        await repo.save(c_other)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        found = await repo2.find_by_project(workspace_id, project_id)
    assert {x.id for x in found} == {a.id, b.id}


async def test_find_by_project_filters_on_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    project_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    draft = _build_campaign(workspace_id=workspace_id, project_id=project_id)
    # No children on the closed one — a DB trigger blocks writes under a
    # closed campaign, and this test only cares about the status filter.
    closed = _build_campaign(
        workspace_id=workspace_id,
        project_id=project_id,
        add_channel=False,
        add_result=False,
        add_measurement=False,
    )
    closed.status = CampaignStatus.CLOSED
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(draft)
        await repo.save(closed)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        found_closed = await repo2.find_by_project(
            workspace_id, project_id, status=CampaignStatus.CLOSED
        )
        found_draft = await repo2.find_by_project(
            workspace_id, project_id, status=CampaignStatus.DRAFT
        )
        found_all = await repo2.find_by_project(workspace_id, project_id)

    assert {x.id for x in found_closed} == {closed.id}
    assert {x.id for x in found_draft} == {draft.id}
    assert {x.id for x in found_all} == {draft.id, closed.id}


async def test_results_keep_their_order_after_a_row_is_updated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Editing one row must not reshuffle the grid.

    Without ``order_by`` on the relationship the rows come back in Postgres
    heap order, and an UPDATE rewrites the tuple — moving the edited row.
    """
    c = _build_campaign(add_result=False, add_measurement=False)
    for _ in range(5):
        c.add_result(CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4()))
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        loaded = await repo2.find_by_id_in_workspace(c.workspace_id, c.id)
        assert loaded is not None
        order_before = [r.id for r in loaded.results]
        # Touch the first row — the one most likely to move in heap order.
        loaded.results[0].notes = "edited"
        await repo2.save(loaded)
        await uow2.commit()

    async with AsyncUnitOfWork(session_factory) as uow3:
        repo3 = SQLAlchemyCampaignRepository(uow3)
        reloaded = await repo3.find_by_id_in_workspace(c.workspace_id, c.id)
    assert reloaded is not None
    assert [r.id for r in reloaded.results] == order_before
    assert order_before == sorted(order_before)


async def test_delete_cascades_children(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow_del:
        repo_del = SQLAlchemyCampaignRepository(uow_del)
        await repo_del.delete(c.workspace_id, c.id)
        await uow_del.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        assert await repo_check.find_by_id(c.id) is None


async def test_update_existing_channel_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sanity: editing an existing channel's label persists via cascade."""
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow_edit:
        repo_edit = SQLAlchemyCampaignRepository(uow_edit)
        reloaded = await repo_edit.find_by_id(c.id)
        assert reloaded is not None
        reloaded.channels[0].label = "EC50"
        await repo_edit.save(reloaded)
        await uow_edit.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        again = await repo_check.find_by_id(c.id)
    assert again is not None
    assert again.channels[0].label == "EC50"


async def test_add_and_remove_channel_persists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(add_channel=False, add_result=False)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    # Add a channel
    new_ch_id: uuid.UUID
    async with AsyncUnitOfWork(session_factory) as uow_add:
        repo_add = SQLAlchemyCampaignRepository(uow_add)
        loaded = await repo_add.find_by_id(c.id)
        assert loaded is not None
        new_ch = CampaignChannel(
            campaign_id=loaded.id,
            label="EC50",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=1,
        )
        loaded.add_channel(new_ch)
        new_ch_id = new_ch.id
        await repo_add.save(loaded)
        await uow_add.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        again = await repo_check.find_by_id(c.id)
    assert again is not None
    assert len(again.channels) == 1
    assert again.channels[0].label == "EC50"

    # Remove it
    async with AsyncUnitOfWork(session_factory) as uow_rm:
        repo_rm = SQLAlchemyCampaignRepository(uow_rm)
        loaded2 = await repo_rm.find_by_id(c.id)
        assert loaded2 is not None
        loaded2.remove_channel(new_ch_id)
        await repo_rm.save(loaded2)
        await uow_rm.commit()

    async with AsyncUnitOfWork(session_factory) as uow_final:
        repo_final = SQLAlchemyCampaignRepository(uow_final)
        final = await repo_final.find_by_id(c.id)
    assert final is not None
    assert final.channels == []


async def test_stage_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(stage_name="Primary hits")
    channel_id = c.channels[0].id
    stage = c.stages[0]
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        reloaded = await repo2.find_by_id(c.id)
    assert reloaded is not None
    assert len(reloaded.stages) == 1
    rs = reloaded.stages[0]
    assert rs.id == stage.id
    assert rs.name == "Primary hits"
    assert rs.display_order == 0
    assert rs.parent_stage_id is None
    assert rs.kind == StageKind.CRITERIA
    assert len(rs.criteria) == 1
    assert rs.criteria[0].channel_id == channel_id
    assert rs.criteria[0].operator == "lt"
    assert rs.criteria[0].value == 5.0


async def test_manual_stage_round_trips_kind(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    stage = CampaignStage(
        campaign_id=c.id,
        name="Manual triage",
        display_order=0,
        kind=StageKind.MANUAL,
    )
    c.add_stage(stage)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        reloaded = await repo2.find_by_id(c.id)
    assert reloaded is not None
    assert reloaded.stages[0].kind == StageKind.MANUAL
    assert reloaded.stages[0].criteria == []

    # ... and the reconcile path (existing model row) persists a kind switch
    async with AsyncUnitOfWork(session_factory) as uow_edit:
        repo_edit = SQLAlchemyCampaignRepository(uow_edit)
        editable = await repo_edit.find_by_id(c.id)
        assert editable is not None
        editable.update_stage(stage.id, kind=StageKind.CRITERIA)
        await repo_edit.save(editable)
        await uow_edit.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        again = await repo_check.find_by_id(c.id)
    assert again is not None
    assert again.stages[0].kind == StageKind.CRITERIA


async def test_stage_rename_and_criteria_replace_reconciles(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(stage_name="Primary hits")
    channel_id = c.channels[0].id
    stage = c.stages[0]
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow_edit:
        repo_edit = SQLAlchemyCampaignRepository(uow_edit)
        reloaded = await repo_edit.find_by_id(c.id)
        assert reloaded is not None
        reloaded.update_stage(
            stage.id,
            name="Renamed hits",
            criteria=[StageCriterion(channel_id=channel_id, operator="gte", value=9.0)],
        )
        await repo_edit.save(reloaded)
        await uow_edit.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        again = await repo_check.find_by_id(c.id)
    assert again is not None
    assert len(again.stages) == 1
    rs = again.stages[0]
    assert rs.name == "Renamed hits"
    assert len(rs.criteria) == 1
    assert rs.criteria[0].operator == "gte"
    assert rs.criteria[0].value == 9.0


async def test_stage_override_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(stage_name="Primary hits")
    stage = c.stages[0]
    result = c.results[0]
    overridden_by = uuid.uuid4()
    result.set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.HIT,
        reason="manual review",
        overridden_by=overridden_by,
    )
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        reloaded = await repo2.find_by_id(c.id)
    assert reloaded is not None
    rr = reloaded.results[0]
    assert stage.id in rr.stage_overrides
    ov = rr.stage_overrides[stage.id]
    assert ov.forced_outcome == StageOutcome.HIT
    assert ov.reason == "manual review"
    assert ov.overridden_by == overridden_by
    assert ov.result_id == rr.id
    assert ov.stage_id == stage.id


async def test_stage_override_removal_reconciles(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(stage_name="Primary hits")
    stage = c.stages[0]
    result = c.results[0]
    result.set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.MISS,
        reason="manual review",
        overridden_by=uuid.uuid4(),
    )
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow_rm:
        repo_rm = SQLAlchemyCampaignRepository(uow_rm)
        reloaded = await repo_rm.find_by_id(c.id)
        assert reloaded is not None
        removed = reloaded.results[0].clear_stage_override(stage.id)
        assert removed is True
        await repo_rm.save(reloaded)
        await uow_rm.commit()

    async with AsyncUnitOfWork(session_factory) as uow_check:
        repo_check = SQLAlchemyCampaignRepository(uow_check)
        again = await repo_check.find_by_id(c.id)
    assert again is not None
    assert again.results[0].stage_overrides == {}


@pytest.mark.asyncio
async def test_channel_resolve_from_all_runs_round_trips(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The run-scope opt-out (spec D4) survives insert, reload, and update."""
    c = _build_campaign(add_result=False, add_measurement=False)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        assert loaded.channels[0].resolve_from_all_runs is False  # column default
        loaded.channels[0].resolve_from_all_runs = True
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        again = await repo.find_by_id(c.id)
    assert again is not None
    assert again.channels[0].resolve_from_all_runs is True


@pytest.mark.asyncio
async def test_seed_runs_round_trip_in_recorded_order(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The campaign's seed runs (spec D4) survive insert, reload, and append."""
    c = _build_campaign(add_result=False, add_measurement=False)
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    c.add_runs_to_stage([SeedRun(r2, p1), SeedRun(r1, p2)], None)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        assert loaded.seed_runs == [SeedRun(r2, p1), SeedRun(r1, p2)]
        loaded.add_runs_to_stage([SeedRun(r3, p1), SeedRun(r2, p1)], None)  # r2 already there
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        again = await repo.find_by_id(c.id)
    assert again is not None
    assert again.seed_runs == [SeedRun(r2, p1), SeedRun(r1, p2), SeedRun(r3, p1)]
    assert again.campaign_run_ids(p1) == [r2, r3]


async def test_stage_owned_fields_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Migration 104: a column's stage and test concentration, a run's stages and a
    cell's facts survive insert, reload, and update."""
    c = _build_campaign(stage_name="Primary hits")
    stage = c.stages[0]
    ch = c.channels[0]
    ch.test_concentration = Concentration(10.0, "µM")
    run, protocol = uuid.uuid4(), ch.protocol_id
    c.add_runs_to_stage([SeedRun(run, protocol)], stage.id)
    batch = uuid.uuid4()
    m = c.results[0].measurements[0]
    m.batch_ids = [batch]
    m.basis = MeasurementBasis.MIXED
    m.concentration_series = True
    m.unresolved_reason = UnresolvedReason.SEVERAL_CONCENTRATIONS
    m.concentrations_found = [Concentration(1.0, "µM"), Concentration(10.0, "µg/mL")]
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        assert loaded.channels[0].stage_id == stage.id
        assert loaded.channels[0].test_concentration == Concentration(10.0, "µM")
        assert loaded.seed_runs == [SeedRun(run, protocol, (stage.id,))]
        lm = loaded.results[0].measurements[0]
        assert lm.batch_ids == [batch]
        assert lm.basis == MeasurementBasis.MIXED
        assert lm.concentration_series is True
        assert lm.unresolved_reason == UnresolvedReason.SEVERAL_CONCENTRATIONS
        assert lm.concentrations_found == [
            Concentration(1.0, "µM"),
            Concentration(10.0, "µg/mL"),
        ]
        # ... and the reconcile path (existing rows) writes them too
        loaded.channels[0].test_concentration = None
        loaded.remove_run_from_stage(stage.id, run)
        lm.batch_ids = None
        lm.basis = MeasurementBasis.REPORTED
        lm.concentration_series = False
        lm.unresolved_reason = None
        lm.concentrations_found = None
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        again = await SQLAlchemyCampaignRepository(uow).find_by_id(c.id)
    assert again is not None
    assert again.channels[0].stage_id == stage.id
    assert again.channels[0].test_concentration is None
    assert again.seed_runs == [SeedRun(run, protocol, ())]
    am = again.results[0].measurements[0]
    assert (am.batch_ids, am.basis, am.concentration_series) == (
        None,
        MeasurementBasis.REPORTED,
        False,
    )
    assert (am.unresolved_reason, am.concentrations_found) == (None, None)
    async with session_factory() as s:
        sql_nulls = (
            await s.execute(
                text(
                    "SELECT (SELECT test_concentration IS NULL"
                    "          FROM campaign_channel WHERE id = :ch),"
                    "       (SELECT concentrations_found IS NULL"
                    "          FROM campaign_measurement WHERE id = :m)"
                ),
                {"ch": ch.id, "m": m.id},
            )
        ).one()
    assert tuple(sql_nulls) == (True, True)  # SQL NULL, not JSON 'null'


async def test_a_campaign_column_has_no_stage_and_a_fresh_cell_no_facts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(c)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        loaded = await SQLAlchemyCampaignRepository(uow).find_by_id(c.id)
    assert loaded is not None
    assert loaded.channels[0].stage_id is None
    assert loaded.channels[0].test_concentration is None
    m = loaded.results[0].measurements[0]
    assert (m.batch_ids, m.basis, m.concentration_series) == (None, None, False)
    assert (m.unresolved_reason, m.concentrations_found) == (None, None)


async def test_removing_a_stage_that_owns_columns_persists(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Spec §9: removing a stage removes its columns, their cells and its overrides,
    and its id from every run's stages, in one save; the run and the campaign's
    other columns stay."""
    c = _build_campaign(stage_name="Primary")
    stage, owned = c.stages[0], c.channels[0]
    other = CampaignChannel(
        campaign_id=c.id,
        label="Counter-screen",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=1,
    )
    c.add_channel(other)
    result = c.results[0]
    result.add_measurement(
        CampaignMeasurement(
            result_id=result.id,
            channel_id=other.id,
            value=7.0,
            value_qualifier=ValueQualifier.EQ,
            unit="%",
            protocol_name_snapshot="Counter",
            protocol_version_snapshot=1,
        )
    )
    result.set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.HIT,
        reason="kept by hand",
        overridden_by=uuid.uuid4(),
    )
    run = uuid.uuid4()
    c.add_runs_to_stage([SeedRun(run, owned.protocol_id)], stage.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        loaded.remove_stage(stage.id)
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        again = await SQLAlchemyCampaignRepository(uow).find_by_id(c.id)
    assert again is not None
    assert again.stages == []
    assert [ch.id for ch in again.channels] == [other.id]
    assert again.seed_runs == [SeedRun(run, owned.protocol_id, ())]
    [row] = again.results
    assert [m.channel_id for m in row.measurements] == [other.id]
    assert row.stage_overrides == {}
    async with session_factory() as s:
        left = (
            await s.execute(
                text(
                    "SELECT (SELECT count(*) FROM campaign_channel WHERE id = :ch),"
                    "       (SELECT count(*) FROM campaign_measurement WHERE channel_id = :ch),"
                    "       (SELECT count(*) FROM campaign_stage WHERE id = :stage)"
                ),
                {"ch": owned.id, "stage": stage.id},
            )
        ).one()
    assert tuple(left) == (0, 0, 0)


_DAIKON = CampaignManagement(
    managed_by="daikon", url="http://localhost:3002/screens/S1?round=R1", label="Daikon"
)


async def test_management_round_trips_and_clears(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign(add_channel=False)
    c.set_management(_DAIKON, user_id=None)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id_in_workspace(c.workspace_id, c.id)
        assert loaded is not None and loaded.management == _DAIKON
        loaded.release_management(reason="round abandoned", user_id=None)
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        released = await SQLAlchemyCampaignRepository(uow).find_by_id_in_workspace(
            c.workspace_id, c.id
        )
    assert released is not None and released.management is None


async def test_find_management_is_workspace_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    managed = _build_campaign(add_channel=False)
    managed.set_management(_DAIKON, user_id=None)
    plain = _build_campaign(add_channel=False)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(managed)
        await repo.save(plain)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        assert await repo.find_management(managed.workspace_id, managed.id) == _DAIKON
        assert await repo.find_management(plain.workspace_id, plain.id) is None
        assert await repo.find_management(uuid.uuid4(), managed.id) is None


async def test_measurement_qc_verdict_round_trips(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    m = c.results[0].measurements[0]
    by, at = uuid.uuid4(), datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
    m.qc_verdict, m.qc_verdict_by, m.qc_verdict_at, m.qc_verdict_note = (
        QcVerdict.VERIFIED,
        by,
        at,
        "clean curve",
    )
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(c)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        lm = loaded.results[0].measurements[0]
        assert (lm.qc_verdict, lm.qc_verdict_by, lm.qc_verdict_at, lm.qc_verdict_note) == (
            QcVerdict.VERIFIED,
            by,
            at,
            "clean curve",
        )
        lm.qc_verdict = lm.qc_verdict_by = lm.qc_verdict_at = lm.qc_verdict_note = None
        await repo.save(loaded)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        again = await SQLAlchemyCampaignRepository(uow).find_by_id(c.id)
    assert again is not None
    am = again.results[0].measurements[0]
    assert (am.qc_verdict, am.qc_verdict_by, am.qc_verdict_at, am.qc_verdict_note) == (
        None,
        None,
        None,
        None,
    )
