"""recompute_columns — every campaign value is written by the bulk column resolver.

One candidate query per column per call (never per cell), manual overrides never
rewritten, measurement ids kept, and a stage column with no runs at its stage left
untested without querying (spec §6.3).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.research_organization.close_campaign import (
    CloseCampaign,
    CloseCampaignCommand,
)
from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSources,
    RefreshFromSourcesCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import SeedRun
from tests.unit.application.research_organization._helpers import (
    FakeColumnQuery,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

PROTO = uuid.uuid4()


def _campaign(n_results: int = 2) -> Campaign:
    c = Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )
    for _ in range(n_results):
        c.add_result(CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4()))
    return c


def _column(c: Campaign, *, stage_id: uuid.UUID | None = None, order: int = 0) -> CampaignChannel:
    ch = CampaignChannel(
        campaign_id=c.id,
        label=f"L{order}",
        protocol_id=PROTO,
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=order,
        stage_id=stage_id,
    )
    c.add_channel(ch)
    return ch


def _stage(c: Campaign) -> CampaignStage:
    s = CampaignStage(campaign_id=c.id, name="Primary", display_order=0)
    c.add_stage(s)
    return s


def _cell(result: CampaignResult, ch: CampaignChannel, *, override: bool = False):
    m = CampaignMeasurement(
        result_id=result.id,
        channel_id=ch.id,
        value=10.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )
    if override:
        m.mark_manual_override("bench check")
    result.add_measurement(m)
    return m


@pytest.mark.asyncio
async def test_recompute_skips_manual_overrides():
    c = _campaign()
    ch = _column(c)
    kept, fresh = c.results
    override = _cell(kept, ch, override=True)
    old = _cell(fresh, ch)
    query = FakeColumnQuery(99.0)

    written = await recompute_columns(query=query, campaign=c, channels=[ch])

    assert written == 1
    assert kept.find_measurement(ch.id) is override
    assert override.value == 10.0
    # The override's molecule is never even fetched.
    assert query.calls == [(ch.id, None, [fresh.molecule_id])]
    replaced = fresh.find_measurement(ch.id)
    assert replaced.value == 99.0
    assert replaced.id == old.id  # UPDATE, never DELETE + INSERT
    assert len(fresh.measurements) == 1


@pytest.mark.asyncio
async def test_recompute_stage_column_without_runs_is_no_runs_at_stage():
    c = _campaign()
    stage = _stage(c)
    ch = _column(c, stage_id=stage.id)
    # A campaign run of the column's protocol at no stage: never a fallback.
    c.add_runs_to_stage([SeedRun(uuid.uuid4(), PROTO)], None)
    kept, untested = c.results
    override = _cell(kept, ch, override=True)
    old = _cell(untested, ch)
    query = FakeColumnQuery(99.0)

    written = await recompute_columns(query=query, campaign=c, channels=[ch])

    assert written == 1
    assert query.calls == []
    assert kept.find_measurement(ch.id) is override
    m = untested.find_measurement(ch.id)
    assert m.id == old.id
    assert m.value is None and m.value_qualifier == ValueQualifier.ND
    assert m.unresolved_reason == UnresolvedReason.NO_RUNS_AT_STAGE
    assert m.source_run_id is None and m.curve_snapshot is None


@pytest.mark.asyncio
async def test_recompute_one_query_per_column():
    c = _campaign(n_results=3)
    columns = [_column(c, order=0), _column(c, order=1)]
    mols = [r.molecule_id for r in c.results]
    query = FakeColumnQuery(99.0)

    written = await recompute_columns(query=query, campaign=c, channels=columns)

    assert written == 6
    assert query.calls == [(ch.id, None, mols) for ch in columns]
    assert all(m.value == 99.0 for r in c.results for m in r.measurements)


@pytest.mark.asyncio
async def test_recompute_named_molecules_only():
    """New rows: one fetch per column for the whole batch, other rows untouched."""
    c = _campaign(n_results=3)
    ch = _column(c)
    old_row, *new_rows = c.results
    _cell(old_row, ch)
    query = FakeColumnQuery(99.0)

    written = await recompute_columns(
        query=query, campaign=c, channels=[ch], molecule_ids=[r.molecule_id for r in new_rows]
    )

    assert written == 2
    assert query.calls == [(ch.id, None, [r.molecule_id for r in new_rows])]
    assert old_row.find_measurement(ch.id).value == 10.0
    assert [r.find_measurement(ch.id).value for r in new_rows] == [99.0, 99.0]


def _stage_scoped_campaign() -> tuple[Campaign, CampaignChannel, uuid.UUID]:
    """A stage column whose protocol has a run at its stage and a campaign run at none."""
    c = _campaign(n_results=1)
    stage = _stage(c)
    ch = _column(c, stage_id=stage.id)
    at_stage = uuid.uuid4()
    c.add_runs_to_stage([SeedRun(at_stage, PROTO)], stage.id)
    c.add_runs_to_stage([SeedRun(uuid.uuid4(), PROTO)], None)
    _cell(c.results[0], ch)
    return c, ch, at_stage


@pytest.mark.asyncio
async def test_refresh_uses_stage_scope():
    auth = fake_auth()
    c, ch, at_stage = _stage_scoped_campaign()
    query = FakeColumnQuery(99.0)
    uc = RefreshFromSources(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=c),
        query=query,
        dispatcher=AsyncMock(),
    )

    out = await uc(
        RefreshFromSourcesCommand(workspace_id=auth.workspace_id, campaign_id=c.id), auth=auth
    )

    assert isinstance(out, Success)
    assert query.run_ids_seen == [[at_stage]]
    assert c.results[0].find_measurement(ch.id).value == 99.0


@pytest.mark.asyncio
async def test_close_uses_stage_scope():
    auth = fake_auth()
    c, ch, at_stage = _stage_scoped_campaign()
    query = FakeColumnQuery(99.0)
    protocol_repo = AsyncMock()
    protocol_repo.find_by_ids = AsyncMock(return_value=[])
    protocol_repo.find_effective_targets_for_protocols = AsyncMock(return_value={})
    uc = CloseCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=c),
        protocol_repo=protocol_repo,
        query=query,
        dispatcher=AsyncMock(),
    )

    out = await uc(
        CloseCampaignCommand(
            workspace_id=auth.workspace_id, campaign_id=c.id, user_id=auth.user_id
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    assert query.run_ids_seen == [[at_stage]]
    assert c.results[0].find_measurement(ch.id).value == 99.0
