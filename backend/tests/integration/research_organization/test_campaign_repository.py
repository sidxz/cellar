"""Integration tests for SQLAlchemyCampaignRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    StageKind,
    StageOutcome,
    ValueQualifier,
)
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
) -> Campaign:
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
    if add_channel:
        ch = CampaignChannel(
            campaign_id=c.id,
            label="IC50",
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
            display_order=0,
        )
        c.add_channel(ch)
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
    c = _build_campaign()
    channel_id = c.channels[0].id
    stage = CampaignStage(
        campaign_id=c.id,
        name="Primary hits",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel_id, operator="lt", value=5.0)],
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
    c = _build_campaign()
    channel_id = c.channels[0].id
    stage = CampaignStage(
        campaign_id=c.id,
        name="Primary hits",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel_id, operator="lt", value=5.0)],
    )
    c.add_stage(stage)
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
    c = _build_campaign()
    channel_id = c.channels[0].id
    stage = CampaignStage(
        campaign_id=c.id,
        name="Primary hits",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel_id, operator="lt", value=5.0)],
    )
    c.add_stage(stage)
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
    c = _build_campaign()
    channel_id = c.channels[0].id
    stage = CampaignStage(
        campaign_id=c.id,
        name="Primary hits",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel_id, operator="lt", value=5.0)],
    )
    c.add_stage(stage)
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


async def test_close_note_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    c = _build_campaign()
    c.close_note = "closed after triage review"
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow2:
        repo2 = SQLAlchemyCampaignRepository(uow2)
        reloaded = await repo2.find_by_id(c.id)
    assert reloaded is not None
    assert reloaded.close_note == "closed after triage review"


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
    c.record_seed_runs([SeedRun(r2, p1), SeedRun(r1, p2)])
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        await repo.save(c)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        loaded = await repo.find_by_id(c.id)
        assert loaded is not None
        assert loaded.seed_runs == [SeedRun(r2, p1), SeedRun(r1, p2)]
        loaded.record_seed_runs([SeedRun(r3, p1), SeedRun(r2, p1)])  # r2 already there
        await repo.save(loaded)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        again = await repo.find_by_id(c.id)
    assert again is not None
    assert again.seed_runs == [SeedRun(r2, p1), SeedRun(r1, p2), SeedRun(r3, p1)]
    assert again.seed_run_ids_for(p1) == [r2, r3]
