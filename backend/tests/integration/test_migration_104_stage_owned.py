"""Migration 104: existing campaigns become stage-owned (spec §11 steps 1-5).

Each test seeds a pre-104 campaign (every column campaign-level, seed runs without
stages), runs 104's downgrade then upgrade on one connection, checks the result and
rolls everything back.

The legacy campaign (closed, so the data steps must get past the lock triggers):

    S1 Primary  (root)       criteria: A < 10
    S2 Confirm  (under S1)   criteria: A < 5, B < 1
    S3 Triage   (under S2)   manual
    A on P1 — named by S1 and S2: moves to S1, cloned for S2
    B on P2 — named by S2 only: moves to S2; P2 has no seed run
    C on P3 — named by nobody: stays a campaign column
    seed runs: r1 on P1, r3 on P3
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    StageKind,
    StageOutcome,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.research_organization.stage_evaluation import (
    evaluate_stages,
    tally_stage_counts,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M104 = Path(__file__).parents[2] / "alembic" / "versions" / "104_stage_owned_campaign_values.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m104", _M104)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class Legacy:
    campaign_id: uuid.UUID
    s1: uuid.UUID
    s2: uuid.UUID
    s3: uuid.UUID
    a: uuid.UUID
    b: uuid.UUID
    c: uuid.UUID
    p1: uuid.UUID
    p2: uuid.UUID
    p3: uuid.UUID
    r1: uuid.UUID
    r3: uuid.UUID


@pytest.fixture
async def tx(engine: AsyncEngine) -> AsyncIterator[tuple[AsyncConnection, async_sessionmaker]]:
    """One connection, one transaction rolled back at the end; sessions use savepoints."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield conn, factory
        await outer.rollback()


def _channel(cid: uuid.UUID, label: str, protocol: uuid.UUID, order: int) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=cid,
        label=label,
        protocol_id=protocol,
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=order,
        qc_filter={"z_prime_min": 0.5},
        normalization_applied="percent_inhibition",
    )


def _cell(result: CampaignResult, channel: CampaignChannel, value: float) -> None:
    result.add_measurement(
        CampaignMeasurement(
            result_id=result.id,
            channel_id=channel.id,
            value=value,
            value_qualifier=ValueQualifier.EQ,
            unit="µM",
            protocol_name_snapshot="P",
            protocol_version_snapshot=1,
            replicate_count=3,
        )
    )


async def _seed_legacy(conn: AsyncConnection, factory: async_sessionmaker) -> Legacy:
    """The pre-104 shape, which the domain no longer builds: criteria on campaign
    columns. Built through the constructor, saved draft, then closed in SQL."""
    cid = uuid.uuid4()
    p1, p2, p3, r1, r3 = (uuid.uuid4() for _ in range(5))
    a, b, c = _channel(cid, "A", p1, 0), _channel(cid, "B", p2, 1), _channel(cid, "C", p3, 2)
    s1 = CampaignStage(
        campaign_id=cid,
        name="Primary",
        display_order=0,
        criteria=[StageCriterion(channel_id=a.id, operator="lt", value=10.0)],
    )
    s2 = CampaignStage(
        campaign_id=cid,
        name="Confirm",
        display_order=1,
        parent_stage_id=s1.id,
        criteria=[
            StageCriterion(channel_id=a.id, operator="lt", value=5.0),
            StageCriterion(channel_id=b.id, operator="lt", value=1.0),
        ],
    )
    s3 = CampaignStage(
        campaign_id=cid,
        name="Triage",
        display_order=2,
        parent_stage_id=s2.id,
        kind=StageKind.MANUAL,
    )
    results = [CampaignResult(campaign_id=cid, molecule_id=uuid.uuid4()) for _ in range(4)]
    for result, (va, vb) in zip(
        results, [(3.0, 0.5), (7.0, 0.5), (20.0, 0.5), (None, 0.5)], strict=True
    ):
        if va is not None:
            _cell(result, a, va)
        _cell(result, b, vb)
        _cell(result, c, 1.0)
    results[1].set_stage_override(
        stage_id=s2.id,
        forced_outcome=StageOutcome.HIT,
        reason="kept by hand",
        overridden_by=uuid.uuid4(),
    )
    campaign = Campaign(
        id=cid,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name=f"legacy-{cid.hex[:6]}",
        created_by=uuid.uuid4(),
        channels=[a, b, c],
        stages=[s1, s2, s3],
        results=results,
        seed_runs=[SeedRun(r1, p1), SeedRun(r3, p3)],
    )
    async with AsyncUnitOfWork(factory) as uow:
        await SQLAlchemyCampaignRepository(uow).save(campaign)
        await uow.commit()
    await conn.execute(
        sa.text("UPDATE campaign SET status = 'closed' WHERE id = :id"), {"id": cid}
    )
    return Legacy(cid, s1.id, s2.id, s3.id, a.id, b.id, c.id, p1, p2, p3, r1, r3)


async def _migrate(conn: AsyncConnection) -> None:
    m104 = _load()

    def run(sync_conn):  # type: ignore[no-untyped-def]
        # The test schema is built at head; step back to the pre-104 shape first.
        with Operations.context(MigrationContext.configure(sync_conn)):
            m104.downgrade()
            m104.upgrade()

    await conn.run_sync(run)


async def _load_campaign(factory: async_sessionmaker, cid: uuid.UUID) -> Campaign:
    async with AsyncUnitOfWork(factory) as uow:
        campaign = await SQLAlchemyCampaignRepository(uow).find_by_id(cid)
    assert campaign is not None
    return campaign


async def test_migration_104_moves_referenced_column(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    after = await _load_campaign(factory, legacy.campaign_id)
    channels = {ch.id: ch for ch in after.channels}
    assert channels[legacy.a].stage_id == legacy.s1
    assert channels[legacy.b].stage_id == legacy.s2
    s1 = after.find_stage(legacy.s1)
    assert s1 is not None
    assert [cr.channel_id for cr in s1.criteria] == [legacy.a]


async def test_migration_104_clones_shared_column(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    after = await _load_campaign(factory, legacy.campaign_id)
    original = next(ch for ch in after.channels if ch.id == legacy.a)
    [clone] = [ch for ch in after.channels if ch.id not in {legacy.a, legacy.b, legacy.c}]
    assert clone.stage_id == legacy.s2
    same = (
        "label",
        "protocol_id",
        "readout_definition_id",
        "source_kind",
        "selection_rule",
        "qualifier_handling",
        "display_order",
        "qc_filter",
        "normalization_applied",
        "intercept_key",
        "resolve_from_all_runs",
    )
    assert {f: getattr(clone, f) for f in same} == {f: getattr(original, f) for f in same}
    s2 = after.find_stage(legacy.s2)
    assert s2 is not None
    assert [(cr.channel_id, cr.value) for cr in s2.criteria] == [(clone.id, 5.0), (legacy.b, 1.0)]
    for result in after.results:
        src, copy = result.find_measurement(legacy.a), result.find_measurement(clone.id)
        if src is None:
            assert copy is None
            continue
        assert copy is not None and copy.id != src.id
        assert (copy.value, copy.unit, copy.replicate_count) == (src.value, "µM", 3)
    # The lock triggers are back on after the data steps.
    enabled = (
        await conn.execute(
            sa.text(
                "SELECT tgenabled::text FROM pg_trigger WHERE tgname IN "
                "('campaign_stage_reject_locked', 'campaign_measurement_reject_locked')"
            )
        )
    ).scalars()
    assert sorted(enabled) == ["O", "O"]


async def test_migration_104_unreferenced_stays_campaign_column(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    after = await _load_campaign(factory, legacy.campaign_id)
    c = next(ch for ch in after.channels if ch.id == legacy.c)
    assert c.stage_id is None
    assert c.resolve_from_all_runs is False
    assert len(after.channels) == 4  # A, B, C and A's clone


async def test_migration_104_seed_run_stage_ids(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    after = await _load_campaign(factory, legacy.campaign_id)
    assert after.seed_runs == [
        SeedRun(legacy.r1, legacy.p1, (legacy.s1, legacy.s2)),  # A in S1, its clone in S2
        SeedRun(legacy.r3, legacy.p3, ()),  # P3 feeds a campaign column only
    ]


async def test_migration_104_unseeded_stage_column_keeps_protocol_wide(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    after = await _load_campaign(factory, legacy.campaign_id)
    flags = {ch.id: ch.resolve_from_all_runs for ch in after.channels if ch.stage_id}
    assert flags.pop(legacy.b) is True  # P2 has no seed run: it read protocol-wide
    assert set(flags.values()) == {False}  # A and its clone read r1


async def test_migration_104_tallies_identical(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)

    async def tally() -> dict[uuid.UUID, dict[str, int]]:
        campaign = await _load_campaign(factory, legacy.campaign_id)
        return tally_stage_counts(campaign, evaluate_stages(campaign))

    before = await tally()
    await _migrate(conn)
    assert await tally() == before
    assert before[legacy.s1]["hit"] == 2 and before[legacy.s1]["untested"] == 1
    assert before[legacy.s2]["hit"] == 2 and before[legacy.s2]["overridden"] == 1
    assert before[legacy.s3]["pending"] == 2


async def test_migration_104_downgrade_strips_stage_ids(tx) -> None:  # type: ignore[no-untyped-def]
    conn, factory = tx
    legacy = await _seed_legacy(conn, factory)
    await _migrate(conn)

    def down(sync_conn):  # type: ignore[no-untyped-def]
        with Operations.context(MigrationContext.configure(sync_conn)):
            _load().downgrade()
        seed_runs = sync_conn.execute(
            sa.text("SELECT seed_runs FROM campaign WHERE id = :id"), {"id": legacy.campaign_id}
        ).scalar_one()
        left = sync_conn.execute(
            sa.text(
                "SELECT count(*) FROM information_schema.columns WHERE "
                "(table_name = 'campaign_channel' AND column_name IN "
                "('stage_id', 'test_concentration')) OR (table_name = 'campaign_measurement' "
                "AND column_name IN ('batch_ids', 'basis', 'concentration_series', "
                "'unresolved_reason', 'concentrations_found'))"
            )
        ).scalar_one()
        return seed_runs, left

    seed_runs, left = await conn.run_sync(down)
    assert seed_runs == [
        {"run_id": str(legacy.r1), "protocol_id": str(legacy.p1)},
        {"run_id": str(legacy.r3), "protocol_id": str(legacy.p3)},
    ]
    assert left == 0
