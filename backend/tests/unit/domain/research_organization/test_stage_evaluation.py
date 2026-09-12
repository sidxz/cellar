"""Unit tests for stage_evaluation — evaluate_stages / tally_stage_counts.

Builds full Campaign graphs (channels, results, measurements, stages,
overrides) the way test_campaign.py does, then asserts on the computed
StageOutcomes. See docs/superpowers/specs/2026-09-11-campaign-hit-stages-and
-soft-close-spec.md §3.6 for the algorithm and the worked example this file
reproduces numerically.
"""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import (
    CampaignStage,
    StageCriterion,
)
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    CheckVerdict,
    QualifierHandling,
    SelectionRule,
    StageOutcome,
    ValueQualifier,
)
from cellar.domain.research_organization.stage_evaluation import (
    StageCheck,
    evaluate_stages,
    tally_stage_counts,
)

# ---------- fixture builders (mirrors test_campaign.py's _make_* helpers;
# these additionally attach the entity to the campaign since every test here
# needs a fully wired graph to evaluate) ----------


def _make_campaign(**overrides) -> Campaign:
    defaults = dict(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Stage Evaluation",
        description=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    return Campaign.create(**defaults)


def _make_channel(campaign: Campaign, **overrides) -> CampaignChannel:
    defaults = dict(
        campaign_id=campaign.id,
        label=f"Channel {uuid.uuid4()}",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    defaults.update(overrides)
    channel = CampaignChannel(**defaults)
    campaign.add_channel(channel)
    return channel


def _make_result(campaign: Campaign) -> CampaignResult:
    result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    campaign.add_result(result)
    return result


def _add_measurement(
    result: CampaignResult,
    channel: CampaignChannel,
    *,
    value: float | None,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    unit: str = "nM",
) -> CampaignMeasurement:
    m = CampaignMeasurement(
        result_id=result.id,
        channel_id=channel.id,
        value=value,
        value_qualifier=qualifier,
        unit=unit,
        protocol_name_snapshot="proto",
        protocol_version_snapshot=1,
    )
    result.add_measurement(m)
    return m


def _make_stage(campaign: Campaign, **overrides) -> CampaignStage:
    defaults = dict(
        campaign_id=campaign.id,
        name=f"Stage {uuid.uuid4()}",
        display_order=0,
    )
    defaults.update(overrides)
    stage = CampaignStage(**defaults)
    campaign.add_stage(stage)
    return stage


# ---------- AND semantics ----------


def test_and_semantics_all_pass_is_hit():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    stage = _make_stage(
        c,
        criteria=[
            StageCriterion(channel_id=ch1.id, operator="gte", value=50.0),
            StageCriterion(channel_id=ch2.id, operator="lt", value=10.0),
        ],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=60.0)
    _add_measurement(r, ch2, value=5.0)

    outcome = evaluate_stages(c)[r.id][stage.id]

    assert outcome.outcome == StageOutcome.HIT
    assert outcome.checks == (
        StageCheck(channel_id=ch1.id, verdict=CheckVerdict.PASS),
        StageCheck(channel_id=ch2.id, verdict=CheckVerdict.PASS),
    )


def test_and_semantics_one_fail_is_miss():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    stage = _make_stage(
        c,
        criteria=[
            StageCriterion(channel_id=ch1.id, operator="gte", value=50.0),
            StageCriterion(channel_id=ch2.id, operator="lt", value=10.0),
        ],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=60.0)  # passes
    _add_measurement(r, ch2, value=20.0)  # fails

    outcome = evaluate_stages(c)[r.id][stage.id]

    assert outcome.outcome == StageOutcome.MISS


# ---------- untested beats hit but not miss ----------


def test_untested_beats_hit():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    stage = _make_stage(
        c,
        criteria=[
            StageCriterion(channel_id=ch1.id, operator="gte", value=50.0),
            StageCriterion(channel_id=ch2.id, operator="lt", value=10.0),
        ],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=60.0)  # passes
    # ch2 has no measurement at all -> untested

    outcome = evaluate_stages(c)[r.id][stage.id]

    assert outcome.outcome == StageOutcome.UNTESTED


def test_untested_does_not_beat_miss():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    stage = _make_stage(
        c,
        criteria=[
            StageCriterion(channel_id=ch1.id, operator="gte", value=50.0),  # fails
            StageCriterion(channel_id=ch2.id, operator="lt", value=10.0),  # untested
        ],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=10.0)  # 10 >= 50 is False -> fail
    # ch2 has no measurement -> untested

    outcome = evaluate_stages(c)[r.id][stage.id]

    assert outcome.outcome == StageOutcome.MISS


# ---------- censored values / nd / excluded ----------


def test_censored_qualifier_compared_as_plain_number():
    c = _make_campaign()
    ch = _make_channel(c)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=10.0)])
    r = _make_result(c)
    _add_measurement(r, ch, value=5.0, qualifier=ValueQualifier.LT)  # reported as "< 5"

    outcome = evaluate_stages(c)[r.id][stage.id]

    # The qualifier symbol is ignored; 5.0 < 10.0 is what's compared.
    assert outcome.outcome == StageOutcome.HIT


def test_nd_and_excluded_qualifiers_are_untested():
    c = _make_campaign()
    ch = _make_channel(c)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="lt", value=10.0)])
    r_nd = _make_result(c)
    _add_measurement(r_nd, ch, value=None, qualifier=ValueQualifier.ND, unit="")
    r_excluded = _make_result(c)
    _add_measurement(r_excluded, ch, value=None, qualifier=ValueQualifier.EXCLUDED, unit="")

    outcomes = evaluate_stages(c)

    assert outcomes[r_nd.id][stage.id].outcome == StageOutcome.UNTESTED
    assert outcomes[r_excluded.id][stage.id].outcome == StageOutcome.UNTESTED


# ---------- root population ----------


def test_root_population_is_all_results():
    c = _make_campaign()
    ch = _make_channel(c)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)])
    r1 = _make_result(c)
    _add_measurement(r1, ch, value=60.0)  # hit
    r2 = _make_result(c)
    _add_measurement(r2, ch, value=10.0)  # miss
    _make_result(c)  # no measurement -> untested

    outcomes = evaluate_stages(c)
    counts = tally_stage_counts(c, outcomes)[stage.id]

    assert counts == {
        "population": 3,
        "hit": 1,
        "miss": 1,
        "untested": 1,
        "not_in_stage": 0,
        "overridden": 0,
    }


# ---------- parent-chain gating ----------


def test_child_not_in_stage_when_parent_miss():
    c = _make_campaign()
    ch = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)]
    )
    child = _make_stage(c, name="Child", parent_stage_id=parent.id, display_order=1)
    r = _make_result(c)
    _add_measurement(r, ch, value=10.0)  # parent misses

    outcomes = evaluate_stages(c)

    assert outcomes[r.id][parent.id].outcome == StageOutcome.MISS
    child_outcome = outcomes[r.id][child.id]
    assert child_outcome.outcome == StageOutcome.NOT_IN_STAGE
    assert child_outcome.checks == ()


def test_child_not_in_stage_when_parent_untested():
    c = _make_campaign()
    ch = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)]
    )
    child = _make_stage(c, name="Child", parent_stage_id=parent.id, display_order=1)
    r = _make_result(c)  # no measurement -> parent untested

    outcomes = evaluate_stages(c)

    assert outcomes[r.id][parent.id].outcome == StageOutcome.UNTESTED
    assert outcomes[r.id][child.id].outcome == StageOutcome.NOT_IN_STAGE


def test_child_evaluated_when_parent_hit():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch1.id, operator="gte", value=50.0)]
    )
    child = _make_stage(
        c,
        name="Child",
        parent_stage_id=parent.id,
        display_order=1,
        criteria=[StageCriterion(channel_id=ch2.id, operator="lt", value=10.0)],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=60.0)  # parent hits
    _add_measurement(r, ch2, value=20.0)  # child's own criterion fails

    outcomes = evaluate_stages(c)

    assert outcomes[r.id][parent.id].outcome == StageOutcome.HIT
    assert outcomes[r.id][child.id].outcome == StageOutcome.MISS  # evaluated, not not_in_stage


def test_branching_two_children_of_one_parent():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    ch3 = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch1.id, operator="gte", value=50.0)]
    )
    child_a = _make_stage(
        c,
        name="ChildA",
        parent_stage_id=parent.id,
        display_order=1,
        criteria=[StageCriterion(channel_id=ch2.id, operator="lt", value=10.0)],
    )
    child_b = _make_stage(
        c,
        name="ChildB",
        parent_stage_id=parent.id,
        display_order=2,
        criteria=[StageCriterion(channel_id=ch3.id, operator="lt", value=10.0)],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=60.0)  # parent hits
    _add_measurement(r, ch2, value=5.0)  # child_a passes
    _add_measurement(r, ch3, value=50.0)  # child_b fails

    outcomes = evaluate_stages(c)

    assert outcomes[r.id][child_a.id].outcome == StageOutcome.HIT
    assert outcomes[r.id][child_b.id].outcome == StageOutcome.MISS


def test_parent_listed_after_child_still_evaluated_first():
    c = _make_campaign()
    ch = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)]
    )
    child = _make_stage(c, name="Child", parent_stage_id=parent.id, display_order=1)
    # Reverse campaign.stages so the child is listed before its parent.
    c.stages = [child, parent]

    r = _make_result(c)
    _add_measurement(r, ch, value=60.0)  # parent hits

    outcomes = evaluate_stages(c)

    assert outcomes[r.id][parent.id].outcome == StageOutcome.HIT
    # zero-criteria child, evaluated on a hit parent -> hit.
    assert outcomes[r.id][child.id].outcome == StageOutcome.HIT


# ---------- overrides ----------


def test_override_forces_hit_and_feeds_child_population():
    c = _make_campaign()
    ch1 = _make_channel(c)
    ch2 = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch1.id, operator="gte", value=50.0)]
    )
    child = _make_stage(
        c,
        name="Child",
        parent_stage_id=parent.id,
        display_order=1,
        criteria=[StageCriterion(channel_id=ch2.id, operator="lt", value=10.0)],
    )
    r = _make_result(c)
    _add_measurement(r, ch1, value=10.0)  # parent would miss
    _add_measurement(r, ch2, value=5.0)  # would pass if the child were reached
    r.set_stage_override(
        stage_id=parent.id,
        forced_outcome=StageOutcome.HIT,
        reason="chemist call",
        overridden_by=uuid.uuid4(),
    )

    outcomes = evaluate_stages(c)

    parent_outcome = outcomes[r.id][parent.id]
    assert parent_outcome.outcome == StageOutcome.HIT
    assert parent_outcome.overridden is True
    assert parent_outcome.override_reason == "chemist call"
    child_outcome = outcomes[r.id][child.id]
    assert child_outcome.outcome == StageOutcome.HIT
    assert child_outcome.overridden is False


def test_override_on_not_in_stage_row():
    c = _make_campaign()
    ch = _make_channel(c)
    parent = _make_stage(
        c, name="Parent", criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)]
    )
    child = _make_stage(c, name="Child", parent_stage_id=parent.id, display_order=1)
    r = _make_result(c)
    _add_measurement(r, ch, value=10.0)  # parent misses -> child would be not_in_stage
    r.set_stage_override(
        stage_id=child.id,
        forced_outcome=StageOutcome.MISS,
        reason="reviewed manually",
        overridden_by=uuid.uuid4(),
    )

    outcomes = evaluate_stages(c)

    child_outcome = outcomes[r.id][child.id]
    assert child_outcome.outcome == StageOutcome.MISS
    assert child_outcome.overridden is True
    assert child_outcome.override_reason == "reviewed manually"
    assert child_outcome.checks == ()  # base was not_in_stage; override doesn't fabricate checks


# ---------- zero-criteria stage ----------


def test_zero_criteria_stage_is_hit_for_whole_population():
    c = _make_campaign()
    stage = _make_stage(c, name="Empty", criteria=[])
    r1 = _make_result(c)
    r2 = _make_result(c)

    outcomes = evaluate_stages(c)

    assert outcomes[r1.id][stage.id].outcome == StageOutcome.HIT
    assert outcomes[r2.id][stage.id].outcome == StageOutcome.HIT
    assert outcomes[r1.id][stage.id].checks == ()


# ---------- worked example (spec §3.6): 68 -> 12 -> 7/3/2/56 ----------


def test_worked_example_tally_matches_spec():
    c = _make_campaign()
    egfr = _make_channel(c, label="% Inhibition (EGFR)")
    ic50 = _make_channel(c, label="IC50 (NadD-Sumo)")
    screening = _make_stage(
        c,
        name="Screening Hits",
        criteria=[StageCriterion(channel_id=egfr.id, operator="gte", value=50.0)],
    )
    confirmed = _make_stage(
        c,
        name="Confirmed Hits",
        parent_stage_id=screening.id,
        display_order=1,
        criteria=[StageCriterion(channel_id=ic50.id, operator="lt", value=10.0)],
    )

    # 56 compounds miss screening -- never reach the IC50 channel.
    for _ in range(56):
        r = _make_result(c)
        _add_measurement(r, egfr, value=10.0, unit="%")

    # 12 compounds pass screening: 7 confirmed hit, 3 confirmed miss, 2 untested.
    for _ in range(7):
        r = _make_result(c)
        _add_measurement(r, egfr, value=80.0, unit="%")
        _add_measurement(r, ic50, value=5.0)
    for _ in range(3):
        r = _make_result(c)
        _add_measurement(r, egfr, value=80.0, unit="%")
        _add_measurement(r, ic50, value=20.0)
    for _ in range(2):
        r = _make_result(c)
        _add_measurement(r, egfr, value=80.0, unit="%")
        # no ic50 measurement -> untested

    assert len(c.results) == 68

    outcomes = evaluate_stages(c)
    counts = tally_stage_counts(c, outcomes)

    assert counts[screening.id] == {
        "population": 68,
        "hit": 12,
        "miss": 56,
        "untested": 0,
        "not_in_stage": 0,
        "overridden": 0,
    }
    assert counts[confirmed.id] == {
        "population": 12,
        "hit": 7,
        "miss": 3,
        "untested": 2,
        "not_in_stage": 56,
        "overridden": 0,
    }


# ---------- defensive guards: dangling parent / cycle (M-1) ----------
#
# Both scenarios are unreachable through the aggregate (Campaign.add_stage
# validates parent existence and walks the chain to refuse cycles) but not
# enforced by the FK (doesn't constrain the parent to the same campaign) or
# the DB — constructed here by mutating `campaign.stages` directly, the same
# way test_parent_listed_after_child_still_evaluated_first bypasses add_stage.


def test_dangling_parent_treated_as_root():
    c = _make_campaign()
    ch = _make_channel(c)
    orphan = CampaignStage(
        campaign_id=c.id,
        name="Orphan",
        display_order=0,
        parent_stage_id=uuid.uuid4(),  # no stage with this id exists anywhere
        criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)],
    )
    c.stages = [orphan]
    r = _make_result(c)
    _add_measurement(r, ch, value=60.0)

    outcomes = evaluate_stages(c)

    # No KeyError; the missing parent is treated as "always in stage".
    assert outcomes[r.id][orphan.id].outcome == StageOutcome.HIT


def test_cycle_guard_terminates_instead_of_recursing_forever():
    c = _make_campaign()
    ch = _make_channel(c)
    a = CampaignStage(
        campaign_id=c.id,
        name="A",
        display_order=0,
        criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)],
    )
    b = CampaignStage(campaign_id=c.id, name="B", display_order=1, parent_stage_id=a.id)
    a.parent_stage_id = b.id  # close the cycle: a -> b -> a
    c.stages = [a, b]
    r = _make_result(c)
    _add_measurement(r, ch, value=60.0)

    outcomes = evaluate_stages(c)

    # Terminates instead of RecursionError: the guard breaks the cycle by
    # treating whichever stage is re-entered as root, so b (no criteria)
    # resolves hit, and a's own (passing) criterion then also hits.
    assert outcomes[r.id][b.id].outcome == StageOutcome.HIT
    assert outcomes[r.id][a.id].outcome == StageOutcome.HIT
