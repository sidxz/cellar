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
from cellar.domain.research_organization.source_ref import CollectionRef
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
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
        publishes_collection=True,
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
            signature_id=uuid.uuid4(),
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
