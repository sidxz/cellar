"""Pure evaluator for CampaignStage funnels — no I/O, no persistence.

``evaluate_stages`` walks every (result, stage) pair and produces the verdict
a chemist sees on the campaign grid. Stages form a forest via
`CampaignStage.parent_stage_id`; a child is only "in play" for a compound
that is a `hit` on its parent (after any override), so parents must be
evaluated before their children. `evaluate_stages` recurses with a per-result
memo rather than relying on `campaign.stages` list order — see
`test_parent_listed_after_child_still_evaluated_first`.

Outcomes are never persisted (spec §7): recomputed on every read from the
live campaign, results, and stages.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import (
    CampaignStage,
    StageCriterion,
)
from cellar.domain.research_organization.enums import (
    CheckVerdict,
    StageOutcome,
    ValueQualifier,
)

_UNTESTED_QUALIFIERS = frozenset({ValueQualifier.ND, ValueQualifier.EXCLUDED})


@dataclass(frozen=True)
class StageCheck:
    """One criterion's verdict for one result."""

    channel_id: uuid.UUID
    verdict: CheckVerdict


@dataclass(frozen=True)
class StageResultOutcome:
    """One (result, stage) verdict — the combination of its checks, gated by
    the parent chain, and any manual override."""

    stage_id: uuid.UUID
    outcome: StageOutcome
    overridden: bool
    override_reason: str | None
    checks: tuple[StageCheck, ...]


#: result_id -> stage_id -> outcome
StageOutcomes = dict[uuid.UUID, dict[uuid.UUID, StageResultOutcome]]


def _check_criterion(result: CampaignResult, criterion: StageCriterion) -> StageCheck:
    measurement = result.find_measurement(criterion.channel_id)
    if (
        measurement is None
        or measurement.value_qualifier in _UNTESTED_QUALIFIERS
        or measurement.value is None
    ):
        return StageCheck(channel_id=criterion.channel_id, verdict=CheckVerdict.UNTESTED)
    # ponytail: censored values (`<`/`>` qualifiers) are compared by their
    # plain numeric value, same as the pre-stages `_compute_hit_call` did —
    # a reported "< 5" is just 5.0 against the criterion. The channel's
    # `qualifier_handling` (exclude/clamp) is the existing knob for callers
    # that want censored-aware filtering instead; upgrade here if a stage
    # ever needs to treat "< 5" as automatically meeting "< 10".
    verdict = CheckVerdict.PASS if criterion.is_met(measurement.value) else CheckVerdict.FAIL
    return StageCheck(channel_id=criterion.channel_id, verdict=verdict)


def _combine(checks: tuple[StageCheck, ...]) -> StageOutcome:
    verdicts = {c.verdict for c in checks}
    if CheckVerdict.FAIL in verdicts:
        return StageOutcome.MISS
    if CheckVerdict.UNTESTED in verdicts:
        return StageOutcome.UNTESTED
    return StageOutcome.HIT


def _evaluate_stage(
    stage: CampaignStage,
    result: CampaignResult,
    stages_by_id: dict[uuid.UUID, CampaignStage],
    memo: dict[uuid.UUID, StageResultOutcome],
) -> StageResultOutcome:
    cached = memo.get(stage.id)
    if cached is not None:
        return cached

    if stage.parent_stage_id is None:
        in_stage = True
    else:
        parent = stages_by_id[stage.parent_stage_id]
        parent_outcome = _evaluate_stage(parent, result, stages_by_id, memo)
        in_stage = parent_outcome.outcome == StageOutcome.HIT

    if in_stage:
        checks = tuple(_check_criterion(result, c) for c in stage.criteria)
        base_outcome = _combine(checks)
    else:
        checks = ()
        base_outcome = StageOutcome.NOT_IN_STAGE

    override = result.stage_overrides.get(stage.id)
    if override is None:
        outcome, overridden, override_reason = base_outcome, False, None
    else:
        outcome, overridden, override_reason = override.forced_outcome, True, override.reason

    outcome_result = StageResultOutcome(
        stage_id=stage.id,
        outcome=outcome,
        overridden=overridden,
        override_reason=override_reason,
        checks=checks,
    )
    memo[stage.id] = outcome_result
    return outcome_result


def evaluate_stages(campaign: Campaign) -> StageOutcomes:
    stages_by_id = {stage.id: stage for stage in campaign.stages}
    outcomes: StageOutcomes = {}
    for result in campaign.results:
        memo: dict[uuid.UUID, StageResultOutcome] = {}
        for stage in campaign.stages:
            _evaluate_stage(stage, result, stages_by_id, memo)
        outcomes[result.id] = memo
    return outcomes


def tally_stage_counts(
    campaign: Campaign, outcomes: StageOutcomes
) -> dict[uuid.UUID, dict[str, int]]:
    """Per-stage funnel counts. ``population = hit + miss + untested``; for a
    root stage that's every result (root outcomes are never `not_in_stage`)."""
    counts: dict[uuid.UUID, dict[str, int]] = {
        stage.id: {
            "population": 0,
            "hit": 0,
            "miss": 0,
            "untested": 0,
            "not_in_stage": 0,
            "overridden": 0,
        }
        for stage in campaign.stages
    }
    for result in campaign.results:
        for stage_id, outcome in outcomes.get(result.id, {}).items():
            bucket = counts.get(stage_id)
            if bucket is None:
                continue
            if outcome.outcome == StageOutcome.NOT_IN_STAGE:
                bucket["not_in_stage"] += 1
            else:
                bucket["population"] += 1
                bucket[outcome.outcome.value] += 1
            if outcome.overridden:
                bucket["overridden"] += 1
    return counts
