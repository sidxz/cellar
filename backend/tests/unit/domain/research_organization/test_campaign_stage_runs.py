import uuid

import pytest

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
)
from cellar.domain.research_organization.source_ref import SeedRun
from cellar.domain.shared.errors import NotFoundError, ValidationError

P1, P2 = uuid.uuid4(), uuid.uuid4()


def _campaign() -> Campaign:
    return Campaign.create(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )


def _stage(c: Campaign, name: str) -> CampaignStage:
    s = CampaignStage(campaign_id=c.id, name=name, display_order=0)
    c.add_stage(s)
    return s


def _channel(c: Campaign, stage_id=None) -> CampaignChannel:
    ch = CampaignChannel(
        campaign_id=c.id,
        label="IC50",
        protocol_id=P1,
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        stage_id=stage_id,
    )
    c.add_channel(ch)
    return ch


def _run(protocol=P1) -> SeedRun:
    return SeedRun(uuid.uuid4(), protocol)


def test_add_runs_to_stage_unions_stage_ids():
    c = _campaign()
    s = _stage(c, "A")
    r = _run()
    c.add_runs_to_stage([r], None)
    assert c.seed_runs[0].stage_ids == ()
    c.add_runs_to_stage([r], s.id)
    c.add_runs_to_stage([r], s.id)
    assert c.seed_runs == [SeedRun(r.run_id, P1, (s.id,))]


def test_add_runs_to_unknown_stage_rejected():
    with pytest.raises(NotFoundError):
        _campaign().add_runs_to_stage([_run()], uuid.uuid4())


def test_same_run_two_stages():
    c = _campaign()
    a, b = _stage(c, "A"), _stage(c, "B")
    r = _run()
    c.add_runs_to_stage([r], a.id)
    c.add_runs_to_stage([r], b.id)
    assert len(c.seed_runs) == 1
    assert c.seed_runs[0].stage_ids == (a.id, b.id)
    assert c.stage_run_ids(a.id, P1) == c.stage_run_ids(b.id, P1) == [r.run_id]


def test_remove_run_from_stage_keeps_run_in_campaign():
    c = _campaign()
    a = _stage(c, "A")
    r = _run()
    c.add_runs_to_stage([r], a.id)
    c.remove_run_from_stage(a.id, r.run_id)
    assert c.stage_run_ids(a.id, P1) == []
    assert c.campaign_run_ids(P1) == [r.run_id]
    with pytest.raises(NotFoundError):
        c.remove_run_from_stage(uuid.uuid4(), r.run_id)


def test_remove_unknown_run_is_noop():
    c = _campaign()
    a = _stage(c, "A")
    r = _run()
    c.add_runs_to_stage([r], a.id)
    before = (list(c.seed_runs), c.updated_at)
    c.remove_run_from_stage(a.id, uuid.uuid4())
    assert (c.seed_runs, c.updated_at) == before


def test_stage_run_ids_filters_by_stage_and_protocol():
    c = _campaign()
    a, b = _stage(c, "A"), _stage(c, "B")
    r1, r2, r3 = _run(P1), _run(P2), _run(P1)
    c.add_runs_to_stage([r1, r2], a.id)
    c.add_runs_to_stage([r3], b.id)
    assert c.stage_run_ids(a.id, P1) == [r1.run_id]
    assert c.stage_run_ids(a.id, P2) == [r2.run_id]
    assert c.stage_run_ids(b.id, P1) == [r3.run_id]
    assert c.campaign_run_ids(P1) == [r1.run_id, r3.run_id]


def test_criterion_on_other_stage_column_rejected():
    c = _campaign()
    a, b = _stage(c, "A"), _stage(c, "B")
    ch = _channel(c, a.id)
    with pytest.raises(ValidationError, match="belongs to another stage"):
        c.update_stage(b.id, criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=1.0)])


def test_criterion_on_campaign_column_rejected():
    c = _campaign()
    a = _stage(c, "A")
    ch = _channel(c)
    with pytest.raises(ValidationError, match="belongs to another stage"):
        c.update_stage(a.id, criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=1.0)])


def test_criterion_on_own_column_accepted():
    c = _campaign()
    a = _stage(c, "A")
    ch = _channel(c, a.id)
    c.update_stage(a.id, criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=1.0)])
    assert c.channels_of_stage(a.id) == [ch]


def test_remove_stage_removes_its_columns_and_memberships():
    c = _campaign()
    a, b = _stage(c, "A"), _stage(c, "B")
    ca, cb = _channel(c, a.id), _channel(c, b.id)
    r = _run()
    c.add_runs_to_stage([r], a.id)
    c.add_runs_to_stage([r], b.id)
    c.remove_stage(a.id)
    assert c.channels == [cb]
    assert c.seed_runs[0].stage_ids == (b.id,)
    assert ca not in c.channels


def test_add_channel_unknown_stage_rejected():
    c = _campaign()
    with pytest.raises(ValidationError, match="not a stage"):
        _channel(c, uuid.uuid4())
