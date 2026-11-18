"""RemoveRunFromStage: the run leaves the stage (it stays a run of the campaign), and
the stage's columns recompute over the runs it has left. Idempotent."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.recompute_columns import recompute_columns
from cellar.application.research_organization.remove_run_from_stage import (
    RemoveRunFromStage,
    RemoveRunFromStageCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    UnresolvedReason,
)
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.unit.application.research_organization._helpers import (
    FakeRunData,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
    reading,
)

PROTO, READOUT, MOL = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def _setup():
    """A stage with one run of MOL at 62 and a resolved column."""
    auth = fake_auth()
    c = Campaign.create(
        workspace_id=auth.workspace_id,
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )
    stage = CampaignStage(campaign_id=c.id, name="Primary", display_order=0)
    c.add_stage(stage)
    column = CampaignChannel(
        campaign_id=c.id,
        label="% inhibition",
        protocol_id=PROTO,
        readout_definition_id=READOUT,
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        stage_id=stage.id,
    )
    c.add_channel(column)
    c.add_result(CampaignResult(campaign_id=c.id, molecule_id=MOL))
    run = uuid.uuid4()
    c.add_runs_to_stage([SeedRun(run, PROTO)], stage.id)
    data = FakeRunData()
    data.add(READOUT, reading(MOL, 62.0, run))
    await recompute_columns(query=data, campaign=c, channels=[column])
    data.calls.clear()
    return auth, c, stage, column, run, data


def _uc(campaign, data, saved=None):
    return RemoveRunFromStage(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        query=data,
        dispatcher=AsyncMock(),
    )


def _cmd(auth, campaign, stage_id, run_id):
    return RemoveRunFromStageCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign.id,
        stage_id=stage_id,
        run_id=run_id,
    )


@pytest.mark.asyncio
async def test_removing_the_only_run_leaves_the_stage_untested() -> None:
    auth, c, stage, column, run, data = await _setup()
    saved: list = []

    out = await _uc(c, data, saved)(_cmd(auth, c, stage.id, run), auth=auth)

    assert isinstance(out, Success)
    assert c.seed_runs == [SeedRun(run, PROTO)]  # still a run of the campaign
    cell = c.results[0].find_measurement(column.id)
    assert cell.value is None
    assert cell.unresolved_reason == UnresolvedReason.NO_RUNS_AT_STAGE
    assert saved == [c]


@pytest.mark.asyncio
async def test_run_not_on_stage_is_a_noop() -> None:
    auth, c, stage, column, _run, data = await _setup()
    other = uuid.uuid4()
    c.add_runs_to_stage([SeedRun(other, PROTO)], None)
    saved: list = []

    for run_id in (other, uuid.uuid4()):  # a campaign run, and a run not in the campaign
        out = await _uc(c, data, saved)(_cmd(auth, c, stage.id, run_id), auth=auth)
        assert isinstance(out, Success)

    assert c.results[0].find_measurement(column.id).value == 62.0
    assert saved == []
    assert data.calls == []


@pytest.mark.asyncio
async def test_unknown_stage_is_not_found() -> None:
    auth, c, _stage, _column, run, data = await _setup()
    out = await _uc(c, data)(_cmd(auth, c, uuid.uuid4(), run), auth=auth)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_unknown_campaign_is_not_found() -> None:
    auth = fake_auth()
    uc = RemoveRunFromStage(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=None),
        query=FakeRunData(),
        dispatcher=AsyncMock(),
    )
    out = await uc(
        RemoveRunFromStageCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            stage_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        ),
        auth=auth,
    )
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_closed_campaign_is_rejected() -> None:
    auth, c, stage, _column, run, data = await _setup()
    c.status = CampaignStatus.CLOSED  # type: ignore[misc]
    out = await _uc(c, data)(_cmd(auth, c, stage.id, run), auth=auth)
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), ValidationError)
    assert stage.id in c.seed_runs[0].stage_ids


@pytest.mark.asyncio
async def test_viewer_is_refused() -> None:
    _auth, c, stage, _column, run, data = await _setup()
    viewer = fake_auth(role="viewer")
    with pytest.raises(AuthorizationError):
        await _uc(c, data)(_cmd(viewer, c, stage.id, run), auth=viewer)
