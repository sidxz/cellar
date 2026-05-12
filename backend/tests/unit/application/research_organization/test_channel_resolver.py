"""Unit tests for ChannelResolver — pure-domain selection/QC/hit logic."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from cellar.application.research_organization.channel_resolution import (
    ChannelResolver,
    ResolvedCandidate,
)
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.enums import (
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.screening_assay.hit_criterion import HitCriterion


class _FakeQuery:
    def __init__(self, candidates: list[ResolvedCandidate]) -> None:
        self._c = candidates

    async def fetch_candidates(self, *, workspace_id, channel, molecule_id):
        return list(self._c)


def _channel(
    rule: SelectionRule,
    *,
    threshold: HitCriterion | None = None,
    qc: dict | None = None,
    qualifier_handling: QualifierHandling | None = None,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="L",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=rule,
        qualifier_handling=qualifier_handling or QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
        qc_filter=qc,
        hit_threshold=threshold,
    )


def _candidate(
    value: float,
    run_date: date | None = None,
    *,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    approved: bool = True,
    z_prime: float | None = 0.7,
) -> ResolvedCandidate:
    return ResolvedCandidate(
        value=value,
        qualifier=qualifier,
        unit="nM",
        run_id=uuid.uuid4(),
        run_date=run_date,
        run_approved=approved,
        z_prime=z_prime,
        protocol_name="X",
        protocol_version=1,
        curve_id=uuid.uuid4(),
        readout_id=None,
    )


@pytest.mark.asyncio
async def test_latest_approved_run_picks_highest_run_date():
    ch = _channel(SelectionRule.LATEST_APPROVED_RUN)
    candidates = [
        _candidate(10.0, run_date=date(2026, 5, 1)),
        _candidate(20.0, run_date=date(2026, 4, 1)),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 10.0  # the May date


@pytest.mark.asyncio
async def test_mean_across_runs_averages():
    ch = _channel(SelectionRule.MEAN_ACROSS_RUNS)
    candidates = [_candidate(10.0), _candidate(20.0)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 15.0


@pytest.mark.asyncio
async def test_geometric_mean_logspace():
    ch = _channel(SelectionRule.GEOMETRIC_MEAN)
    candidates = [_candidate(10.0), _candidate(1000.0)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == pytest.approx(100.0)  # sqrt(10 * 1000)


@pytest.mark.asyncio
async def test_no_candidates_yields_nd():
    ch = _channel(SelectionRule.LATEST_APPROVED_RUN)
    resolver = ChannelResolver(_FakeQuery([]))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.value_qualifier == ValueQualifier.ND
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_hit_threshold_computes_hit():
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        threshold=HitCriterion(readout_name="IC50", operator="lt", value=1000.0),
    )
    candidates = [_candidate(42.0, run_date=date(2026, 5, 1))]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.hit_call == HitCall.HIT


@pytest.mark.asyncio
async def test_qc_filter_drops_low_z_prime():
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        qc={"min_z_prime": 0.5, "require_approved": True},
    )
    candidates = [_candidate(99.0, run_date=date(2026, 5, 1), z_prime=0.3)]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value_qualifier == ValueQualifier.ND


@pytest.mark.asyncio
async def test_qualifier_handling_excludes_qualified():
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.EXCLUDE_QUALIFIED,
    )
    candidates = [
        _candidate(10.0, qualifier=ValueQualifier.EQ),
        _candidate(99.0, qualifier=ValueQualifier.GT),  # excluded
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 10.0  # GT 99.0 was excluded before averaging
