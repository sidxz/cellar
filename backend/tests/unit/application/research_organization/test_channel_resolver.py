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
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey


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
    intercept_key: InterceptKey | None = None,
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
        intercept_key=intercept_key,
    )


def _candidate(
    value: float,
    run_date: date | None = None,
    *,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    approved: bool = True,
    z_prime: float | None = 0.7,
    intercept_values: list[dict] | None = None,
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
        intercept_values=intercept_values,
    )


def _iv(kind: str, level: float, value: float) -> dict:
    """JSONB-shaped intercept_values row, mirroring the persisted shape."""
    return {"spec": {"kind": kind, "level": level}, "value": value}


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
async def test_intercept_key_resolves_secondary_intercept_for_hit_call():
    """A channel that surfaces EC90 yields EC90's value as the cell value,
    and the threshold (`< 50`) compares against EC90 (80) → MISS."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.hit_call == HitCall.MISS
    assert m.value == 80.0  # the channel IS for EC90 — its value IS EC90


@pytest.mark.asyncio
async def test_intercept_key_none_keeps_legacy_primary_behavior():
    """No channel-level intercept_key → cell value is the primary fitted value."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)],
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 2.0
    assert m.hit_call == HitCall.HIT


@pytest.mark.asyncio
async def test_intercept_key_missing_match_yields_no_hit_call():
    """Channel targets EC90 but the curve only has EC50 → cell value None, hit_call None."""
    ch = _channel(
        SelectionRule.LATEST_APPROVED_RUN,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    candidates = [
        _candidate(
            2.0,
            run_date=date(2026, 5, 1),
            intercept_values=[_iv("ec", 50.0, 2.0)],  # no EC90 row
        )
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value is None
    assert m.hit_call is None


@pytest.mark.asyncio
async def test_intercept_key_aggregates_under_mean_selection():
    """MEAN_ACROSS_RUNS on a channel keyed to EC90 averages the EC90 values."""
    ch = _channel(
        SelectionRule.MEAN_ACROSS_RUNS,
        intercept_key=InterceptKey(kind="ec", level=90.0),
        threshold=HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
    )
    # EC90 values 80 and 100 average to 90 → MISS under lt 50.
    candidates = [
        _candidate(2.0, intercept_values=[_iv("ec", 50.0, 2.0), _iv("ec", 90.0, 80.0)]),
        _candidate(4.0, intercept_values=[_iv("ec", 50.0, 4.0), _iv("ec", 90.0, 100.0)]),
    ]
    resolver = ChannelResolver(_FakeQuery(candidates))
    m = await resolver.resolve(
        workspace_id=uuid.uuid4(),
        channel=ch,
        result_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert m.value == 90.0  # mean of the EC90 values
    assert m.hit_call == HitCall.MISS


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
